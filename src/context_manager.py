"""Conversational context layer, built up across three sub-phases -
each independently flag-gated, each deliberately narrow in scope,
matching every prior phase's incremental discipline:

- Phase 10.3 (config.ENABLE_CONTEXT_LAYER): pending-slot-filling.
  Only ONE intent is slot-fillable - SEARCH with a missing query
  (e.g. "search youtube" -> "What should I search for?" -> the next
  reply becomes the query). See PendingSlotRequest, create_pending_
  slot(), is_pending_expired(), resolve_pending_slot().
- Phase 10.4 (config.ENABLE_REFERENCE_RESOLUTION): "it"/"that"/"this"
  (optionally with a trailing "again"/"once more" - widened in Phase
  10.5) resolved against the last-named application (e.g. "open
  chrome" ... later ... "close it" -> "close chrome"). See
  REFERENCE_COMMAND_RE, is_reference_expired(), resolve_reference().
- Phase 10.5 (also config.ENABLE_REFERENCE_RESOLUTION - deliberately
  reuses the Phase 10.4 flag rather than adding a new one, see the
  Phase 10.5 architecture audit): the exact phrase "search that
  again" resolved against the last search query, tracked in a
  COMPLETELY SEPARATE state slot from the last-named application (see
  ConversationContext below) so naming an application and searching
  never clobber each other's memory. See REPEAT_SEARCH_RE,
  is_search_expired(), resolve_repeat_search().

This module is PURE: data structures plus functions that take text and
return either a canonical command string (the same fixed vocabulary
command_parser.py/intent_parser.py/intent_layer.py already produce) or
a plain enum-like result describing what commands.py should do next.
Nothing here ever calls voice.speak(), imports a control module
(web_control, system_control, window_control, volume_control,
media_control, keyboard_control, screen_control), or has any way to
run a process, touch Windows COM automation, or shell out - grep this
file: none of those mechanisms appear anywhere below. See
tests/test_security.py's Phase 10.3/10.4/10.5 sections, which assert
this by inspecting this module's import list directly, not just by
convention.

Every canonical command this module can produce is handed back to
CommandProcessor.process() (see commands.py) - recursively, exactly
like natural_language.split_into_clauses()'s clause loop and Phase
10.2's intent_layer fallback loop already do - so the Phase 9
dangerous-command confirmation gate (the unconditional first
behavioral check on every process() call, including recursive ones)
can never be bypassed by anything produced here. This module cannot
even try to bypass it: it has no reference to a CommandProcessor, a
Voice, or any control module, so it structurally cannot execute
anything by itself.

No LLM or external AI service, no new third-party dependency - plain
deterministic string handling and the project's own existing
`command_parser`/`intent_parser`/`intent_layer` modules, reused by
import exactly like intent_layer.py already reuses intent_parser.py.
"""

import re
import time

import command_parser
import config
import intent_layer
import intent_parser
import multilingual_normalizer


