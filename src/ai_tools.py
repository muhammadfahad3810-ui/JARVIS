"""Phase 12.1: the AI tool contract - allow-listed tools, closed-enum
argument validation, and rendering to the EXACT SAME canonical command
strings the deterministic dispatch chain already understands.

SECURITY MODEL (see ai_router.py's own docstring for the full picture):

- LLM output is ALWAYS untrusted input. Every function in this module
  that accepts a tool name or arguments treats them as hostile by
  default - nothing here ever trusts that a caller already validated
  anything.
- Only a tool name present in TOOL_REGISTRY can ever be resolved to a
  command - an unrecognized name is REJECTED (UnknownToolError), never
  guessed at, never fuzzy-matched.
- Every argument is validated against a CLOSED enum of allowed string
  values, reusing this project's EXISTING allow-lists wherever one
  already exists (intent_parser.KNOWN_APPLICATIONS, intent_parser.
  KNOWN_KEYS) rather than defining a second, parallel list that could
  drift out of sync. The ONE deliberate exception is search's `query`
  argument (see SEARCH_FREE_TEXT_ARGS below) - free text is allowed
  there ONLY because web_control.search() already only ever URL-
  encodes it into a Google search link and hands it to webbrowser.
  open(), never to subprocess/os.system/eval/exec - see tests/test_
  ai_tools.py's dedicated safety tests for direct proof of that claim,
  not just an assertion of it here.
- Nothing in TOOL_REGISTRY can render to "lock computer"/"shutdown
  computer"/"restart computer" (commands.DANGEROUS_COMMANDS) - there
  is no tool, and no argument value of any tool, that produces one of
  those three strings. This is a structural property of the fixed
  dict literal below, not a runtime check - verified directly by
  tests/test_ai_tools.py's own exhaustive sweep.
- Every tool's render() function reuses an EXISTING deterministic
  handler's canonical command string (see each ToolSpec below) - this
  module never implements a second copy of scrolling, clicking,
  opening an application, etc. A rendered string is only ever handed
  BACK to commands.CommandProcessor.process() (by ai_router.py, never
  by this module directly) - the exact same recursion pattern intent_
  layer.py and multilingual_normalizer.py already use, which is what
  keeps the Phase 9 dangerous-command gate (the unconditional first
  check on every process() call, including recursive ones) authoritative
  over anything this module ever produces.
- This module NEVER imports voice, any control module, subprocess,
  os.system, or ctypes - it cannot execute anything, even in
  principle. Verified structurally by tests/test_ai_tools.py, not just
  by convention (the same "prove it, don't just claim it" discipline
  multilingual_normalizer.py's own tests already use for the identical
  property).

Nothing in this module is wired to an actual LLM (Phase 12.1 scope -
see ai_backend.py). It is pure, deterministic Python: given the same
tool name and arguments, it always either raises the same exception or
returns the same canonical string.
"""

import intent_parser


# ---------------------------------------------------------------------
# Rejection reasons - one exception type per failure mode (Task 1),
# so a caller/test can assert exactly WHY a request was rejected, not
# just that it was. All inherit from ToolContractError so callers that
# don't care about the distinction can catch that alone.
# ---------------------------------------------------------------------

class ToolContractError(Exception):
    """Base class for every way a tool request can be rejected."""


class MalformedToolCallError(ToolContractError):
    """The request isn't even shaped like a tool call (not an object,
    missing the tool name field, tool name isn't a string, arguments
    present but not an object/dict)."""


class UnknownToolError(ToolContractError):
    """The tool name isn't in TOOL_REGISTRY at all."""


class MissingArgumentError(ToolContractError):
    """A required argument for this tool is absent."""


class UnknownArgumentError(ToolContractError):
    """An argument was supplied that this tool doesn't accept."""


class InvalidArgumentTypeError(ToolContractError):
    """An argument's value isn't the type this tool expects (e.g. a
    number, list, or nested object where a string was required)."""


class InvalidArgumentValueError(ToolContractError):
    """An argument's value IS the right type, but isn't in its closed
    allow-list of accepted values (or, for the one free-text argument
    this module permits, is empty/blank)."""


