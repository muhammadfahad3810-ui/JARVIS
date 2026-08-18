import datetime
import re

import ai_router
import command_parser
import config
import context_manager
import intent_layer
import intent_parser
import keyboard_control
import media_control
import mouse_control
import multilingual_normalizer
import natural_language
import screen_control
import system_control
import volume_control
import web_control
import window_control


GREETINGS = [
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
]

EXIT_WORDS = [
    "exit",
    "quit",
    "goodbye",
    "go offline",
]


def _word_boundary_patterns(words):
    """Compile each phrase as a whole-word/whole-phrase regex, so short
    words like 'hi' don't false-match inside unrelated words like
    'this' (a bare `"hi" in command` substring check would)."""

    return [
        re.compile(r"\b" + re.escape(word) + r"\b")
        for word in words
    ]


GREETING_PATTERNS = _word_boundary_patterns(GREETINGS)
EXIT_PATTERNS = _word_boundary_patterns(EXIT_WORDS)

# Phase 9: confirmation layer for dangerous system commands. These are
# the exact same three fixed phrases system_control.handle_system()
# matches - defined once here (not imported from system_control.py) so
# system_control.py needs zero changes and stays fully protected.
DANGEROUS_COMMANDS = ("lock computer", "shutdown computer", "restart computer")

DANGEROUS_COMMAND_PROMPTS = {
    "lock computer": "Are you sure you want to lock the computer? Say yes to confirm.",
    "shutdown computer": "Are you sure you want to shut down the computer? Say yes to confirm.",
    "restart computer": "Are you sure you want to restart the computer? Say yes to confirm.",
}

CONFIRM_WORDS = ["yes", "confirm", "confirmed"]
CONFIRM_PATTERNS = _word_boundary_patterns(CONFIRM_WORDS)


def is_confirm_command(command):
    return any(pattern.search(command) for pattern in CONFIRM_PATTERNS)


def _light_normalize(text):
    """Lowercase + whitespace-collapse ONLY - deliberately NOT the full
    command_parser.normalize() pipeline. normalize() can rewrite (and
    thereby destroy) a dangerous phrase before this gate ever sees it:
    e.g. "restart computer and mute" -> normalize() -> "mute" (via
    canonicalize_volume_phrase(), which rewrites the ENTIRE string to
    just "mute" whenever the word "mute" appears anywhere in it - a
    pre-existing Phase 5 behavior, unrelated to and not modified by
    Phase 9). Checking dangerous phrases on this lightly-normalized
    text instead - before normalize() ever runs - means the phrase is
    always seen intact, regardless of what normalize() would later do
    to the rest of the string."""

    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _matched_dangerous_command(command):
    """Return the first DANGEROUS_COMMANDS phrase found as a substring
    of `command`, or None - mirrors system_control.handle_system()'s
    own bare-substring matching exactly, so a phrase like "lock
    computer and open chrome" (which handle_system() would still act
    on, discarding the suffix - see test_security.py's Phase 6
    "dangerous suffix" tests) is caught by the confirmation gate too,
    not just an exact "lock computer" match."""

    for phrase in DANGEROUS_COMMANDS:
        if phrase in command:
            return phrase

    return None


def handle_information(command, voice):

    if "time" in command:

        current_time = datetime.datetime.now().strftime(
            "%I:%M %p"
        )

        voice.speak(
            f"The current time is {current_time}."
        )

        return True

    if "date" in command:

        current_date = datetime.datetime.now().strftime(
            "%A, %B %d, %Y"
        )

        voice.speak(
            f"Today is {current_date}."
        )

        return True

    return False


def handle_greeting(command, voice):

    if any(pattern.search(command) for pattern in GREETING_PATTERNS):

        voice.speak(
            "Hello. I am JARVIS. "
            "How can I help you?"
        )

        return True

    return False


def is_exit_command(command):
    return any(pattern.search(command) for pattern in EXIT_PATTERNS)


