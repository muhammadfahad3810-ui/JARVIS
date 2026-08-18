import ai_backend


class _FakeBackend(ai_backend.AIBackend):
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def converse(self, command, context):
        self.calls.append((command, context))
        if self.error is not None:
            raise self.error
        return self.response


def teardown_function(_fn):
    """Every test in this module registers a backend - always restore
    the Phase 12.1 "no backend" default afterward, so tests in other
    files never see a leftover fake backend."""
    ai_backend.register_backend(None)


# ---------------------------------------------------------------------
# get_backend() / register_backend() - Phase 12.1 default state
# ---------------------------------------------------------------------

def test_no_backend_registered_by_default():
    """The actual Phase 12.1 production state: no AI backend is ever
    registered in this phase."""
    assert ai_backend.get_backend() is None


def test_register_and_get_backend():
    backend = _FakeBackend()
    ai_backend.register_backend(backend)
    assert ai_backend.get_backend() is backend


def test_register_none_clears_the_backend():
    ai_backend.register_backend(_FakeBackend())
    ai_backend.register_backend(None)
    assert ai_backend.get_backend() is None


def test_register_backend_rejects_non_ai_backend_objects():
    for bad in ["not a backend", 42, object(), lambda: None]:
        try:
            ai_backend.register_backend(bad)
            assert False, f"expected TypeError for {bad!r}"
        except TypeError:
            pass


# ---------------------------------------------------------------------
# AIBackend - abstract, cannot be instantiated directly
# ---------------------------------------------------------------------

def test_ai_backend_cannot_be_instantiated_directly():
    try:
        ai_backend.AIBackend()
        assert False, "expected TypeError (abstract class)"
    except TypeError:
        pass


def test_subclass_must_implement_converse():
    class IncompleteBackend(ai_backend.AIBackend):
        pass

    try:
        IncompleteBackend()
        assert False, "expected TypeError (abstract method not implemented)"
    except TypeError:
        pass


def test_fake_backend_converse_is_called_with_command_and_context():
    backend = _FakeBackend(response=ai_backend.AIResponse.speak("hi"))
    backend.converse("hello there", context={"turn": 1})
    assert backend.calls == [("hello there", {"turn": 1})]


# ---------------------------------------------------------------------
# ToolCall - inert data only
# ---------------------------------------------------------------------

def test_tool_call_defaults_to_empty_arguments():
    call = ai_backend.ToolCall("refresh")
    assert call.tool_name == "refresh"
    assert call.arguments == {}


def test_tool_call_stores_arguments_verbatim():
    call = ai_backend.ToolCall("scroll", {"direction": "down"})
    assert call.tool_name == "scroll"
    assert call.arguments == {"direction": "down"}


def test_tool_call_has_no_execute_method():
    """Structural guarantee: ToolCall is pure data - it cannot execute
    anything, even in principle."""
    call = ai_backend.ToolCall("scroll", {"direction": "down"})
    dangerous_names = ["execute", "run", "call", "invoke", "__call__"]
    for name in dangerous_names:
        assert not hasattr(call, name)


# ---------------------------------------------------------------------
# AIResponse - exactly tool-call XOR text
# ---------------------------------------------------------------------

def test_response_tool_constructor():
    response = ai_backend.AIResponse.tool("scroll", {"direction": "down"})
    assert response.kind == ai_backend.ResponseKind.TOOL_CALL
    assert response.tool_call.tool_name == "scroll"
    assert response.tool_call.arguments == {"direction": "down"}
    assert response.text is None


def test_response_speak_constructor():
    response = ai_backend.AIResponse.speak("Hello, how can I help?")
    assert response.kind == ai_backend.ResponseKind.TEXT
    assert response.text == "Hello, how can I help?"
    assert response.tool_call is None


def test_response_tool_call_requires_a_tool_call():
    try:
        ai_backend.AIResponse(ai_backend.ResponseKind.TOOL_CALL, tool_call=None)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_response_text_requires_a_string():
    for bad_text in [None, 123, ["hi"], {"text": "hi"}]:
        try:
            ai_backend.AIResponse(ai_backend.ResponseKind.TEXT, text=bad_text)
            assert False, f"expected ValueError for text={bad_text!r}"
        except ValueError:
            pass


def test_response_has_no_way_to_carry_executable_code():
    """Structural guarantee: AIResponse's only fields are tool_call
    (inert data) and text (a plain string) - there is no field or
    method that could carry a callable, bytecode, or a reference to a
    control module."""
    response = ai_backend.AIResponse.speak("hello")
    assert response.__slots__ == ("kind", "tool_call", "text")
