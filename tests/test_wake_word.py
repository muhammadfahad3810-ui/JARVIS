import io

import jarvis


# ---------------------------------------------------------------------
# extract_command_after_wake_word()
# ---------------------------------------------------------------------

def test_wake_word_alone_returns_empty_string():
    assert jarvis.extract_command_after_wake_word("jarvis") == ""


def test_wake_word_with_command():
    assert jarvis.extract_command_after_wake_word(
        "jarvis open chrome"
    ) == "open chrome"


def test_wake_word_anywhere_in_phrase():
    assert jarvis.extract_command_after_wake_word(
        "hey jarvis open chrome"
    ) == "open chrome"


def test_doubled_wake_word_is_handled_gracefully():
    assert jarvis.extract_command_after_wake_word(
        "jarvis jarvis open chrome"
    ) == "open chrome"


def test_tripled_wake_word_is_handled_gracefully():
    assert jarvis.extract_command_after_wake_word(
        "jarvis jarvis jarvis open chrome"
    ) == "open chrome"


def test_no_wake_word_returns_none():
    assert jarvis.extract_command_after_wake_word("open chrome") is None


# ---------------------------------------------------------------------
# Wake-word variations (Phase 4)
# ---------------------------------------------------------------------

def test_jervis_alias_is_recognized():
    assert jarvis.extract_command_after_wake_word(
        "jervis open chrome"
    ) == "open chrome"


def test_possessive_jarviss_is_recognized():
    assert jarvis.extract_command_after_wake_word(
        "jarvis's open chrome"
    ) == "open chrome"


def test_repeated_jervis_alias_is_handled():
    assert jarvis.extract_command_after_wake_word(
        "jervis jervis open chrome"
    ) == "open chrome"


def test_mixed_alias_and_canonical_repeat_is_handled():
    assert jarvis.extract_command_after_wake_word(
        "jarvis jervis open chrome"
    ) == "open chrome"


def test_word_that_merely_contains_wake_word_does_not_match():
    """'jarvison' contains 'jarvis' as a substring but is not the wake
    word - word-boundary matching must reject it."""
    assert jarvis.extract_command_after_wake_word(
        "jarvison is not a real word"
    ) is None


def test_word_ending_in_wake_word_does_not_match():
    assert jarvis.extract_command_after_wake_word(
        "myjarvis open chrome"
    ) is None


# ---------------------------------------------------------------------
# contains_wake_word()
# ---------------------------------------------------------------------

def test_contains_wake_word_true_for_canonical():
    assert jarvis.contains_wake_word("jarvis open chrome") is True


def test_contains_wake_word_true_for_alias():
    assert jarvis.contains_wake_word("jervis open chrome") is True


def test_contains_wake_word_false_when_absent():
    assert jarvis.contains_wake_word("open chrome") is False


def test_contains_wake_word_false_for_substring_word():
    assert jarvis.contains_wake_word("jarvison opens things") is False


# =======================================================================
# PHASE 11.9 (Step 2): console I/O hardening - jarvis.harden_console_io()
#
# Direct, real-stream proof of the confirmed Phase 11.8 live bug and its
# fix: a genuine io.TextIOWrapper over a cp1252-encoded buffer (the same
# codec this Windows console actually used) raises UnicodeEncodeError on
# a bare write() of non-Latin-1 text BEFORE hardening, and does not
# after - never by mocking away the encoding problem, always
# reproducing it first.
# =======================================================================

PROBLEM_TEXT_SAMPLES = (
    "पखि़नै हुचं यहें",  # Devanagari - the exact class of text that
                          # crashed the Phase 11.8 live session
    "そんないので",         # Japanese
    "کمپیوٹر بند کرو",     # Urdu script - a LEGITIMATE recognition
                          # result this project must never crash on
    "\U0001F389\U0001F389",  # emoji, for good measure
)


def _cp1252_text_stream():
    """A real io.TextIOWrapper over an in-memory buffer, encoded as
    cp1252 - the same codec the Phase 11.8 live session's Windows
    console actually used. Not a mock: proves the crash and the fix
    against the real codec machinery."""

    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def test_problem_text_genuinely_crashes_an_unhardened_cp1252_stream():
    """Establishes the baseline failure BEFORE any fix is applied -
    proves this test suite is reproducing the real Phase 11.8 bug, not
    a hypothetical one."""

    for text in PROBLEM_TEXT_SAMPLES:

        stream = _cp1252_text_stream()

        try:
            stream.write(text)
            stream.flush()
            raised = False
        except UnicodeEncodeError:
            raised = True

        assert raised, f"expected {text!r} to crash an unhardened cp1252 stream"


def test_harden_console_io_prevents_the_crash_on_a_real_stream():
    for text in PROBLEM_TEXT_SAMPLES:

        stream = _cp1252_text_stream()
        jarvis.harden_console_io(stdout=stream, stderr=stream)

        # Must not raise - this is the actual regression proof.
        stream.write(text)
        stream.flush()


