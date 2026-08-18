import json
from unittest.mock import Mock, patch

import ai_backend
import ai_router
import ai_tools
import local_llm_backend


def _fake_http_response(body_dict):
    """Build a mock object usable as the `with urllib.request.urlopen(...)
    as response:` context manager result - .read() returns the JSON-
    encoded body, exactly like a real urllib response."""
    resp = Mock()
    resp.read.return_value = json.dumps(body_dict).encode("utf-8")
    resp.__enter__ = Mock(return_value=resp)
    resp.__exit__ = Mock(return_value=False)
    return resp


def teardown_function(_fn):
    """A couple of tests below register a real LocalLLMBackend through
    ai_backend.register_backend() to prove the full ai_router chain -
    always restore the Phase 12.1 "no backend" default afterward."""
    ai_backend.register_backend(None)


# ---------------------------------------------------------------------
# LocalLLMBackend is a real AIBackend
# ---------------------------------------------------------------------

def test_local_llm_backend_is_an_ai_backend():
    backend = local_llm_backend.LocalLLMBackend()
    assert isinstance(backend, ai_backend.AIBackend)


def test_default_model_and_url():
    backend = local_llm_backend.LocalLLMBackend()
    assert backend.model == local_llm_backend.DEFAULT_MODEL
    assert backend.url == local_llm_backend.DEFAULT_OLLAMA_URL