class ConversationContext:
    """Minimal, bounded conversational state carried by one
    CommandProcessor for the lifetime of a JARVIS session - NOT a
    general-purpose conversation history/transcript. Holds exactly
    three independent things, each serving a different sub-phase and
    each expired on its own clock:

    - turn_count/timestamp (Phase 10.3): a plain call counter/clock
      tick, advanced once per CommandProcessor.process() call (see
      commands.py) whenever config.ENABLE_CONTEXT_LAYER or config.
      ENABLE_REFERENCE_RESOLUTION is True. Used to bound a pending
      slot request's lifetime - see is_pending_expired() below.
    - last_intent/last_entities/last_recorded_turn/last_recorded_at
      (Phase 10.4): the last-named application, recorded by record()
      whenever commands.py's _finish_dispatch() sees a successfully
      dispatched OPEN_APPLICATION command. Read by resolve_reference()
      below.
    - last_search_query/last_search_recorded_turn/
      last_search_recorded_at (Phase 10.5): the last SEARCH query,
      recorded by record_search() - deliberately kept in entirely
      separate fields from last_entities above, not merged into it, so
      naming an application and then searching (or vice versa) never
      clobbers the other's memory. Read by resolve_repeat_search()
      below.
    """

    __slots__ = (
        "last_intent", "last_entities", "turn_count", "timestamp",
        "last_recorded_turn", "last_recorded_at",
        "last_search_query", "last_search_recorded_turn", "last_search_recorded_at",
    )

    def __init__(self):
        self.last_intent = None
        self.last_entities = {}
        self.turn_count = 0
        self.timestamp = None
        # Phase 10.4: when last_entities was actually recorded (as
        # opposed to turn_count/timestamp above, which tick on every
        # process() call regardless of whether anything was recorded) -
        # see record()/is_reference_expired() below.
        self.last_recorded_turn = None
        self.last_recorded_at = None
        # Phase 10.5: the last SEARCH query, tracked in COMPLETELY
        # separate fields from last_entities/last_recorded_* above -
        # deliberately never merged into that shared state, so naming
        # an application and then searching (or vice versa) never
        # clobbers the other's memory. See record_search()/
        # is_search_expired() below, and the Phase 10.5 architecture
        # audit's finding on this exact scenario ("open chrome" ->
        # "search for cats" -> "open it" must still resolve to
        # Chrome).
        self.last_search_query = None
        self.last_search_recorded_turn = None
        self.last_search_recorded_at = None

    def advance_turn(self):
        """Called once per CommandProcessor.process() call - see
        commands.py. A plain counter/clock tick, not itself a security
        boundary - see is_pending_expired()'s docstring for why an
        imprecise count is safe here."""

        self.turn_count += 1
        self.timestamp = time.monotonic()

    def record(self, intent, entities):
        """Phase 10.4: record the entities of a command that was just
        successfully dispatched - see commands.py's _finish_dispatch().
        Only ever called with an already-validated, already-safe
        entity shape (currently only ever {"application": <a
        intent_parser.KNOWN_APPLICATIONS key>} - see context_manager.
        resolve_reference() below, the only reader of this state)."""

        self.last_intent = intent
        self.last_entities = dict(entities or {})
        self.last_recorded_turn = self.turn_count
        self.last_recorded_at = time.monotonic()

    def record_search(self, query):
        """Phase 10.5: record the most recent SEARCH query - see
        commands.py's _finish_dispatch(). Intentionally a completely
        separate method/state from record()/last_entities above, not
        an additional entry merged into that dict - see this class's
        __init__ docstring note on last_search_query for why."""

        self.last_search_query = query
        self.last_search_recorded_turn = self.turn_count
        self.last_search_recorded_at = time.monotonic()


class PendingSlotRequest:
    """A single outstanding follow-up question JARVIS has already
    spoken, awaiting the user's next utterance to fill in one missing
    entity. Phase 10.3: `intent` is always intent_layer.Intent.SEARCH
    and `missing_slot` is always "query" - the schema is intentionally
    general so a future phase can add more slot-fillable intents
    without changing this shape."""

    __slots__ = ("intent", "missing_slot", "prompt", "created_turn", "created_at")

    def __init__(self, intent, missing_slot, prompt, created_turn):
        self.intent = intent
        self.missing_slot = missing_slot
        self.prompt = prompt
        self.created_turn = created_turn
        self.created_at = time.monotonic()

    def __repr__(self):
        return (
            f"PendingSlotRequest({self.intent!r}, "
            f"missing_slot={self.missing_slot!r})"
        )


class ResolutionKind:
    # The reply filled the slot - `canonical_command` is safe to feed
    # back into CommandProcessor.process().
    RESOLVED = "RESOLVED"
    # The reply doesn't look like an answer to the pending question at
    # all - it independently looks like its own recognizable command
    # (including a dangerous one). The pending slot must be dropped and
    # the ORIGINAL, unmodified text re-processed as a fresh command, so
    # every existing gate (Phase 9 included) sees it normally.
    NEW_COMMAND = "NEW_COMMAND"
    # Neither of the above (empty reply, gibberish, or an expired
    # slot) - fail closed, say nothing was captured, do not guess.
    UNRESOLVED = "UNRESOLVED"


class SlotResolution:
    __slots__ = ("kind", "canonical_command")

    def __init__(self, kind, canonical_command=None):
        self.kind = kind
        self.canonical_command = canonical_command

    def __repr__(self):
        return f"SlotResolution({self.kind!r}, {self.canonical_command!r})"


# Phase 10.3: only SEARCH is slot-fillable. Extending this to another
# intent is an explicit, separate future decision (see README's Phase
# 10.3 "Limitations" section) - not something this dict is designed to
# be casually grown for other intents without also reviewing
# resolve_pending_slot() below, which currently hardcodes the SEARCH
# rendering rule.
SLOT_PROMPTS = {
    "query": "What should I search for?",
}


