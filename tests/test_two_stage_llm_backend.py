import json
from unittest.mock import Mock, patch

import ai_backend
import ai_router
import ai_tools
import local_llm_backend
import two_stage_llm_backend


def _fake_http_response(body_dict):
    """Build a mock object usable as the `with urllib.request.urlopen(...)
    as response:` context manager result - .read() returns the JSON-
    encoded body, exactly like a real urllib response."""
    resp = Mock()
    resp.read.return_value = json.dumps(body_dict).encode("utf-8")
    resp.__enter__ = Mock(return_value=resp)
    resp.__exit__ = Mock(return_value=False)
    return resp


def _fake_structured_response(parsed_content):
    """Build a fake Ollama /api/chat response whose message.content is
    the JSON-encoded string a structured-output-constrained model
    would produce."""
    return _fake_http_response({
        "message": {"content": json.dumps(parsed_content)}
    })


def _sequenced_urlopen(*responses):
    """Return a Mock suitable for `side_effect=` that yields each
    response in order across successive urlopen() calls - this
    backend makes TWO Ollama calls per converse() (stage 1 then stage
    2), unlike its single-call predecessor."""
    return list(responses)


def teardown_function(_fn):
    """A couple of tests below register a real TwoStageLocalLLMBackend
    through ai_backend.register_backend() to prove the full ai_router
    chain - always restore the Phase 12.1 "no backend" default after."""
    ai_backend.register_backend(None)


# ---------------------------------------------------------------------
# TwoStageLocalLLMBackend is a real AIBackend, built on LocalLLMBackend
# ---------------------------------------------------------------------

def test_two_stage_backend_is_an_ai_backend():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    assert isinstance(backend, ai_backend.AIBackend)
    assert isinstance(backend, local_llm_backend.LocalLLMBackend)


def test_two_stage_backend_reuses_parent_defaults():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    assert backend.model == local_llm_backend.DEFAULT_MODEL
    assert backend.url == local_llm_backend.DEFAULT_OLLAMA_URL
    assert backend.timeout == local_llm_backend.DEFAULT_TIMEOUT_SECONDS


# ---------------------------------------------------------------------
# Stage-1 schema structurally CANNOT select a tool (Task 6)
# ---------------------------------------------------------------------

def test_stage1_schema_has_no_tool_or_argument_fields():
    props = two_stage_llm_backend.STAGE1_SCHEMA["properties"]
    assert set(props.keys()) == {"decision"}
    assert props["decision"]["enum"] == ["tool", "text"]


def test_first_ollama_call_uses_stage1_schema_not_tools():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    resp = _fake_structured_response({"decision": "text"})
    text_resp = _fake_structured_response({"text": "hi"})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(resp, text_resp),
    ) as mock_urlopen:
        backend.converse("hello", context=None)

    first_call_body = json.loads(mock_urlopen.call_args_list[0][0][0].data.decode("utf-8"))
    assert first_call_body["format"] == two_stage_llm_backend.STAGE1_SCHEMA
    assert "tools" not in first_call_body


# ---------------------------------------------------------------------
# Stage-2 tool schema is derived LIVE from TOOL_REGISTRY, never
# hand-copied (Task 9/10), and has NO text variant (Task 8)
# ---------------------------------------------------------------------

def test_stage2_tool_schema_variants_match_tool_registry_names_exactly():
    schema = two_stage_llm_backend.build_stage2_tool_schema()
    variant_tool_names = {v["properties"]["tool"]["const"] for v in schema["oneOf"]}
    assert variant_tool_names == set(ai_tools.TOOL_REGISTRY.keys())


def test_stage2_tool_schema_has_no_text_variant():
    schema = two_stage_llm_backend.build_stage2_tool_schema()
    for variant in schema["oneOf"]:
        assert "text" not in variant["properties"]
        assert variant["properties"]["tool"]["const"] in ai_tools.TOOL_REGISTRY


def test_stage2_tool_schema_argument_properties_and_enums_match_tool_registry():
    schema = two_stage_llm_backend.build_stage2_tool_schema()
    by_tool = {v["properties"]["tool"]["const"]: v for v in schema["oneOf"]}

    for name, spec in ai_tools.TOOL_REGISTRY.items():
        variant = by_tool[name]
        arg_schema = variant["properties"]["arguments"]

        assert set(arg_schema["properties"].keys()) == set(spec.args.keys())
        assert set(arg_schema["required"]) == set(spec.args.keys())
        assert arg_schema["additionalProperties"] is False

        for arg_name, allowed in spec.args.items():
            prop = arg_schema["properties"][arg_name]
            if allowed is ai_tools.FREE_TEXT:
                assert prop == {"type": "string"}
            else:
                assert prop == {"type": "string", "enum": sorted(allowed)}


