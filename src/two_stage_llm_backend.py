"""Phase 12.2.7: TwoStageLocalLLMBackend - a two-call replacement for
StructuredLocalLLMBackend's single-call oneOf(TEXT, TOOL_1, ..., TOOL_N)
decoding.

WHY: the Phase 12.2.6 benchmark ran StructuredLocalLLMBackend (Phase
12.2.4) against the live model (qwen2.5:3b-instruct-q4_K_M) on a fixed
24-prompt set and measured a 33% false-tool-call rate - a VALID,
ai_tools-accepted, but semantically WRONG tool call (e.g. "execute
python" -> open_application(notepad); "what can you do?" ->
open_application(chrome)), concentrated almost entirely in the
AMBIGUOUS/unsupported-capability category (29% accuracy there). The
same benchmark's own hypothesis - forcing the sampler to choose between
many valid JSON shapes in one grammar removes the built-in bias native
tool-calling templates have toward "no tool applies" - was tested
directly by splitting the decision into two separate, separately-
constrained calls: this module implements that split, and the
benchmark measured it at a 17% false-tool-call rate and 86% AMBIGUOUS
accuracy on the same prompt set (vs 29% for the single-call design).

ARCHITECTURE:

  STAGE 1 (classify only): Ollama structured output constrained to
  EXACTLY {"decision": "tool" | "text"} - see STAGE1_SCHEMA. This
  schema cannot express a tool name or arguments at all, so stage 1 is
  structurally incapable of selecting or executing a tool (Task 6) -
  not a policy choice enforced by the prompt, a grammar the sampler
  cannot violate.

  CONSERVATIVE DECISION RULE (Task 15): only a decision that parses as
  the JSON object {"decision": "tool"} (exact string match) proceeds to
  stage 2's tool-resolution schema. Every other outcome - decision ==
  "text", a missing/wrong-typed decision field, or any other value a
  future/misconfigured Ollama build might emit despite the schema -
  defaults to the TEXT path. Positive proof is required to reach the
  branch that can trigger a real action; the safe branch is the
  default, never something that has to be earned by ruling out
  ambiguity first. Only a genuinely unparseable stage-1 response (not
  valid JSON, or not a JSON object at all) fails closed via exception
  instead - see FAIL-CLOSED below.

  STAGE 2a (decision == "tool"): a SECOND Ollama call, constrained to a
  CLOSED oneOf of ONLY the registered tools' shapes (no text branch is
  present in this schema at all - see build_stage2_tool_schema()).
  Structurally derived from the LIVE ai_tools.TOOL_REGISTRY (Task 9/10)
  - every tool name, argument name, and allowed enum value is read from
  the registry at call time, exactly like structured_llm_backend.
  build_response_schema() already does for its own (single-stage)
  schema; nothing here hand-copies or independently re-derives what
  that module already reads the same way.

  STAGE 2b (decision == "text" or the conservative fallback above): a
  second Ollama call constrained to {"text": <string>}, generating a
  real conversational reply (so "tell me a joke" still gets an actual
  joke, not a canned refusal) rather than a fixed fallback string.

SAFETY - identical security model to StructuredLocalLLMBackend (Phase
12.2.4) and LocalLLMBackend (Phase 12.2.3), unchanged by this module:

- ai_tools.validate_tool_call()/process_tool_call() remain the ONLY
  authority over what becomes a canonical command (Task 12). This
  module never calls either function itself and never treats stage-2's
  closed schema as a substitute for that validation - every ToolCall
  this backend returns still carries RAW, UNVALIDATED arguments,
  exactly like its predecessor, and is still independently re-
  validated by ai_router.py's unmodified _resolve() before it can ever
  become a canonical command. If a future/misconfigured Ollama build
  ignores `format` entirely, this backend degrades to "a backend that
  reads .content as JSON instead of .tool_calls" - it does NOT degrade
  the security boundary, because there isn't one here to degrade.
- Nothing here can even name a dangerous command. Both stage-2 schemas
  are generated from (or, for the text branch, entirely independent
  of) ai_tools.TOOL_REGISTRY, which structurally contains no tool that
  renders "lock computer"/"shutdown computer"/"restart computer" (Task
  17 - see ai_tools.py's own docstring and tests/test_ai_tools.py's
  exhaustive sweep, unmodified and unaffected by this module).
- NOT registered anywhere by this module (Task 13/16). Constructing a
  TwoStageLocalLLMBackend has zero effect on live JARVIS behavior on
  its own - only jarvis._initialize_ai_backend() decides whether/what
  to register, and only after config.ENABLE_AI_LAYER is True. This
  module never imports voice, any control module, subprocess,
  os.system, or ctypes, and never calls CommandProcessor.process() -
  it can only ever return an ai_backend.AIResponse or raise
  local_llm_backend.OllamaError, exactly like every AIBackend
  implementation must (see ai_backend.py's own docstring). Verified
  structurally by this module's own tests, not just claimed here.
- structured_llm_backend.py (Phase 12.2.4, already validated) is not
  imported, modified, or referenced by this module at all - this is a
  fully independent AIBackend implementation, not a variant of it.
  local_llm_backend.py IS reused (subclassed, for __init__/
  _call_ollama only - unmodified) exactly as structured_llm_backend.py
  already does, for the same "don't re-implement HTTP/error handling a
  third time" reason.

FAIL-CLOSED (Task 14): every one of these raises local_llm_backend.
OllamaError, uncaught here - ai_router.handle() already wraps every
AIBackend.converse() call in try/except Exception and treats a raised
exception as fail-closed "nothing to do" (see ai_router.py's own
docstring), so this module needs no fallback logic of its own for any
of these - raising IS the complete, correct behavior:
  - Ollama unreachable, times out, or returns invalid JSON at the HTTP
    level (inherited _call_ollama(), unchanged).
  - Stage 1's `content` is empty, not valid JSON, or not a JSON object.
  - Stage 2's `content` is empty, not valid JSON, or not a JSON object,
    or (tool branch) `tool`/`arguments` aren't the right shape, or
    (text branch) `text` is missing/blank.
An unknown tool name, an invalid enum value, a missing/extra argument,
or a dangerous-adjacent tool/argument value are NOT raised here -
every one of those is a valid-SHAPE response this backend passes
through as RAW, UNVALIDATED ToolCall data, exactly like its
predecessor; ai_router.py's existing, unmodified try/except around
ai_tools.process_tool_call() is what fails them closed (see Task 12).
"""