def create_pending_slot(frame, context):
    """Build a PendingSlotRequest from an incomplete IntentFrame (see
    intent_layer.IntentFrame.incomplete), or return None if `frame`
    isn't a slot-fillable incomplete frame at all - callers must treat
    None as "nothing to ask", never guess a prompt.

    Phase 10.3: only ever returns non-None for an incomplete SEARCH
    frame.
    """

    if frame is None or not frame.incomplete:
        return None

    if frame.intent != intent_layer.Intent.SEARCH:
        return None

    prompt = SLOT_PROMPTS.get("query")

    if prompt is None:
        return None

    return PendingSlotRequest(
        intent=frame.intent,
        missing_slot="query",
        prompt=prompt,
        created_turn=context.turn_count,
    )


def is_pending_expired(pending, context):
    """True if `pending` is too old to still be treated as awaiting an
    answer - either too many CommandProcessor.process() calls have
    happened since it was created (config.CONTEXT_SLOT_MAX_TURNS) or
    too much wall-clock time has passed (config.CONTEXT_SLOT_TTL_
    SECONDS). Deliberately a soft/approximate bound, not a security
    boundary: even a wrongly-still-valid pending slot can only ever be
    rendered into a "search for <text>" canonical command (see
    resolve_pending_slot() below) - it can never itself produce or
    unlock a dangerous command, so imprecision here has no safety
    impact, only a UX one (answering a stale question that should have
    been treated as a fresh command instead).
    """

    if pending is None:
        return True

    if context.turn_count - pending.created_turn > config.CONTEXT_SLOT_MAX_TURNS:
        return True

    if time.monotonic() - pending.created_at > config.CONTEXT_SLOT_TTL_SECONDS:
        return True

    return False


def _looks_like_new_command(text):
    """True if `text` independently resolves to an already-recognized
    command via the EXISTING deterministic pipeline (intent_parser's
    closed allow-list classifier, then intent_layer's broader rule
    set - including its dangerous-command paraphrase rules - then,
    Phase 11.2, multilingual_normalizer's dedicated dangerous-command
    recognizer) - meaning it should be treated as a fresh command, not
    blindly poured into the pending slot as free-text data.

    This is the mechanism that keeps a dangerous command safe even
    while a slot is pending: "lock my computer" said in reply to "What
    should I search for?" must never become the search query "lock my
    computer" - it must be recognized here and handed back to
    CommandProcessor.process() unmodified, so the Phase 9 gate (or, for
    an exact-phrase match, the raw dangerous-phrase gate even earlier
    in process()) sees the real command. This function only READS the
    existing rule-based classifiers - it never executes anything.

    Phase 11.2: the same protection now also covers an Urdu-script/
    Roman-Urdu/mixed-language dangerous-command paraphrase - e.g.
    "computer lock karo" said in reply to "What should I search for?"
    must never become that literal search query either. multilingual_
    normalizer.understand_dangerous() is called unconditionally here,
    independent of config.ENABLE_MULTILINGUAL_LAYER, for the exact same
    reason intent_layer.understand() above is already called
    independent of config.ENABLE_INTENT_FALLBACK_LAYER: this is a
    read-only safety diversion check, not a live dispatch path, so it
    stays maximally sensitive regardless of whether that layer's own
    dispatch is enabled elsewhere in commands.py. understand_dangerous()
    is pure and only ever returns one of the three fixed canonical
    dangerous-command strings (or None) - never executes anything -
    exactly like every other classifier call in this function; this
    module remains completely execution-free.
    """

    if not text:
        return False

    normalized = command_parser.normalize(text)

    if not normalized:
        return False

    if intent_parser.classify(normalized).intent != intent_parser.Intent.UNKNOWN:
        return True

    for candidate_frame in intent_layer.understand(normalized):

        if (
            candidate_frame.confidence >= config.INTENT_CONFIDENCE_THRESHOLD
            and not candidate_frame.incomplete
        ):
            return True

    if multilingual_normalizer.understand_dangerous(normalized) is not None:
        return True

    return False


