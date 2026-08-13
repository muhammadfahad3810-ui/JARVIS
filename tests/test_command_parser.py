import command_parser


# ---------------------------------------------------------------------
# OPEN variations
# ---------------------------------------------------------------------

def test_open_youtube_canonical_is_unchanged():
    assert command_parser.normalize("open youtube") == "open youtube"


def test_open_up_youtube():
    assert command_parser.normalize("open up youtube") == "open youtube"


def test_launch_youtube():
    assert command_parser.normalize("launch youtube") == "open youtube"


def test_go_to_youtube():
    assert command_parser.normalize("go to youtube") == "open youtube"


def test_please_open_youtube():
    assert command_parser.normalize("please open youtube") == "open youtube"


def test_can_you_open_youtube_for_me():
    assert command_parser.normalize(
        "can you open youtube for me"
    ) == "open youtube"


# ---------------------------------------------------------------------
# SEARCH variations
# ---------------------------------------------------------------------

def test_search_for_canonical_is_unchanged():
    assert command_parser.normalize("search for python") == "search for python"


def test_google_python():
    assert command_parser.normalize("google python") == "search for python"


def test_search_python():
    assert command_parser.normalize("search python") == "search for python"


def test_look_up_python():
    assert command_parser.normalize("look up python") == "search for python"


def test_find_information_about_python():
    assert command_parser.normalize(
        "find information about python"
    ) == "search for python"


def test_search_the_web_for_python():
    assert command_parser.normalize(
        "search the web for python"
    ) == "search for python"


# ---------------------------------------------------------------------
# APPLICATION variations
# ---------------------------------------------------------------------

def test_open_chrome_canonical_is_unchanged():
    assert command_parser.normalize("open chrome") == "open chrome"


def test_launch_chrome():
    assert command_parser.normalize("launch chrome") == "open chrome"


def test_start_notepad():
    assert command_parser.normalize("start notepad") == "open notepad"


def test_open_calculator_canonical_is_unchanged():
    assert command_parser.normalize("open calculator") == "open calculator"


def test_launch_file_explorer():
    assert command_parser.normalize(
        "launch file explorer"
    ) == "open file explorer"


def test_run_notepad():
    assert command_parser.normalize("run notepad") == "open notepad"


def test_run_powershell():
    assert command_parser.normalize("run powershell") == "open powershell"


def test_start_file_explorer():
    assert command_parser.normalize(
        "start file explorer"
    ) == "open file explorer"


# ---------------------------------------------------------------------
# VOLUME variations
# ---------------------------------------------------------------------

def test_volume_up_canonical_is_unchanged():
    assert command_parser.normalize("volume up") == "volume up"


def test_volume_down_canonical_is_unchanged():
    assert command_parser.normalize("volume down") == "volume down"


def test_increase_volume():
    assert command_parser.normalize("increase volume") == "volume up"


def test_increase_the_volume():
    assert command_parser.normalize("increase the volume") == "volume up"


def test_turn_the_volume_up():
    assert command_parser.normalize("turn the volume up") == "volume up"


def test_decrease_volume():
    assert command_parser.normalize("decrease volume") == "volume down"


def test_turn_the_volume_down():
    assert command_parser.normalize("turn the volume down") == "volume down"


def test_mute_the_computer():
    assert command_parser.normalize("mute the computer") == "mute"


def test_mute_canonical_is_unchanged():
    assert command_parser.normalize("mute") == "mute"


def test_unmute_canonical_is_unchanged():
    assert command_parser.normalize("unmute") == "unmute"


def test_unmute_is_not_rewritten_to_mute():
    result = command_parser.normalize("unmute")
    assert result == "unmute"


# ---------------------------------------------------------------------
# PHASE 7: absolute volume ("set volume to <N> percent" / "...to <N>%")
# ---------------------------------------------------------------------

def test_set_volume_to_40_percent():
    assert command_parser.normalize(
        "set volume to 40 percent"
    ) == "set volume to 40"


def test_set_volume_to_40_percent_sign():
    assert command_parser.normalize(
        "set volume to 40%"
    ) == "set volume to 40"


def test_set_volume_case_insensitive():
    assert command_parser.normalize(
        "SET VOLUME TO 40 PERCENT"
    ) == "set volume to 40"


def test_set_volume_extra_whitespace_is_collapsed():
    assert command_parser.normalize(
        "set   volume   to   40   percent"
    ) == "set volume to 40"


def test_set_the_volume_to_40_percent():
    assert command_parser.normalize(
        "set the volume to 40 percent"
    ) == "set volume to 40"


def test_set_volume_to_0_percent_is_valid_boundary():
    assert command_parser.normalize(
        "set volume to 0 percent"
    ) == "set volume to 0"


def test_set_volume_to_100_percent_is_valid_boundary():
    assert command_parser.normalize(
        "set volume to 100 percent"
    ) == "set volume to 100"


