"""Unit tests for context_manager.py (Phase 10.3) in isolation - no
CommandProcessor, no voice, no control module involved. Verifies the
module is pure: it only ever returns data (a PendingSlotRequest or a
SlotResolution), never executes anything itself.
"""

import ast
import importlib
import inspect

import config
import context_manager
import intent_layer
import intent_parser


def make_context(turn_count=1):
    context = context_manager.ConversationContext()
    context.turn_count = turn_count
    return context


def make_search_pending(created_turn=1):
    return context_manager.PendingSlotRequest(
        intent=intent_layer.Intent.SEARCH,
        missing_slot="query",
        prompt="What should I search for?",
        created_turn=created_turn,
    )


# =======================================================================
# 1. Search slot creation
# =======================================================================

def test_create_pending_slot_from_incomplete_search_frame():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.SEARCH,
        entities={},
        confidence=0.7,
        incomplete=True,
    )

    pending = context_manager.create_pending_slot(frame, make_context())

    assert pending is not None
    assert pending.intent == intent_layer.Intent.SEARCH
    assert pending.missing_slot == "query"
    assert pending.prompt == "What should I search for?"


def test_create_pending_slot_returns_none_for_complete_frame():
    frame = intent_layer.IntentFrame(
        intent_layer.Intent.SEARCH,
        entities={"query": "python"},
        confidence=0.75,
        incomplete=False,
    )

    assert context_manager.create_pending_slot(frame, make_context()) is None


def test_create_pending_slot_returns_none_for_non_search_incomplete_frame():
    """Phase 10.3 scope: only SEARCH is slot-fillable, even if some
    other frame were ever marked incomplete in the future."""

    frame = intent_layer.IntentFrame(
        intent_layer.Intent.PLAY_PAUSE,
        confidence=0.9,
        incomplete=True,
    )

    assert context_manager.create_pending_slot(frame, make_context()) is None


def test_create_pending_slot_returns_none_for_none_frame():
    assert context_manager.create_pending_slot(None, make_context()) is None


# =======================================================================
# 2. Valid slot resolution
# =======================================================================

def test_resolve_pending_slot_valid_reply():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(pending, "Spider-Man", context)

    assert resolution.kind == context_manager.ResolutionKind.RESOLVED
    assert resolution.canonical_command == "search for spider-man"


def test_resolve_pending_slot_lowercases_and_strips_reply():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "  Bed AND Breakfast  ", context
    )

    assert resolution.kind == context_manager.ResolutionKind.RESOLVED
    assert resolution.canonical_command == "search for bed and breakfast"


# =======================================================================
# 3. Empty reply
# =======================================================================

def test_resolve_pending_slot_empty_reply_is_unresolved():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(pending, "", context)

    assert resolution.kind == context_manager.ResolutionKind.UNRESOLVED
    assert resolution.canonical_command is None


def test_resolve_pending_slot_whitespace_only_reply_is_unresolved():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(pending, "   ", context)

    assert resolution.kind == context_manager.ResolutionKind.UNRESOLVED


# =======================================================================
# 4. Unrelated / dangerous reply -> treated as a new command, never
#    silently poured into the search query
# =======================================================================

def test_resolve_pending_slot_unrelated_known_command_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(pending, "open chrome", context)

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND
    assert resolution.canonical_command is None


def test_resolve_pending_slot_dangerous_paraphrase_is_new_command_not_a_query():
    """CRITICAL SAFETY TEST: a pending search slot must never convert a
    dangerous phrase into a search query - it must be handed back as a
    fresh command instead, so CommandProcessor.process() re-evaluates
    it (and the Phase 9 gate sees it)."""

    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "lock my computer", context
    )

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND
    assert resolution.canonical_command is None
    assert resolution.canonical_command != "search for lock my computer"


def test_resolve_pending_slot_exact_dangerous_phrase_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "lock computer", context
    )

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND


# =======================================================================
# Phase 11.2: a pending search slot must never convert an Urdu-script/
# Roman-Urdu/mixed-language dangerous-command paraphrase into a search
# query either - see context_manager._looks_like_new_command(), which
# now also consults multilingual_normalizer.understand_dangerous().
# Same shape as test_resolve_pending_slot_dangerous_paraphrase_is_new_
# command_not_a_query() above, for each of lock/shutdown/restart, in
# Urdu script, Roman Urdu, and mixed-language form.
# =======================================================================

