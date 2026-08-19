import json
from unittest.mock import Mock, patch

import ai_backend
import ai_router
import ai_tools
import local_llm_backend
import structured_llm_backend


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
    would produce - i.e. content is itself JSON TEXT, not a nested
    object (matching Ollama's real `format` behavior)."""
    return _fake_http_response({
        "message": {"content": json.dumps(parsed_content)}
    })


def teardown_function(_fn):
    """A couple of tests below register a real StructuredLocalLLMBackend
    through ai_backend.register_backend() to prove the full ai_router
    chain - always restore the Phase 12.1 "no backend" default after."""
    ai_backend.register_backend(None)


# ---------------------------------------------------------------------
# StructuredLocalLLMBackend is a real AIBackend, built on LocalLLMBackend
# ---------------------------------------------------------------------

def test_structured_backend_is_an_ai_backend():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    assert isinstance(backend, ai_backend.AIBackend)
    assert isinstance(backend, local_llm_backend.LocalLLMBackend)


def test_structured_backend_reuses_parent_defaults():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    assert backend.model == local_llm_backend.DEFAULT_MODEL
    assert backend.url == local_llm_backend.DEFAULT_OLLAMA_URL
    assert backend.timeout == local_llm_backend.DEFAULT_TIMEOUT_SECONDS


def test_converse_sends_format_schema_instead_of_tools():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "text", "text": "hi"}
    )

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp) as mock_urlopen:
        backend.converse("hello", context=None)

    sent = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert "format" in sent
    assert sent["format"] == structured_llm_backend.build_response_schema()
    assert "tools" not in sent


# ---------------------------------------------------------------------
# Schema is derived from TOOL_REGISTRY, never hand-duplicated (Task 12)
# ---------------------------------------------------------------------

def test_schema_tool_call_variants_match_tool_registry_names_exactly():
    schema = structured_llm_backend.build_response_schema()
    variant_tool_names = {
        v["properties"]["tool"]["const"]
        for v in schema["oneOf"]
        if v["properties"].get("response_type", {}).get("const") == "tool_call"
    }
    assert variant_tool_names == set(ai_tools.TOOL_REGISTRY.keys())


def test_schema_has_exactly_one_text_variant():
    schema = structured_llm_backend.build_response_schema()
    text_variants = [
        v for v in schema["oneOf"]
        if v["properties"].get("response_type", {}).get("const") == "text"
    ]
    assert len(text_variants) == 1
    assert text_variants[0]["properties"]["text"] == {"type": "string"}


def test_schema_argument_properties_and_enums_match_tool_registry():
    schema = structured_llm_backend.build_response_schema()
    by_tool = {
        v["properties"]["tool"]["const"]: v
        for v in schema["oneOf"]
        if v["properties"].get("response_type", {}).get("const") == "tool_call"
    }

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


def test_schema_additional_properties_false_on_every_tool_call_variant():
    """Structural proof no extra argument can even be generated."""
    schema = structured_llm_backend.build_response_schema()
    for variant in schema["oneOf"]:
        assert variant["additionalProperties"] is False


def test_schema_reflects_a_registry_change_live_not_a_stale_snapshot():
    """Task 12: prove build_response_schema() reads TOOL_REGISTRY at
    CALL time, not once at import time - a future registry addition (or
    removal) can never silently leave this schema stale, because there
    is no cached copy to go stale. Monkeypatches TOOL_REGISTRY with an
    extra fake tool, rebuilds the schema, and checks the new tool
    appears; restores the real registry immediately after."""
    original_registry = dict(ai_tools.TOOL_REGISTRY)
    try:
        ai_tools.TOOL_REGISTRY["totally_new_fake_tool"] = ai_tools.ToolSpec(
            name="totally_new_fake_tool",
            args={"mode": frozenset({"a", "b"})},
            render=lambda mode: f"fake {mode}",
        )

        schema = structured_llm_backend.build_response_schema()
        variant_tool_names = {
            v["properties"]["tool"]["const"]
            for v in schema["oneOf"]
            if v["properties"].get("response_type", {}).get("const") == "tool_call"
        }

        assert "totally_new_fake_tool" in variant_tool_names

        new_variant = next(
            v for v in schema["oneOf"]
            if v["properties"].get("tool", {}).get("const") == "totally_new_fake_tool"
        )
        assert new_variant["properties"]["arguments"]["properties"]["mode"] == {
            "type": "string", "enum": ["a", "b"],
        }
    finally:
        ai_tools.TOOL_REGISTRY.clear()
        ai_tools.TOOL_REGISTRY.update(original_registry)

    # And after restoring, the fake tool is gone from a freshly-built schema.
    schema_after = structured_llm_backend.build_response_schema()
    variant_tool_names_after = {
        v["properties"]["tool"]["const"]
        for v in schema_after["oneOf"]
        if v["properties"].get("response_type", {}).get("const") == "tool_call"
    }
    assert "totally_new_fake_tool" not in variant_tool_names_after


# ---------------------------------------------------------------------
# Valid responses (Task 11)
# ---------------------------------------------------------------------

def test_valid_structured_tool_call():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "tool": "scroll", "arguments": {"direction": "down"}}
    )

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        result = backend.converse("scroll down", context=None)

    assert result.kind == ai_backend.ResponseKind.TOOL_CALL
    assert result.tool_call.tool_name == "scroll"
    assert result.tool_call.arguments == {"direction": "down"}