def test_harden_console_io_does_not_corrupt_ascii_text():
    """The fix must not change what gets written for ordinary text -
    only non-encodable text is affected."""

    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    jarvis.harden_console_io(stdout=stream, stderr=stream)

    stream.write("Opening Chrome.")
    stream.flush()

    stream.buffer.seek(0)
    assert stream.buffer.read() == b"Opening Chrome."


def test_harden_console_io_reconfigures_to_utf8_replace():
    stream = _cp1252_text_stream()
    jarvis.harden_console_io(stdout=stream, stderr=stream)

    assert stream.encoding.lower().replace("-", "") == "utf8"
    assert stream.errors == "replace"


def test_harden_console_io_never_raises_when_reconfigure_is_missing():
    """A stream type without .reconfigure() at all (e.g. some redirected-
    output or test-harness stream types) must be silently skipped, not
    treated as an error - startup must never be blocked by this."""

    class NoReconfigure:
        pass

    jarvis.harden_console_io(stdout=NoReconfigure(), stderr=NoReconfigure())


def test_harden_console_io_never_raises_when_reconfigure_itself_raises():
    class BrokenReconfigure:
        def reconfigure(self, **kwargs):
            raise ValueError("nope")

    jarvis.harden_console_io(
        stdout=BrokenReconfigure(), stderr=BrokenReconfigure()
    )


def test_harden_console_io_defaults_to_real_sys_stdout_stderr():
    """Zero-argument call (as main() actually uses it) must not raise
    against whatever sys.stdout/sys.stderr happen to be in this process
    (pytest's own capture streams included)."""

    jarvis.harden_console_io()


def test_main_calls_harden_console_io_before_anything_else():
    """Structural proof, not just convention: main() hardens console
    I/O as its very first action, before constructing Jarvis() (which
    would touch the real microphone/TTS engine)."""

    import inspect

    source = inspect.getsource(jarvis.main)
    body_lines = [line.strip() for line in source.splitlines()[1:] if line.strip()]

    assert body_lines[0] == "harden_console_io()"


# =======================================================================
# PHASE 11.9 (Step 3): wake-word-omission recovery -
# jarvis.resolve_wake_word_omission()
#
# Pure-function tests, mirroring the style already used for intent_
# layer.understand()/multilingual_normalizer.understand() (which this
# function reuses, unmodified). No I/O, no execution, no mocking needed
# in this section - Jarvis-level integration (the confirm/execute flow)
# is covered separately in tests/test_pipeline.py and tests/
# test_security.py.
# =======================================================================

def test_resolve_wake_word_omission_none_and_empty_input():
    assert jarvis.resolve_wake_word_omission(None) is None
    assert jarvis.resolve_wake_word_omission("") is None


def test_resolve_wake_word_omission_unrecognizable_text_returns_none():
    assert jarvis.resolve_wake_word_omission("okay okay") is None
    assert jarvis.resolve_wake_word_omission("thank you very much") is None


# ---- The exact two live-observed Phase 11.8 failures ----

def test_resolve_wake_word_omission_recovers_live_observed_time_kya_hai():
    """"jarvis time kya hai" -> STT transcript "time kya hai" (Phase
    11.8 TEST 9, wake word cleanly dropped) - must now resolve to the
    correct canonical command via multilingual_normalizer.py."""

    assert jarvis.resolve_wake_word_omission("time kya hai") == "what time is it"


def test_resolve_wake_word_omission_recovers_live_observed_awaaz_kam_kar_do():
    """"jarvis volume kam kar do" -> STT transcript "awaaz kam kar do"
    (Phase 11.8 TEST 5) - must resolve to volume down."""

    assert jarvis.resolve_wake_word_omission("awaaz kam kar do") == "volume down"


# ---- English ----

def test_resolve_wake_word_omission_english_paraphrase_via_intent_layer():
    assert jarvis.resolve_wake_word_omission("power off the computer") is None
    assert jarvis.resolve_wake_word_omission("shut down the computer") is None
    assert jarvis.resolve_wake_word_omission("open youtube") == "open youtube"


# ---- Roman Urdu ----

def test_resolve_wake_word_omission_roman_urdu():
    assert jarvis.resolve_wake_word_omission("chrome kholo") == "open chrome"
    # NOT "mute karo" - command_parser.normalize() already rewrites
    # that to plain "mute" via its own pre-existing MUTE_WORD regex
    # (Phase 5), before either fallback resolver even runs - "khamosh
    # karo" (no literal "mute" substring) isolates the multilingual
    # layer specifically, matching this function's own documented
    # scope (see its docstring: it never re-implements what command_
    # parser.normalize() or the primary dispatch chain already do).
    assert jarvis.resolve_wake_word_omission("khamosh karo") == "mute"
    assert jarvis.resolve_wake_word_omission("scroll upar") == "scroll up"


# ---- Urdu script ----

def test_resolve_wake_word_omission_urdu_script():
    assert jarvis.resolve_wake_word_omission("چھوٹا کرو") == "minimize this window"
    assert jarvis.resolve_wake_word_omission("آواز بڑھاؤ") == "volume up"


# ---- Dangerous commands: structural, hard "never" - see also
# tests/test_security.py for the full sweep across every marker
# phrase/language. ----