class CommandProcessor:
    """Routes a recognized command string to the right handler."""

    def __init__(self, voice):
        self.voice = voice
        # Phase 9: set to a pending dangerous-command string between the
        # confirmation prompt and the reply that resolves it. None the
        # rest of the time (the overwhelming majority of this object's
        # lifetime) - see DANGEROUS_COMMANDS/is_confirm_command() above.
        self._pending_confirmation = None
        # Phase 10.3: set to a context_manager.PendingSlotRequest
        # between a follow-up question ("What should I search for?")
        # and the reply that resolves it. None the rest of the time -
        # see context_manager.py. Structurally separate from
        # self._pending_confirmation above so the two pending-state
        # machines can never be confused with each other; only one of
        # the two is ever non-None at a time in practice, since each is
        # resolved (and cleared) before the code path that could set
        # the other one runs.
        self._pending_slot = None
        self._context = context_manager.ConversationContext()

    def _finish_dispatch(self, classified):
        """Called at every primary-dispatch-chain success point in
        process() below, immediately before returning True. Records
        entity state onto self._context when the command that was just
        dispatched names something rememberable - purely a read of
        `classified` (an already-computed, pure intent_parser.
        classify() result), never a second dispatch path and never a
        change to the return value itself. `classified` is None
        whenever neither DEBUG nor ENABLE_REFERENCE_RESOLUTION needed
        it (see process()), in which case this is a no-op. With config.
        ENABLE_REFERENCE_RESOLUTION False (the default), this never
        records anything, so behavior is byte-for-byte unchanged from
        before Phase 10.4/10.5.

        Phase 10.4: OPEN_APPLICATION -> self._context.record() (the
        "last-named application" slot).

        Phase 10.5: SEARCH -> self._context.record_search() (the
        "last search query" slot) - a COMPLETELY SEPARATE state slot
        from the one above, deliberately never merged into it (see
        context_manager.ConversationContext's docstring), so naming an
        application and then searching (or vice versa) never clobbers
        the other's memory. This also naturally captures a Phase 10.3
        slot-filled search ("search youtube" -> "Spider-Man" -> "search
        for spider-man"): that resolution recurses through self.
        process(), reaching this same dispatch chain and this same
        recording point like any other command.
        """

        if config.ENABLE_REFERENCE_RESOLUTION and classified is not None:

            if (
                classified.intent == intent_parser.Intent.OPEN_APPLICATION
                and classified.target in intent_parser.KNOWN_APPLICATIONS
            ):
                self._context.record(
                    classified.intent, {"application": classified.target}
                )

            elif (
                classified.intent == intent_parser.Intent.SEARCH
                and classified.target
            ):
                self._context.record_search(classified.target)

        return True

    def process(self, command):
        """Process a single command.

        Returns False if this was an exit command (caller should stop
        the main loop), True otherwise.

        Phase 8: if `command` deterministically splits into more than
        one already-known clause (see natural_language.split_into_
        clauses() - "open chrome and search for python"), each clause
        is processed independently, in order, through this exact same
        method - no validation is bypassed, nothing here executes a
        clause directly. If it does NOT cleanly split (including the
        common case of a single, unchanged command), `command` is used
        completely unmodified below, byte-for-byte identical to before
        Phase 8.

        Phase 9: if a dangerous command is awaiting confirmation (see
        DANGEROUS_COMMANDS above), THIS call is treated purely as the
        yes/no reply to it - resolved first, before wake-word-stripped
        text is split, normalized, or dispatched in any way. Only
        reachable at all when config.REQUIRE_CONFIRMATION_FOR_DANGEROUS_
        COMMANDS is True; when it's False (the default), self.
        _pending_confirmation can never become non-None, so this branch
        is dead code and behavior is byte-for-byte unchanged from before
        Phase 9.

        Phase 10.3: if a follow-up question is awaiting a reply (see
        self._pending_slot / context_manager.py), THIS call is treated
        purely as that reply - resolved second, right after the Phase 9
        confirmation check above and before anything else. Only
        reachable at all when config.ENABLE_CONTEXT_LAYER is True (and,
        in practice, config.ENABLE_INTENT_FALLBACK_LAYER is also True,
        since that layer is what discovers a slot-fillable incomplete
        intent in the first place); with either off, self._pending_slot
        can never become non-None, so this branch is dead code and
        behavior is byte-for-byte unchanged from before Phase 10.3.

        Phase 10.4: a standalone "close it"/"open that"/"switch to
        this" style command is resolved against the last-named
        application (see self._context / context_manager.py) near the
        very end of this method - only after the entire deterministic
        dispatch chain AND the Phase 10.2 intent fallback have both
        already failed to recognize the command as-is. Only reachable
        at all when config.ENABLE_REFERENCE_RESOLUTION is True; when
        it's False (the default), context_manager.resolve_reference()
        is never even called, so behavior is byte-for-byte unchanged
        from before Phase 10.4.
        """

        if config.ENABLE_CONTEXT_LAYER or config.ENABLE_REFERENCE_RESOLUTION:
            self._context.advance_turn()

        if self._pending_confirmation is not None:

            pending = self._pending_confirmation
            self._pending_confirmation = None

            if is_confirm_command(_light_normalize(command)):
                return system_control.handle_system(pending, self.voice)

            self.voice.speak("Cancelled.")
            return True

        # PENDING CONTEXT/SLOT STATE (Phase 10.3) - checked immediately
        # after the Phase 9 confirmation-reply check above (so the two
        # pending-state machines never overlap) and BEFORE the Phase 9
        # dangerous-phrase gate below, exactly per the architecture in
        # the Phase 10.3 audit/plan. This block NEVER executes a
        # control module itself - context_manager.resolve_pending_slot()
        # is pure and only ever returns either a canonical command
        # string (fed back into self.process(), which re-enters this
        # method from the top - so the Phase 9 gate immediately below
        # still sees it) or an instruction to treat `command` as a
        # brand-new, unmodified command (also fed back into
        # self.process(), for the exact same reason). Only reachable at
        # all when config.ENABLE_CONTEXT_LAYER is True; when it's False
        # (the default), self._pending_slot can never become non-None,
        # so this branch is dead code and behavior is byte-for-byte
        # unchanged from before Phase 10.3.
        if self._pending_slot is not None:

            pending = self._pending_slot
            self._pending_slot = None

            resolution = context_manager.resolve_pending_slot(
                pending, command, self._context
            )

            if resolution.kind == context_manager.ResolutionKind.RESOLVED:
                return self.process(resolution.canonical_command)

            if resolution.kind == context_manager.ResolutionKind.NEW_COMMAND:
                return self.process(command)

            # UNRESOLVED (empty/unintelligible reply, or an expired
            # slot with nothing recognizable in the new text) - fail
            # closed, do not guess at a query.
            self.voice.speak("Never mind.")
            return True

        # DANGEROUS COMMAND CONFIRMATION GATE (Phase 9) - checked here,
        # first, on lightly-normalized RAW text - deliberately BEFORE
        # natural_language.split_into_clauses() and BEFORE command_
        # parser.normalize(). Two independent reasons this ordering is
        # load-bearing, not stylistic:
        #
        # 1. A phrase like "lock computer and open chrome" is never
        #    split by split_into_clauses() (intent_parser.classify(
        #    "lock computer") is UNKNOWN - there is no SYSTEM category
        #    in that classifier - so the all-or-nothing split safety
        #    correctly refuses to split it), so the WHOLE unsplit
        #    phrase reaches this dispatch chain as one string. If this
        #    gate ran any later than the earliest possible point, an
        #    earlier-checked branch (e.g. web_control.handle()'s bare
        #    "chrome" substring match) would fire first and execute
        #    before the dangerous phrase was ever evaluated.
        #
        # 2. command_parser.normalize() itself can DESTROY a dangerous
        #    phrase before this gate would ever see it if checked after
        #    normalize() ran: "restart computer and mute" normalizes to
        #    just "mute" (canonicalize_volume_phrase() rewrites the
        #    ENTIRE string to "mute" whenever that word appears
        #    anywhere in it - pre-existing since Phase 5, not modified
        #    here). Checking the lightly-normalized (lowercase/
        #    whitespace-collapsed only, NOT the full normalize()
        #    pipeline) raw text instead means the dangerous phrase is
        #    always seen intact.
        #
        # Default False -> this whole block never executes, so behavior
        # is byte-for-byte unchanged from before Phase 9.
        if config.REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS:

            light_command = _light_normalize(command)
            matched = _matched_dangerous_command(light_command)

            if matched:
                self._pending_confirmation = light_command
                self.voice.speak(DANGEROUS_COMMAND_PROMPTS[matched])
                return True

        clauses = natural_language.split_into_clauses(command)

        if len(clauses) > 1:

            if config.DEBUG:
                print(f"[DEBUG] split '{command}' into clauses: {clauses}")

            result = True

            for clause in clauses:
                if not self.process(clause):
                    result = False

            return result

        raw_command = command
        command = command_parser.normalize(command)

        # Phase 10.4: classified once here (reusing the exact same
        # pure intent_parser.classify() call this project has used for
        # DEBUG diagnostics since Phase 8) and passed to
        # _finish_dispatch() below, which records the last-named
        # application entity when the command that's about to be
        # dispatched names one - see context_manager.py /
        # self._context. Only computed when actually needed (DEBUG
        # output or the reference-resolution layer being enabled) -
        # with both off, this is skipped entirely and behavior/cost is
        # unchanged from before Phase 10.4.
        classified = None

        if config.DEBUG or config.ENABLE_REFERENCE_RESOLUTION:
            classified = intent_parser.classify(command)

        if config.DEBUG:
            print(f"[DEBUG] raw='{raw_command}' normalized='{command}'")
            print(
                f"[DEBUG] intent={classified.intent} "
                f"target={classified.target!r}"
            )

        if not command:
            return True

        # EXIT
        if is_exit_command(command):

            self.voice.speak(
                "Going offline. Goodbye."
            )

            return False

        # INFORMATION
        if handle_information(command, self.voice):
            return True

        # GREETING
        if handle_greeting(command, self.voice):
            return True

        # TARGETED WINDOW CONTROL (Phase 6) - must run before WEB, since
        # e.g. "close chrome" would otherwise be caught by web_control's
        # bare "chrome" substring check, which only knows how to OPEN
        # Chrome, not close a specific window. Only intercepts commands
        # that name a known application from the fixed allow-list; any
        # other command (including all untargeted window commands) is
        # unaffected and falls through to the unchanged chain below.
        if window_control.handle_targeted(command, self.voice):
            return self._finish_dispatch(classified)

        # WEB
        if web_control.handle(command, self.voice):
            return self._finish_dispatch(classified)

        # APPLICATIONS
        if system_control.handle_application(command, self.voice):
            return self._finish_dispatch(classified)

        # SYSTEM
        if system_control.handle_system(command, self.voice):
            return self._finish_dispatch(classified)

        # WINDOW CONTROL
        if window_control.handle(command, self.voice):
            return self._finish_dispatch(classified)

        # VOLUME
        if volume_control.handle(command, self.voice):
            return self._finish_dispatch(classified)

        # MEDIA
        if media_control.handle(command, self.voice):
            return self._finish_dispatch(classified)

        # SCREEN
        if screen_control.handle(command, self.voice):
            return self._finish_dispatch(classified)

        # KEYBOARD
        if keyboard_control.handle(command, self.voice):
            return self._finish_dispatch(classified)

        # MOUSE
        if mouse_control.handle(command, self.voice):
            return self._finish_dispatch(classified)

        # INTENT FALLBACK LAYER (Phase 10.2) - only reached once every
        # handler above has already failed to recognize `command`.
        # Rule-based only (see intent_layer.py) - no LLM, no new
        # dependency. Every frame it produces is rendered to a
        # canonical command string and re-fed into THIS SAME process()
        # method (never into a control module directly), so the
        # Phase 9 dangerous-command gate at the very top of process()
        # - which runs on every call, including this recursive one -
        # cannot be bypassed by anything this layer produces. Default
        # off (config.ENABLE_INTENT_FALLBACK_LAYER) - when off, this
        # block never executes and behavior is byte-for-byte unchanged
        # from before Phase 10.2.
        if config.ENABLE_INTENT_FALLBACK_LAYER:

            frames = intent_layer.understand(command)

            confident_frames = [
                frame for frame in frames
                if frame.confidence >= config.INTENT_CONFIDENCE_THRESHOLD
            ]

            if confident_frames:

                if config.DEBUG:
                    print(f"[DEBUG] intent_layer frames: {confident_frames}")

                # CONTEXT SLOT CREATION (Phase 10.3) - only when the
                # context layer is enabled, exactly one confident frame
                # was found this turn, and it's incomplete (currently
                # only ever an incomplete SEARCH frame - see
                # intent_layer.SEARCH_INCOMPLETE_RE). A multi-frame
                # chain never triggers a follow-up question - same
                # all-or-nothing conservatism natural_language.
                # split_into_clauses() and this module's own multi-
                # intent loop already use elsewhere. This never calls a
                # control module: context_manager.create_pending_slot()
                # is pure and only ever returns a PendingSlotRequest (or
                # None) - the actual question is spoken here, by this
                # same voice.speak() call every other handler in this
                # file already uses.
                if (
                    config.ENABLE_CONTEXT_LAYER
                    and len(confident_frames) == 1
                    and confident_frames[0].incomplete
                ):

                    pending = context_manager.create_pending_slot(
                        confident_frames[0], self._context
                    )

                    if pending is not None:
                        self._pending_slot = pending
                        self.voice.speak(pending.prompt)
                        return True

                result = True
                executed = False

                for frame in confident_frames:

                    canonical = intent_layer.to_canonical_command(frame)

                    if canonical:
                        executed = True
                        if not self.process(canonical):
                            result = False

                # Every confident frame this project could produce
                # BEFORE Phase 10.3 always rendered to a non-None
                # canonical command by construction (see intent_layer.
                # to_canonical_command()'s per-intent branches - each
                # only ever builds a frame from already-validated
                # entities), so `executed` was always True here and
                # this check changes nothing for any of them. The one
                # new exception is an incomplete SEARCH frame reaching
                # this loop with the context layer OFF (to_canonical_
                # command() returns None for it by design) - that case
                # now correctly falls through to the standard "I don't
                # know how to do that" response below, instead of
                # silently returning True with no spoken response.
                if executed:
                    return result

        # MULTILINGUAL NORMALIZATION LAYER (Phase 11.1) - only reached
        # once the entire primary dispatch chain AND the Phase 10.2
        # intent fallback above have both already failed to recognize
        # `command`. Deterministic Urdu-script/Roman-Urdu (and mixed-
        # language) phrase recognition - see multilingual_normalizer.py.
        # Almost every command it can produce is rendered via intent_
        # parser.to_canonical_command() (reused, UNMODIFIED - see that
        # module's docstring), so it inherits intent_parser's own
        # allow-list validation for free; the two exceptions ("hello"/
        # "exit") are fixed string literals, not derived from user
        # input. Either way this can only ever produce one of the exact
        # same fixed canonical command strings the existing dispatch
        # chain already understands - never an arbitrary string, and
        # structurally never "lock computer"/"shutdown computer"/
        # "restart computer" (intent_parser.Intent has no such category
        # at all - see multilingual_normalizer.py's module docstring).
        # Fed back into THIS SAME process() method (recursively),
        # exactly like the Phase 10.2 intent-fallback loop above, so the
        # Phase 9 dangerous-command gate at the very top of process() -
        # which runs on every call, including this recursive one -
        # cannot be bypassed by anything this layer produces.
        #
        # Phase 11.1 deliberately implements NO dangerous-command
        # recognition, in any language - that is explicit, separate,
        # future Phase 11.2 scope (see the Phase 11.0 architecture
        # audit, section D, and multilingual_normalizer.py's module
        # docstring). Default off (config.ENABLE_MULTILINGUAL_LAYER) -
        # when off, this block never executes and behavior is
        # byte-for-byte unchanged from before Phase 11.1.
        if config.ENABLE_MULTILINGUAL_LAYER:

            multilingual_canonical = multilingual_normalizer.understand(command)

            if multilingual_canonical:

                if config.DEBUG:
                    print(
                        f"[DEBUG] multilingual_normalizer: '{command}' -> "
                        f"'{multilingual_canonical}'"
                    )

                return self.process(multilingual_canonical)

        # REFERENCE RESOLUTION (Phase 10.4/10.5) - "it"/"that"/"this"
        # (optionally "... again"/"... once more" - Phase 10.5) -> the
        # last-named application (e.g. "open chrome" ... later ...
        # "close it" -> "close chrome"), OR (Phase 10.5) the exact
        # phrase "search that again" -> the last search query (e.g.
        # "search for cats" ... later ... "search that again" ->
        # "search for cats"). Only reached once the entire primary
        # dispatch chain AND the Phase 10.2 intent fallback above have
        # both already failed to recognize `command` as-is.
        # context_manager.resolve_reference()/resolve_repeat_search()
        # are pure and only ever render one of the exact same fixed
        # canonical command strings the dispatch chain above already
        # understands - never a control module call, never an
        # arbitrary command. Fed back into THIS SAME process() method
        # (recursively), so the Phase 9 dangerous-command gate at the
        # very top of process() - which runs on every call, including
        # this recursive one - cannot be bypassed by anything either
        # layer produces. Default off (config.ENABLE_REFERENCE_
        # RESOLUTION, reused for both - see the Phase 10.5 architecture
        # audit) - when off, this block never executes and behavior is
        # byte-for-byte unchanged from before Phase 10.4/10.5.
        if config.ENABLE_REFERENCE_RESOLUTION:

            resolved = context_manager.resolve_reference(command, self._context)

            if resolved is None:
                resolved = context_manager.resolve_repeat_search(
                    command, self._context
                )

            if config.DEBUG and resolved:
                print(f"[DEBUG] resolved reference '{command}' -> '{resolved}'")

            if resolved:
                return self.process(resolved)

        # AI ROUTER (Phase 12.1) - only reached once the ENTIRE
        # deterministic chain above (clause splitting, normalize(), the
        # fixed dispatch chain, the intent fallback layer, the
        # multilingual layer, reference resolution) has already failed
        # to recognize `command`. See ai_router.py's own docstring for
        # the complete security model - in short: a tool-call outcome
        # is ALREADY validated against ai_tools.TOOL_REGISTRY's closed
        # allow-list and rendered to a canonical command string by the
        # time it reaches here, and is fed back into THIS SAME
        # process() method (recursively), so the Phase 9 dangerous-
        # command gate at the very top of process() - which runs on
        # every call, including this recursive one - cannot be
        # bypassed by anything this layer produces. A speech outcome is
        # spoken DIRECTLY and deliberately never recurses through
        # process() - see ai_router.RoutingOutcome's own docstring for
        # why blurring that distinction would be unsafe.
        #
        # Default off (config.ENABLE_AI_LAYER) - when off, this block
        # never executes and behavior is byte-for-byte unchanged from
        # before Phase 12.1. Even when on, Phase 12.1 registers NO AI
        # backend at all (see ai_backend.get_backend()), so ai_router.
        # handle() always returns None today regardless - this hook
        # exists now so a future phase can register a real backend
        # without any further changes to this dispatch chain.
        if config.ENABLE_AI_LAYER:

            outcome = ai_router.handle(command, self._context)

            if outcome is not None:

                if outcome.kind == ai_router.RoutingOutcome.COMMAND:
                    return self.process(outcome.value)

                if outcome.kind == ai_router.RoutingOutcome.SPEECH:
                    self.voice.speak(outcome.value)
                    return True

        # UNKNOWN
        self.voice.speak(
            "I heard you, but I don't "
            "know how to do that yet."
        )

        return True