def test_valid_text_response():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "text", "text": "I can help with that."}
    )

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        result = backend.converse("hello", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT
    assert result.text == "I can help with that."


# ---------------------------------------------------------------------
# Raw/unvalidated passthrough: this backend never filters bad tool
# names/enums/args itself - ai_tools/ai_router does, downstream (Task 11)
# ---------------------------------------------------------------------

def test_backend_passes_through_invalid_tool_name_raw_and_router_rejects_it():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "tool": "run_shell_command", "arguments": {"cmd": "rm -rf /"}}
    )
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("do something weird", context=None)

    assert outcome is None


def test_invalid_enum_is_passed_through_raw_and_router_rejects_it():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "tool": "scroll", "arguments": {"direction": "sideways"}}
    )
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("scroll sideways", context=None)

    assert outcome is None


def test_missing_argument_is_passed_through_raw_and_router_rejects_it():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "tool": "scroll", "arguments": {}}
    )
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("scroll", context=None)

    assert outcome is None


def test_extra_argument_is_passed_through_raw_and_router_rejects_it():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {
            "response_type": "tool_call",
            "tool": "scroll",
            "arguments": {"direction": "down", "extra": "unexpected"},
        }
    )
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("scroll down please", context=None)

    assert outcome is None


def test_dangerous_hallucinated_tool_fails_closed_via_router():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "tool": "shutdown_computer", "arguments": {}}
    )
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("shut down the pc", context=None)

    assert outcome is None


def test_dangerous_enum_value_smuggled_into_a_real_tool_fails_closed():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "tool": "press_key", "arguments": {"key": "delete"}}
    )
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("press delete", context=None)

    assert outcome is None


# ---------------------------------------------------------------------
# Malformed structured responses (Task 11)
# ---------------------------------------------------------------------

def test_malformed_non_json_content_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_http_response({"message": {"content": "not valid json {{"}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_content_that_is_a_json_array_not_object_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(["not", "an", "object"])

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_unrecognized_response_type_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response({"response_type": "something_else"})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_tool_call_missing_tool_field_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "arguments": {"direction": "down"}}
    )

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("scroll down", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_tool_call_non_object_arguments_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "tool": "scroll", "arguments": "down"}
    )

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("scroll down", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_text_response_with_missing_text_field_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response({"response_type": "text"})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("hello", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_text_response_with_blank_text_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response({"response_type": "text", "text": "   "})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("hello", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


# ---------------------------------------------------------------------
# Empty response (Task 11)
# ---------------------------------------------------------------------

def test_empty_content_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_http_response({"message": {"content": ""}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("do something vague", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_whitespace_only_content_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_http_response({"message": {"content": "   "}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("do something vague", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_missing_message_key_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_http_response({})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("do something vague", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


# ---------------------------------------------------------------------
# Ollama connectivity errors (Task 11) - inherited _call_ollama, but
# proven explicitly for THIS class/entry point, not just assumed
# ---------------------------------------------------------------------

def test_ollama_connection_failure_raises_ollama_error():
    backend = structured_llm_backend.StructuredLocalLLMBackend()

    with patch("local_llm_backend.urllib.request.urlopen",
               side_effect=ConnectionRefusedError("target refused connection")):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_ollama_timeout_raises_ollama_error():
    import socket

    backend = structured_llm_backend.StructuredLocalLLMBackend()

    with patch("local_llm_backend.urllib.request.urlopen",
               side_effect=socket.timeout("timed out")):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


# ---------------------------------------------------------------------
# End-to-end through ai_router (mirrors test_local_llm_backend.py)
# ---------------------------------------------------------------------

def test_end_to_end_valid_tool_call_resolves_to_canonical_command_via_router():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "tool_call", "tool": "open_application", "arguments": {"application": "chrome"}}
    )
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("chrome kholo", context=None)

    assert outcome is not None
    assert outcome.kind == ai_router.RoutingOutcome.COMMAND
    assert outcome.value == "open chrome"


def test_end_to_end_text_response_resolves_to_speech_via_router():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    resp = _fake_structured_response(
        {"response_type": "text", "text": "I'm not sure how to help with that."}
    )
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("tell me a joke", context=None)

    assert outcome is not None
    assert outcome.kind == ai_router.RoutingOutcome.SPEECH
    assert outcome.value == "I'm not sure how to help with that."


def test_end_to_end_backend_exception_fails_closed_via_router():
    backend = structured_llm_backend.StructuredLocalLLMBackend()
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", side_effect=OSError("down")):
        outcome = ai_router.handle("open chrome", context=None)

    assert outcome is None


# ---------------------------------------------------------------------
# Structural safety: no execution primitive imported (mirrors
# test_local_llm_backend.py's own equivalent test)
# ---------------------------------------------------------------------

def test_module_never_imports_dangerous_capabilities():
    """Same discipline as local_llm_backend.py's own equivalent test:
    check the exact 'import X' tokens, not prose substrings, so this
    doesn't false-positive on this module's own docstring explaining
    what it deliberately does NOT import."""
    import inspect

    source = inspect.getsource(structured_llm_backend)

    forbidden = (
        "import subprocess", "import os", "import ctypes", "import voice",
        "import web_control", "import system_control", "import window_control",
        "import volume_control", "import media_control", "import screen_control",
        "import keyboard_control", "import mouse_control", "import input_control",
        "import commands", "eval(", "exec(",
    )

    for token in forbidden:
        assert token not in source, f"structured_llm_backend.py must never contain {token!r}"