# Sentinel marking an argument as this module's ONE deliberate free-
# text exception (see module docstring) - never a second, arbitrary
# escape hatch; only ever used for search's `query` argument below.
FREE_TEXT = object()


class ToolSpec:
    """One allow-listed tool: its argument schema (each value either a
    frozenset of allowed strings, or the FREE_TEXT sentinel) and the
    render() function that turns ALREADY-VALIDATED arguments into the
    exact canonical command string commands.py's existing dispatch
    chain already understands. Every argument is required - this
    project's tools are small and fixed enough that optional arguments
    would only add ambiguity, not value."""

    __slots__ = ("name", "args", "render")

    def __init__(self, name, args, render):
        self.name = name
        self.args = args
        self.render = render


class ValidatedToolCall:
    """A tool name plus arguments that have ALREADY passed validate_
    tool_call() - every argument present, every value within its
    closed allow-list, no extras. Only ever constructed by validate_
    tool_call() below; never construct one directly from untrusted
    input."""

    __slots__ = ("tool_name", "arguments")

    def __init__(self, tool_name, arguments):
        self.tool_name = tool_name
        self.arguments = arguments

    def __repr__(self):
        return f"ValidatedToolCall({self.tool_name!r}, {self.arguments!r})"


# ---------------------------------------------------------------------
# TOOL_REGISTRY - the complete, closed set of actions an AI tool call
# can ever request. Every entry below maps to an ALREADY-EXISTING,
# ALREADY-TESTED deterministic handler - see each render()'s comment
# for exactly which one. Deliberately narrow: only the categories the
# Phase 12.1 task explicitly named (open_application, press_key,
# scroll, mouse_action, volume, media, tab_navigation, browser_
# navigation, refresh, search) - NEW_TAB/CLOSE_TAB and anything else
# not explicitly requested are intentionally left out of this initial
# rollout, not an oversight.
#
# NOTHING here can render "lock computer"/"shutdown computer"/
# "restart computer", type arbitrary text, run a shell/PowerShell/
# Python command, open an arbitrary executable path, or target an
# arbitrary (non-allow-listed) window.
# ---------------------------------------------------------------------

# Reused, not duplicated, from intent_parser.py - the SAME allow-list
# window_control.py/system_control.py's own dispatch already trusts.
# Note: this legitimately includes "command prompt"/"powershell"/"cmd"
# - OPENING an empty terminal window is a pre-existing, safe JARVIS
# capability since Phase 3 (system_control.open_command_prompt() etc.),
# completely distinct from EXECUTING a command inside one, which no
# tool in this registry can ever do.
_KNOWN_APPLICATIONS = frozenset(intent_parser.KNOWN_APPLICATIONS.keys())

# Reused, not duplicated, from intent_parser.py - "delete" is
# deliberately NOT in this list (see intent_parser.KNOWN_KEYS and
# keyboard_control.handle()'s own docstring) and this module never
# adds it back.
_KNOWN_KEYS = frozenset(intent_parser.KNOWN_KEYS)

_SCROLL_DIRECTIONS = frozenset({"up", "down"})
_MOUSE_ACTIONS = frozenset({
    "click", "double_click", "right_click",
    "move_left", "move_right", "move_up", "move_down",
})
_VOLUME_ACTIONS = frozenset({"up", "down", "mute", "unmute"})
_MEDIA_ACTIONS = frozenset({"play_pause", "next_track", "previous_track"})
_TAB_DIRECTIONS = frozenset({"next", "previous"})
_BROWSER_DIRECTIONS = frozenset({"back", "forward"})

_MOUSE_ACTION_TO_CANONICAL = {
    "click": "click",
    "double_click": "double click",
    "right_click": "right click",
    "move_left": "move left",
    "move_right": "move right",
    "move_up": "move up",
    "move_down": "move down",
}

_VOLUME_ACTION_TO_CANONICAL = {
    "up": "volume up",
    "down": "volume down",
    "mute": "mute",
    "unmute": "unmute",
}

_MEDIA_ACTION_TO_CANONICAL = {
    "play_pause": "play",
    "next_track": "next track",
    "previous_track": "previous track",
}