def test_stage2_tool_schema_reflects_a_registry_change_live_not_a_stale_snapshot():
    original_registry = dict(ai_tools.TOOL_REGISTRY)
    try:
        ai_tools.TOOL_REGISTRY["totally_new_fake_tool"] = ai_tools.ToolSpec(
            name="totally_new_fake_tool",
            args={"mode": frozenset({"a", "b"})},
            render=lambda mode: f"fake {mode}",
        )

        schema = two_stage_llm_backend.build_stage2_tool_schema()
        variant_tool_names = {v["properties"]["tool"]["const"] for v in schema["oneOf"]}
        assert "totally_new_fake_tool" in variant_tool_names
    finally:
        ai_tools.TOOL_REGISTRY.clear()
        ai_tools.TOOL_REGISTRY.update(original_registry)

    schema_after = two_stage_llm_backend.build_stage2_tool_schema()
    variant_tool_names_after = {v["properties"]["tool"]["const"] for v in schema_after["oneOf"]}
    assert "totally_new_fake_tool" not in variant_tool_names_after


def test_backend_instance_caches_stage2_schema_built_from_current_registry():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    assert backend._stage2_tool_schema == two_stage_llm_backend.build_stage2_tool_schema()


# ---------------------------------------------------------------------
# Valid TOOL classification (stage1=tool -> stage2 tool call)
# ---------------------------------------------------------------------

def test_valid_tool_classification_and_resolution():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "scroll", "arguments": {"direction": "down"}}
    )

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ) as mock_urlopen:
        result = backend.converse("scroll down", context=None)

    assert result.kind == ai_backend.ResponseKind.TOOL_CALL
    assert result.tool_call.tool_name == "scroll"
    assert result.tool_call.arguments == {"direction": "down"}

    second_call_body = json.loads(mock_urlopen.call_args_list[1][0][0].data.decode("utf-8"))
    assert second_call_body["format"] == backend._stage2_tool_schema


def test_stage2_tool_call_only_made_when_stage1_says_tool():
    """Stage 2 is never even invoked for a text decision - only ONE
    HTTP call happens for the text-generation path plus classification
    (two total), and the second one uses the TEXT schema, never the
    tool schema (Task 8)."""
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response({"text": "I can't do that."})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ) as mock_urlopen:
        result = backend.converse("execute python", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT
    assert mock_urlopen.call_count == 2
    second_call_body = json.loads(mock_urlopen.call_args_list[1][0][0].data.decode("utf-8"))
    assert second_call_body["format"] == two_stage_llm_backend.STAGE2_TEXT_SCHEMA


# ---------------------------------------------------------------------
# Valid TEXT classification (Task: TEXT classification / conversational
# prompts)
# ---------------------------------------------------------------------

def test_valid_text_classification_and_generation():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response({"text": "I'm just a program, thanks for asking!"})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("how are you?", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT
    assert result.text == "I'm just a program, thanks for asking!"


def test_conversational_prompt_never_reaches_stage2_tool_schema():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response({"text": "Why did the chicken cross the road?"})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ) as mock_urlopen:
        backend.converse("tell me a joke", context=None)

    second_call_body = json.loads(mock_urlopen.call_args_list[1][0][0].data.decode("utf-8"))
    assert second_call_body["format"] != backend._stage2_tool_schema


# ---------------------------------------------------------------------
# Task 15: conservative decision rule - anything other than an EXACT
# "tool" match defaults to text, without raising
# ---------------------------------------------------------------------

def test_missing_decision_field_defaults_to_text_not_an_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({})  # no "decision" key at all
    stage2 = _fake_structured_response({"text": "Could you rephrase that?"})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("mumble mumble", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT


def test_unrecognized_decision_value_defaults_to_text_not_an_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "maybe"})
    stage2 = _fake_structured_response({"text": "I'm not sure I understand."})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("something odd", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT


def test_wrong_typed_decision_value_defaults_to_text_not_an_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": 1})
    stage2 = _fake_structured_response({"text": "Hmm."})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("???", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT


# ---------------------------------------------------------------------
# Roman Urdu - short commands must not be defaulted to text (the
# specific Phase 12.2.6 regression this phase must address)
# ---------------------------------------------------------------------

def test_roman_urdu_wapas_jao_classified_as_tool_resolves_to_browser_back():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "browser_navigation", "arguments": {"direction": "back"}}
    )

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("wapas jao", context=None)

    assert result.kind == ai_backend.ResponseKind.TOOL_CALL
    assert result.tool_call.tool_name == "browser_navigation"
    assert result.tool_call.arguments == {"direction": "back"}


