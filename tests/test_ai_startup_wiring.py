"""Phase 12.2.5: startup-wiring tests for jarvis._initialize_ai_backend().

Everything that would touch the real world is mocked: voice.Voice and
speech.Speech (no real microphone/TTS engine), and (where a backend is
registered) StructuredLocalLLMBackend itself, so these tests never make
a real network call to Ollama. No control-module action ever runs.
"""

from unittest.mock import MagicMock, patch

import ai_backend
import config
import jarvis as jarvis_module
import structured_llm_backend


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def make_jarvis():
    """Build a real Jarvis instance with voice.Voice and speech.Speech
    replaced by fakes, so no real microphone or TTS engine is touched.
    Mirrors test_pipeline.py's own make_jarvis() helper."""

    with patch("jarvis.voice.Voice") as mock_voice_cls, \
         patch("jarvis.speech.Speech") as mock_speech_cls:

        fake_voice = FakeVoice()
        mock_voice_cls.return_value = fake_voice

        fake_speech = MagicMock()
        mock_speech_cls.return_value = fake_speech

        j = jarvis_module.Jarvis()

    return j, fake_voice, fake_speech


def teardown_function(_fn):
    """Every test below can end with a backend registered - always
    restore the "no backend" default afterward, exactly like test_
    commands.py's and test_local_llm_backend.py's own teardown_
    function() for the same Phase 12.1 global."""
    ai_backend.register_backend(None)


# ---------------------------------------------------------------------
# AI disabled -> nothing registered
# ---------------------------------------------------------------------

def test_ai_disabled_backend_is_not_registered():
    with patch.object(config, "ENABLE_AI_LAYER", False):
        j, _, _ = make_jarvis()

    assert ai_backend.get_backend() is None


def test_ai_disabled_clears_a_previously_registered_backend():
    """The explicit-clear half of the fail-closed guarantee: if some
    earlier code path (e.g. an earlier test, or an earlier Jarvis
    instance in the same process) left a backend registered, starting
    Jarvis with the flag off must leave the system with NO backend,
    not whatever was left over."""
    leftover = MagicMock(spec=ai_backend.AIBackend)
    ai_backend.register_backend(leftover)
    assert ai_backend.get_backend() is leftover  # sanity check on the setup

    with patch.object(config, "ENABLE_AI_LAYER", False):
        make_jarvis()

    assert ai_backend.get_backend() is None


def test_ai_disabled_never_instantiates_structured_backend():
    with patch.object(config, "ENABLE_AI_LAYER", False), \
         patch("jarvis.structured_llm_backend.StructuredLocalLLMBackend") as mock_cls:
        make_jarvis()

    mock_cls.assert_not_called()


# ---------------------------------------------------------------------
# AI enabled -> StructuredLocalLLMBackend registered exactly once
# ---------------------------------------------------------------------

def test_ai_enabled_registers_structured_local_llm_backend_exactly_once():
    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch("jarvis.ai_backend.register_backend", wraps=ai_backend.register_backend) as mock_register:
        j, _, _ = make_jarvis()

    backend = ai_backend.get_backend()
    assert isinstance(backend, structured_llm_backend.StructuredLocalLLMBackend)
    assert mock_register.call_count == 1


def test_ai_enabled_constructs_backend_exactly_once():
    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch(
             "jarvis.structured_llm_backend.StructuredLocalLLMBackend",
             wraps=structured_llm_backend.StructuredLocalLLMBackend,
         ) as mock_cls:
        make_jarvis()

    mock_cls.assert_called_once_with()


def test_ai_enabled_backend_init_makes_no_network_call():
    """StructuredLocalLLMBackend.__init__() only reads ai_tools.
    TOOL_REGISTRY to build its schema - proves startup wiring alone
    can never reach out to Ollama, only a later .converse() call
    could (and that path is unchanged, still gated by ai_router.py's
    existing try/except)."""
    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch("local_llm_backend.urllib.request.urlopen") as mock_urlopen:
        make_jarvis()

    mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------