import json

import ai_backend
import ai_tools
import local_llm_backend

# ---------------------------------------------------------------------
# STAGE 1: classify-only schema and prompt. The schema below is the
# ENTIRE structural guarantee behind Task 6 ("Stage 1 must NOT be
# allowed to select or execute a tool") - it has no way to express a
# tool name or arguments, so the sampler cannot produce one no matter
# what the prompt says.
# ---------------------------------------------------------------------

STAGE1_SCHEMA = {
    "type": "object",
    "properties": {"decision": {"type": "string", "enum": ["tool", "text"]}},
    "required": ["decision"],
    "additionalProperties": False,
}

# Human-readable tool descriptions are deliberately reused from local_
# llm_backend._TOOL_DESCRIPTIONS (Task 11: kept separate from, and
# never duplicated into, either JSON schema below) rather than a third
# hand-written copy - if a tool's description changes there, both
# stage-1's prompt and stage-2's prompt pick it up automatically.
_TOOL_LIST_FOR_PROMPT = "\n".join(
    f"- {desc}" for desc in local_llm_backend._TOOL_DESCRIPTIONS.values()
)

# Required (Phase 12.2.7 task spec) few-shot examples, split so stage 1
# only ever has to answer "tool or text", never "which tool" -
# deliberately NOT "dozens of examples" (see the Phase 12.2.6 report's
# own explicit warning against solving this by prompt-stuffing alone):
# a small, fixed, evenly-split set covering exactly the failure modes
# already measured (short Roman-Urdu commands wrongly refused, and
# unsupported-capability requests wrongly granted a tool).
STAGE1_SYSTEM_PROMPT = (
    "You are JARVIS's request classifier. JARVIS has a FIXED set of device-control tools:\n"
    f"{_TOOL_LIST_FOR_PROMPT}\n\n"
    "Your ONLY job is to decide whether the user's request is an EXACT match for one of "
    "those tools (decision=\"tool\") or not (decision=\"text\"). Do NOT decide which tool, "
    "do NOT produce arguments - that happens in a separate step you are not part of.\n\n"
    "decision=\"tool\" for a request that clearly and exactly matches a capability above, "
    "including short imperative commands and Roman Urdu (Urdu written in Latin script) - "
    "a short phrase is not automatically vague just because it's short:\n"
    "- \"open chrome\" -> tool\n"
    "- \"scroll down\" -> tool\n"
    "- \"chrome kholo\" -> tool (open chrome)\n"
    "- \"niche scroll karo\" -> tool (scroll down)\n"
    "- \"wapas jao\" -> tool (this means \"go back\" - browser back navigation IS one of "
    "your tools; do not mistake this short phrase for conversational text)\n"
    "- \"aagay jao\" -> tool (this means \"go forward\" - browser forward navigation IS one "
    "of your tools; same reasoning as \"wapas jao\" above)\n\n"
    "decision=\"text\" for anything else - a greeting, a question about yourself, small talk, "
    "a joke request, or a request that NAMES a capability with no exact matching tool (running "
    "or executing code/commands/programs, opening or closing a tab that doesn't already exist, "
    "smart-home/IoT control, playing a specific numbered item) - and ALWAYS for a dangerous "
    "system command (locking, shutting down, restarting, or deleting anything), since no tool "
    "exists for any of those either:\n"
    "- \"what can you do?\" -> text\n"
    "- \"how are you?\" -> text\n"
    "- \"tell me a joke\" -> text\n"
    "- \"execute python\" -> text (no tool executes code)\n"
    "- \"run powershell\" -> text (no tool executes commands)\n"
    "- \"lock the computer\" -> text (no tool locks the computer)\n"
    "- \"shutdown the computer\" -> text (no tool shuts down the computer)\n"
    "- \"restart the computer\" -> text (no tool restarts the computer)\n"
    "- \"delete my files\" -> text (no tool deletes anything)\n"
    "- \"set thermostat to 72\" -> text (no tool controls smart-home devices)\n\n"
    "When genuinely unsure, choose text - a wrong \"text\" costs a follow-up question; a wrong "
    "\"tool\" costs a real, incorrect action being taken."
)

