import intent_layer


# ---------------------------------------------------------------------
# Dangerous commands (lock/shutdown/restart) - intent_parser.py has
# zero representation of these; these paraphrases genuinely reach
# UNKNOWN in the existing pipeline today (verified against
# command_parser.normalize() + the full dispatch chain during the
# Phase 10.2 architecture audit).
# ---------------------------------------------------------------------

def test_shutdown_paraphrase_power_off():
    frames = intent_layer.understand("power off the computer")
    assert len(frames) == 1
    assert frames[0].intent == intent_layer.Intent.SHUTDOWN_COMPUTER
    assert frames[0].confidence >= 0.6


def test_shutdown_paraphrase_turn_off_pc():
    frames = intent_layer.understand("please turn off the pc")
    assert frames[0].intent == intent_layer.Intent.SHUTDOWN_COMPUTER


def test_restart_paraphrase_reboot():
    frames = intent_layer.understand("reboot the machine")
    assert frames[0].intent == intent_layer.Intent.RESTART_COMPUTER


def test_lock_paraphrase_workstation():
    frames = intent_layer.understand("lock the workstation")
    assert frames[0].intent == intent_layer.Intent.LOCK_COMPUTER


def test_existing_exact_dangerous_phrase_still_recognized():
    """The layer also recognizes the exact, already-working phrases -
    redundant in production (dispatch already handles these before
    this layer is ever reached) but confirms the rule itself is
    correct in isolation."""
    frames = intent_layer.understand("shutdown computer")
    assert frames[0].intent == intent_layer.Intent.SHUTDOWN_COMPUTER


def test_dangerous_word_without_dangerous_noun_is_not_flagged():
    """'restart' with no computer/pc/machine/system/workstation noun
    must not be misclassified as dangerous - avoids false positives on
    unrelated uses of the word."""
    frames = intent_layer.understand("restart the music")
    assert not any(
        f.intent
        in (
            intent_layer.Intent.RESTART_COMPUTER,
            intent_layer.Intent.SHUTDOWN_COMPUTER,
            intent_layer.Intent.LOCK_COMPUTER,
        )
        for f in frames
    )


def test_pc_does_not_false_match_inside_unrelated_word():
    """Word-boundary matching: 'pc' must not match inside an unrelated
    word like 'topcoat'."""
    frames = intent_layer.understand("open topcoat")
    assert frames == []


# ---------------------------------------------------------------------
# Volume percentage
# ---------------------------------------------------------------------

def test_volume_percent_without_verb():
    frames = intent_layer.understand("volume to 40 percent")
    assert frames[0].intent == intent_layer.Intent.SET_VOLUME
    assert frames[0].entities == {"percent": 40}


def test_volume_percent_reversed_word_order():
    frames = intent_layer.understand("can i get the volume at 40 percent")
    assert frames[0].intent == intent_layer.Intent.SET_VOLUME
    assert frames[0].entities["percent"] == 40


def test_volume_percent_out_of_range_produces_no_frame():
    frames = intent_layer.understand("volume to 150 percent")
    assert frames == []


def test_volume_percent_symbol_form():
    frames = intent_layer.understand("volume to 25%")
    assert frames[0].entities == {"percent": 25}


# ---------------------------------------------------------------------
# Search queries
# ---------------------------------------------------------------------

def test_search_query_mid_sentence():
    frames = intent_layer.understand("i want to search for python tutorials")
    assert frames[0].intent == intent_layer.Intent.SEARCH
    assert frames[0].entities == {"query": "python tutorials"}


def test_search_with_no_query_produces_no_frame():
    frames = intent_layer.understand("i want to search for")
    assert frames == []


# ---------------------------------------------------------------------
# Keyboard keys
# ---------------------------------------------------------------------

def test_press_key_hit_enter():
    frames = intent_layer.understand("hit enter")
    assert frames[0].intent == intent_layer.Intent.PRESS_KEY
    assert frames[0].entities == {"key": "enter"}


def test_press_key_tab_key_phrase():
    frames = intent_layer.understand("tab key")
    assert frames[0].entities == {"key": "tab"}


def test_press_key_does_not_false_match_inside_word():
    """'tab' must not match inside 'tablet', 'space' must not match
    inside 'workspace' - word-boundary matching."""
    frames = intent_layer.understand("open my tablet workspace")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


