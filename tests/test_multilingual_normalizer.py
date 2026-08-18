"""Phase 11.1 unit tests: the deterministic Urdu-script + Roman-Urdu
normalization layer (src/multilingual_normalizer.py).

Structured in three parts:

1. Direct recognition tests - Urdu-script phrases, Roman-Urdu phrases,
   and mixed-language phrases, asserting the exact canonical command
   string produced (mirrors tests/test_intent_layer.py's shape).
2. Non-match / negative tests - text that must NOT be recognized.
3. Structural safety tests - proving, not just claiming, that this
   module (a) cannot produce any of the three dangerous command
   phrases for any input, and (b) imports no control module, no voice,
   no execution primitive. These mirror the same import-list-inspection
   test style tests/test_context_manager.py already uses for
   context_manager.py.

No real action of any kind is possible from this module (it is pure -
see its own module docstring), so no mocking is required in this file
itself. Integration-level tests proving the full recursive wiring
through CommandProcessor.process() - with every real action primitive
mocked - live in tests/test_commands.py and tests/test_security.py.
"""

import ast
import inspect
from unittest.mock import patch

import commands
import config
import intent_parser
import multilingual_normalizer
import window_control


def _non_docstring_string_literals(source):
    """All string literal constants in `source` EXCLUDING docstrings
    (the first statement of the module/any function/class, when it's a
    bare string expression) - so a docstring merely discussing a
    dangerous phrase (to explain why it can never occur) doesn't
    falsely trip a literal-content check the way a plain substring
    search over the whole source text would."""

    tree = ast.parse(source)
    docstring_ids = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_ids.add(id(body[0].value))

    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_ids
    ]


# ---------------------------------------------------------------------
# 1. Direct recognition - open application
# ---------------------------------------------------------------------

def test_urdu_script_open_chrome():
    assert multilingual_normalizer.understand("chrome کھولو") == "open chrome"


def test_urdu_script_open_verb_before_app_name():
    assert multilingual_normalizer.understand("کھولو chrome") == "open chrome"


def test_roman_urdu_open_youtube():
    assert multilingual_normalizer.understand("youtube kholo") == "open youtube"


def test_roman_urdu_open_notepad_polite_form():
    assert multilingual_normalizer.understand("notepad khol dein") == "open notepad"


def test_open_application_without_marker_is_not_recognized():
    # Bare "chrome" with no open-verb marker is not treated as an open
    # command by this layer - deliberately conservative (fail closed).
    assert multilingual_normalizer.understand("chrome") is None


def test_open_unknown_application_is_not_recognized():
    assert multilingual_normalizer.understand("spotify kholo") is None


# ---------------------------------------------------------------------
# 1. Direct recognition - volume / mute
# ---------------------------------------------------------------------

def test_urdu_script_volume_up():
    assert multilingual_normalizer.understand("آواز بڑھاؤ") == "volume up"


def test_roman_urdu_volume_down():
    assert multilingual_normalizer.understand("awaz kam karo") == "volume down"


def test_urdu_script_mute():
    assert multilingual_normalizer.understand("خاموش کرو") == "mute"


def test_roman_urdu_unmute():
    assert multilingual_normalizer.understand("unmute karo") == "unmute"


def test_urdu_script_set_volume_to_40_percent():
    assert multilingual_normalizer.understand("آواز 40 فیصد کرو") == "set volume to 40"


def test_roman_urdu_set_volume_to_100_percent():
    assert multilingual_normalizer.understand("volume 100 percent karo") == "set volume to 100"


def test_set_volume_out_of_range_is_rejected_not_clamped():
    assert multilingual_normalizer.understand("آواز 150 فیصد کرو") is None


def test_set_volume_negative_is_rejected_not_reinterpreted():
    # "-10" must never be silently reinterpreted as 10 (reject-not-clamp,
    # same policy as intent_layer.VOLUME_NUMBER_RE).
    assert multilingual_normalizer.understand("volume -10 percent karo") is None


def test_set_volume_decimal_is_rejected_not_truncated():
    assert multilingual_normalizer.understand("volume 40.5 percent karo") is None


# ---------------------------------------------------------------------
# 1. Direct recognition - window control
# ---------------------------------------------------------------------

def test_urdu_script_minimize():
    assert multilingual_normalizer.understand("چھوٹا کرو") == "minimize this window"


def test_roman_urdu_maximize():
    assert multilingual_normalizer.understand("bara karo") == "maximize this window"


def test_roman_urdu_restore():
    assert multilingual_normalizer.understand("restore karo") == "restore this window"


def test_urdu_script_close_window():
    assert multilingual_normalizer.understand("ونڈو بند کرو") == "close this window"


def test_roman_urdu_switch_window():
    assert multilingual_normalizer.understand("switch window karo") == "switch window"


def test_urdu_script_show_desktop():
    assert multilingual_normalizer.understand("ڈیسک ٹاپ دکھاؤ") == "show desktop"


# ---------------------------------------------------------------------
# 1. Direct recognition - media
# ---------------------------------------------------------------------

def test_roman_urdu_play():
    assert multilingual_normalizer.understand("chalao") == "play"


def test_urdu_script_pause():
    assert multilingual_normalizer.understand("روکو") == "play"


def test_roman_urdu_next_track():
    assert multilingual_normalizer.understand("agla gana") == "next track"


def test_urdu_script_previous_track():
    assert multilingual_normalizer.understand("پچھلا گانا") == "previous track"


def test_next_track_wins_over_play_when_both_markers_present():
    assert multilingual_normalizer.understand("agla gana chalao") == "next track"


# ---------------------------------------------------------------------
# 1. Direct recognition - screenshot / keyboard
# ---------------------------------------------------------------------

def test_roman_urdu_screenshot():
    assert multilingual_normalizer.understand("screenshot lo") == "screenshot"


def test_urdu_script_screenshot():
    assert multilingual_normalizer.understand("تصویر لو") == "screenshot"


def test_roman_urdu_copy():
    assert multilingual_normalizer.understand("copy karo") == "copy"


def test_roman_urdu_paste():
    assert multilingual_normalizer.understand("paste karo") == "paste"


def test_urdu_script_select_all():
    assert multilingual_normalizer.understand("سب منتخب کرو") == "select all"


def test_roman_urdu_undo():
    assert multilingual_normalizer.understand("wapas karo") == "undo"


def test_roman_urdu_press_enter():
    assert multilingual_normalizer.understand("enter dabao") == "press enter"


def test_urdu_script_press_tab():
    assert multilingual_normalizer.understand("ٹیب دباؤ") == "press tab"


# ---------------------------------------------------------------------
# 1. Direct recognition - search (free-text query)
# ---------------------------------------------------------------------

def test_urdu_script_search_suffix_form():
    assert (
        multilingual_normalizer.understand("spider man تلاش کرو")
        == "search for spider man"
    )


def test_roman_urdu_search_suffix_form():
    assert multilingual_normalizer.understand("cats talash karo") == "search for cats"


def test_roman_urdu_search_prefix_form():
    assert multilingual_normalizer.understand("search karo cats") == "search for cats"


def test_search_with_empty_query_is_not_recognized():
    assert multilingual_normalizer.understand("talash karo") is None


# ---------------------------------------------------------------------
# 1. Direct recognition - time / date / greeting / exit
# ---------------------------------------------------------------------

def test_urdu_script_time():
    assert multilingual_normalizer.understand("وقت کیا ہے") == "what time is it"


def test_roman_urdu_date():
    assert multilingual_normalizer.understand("tareekh kya hai") == "what is the date"


def test_urdu_script_greeting():
    assert multilingual_normalizer.understand("سلام") == "hello"


def test_roman_urdu_greeting():
    assert multilingual_normalizer.understand("salaam") == "hello"


def test_urdu_script_exit():
    assert multilingual_normalizer.understand("خدا حافظ") == "exit"


def test_roman_urdu_exit():
    assert multilingual_normalizer.understand("khuda hafiz") == "exit"


# ---------------------------------------------------------------------
# 1. Mixed-language forms
# ---------------------------------------------------------------------

def test_mixed_language_open_application():
    assert multilingual_normalizer.understand("youtube پر kholo") == "open youtube"


def test_mixed_language_english_verb_urdu_noise_around_app_name():
    assert multilingual_normalizer.understand("please chrome kholo") == "open chrome"


# ---------------------------------------------------------------------
# 2. Non-matches
# ---------------------------------------------------------------------

def test_empty_string_returns_none():
    assert multilingual_normalizer.understand("") is None


def test_none_input_returns_none():
    assert multilingual_normalizer.understand(None) is None


def test_unrelated_urdu_text_returns_none():
    assert multilingual_normalizer.understand("آج موسم اچھا ہے") is None


def test_unrelated_roman_urdu_text_returns_none():
    assert multilingual_normalizer.understand("aaj mausam acha hai") is None


def test_english_command_falls_through_to_none():
    # English commands are handled entirely by the existing dispatch
    # chain long before this layer would ever be reached in practice;
    # this module itself has no English vocabulary and correctly
    # recognizes nothing for it, in isolation.
    assert multilingual_normalizer.understand("open chrome") is None


# ---------------------------------------------------------------------
# 3. Structural safety
# ---------------------------------------------------------------------

DANGEROUS_PHRASES = (
    "lock computer",
    "shutdown computer",
    "restart computer",
)