def resolve_pending_slot(pending, reply_text, context):
    """Decide what a new utterance means while `pending` is awaiting an
    answer. Returns a SlotResolution - never raises, never executes
    anything, never imports or calls a control module.

    Phase 10.3: the only slot ever filled is SEARCH's "query" - the
    reply text itself (lightly normalized: stripped + lowercased, the
    same casing normalize() already applies to everything else in this
    project) becomes the query, rendered into the canonical
    "search for <query>" string web_control.handle() already
    understands.
    """

    if pending is None:
        return SlotResolution(ResolutionKind.UNRESOLVED)

    if is_pending_expired(pending, context):
        return SlotResolution(ResolutionKind.NEW_COMMAND)

    stripped = (reply_text or "").strip()

    if not stripped:
        return SlotResolution(ResolutionKind.UNRESOLVED)

    if _looks_like_new_command(stripped):
        return SlotResolution(ResolutionKind.NEW_COMMAND)

    if pending.intent == intent_layer.Intent.SEARCH and pending.missing_slot == "query":

        query = stripped.lower()

        if query:
            return SlotResolution(
                ResolutionKind.RESOLVED, f"search for {query}"
            )

    return SlotResolution(ResolutionKind.UNRESOLVED)


# =======================================================================
# PHASE 10.4: contextual reference resolution - "it"/"that"/"this" ->
# the last-named application. Deliberately narrow, matching Phase
# 10.3's own incremental discipline: no other reference (a previous
# search result, a previous website, a previous anything-else) is
# resolved by this phase - see the Phase 10.4 architecture audit for
# why those are explicitly out of scope (no capability exists in this
# codebase to read back a search result or navigate browser history;
# building that is a separate, much larger, not-yet-approved decision).
#
# Reuses the exact same fixed vocabulary intent_parser.py/window_
# control.py already understand - a resolved reference can only ever
# render into "open <app>" or "<action> <app>" for an app already in
# intent_parser.KNOWN_APPLICATIONS, never an arbitrary string. Fed back
# into CommandProcessor.process() by the caller (commands.py) exactly
# like every other layer in this project - this module never executes
# anything itself.
# =======================================================================

# Deliberately anchored to the WHOLE command ("^...$") - exactly the
# same "exact-phrase-only" discipline command_parser.VOLUME_PRONOUN_UP/
# DOWN already use for "turn it up"/"make it louder" ("these must never
# match as a fragment inside a longer, unrelated sentence" - see
# command_parser.py). This is what keeps "what time is it" (containing
# "it" as a whole word) safe: it's handled earlier, by handle_
# information(), and this function is never even reached for it - but
# the anchoring is a second, independent safeguard, not the only one.
#
# Known, disclosed limitation (same spirit as intent_layer.py's own
# "known limitation" note for TARGETED_WINDOW_ACTION): "minimize it"/
# "maximize it"/"restore it" are, in practice, ALREADY intercepted
# earlier in commands.py's dispatch chain by window_control.handle()'s
# untargeted, bare "minimize"/"maximize"/"restore" substring checks
# (which act on whatever window currently has focus) - so this
# function's minimize/maximize/restore branches are effectively
# unreachable via the live dispatch chain today. Included anyway for
# completeness, direct unit testing, and defensive value against any
# future dispatch reordering - exactly the same rationale intent_
# layer.py already documents for its own analogous case. "close it"/
# "switch it"/"switch to it"/"open it" are the phrasings that actually
# reach this function in practice, since nothing earlier in the
# dispatch chain matches them.
REFERENCE_PRONOUNS = ("it", "that", "this")
REFERENCE_VERBS = (
    "minimize", "maximize", "restore", "close", "switch to", "switch", "open",
)
# Phase 10.5: an optional trailing "again"/"once more" is now also
# accepted ("open it again", "open that once more") - a pure widening,
# non-capturing and optional, so plain "open it" (no trailing word)
# continues to match exactly as it did in Phase 10.4, and match.group(
# "verb")/match.group("pronoun") are completely unaffected either way.
REFERENCE_COMMAND_RE = re.compile(
    r"^(?P<verb>" + "|".join(REFERENCE_VERBS) + r")\s+"
    r"(?P<pronoun>" + "|".join(REFERENCE_PRONOUNS) + r")"
    r"(?:\s+(?:again|once more))?$"
)


def is_reference_expired(context):
    """True if context.last_entities is too old to still be used for
    reference resolution - either too many CommandProcessor.process()
    calls have happened since it was recorded (config.
    REFERENCE_MAX_TURNS) or too much wall-clock time has passed
    (config.REFERENCE_TTL_SECONDS).

    Unlike is_pending_expired() above, this IS load-bearing for safety,
    not just UX: a resolved reference can render into a real window/
    application action (e.g. "close chrome"), not just a search
    string - see the Phase 10.4 architecture audit's security section.
    A deliberately conservative (short) bound is used for exactly this
    reason.
    """

    if context is None or context.last_recorded_at is None:
        return True

    if context.turn_count - context.last_recorded_turn > config.REFERENCE_MAX_TURNS:
        return True

    if time.monotonic() - context.last_recorded_at > config.REFERENCE_TTL_SECONDS:
        return True

    return False