# ---- Bug-fix: browser tab-management phrases must not be swallowed by
# the bare "tab" PRESS_KEY rescue (see TAB_MANAGEMENT_MARKERS) ----

def test_press_key_tab_excluded_for_open_new_tab_phrase():
    frames = intent_layer.understand("open new tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_new_tab_phrase():
    frames = intent_layer.understand("new tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_close_tab_phrase():
    frames = intent_layer.understand("close tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_next_tab_phrase():
    frames = intent_layer.understand("next tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_previous_tab_phrase():
    frames = intent_layer.understand("previous tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_roman_urdu_tab_band_karo():
    frames = intent_layer.understand("tab band karo")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_roman_urdu_naya_tab_kholo():
    frames = intent_layer.understand("naya tab kholo")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_rescue_still_works_for_unrelated_tab_phrase():
    """Regression: the tab-management exclusion must not break the
    pre-existing bare "tab key"/"hit tab" rescue for phrases that are
    NOT browser tab management."""
    frames = intent_layer.understand("tab key")
    assert frames[0].intent == intent_layer.Intent.PRESS_KEY
    assert frames[0].entities == {"key": "tab"}


# ---- Phase 11.12: "close (the|this|a|new) tab" article tolerance ----

def test_press_key_tab_excluded_for_close_the_tab_phrase():
    frames = intent_layer.understand("close the tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_close_this_tab_phrase():
    frames = intent_layer.understand("close this tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_close_the_new_tab_phrase():
    frames = intent_layer.understand("close the new tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_new_tab_kholo_phrase():
    frames = intent_layer.understand("new tab kholo")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_closed_tab_phrase():
    frames = intent_layer.understand("closed tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_closed_the_tab_phrase():
    frames = intent_layer.understand("closed the tab")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


def test_press_key_tab_excluded_for_bare_tab_band_phrase():
    frames = intent_layer.understand("tab band")
    assert not any(f.intent == intent_layer.Intent.PRESS_KEY for f in frames)


# ---------------------------------------------------------------------
# Targeted window actions
# ---------------------------------------------------------------------

def test_targeted_window_kill_synonym():
    frames = intent_layer.understand("kill chrome")
    assert frames[0].intent == intent_layer.Intent.TARGETED_WINDOW_ACTION
    assert frames[0].entities == {"application": "chrome", "action": "close"}


def test_targeted_window_hide_synonym():
    frames = intent_layer.understand("hide notepad")
    assert frames[0].entities == {"application": "notepad", "action": "minimize"}


# ---- Phase 11.7: Roman-Urdu/Urdu-script "close" synonyms ----

def test_targeted_window_roman_urdu_band_karo_synonym():
    frames = intent_layer.understand("youtube band karo")
    assert frames[0].intent == intent_layer.Intent.TARGETED_WINDOW_ACTION
    assert frames[0].entities == {"application": "youtube", "action": "close"}


def test_targeted_window_roman_urdu_band_kar_do_synonym():
    frames = intent_layer.understand("github band kar do")
    assert frames[0].entities == {"application": "github", "action": "close"}


def test_targeted_window_mixed_close_karo_synonym():
    frames = intent_layer.understand("youtube close karo")
    assert frames[0].entities == {"application": "youtube", "action": "close"}


def test_targeted_window_urdu_script_band_karo_synonym():
    frames = intent_layer.understand("youtube بند کرو")
    assert frames[0].entities == {"application": "youtube", "action": "close"}


def test_targeted_window_urdu_synonym_without_known_app_produces_no_frame():
    """"band karo" alone (no known application name present) must not
    produce a TARGETED_WINDOW_ACTION frame - this dict is only ever
    consulted when app_name is already not None."""
    frames = intent_layer.understand("band karo")
    assert not any(f.intent == intent_layer.Intent.TARGETED_WINDOW_ACTION for f in frames)


def test_targeted_window_band_karo_does_not_false_match_mid_word():
    """"band karo" is word-boundary-anchored (see TARGETED_ACTION_
    SYNONYMS_UR_RE) - it must not match as a substring of "karobar"
    ("business", a real Roman-Urdu word), unlike the bare `in text`
    check the pre-existing English synonyms above use."""
    frames = intent_layer.understand("youtube band karobar")
    assert not any(f.intent == intent_layer.Intent.TARGETED_WINDOW_ACTION for f in frames)
    # Falls through to the OPEN_APPLICATION last-resort rule instead -
    # the same pre-existing "known limitation" documented in this
    # module's own module docstring, not a new gap this phase created.
    assert frames[0].intent == intent_layer.Intent.OPEN_APPLICATION


def test_to_canonical_command_targeted_window_action_urdu_synonym():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.TARGETED_WINDOW_ACTION,
        entities={"application": "youtube", "action": "close"},
        confidence=1.0,
    )
    assert intent_layer.to_canonical_command(frame) == "close youtube"


# ---------------------------------------------------------------------
# Application entities (open application, last-resort rule)
# ---------------------------------------------------------------------

def test_open_application_entity_extraction():
    frames = intent_layer.understand("i would really like to use chrome now")
    assert frames[0].intent == intent_layer.Intent.OPEN_APPLICATION
    assert frames[0].entities == {"application": "chrome"}


# ---------------------------------------------------------------------
# play/pause
# ---------------------------------------------------------------------

def test_resume_maps_to_play_pause():
    frames = intent_layer.understand("resume the music")
    assert frames[0].intent == intent_layer.Intent.PLAY_PAUSE


# ---------------------------------------------------------------------
# Unknown commands
# ---------------------------------------------------------------------

def test_unrecognizable_text_produces_no_frames():
    frames = intent_layer.understand("the quick brown fox jumps")
    assert frames == []


def test_empty_text_produces_no_frames():
    assert intent_layer.understand("") == []
    assert intent_layer.understand(None) == []


# ---------------------------------------------------------------------
# Multi-intent handling
# ---------------------------------------------------------------------

def test_multi_intent_and_conjunction():
    frames = intent_layer.understand("power off the computer and hit enter")
    assert len(frames) == 2
    assert frames[0].intent == intent_layer.Intent.SHUTDOWN_COMPUTER
    assert frames[1].intent == intent_layer.Intent.PRESS_KEY
    assert frames[1].entities == {"key": "enter"}


def test_multi_intent_rejects_split_if_any_clause_unrecognized():
    """All-or-nothing, mirroring natural_language.split_into_clauses():
    if even one clause can't be understood, the multi-frame split is
    never committed to. The whole (unsplit) text may still resolve to
    a single frame via the fallback pass below - that's expected and
    safe - but it must never come back as an (incorrect) 2-item split
    result."""
    frames = intent_layer.understand("hit enter and do something impossible")
    assert len(frames) <= 1
    if frames:
        assert frames[0].intent == intent_layer.Intent.PRESS_KEY


def test_split_rejected_falls_back_to_whole_string_match():
    """When the split is rejected (one clause - "pc" alone - matches
    no rule), the whole unsplit text is tried as a fallback and
    correctly resolves as a single dangerous-command frame, rather
    than silently producing nothing."""
    frames = intent_layer.understand("power off the computer and pc")
    assert len(frames) == 1
    assert frames[0].intent == intent_layer.Intent.SHUTDOWN_COMPUTER


# ---------------------------------------------------------------------
# to_canonical_command()
# ---------------------------------------------------------------------

def test_to_canonical_command_shutdown():
    frame = intent_layer.IntentFrame(intent_layer.Intent.SHUTDOWN_COMPUTER, confidence=0.8)
    assert intent_layer.to_canonical_command(frame) == "shutdown computer"


def test_to_canonical_command_restart():
    frame = intent_layer.IntentFrame(intent_layer.Intent.RESTART_COMPUTER, confidence=0.8)
    assert intent_layer.to_canonical_command(frame) == "restart computer"


def test_to_canonical_command_lock():
    frame = intent_layer.IntentFrame(intent_layer.Intent.LOCK_COMPUTER, confidence=0.8)
    assert intent_layer.to_canonical_command(frame) == "lock computer"


def test_to_canonical_command_set_volume():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.SET_VOLUME, entities={"percent": 40}, confidence=0.75
    )
    assert intent_layer.to_canonical_command(frame) == "set volume to 40"


def test_to_canonical_command_set_volume_rejects_out_of_range():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.SET_VOLUME, entities={"percent": 150}, confidence=0.75
    )
    assert intent_layer.to_canonical_command(frame) is None


def test_to_canonical_command_search():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.SEARCH, entities={"query": "python tutorials"}, confidence=0.75
    )
    assert intent_layer.to_canonical_command(frame) == "search for python tutorials"


def test_to_canonical_command_search_rejects_empty_query():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.SEARCH, entities={"query": ""}, confidence=0.75
    )
    assert intent_layer.to_canonical_command(frame) is None


def test_to_canonical_command_press_key():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.PRESS_KEY, entities={"key": "enter"}, confidence=0.7
    )
    assert intent_layer.to_canonical_command(frame) == "press enter"


def test_to_canonical_command_press_key_rejects_unknown_key():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.PRESS_KEY, entities={"key": "delete"}, confidence=0.7
    )
    assert intent_layer.to_canonical_command(frame) is None


def test_to_canonical_command_targeted_window_action():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.TARGETED_WINDOW_ACTION,
        entities={"application": "chrome", "action": "close"},
        confidence=0.7,
    )
    assert intent_layer.to_canonical_command(frame) == "close chrome"


def test_to_canonical_command_targeted_window_action_rejects_unknown_application():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.TARGETED_WINDOW_ACTION,
        entities={"application": "not-a-real-app", "action": "close"},
        confidence=0.7,
    )
    assert intent_layer.to_canonical_command(frame) is None