def test_custom_model_and_url_are_used_in_the_request():
    backend = local_llm_backend.LocalLLMBackend(model="custom:model", url="http://example.invalid/api/chat")
    resp = _fake_http_response({"message": {"content": "hi"}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp) as mock_urlopen:
        backend.converse("hello", context=None)

    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "http://example.invalid/api/chat"
    sent = json.loads(request.data.decode("utf-8"))
    assert sent["model"] == "custom:model"


# ---------------------------------------------------------------------
# build_tool_schema() - derived from ai_tools.TOOL_REGISTRY, never
# hand-copied
# ---------------------------------------------------------------------

def test_tool_schema_names_match_tool_registry_exactly():
    schema = local_llm_backend.build_tool_schema()
    schema_names = {t["function"]["name"] for t in schema}
    assert schema_names == set(ai_tools.TOOL_REGISTRY.keys())


def test_tool_schema_enums_match_tool_registry_allowed_values():
    schema = {t["function"]["name"]: t for t in local_llm_backend.build_tool_schema()}
    for name, spec in ai_tools.TOOL_REGISTRY.items():
        properties = schema[name]["function"]["parameters"]["properties"]
        for arg_name, allowed in spec.args.items():
            if allowed is ai_tools.FREE_TEXT:
                assert "enum" not in properties[arg_name]
            else:
                assert properties[arg_name]["enum"] == sorted(allowed)


def test_tool_schema_required_matches_every_declared_argument():
    schema = {t["function"]["name"]: t for t in local_llm_backend.build_tool_schema()}
    for name, spec in ai_tools.TOOL_REGISTRY.items():
        required = schema[name]["function"]["parameters"]["required"]
        assert set(required) == set(spec.args.keys())


def test_refresh_tool_has_no_arguments():
    schema = {t["function"]["name"]: t for t in local_llm_backend.build_tool_schema()}
    params = schema["refresh"]["function"]["parameters"]
    assert params["properties"] == {}
    assert params["required"] == []


# ---------------------------------------------------------------------
# converse() - request shape
# ---------------------------------------------------------------------

def test_converse_sends_system_prompt_user_command_and_tools():
    backend = local_llm_backend.LocalLLMBackend()
    resp = _fake_http_response({"message": {"content": "ok"}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp) as mock_urlopen:
        backend.converse("open chrome", context={"turn": 1})

    request = mock_urlopen.call_args[0][0]
    sent = json.loads(request.data.decode("utf-8"))
    assert sent["stream"] is False
    assert sent["messages"][0] == {"role": "system", "content": local_llm_backend.SYSTEM_PROMPT}
    assert sent["messages"][1] == {"role": "user", "content": "open chrome"}
    assert [t["function"]["name"] for t in sent["tools"]] == list(ai_tools.TOOL_REGISTRY.keys())


def test_converse_passes_timeout_to_urlopen():
    backend = local_llm_backend.LocalLLMBackend(timeout=5)
    resp = _fake_http_response({"message": {"content": "ok"}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp) as mock_urlopen:
        backend.converse("hi", context=None)

    assert mock_urlopen.call_args.kwargs["timeout"] == 5


# ---------------------------------------------------------------------
# converse() - tool-call responses
# ---------------------------------------------------------------------

def test_converse_returns_tool_response_for_a_single_tool_call():
    backend = local_llm_backend.LocalLLMBackend()
    ollama_body = {
        "message": {
            "tool_calls": [
                {"function": {"name": "scroll", "arguments": {"direction": "down"}}}
            ],
            "content": "",
        }
    }
    resp = _fake_http_response(ollama_body)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        result = backend.converse("scroll down", context=None)

    assert isinstance(result, ai_backend.AIResponse)
    assert result.kind == ai_backend.ResponseKind.TOOL_CALL
    assert result.tool_call.tool_name == "scroll"
    assert result.tool_call.arguments == {"direction": "down"}


def test_converse_uses_only_the_first_tool_call_when_several_are_returned():
    backend = local_llm_backend.LocalLLMBackend()
    ollama_body = {
        "message": {
            "tool_calls": [
                {"function": {"name": "scroll", "arguments": {"direction": "down"}}},
                {"function": {"name": "refresh", "arguments": {}}},
            ],
            "content": "",
        }
    }
    resp = _fake_http_response(ollama_body)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        result = backend.converse("do stuff", context=None)

    assert result.tool_call.tool_name == "scroll"


def test_converse_passes_raw_unvalidated_arguments_through_unmodified():
    """LocalLLMBackend must NOT pre-validate or filter tool-call
    arguments itself - even a hallucinated, dangerous-looking value
    (e.g. a nonexistent 'lock' key, mirroring the actual Qwen output
    observed in the Phase 12.2.2 security benchmark) must pass through
    as-is. Rejecting it is ai_tools.validate_tool_call()'s job, proven
    below via ai_router.handle(), not this module's."""
    backend = local_llm_backend.LocalLLMBackend()
    ollama_body = {
        "message": {
            "tool_calls": [{"function": {"name": "press_key", "arguments": {"key": "lock"}}}],
            "content": "",
        }
    }
    resp = _fake_http_response(ollama_body)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        result = backend.converse("Lock the computer.", context=None)

    assert result.tool_call.tool_name == "press_key"
    assert result.tool_call.arguments == {"key": "lock"}

    ai_backend.register_backend(backend)
    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("Lock the computer.")
    assert outcome is None  # rejected by ai_tools - fails closed


# ---------------------------------------------------------------------
# converse() - text responses
# ---------------------------------------------------------------------

def test_converse_returns_text_response_when_no_tool_calls():
    backend = local_llm_backend.LocalLLMBackend()
    resp = _fake_http_response({"message": {"content": "Hello! How can I help?"}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        result = backend.converse("Hello Jarvis.", context=None)

    assert result.kind == ai_backend.ResponseKind.TEXT
    assert result.text == "Hello! How can I help?"


def test_converse_strips_surrounding_whitespace_from_text():
    backend = local_llm_backend.LocalLLMBackend()
    resp = _fake_http_response({"message": {"content": "  hi there  \n"}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        result = backend.converse("hi", context=None)

    assert result.text == "hi there"


# ---------------------------------------------------------------------
# converse() - failure modes: must raise OllamaError, never return None
# ---------------------------------------------------------------------

def test_converse_raises_when_response_has_neither_tool_call_nor_text():
    """The real anomaly observed twice in the Phase 12.2.2 benchmark
    ('double click', 'awaaz kam karo'): Ollama returns a 200 with an
    empty message. Must raise, not silently return something that
    could be misread as a valid outcome."""
    backend = local_llm_backend.LocalLLMBackend()
    resp = _fake_http_response({"message": {"content": "", "tool_calls": []}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("double click", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_converse_raises_on_connection_failure():
    backend = local_llm_backend.LocalLLMBackend()

    with patch("local_llm_backend.urllib.request.urlopen", side_effect=OSError("connection refused")):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_converse_raises_on_invalid_json_response():
    backend = local_llm_backend.LocalLLMBackend()
    resp = Mock()
    resp.read.return_value = b"not json"
    resp.__enter__ = Mock(return_value=resp)
    resp.__exit__ = Mock(return_value=False)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        try:
            backend.converse("open chrome", context=None)
            assert False, "expected OllamaError"
        except local_llm_backend.OllamaError:
            pass


def test_converse_never_returns_none():
    """Structural contract from ai_backend.AIBackend.converse(): must
    return an AIResponse or raise - covered across every branch above,
    asserted explicitly here for the success paths."""
    backend = local_llm_backend.LocalLLMBackend()
    resp = _fake_http_response({"message": {"content": "text reply"}})
    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        result = backend.converse("hi", context=None)
    assert result is not None


# ---------------------------------------------------------------------
# ai_router.handle() end-to-end with a real LocalLLMBackend + mocked HTTP
# ---------------------------------------------------------------------

def test_end_to_end_valid_tool_call_resolves_to_canonical_command_via_router():
    backend = local_llm_backend.LocalLLMBackend()
    ai_backend.register_backend(backend)
    ollama_body = {
        "message": {
            "tool_calls": [{"function": {"name": "open_application", "arguments": {"application": "chrome"}}}],
            "content": "",
        }
    }
    resp = _fake_http_response(ollama_body)

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("open chrome")

    assert outcome.kind == ai_router.RoutingOutcome.COMMAND
    assert outcome.value == "open chrome"


def test_end_to_end_text_response_resolves_to_speech_via_router():
    backend = local_llm_backend.LocalLLMBackend()
    ai_backend.register_backend(backend)
    resp = _fake_http_response({"message": {"content": "I can't do that."}})

    with patch("local_llm_backend.urllib.request.urlopen", return_value=resp):
        outcome = ai_router.handle("Shut down the computer.")

    assert outcome.kind == ai_router.RoutingOutcome.SPEECH
    assert outcome.value == "I can't do that."


def test_end_to_end_backend_exception_fails_closed_via_router():
    backend = local_llm_backend.LocalLLMBackend()
    ai_backend.register_backend(backend)

    with patch("local_llm_backend.urllib.request.urlopen", side_effect=OSError("boom")):
        outcome = ai_router.handle("open chrome")

    assert outcome is None


# ---------------------------------------------------------------------
# Structural safety: this module cannot execute anything, even in
# principle - same discipline ai_tools.py's own tests already apply.
# ---------------------------------------------------------------------

def test_module_never_imports_dangerous_capabilities():
    """Same discipline as ai_tools.py's own structural safety test:
    check the exact 'import X' tokens, not prose substrings, so this
    doesn't false-positive on the module's own docstring explaining
    what it deliberately does NOT import."""
    import inspect
    source = inspect.getsource(local_llm_backend)

    forbidden = (
        "import subprocess", "import os", "import ctypes", "import voice",
        "import web_control", "import system_control", "import window_control",
        "import volume_control", "import media_control", "import screen_control",
        "import keyboard_control", "import mouse_control", "import input_control",
        "import commands", "eval(", "exec(",
    )

    for token in forbidden:
        assert token not in source, f"local_llm_backend.py must never contain {token!r}"