def test_resolve_pending_slot_roman_urdu_lock_paraphrase_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "computer lock karo", context
    )

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND
    assert resolution.canonical_command is None
    assert resolution.canonical_command != "search for computer lock karo"


def test_resolve_pending_slot_urdu_script_shutdown_paraphrase_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "کمپیوٹر بند کرو", context
    )

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND
    assert resolution.canonical_command is None


def test_resolve_pending_slot_urdu_script_restart_paraphrase_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "کمپیوٹر ری اسٹارٹ کرو", context
    )

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND
    assert resolution.canonical_command is None


def test_resolve_pending_slot_mixed_language_lock_paraphrase_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "computer کو lock کرو", context
    )

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND
    assert resolution.canonical_command is None


def test_resolve_pending_slot_mixed_language_shutdown_paraphrase_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "کمپیوٹر shutdown کرو", context
    )

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND
    assert resolution.canonical_command is None


def test_resolve_pending_slot_mixed_language_restart_paraphrase_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "کمپیوٹر ko restart karo", context
    )

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND
    assert resolution.canonical_command is None


def test_resolve_pending_slot_non_dangerous_urdu_still_fills_the_slot():
    """Sanity check for the opposite direction: an Urdu-script reply
    that does NOT match the dangerous-command pattern (no "computer"/
    "کمپیوٹر" noun, e.g. someone actually wants to search in Urdu) is
    still treated as ordinary free-text search input - Phase 11.2 must
    not make replies MORE likely to be diverted than before, only
    dangerous ones."""

    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "اسپائیڈر مین", context
    )

    assert resolution.kind == context_manager.ResolutionKind.RESOLVED
    assert resolution.canonical_command == "search for اسپائیڈر مین"


def test_looks_like_new_command_does_not_call_understand_full_vocabulary():
    """Structural check: the Phase 11.2 fix calls multilingual_
    normalizer.understand_dangerous() specifically - NOT the module's
    much broader understand() - so a pending slot reply is only ever
    diverted for a genuine dangerous-command paraphrase, never for an
    ordinary Urdu-script command like "چھوٹا کرو" ("minimize"), which
    would be a much bigger, separately-scoped behavior change outside
    Phase 11.2's remit. (Deliberately not an app-name phrase here:
    intent_parser.classify() bare-substring-matches ANY known
    application name anywhere in the text - including "youtube"/
    "google"/"github", not just "chrome" - completely independently of
    this Phase 11.2 change, so an app-name phrase would already be
    diverted for an unrelated, pre-existing reason and wouldn't isolate
    what THIS fix does or doesn't add.)"""

    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "چھوٹا کرو", context
    )

    assert resolution.kind == context_manager.ResolutionKind.RESOLVED
    assert resolution.canonical_command == "search for چھوٹا کرو"


def test_resolve_pending_slot_gibberish_reply_still_fills_the_slot():
    """A reply that is neither a recognized command nor empty is still
    accepted as free-text search input - only genuinely recognized
    commands are diverted; this is not itself an ambiguity case the
    way an unrecognized top-level command is, since ANY free text is a
    valid search query by definition."""

    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    resolution = context_manager.resolve_pending_slot(
        pending, "the quick brown fox", context
    )

    assert resolution.kind == context_manager.ResolutionKind.RESOLVED
    assert resolution.canonical_command == "search for the quick brown fox"


# =======================================================================
# 5. Expired slot (TTL)
# =======================================================================

def test_resolve_pending_slot_ttl_expired_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=1)  # turn count says "fresh"

    # Force wall-clock expiry directly, without sleeping in the test.
    pending.created_at -= (config.CONTEXT_SLOT_TTL_SECONDS + 1)

    resolution = context_manager.resolve_pending_slot(pending, "Spider-Man", context)

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND


def test_is_pending_expired_true_past_ttl():
    pending = make_search_pending(created_turn=1)
    pending.created_at -= (config.CONTEXT_SLOT_TTL_SECONDS + 1)
    context = make_context(turn_count=1)

    assert context_manager.is_pending_expired(pending, context) is True


def test_is_pending_expired_false_within_ttl_and_turn_limit():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=2)

    assert context_manager.is_pending_expired(pending, context) is False


def test_is_pending_expired_true_for_none():
    assert context_manager.is_pending_expired(None, make_context()) is True


# =======================================================================
# 6. Turn-limit behavior
# =======================================================================