def test_to_canonical_command_open_application():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.OPEN_APPLICATION, entities={"application": "notepad"}, confidence=0.8
    )
    assert intent_layer.to_canonical_command(frame) == "open notepad"


def test_to_canonical_command_play_pause():
    frame = intent_layer.IntentFrame(intent_layer.Intent.PLAY_PAUSE, confidence=0.7)
    assert intent_layer.to_canonical_command(frame) == "play"


# ---------------------------------------------------------------------
# IntentFrame
# ---------------------------------------------------------------------

def test_intent_frame_equality():
    a = intent_layer.IntentFrame(intent_layer.Intent.PLAY_PAUSE, confidence=0.7)
    b = intent_layer.IntentFrame(intent_layer.Intent.PLAY_PAUSE, confidence=0.7, raw_text="resume")
    assert a == b


def test_intent_frame_repr_contains_intent_name():
    frame = intent_layer.IntentFrame(intent_layer.Intent.PLAY_PAUSE, confidence=0.7)
    assert "PLAY_PAUSE" in repr(frame)


# =======================================================================
# BUG-FIX REGRESSION TESTS (Phase 10.2 validation follow-up)
#
# Three defects were found by temporarily enabling the layer and
# running the full suite: (1) dangerous-word matching had no
# adjacency/order requirement between the verb and the noun, causing
# false positives on reversed or unrelated phrasing; (2) the
# volume-percent regex silently dropped a leading "-", turning "-10
# percent" into 10; (3) the same regex could match a fragment after a
# decimal point, turning "40.5 percent" into 5. Fixed in
# RESTART_DANGEROUS_RE/SHUTDOWN_DANGEROUS_RE/LOCK_DANGEROUS_RE and
# VOLUME_NUMBER_RE respectively - see the comments above those
# patterns in intent_layer.py.
# =======================================================================