def test_roman_urdu_aagay_jao_classified_as_tool_resolves_to_browser_forward():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "browser_navigation", "arguments": {"direction": "forward"}}
    )

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("aagay jao", context=None)

    assert result.kind == ai_backend.ResponseKind.TOOL_CALL
    assert result.tool_call.tool_name == "browser_navigation"
    assert result.tool_call.arguments == {"direction": "forward"}


def test_roman_urdu_chrome_kholo_resolves_to_open_application():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "open_application", "arguments": {"application": "chrome"}}
    )

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("chrome kholo", context=None)

    assert result.kind == ai_backend.ResponseKind.TOOL_CALL
    assert result.tool_call.tool_name == "open_application"
    assert result.tool_call.arguments == {"application": "chrome"}


def test_roman_urdu_niche_scroll_karo_resolves_to_scroll_down():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "scroll", "arguments": {"direction": "down"}}
    )

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("niche scroll karo", context=None)

    assert result.kind == ai_backend.ResponseKind.TOOL_CALL
    assert result.tool_call.tool_name == "scroll"
    assert result.tool_call.arguments == {"direction": "down"}


def test_stage1_prompt_explicitly_covers_required_roman_urdu_examples():
    """Task spec requires explicit few-shots for these phrases in the
    stage-1 prompt - not left to generalization alone."""
    prompt = two_stage_llm_backend.STAGE1_SYSTEM_PROMPT
    for phrase in ("chrome kholo", "niche scroll karo", "wapas jao", "aagay jao",
                   "open chrome", "scroll down"):
        assert phrase in prompt


def test_stage1_prompt_explicitly_covers_required_text_refusal_examples():
    prompt = two_stage_llm_backend.STAGE1_SYSTEM_PROMPT
    for phrase in ("what can you do?", "how are you?", "tell me a joke",
                   "execute python", "run powershell", "lock the computer",
                   "shutdown the computer", "restart the computer",
                   "delete my files", "set thermostat to 72"):
        assert phrase in prompt


# ---------------------------------------------------------------------
# Dangerous / arbitrary shell-execution prompts - stage 1 should say
# text; even if it didn't, the registry structurally has no dangerous
# tool and ai_router still fails closed on anything invalid (Task:
# dangerous prompts / arbitrary shell/PowerShell/Python prompts)
# ---------------------------------------------------------------------

def test_dangerous_prompt_resolved_as_text_never_reaches_tool_schema():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response(
        {"text": "I can't do that - there's no tool for locking the computer."}
    )

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ) as mock_urlopen:
        result = backend.converse("lock the computer", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT
    second_call_body = json.loads(mock_urlopen.call_args_list[1][0][0].data.decode("utf-8"))
    assert second_call_body["format"] == two_stage_llm_backend.STAGE2_TEXT_SCHEMA


def test_hallucinated_dangerous_tool_name_fails_closed_via_router():
    """Even in the worst case - stage 1 wrongly says "tool" AND stage 2
    hallucinates a tool name that isn't in the registry at all - the
    unmodified ai_router/ai_tools validation boundary still rejects
    it. Proves Task 12/17 hold even under a doubly-wrong model output."""
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "shutdown_computer", "arguments": {}}
    )
    ai_backend.register_backend(backend)

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        outcome = ai_router.handle("shut down the pc", context=None)

    assert outcome is None


def test_arbitrary_shell_command_prompt_resolved_as_text():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response(
        {"text": "I don't have a way to execute shell commands."}
    )

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("run powershell", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT


def test_arbitrary_python_execution_prompt_resolved_as_text():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response(
        {"text": "I can't execute Python code."}
    )

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        result = backend.converse("execute python", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT


# ---------------------------------------------------------------------
# Raw/unvalidated passthrough: this backend never filters bad tool
# names/enums/args itself - ai_tools/ai_router does, downstream
# ---------------------------------------------------------------------

def test_backend_passes_through_invalid_tool_name_raw_and_router_rejects_it():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "run_shell_command", "arguments": {"cmd": "rm -rf /"}}
    )
    ai_backend.register_backend(backend)

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        outcome = ai_router.handle("do something weird", context=None)

    assert outcome is None