def test_resolve_pending_slot_turn_limit_exceeded_is_new_command():
    pending = make_search_pending(created_turn=1)
    context = make_context(
        turn_count=1 + config.CONTEXT_SLOT_MAX_TURNS + 1
    )

    resolution = context_manager.resolve_pending_slot(pending, "Spider-Man", context)

    assert resolution.kind == context_manager.ResolutionKind.NEW_COMMAND


def test_resolve_pending_slot_within_turn_limit_resolves_normally():
    pending = make_search_pending(created_turn=1)
    context = make_context(turn_count=1 + config.CONTEXT_SLOT_MAX_TURNS)

    resolution = context_manager.resolve_pending_slot(pending, "Spider-Man", context)

    assert resolution.kind == context_manager.ResolutionKind.RESOLVED


# =======================================================================
# 7 & 8. No control-module / voice imports (structural safety)
# =======================================================================

FORBIDDEN_MODULES = {
    "web_control",
    "system_control",
    "window_control",
    "volume_control",
    "media_control",
    "keyboard_control",
    "screen_control",
    "voice",
    "subprocess",
    "ctypes",
    "comtypes",
}


def _imported_module_names(module):
    """Return the set of top-level module names `module`'s source
    imports, via `import X` or `from X import ...` - static AST
    inspection, not reliant on what happens to already be loaded."""

    source = inspect.getsource(module)
    tree = ast.parse(source)

    names = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])

    return names


def test_context_manager_imports_no_control_module_or_voice():
    imported = _imported_module_names(context_manager)

    forbidden_hit = imported & FORBIDDEN_MODULES

    assert forbidden_hit == set(), (
        f"context_manager.py must never import {forbidden_hit} - "
        "it must only ever produce data, never execute a control "
        "module or touch voice/subprocess/ctypes/comtypes directly."
    )


def test_context_manager_has_no_os_system_or_exec_primitives():
    source = inspect.getsource(context_manager)

    for forbidden_call in ("os.system(", "subprocess.", "eval(", "exec("):
        assert forbidden_call not in source


def test_context_manager_imports_multilingual_normalizer_for_phase_11_2():
    """Phase 11.2 deliberately ADDS one new import - multilingual_
    normalizer - to close the dangerous-command diversion gap (see
    _looks_like_new_command()'s docstring). This is expected and safe:
    multilingual_normalizer.py is itself execution-free (verified by
    its own tests) and is not in FORBIDDEN_MODULES - importing it does
    not give context_manager.py any new way to execute anything."""

    imported = _imported_module_names(context_manager)

    assert "multilingual_normalizer" in imported
    assert imported & FORBIDDEN_MODULES == set()


# =======================================================================
# 9. Resolver never executes anything - it only returns data
# =======================================================================

def test_resolve_pending_slot_return_type_is_always_slot_resolution():
    context = make_context(turn_count=2)
    pending = make_search_pending(created_turn=1)

    for reply in ("Spider-Man", "", "open chrome", "lock my computer", "   "):
        resolution = context_manager.resolve_pending_slot(pending, reply, context)
        assert isinstance(resolution, context_manager.SlotResolution)
        assert resolution.kind in (
            context_manager.ResolutionKind.RESOLVED,
            context_manager.ResolutionKind.NEW_COMMAND,
            context_manager.ResolutionKind.UNRESOLVED,
        )


def test_resolve_pending_slot_with_none_pending_is_unresolved():
    resolution = context_manager.resolve_pending_slot(None, "Spider-Man", make_context())
    assert resolution.kind == context_manager.ResolutionKind.UNRESOLVED


def test_conversation_context_advance_turn_increments_and_stamps_time():
    context = context_manager.ConversationContext()
    assert context.turn_count == 0
    assert context.timestamp is None

    context.advance_turn()

    assert context.turn_count == 1
    assert context.timestamp is not None


def test_conversation_context_record_stores_a_copy_of_entities():
    context = context_manager.ConversationContext()
    entities = {"query": "python"}

    context.record(intent_layer.Intent.SEARCH, entities)
    entities["query"] = "mutated"

    assert context.last_intent == intent_layer.Intent.SEARCH
    assert context.last_entities == {"query": "python"}


# =======================================================================
# PHASE 10.4: contextual reference resolution - "it"/"that"/"this" ->
# last-named application.
# =======================================================================

def make_context_with_app(app="chrome", turn_count=2):
    context = context_manager.ConversationContext()
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": app})
    context.turn_count = turn_count
    return context


