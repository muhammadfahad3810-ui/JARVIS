"""Phase 12.1: the abstraction a future LLM provider (a local model, a
cloud API, or anything else) will implement - NO PROVIDER IS
IMPLEMENTED OR REGISTERED IN THIS PHASE. get_backend() always returns
None right now. This is deliberate, not a placeholder bug: Phase 12.1's
own task scope is "build the router/tool-contract infrastructure
WITHOUT connecting an actual LLM."

A future phase adds a concrete AIBackend subclass (e.g. LocalLLMBackend
wrapping a local model, CloudLLMBackend wrapping an API client) and
calls register_backend() with it, once, somewhere in startup wiring
(mirroring how voice.py selects a TTS backend and stt_backend.py
selects an STT backend). ai_router.py and ai_tools.py need NO changes
to support that - proving this is possible without touching either is
the actual point of this module existing now.

SAFETY - what an AIBackend implementation can and cannot return:

An AIBackend.converse() call may ONLY ever return an AIResponse, and an
AIResponse is STRUCTURALLY constrained to be exactly one of:
  - a ToolCall: a tool NAME (a plain string) plus RAW, UNVALIDATED
    arguments (a plain dict) - untrusted input, by construction, until
    ai_tools.validate_tool_call() has processed it. A ToolCall is
    inert data; it has no method that executes anything.
  - TEXT: a plain string to be spoken, never re-interpreted as a
    command (see ai_router.py's own docstring for why that distinction
    is load-bearing).

There is no third option, and specifically no way for an AIBackend to
hand back executable code, a shell command, a callable, or a direct
reference to any control module - the type system here cannot
represent that even if a future provider implementation wanted to.
"""

import abc


class ResponseKind:
    TOOL_CALL = "tool_call"
    TEXT = "text"


class ToolCall:
    """A tool name and RAW, UNVALIDATED arguments, exactly as an
    AIBackend produced them. Inert data only - see this module's own
    docstring. Always passed through ai_tools.validate_tool_call()
    before anything renders to a command; never executed directly by
    anything in this module or ai_router.py."""

    __slots__ = ("tool_name", "arguments")

    def __init__(self, tool_name, arguments=None):
        self.tool_name = tool_name
        self.arguments = arguments if arguments is not None else {}

    def __repr__(self):
        return f"ToolCall({self.tool_name!r}, {self.arguments!r})"


class AIResponse:
    """Exactly one of a ToolCall or plain text - never both, never
    anything else. Use the tool()/speak() constructors below rather
    than calling __init__() directly."""

    __slots__ = ("kind", "tool_call", "text")

    def __init__(self, kind, tool_call=None, text=None):

        if kind == ResponseKind.TOOL_CALL and tool_call is None:
            raise ValueError("a TOOL_CALL response requires a tool_call")

        if kind == ResponseKind.TEXT and not isinstance(text, str):
            raise ValueError("a TEXT response requires a text string")

        self.kind = kind
        self.tool_call = tool_call
        self.text = text

    @classmethod
    def tool(cls, tool_name, arguments=None):
        return cls(ResponseKind.TOOL_CALL, tool_call=ToolCall(tool_name, arguments))

    @classmethod
    def speak(cls, text):
        return cls(ResponseKind.TEXT, text=text)

    def __repr__(self):
        if self.kind == ResponseKind.TOOL_CALL:
            return f"AIResponse.tool({self.tool_call!r})"
        return f"AIResponse.speak({self.text!r})"


class AIBackend(abc.ABC):
    """Interface a future LLM provider must implement. Deliberately
    narrow: one method, a conversational turn in, one AIResponse out."""

    @abc.abstractmethod
    def converse(self, command, context):
        """`command` is the already-STT-transcribed, already-proven-
        NOT-deterministically-recognized user utterance (a plain
        string) - see ai_router.py's own docstring for exactly when
        this is reached. `context` is whatever short-term
        conversational state the caller passes (Phase 12.1: opaque to
        this interface - a future phase defines its exact shape, most
        likely built on context_manager.ConversationContext).

        Must return an AIResponse, or raise - implementations must
        never return None, a bare string, or anything else, and must
        never execute anything themselves; they only ever describe
        what they'd like to happen."""

        raise NotImplementedError


_registered_backend = None


def get_backend():
    """Return the currently registered AIBackend, or None if none is
    registered - the ALWAYS-true case in Phase 12.1, since no provider
    exists yet. ai_router.py treats None as "nothing to do" and falls
    through to the existing unknown-command response, the same fail-
    closed/inert-by-default policy this project already uses for every
    optional backend (see stt_backend.py/tts_backend.py's own is_
    available()-gated patterns)."""

    return _registered_backend


def register_backend(backend):
    """Register the AIBackend instance ai_router.py should consult.
    Not called anywhere in production code yet (Phase 12.1 registers
    nothing) - exists so tests can register a fake backend, and so a
    future phase's real provider has a single, obvious place to plug
    in without touching ai_router.py or ai_tools.py. Pass None to
    unregister (restores the Phase 12.1 default "no backend" state)."""

    global _registered_backend

    if backend is not None and not isinstance(backend, AIBackend):
        raise TypeError("backend must be an AIBackend instance (or None)")

    _registered_backend = backend