# A broad sweep of every marker phrase this module defines, plus common
# combinations, run through understand() and checked against the fixed
# dangerous-command phrases - proving, not just documenting, that no
# input can make this module produce one of them.
_ALL_MARKER_GROUPS = (
    multilingual_normalizer.OPEN_MARKERS,
    multilingual_normalizer.MINIMIZE_MARKERS,
    multilingual_normalizer.MAXIMIZE_MARKERS,
    multilingual_normalizer.RESTORE_MARKERS,
    multilingual_normalizer.CLOSE_WINDOW_MARKERS,
    multilingual_normalizer.SWITCH_WINDOW_MARKERS,
    multilingual_normalizer.SHOW_DESKTOP_MARKERS,
    multilingual_normalizer.PLAY_MARKERS,
    multilingual_normalizer.PAUSE_MARKERS,
    multilingual_normalizer.NEXT_TRACK_MARKERS,
    multilingual_normalizer.PREVIOUS_TRACK_MARKERS,
    multilingual_normalizer.SCREENSHOT_MARKERS,
    multilingual_normalizer.UNMUTE_MARKERS,
    multilingual_normalizer.MUTE_MARKERS,
    multilingual_normalizer.VOLUME_UP_MARKERS,
    multilingual_normalizer.VOLUME_DOWN_MARKERS,
    multilingual_normalizer.COPY_MARKERS,
    multilingual_normalizer.PASTE_MARKERS,
    multilingual_normalizer.SELECT_ALL_MARKERS,
    multilingual_normalizer.UNDO_MARKERS,
    multilingual_normalizer.SEARCH_SUFFIX_MARKERS,
    multilingual_normalizer.SEARCH_PREFIX_MARKERS,
    multilingual_normalizer.TIME_MARKERS,
    multilingual_normalizer.DATE_MARKERS,
    multilingual_normalizer.GREETING_MARKERS,
    multilingual_normalizer.EXIT_MARKERS,
    # Phase 11.5
    multilingual_normalizer.BROWSER_WORD_MARKERS,
    multilingual_normalizer.SCROLL_UP_MARKERS,
    multilingual_normalizer.SCROLL_DOWN_MARKERS,
    multilingual_normalizer._AMBIGUOUS_EXIT_MARKERS,
    # Phase 11.7
    multilingual_normalizer.CLOSE_APP_MARKERS,
    # Browser tab management / navigation (brand-new capability)
    multilingual_normalizer.NEW_TAB_MARKERS,
    multilingual_normalizer.CLOSE_TAB_MARKERS,
    multilingual_normalizer.REFRESH_MARKERS,
    multilingual_normalizer.GO_BACK_MARKERS,
    multilingual_normalizer.GO_FORWARD_MARKERS,
    # Phase 11.2: each dangerous ACTION+VERB phrase, tested ALONE
    # (without the required "computer"/"کمپیوٹر" noun) - proves the
    # noun requirement is load-bearing, not decorative: "lock karo" by
    # itself must never be dangerous.
    multilingual_normalizer.LOCK_ACTION_PHRASES,
    multilingual_normalizer.SHUTDOWN_ACTION_PHRASES,
    multilingual_normalizer.RESTART_ACTION_PHRASES,
)


def test_no_single_marker_phrase_ever_produces_a_dangerous_command():
    for group in _ALL_MARKER_GROUPS:
        for phrase in group:
            result = multilingual_normalizer.understand(phrase)
            assert result not in DANGEROUS_PHRASES


def test_every_marker_combined_with_every_known_application_is_safe():
    # The broadest possible sweep: every open-verb marker crossed with
    # every known application name (the only place this module accepts
    # free-form entity substitution) can never yield a dangerous phrase.
    for marker in multilingual_normalizer.OPEN_MARKERS:
        for app in intent_parser.KNOWN_APPLICATIONS:
            result = multilingual_normalizer.understand(f"{app} {marker}")
            assert result not in DANGEROUS_PHRASES


# =======================================================================
# PHASE 11.2: dangerous-command (lock/shutdown/restart) recognition.
#
# Section labels (A-K) mirror the Phase 11.2 test-matrix requirements.
# =======================================================================

# ---- A. Direct multilingual dangerous recognition, per canonical
# command - Urdu script, Roman Urdu, mixed language, optional "ko", and
# the verb variations this implementation explicitly supports ----

LOCK_PHRASES = (
    "computer lock karo",
    "computer ko lock karo",
    "کمپیوٹر لاک کرو",
    "کمپیوٹر کو لاک کرو",
    "computer کو lock کرو",           # mixed: EN noun + UR "ko" + EN action + UR verb
    "کمپیوٹر لاک karo",               # mixed: UR noun + UR action + Roman verb
)

SHUTDOWN_PHRASES = (
    "computer band karo",
    "computer ko band karo",
    "کمپیوٹر بند کرو",
    "کمپیوٹر کو بند کرو",
    "کمپیوٹر shutdown کرو",           # mixed: UR noun + EN action + UR verb
    "computer shutdown karo",         # Roman variant of the EN action word
    "کمپیوٹر بند karo",               # mixed: UR noun + UR action + Roman verb
)

RESTART_PHRASES = (
    "computer restart karo",
    "computer ko restart karo",
    "کمپیوٹر ری اسٹارٹ کرو",
    "کمپیوٹر کو ری اسٹارٹ کرو",
    "کمپیوٹر ko restart karo",        # mixed: UR noun + Roman "ko" + Roman action/verb
    "کمپیوٹر ری اسٹارٹ karo",         # mixed: UR noun + UR action + Roman verb
)


def test_all_lock_phrasings_produce_lock_computer():
    for phrase in LOCK_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "lock computer", phrase


def test_all_shutdown_phrasings_produce_shutdown_computer():
    for phrase in SHUTDOWN_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "shutdown computer", phrase


def test_all_restart_phrasings_produce_restart_computer():
    for phrase in RESTART_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "restart computer", phrase


def test_understand_dangerous_matches_understand_for_all_dangerous_phrasings():
    for phrase in LOCK_PHRASES + SHUTDOWN_PHRASES + RESTART_PHRASES:
        assert (
            multilingual_normalizer.understand_dangerous(phrase)
            == multilingual_normalizer.understand(phrase)
        )


def test_understand_dangerous_returns_none_for_non_dangerous_text():
    assert multilingual_normalizer.understand_dangerous("chrome کھولو") is None
    assert multilingual_normalizer.understand_dangerous("") is None
    assert multilingual_normalizer.understand_dangerous(None) is None


def test_optional_ko_does_not_change_the_result():
    """The exact same command, with and without the optional "ko"/"کو"
    object marker, must produce the identical canonical output."""

    assert (
        multilingual_normalizer.understand("computer lock karo")
        == multilingual_normalizer.understand("computer ko lock karo")
        == "lock computer"
    )
    assert (
        multilingual_normalizer.understand("کمپیوٹر بند کرو")
        == multilingual_normalizer.understand("کمپیوٹر کو بند کرو")
        == "shutdown computer"
    )


# ---- B. Canonical output is restricted to exactly the three fixed
# strings, byte-for-byte identical to the authoritative Phase 9
# vocabulary (commands.DANGEROUS_COMMANDS) ----

def test_dangerous_recognition_never_produces_anything_but_the_three_canonical_strings():
    allowed = set(DANGEROUS_PHRASES)

    for phrase in LOCK_PHRASES + SHUTDOWN_PHRASES + RESTART_PHRASES:
        assert multilingual_normalizer.understand(phrase) in allowed


def test_dangerous_canonical_strings_match_commands_dangerous_commands_exactly():
    """Parity proof, not just a guess at the right strings: every
    literal _check_dangerous() can produce must be byte-for-byte
    identical to commands.DANGEROUS_COMMANDS - the authoritative Phase 9
    vocabulary the confirmation gate itself matches against."""

    produced = {
        multilingual_normalizer.understand(phrase)
        for phrase in LOCK_PHRASES + SHUTDOWN_PHRASES + RESTART_PHRASES
    }

    assert produced == set(commands.DANGEROUS_COMMANDS)


# ---- C. Structural security: proves, not just documents, that dangerous
# recognition cannot generate an arbitrary command string ----

def _string_literals_by_enclosing_function(source):
    """Map: function name -> every string literal directly RETURNED
    (ast.Return(value=ast.Constant)) from within that function's body -
    used to prove the three dangerous canonical strings are bare,
    hardcoded return values from exactly ONE function, never built from
    other data (an f-string, concatenation, or a call result would NOT
    show up here as a Constant, so it would silently fail to appear in
    this map at all - exactly the failure mode the assertions below
    check for)."""

    tree = ast.parse(source)
    result = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            returned = [
                child.value.value
                for child in ast.walk(node)
                if (
                    isinstance(child, ast.Return)
                    and isinstance(child.value, ast.Constant)
                    and isinstance(child.value.value, str)
                )
            ]
            result[node.name] = returned

    return result


def test_dangerous_phrase_literals_only_appear_as_bare_returns_in_check_dangerous():
    source = inspect.getsource(multilingual_normalizer)
    by_function = _string_literals_by_enclosing_function(source)

    for phrase in DANGEROUS_PHRASES:

        producing_functions = [
            name for name, literals in by_function.items() if phrase in literals
        ]

        assert producing_functions == ["_check_dangerous"], (
            f"{phrase!r} must be returned as a bare literal ONLY from "
            f"_check_dangerous(), found in: {producing_functions}"
        )

    # And, more broadly: outside those bare returns, these three exact
    # strings must not appear as ANY other string literal anywhere else
    # in the module's actual code (excluding docstrings) - e.g. not
    # stored in a second constant, not used as a dict key/value, not
    # embedded in a template string.
    all_literals = _non_docstring_string_literals(source)

    for phrase in DANGEROUS_PHRASES:
        count = all_literals.count(phrase)
        assert count == 1, f"{phrase!r} appears {count} times as a literal, expected exactly 1"