def test_conversation_context_record_stamps_recorded_turn_and_time():
    context = context_manager.ConversationContext()
    context.turn_count = 5

    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})

    assert context.last_recorded_turn == 5
    assert context.last_recorded_at is not None


def test_resolve_reference_close_it():
    context = make_context_with_app("chrome")
    assert context_manager.resolve_reference("close it", context) == "close chrome"


def test_resolve_reference_open_it_renders_open_command():
    context = make_context_with_app("notepad")
    assert context_manager.resolve_reference("open it", context) == "open notepad"


def test_resolve_reference_switch_to_this():
    context = make_context_with_app("chrome")
    assert context_manager.resolve_reference("switch to this", context) == "switch chrome"


def test_resolve_reference_switch_that():
    context = make_context_with_app("chrome")
    assert context_manager.resolve_reference("switch that", context) == "switch chrome"


def test_resolve_reference_minimize_maximize_restore_still_render_correctly():
    """Included for completeness/direct unit testing even though, in
    the live dispatch chain, these three are shadowed by the existing
    untargeted window_control.handle() checks - see context_manager.py
    's module docstring."""
    context = make_context_with_app("notepad")
    assert context_manager.resolve_reference("minimize it", context) == "minimize notepad"
    assert context_manager.resolve_reference("maximize it", context) == "maximize notepad"
    assert context_manager.resolve_reference("restore it", context) == "restore notepad"


def test_resolve_reference_returns_none_with_no_context_recorded():
    context = context_manager.ConversationContext()
    assert context_manager.resolve_reference("close it", context) is None


def test_resolve_reference_returns_none_for_non_matching_command():
    context = make_context_with_app("chrome")
    assert context_manager.resolve_reference("what time is it", context) is None
    assert context_manager.resolve_reference("search for it", context) is None
    assert context_manager.resolve_reference("mute it", context) is None


def test_resolve_reference_returns_none_for_empty_command():
    context = make_context_with_app("chrome")
    assert context_manager.resolve_reference("", context) is None
    assert context_manager.resolve_reference(None, context) is None


def test_resolve_reference_returns_none_when_turn_limit_exceeded():
    context = context_manager.ConversationContext()
    context.turn_count = 1
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})
    context.turn_count = 1 + config.REFERENCE_MAX_TURNS + 1

    assert context_manager.resolve_reference("close it", context) is None


def test_resolve_reference_returns_none_when_ttl_expired():
    context = context_manager.ConversationContext()
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})
    context.last_recorded_at -= (config.REFERENCE_TTL_SECONDS + 1)

    assert context_manager.resolve_reference("close it", context) is None


def test_resolve_reference_within_turn_limit_and_ttl_still_resolves():
    context = context_manager.ConversationContext()
    context.turn_count = 1
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})
    context.turn_count = 1 + config.REFERENCE_MAX_TURNS

    assert context_manager.resolve_reference("close it", context) == "close chrome"


def test_resolve_reference_ignores_application_outside_allow_list():
    """Defense in depth: even if last_entities somehow held a value
    outside intent_parser.KNOWN_APPLICATIONS, it must never be
    rendered into a command."""
    context = context_manager.ConversationContext()
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "not-a-real-app"})

    assert context_manager.resolve_reference("close it", context) is None


def test_is_reference_expired_true_for_never_recorded():
    assert context_manager.is_reference_expired(context_manager.ConversationContext()) is True


def test_is_reference_expired_true_for_none_context():
    assert context_manager.is_reference_expired(None) is True


def test_is_reference_expired_false_when_fresh():
    context = context_manager.ConversationContext()
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})
    assert context_manager.is_reference_expired(context) is False


def test_resolve_reference_never_calls_anything_only_returns_strings_or_none():
    context = make_context_with_app("chrome")

    for command in ("close it", "open that", "switch to this", "hello", "", None):
        result = context_manager.resolve_reference(command, context)
        assert result is None or isinstance(result, str)


# =======================================================================
# PHASE 10.5: "again"/"once more" phrasing widening + independent
# repeat-search state.
# =======================================================================

def test_resolve_reference_open_it_again():
    context = make_context_with_app("chrome")
    assert context_manager.resolve_reference("open it again", context) == "open chrome"


def test_resolve_reference_open_that_once_more():
    context = make_context_with_app("chrome")
    assert (
        context_manager.resolve_reference("open that once more", context)
        == "open chrome"
    )


def test_resolve_reference_close_it_again():
    context = make_context_with_app("notepad")
    assert context_manager.resolve_reference("close it again", context) == "close notepad"