def _render_open_application(application):
    # Reuses intent_parser.KNOWN_APPLICATIONS' own canonical strings
    # directly - the SAME dict window_control.py/web_control.py/
    # system_control.py's dispatch already resolves these names
    # through, not a second copy.
    return intent_parser.KNOWN_APPLICATIONS[application]


def _render_press_key(key):
    # Matches keyboard_control.handle()'s own "press <key>" checks
    # exactly. `key` is already guaranteed in intent_parser.KNOWN_KEYS
    # (never "delete") by validate_tool_call() before this ever runs.
    return f"press {key}"


def _render_scroll(direction):
    # Matches keyboard_control.handle()'s "scroll up"/"scroll down"
    # checks exactly.
    return f"scroll {direction}"


def _render_mouse_action(action):
    # Matches mouse_control.handle()'s own fixed phrase checks exactly.
    return _MOUSE_ACTION_TO_CANONICAL[action]


def _render_volume(action):
    # Matches volume_control.handle()'s own fixed phrase checks
    # exactly - "up"/"down" nudge via the multimedia keys, "mute"/
    # "unmute" go through the true Core Audio SetMute() path, exactly
    # as they already do for a spoken "mute"/"unmute" command.
    return _VOLUME_ACTION_TO_CANONICAL[action]


def _render_media(action):
    # Matches media_control.handle()'s own fixed phrase checks exactly.
    return _MEDIA_ACTION_TO_CANONICAL[action]


def _render_tab_navigation(direction):
    # Matches web_control.handle()'s "next tab"/"previous tab" checks
    # exactly.
    return f"{direction} tab"


def _render_browser_navigation(direction):
    # Matches web_control.handle()'s go_back()/go_forward() dispatch
    # exactly ("go back" via _BACK_PATTERN, "go forward" via its own
    # substring check).
    return f"go {direction}"


def _render_refresh():
    # Matches web_control.handle()'s "refresh" check exactly.
    return "refresh"


def _render_search(query):
    # Matches web_control.handle()'s "search for <query>" prefix check
    # exactly - web_control.search() only ever URL-encodes `query` into
    # a Google search link and hands it to webbrowser.open(); it is
    # NEVER passed to subprocess.Popen, os.system, eval, or exec, in
    # this function or anywhere downstream of it. See tests/test_ai_
    # tools.py's dedicated search-safety tests for direct proof, not
    # just this comment's claim.
    return f"search for {query}"


TOOL_REGISTRY = {
    "open_application": ToolSpec(
        name="open_application",
        args={"application": _KNOWN_APPLICATIONS},
        render=_render_open_application,
    ),
    "press_key": ToolSpec(
        name="press_key",
        args={"key": _KNOWN_KEYS},
        render=_render_press_key,
    ),
    "scroll": ToolSpec(
        name="scroll",
        args={"direction": _SCROLL_DIRECTIONS},
        render=_render_scroll,
    ),
    "mouse_action": ToolSpec(
        name="mouse_action",
        args={"action": _MOUSE_ACTIONS},
        render=_render_mouse_action,
    ),
    "volume": ToolSpec(
        name="volume",
        args={"action": _VOLUME_ACTIONS},
        render=_render_volume,
    ),
    "media": ToolSpec(
        name="media",
        args={"action": _MEDIA_ACTIONS},
        render=_render_media,
    ),
    "tab_navigation": ToolSpec(
        name="tab_navigation",
        args={"direction": _TAB_DIRECTIONS},
        render=_render_tab_navigation,
    ),
    "browser_navigation": ToolSpec(
        name="browser_navigation",
        args={"direction": _BROWSER_DIRECTIONS},
        render=_render_browser_navigation,
    ),
    "refresh": ToolSpec(
        name="refresh",
        args={},
        render=_render_refresh,
    ),
    "search": ToolSpec(
        name="search",
        args={"query": FREE_TEXT},
        render=_render_search,
    ),
}


# ---------------------------------------------------------------------
# The validation boundary (Task 1 / Task 5). Three explicit stages -
# parse (shape only) -> validate (allow-list/type) -> render (canonical
# string) - each independently callable/testable, and composed by
# process_tool_call() below for the one obvious path a caller should
# actually use.
# ---------------------------------------------------------------------