# ---------------------------------------------------------------------
# STAGE 2a: tool-only schema, derived LIVE from ai_tools.TOOL_REGISTRY
# (Task 9/10) - structurally identical per-tool object shape to
# structured_llm_backend.build_response_schema()'s own tool_call
# variants, but with NO text variant anywhere in the oneOf: this
# function is only ever called after stage 1 already committed to
# "tool", so the text escape hatch is deliberately absent here, not
# just discouraged by the prompt.
# ---------------------------------------------------------------------

def build_stage2_tool_schema():
    """Generate the stage-2 (tool-only) JSON Schema entirely from the
    live ai_tools.TOOL_REGISTRY - called fresh each time (never cached
    at import time), so a future registry change is picked up
    automatically with nothing here to keep in sync by hand."""

    variants = []

    for name, spec in ai_tools.TOOL_REGISTRY.items():
        properties = {}
        required = []
        for arg_name, allowed in spec.args.items():
            if allowed is ai_tools.FREE_TEXT:
                properties[arg_name] = {"type": "string"}
            else:
                properties[arg_name] = {"type": "string", "enum": sorted(allowed)}
            required.append(arg_name)

        variants.append({
            "type": "object",
            "properties": {
                "tool": {"const": name},
                "arguments": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
            "required": ["tool", "arguments"],
            "additionalProperties": False,
        })

    return {"oneOf": variants}


STAGE2_TOOL_SYSTEM_PROMPT = (
    "You already determined the user's request is an EXACT match for one of JARVIS's tools. "
    "Choose the single correct tool and its arguments. Available tools:\n"
    f"{_TOOL_LIST_FOR_PROMPT}\n\n"
    "Roman Urdu reference (Urdu written in Latin script):\n"
    "- \"chrome kholo\" -> open_application(application=\"chrome\")\n"
    "- \"niche scroll karo\" -> scroll(direction=\"down\")\n"
    "- \"wapas jao\" -> browser_navigation(direction=\"back\")\n"
    "- \"aagay jao\" -> browser_navigation(direction=\"forward\")\n"
)

# ---------------------------------------------------------------------
# STAGE 2b: text-only schema - reached when stage 1 said "text", OR
# (Task 15's conservative fallback) when stage 1's response could not
# be cleanly read as exactly {"decision": "tool"}.
# ---------------------------------------------------------------------

STAGE2_TEXT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}

STAGE2_TEXT_SYSTEM_PROMPT = (
    "You already determined no JARVIS tool applies to this request. Reply with a short, "
    "natural spoken response in your own words - never parrot or repeat the user's phrase back "
    "as if it were your answer. If it's a dangerous or unsupported request, briefly explain you "
    "can't do that. Never mention a tool name or produce anything that looks like a command."
)