def test_check_dangerous_never_constructs_a_string_dynamically():
    """No f-string (ast.JoinedStr) and no string concatenation
    (ast.BinOp) anywhere in _check_dangerous()'s body - its only
    possible outputs are the three bare literals asserted above."""

    tree = ast.parse(inspect.getsource(multilingual_normalizer))

    check_dangerous_node = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_check_dangerous"
    )

    for child in ast.walk(check_dangerous_node):
        assert not isinstance(child, ast.JoinedStr)
        assert not isinstance(child, ast.BinOp)


def test_intent_parser_still_has_no_dangerous_command_category():
    """intent_parser.py remains untouched and structurally incapable of
    representing a dangerous command - _check_dangerous() is the ONLY
    exception to "always render via intent_parser" in this module (see
    its module docstring), and this proves intent_parser itself was
    never given a matching category to make that exception unnecessary
    by other means."""

    for forbidden in ("LOCK_COMPUTER", "SHUTDOWN_COMPUTER", "RESTART_COMPUTER"):
        assert not hasattr(intent_parser.Intent, forbidden)


# ---- K. Dangerous substring defense: ordinary text/search queries that
# merely CONTAIN dangerous-sounding words, but do not match the
# explicit noun+action+verb pattern, must remain ordinary ----

def test_chrome_close_is_never_mistaken_for_a_dangerous_command():
    result = multilingual_normalizer.understand("chrome بند کرو")
    assert result != "shutdown computer"
    assert result not in DANGEROUS_PHRASES


def test_bare_action_phrase_without_noun_is_not_dangerous():
    for phrase in ("lock karo", "بند کرو", "restart karo", "لاک کرو", "shutdown karo"):
        assert multilingual_normalizer.understand(phrase) not in DANGEROUS_PHRASES


def test_computer_noun_alone_without_action_is_not_dangerous():
    """Mere presence of "computer"/"کمپیوٹر" is not enough on its own -
    it must fall through to whatever else the text actually says (here,
    a plain search for the word "computer")."""

    assert multilingual_normalizer.understand("کمپیوٹر تلاش کرو") == "search for کمپیوٹر"


def test_action_phrase_embedded_in_unrelated_word_does_not_match():
    """"karo" as a PREFIX of a longer, unrelated word ("karobar" - Urdu/
    Roman Urdu for "business") must never be mistaken for the dangerous
    "lock karo" marker - proves word-boundary anchoring, not a bare
    substring search."""

    assert multilingual_normalizer.understand("computer lock karobar") not in DANGEROUS_PHRASES


def test_search_query_containing_dangerous_words_without_noun_remains_a_search():
    """A legitimate search whose query text happens to contain
    dangerous-sounding words, but never combines them with the
    "computer"/"کمپیوٹر" noun, must remain an ordinary search - proving
    this module does not implement broad substring-based dangerous-word
    detection, only the explicit noun+action+verb pattern."""

    result = multilingual_normalizer.understand("لاک کرو تلاش کرو")
    assert result == "search for لاک کرو"
    assert result not in DANGEROUS_PHRASES


FORBIDDEN_IMPORT_NAMES = (
    "voice",
    "commands",
    "web_control",
    "system_control",
    "window_control",
    "volume_control",
    "media_control",
    "keyboard_control",
    "screen_control",
    "audio_endpoint",
    "input_control",
    "subprocess",
    "ctypes",
    "comtypes",
)

def test_module_imports_no_control_module_and_no_execution_primitive():
    """Structural guarantee, verified by inspecting the actual imported
    module names and the parsed AST - not just by convention, and not
    by a naive text search that would also match this module's own
    docstring discussing what it must never do - mirroring tests/
    test_context_manager.py's own import-list inspection test for
    context_manager.py.

    os.system() is structurally impossible without importing `os` at
    all (it would raise NameError) - proven by the import-name check
    below. eval()/exec() are always-available builtins regardless of
    imports, so those are checked directly via the AST's Call nodes."""

    imported_names = {
        name for name, value in vars(multilingual_normalizer).items()
        if inspect.ismodule(value)
    }

    for forbidden in FORBIDDEN_IMPORT_NAMES:
        assert forbidden not in imported_names

    assert "os" not in imported_names

    tree = ast.parse(inspect.getsource(multilingual_normalizer))

    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "eval" not in called_names
    assert "exec" not in called_names


def test_module_only_imports_re_and_intent_parser():
    imported_names = sorted(
        name for name, value in vars(multilingual_normalizer).items()
        if inspect.ismodule(value)
    )
    assert imported_names == ["intent_parser", "re"]


def test_understand_never_raises_for_arbitrary_text():
    weird_inputs = (
        "",
        " ",
        "١٢٣ فیصد",
        "🎉🎉🎉",
        "a" * 5000,
        "کھولو" * 200,
        None,
    )

    for weird in weird_inputs:
        multilingual_normalizer.understand(weird)


# Phase 11.5: "scroll up"/"scroll down" are fixed literals with no
# intent_parser.Intent category (same reasoning as "hello"/"exit" - see
# multilingual_normalizer._check_scroll()) - dispatched instead by the
# real, unmodified keyboard_control.handle() bare-substring checks
# added in Phase 11.5 (see tests/test_keyboard_control.py), which is
# what makes them part of the known-safe set despite intent_parser not
# recognizing them.
SCROLL_LITERALS = ("scroll up", "scroll down")

# Browser tab-management/navigation literals: same reasoning as
# SCROLL_LITERALS above - no intent_parser.Intent category exists for
# them, dispatched instead by the real, unmodified web_control.handle()
# bare-substring checks (see tests/test_commands.py).
BROWSER_LITERALS = (
    "new tab", "close tab", "refresh", "go back", "go forward",
)


def test_every_produced_canonical_command_is_in_the_known_safe_set():
    """Every canonical string this module can ever produce must already
    be one this project's own dispatch chain understands - proven by
    cross-checking against intent_parser.classify() (which recognizes
    every canonical string except the two greeting/exit literals, the
    two Phase 11.5 scroll literals, and the three Phase 11.2
    dangerous-command literals, checked against commands.
    DANGEROUS_COMMANDS instead - see that module's own docstring for
    why intent_parser structurally cannot represent those) - so this
    module cannot introduce a new, unreviewed command surface."""

    sample_inputs = [phrase for group in _ALL_MARKER_GROUPS for phrase in group]
    sample_inputs += [
        f"{app} {marker}"
        for marker in multilingual_normalizer.OPEN_MARKERS
        for app in intent_parser.KNOWN_APPLICATIONS
    ]
    sample_inputs += ["آواز 40 فیصد کرو", "volume 100 percent karo"]
    sample_inputs += list(LOCK_PHRASES) + list(SHUTDOWN_PHRASES) + list(RESTART_PHRASES)

    for raw in sample_inputs:

        canonical = multilingual_normalizer.understand(raw)

        if canonical is None:
            continue

        if canonical in ("hello", "exit"):
            assert canonical in commands.GREETINGS + commands.EXIT_WORDS
            continue

        if canonical in commands.DANGEROUS_COMMANDS:
            continue

        if canonical in SCROLL_LITERALS:
            continue

        if canonical in BROWSER_LITERALS:
            continue

        assert intent_parser.classify(canonical).intent != intent_parser.Intent.UNKNOWN


# =======================================================================
# PHASE 11.3.1: word-boundary hardening for the GENERAL (non-dangerous)
# vocabulary - see multilingual_normalizer._contains_any_bounded().
# Phase 11.2's dangerous-command recognition is frozen; this section
# also directly proves it was not touched, shared, or refactored.
# =======================================================================

# ---- 1. The exact reproduced bug (Phase 11.3 architecture audit) is
# fixed ----

def test_mute_karobar_no_longer_false_matches_mute():
    """The exact false positive the Phase 11.3 audit found and verified
    empirically before this fix existed: "mute karo" was matched as a
    bare substring of "mute karobar" (a real Urdu/Roman-Urdu word
    meaning "business")."""

    assert multilingual_normalizer.understand("mute karobar") is None


# ---- 2. Equivalent mid-word false positives, across representative
# general markers (window control, volume, keyboard, open-verb, and
# Urdu script) - each constructed the same way as the reproduced bug:
# a real two-word marker phrase immediately followed by more letters
# that turn it into a different, unrelated word. ----

MID_WORD_FALSE_POSITIVE_CASES = (
    "mute karobar",              # MUTE_MARKERS: "mute karo" + "bar"
    "awaz kam karobar",          # VOLUME_DOWN_MARKERS: "awaz kam karo" + "bar"
    "chota karobar",             # MINIMIZE_MARKERS: "chota karo" + "bar"
    "window band karobar",       # CLOSE_WINDOW_MARKERS: "window band karo" + "bar"
    "enter dabaoge",             # PRESS_KEY_MARKERS["enter"]: "enter dabao" + "ge"
    "chrome khologe",            # OPEN_MARKERS: "kholo" + "ge" (real Urdu future-tense word)
)


def test_representative_general_markers_reject_mid_word_matches():
    for phrase in MID_WORD_FALSE_POSITIVE_CASES:
        assert multilingual_normalizer.understand(phrase) is None, phrase


def test_urdu_script_mid_word_false_positive_is_rejected():
    """Urdu-script equivalent of the Roman-Urdu "karobar" case: "کرو"
    (karo) followed immediately by "گے" (a real future-tense suffix,
    "کروگے" = "will do") must not be mistaken for the mute marker
    "خاموش کرو"."""

    assert multilingual_normalizer.understand("خاموش کروگے") is None


# ---- 3/4/5. Legitimate marker phrases - Urdu script AND Roman Urdu -
# remain recognized exactly as before, across every general concept. ----

