"""Phase 12.1: the AI router - the ONE place a future LLM's output is
allowed to influence what JARVIS does, and the ONE place that decides
whether the (currently unconnected) AI layer is even consulted at all.

SECURITY MODEL:

- Deterministic-first, structurally, not by convention: commands.py
  only ever calls handle() (this module's entry point) AFTER its
  entire existing deterministic chain - normalize, the fixed dispatch
  chain, the intent fallback layer, the multilingual layer, reference
  resolution - has ALREADY failed to recognize the command (see
  commands.py's own insertion point, immediately before the final "I
  don't know how to do that yet." response). This module has no
  separate "is this deterministic" pre-check of its own to keep in
  sync with that chain - POSITION in commands.py IS the guarantee, the
  same way intent_layer.py and multilingual_normalizer.py are already
  positioned after the primary chain for the identical reason.
- LLM output is ALWAYS untrusted input. A ToolCall response is NEVER
  turned into a canonical command without first passing through ai_
  tools.validate_tool_call()/process_tool_call() - this module never
  bypasses that boundary, and never renders a command string itself.
- A resolved canonical command is handed back to the CALLER (commands.
  py), which recurses through CommandProcessor.process() - the exact
  same pattern intent_layer.py/multilingual_normalizer.py already use.
  This module has no reference to a CommandProcessor and cannot call
  process() itself - the Phase 9 dangerous-command gate (the
  unconditional first check on every process() call) is enforced by
  the CALLER's own recursion, by construction, not by anything in this
  module choosing to respect it.
- A TEXT response is handed back to the caller as something to SPEAK
  directly (voice.speak()) - it is NEVER fed back into process(). This
  is the other half of the safety property above: a generated sentence
  that happens to resemble a command must never self-execute just
  because it was returned in the wrong "slot". See RoutingOutcome
  below - COMMAND and SPEECH are structurally distinct, and the caller
  (commands.py) must route each to a different place, never both to
  the same one.
- Every failure mode fails CLOSED: no backend registered, the backend
  raises, the backend returns something that isn't a proper AIResponse,
  or the tool call it produced is rejected by ai_tools - all of these
  return None, and the caller falls through to the EXISTING "I don't
  know how to do that yet." response, exactly as if this module didn't
  exist. Nothing here ever guesses at what a malformed response
  "probably meant".

NO LLM IS CONNECTED IN THIS PHASE (see ai_backend.py - get_backend()
always returns None until a future phase registers a real provider).
handle() below is exercised in tests via a fake AIBackend registered
with ai_backend.register_backend() - never a real model.
"""

import ai_backend
import ai_tools


class RoutingOutcome:
    """What handle() decided the caller should do, if anything.

    kind == COMMAND: `value` is a canonical command string - the
    caller MUST recurse it through CommandProcessor.process(), never
    execute it directly.

    kind == SPEECH: `value` is plain text - the caller MUST hand it
    directly to voice.speak(), and MUST NEVER pass it to process().
    """

    COMMAND = "command"
    SPEECH = "speech"

    __slots__ = ("kind", "value")

    def __init__(self, kind, value):
        self.kind = kind
        self.value = value

    def __repr__(self):
        return f"RoutingOutcome({self.kind!r}, {self.value!r})"


def handle(command, context=None):
    """The Phase 12.1 AI-router entry point. `command` is a not-
    deterministically-recognized user utterance (already past the
    entire existing deterministic chain - see this module's own
    docstring). `context` is passed through opaquely to whatever
    backend is registered (see ai_backend.AIBackend.converse()).

    Returns a RoutingOutcome, or None if there's nothing to do - which
    is unconditionally true in Phase 12.1 (no backend registered - see
    ai_backend.get_backend()), and remains true for a future phase
    whenever the backend can't be reached, raises, returns something
    malformed, or requests a tool call that ai_tools rejects. Never
    raises itself - every failure path here is a normal, expected,
    "nothing to do" outcome, not an error the caller needs to handle
    specially."""

    backend = ai_backend.get_backend()

    if backend is None:
        return None

    try:
        response = backend.converse(command, context)
    except Exception:
        return None

    return _resolve(response)


def _resolve(response):
    """Turn a raw AIResponse into a RoutingOutcome, or None if it
    can't be trusted/resolved. This is where the "LLM output is always
    untrusted" rule is actually enforced for tool calls - see ai_
    tools.process_tool_call()."""

    if not isinstance(response, ai_backend.AIResponse):
        return None

    if response.kind == ai_backend.ResponseKind.TOOL_CALL:

        try:
            canonical = ai_tools.process_tool_call({
                "tool": response.tool_call.tool_name,
                "arguments": response.tool_call.arguments,
            })
        except ai_tools.ToolContractError:
            return None

        return RoutingOutcome(RoutingOutcome.COMMAND, canonical)

    if response.kind == ai_backend.ResponseKind.TEXT:
        return RoutingOutcome(RoutingOutcome.SPEECH, response.text)

    return None