def test_resolve_reference_bare_open_it_still_works_unchanged():
    """Existing Phase 10.4 behavior (no trailing word) must be
    completely unaffected by the Phase 10.5 regex widening."""
    context = make_context_with_app("chrome")
    assert context_manager.resolve_reference("open it", context) == "open chrome"


def test_resolve_reference_rejects_other_trailing_words():
    """Only "again"/"once more" are accepted trailing phrases - not an
    open-ended "any trailing word" widening."""
    context = make_context_with_app("chrome")
    assert context_manager.resolve_reference("open it please", context) is None
    assert context_manager.resolve_reference("open it now", context) is None


def make_context_with_search(query="cats", turn_count=2):
    context = context_manager.ConversationContext()
    context.turn_count = 1
    context.record_search(query)
    context.turn_count = turn_count
    return context


def test_record_search_is_independent_of_application_entities():
    context = context_manager.ConversationContext()
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})
    context.record_search("cats")

    assert context.last_entities == {"application": "chrome"}
    assert context.last_search_query == "cats"


def test_record_application_after_search_does_not_erase_search():
    context = context_manager.ConversationContext()
    context.record_search("cats")
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})

    assert context.last_search_query == "cats"
    assert context.last_entities == {"application": "chrome"}


def test_resolve_repeat_search_valid():
    context = make_context_with_search("cats")
    assert (
        context_manager.resolve_repeat_search("search that again", context)
        == "search for cats"
    )


def test_resolve_repeat_search_wrong_phrase_returns_none():
    context = make_context_with_search("cats")
    assert context_manager.resolve_repeat_search("search again", context) is None
    assert context_manager.resolve_repeat_search("search cats again", context) is None
    assert context_manager.resolve_repeat_search("repeat that search", context) is None


def test_resolve_repeat_search_no_context_returns_none():
    context = context_manager.ConversationContext()
    assert context_manager.resolve_repeat_search("search that again", context) is None


def test_resolve_repeat_search_empty_or_none_command_returns_none():
    context = make_context_with_search("cats")
    assert context_manager.resolve_repeat_search("", context) is None
    assert context_manager.resolve_repeat_search(None, context) is None


def test_resolve_repeat_search_turn_limit_exceeded_returns_none():
    context = context_manager.ConversationContext()
    context.turn_count = 1
    context.record_search("cats")
    context.turn_count = 1 + config.SEARCH_REPEAT_MAX_TURNS + 1

    assert context_manager.resolve_repeat_search("search that again", context) is None


def test_resolve_repeat_search_within_turn_limit_resolves():
    context = context_manager.ConversationContext()
    context.turn_count = 1
    context.record_search("cats")
    context.turn_count = 1 + config.SEARCH_REPEAT_MAX_TURNS

    assert (
        context_manager.resolve_repeat_search("search that again", context)
        == "search for cats"
    )


def test_resolve_repeat_search_ttl_expired_returns_none():
    context = context_manager.ConversationContext()
    context.record_search("cats")
    context.last_search_recorded_at -= (config.SEARCH_REPEAT_TTL_SECONDS + 1)

    assert context_manager.resolve_repeat_search("search that again", context) is None


def test_is_search_expired_true_for_never_recorded():
    assert context_manager.is_search_expired(context_manager.ConversationContext()) is True


def test_is_search_expired_true_for_none_context():
    assert context_manager.is_search_expired(None) is True


def test_is_search_expired_false_when_fresh():
    context = context_manager.ConversationContext()
    context.record_search("cats")
    assert context_manager.is_search_expired(context) is False


def test_search_expiry_independent_of_reference_expiry():
    """A fresh application record and a stale search record (or vice
    versa) must expire completely independently of each other."""
    context = context_manager.ConversationContext()
    context.turn_count = 1
    context.record_search("cats")
    context.turn_count = 1 + config.SEARCH_REPEAT_MAX_TURNS + 1
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})

    # search record is now stale (too many turns since it was recorded)...
    assert context_manager.is_search_expired(context) is True
    # ...but the application record, just recorded, is fresh.
    assert context_manager.is_reference_expired(context) is False


def test_resolve_repeat_search_never_calls_anything_only_returns_strings_or_none():
    context = make_context_with_search("cats")

    for command in ("search that again", "search again", "", None, "hello"):
        result = context_manager.resolve_repeat_search(command, context)
        assert result is None or isinstance(result, str)