LEGITIMATE_GENERAL_PHRASES = (
    ("چھوٹا کرو", "minimize this window"),
    ("bara karo", "maximize this window"),
    ("restore karo", "restore this window"),
    ("ونڈو بند کرو", "close this window"),
    ("desktop dikhao", "show desktop"),
    ("switch window karo", "switch window"),
    ("chalao", "play"),
    ("روکو", "play"),
    ("agla gana", "next track"),
    ("پچھلا گانا", "previous track"),
    ("تصویر لو", "screenshot"),
    ("mute karo", "mute"),
    ("unmute karo", "unmute"),
    ("آواز بڑھاؤ", "volume up"),
    ("awaz kam karo", "volume down"),
    ("سب منتخب کرو", "select all"),
    ("copy karo", "copy"),
    ("paste karo", "paste"),
    ("wapas karo", "undo"),
    ("enter dabao", "press enter"),
    ("waqt kya hai", "what time is it"),
    ("تاریخ کیا ہے", "what is the date"),
    ("salaam", "hello"),
    ("خدا حافظ", "exit"),
    ("chrome کھولو", "open chrome"),
    ("youtube kholo", "open youtube"),
    ("کھولو chrome", "open chrome"),
)


def test_legitimate_general_marker_phrases_still_recognized():
    for phrase, expected in LEGITIMATE_GENERAL_PHRASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


# ---- 6/7. Phase 11.2 (dangerous-command recognition) is completely
# unchanged - frozen, not touched, not shared, not refactored. ----

# Byte-for-byte snapshot of the compiled regex pattern text as it
# existed at the end of Phase 11.2, captured before this phase made any
# change - a direct equality check, not just a claim.
FROZEN_LOCK_PATTERN = (
    r"\b(?:computer|کمپیوٹر)\b\s+(?:\b(?:ko|کو)\b\s+)?"
    r"\b(?:lock\ karo|lock\ کرو|لاک\ کرو|لاک\ karo)\b"
)
FROZEN_SHUTDOWN_PATTERN = (
    r"\b(?:computer|کمپیوٹر)\b\s+(?:\b(?:ko|کو)\b\s+)?"
    r"\b(?:band\ karo|band\ کرو|بند\ کرو|بند\ karo|shutdown\ karo|shutdown\ کرو)\b"
)
FROZEN_RESTART_PATTERN = (
    r"\b(?:computer|کمپیوٹر)\b\s+(?:\b(?:ko|کو)\b\s+)?"
    r"\b(?:restart\ karo|restart\ کرو|ری\ اسٹارٹ\ کرو|ری\ اسٹارٹ\ karo)\b"
)


def test_dangerous_regex_patterns_are_byte_for_byte_unchanged():
    assert multilingual_normalizer.LOCK_DANGEROUS_RE.pattern == FROZEN_LOCK_PATTERN
    assert multilingual_normalizer.SHUTDOWN_DANGEROUS_RE.pattern == FROZEN_SHUTDOWN_PATTERN
    assert multilingual_normalizer.RESTART_DANGEROUS_RE.pattern == FROZEN_RESTART_PATTERN


def test_dangerous_action_phrase_tuples_are_unchanged():
    assert multilingual_normalizer.LOCK_ACTION_PHRASES == (
        "lock karo", "lock کرو", "لاک کرو", "لاک karo",
    )
    assert multilingual_normalizer.SHUTDOWN_ACTION_PHRASES == (
        "band karo", "band کرو", "بند کرو", "بند karo",
        "shutdown karo", "shutdown کرو",
    )
    assert multilingual_normalizer.RESTART_ACTION_PHRASES == (
        "restart karo", "restart کرو", "ری اسٹارٹ کرو", "ری اسٹارٹ karo",
    )