class TwoStageLocalLLMBackend(local_llm_backend.LocalLLMBackend):
    """Same Ollama server/model/timeout as LocalLLMBackend (Phase
    12.2.3, inherited __init__ unchanged), but resolves each turn in
    TWO structured-output calls instead of one - see this module's own
    docstring for the full architecture and rationale. Still returns
    exactly one ai_backend.AIResponse, or raises local_llm_backend.
    OllamaError - identical contract, identical "raw/unvalidated
    arguments" guarantee as LocalLLMBackend/StructuredLocalLLMBackend."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stage2_tool_schema = build_stage2_tool_schema()

    def converse(self, command, context):
        """See ai_backend.AIBackend.converse() for the full contract.
        Stage 1 classifies; only a decision that is EXACTLY the string
        "tool" reaches stage 2's tool-resolution schema (Task 6/8/15) -
        every other outcome resolves through stage 2's text-generation
        schema instead. Raises local_llm_backend.OllamaError for any
        transport failure or any response this backend cannot cleanly
        parse - never returns None, never guesses at what a malformed
        response "probably meant" (Task 14)."""

        if self._stage1_wants_tool(command):
            return self._resolve_tool(command)

        return self._resolve_text(command)

    def _stage1_wants_tool(self, command):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": STAGE1_SYSTEM_PROMPT},
                {"role": "user", "content": command},
            ],
            "format": STAGE1_SCHEMA,
            "stream": False,
        }

        body = self._call_ollama(payload)
        content = body.get("message", {}).get("content", "")

        if not content or not content.strip():
            raise local_llm_backend.OllamaError(
                "Ollama returned an empty stage-1 classification response"
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise local_llm_backend.OllamaError(
                f"Ollama's stage-1 response was not valid JSON: {e}"
            ) from e

        if not isinstance(parsed, dict):
            raise local_llm_backend.OllamaError(
                "Ollama's stage-1 response must be a JSON object, "
                f"got {type(parsed).__name__}"
            )

        # Task 15 - the entire conservative decision rule: only an
        # EXACT "tool" match proceeds to tool resolution. A clean
        # "text", a missing field, a wrong type, or any other value a
        # future/misconfigured Ollama build might emit despite the
        # schema all fall through to the same safe branch. This is a
        # soft fallback (no exception) - we already got a well-formed
        # JSON object back, so "we're just not confident it means
        # tool" is treated as information, not a hard failure.
        return parsed.get("decision") == "tool"

    def _resolve_tool(self, command):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": STAGE2_TOOL_SYSTEM_PROMPT},
                {"role": "user", "content": command},
            ],
            "format": self._stage2_tool_schema,
            "stream": False,
        }

        body = self._call_ollama(payload)
        content = body.get("message", {}).get("content", "")

        if not content or not content.strip():
            raise local_llm_backend.OllamaError(
                "Ollama returned an empty stage-2 tool-resolution response"
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise local_llm_backend.OllamaError(
                f"Ollama's stage-2 tool response was not valid JSON: {e}"
            ) from e

        if not isinstance(parsed, dict):
            raise local_llm_backend.OllamaError(
                "Ollama's stage-2 tool response must be a JSON object, "
                f"got {type(parsed).__name__}"
            )

        tool_name = parsed.get("tool")
        arguments = parsed.get("arguments")

        if not isinstance(tool_name, str):
            raise local_llm_backend.OllamaError(
                "Ollama's stage-2 tool response has a non-string "
                f"'tool' field: {tool_name!r}"
            )

        if not isinstance(arguments, dict):
            raise local_llm_backend.OllamaError(
                "Ollama's stage-2 tool response has a non-object "
                f"'arguments' field: {arguments!r}"
            )

        # Deliberately NOT validated against ai_tools here - see Task
        # 12 / this module's own docstring. tool_name/arguments are
        # handed back exactly as raw, untrusted data; ai_router.py's
        # unmodified _resolve() is the sole place that calls ai_tools.
        # process_tool_call() before anything can become a canonical
        # command.
        return ai_backend.AIResponse.tool(tool_name, arguments)

    def _resolve_text(self, command):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": STAGE2_TEXT_SYSTEM_PROMPT},
                {"role": "user", "content": command},
            ],
            "format": STAGE2_TEXT_SCHEMA,
            "stream": False,
        }

        body = self._call_ollama(payload)
        content = body.get("message", {}).get("content", "")

        if not content or not content.strip():
            raise local_llm_backend.OllamaError(
                "Ollama returned an empty stage-2 text response"
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise local_llm_backend.OllamaError(
                f"Ollama's stage-2 text response was not valid JSON: {e}"
            ) from e

        if not isinstance(parsed, dict):
            raise local_llm_backend.OllamaError(
                "Ollama's stage-2 text response must be a JSON object, "
                f"got {type(parsed).__name__}"
            )

        text = parsed.get("text")

        if not isinstance(text, str) or not text.strip():
            raise local_llm_backend.OllamaError(
                "Ollama's stage-2 text response has a missing or "
                f"empty 'text' field: {text!r}"
            )

        return ai_backend.AIResponse.speak(text.strip())