# ---- A. Reversed/unrelated dangerous phrases must remain UNKNOWN ----

def test_reversed_shutdown_phrase_is_not_dangerous():
    frames = intent_layer.understand("computer shutdown information")
    assert frames == []


def test_shutdown_verb_far_from_noun_is_not_dangerous():
    frames = intent_layer.understand(
        "can you shut down information about the computer"
    )
    assert frames == []


def test_reversed_restart_phrase_is_not_dangerous():
    frames = intent_layer.understand("computer restart information")
    assert frames == []


def test_reversed_lock_phrase_is_not_dangerous():
    frames = intent_layer.understand("computer lock information")
    assert frames == []


# ---- B. Legitimate dangerous paraphrases must still be recognized ----

def test_legitimate_shutdown_paraphrase_please_shut_down_the_computer():
    frames = intent_layer.understand("please shut down the computer")
    assert frames[0].intent == intent_layer.Intent.SHUTDOWN_COMPUTER


def test_legitimate_shutdown_paraphrase_turn_off_the_computer():
    frames = intent_layer.understand("turn off the computer")
    assert frames[0].intent == intent_layer.Intent.SHUTDOWN_COMPUTER


def test_legitimate_restart_paraphrase_please_reboot_the_machine():
    frames = intent_layer.understand("please reboot the machine")
    assert frames[0].intent == intent_layer.Intent.RESTART_COMPUTER