def test_check_dangerous_does_not_call_the_new_bounded_helper():
    """AST proof that _check_dangerous() was not refactored to share
    _contains_any_bounded() - it must keep using its own, separate,
    already-boundary-safe regex machinery, untouched by this phase."""

    tree = ast.parse(inspect.getsource(multilingual_normalizer))

    check_dangerous_node = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_check_dangerous"
    )

    called_names = {
        node.func.id
        for node in ast.walk(check_dangerous_node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "_contains_any_bounded" not in called_names
    assert "_contains_any" not in called_names


def test_dangerous_recognition_still_works_identically_after_hardening():
    """Full re-verification of the Phase 11.2 dangerous-command test
    matrix's own examples - every phrasing still resolves to exactly
    the same canonical string it did before this phase."""

    for phrase in LOCK_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "lock computer", phrase
    for phrase in SHUTDOWN_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "shutdown computer", phrase
    for phrase in RESTART_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "restart computer", phrase


# ---- 8. ENABLE_MULTILINGUAL_LAYER flag value ----
#
# Rolled out (default True) after dedicated validation - see the Phase
# 11 validation report. This section's original Phase 11.3.1 intent
# (prove Phase 11.3.1's hardening work did not itself flip the flag)
# still holds; only the expected value changed to match the completed
# rollout decision.

def test_multilingual_layer_flag_reflects_completed_rollout():
    assert config.ENABLE_MULTILINGUAL_LAYER is True


# ---- 9. No control-module import was introduced by this phase ----

def test_module_still_only_imports_re_and_intent_parser_after_hardening():
    """Re-verification, specific to this phase: the new
    _contains_any_bounded() helper uses only re.search()/re.escape() -
    no new import was introduced to implement it."""

    imported_names = sorted(
        name for name, value in vars(multilingual_normalizer).items()
        if inspect.ismodule(value)
    )
    assert imported_names == ["intent_parser", "re"]


def test_contains_any_bounded_is_not_used_by_search_or_application_lookup():
    """Documents two deliberate exclusions from this phase's scope: the
    KNOWN_APPLICATIONS name lookup in _check_open_application() (kept
    as a bare substring check, for exact parity with intent_parser.
    classify()'s own equivalent check over the same allow-list) and
    _check_search()'s prefix/suffix matching (already anchored to the
    start/end of the relevant side via .startswith()/.endswith(), a
    different mechanism entirely) were intentionally NOT converted to
    _contains_any_bounded() - only the marker-phrase checks were."""

    source = inspect.getsource(multilingual_normalizer)
    check_open_application_source = inspect.getsource(
        multilingual_normalizer._check_open_application
    )
    check_search_source = inspect.getsource(multilingual_normalizer._check_search)

    assert "if name in text" in check_open_application_source
    assert "_contains_any_bounded" not in check_search_source


# =======================================================================
# PHASE 11.3.2: selective Roman-Urdu spelling/imperative hardening for
# the GENERAL (non-dangerous) vocabulary only - "khol dou", a small
# "kar do" split-imperative family (mute/unmute/volume up/volume down
# only), "daba do" (all four PRESS_KEY_MARKERS keys), and "chala do"
# (PLAY_MARKERS). Phase 11.2's dangerous-command recognition remains
# frozen; this section also re-proves it was not touched.
# =======================================================================

# ---- A. Positive recognition - new variant AND its existing
# equivalent both still resolve identically ----

NEW_SPELLING_VARIANT_CASES = (
    # "khol dou" - open-application, representative apps.
    ("youtube khol dou", "open youtube"),
    ("github khol dou", "open github"),
    ("khol dou youtube", "open youtube"),  # order-independence preserved
    # existing equivalents, unaffected
    ("youtube khol do", "open youtube"),
    ("youtube kholo", "open youtube"),
    # "kar do" family - mute/unmute/volume only
    ("mute kar do", "mute"),
    ("khamosh kar do", "mute"),
    ("unmute kar do", "unmute"),
    ("un mute kar do", "unmute"),
    ("awaz zyada kar do", "volume up"),
    ("awaz kam kar do", "volume down"),
    ("volume kam kar do", "volume down"),
    # existing equivalents, unaffected
    ("mute karo", "mute"),
    ("unmute karo", "unmute"),
    ("awaz zyada karo", "volume up"),
    ("awaz kam karo", "volume down"),
    # "daba do" - all four keys
    ("enter daba do", "press enter"),
    ("escape daba do", "press escape"),
    ("space daba do", "press space"),
    ("tab daba do", "press tab"),
    # existing equivalents, unaffected
    ("enter dabao", "press enter"),
    # "chala do" - play
    ("music chala do", "play"),
    ("chala do", "play"),
    # existing equivalent, unaffected
    ("chalao", "play"),
)


def test_new_roman_urdu_spelling_variants_are_recognized():
    for phrase, expected in NEW_SPELLING_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


# ---- B. Regression: every phrase already proven to work before this
# phase (Phase 11.3.1's own legitimate-phrase sweep) still produces the
# exact same canonical command. ----

def test_pre_11_3_2_legitimate_phrases_still_produce_identical_output():
    for phrase, expected in LEGITIMATE_GENERAL_PHRASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_pre_11_3_2_dangerous_phrases_still_produce_identical_output():
    for phrase in LOCK_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "lock computer", phrase
    for phrase in SHUTDOWN_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "shutdown computer", phrase
    for phrase in RESTART_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "restart computer", phrase


# ---- C. Boundary safety: the new markers must not match as a
# mid-word substring of a longer, unrelated word - the same class of
# case Phase 11.3.1 already closed for the pre-existing vocabulary,
# now verified for the newly added markers too. ----

NEW_MARKER_MID_WORD_FALSE_POSITIVE_CASES = (
    "khol dosti",       # "khol do" + "sti" ("dosti" = a real word, "friendship")
    "daba dog",         # "daba do" + "g"
    "mute kar dobara",  # "kar do" + "bara" ("dobara" = a real word, "again")
    "chala dost",       # "chala do" + "st" ("dost" = a real word, "friend")
    "chala dobara",     # "chala do" + "bara"
)


def test_new_markers_reject_mid_word_matches():
    for phrase in NEW_MARKER_MID_WORD_FALSE_POSITIVE_CASES:
        assert multilingual_normalizer.understand(phrase) is None, phrase


# ---- D. Dangerous-command safety: every newly added GENERAL marker,
# combined with "computer"/"کمپیوٹر", must never produce a dangerous
# canonical command - none of these new markers appear in any
# LOCK/SHUTDOWN/RESTART_ACTION_PHRASES entry, so this proves the
# addition didn't accidentally create a collision. ----

NEW_MARKERS_FOR_DANGEROUS_SWEEP = (
    "khol dou",
    "chala do",
    "mute kar do", "khamosh kar do",
    "unmute kar do", "un mute kar do",
    "awaz zyada kar do",
    "awaz kam kar do", "volume kam kar do",
    "enter daba do", "escape daba do", "space daba do", "tab daba do",
)

DANGEROUS_PHRASES_11_3_2 = ("lock computer", "shutdown computer", "restart computer")


def test_new_markers_combined_with_computer_noun_never_produce_dangerous_command():
    for marker in NEW_MARKERS_FOR_DANGEROUS_SWEEP:
        for noun in ("computer", "کمپیوٹر"):
            for phrase in (f"{noun} {marker}", f"{marker} {noun}"):
                result = multilingual_normalizer.understand(phrase)
                assert result not in DANGEROUS_PHRASES_11_3_2, phrase


def test_specific_named_dangerous_safety_examples():
    """The exact phrases named in the Phase 11.3.2 spec's safety
    boundary section, verified directly."""

    assert multilingual_normalizer.understand("computer mute kar do") not in DANGEROUS_PHRASES_11_3_2
    assert multilingual_normalizer.understand("computer unmute kar do") not in DANGEROUS_PHRASES_11_3_2
    assert multilingual_normalizer.understand("کمپیوٹر mute kar do") not in DANGEROUS_PHRASES_11_3_2


# ---- E. Phase 11.2 frozen-code proof, re-verified after this phase's
# edits (same snapshot values as Phase 11.3.1's own proof) ----

def test_dangerous_regex_patterns_still_byte_for_byte_unchanged_after_11_3_2():
    assert multilingual_normalizer.LOCK_DANGEROUS_RE.pattern == FROZEN_LOCK_PATTERN
    assert multilingual_normalizer.SHUTDOWN_DANGEROUS_RE.pattern == FROZEN_SHUTDOWN_PATTERN
    assert multilingual_normalizer.RESTART_DANGEROUS_RE.pattern == FROZEN_RESTART_PATTERN


def test_dangerous_action_phrase_tuples_still_unchanged_after_11_3_2():
    assert multilingual_normalizer.LOCK_ACTION_PHRASES == (
        "lock karo", "lock کرو", "لاک کرو", "لاک karo",
    )
    assert multilingual_normalizer.SHUTDOWN_ACTION_PHRASES == (
        "band karo", "band کرو", "بند کرو", "بند karo",
        "shutdown karo", "shutdown کرو",
    )
    assert multilingual_normalizer.RESTART_ACTION_PHRASES == (
        "restart karo", "restart کرو", "ری اسٹارٹ کرو", "ری اسٹارٹ karo",
    )


def test_check_dangerous_still_does_not_call_the_bounded_helper_after_11_3_2():
    tree = ast.parse(inspect.getsource(multilingual_normalizer))

    check_dangerous_node = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_check_dangerous"
    )

    called_names = {
        node.func.id
        for node in ast.walk(check_dangerous_node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "_contains_any_bounded" not in called_names
    assert "_contains_any" not in called_names


# ---- F. Feature flag ----

def test_multilingual_layer_flag_reflects_completed_rollout_after_11_3_2():
    assert config.ENABLE_MULTILINGUAL_LAYER is True


# ---- G. Imports ----

def test_module_still_only_imports_re_and_intent_parser_after_11_3_2():
    imported_names = sorted(
        name for name, value in vars(multilingual_normalizer).items()
        if inspect.ismodule(value)
    )
    assert imported_names == ["intent_parser", "re"]


# =======================================================================
# PHASE 11.3.3: precedence & conflict test hardening. TEST-ONLY - no
# source file is modified by this phase. Every test below documents
# EXISTING, already-implemented behavior (verified empirically against
# the actual current implementation before being written) - none of
# them impose a redesign, and none of them touch _CHECKERS'
# construction, KNOWN_APPLICATIONS, or any Phase 11.2 dangerous code.
# =======================================================================

# ---- 1. Multi-application precedence: OPEN_APPLICATION resolution
# uses intent_parser.KNOWN_APPLICATIONS' own (insertion) dict order,
# not the order application names appear in the spoken text. ----

def test_multi_application_precedence_dict_order_not_textual_order():
    """The two examples named in the Phase 11.3 architecture audit,
    locked down as regression tests. "chrome" (index 0 in
    KNOWN_APPLICATIONS) wins over "youtube" (index 2) regardless of
    which one is spoken first."""

    assert multilingual_normalizer.understand(
        "chrome kholo aur youtube kholo"
    ) == "open chrome"

    assert multilingual_normalizer.understand(
        "youtube kholo phir chrome kholo"
    ) == "open chrome"


def test_multi_application_precedence_wins_even_when_textually_later():
    """"edge" appears textually FIRST in this phrase, but "chrome" is
    earlier in KNOWN_APPLICATIONS' insertion order (chrome, edge,
    youtube, ...) - chrome still wins. Proves the precedence is purely
    dict-order-driven, not a "first name found while scanning the text
    left-to-right" heuristic."""

    assert multilingual_normalizer.understand("edge kholo aur chrome kholo") == "open chrome"


def test_multi_application_precedence_additional_combinations():
    """Further combinations across the KNOWN_APPLICATIONS list,
    including one where the winning (dict-earlier) application is
    spoken LAST in the utterance ("settings" wins over "task manager"
    despite "task manager" appearing first)."""

    cases = (
        ("github kholo aur google kholo", "open google"),
        ("notepad kholo aur calculator kholo", "open notepad"),
        ("task manager kholo phir settings kholo", "open settings"),
    )

    for phrase, expected in cases:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_known_applications_order_is_the_documented_precedence_baseline():
    """Pins the exact KNOWN_APPLICATIONS insertion order the precedence
    tests above rely on - read directly from intent_parser.py, not
    assumed. If this order ever changes, this test fails first, making
    the dependency explicit rather than causing a confusing failure in
    the precedence tests themselves."""

    assert list(intent_parser.KNOWN_APPLICATIONS.keys()) == [
        "chrome", "edge", "youtube", "google", "github",
        "notepad", "calculator", "command prompt", "cmd",
        "powershell", "file explorer", "settings", "task manager",
    ]


# ---- 2. Checker-order precedence: _check_search runs before
# _check_open_application in _CHECKERS. ----

def test_checker_order_search_before_open_application():
    """"search cats aur chrome kholo" resolves to "open chrome" - but
    NOT because a recognized SEARCH intent was overridden by
    OPEN_APPLICATION. "search cats" does not match SEARCH_SUFFIX_
    MARKERS or SEARCH_PREFIX_MARKERS at all (it lacks the required
    "تلاش کرو"/"talash karo"/"dhoondo"/"search karo" phrase structure -
    bare "search" is not itself a marker), so _check_search() returns
    None for the whole phrase, which then falls through to
    _check_open_application() - the only checker that matches anything
    in this text at all."""

    assert multilingual_normalizer.understand(
        "search cats aur chrome kholo"
    ) == "open chrome"

    # Direct proof of the stated reason: "search cats" alone matches no
    # SEARCH marker and resolves to nothing.
    assert multilingual_normalizer.understand("search cats") is None


def test_checkers_order_is_the_documented_precedence_baseline():
    """Pins the exact _CHECKERS order the precedence tests above rely
    on - read directly from the module, not assumed."""

    assert [checker.__name__ for checker in multilingual_normalizer._CHECKERS] == [
        "_check_dangerous",
        "_check_screenshot",
        "_check_window_control",
        "_check_close_application",
        "_check_media",
        "_check_mute_unmute",
        "_check_set_volume",
        "_check_volume_up_down",
        "_check_keyboard",
        "_check_scroll",
        "_check_tab_browser",
        "_check_search",
        "_check_open_application",
        "_check_open_browser",
        "_check_time_date",
        "_check_greeting",
        "_check_exit",
    ]


# ---- 3. Multi-intent safety: exactly one canonical command is ever
# returned; no clause splitting, no multi-command execution. ----

def test_multi_intent_phrase_returns_exactly_one_canonical_command():
    """understand() returns a single string or None by construction
    (its own return type/control flow - see its docstring) - it cannot
    return multiple commands. These tests confirm WHICH single value is
    produced for phrases naming two intents, documenting the existing
    first-match-wins behavior rather than any multi-execution."""

    cases = (
        "chrome kholo aur youtube kholo",
        "youtube kholo phir chrome kholo",
    )

    for phrase in cases:
        result = multilingual_normalizer.understand(phrase)
        assert isinstance(result, str)
        assert result == "open chrome"


def test_natural_language_does_not_split_on_urdu_conjunctions():
    """Read-only observation (natural_language.py is not modified by
    this phase, or by Phase 11.3 at all): clause-splitting recognizes
    only English "and"/"then"/"and then" - not "aur"/"phir" - so these
    multi-intent-looking Roman-Urdu phrases are never split upstream;
    the whole phrase reaches multilingual_normalizer.understand() as
    ONE string, which is why exactly one canonical command comes out
    the other end. This is existing, unmodified behavior."""

    import natural_language

    phrase = "chrome kholo aur youtube kholo"
    assert natural_language.split_into_clauses(phrase) == [phrase]


# ---- 4. New Phase 11.3.2 marker conflict checks ----

def test_11_3_2_markers_resolve_to_their_documented_canonical_commands():
    cases = (
        ("mute kar do", "mute"),
        ("unmute kar do", "unmute"),
        ("un mute kar do", "unmute"),
        ("awaz zyada kar do", "volume up"),
        ("awaz kam kar do", "volume down"),
        ("volume kam kar do", "volume down"),
        ("enter daba do", "press enter"),
        ("music chala do", "play"),
        ("youtube khol dou", "open youtube"),
    )

    for phrase, expected in cases:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_unmute_variants_do_not_resolve_to_mute_despite_substring_relationship():
    """"unmute kar do" and "un mute kar do" both literally CONTAIN
    "mute kar do" as a substring (MUTE_MARKERS gained "mute kar do" in
    Phase 11.3.2, so this is a real, checkable overlap, not a
    hypothetical one). Correctness here depends entirely on
    _check_mute_unmute() checking UNMUTE_MARKERS before MUTE_MARKERS -
    existing, unmodified order - which this test locks down."""

    assert multilingual_normalizer.understand("unmute kar do") == "unmute"
    assert multilingual_normalizer.understand("un mute kar do") == "unmute"
    assert multilingual_normalizer.understand("unmute kar do") != "mute"
    assert multilingual_normalizer.understand("un mute kar do") != "mute"


# ---- 5/6. Phase 11.2 dangerous-command regression - re-verified as
# part of this (test-only) phase, not modified. ----

def test_phase_11_2_dangerous_commands_unchanged_after_11_3_3():
    for phrase in LOCK_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "lock computer", phrase
    for phrase in SHUTDOWN_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "shutdown computer", phrase
    for phrase in RESTART_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "restart computer", phrase

    assert multilingual_normalizer.LOCK_DANGEROUS_RE.pattern == FROZEN_LOCK_PATTERN
    assert multilingual_normalizer.SHUTDOWN_DANGEROUS_RE.pattern == FROZEN_SHUTDOWN_PATTERN
    assert multilingual_normalizer.RESTART_DANGEROUS_RE.pattern == FROZEN_RESTART_PATTERN

    assert multilingual_normalizer.LOCK_ACTION_PHRASES == (
        "lock karo", "lock کرو", "لاک کرو", "لاک karo",
    )
    assert multilingual_normalizer.SHUTDOWN_ACTION_PHRASES == (
        "band karo", "band کرو", "بند کرو", "بند karo",
        "shutdown karo", "shutdown کرو",
    )
    assert multilingual_normalizer.RESTART_ACTION_PHRASES == (
        "restart karo", "restart کرو", "ری اسٹارٹ کرو", "ری اسٹارٹ karo",
    )


def test_no_new_kar_do_dangerous_vocabulary_was_added():
    """Explicit, named proof that this phase did not do what it was
    told not to: none of the "kar do"-family dangerous phrasings the
    Phase 11.3.2 spec explicitly forbade are recognized as dangerous."""

    forbidden_still_unrecognized = (
        "lock kar do",
        "computer lock kar do",
        "shutdown kar do",
        "computer shutdown kar do",
        "band kar do",
        "computer band kar do",
        "restart kar do",
        "computer restart kar do",
    )

    dangerous_phrases = ("lock computer", "shutdown computer", "restart computer")

    for phrase in forbidden_still_unrecognized:
        assert multilingual_normalizer.understand(phrase) not in dangerous_phrases, phrase


# =======================================================================
# PHASE 11.5: expanded natural-language coverage - greeting variants,
# a generic "browser" open, additional volume-up/down phrasings, scroll
# up/down (a brand-new capability - see keyboard_control.scroll_up()/
# scroll_down()), and additional exit phrasings. Existing English
# commands and every marker phrase from Phase 11.1-11.3.3 are untouched
# - only new marker phrases/checkers were added.
# =======================================================================

# ---- A. Greeting: "kaise ho" and spelling variants ----

GREETING_VARIANT_CASES = (
    "kaise ho",
    "kaisay ho",
    "kese ho",
    "kesay ho",
    "aap kaise ho",
    "tum kaise ho",
)


def test_greeting_variants_all_resolve_to_hello():
    for phrase in GREETING_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) == "hello", phrase


# ---- B. Browser / application open ----

BROWSER_OPEN_CASES = (
    "browser kholo",
    "brouser kholo",
    "mera browser kholo",
    "mera brouser kholo",
    "browser open karo",
    "chrome kholo",
    "chrome open karo",
)


def test_browser_open_variants_all_resolve_to_open_chrome():
    for phrase in BROWSER_OPEN_CASES:
        assert multilingual_normalizer.understand(phrase) == "open chrome", phrase


def test_bare_browser_word_without_open_marker_is_not_recognized():
    # Fail-closed, same discipline as test_open_application_without_
    # marker_is_not_recognized() above: the bare word alone (no
    # open-verb marker present) must never be treated as a command.
    assert multilingual_normalizer.understand("browser") is None
    assert multilingual_normalizer.understand("brouser") is None


def test_specific_browser_name_is_not_shadowed_by_generic_browser_check():
    # "edge kholo" must still resolve to the SPECIFIC named browser,
    # not the generic "open chrome" fallback - proves _check_open_
    # application() (checked first) wins over _check_open_browser().
    assert multilingual_normalizer.understand("edge kholo") == "open edge"


# ---- C. Volume up/down: additional phrasings and misspellings ----

VOLUME_UP_VARIANT_CASES = (
    "volume badha do",
    "volume barha do",
    "volume bara do",
    "volume zyada kar do",
    "volume jyada kar do",
    "awaaz badha do",
    "awaz barha do",
)

VOLUME_DOWN_VARIANT_CASES = (
    "volume kam kar do",  # pre-existing, must still work unchanged
    "volume kam karo",    # pre-existing, must still work unchanged
    "volume neeche karo",
    "awaaz kam kar do",
    "awaz kam karo",       # pre-existing, must still work unchanged
)


def test_volume_up_variants_all_resolve_to_volume_up():
    for phrase in VOLUME_UP_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) == "volume up", phrase


def test_volume_down_variants_all_resolve_to_volume_down():
    for phrase in VOLUME_DOWN_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) == "volume down", phrase