def parse_tool_call(raw):
    """Stage 1: extract (tool_name, arguments) from `raw` - the
    untrusted structure a future LLM provider's tool-call output would
    already have been JSON-decoded into (e.g. {"tool": "scroll",
    "arguments": {"direction": "down"}}). Only checks SHAPE, never
    allow-list membership (see validate_tool_call() for that) - raises
    MalformedToolCallError for anything that isn't even shaped like a
    tool call: not a dict/object, missing the "tool" field, "tool" not
    a string, or "arguments" present but not a dict/object."""

    if not isinstance(raw, dict):
        raise MalformedToolCallError(
            f"tool call must be an object, got {type(raw).__name__}"
        )

    if "tool" not in raw:
        raise MalformedToolCallError("tool call is missing the 'tool' field")

    tool_name = raw["tool"]

    if not isinstance(tool_name, str):
        raise MalformedToolCallError(
            f"'tool' must be a string, got {type(tool_name).__name__}"
        )

    arguments = raw.get("arguments", {})

    if arguments is None:
        arguments = {}

    if not isinstance(arguments, dict):
        raise MalformedToolCallError(
            f"'arguments' must be an object, got {type(arguments).__name__}"
        )

    return tool_name, arguments


def validate_tool_call(tool_name, arguments):
    """Stage 2 - THE validation boundary (Task 5): reject an unknown
    tool, an unknown argument, a wrong argument type, an invalid enum
    value, a missing required argument, or an extra argument. Never
    silently coerces or guesses at a dangerous/ambiguous value - every
    rejection raises a specific ToolContractError subclass. Returns a
    ValidatedToolCall only when the request is fully well-formed."""

    spec = TOOL_REGISTRY.get(tool_name)

    if spec is None:
        raise UnknownToolError(f"unknown tool: {tool_name!r}")

    if not isinstance(arguments, dict):
        raise MalformedToolCallError(
            f"arguments for {tool_name!r} must be an object, "
            f"got {type(arguments).__name__}"
        )

    validated = {}

    for arg_name, allowed in spec.args.items():

        if arg_name not in arguments:
            raise MissingArgumentError(
                f"{tool_name!r} is missing required argument {arg_name!r}"
            )

        value = arguments[arg_name]

        if not isinstance(value, str):
            raise InvalidArgumentTypeError(
                f"{tool_name!r} argument {arg_name!r} must be a string, "
                f"got {type(value).__name__}"
            )

        if allowed is FREE_TEXT:

            if not value.strip():
                raise InvalidArgumentValueError(
                    f"{tool_name!r} argument {arg_name!r} must not be empty"
                )

        elif value not in allowed:
            raise InvalidArgumentValueError(
                f"{tool_name!r} argument {arg_name!r} has invalid value "
                f"{value!r} - must be one of {sorted(allowed)}"
            )

        validated[arg_name] = value

    extra = set(arguments) - set(spec.args)

    if extra:
        raise UnknownArgumentError(
            f"{tool_name!r} received unknown argument(s): {sorted(extra)}"
        )

    return ValidatedToolCall(tool_name=tool_name, arguments=validated)


def resolve_to_canonical_command(validated_call):
    """Stage 3: render an ALREADY-VALIDATED tool call to the exact
    canonical command string the existing deterministic dispatch chain
    already understands. Only ever called with a ValidatedToolCall
    (see validate_tool_call()) - never with raw/untrusted input. Never
    executes anything itself, never touches a control module, never
    calls voice.speak() - purely a string transform."""

    spec = TOOL_REGISTRY[validated_call.tool_name]

    return spec.render(**validated_call.arguments)


def process_tool_call(raw):
    """The one obvious path (Task 5): raw untrusted structure -> parse
    -> validate -> canonical command string. Composes parse_tool_call()
    -> validate_tool_call() -> resolve_to_canonical_command() in that
    fixed order; raises the same ToolContractError subclass any stage
    would raise on its own. This is what ai_router.py calls - nothing
    in this project should call the three stages separately outside of
    tests."""

    tool_name, arguments = parse_tool_call(raw)
    validated = validate_tool_call(tool_name, arguments)

    return resolve_to_canonical_command(validated)
