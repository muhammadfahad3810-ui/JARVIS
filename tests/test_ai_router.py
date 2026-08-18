import ai_backend
import ai_router


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
    ai_backend.register_backend(None)


# ---------------------------------------------------------------------
# Phase 12.1 default state: no backend registered -> always None
# ---------------------------------------------------------------------

def test_handle_returns_none_when_no_backend_registered():
    """The actual current production state - no LLM is connected."""
    assert ai_router.handle("how are you?") is None


# ---------------------------------------------------------------------
# Tool-call responses - validated via ai_tools before becoming an
# outcome
# ---------------------------------------------------------------------

def test_handle_resolves_a_valid_tool_call_to_a_command_outcome():
    ai_backend.register_backend(
        _FakeBackend(response=ai_backend.AIResponse.tool("scroll", {"direction": "down"}))
    )

    outcome = ai_router.handle("scroll down please")

    assert outcome.kind == ai_router.RoutingOutcome.COMMAND
    assert outcome.value == "scroll down"


def test_handle_rejects_invalid_tool_call_and_returns_none():
    ai_backend.register_backend(
        _FakeBackend(response=ai_backend.AIResponse.tool("shutdown_now", {}))
    )

    assert ai_router.handle("do something bad") is None


def test_handle_rejects_tool_call_with_invalid_enum_value():
    ai_backend.register_backend(
        _FakeBackend(
            response=ai_backend.AIResponse.tool(
                "open_application", {"application": "malware.exe"}
            )
        )
    )

    assert ai_router.handle("open something") is None


def test_handle_rejects_tool_call_requesting_the_delete_key():
    ai_backend.register_backend(
        _FakeBackend(response=ai_backend.AIResponse.tool("press_key", {"key": "delete"}))
    )

    assert ai_router.handle("press delete") is None


# ---------------------------------------------------------------------
# Text responses - a SPEECH outcome, never a COMMAND outcome
# ---------------------------------------------------------------------

def test_handle_resolves_text_response_to_a_speech_outcome():
    ai_backend.register_backend(
        _FakeBackend(response=ai_backend.AIResponse.speak("I'm doing well, thank you!"))
    )

    outcome = ai_router.handle("how are you?")

    assert outcome.kind == ai_router.RoutingOutcome.SPEECH
    assert outcome.value == "I'm doing well, thank you!"


def test_text_response_containing_a_dangerous_phrase_is_never_a_command_outcome():
    """The core 'confused deputy' guard: even if a (hostile or buggy)
    backend returns TEXT that happens to contain a dangerous-sounding
    phrase, the outcome is ALWAYS kind=SPEECH, never kind=COMMAND - the
    caller (commands.py) is structurally prevented from ever recursing
    this through process()."""

    ai_backend.register_backend(
        _FakeBackend(response=ai_backend.AIResponse.speak("Sure, let me shutdown computer for you"))
    )

    outcome = ai_router.handle("do something")

    assert outcome.kind == ai_router.RoutingOutcome.SPEECH
    assert outcome.value == "Sure, let me shutdown computer for you"


# ---------------------------------------------------------------------
# Failure modes all fail closed (None), never raise
# ---------------------------------------------------------------------

def test_handle_returns_none_when_backend_raises():
    ai_backend.register_backend(_FakeBackend(error=RuntimeError("model unavailable")))

    assert ai_router.handle("anything") is None  # must not raise


def test_handle_returns_none_when_backend_returns_none():
    ai_backend.register_backend(_FakeBackend(response=None))

    assert ai_router.handle("anything") is None


def test_handle_returns_none_when_backend_returns_garbage():
    ai_backend.register_backend(_FakeBackend(response="not an AIResponse"))

    assert ai_router.handle("anything") is None


def test_handle_passes_context_through_to_the_backend():
    backend = _FakeBackend(response=ai_backend.AIResponse.speak("ok"))
    ai_backend.register_backend(backend)

    fake_context = object()
    ai_router.handle("hello", context=fake_context)

    assert backend.calls == [("hello", fake_context)]


# ---------------------------------------------------------------------
# Every safe tool round-trips through the router end-to-end
# ---------------------------------------------------------------------

def test_every_registered_tool_resolves_through_the_router():
    import ai_tools

    cases = [
        ("open_application", {"application": "chrome"}, "open chrome"),
        ("press_key", {"key": "enter"}, "press enter"),
        ("scroll", {"direction": "up"}, "scroll up"),
        ("mouse_action", {"action": "click"}, "click"),
        ("volume", {"action": "mute"}, "mute"),
        ("media", {"action": "play_pause"}, "play"),
        ("tab_navigation", {"direction": "next"}, "next tab"),
        ("browser_navigation", {"direction": "back"}, "go back"),
        ("refresh", {}, "refresh"),
        ("search", {"query": "python"}, "search for python"),
    ]

    for tool_name, args, expected in cases:
        assert tool_name in ai_tools.TOOL_REGISTRY  # sanity: registry is in sync

        ai_backend.register_backend(
            _FakeBackend(response=ai_backend.AIResponse.tool(tool_name, args))
        )
        outcome = ai_router.handle(f"do {tool_name}")

        assert outcome.kind == ai_router.RoutingOutcome.COMMAND
        assert outcome.value == expected