# ---- D. Scroll up/down (brand-new capability) ----

SCROLL_UP_CASES = ("scroll upar", "scroll up", "upar scroll karo", "upar scroll kar do")
SCROLL_DOWN_CASES = ("scroll neeche", "scroll down", "neeche scroll karo", "neeche scroll kar do")


def test_scroll_up_variants_all_resolve_to_scroll_up():
    for phrase in SCROLL_UP_CASES:
        assert multilingual_normalizer.understand(phrase) == "scroll up", phrase


def test_scroll_down_variants_all_resolve_to_scroll_down():
    for phrase in SCROLL_DOWN_CASES:
        assert multilingual_normalizer.understand(phrase) == "scroll down", phrase


def test_scroll_niche_spelling_variant_resolves_to_scroll_down():
    assert multilingual_normalizer.understand("scroll niche") == "scroll down"


def test_niche_scroll_karo_resolves_to_scroll_down():
    assert multilingual_normalizer.understand("niche scroll karo") == "scroll down"


# ---- D.1 Browser tab management / navigation (brand-new capability) ----

def test_naya_tab_kholo_resolves_to_new_tab():
    assert multilingual_normalizer.understand("naya tab kholo") == "new tab"


def test_nya_tab_kholo_resolves_to_new_tab():
    assert multilingual_normalizer.understand("nya tab kholo") == "new tab"


def test_tab_band_karo_resolves_to_close_tab():
    assert multilingual_normalizer.understand("tab band karo") == "close tab"


def test_tab_band_kar_do_resolves_to_close_tab():
    assert multilingual_normalizer.understand("tab band kar do") == "close tab"


def test_tab_band_karo_does_not_resolve_to_exit():
    """"tab band karo" contains the generic _AMBIGUOUS_EXIT_MARKERS
    phrase "band karo" - it must resolve to closing the browser tab,
    never to exiting JARVIS (see _check_tab_browser()'s own docstring,
    checked before _check_exit() in _CHECKERS)."""
    assert multilingual_normalizer.understand("tab band karo") != "exit"


def test_wapas_jao_resolves_to_go_back():
    assert multilingual_normalizer.understand("wapas jao") == "go back"


def test_aagay_jao_resolves_to_go_forward():
    assert multilingual_normalizer.understand("aagay jao") == "go forward"


def test_agay_jao_resolves_to_go_forward():
    assert multilingual_normalizer.understand("agay jao") == "go forward"


def test_refresh_karo_resolves_to_refresh():
    assert multilingual_normalizer.understand("refresh karo") == "refresh"


# ---- Phase 11.12: additional Roman-Urdu navigation/tab aliases ----

def test_new_tab_kholo_resolves_to_new_tab():
    assert multilingual_normalizer.understand("new tab kholo") == "new tab"


def test_bare_tab_band_resolves_to_close_tab():
    """"tab band" with no trailing helper verb - a common clipped/STT-
    truncated form of "tab band karo"/"tab band kar do"."""
    assert multilingual_normalizer.understand("tab band") == "close tab"


def test_aage_jao_resolves_to_go_forward():
    assert multilingual_normalizer.understand("aage jao") == "go forward"


def test_aglay_page_par_jao_resolves_to_go_forward():
    assert multilingual_normalizer.understand("aglay page par jao") == "go forward"


def test_peechay_jao_resolves_to_go_back():
    assert multilingual_normalizer.understand("peechay jao") == "go back"