def resolve_reference(command, context):
    """Resolve a standalone "<verb> it/that/this" command against the
    last-named application in `context`, or return None if it can't be
    safely resolved (no such command shape, nothing recorded yet, the
    record has expired, or the recorded application somehow isn't in
    the fixed allow-list). Never raises, never executes anything.

    Returns one of the exact same canonical command strings the
    existing dispatch chain already understands (e.g. "close chrome",
    "open chrome") - callers must feed this back through
    CommandProcessor.process(), never act on it directly.
    """

    if not command:
        return None

    match = REFERENCE_COMMAND_RE.match(command)

    if match is None:
        return None

    if is_reference_expired(context):
        return None

    app = context.last_entities.get("application")

    if not app or app not in intent_parser.KNOWN_APPLICATIONS:
        return None

    verb = match.group("verb")

    if verb == "open":
        return intent_parser.KNOWN_APPLICATIONS.get(app)

    if verb == "switch to":
        verb = "switch"

    return f"{verb} {app}"


# =======================================================================
# PHASE 10.5: repeat-search - "search that again" -> "search for
# <previous_query>". Deliberately exactly ONE trigger phrase, no other
# repeat-search phrasing - see the Phase 10.5 architecture audit.
#
# Uses last_search_query/last_search_recorded_turn/last_search_
# recorded_at on ConversationContext - a state slot kept completely
# independent of last_entities (the Phase 10.4 "last-named
# application" slot) on purpose: see ConversationContext.__init__'s
# docstring note. This is what guarantees "open chrome" -> "search for
# cats" -> "open it" still resolves to "open chrome" - recording the
# search never touches last_entities, so the application memory is
# untouched by an intervening search (or vice versa).
#
# Same safety shape as resolve_reference() above: only ever renders
# "search for <text>" from a query that was itself already safely
# recorded from a prior, already-dispatched SEARCH command (see
# commands.py's _finish_dispatch()) - never a control module call,
# never an arbitrary command, never executes anything itself. Fed back
# into CommandProcessor.process() by the caller (commands.py), so the
# Phase 9 gate always sees the final canonical command.
# =======================================================================

REPEAT_SEARCH_RE = re.compile(r"^search that again$")


def is_search_expired(context):
    """True if context.last_search_query is too old to still be
    repeatable - either too many CommandProcessor.process() calls have
    happened since it was recorded (config.SEARCH_REPEAT_MAX_TURNS) or
    too much wall-clock time has passed (config.SEARCH_REPEAT_TTL_
    SECONDS). Tracked entirely independently of is_reference_expired()
    above - a stale application reference and a stale search query
    expire on their own separate clocks, even though both currently
    use the same conservative bound values by default.

    Like is_reference_expired(), this is a soft UX bound more than a
    hard safety boundary in practice: a resolved repeat-search can only
    ever render "search for <text>" - the exact same, already-safe
    shape any ordinary search command already produces - never a
    window/application action, so a wrongly-still-valid record is far
    lower-risk than Phase 10.4's own case. It's still bounded, on the
    same "never reuse something from a stale, unrelated point in the
    conversation" principle applied everywhere else in this project.
    """

    if context is None or context.last_search_recorded_at is None:
        return True

    if (
        context.turn_count - context.last_search_recorded_turn
        > config.SEARCH_REPEAT_MAX_TURNS
    ):
        return True

    if (
        time.monotonic() - context.last_search_recorded_at
        > config.SEARCH_REPEAT_TTL_SECONDS
    ):
        return True

    return False


def resolve_repeat_search(command, context):
    """Resolve the exact phrase "search that again" against the last
    recorded search query in `context`, or return None if it can't be
    safely resolved (wrong phrase, nothing recorded yet, or the record
    has expired). Never raises, never executes anything.

    Returns the canonical "search for <query>" string web_control.
    handle() already understands - callers must feed this back through
    CommandProcessor.process(), never act on it directly.
    """

    if not command:
        return None

    if not REPEAT_SEARCH_RE.match(command):
        return None

    if is_search_expired(context):
        return None

    query = context.last_search_query

    if not query:
        return None

    return f"search for {query}"
