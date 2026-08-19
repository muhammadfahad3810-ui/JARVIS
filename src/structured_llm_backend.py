"""Phase 12.2.4: Structured Output Enforcement.

Adds StructuredLocalLLMBackend, a variant of Phase 12.2.3's
LocalLLMBackend that asks Ollama to grammar-constrain its ENTIRE
response to a JSON Schema generated from ai_tools.TOOL_REGISTRY (
Ollama's `format` structured-output field: POST /api/chat with
format=<schema>, stream=False), instead of relying on native
tool-calling (`tools=[...]`) alone.

WHY: native tool-calling (Phase 12.2.3) asks the model to choose
correctly; structured output makes the token sampler itself unable to
emit anything outside the schema's shape - an unknown tool name, a
wrong/extra/missing argument name, or an enum value outside a tool's
allow-list becomes a grammar violation the sampler cannot produce,
not just a mistake the model might make. This is a CORRECTNESS/
reliability improvement only - see SAFETY below for why the security
model is completely unchanged.

SAFETY - nothing about the Phase 12.1/12.2.3 security model changes:

- ai_tools.validate_tool_call()/process_tool_call() remain the ONLY
  authority over what becomes a canonical command. Every response
  this backend produces - however structurally constrained by Ollama
  - is still handed back as an ai_backend.AIResponse carrying RAW,
  UNVALIDATED arguments, exactly like LocalLLMBackend. This module
  never calls ai_tools.validate_tool_call() itself and never treats
  schema conformance as a substitute for it. If a future or
  misconfigured Ollama build ignores `format` entirely (or only
  partially honors it), this backend degrades to "LocalLLMBackend
  that reads .content as JSON instead of .tool_calls" - it does NOT
  degrade the security boundary, because there isn't a security
  boundary here to degrade: ai_router.py's re-validation is
  unconditional regardless of what this module returns.
- Nothing here can even name a dangerous command. build_response_
  schema() below is generated from the exact same ai_tools.
  TOOL_REGISTRY every other AI-facing schema in this project reads -
  the same structural absence of shutdown/restart/lock/delete-key/
  shell-execution applies here as it does to build_tool_schema() in
  local_llm_backend.py. Verified directly by this module's own tests
  (test_structured_llm_backend.py), not just claimed here.
- NOT registered anywhere in production code. Nothing here calls
  ai_backend.register_backend() and nothing here reads or changes
  config.ENABLE_AI_LAYER (still False - see config.py). Constructing a
  StructuredLocalLLMBackend has zero effect on live JARVIS behavior.
- local_llm_backend.py (Phase 12.2.3, already validated) is not
  modified by this module at all - this file only ADDS a new,
  independently-tested class that subclasses LocalLLMBackend and
  reuses its __init__/_call_ollama unchanged.
- Same as LocalLLMBackend: never imports voice, any control module,
  subprocess, os.system, or ctypes, and never calls CommandProcessor.
  process() - it can only ever return an ai_backend.AIResponse or
  raise local_llm_backend.OllamaError.
"""

import json

import ai_backend
import ai_tools
import local_llm_backend


def build_response_schema():
    """Generate a JSON Schema, entirely from ai_tools.TOOL_REGISTRY,
    for Ollama's structured-output `format` field to grammar-
    constrain generation to. A closed `oneOf`: one exact object shape
    per registered tool (the tool name pinned via `const`, arguments
    matching that tool's own required names/types/closed-enum values
    exactly, `additionalProperties: false` so no extra argument can
    even be generated), plus one exact shape for a plain-text
    response. Every tool name, argument name, and allowed enum value
    is READ from TOOL_REGISTRY - nothing here hand-copies or
    independently re-derives what build_tool_schema() in local_llm_
    backend.py already reads the same way from the same registry."""

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
                "response_type": {"const": "tool_call"},
                "tool": {"const": name},
                "arguments": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
            "required": ["response_type", "tool", "arguments"],
            "additionalProperties": False,
        })

    variants.append({
        "type": "object",
        "properties": {
            "response_type": {"const": "text"},
            "text": {"type": "string"},
        },
        "required": ["response_type", "text"],
        "additionalProperties": False,
    })

    return {"oneOf": variants}


class StructuredLocalLLMBackend(local_llm_backend.LocalLLMBackend):
    """Same Ollama server/model/timeout as LocalLLMBackend (Phase
    12.2.3, inherited __init__ unchanged), but asks Ollama to grammar-
    constrain the ENTIRE response to build_response_schema() via the
    `format` field instead of relying on native tool-calling (`tools=
    [...]`) alone. Still returns exactly one ai_backend.AIResponse, or
    raises local_llm_backend.OllamaError - identical contract,
    identical failure semantics, identical "raw/unvalidated
    arguments" guarantee as its parent class (see this module's own
    docstring)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._response_schema = build_response_schema()

    def converse(self, command, context):
        """See ai_backend.AIBackend.converse() for the full contract
        (identical to LocalLLMBackend.converse()'s). Sends `command`
        to Ollama with the same fixed system prompt as LocalLLMBackend
        and `format=build_response_schema()` instead of `tools=[...]`.
        Parses the (schema-constrained, but still treated as
        untrusted) JSON in the response's `content` field into exactly
        one AIResponse - a ToolCall carrying RAW, UNVALIDATED
        arguments if response_type is "tool_call", TEXT if it is
        "text". Raises local_llm_backend.OllamaError for anything that
        isn't valid JSON, isn't a JSON object, or doesn't match one of
        those two shapes - never returns None, never guesses at what a
        malformed response "probably meant"."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": local_llm_backend.SYSTEM_PROMPT},
                {"role": "user", "content": command},
            ],
            "format": self._response_schema,
            "stream": False,
        }

        body = self._call_ollama(payload)
        message = body.get("message", {})
        content = message.get("content", "")

        if not content or not content.strip():
            raise local_llm_backend.OllamaError(
                "Ollama returned an empty structured response"
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise local_llm_backend.OllamaError(
                f"Ollama's structured response was not valid JSON: {e}"
            ) from e

        if not isinstance(parsed, dict):
            raise local_llm_backend.OllamaError(
                "Ollama's structured response must be a JSON object, "
                f"got {type(parsed).__name__}"
            )

        response_type = parsed.get("response_type")

        if response_type == "tool_call":
            tool_name = parsed.get("tool")
            arguments = parsed.get("arguments")

            if not isinstance(tool_name, str):
                raise local_llm_backend.OllamaError(
                    "Ollama's structured tool_call response has a "
                    f"non-string 'tool' field: {tool_name!r}"
                )

            if not isinstance(arguments, dict):
                raise local_llm_backend.OllamaError(
                    "Ollama's structured tool_call response has a "
                    f"non-object 'arguments' field: {arguments!r}"
                )

            return ai_backend.AIResponse.tool(tool_name, arguments)

        if response_type == "text":
            text = parsed.get("text")

            if not isinstance(text, str) or not text.strip():
                raise local_llm_backend.OllamaError(
                    "Ollama's structured text response has a missing "
                    f"or empty 'text' field: {text!r}"
                )

            return ai_backend.AIResponse.speak(text.strip())

        raise local_llm_backend.OllamaError(
            "Ollama's structured response has an unrecognized "
            f"response_type: {response_type!r}"
        )