def test_invalid_enum_is_passed_through_raw_and_router_rejects_it():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "scroll", "arguments": {"direction": "sideways"}}
    )
    ai_backend.register_backend(backend)

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        outcome = ai_router.handle("scroll sideways", context=None)

    assert outcome is None


def test_missing_argument_is_passed_through_raw_and_router_rejects_it():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response({"tool": "scroll", "arguments": {}})
    ai_backend.register_backend(backend)

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        outcome = ai_router.handle("scroll", context=None)

    assert outcome is None


def test_extra_argument_is_passed_through_raw_and_router_rejects_it():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "scroll", "arguments": {"direction": "down", "extra": "unexpected"}}
    )
    ai_backend.register_backend(backend)

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        outcome = ai_router.handle("scroll down please", context=None)

    assert outcome is None


def test_dangerous_enum_value_smuggled_into_a_real_tool_fails_closed():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "press_key", "arguments": {"key": "delete"}}
    )
    ai_backend.register_backend(backend)

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        outcome = ai_router.handle("press delete", context=None)

    assert outcome is None


# ---------------------------------------------------------------------
# Malformed stage-1 responses (hard failures - fail closed via
# exception, distinct from Task 15's soft "unrecognized value" case)
# ---------------------------------------------------------------------

def test_stage1_non_json_content_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    resp = _fake_http_response({"message": {"content": "not valid json {{"}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage1_content_that_is_a_json_array_not_object_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    resp = _fake_structured_response(["not", "an", "object"])

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage1_empty_content_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    resp = _fake_http_response({"message": {"content": ""}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("do something vague", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage1_missing_message_key_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    resp = _fake_http_response({})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("do something vague", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


# ---------------------------------------------------------------------
# Malformed stage-2 responses (both branches)
# ---------------------------------------------------------------------

def test_stage2_tool_non_json_content_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_http_response({"message": {"content": "not json {{"}})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        try:
            backend.converse("scroll down", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_tool_missing_tool_field_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response({"arguments": {"direction": "down"}})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        try:
            backend.converse("scroll down", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_tool_non_object_arguments_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response({"tool": "scroll", "arguments": "down"})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        try:
            backend.converse("scroll down", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_tool_content_that_is_a_json_array_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(["not", "an", "object"])

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        try:
            backend.converse("scroll down", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_tool_empty_content_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_http_response({"message": {"content": ""}})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        try:
            backend.converse("scroll down", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_text_missing_text_field_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response({})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        try:
            backend.converse("hello", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_text_blank_text_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response({"text": "   "})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        try:
            backend.converse("hello", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_text_non_string_text_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response({"text": 12345})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        try:
            backend.converse("hello", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


# ---------------------------------------------------------------------
# Ollama connectivity errors - proven for BOTH stages
# ---------------------------------------------------------------------

def test_stage1_ollama_connection_failure_raises_ollama_error():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=ConnectionRefusedError("target refused connection"),
    ):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage1_ollama_timeout_raises_ollama_error():
    import socket

    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=socket.timeout("timed out"),
    ):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_ollama_connection_failure_raises_ollama_error():
    """Stage 1 succeeds (decision=tool), but the server goes away
    before stage 2 completes - still fails closed via exception, never
    silently falls back to executing a guessed tool."""
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=[stage1, ConnectionRefusedError("target refused connection")],
    ):
        try:
            backend.converse("scroll down", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_stage2_ollama_timeout_raises_ollama_error():
    import socket

    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=[stage1, socket.timeout("timed out")],
    ):
        try:
            backend.converse("hello", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


# ---------------------------------------------------------------------
# End-to-end through ai_router
# ---------------------------------------------------------------------

def test_end_to_end_valid_tool_call_resolves_to_canonical_command_via_router():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "tool"})
    stage2 = _fake_structured_response(
        {"tool": "open_application", "arguments": {"application": "chrome"}}
    )
    ai_backend.register_backend(backend)

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        outcome = ai_router.handle("chrome kholo", context=None)

    assert outcome is not None
    assert outcome.kind == ai_router.RoutingOutcome.COMMAND
    assert outcome.value == "open chrome"


def test_end_to_end_text_response_resolves_to_speech_via_router():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    stage1 = _fake_structured_response({"decision": "text"})
    stage2 = _fake_structured_response({"text": "I'm not sure how to help with that."})
    ai_backend.register_backend(backend)

    with patch(
        "local_llm_backend.urllib.request.urlopen",
        side_effect=_sequenced_urlopen(stage1, stage2),
    ):
        outcome = ai_router.handle("tell me a joke", context=None)

    assert outcome is not None
    assert outcome.kind == ai_router.RoutingOutcome.SPEECH
    assert outcome.value == "I'm not sure how to help with that."


def test_end_to_end_backend_exception_fails_closed_via_router():
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", side_effect=OSError("down")):
        outcome = ai_router.handle("open chrome", context=None)

    assert outcome is None


# ---------------------------------------------------------------------
# Deterministic-first routing: this backend is never even reached for
# a command the deterministic dispatch chain already recognizes (Task:
# deterministic-first routing). ai_router.handle() is only ever called
# by commands.py AFTER the full deterministic chain has already failed
# - proven here the same way test_ai_startup_wiring.py's own spy tests
# prove it for the wiring layer: a backend that raises if consulted at
# all, run through the real CommandProcessor.
# ---------------------------------------------------------------------

def test_deterministic_command_never_reaches_this_backend_via_router():
    import commands

    class _ExplodingBackend(ai_backend.AIBackend):
        def converse(self, command, context):
            raise AssertionError(f"AI layer reached for deterministic command: {command!r}")

    ai_backend.register_backend(_ExplodingBackend())
    voice = Mock()
    processor = commands.CommandProcessor(voice)

    import config
    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    voice.speak.assert_called_with("Opening Chrome.")


# ---------------------------------------------------------------------
# Structural safety: no execution primitive imported (Task 13/16/17)
# ---------------------------------------------------------------------

def test_module_never_imports_dangerous_capabilities():
    import inspect

    source = inspect.getsource(two_stage_llm_backend)

    forbidden = (
        "import subprocess", "import os", "import ctypes", "import voice",
        "import web_control", "import system_control", "import window_control",
        "import volume_control", "import media_control", "import screen_control",
        "import keyboard_control", "import mouse_control", "import input_control",
        "import commands", "eval(", "exec(",
    )

    for token in forbidden:
        assert token not in source, f"two_stage_llm_backend.py must never contain {token!r}"


def test_module_never_calls_ai_tools_validate_or_process_itself():
    """This backend must never pre-validate a tool call itself - Task
    12 requires ai_router.py's unmodified _resolve() to remain the
    SOLE caller of ai_tools.validate_tool_call()/process_tool_call().
    Walks the actual AST for `ai_tools.<name>(...)` call nodes rather
    than substring-matching the source text, so this can't false-
    positive on the module's own docstring/comments explaining (in
    prose) why those calls are deliberately absent from the code."""
    import ast
    import inspect

    source = inspect.getsource(two_stage_llm_backend)
    tree = ast.parse(source)

    forbidden_calls = {"validate_tool_call", "process_tool_call", "resolve_to_canonical_command"}
    found = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden_calls
        ):
            found.append(node.func.attr)

    assert found == [], f"two_stage_llm_backend.py must never call: {found}"


def test_registry_structurally_cannot_render_dangerous_commands():
    """Even a maximally-wrong stage-2 output can only ever name a tool
    that exists in TOOL_REGISTRY - and the registry itself cannot
    render lock/shutdown/restart (see ai_tools.py's own docstring and
    test_ai_tools.py's exhaustive sweep, unaffected by this module).
    Sanity-checked here directly against the schema this backend
    actually sends to Ollama."""
    schema = two_stage_llm_backend.build_stage2_tool_schema()
    dangerous_strings = {"lock computer", "shutdown computer", "restart computer"}

    for variant in schema["oneOf"]:
        name = variant["properties"]["tool"]["const"]
        spec = ai_tools.TOOL_REGISTRY[name]
        # exhaustively render every enum combination for this tool and
        # confirm none of them can ever equal a dangerous string
        import itertools
        arg_names = list(spec.args.keys())
        value_options = [
            sorted(allowed) if allowed is not ai_tools.FREE_TEXT else ["x"]
            for allowed in spec.args.values()
        ]
        for combo in itertools.product(*value_options) if arg_names else [()]:
            kwargs = dict(zip(arg_names, combo))
            rendered = spec.render(**kwargs)
            assert rendered not in dangerous_strings