def test_set_volume_above_100_is_rejected_not_clamped():
    """Out-of-range values are left completely unrewritten (never
    clamped to 100) - see canonicalize_set_volume_phrase()'s docstring
    for the documented rejection policy."""
    result = command_parser.normalize("set volume to 150 percent")
    assert result == "set volume to 150 percent"
    assert result != "set volume to 100"


def test_set_volume_negative_is_rejected():
    """The regex has no '-' in its character class, so a negative
    number can never match at all - the text is left completely
    unrewritten, not clamped to 0."""
    result = command_parser.normalize("set volume to -10 percent")
    assert result == "set volume to -10 percent"


def test_set_volume_huge_number_is_rejected():
    """A huge digit string can never match the pattern - it's capped at
    3 digits by construction (the 4th+ digit is never immediately
    followed by 'percent'/'%'), so this can't reach a canonical
    'set volume to <N>' form at all."""
    result = command_parser.normalize(
        "set volume to 999999999999999999 percent"
    )
    assert result == "set volume to 999999999999999999 percent"


def test_set_volume_spelled_out_number_is_rejected():
    result = command_parser.normalize("set volume to forty percent")
    assert result == "set volume to forty percent"


def test_set_volume_decimal_is_rejected():
    result = command_parser.normalize("set volume to 40.5 percent")
    assert result == "set volume to 40.5 percent"


def test_set_volume_missing_percent_marker_is_left_unrewritten():
    """The percent/% marker is required by design - a bare number with
    no marker is not rewritten by this function (it happens to already
    equal the canonical form as plain text, which is handled - and
    intentionally accepted - separately by volume_control.handle(),
    not by this rewrite)."""
    result = command_parser.canonicalize_set_volume_phrase(
        "set volume to 40"
    )
    assert result == "set volume to 40"


def test_unrelated_text_is_not_treated_as_set_volume():
    result = command_parser.normalize("set the table for dinner")
    assert result == "set the table for dinner"


# ---------------------------------------------------------------------
# TIME variations (already pass through unchanged - "time" is a bare
# substring match downstream, no rewrite needed)
# ---------------------------------------------------------------------

def test_what_time_is_it():
    assert command_parser.normalize("what time is it") == "what time is it"


def test_tell_me_the_time():
    assert command_parser.normalize("tell me the time") == "tell me the time"


def test_whats_the_current_time():
    assert command_parser.normalize(
        "what's the current time"
    ) == "what's the current time"


# ---------------------------------------------------------------------
# DATE variations
# ---------------------------------------------------------------------

def test_what_is_todays_date():
    assert command_parser.normalize(
        "what is today's date"
    ) == "what is today's date"


def test_tell_me_todays_date():
    assert command_parser.normalize(
        "tell me today's date"
    ) == "tell me today's date"


def test_what_day_is_it_is_rewritten_to_contain_date():
    result = command_parser.normalize("what day is it")
    assert "date" in result


# ---------------------------------------------------------------------
# Existing / unrelated commands must be passed through unchanged
# ---------------------------------------------------------------------

def test_existing_system_commands_are_unchanged():
    assert command_parser.normalize("lock computer") == "lock computer"
    assert command_parser.normalize("shutdown computer") == "shutdown computer"
    assert command_parser.normalize("restart computer") == "restart computer"


def test_exit_words_are_unchanged():
    assert command_parser.normalize("exit") == "exit"
    assert command_parser.normalize("quit") == "quit"
    assert command_parser.normalize("goodbye") == "goodbye"
    assert command_parser.normalize("go offline") == "go offline"


def test_greeting_is_unchanged():
    assert command_parser.normalize("hello") == "hello"


def test_empty_string_returns_empty_string():
    assert command_parser.normalize("") == ""


def test_unrelated_command_is_left_alone():
    assert command_parser.normalize(
        "do a backflip"
    ) == "do a backflip"


def test_whitespace_is_collapsed_and_trimmed():
    assert command_parser.normalize("  open    chrome  ") == "open chrome"


def test_normalization_is_case_insensitive():
    assert command_parser.normalize("LAUNCH Chrome") == "open chrome"


# ---------------------------------------------------------------------
# PHASE 5: stacked / additional politeness wrappers
# ---------------------------------------------------------------------

def test_could_you_open_chrome_for_me():
    assert command_parser.normalize(
        "could you open Chrome for me"
    ) == "open chrome"


def test_can_you_open_youtube():
    assert command_parser.normalize("can you open YouTube") == "open youtube"


def test_would_you_open_chrome():
    assert command_parser.normalize("would you open Chrome") == "open chrome"


def test_i_want_you_to_open_chrome():
    assert command_parser.normalize(
        "I want you to open Chrome"
    ) == "open chrome"