# Initialization failure -> JARVIS still starts, fails closed
# ---------------------------------------------------------------------

def test_backend_initialization_failure_still_starts_jarvis():
    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch(
             "jarvis.structured_llm_backend.StructuredLocalLLMBackend",
             side_effect=RuntimeError("boom"),
         ):
        j, voice_double, _ = make_jarvis()

    assert isinstance(j, jarvis_module.Jarvis)


def test_backend_initialization_failure_registers_nothing():
    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch(
             "jarvis.structured_llm_backend.StructuredLocalLLMBackend",
             side_effect=RuntimeError("boom"),
         ):
        make_jarvis()

    assert ai_backend.get_backend() is None


def test_backend_initialization_failure_does_not_propagate():
    """The exception from a broken constructor must never escape
    Jarvis.__init__() - it is caught inside _initialize_ai_backend()."""
    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch(
             "jarvis.structured_llm_backend.StructuredLocalLLMBackend",
             side_effect=RuntimeError("boom"),
         ):
        # make_jarvis() itself will raise here if the exception escapes -
        # a bare successful call is the assertion.
        make_jarvis()


# ---------------------------------------------------------------------
# Deterministic commands never reach the AI backend, even when a real
# StructuredLocalLLMBackend-shaped spy IS registered at startup
# ---------------------------------------------------------------------

class _SpyBackend(ai_backend.AIBackend):
    """Records every command it was asked about - proves the AI router
    is never even consulted for commands the deterministic chain
    already recognizes, not just that its result would be unused.
    Mirrors test_commands.py's own _SpyBackend."""

    def __init__(self, *args, **kwargs):
        self.calls = []

    def converse(self, command, context):
        self.calls.append(command)
        raise AssertionError(f"AI layer was reached for deterministic command: {command!r}")


def test_deterministic_commands_never_reach_the_startup_registered_backend():
    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch("jarvis.structured_llm_backend.StructuredLocalLLMBackend", _SpyBackend):
        j, voice_double, _ = make_jarvis()

        backend = ai_backend.get_backend()
        assert isinstance(backend, _SpyBackend)

        deterministic_commands = [
            "open chrome", "scroll down", "close tab", "next tab", "press enter",
        ]

        # config.ENABLE_AI_LAYER is checked BOTH at startup-wiring time
        # (above, whether to register a backend at all) AND again at
        # commands.py process()-time (whether to consult the router for
        # THIS call) - process() must run inside the same patched
        # context for this to actually exercise the flag-on path,
        # otherwise it would only prove the (trivially true) inert
        # case.
        with patch("web_control.os.path.exists", return_value=False), \
             patch("web_control.webbrowser.open"), \
             patch("web_control.input_control.press_key_combo", return_value=True), \
             patch("keyboard_control.input_control.press_key", return_value=True):
            for command in deterministic_commands:
                j.commands.process(command)

    assert backend.calls == []


def test_non_deterministic_command_does_reach_the_startup_registered_backend():
    """The positive counterpart: proves the wiring actually connects
    end to end (not just that it stays silent), using a spy that
    returns a real AIResponse instead of raising."""

    class _RespondingSpyBackend(ai_backend.AIBackend):
        def __init__(self, *args, **kwargs):
            self.calls = []

        def converse(self, command, context):
            self.calls.append(command)
            return ai_backend.AIResponse.speak("I'm not sure how to help with that.")

    with patch.object(config, "ENABLE_AI_LAYER", True), \
         patch("jarvis.structured_llm_backend.StructuredLocalLLMBackend", _RespondingSpyBackend):
        j, voice_double, _ = make_jarvis()

        backend = ai_backend.get_backend()

        j.commands.process("tell me a joke about compilers")

    assert backend.calls == ["tell me a joke about compilers"]
    assert voice_double.spoken == ["I'm not sure how to help with that."]