def test_peeche_jao_resolves_to_go_back():
    assert multilingual_normalizer.understand("peeche jao") == "go back"


# ---- E. Exit: "band ho jao"/"off ho jao" and bare "band karo" ----

EXIT_VARIANT_CASES = (
    "band ho jao",
    "band hojayo",
    "off ho jao",
    "off hojayo",
    "band karo",
    "jarvis band ho jao",
    "jarvis off ho jao",
)


def test_exit_variants_all_resolve_to_exit():
    for phrase in EXIT_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) == "exit", phrase


def test_exit_variants_never_resolve_to_a_dangerous_command():
    # "band ho jao"/"band karo" share the "band" word with the
    # dangerous SHUTDOWN vocabulary ("computer band karo") - direct
    # proof neither ever produces a dangerous canonical string.
    for phrase in EXIT_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) not in DANGEROUS_PHRASES, phrase


def test_computer_band_karo_still_wins_as_dangerous_not_exit():
    # The dangerous-command gate (_check_dangerous, checked FIRST in
    # _CHECKERS) must still claim "computer band karo" - the new bare
    # "band karo" exit marker must never shadow it.
    assert multilingual_normalizer.understand("computer band karo") == "shutdown computer"
    assert multilingual_normalizer.understand("کمپیوٹر بند کرو") == "shutdown computer"


def test_bare_band_karo_maps_to_exit():
    assert multilingual_normalizer.understand("band karo") == "exit"


def test_band_karo_with_a_known_application_name_is_not_exit():
    """The collision this phase originally guarded against by failing
    closed: "chrome band karo" most plausibly means "close chrome", not
    "exit JARVIS". As of Phase 11.7 (see _check_close_application()),
    this is no longer just suppressed - it resolves to the real,
    correct, safe "close <app>" action instead. This test now proves
    both halves: never "exit", and the real intended action instead."""

    for app in intent_parser.KNOWN_APPLICATIONS:
        phrase = f"{app} band karo"
        result = multilingual_normalizer.understand(phrase)
        assert result != "exit", phrase
        assert result == f"close {app}", phrase


# ---- F. Safety/structural re-verification ----

def test_phase_11_5_dangerous_recognition_unchanged():
    for phrase in LOCK_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "lock computer", phrase
    for phrase in SHUTDOWN_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "shutdown computer", phrase
    for phrase in RESTART_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "restart computer", phrase

    assert multilingual_normalizer.LOCK_DANGEROUS_RE.pattern == FROZEN_LOCK_PATTERN
    assert multilingual_normalizer.SHUTDOWN_DANGEROUS_RE.pattern == FROZEN_SHUTDOWN_PATTERN
    assert multilingual_normalizer.RESTART_DANGEROUS_RE.pattern == FROZEN_RESTART_PATTERN


def test_phase_11_5_pre_existing_legitimate_phrases_still_produce_identical_output():
    for phrase, expected in LEGITIMATE_GENERAL_PHRASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_phase_11_5_module_still_only_imports_re_and_intent_parser():
    imported_names = sorted(
        name for name, value in vars(multilingual_normalizer).items()
        if inspect.ismodule(value)
    )
    assert imported_names == ["intent_parser", "re"]


def test_phase_11_5_new_markers_reject_mid_word_matches():
    """Same word-boundary discipline as the Phase 11.3.1/11.3.2 mid-word
    false-positive sweeps, applied to the new Phase 11.5 markers."""

    cases = (
        "browser khologe",       # OPEN_MARKERS "kholo" + "ge" (real word)
        "scroll upardar",        # SCROLL_UP_MARKERS "scroll upar" + "dar"
        "volume badha dobara",   # VOLUME_UP_MARKERS "badha do" + "bara"
        "band ho jaoge",         # EXIT_MARKERS "band ho jao" + "ge"
        "kaise hote",            # GREETING_MARKERS "kaise ho" + "te"
    )

    for phrase in cases:
        assert multilingual_normalizer.understand(phrase) is None, phrase


# =======================================================================
# PHASE 11.7: finish-the-job pass - targeted "close <app>" (routes
# through the existing, unmodified window_control.handle_targeted()
# mechanism), Urdu-script equivalents for greeting/browser/scroll/exit,
# bounded intensifier phrasings ("thora"/"zara"), "upar"/"oopar" and
# "awaz"/"awaaz" spelling parity, "<key> key dabao", and mixed
# English/Urdu "time kya hai"/"date kya hai". No existing marker,
# checker, or _CHECKERS order was removed - only added to.
# =======================================================================

# ---- A. Targeted "close <app>" - the collision fix ----

CLOSE_APP_ROMAN_CASES = (
    ("chrome band karo", "close chrome"),
    ("chrome close karo", "close chrome"),
    ("chrome band kar do", "close chrome"),
    ("chrome close kar do", "close chrome"),
)

CLOSE_BROWSER_CASES = (
    ("browser band karo", "close chrome"),
    ("browser close karo", "close chrome"),
    ("brouser band karo", "close chrome"),
)

CLOSE_APP_URDU_CASES = (
    ("chrome بند کرو", "close chrome"),
    ("chrome بند کر دو", "close chrome"),
)


def test_close_app_roman_urdu_variants_resolve_to_close_app():
    for phrase, expected in CLOSE_APP_ROMAN_CASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_close_browser_variants_resolve_to_close_chrome():
    for phrase, expected in CLOSE_BROWSER_CASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_close_app_urdu_script_variants_resolve_to_close_app():
    for phrase, expected in CLOSE_APP_URDU_CASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_close_app_never_resolves_to_exit_for_any_known_application():
    for app in intent_parser.KNOWN_APPLICATIONS:
        for marker in ("band karo", "band kar do", "close karo", "close kar do"):
            phrase = f"{app} {marker}"
            result = multilingual_normalizer.understand(phrase)
            assert result != "exit", phrase
            assert result == f"close {app}", phrase


def test_close_app_never_resolves_to_a_dangerous_command():
    for app in intent_parser.KNOWN_APPLICATIONS:
        for marker in multilingual_normalizer.CLOSE_APP_MARKERS:
            phrase = f"{app} {marker}"
            assert multilingual_normalizer.understand(phrase) not in DANGEROUS_PHRASES, phrase


def test_untargeted_window_close_still_wins_over_close_application():
    """"window band karo" (untargeted "close THIS window") must still
    resolve via _check_window_control (checked BEFORE _check_close_
    application) - "window" is not a KNOWN_APPLICATIONS name, so this
    is also directly proven by construction, not just by ordering."""

    assert multilingual_normalizer.understand("window band karo") == "close this window"
    assert multilingual_normalizer.understand("ونڈو بند کرو") == "close this window"


def test_close_application_end_to_end_through_the_real_window_control_handler():
    """Recursion + real-handler proof: the canonical string this module
    renders ("close <app>") is handed back to CommandProcessor.
    process(), which dispatches it through the REAL, unmodified
    window_control.handle_targeted() - never a direct control-module
    call from multilingual_normalizer.py itself.

    Deliberately uses "youtube", NOT "chrome" - see
    test_close_application_is_unreachable_for_bare_matched_apps_known_
    limitation() below for why "chrome band karo" can never reach this
    checker at all in the real end-to-end pipeline (web_control.
    handle()'s pre-existing bare "chrome" substring check, part of the
    PRIMARY dispatch chain, always claims it first). "youtube" has no
    such bare match anywhere in the primary chain (web_control only
    matches the exact "open youtube" substring).

    ENABLE_INTENT_FALLBACK_LAYER is explicitly turned OFF here: as of
    Phase 11.7, intent_layer.py ALSO recognizes "youtube band karo"
    (via its own new TARGETED_ACTION_SYNONYMS_UR - see tests/test_
    intent_layer.py for that layer's own dedicated coverage) and runs
    BEFORE the multilingual layer in commands.py's dispatch order, so
    without this override this test would actually be exercising THAT
    layer, not this module's _check_close_application() - which would
    make its name and docstring misleading. Disabling it here isolates
    and proves multilingual_normalizer.py's OWN recursion/wiring
    specifically."""

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", False), \
         patch("window_control.user32.PostMessageW") as mock_post, \
         patch("window_control.user32.GetForegroundWindow", return_value=0), \
         patch(
             "window_control.find_window_by_application", return_value=777
         ):
        result = processor.process("youtube band karo")

    assert result is True
    mock_post.assert_called_once_with(777, window_control.WM_CLOSE, 0, 0)
    assert voice.spoken == ["Closing Youtube."]


def test_close_application_is_unreachable_for_bare_matched_apps_known_limitation():
    """Documents a genuine, PRE-EXISTING architectural characteristic
    (not introduced by this phase, and not fixed by it - see the Phase
    11.7 report): "chrome"/"edge"/"notepad"/"calculator"/etc. are all
    bare-substring-matched by web_control.handle()/system_control.
    handle_application() - part of the PRIMARY dispatch chain, checked
    LONG before the multilingual fallback layer is ever consulted (see
    commands.py's dispatch order) - so "chrome band karo" is claimed by
    that bare "chrome" match and OPENS Chrome, never reaching this
    module's _check_close_application() at all. This is the exact same
    documented limitation intent_layer.py's own TARGETED_WINDOW_ACTION
    rule already discloses in its module docstring ("most existing
    control-module handlers already match very broad bare substrings
    ... a targeted-window ... phrase ... will usually already be
    handled (sometimes with the wrong action) ... before this module is
    ever reached"). Critically, this is still SAFE: the outcome is
    "opens the app" (harmless, pre-existing, unrelated to this phase),
    never "exit JARVIS" - the one behavior task step 7 required this
    phase to prevent."""

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        voice_spoken = []

        class FakeVoice:
            def speak(self, text):
                voice_spoken.append(text)

        processor = commands.CommandProcessor(FakeVoice())
        result = processor.process("chrome band karo")

    assert result is True
    assert result is not False
    mock_open.assert_called_once_with("https://www.google.com")
    assert voice_spoken == ["Opening Chrome."]