def test_legitimate_restart_paraphrase_restart_the_pc():
    frames = intent_layer.understand("restart the pc")
    assert frames[0].intent == intent_layer.Intent.RESTART_COMPUTER


def test_legitimate_lock_paraphrase_lock_the_workstation():
    frames = intent_layer.understand("lock the workstation")
    assert frames[0].intent == intent_layer.Intent.LOCK_COMPUTER


# ---- C. Negative volume values must be rejected, never flipped positive ----

def test_negative_volume_percent_is_rejected():
    frames = intent_layer.understand("set volume to -10 percent")
    assert frames == []


def test_negative_volume_percent_symbol_form_is_rejected():
    frames = intent_layer.understand("turn volume to -10%")
    assert frames == []


# ---- D. Decimal volume values must be rejected, never truncated ----

def test_decimal_volume_percent_is_rejected():
    frames = intent_layer.understand("set volume to 40.5 percent")
    assert frames == []


def test_decimal_volume_percent_symbol_form_is_rejected():
    frames = intent_layer.understand("set volume to 99.9%")
    assert frames == []


# ---- E. Normal integer volume values still work ----

def test_integer_volume_percent_still_works():
    frames = intent_layer.understand("volume to 40 percent")
    assert frames[0].intent == intent_layer.Intent.SET_VOLUME
    assert frames[0].entities == {"percent": 40}


def test_integer_volume_percent_boundary_values_still_work():
    assert intent_layer.understand("volume to 0 percent")[0].entities == {"percent": 0}
    assert intent_layer.understand("volume to 100 percent")[0].entities == {"percent": 100}


# =======================================================================
# PHASE 10.3: incomplete SEARCH frame ("search youtube" - a site named
# with no query supplied). Deliberately narrow - only "youtube".
# =======================================================================

def test_bare_search_youtube_is_incomplete_search_frame():
    frames = intent_layer.understand("search youtube")

    assert len(frames) == 1
    assert frames[0].intent == intent_layer.Intent.SEARCH
    assert frames[0].incomplete is True
    assert frames[0].entities == {}
    assert frames[0].confidence >= 0.6


def test_to_canonical_command_incomplete_search_returns_none():
    """Never safely renderable - callers (commands.py) must ask a
    follow-up question instead of guessing a query."""
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.SEARCH, entities={}, confidence=0.7, incomplete=True
    )
    assert intent_layer.to_canonical_command(frame) is None


def test_complete_search_for_phrase_is_not_marked_incomplete():
    """"search for spider-man" must continue to work exactly as
    before - a complete SEARCH frame, incomplete=False."""
    frames = intent_layer.understand("search for spider-man")

    assert frames[0].intent == intent_layer.Intent.SEARCH
    assert frames[0].incomplete is False
    assert frames[0].entities == {"query": "spider-man"}


def test_open_youtube_is_unaffected_still_open_application():
    """Only the bare "search youtube" phrasing is special-cased -
    "open youtube"/"launch youtube" must still resolve to
    OPEN_APPLICATION exactly as before this phase."""
    frames = intent_layer.understand("open youtube")

    assert frames[0].intent == intent_layer.Intent.OPEN_APPLICATION
    assert frames[0].incomplete is False
    assert frames[0].entities == {"application": "youtube"}


def test_search_youtube_for_something_is_not_marked_incomplete():
    """A real query after the site name is out of this phase's scope
    and falls through to the existing generic search-query rewrite in
    command_parser.py - intent_layer never even sees "search youtube
    for cats" as incomplete, since SEARCH_INCOMPLETE_RE only matches
    the bare, no-query phrasing exactly."""
    assert intent_layer.SEARCH_INCOMPLETE_RE.match("search youtube for cats") is None


def test_intent_frame_equality_includes_incomplete_flag():
    complete = intent_layer.IntentFrame(
        intent_layer.Intent.SEARCH, entities={}, confidence=0.7, incomplete=False
    )
    incomplete = intent_layer.IntentFrame(
        intent_layer.Intent.SEARCH, entities={}, confidence=0.7, incomplete=True
    )
    assert complete != incomplete