def test_could_you_please_launch_youtube_stacked_fillers():
    """Regression case: stacked fillers ('could you' + leftover
    'please') were not fully stripped before the strip_filler fixed-
    point fix - the leftover 'please' blocked the open-verb rewrite."""
    assert command_parser.normalize(
        "could you please launch YouTube"
    ) == "open youtube"


def test_please_could_you_open_chrome_double_stack():
    assert command_parser.normalize(
        "please could you open Chrome"
    ) == "open chrome"


def test_can_you_turn_the_volume_up():
    assert command_parser.normalize(
        "can you turn the volume up"
    ) == "volume up"


def test_please_increase_the_volume():
    assert command_parser.normalize(
        "please increase the volume"
    ) == "volume up"


def test_could_you_open_file_explorer():
    assert command_parser.normalize(
        "could you open File Explorer"
    ) == "open file explorer"


def test_please_launch_powershell():
    assert command_parser.normalize(
        "please launch PowerShell"
    ) == "open powershell"


def test_can_you_minimize_this_window():
    assert command_parser.normalize(
        "can you minimize this window"
    ) == "minimize this window"


def test_can_you_tell_me_todays_date():
    assert command_parser.normalize(
        "can you tell me today's date"
    ) == "tell me today's date"


def test_could_you_tell_me_the_current_time():
    assert command_parser.normalize(
        "could you tell me the current time"
    ) == "tell me the current time"


# ---------------------------------------------------------------------
# PHASE 5: volume - "louder"/"quieter" words and pronoun-only phrases
# ---------------------------------------------------------------------

def test_make_the_volume_louder():
    assert command_parser.normalize(
        "make the volume louder"
    ) == "volume up"


def test_turn_it_down():
    assert command_parser.normalize("turn it down") == "volume down"


def test_turn_it_up():
    assert command_parser.normalize("turn it up") == "volume up"


def test_make_it_quieter():
    assert command_parser.normalize("make it quieter") == "volume down"


def test_make_it_louder():
    assert command_parser.normalize("make it louder") == "volume up"


def test_please_turn_it_down():
    assert command_parser.normalize("please turn it down") == "volume down"


def test_pronoun_volume_phrase_does_not_match_unrelated_sentence():
    """The pronoun phrases are anchored to the whole string - they must
    not match as a fragment inside a longer, unrelated sentence."""
    result = command_parser.normalize(
        "turn it down a notch please, this song is too loud"
    )
    assert result != "volume down"


# ---------------------------------------------------------------------
# PHASE 5: window / media / screenshot phrase gaps
# ---------------------------------------------------------------------

def test_show_me_the_desktop():
    assert command_parser.normalize(
        "show me the desktop"
    ) == "show desktop"


def test_maximize_this_window_unchanged():
    assert command_parser.normalize(
        "maximize this window"
    ) == "maximize this window"


def test_restore_this_window_unchanged():
    assert command_parser.normalize(
        "restore this window"
    ) == "restore this window"


def test_close_this_window_unchanged():
    assert command_parser.normalize(
        "close this window"
    ) == "close this window"


def test_play_the_music():
    assert command_parser.normalize("play the music") == "play the music"


def test_pause_the_music():
    assert command_parser.normalize("pause the music") == "pause the music"


def test_skip_this_song():
    assert command_parser.normalize("skip this song") == "next track"


def test_go_to_the_next_track():
    """'go to' is also a recognized open-verb synonym, so this becomes
    'open the next track' - it still routes correctly downstream since
    media_control.handle() matches 'next track' as a bare substring."""
    result = command_parser.normalize("go to the next track")
    assert "next track" in result


def test_take_a_screenshot_unchanged():
    assert command_parser.normalize(
        "take a screenshot"
    ) == "take a screenshot"


def test_capture_my_screen():
    assert command_parser.normalize("capture my screen") == "screenshot"


def test_what_is_todays_date_variant():
    assert command_parser.normalize(
        "what is today's date"
    ) == "what is today's date"


def test_whats_todays_date_variant():
    assert command_parser.normalize(
        "what's today's date"
    ) == "what's today's date"


def test_what_time_is_it_right_now():
    assert command_parser.normalize(
        "what time is it right now"
    ) == "what time is it right now"


# ---------------------------------------------------------------------
# PHASE 5: existing canonical commands remain byte-for-byte unchanged
# ---------------------------------------------------------------------

def test_all_canonical_commands_are_unchanged():
    canonical_commands = [
        "open chrome",
        "open youtube",
        "search for python",
        "open notepad",
        "open calculator",
        "open powershell",
        "open file explorer",
        "volume up",
        "volume down",
        "mute",
        "unmute",
        "next track",
        "previous track",
        "take a screenshot",
        "press enter",
        "copy",
        "paste",
        "lock computer",
        "shutdown computer",
        "restart computer",
        "what time is it",
        "what's the date",
        "exit",
    ]

    for command in canonical_commands:
        assert command_parser.normalize(command) == command, command