# ---- B. Urdu-script equivalents (hello/browser/scroll/exit) ----

def test_urdu_script_how_are_you_resolves_to_hello():
    assert multilingual_normalizer.understand("کیسے ہو") == "hello"


def test_urdu_script_browser_open_resolves_to_open_chrome():
    assert multilingual_normalizer.understand("براؤزر کھولو") == "open chrome"


def test_urdu_script_scroll_up_down_resolve_correctly():
    assert multilingual_normalizer.understand("اسکرول اوپر") == "scroll up"
    assert multilingual_normalizer.understand("اوپر اسکرول کرو") == "scroll up"
    assert multilingual_normalizer.understand("اسکرول نیچے") == "scroll down"
    assert multilingual_normalizer.understand("نیچے اسکرول کرو") == "scroll down"


def test_urdu_script_exit_variants_resolve_to_exit():
    assert multilingual_normalizer.understand("بند ہو جاؤ") == "exit"
    assert multilingual_normalizer.understand("آف ہو جاؤ") == "exit"
    assert multilingual_normalizer.understand("بند کرو") == "exit"


def test_urdu_script_exit_variants_never_resolve_to_a_dangerous_command():
    for phrase in ("بند ہو جاؤ", "آف ہو جاؤ", "بند کرو"):
        assert multilingual_normalizer.understand(phrase) not in DANGEROUS_PHRASES, phrase


def test_urdu_script_bare_band_karo_with_known_app_is_close_not_exit():
    result = multilingual_normalizer.understand("chrome بند کرو")
    assert result == "close chrome"
    assert result != "exit"


def test_urdu_script_computer_band_karo_still_wins_as_dangerous():
    """Symmetry check: the Urdu-script bare exit/close marker "بند کرو"
    must never shadow the dangerous-command gate for the "کمپیوٹر"
    noun, exactly like the Roman-Urdu "band karo" already doesn't."""

    assert multilingual_normalizer.understand("کمپیوٹر بند کرو") == "shutdown computer"


# ---- C. Bounded intensifier phrasings ("thora"/"zara") ----

INTENSIFIER_CASES = (
    ("volume thora barha do", "volume up"),
    ("volume thora badha do", "volume up"),
    ("awaaz zara zyada karo", "volume up"),
    ("awaz zara zyada karo", "volume up"),
    ("volume thora kam karo", "volume down"),
    ("volume thora kam kar do", "volume down"),
)


def test_intensifier_phrasings_resolve_correctly():
    for phrase, expected in INTENSIFIER_CASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_intensifier_bounded_not_a_generic_word_wildcard():
    """Fail-closed proof that "thora"/"zara" were added as bounded,
    explicit literal phrases - NOT a generic "any word may appear
    between volume and the verb" pattern. A NONSENSE word standing in
    for the intensifier (in the same slot "thora"/"zara" occupy) must
    NOT match volume up/down - if this module implemented a generic
    "<any word> barha do" wildcard instead of the specific enumerated
    phrases, these would incorrectly resolve to "volume up"/"volume
    down"."""

    assert multilingual_normalizer.understand("volume xyz barha do") is None
    assert multilingual_normalizer.understand("volume xyz badha do") is None
    assert multilingual_normalizer.understand("volume xyz kam karo") is None
    assert multilingual_normalizer.understand("awaaz xyz zyada karo") is None


# ---- D. "upar"/"oopar" and "awaz"/"awaaz" spelling parity ----

def test_scroll_oopar_spelling_variant_resolves_to_scroll_up():
    assert multilingual_normalizer.understand("scroll oopar") == "scroll up"
    assert multilingual_normalizer.understand("oopar scroll karo") == "scroll up"
    assert multilingual_normalizer.understand("oopar scroll kar do") == "scroll up"


def test_awaaz_set_volume_percent_recognized():
    """VOLUME_WORD_MARKERS gained "awaaz" (Phase 11.7) - previously only
    "awaz"/"volume"/"آواز" triggered the SET_VOLUME percent check."""

    assert multilingual_normalizer.understand("awaaz 40 percent karo") == "set volume to 40"


# ---- E. "<key> key dabao" ----

KEY_DABAO_CASES = (
    ("enter key dabao", "press enter"),
    ("escape key dabao", "press escape"),
    ("space key dabao", "press space"),
    ("tab key dabao", "press tab"),
)


def test_key_dabao_with_english_key_word_resolves_correctly():
    for phrase, expected in KEY_DABAO_CASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


# ---- F. Mixed English/Urdu time/date ----

def test_mixed_time_kya_hai_resolves_to_time():
    assert multilingual_normalizer.understand("time kya hai") == "what time is it"


def test_mixed_date_kya_hai_resolves_to_date():
    assert multilingual_normalizer.understand("date kya hai") == "what is the date"
    # Also matches as a substring of the fuller phrase - word-boundary
    # anchored, so the leading "aaj ki" prefix needs no marker of its
    # own.
    assert multilingual_normalizer.understand("aaj ki date kya hai") == "what is the date"


# ---- G. Mid-word false-positive sweep for every new Phase 11.7 marker ----

PHASE_11_7_MID_WORD_FALSE_POSITIVE_CASES = (
    "chrome band karobar",     # CLOSE_APP_MARKERS "band karo" + "bar"
    "scroll oopardar",         # SCROLL_UP_MARKERS "scroll oopar" + "dar"
    "volume thora barha dobara",  # "thora barha do" + "bara"
    "بند ہو جاؤگے",            # EXIT_MARKERS "بند ہو جاؤ" + future suffix
    "کیسے ہوگے",               # GREETING_MARKERS "کیسے ہو" + future suffix
    "enter key dabaoge",       # PRESS_KEY_MARKERS "enter key dabao" + "ge"
    "time kya haigi",          # TIME_MARKERS "time kya hai" + "gi"
)


def test_phase_11_7_new_markers_reject_mid_word_matches():
    for phrase in PHASE_11_7_MID_WORD_FALSE_POSITIVE_CASES:
        assert multilingual_normalizer.understand(phrase) is None, phrase


# ---- H. Canonical-command safety re-verification ----

def test_phase_11_7_dangerous_recognition_unchanged():
    for phrase in LOCK_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "lock computer", phrase
    for phrase in SHUTDOWN_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "shutdown computer", phrase
    for phrase in RESTART_PHRASES:
        assert multilingual_normalizer.understand(phrase) == "restart computer", phrase

    assert multilingual_normalizer.LOCK_DANGEROUS_RE.pattern == FROZEN_LOCK_PATTERN
    assert multilingual_normalizer.SHUTDOWN_DANGEROUS_RE.pattern == FROZEN_SHUTDOWN_PATTERN
    assert multilingual_normalizer.RESTART_DANGEROUS_RE.pattern == FROZEN_RESTART_PATTERN
    assert multilingual_normalizer.LOCK_ACTION_PHRASES == (
        "lock karo", "lock کرو", "لاک کرو", "لاک karo",
    )
    assert multilingual_normalizer.SHUTDOWN_ACTION_PHRASES == (
        "band karo", "band کرو", "بند کرو", "بند karo",
        "shutdown karo", "shutdown کرو",
    )
    assert multilingual_normalizer.RESTART_ACTION_PHRASES == (
        "restart karo", "restart کرو", "ری اسٹارٹ کرو", "ری اسٹارٹ karo",
    )


def test_phase_11_7_pre_existing_legitimate_phrases_still_produce_identical_output():
    for phrase, expected in LEGITIMATE_GENERAL_PHRASES:
        assert multilingual_normalizer.understand(phrase) == expected, phrase


def test_phase_11_7_pre_existing_phase_11_5_cases_still_produce_identical_output():
    for phrase in GREETING_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) == "hello", phrase
    for phrase in BROWSER_OPEN_CASES:
        assert multilingual_normalizer.understand(phrase) == "open chrome", phrase
    for phrase in VOLUME_UP_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) == "volume up", phrase
    for phrase in VOLUME_DOWN_VARIANT_CASES:
        assert multilingual_normalizer.understand(phrase) == "volume down", phrase
    for phrase in SCROLL_UP_CASES:
        assert multilingual_normalizer.understand(phrase) == "scroll up", phrase
    for phrase in SCROLL_DOWN_CASES:
        assert multilingual_normalizer.understand(phrase) == "scroll down", phrase


def test_phase_11_7_module_still_only_imports_re_and_intent_parser():
    imported_names = sorted(
        name for name, value in vars(multilingual_normalizer).items()
        if inspect.ismodule(value)
    )
    assert imported_names == ["intent_parser", "re"]


def test_phase_11_7_module_still_imports_no_control_module():
    """Re-verification of the module's own structural PURE guarantee
    (see test_module_imports_no_control_module_and_no_execution_
    primitive above) after this phase's additions - _check_close_
    application() renders a plain string, it never imports or calls
    window_control itself."""

    imported_names = {
        name for name, value in vars(multilingual_normalizer).items()
        if inspect.ismodule(value)
    }
    for forbidden in FORBIDDEN_IMPORT_NAMES:
        assert forbidden not in imported_names


def test_phase_11_7_understand_never_raises_for_arbitrary_text():
    weird_inputs = (
        "براؤزر" * 200,
        "chrome " + "band karo " * 50,
        "١٢٣ thora zara",
        "",
        None,
    )
    for weird in weird_inputs:
        multilingual_normalizer.understand(weird)