def test_resolve_wake_word_omission_never_returns_a_dangerous_command():
    import commands

    dangerous_phrasings = (
        "shut down the computer",
        "turn off the computer",
        "restart the computer",
        "reboot the pc",
        "lock the computer",
        "computer band karo",
        "computer lock karo",
        "computer restart karo",
        "کمپیوٹر بند کرو",
        "کمپیوٹر لاک کرو",
    )

    for phrase in dangerous_phrasings:
        result = jarvis.resolve_wake_word_omission(phrase)
        assert result not in commands.DANGEROUS_COMMANDS, phrase
        assert result is None, phrase


# ---- Ambiguity: multi-clause or incomplete results are NOT resolved -
# too ambiguous for an unattended spoken confirmation prompt. ----

def test_resolve_wake_word_omission_multi_clause_utterance_returns_none():
    """A two-command utterance is exactly the kind of ambiguous result
    this function deliberately refuses to guess at - see its own
    docstring."""

    assert jarvis.resolve_wake_word_omission(
        "open chrome and search for python"
    ) is None


def test_resolve_wake_word_omission_incomplete_search_returns_none():
    """"search youtube" (bare, no query) is an INCOMPLETE intent_layer
    frame - must not be offered as a confirmable command."""

    assert jarvis.resolve_wake_word_omission("search youtube") is None


# ---- Feature-flag gating (the CALLER's responsibility, not this pure
# function's - resolve_wake_word_omission() itself has no flag check;
# jarvis.Jarvis._maybe_recover_omitted_wake_word() is what gates on
# config.ENABLE_WAKE_WORD_OMISSION_TOLERANCE - see test_pipeline.py). ----

def test_wake_word_omission_tolerance_flag_defaults_false():
    import config

    assert config.ENABLE_WAKE_WORD_OMISSION_TOLERANCE is False


def test_resolve_wake_word_omission_respects_layer_flags_being_off():
    """With BOTH fallback layers off, nothing can ever be resolved -
    same fail-closed contract as commands.CommandProcessor.process()
    itself when both flags are off."""

    import config
    from unittest.mock import patch

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", False), \
         patch.object(config, "ENABLE_MULTILINGUAL_LAYER", False):
        assert jarvis.resolve_wake_word_omission("time kya hai") is None
        assert jarvis.resolve_wake_word_omission("open youtube") is None


def test_resolve_wake_word_omission_never_raises_for_arbitrary_text():
    weird_inputs = (
        "",
        " ",
        "a" * 5000,
        "🎉" * 200,
        None,
        "\x00\x01\x02",
    )

    for weird in weird_inputs:
        jarvis.resolve_wake_word_omission(weird)


# =======================================================================
# PHASE 11.11 (Step 7): jarvis.is_wake_word_recovery_confirmation() -
# the WIDER, but still conservative, affirmative-word check used ONLY
# by Jarvis._maybe_recover_omitted_wake_word() (never by the Phase 9
# dangerous-command gate, which keeps using commands.is_confirm_
# command()/CONFIRM_WORDS completely unmodified - see tests/
# test_security.py for the regression proof that this phase did not
# touch that list).
# =======================================================================

CONFIRM_CASES = ("yes", "yeah", "confirm", "confirmed", "haan", "han", "جی ہاں", "جی")
DECLINE_CASES = ("no", "nahi", "نہیں", "", None, "thank you", "sure whatever")


def test_wake_word_recovery_confirmation_accepts_every_documented_word():
    for word in CONFIRM_CASES:
        assert jarvis.is_wake_word_recovery_confirmation(word) is True, word


def test_wake_word_recovery_confirmation_rejects_decline_and_unrelated_words():
    for word in DECLINE_CASES:
        assert jarvis.is_wake_word_recovery_confirmation(word) is False, word


def test_wake_word_recovery_confirmation_words_within_a_longer_reply():
    assert jarvis.is_wake_word_recovery_confirmation("yeah sure do it") is True
    assert jarvis.is_wake_word_recovery_confirmation("haan theek hai") is True


def test_wake_word_recovery_confirmation_does_not_false_match_mid_word():
    """"han" must not match inside "khan" (a real name) - word-boundary
    anchored, same discipline as every other marker phrase in this
    project."""

    assert jarvis.is_wake_word_recovery_confirmation("khan") is False


def test_wake_word_recovery_confirmation_never_raises():
    weird_inputs = ("", None, "a" * 5000, "🎉" * 50, "\x00\x01")
    for weird in weird_inputs:
        jarvis.is_wake_word_recovery_confirmation(weird)


def test_wake_word_recovery_confirm_words_distinct_from_commands_confirm_words():
    """Structural proof that the two lists are genuinely separate
    objects, not the same list reused - the whole point of keeping them
    apart (see WAKE_WORD_RECOVERY_CONFIRM_WORDS' own comment)."""

    import commands

    assert "yeah" in jarvis.WAKE_WORD_RECOVERY_CONFIRM_WORDS
    assert "yeah" not in commands.CONFIRM_WORDS
    assert commands.CONFIRM_WORDS == ["yes", "confirm", "confirmed"]
