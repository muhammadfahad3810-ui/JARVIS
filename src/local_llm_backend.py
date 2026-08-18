"""Phase 12.2.3: LocalLLMBackend - a concrete ai_backend.AIBackend that
talks to a local Ollama server's native tool-calling API over HTTP.

NOT registered anywhere in production code by this module. Nothing
here calls ai_backend.register_backend() and nothing here reads or
changes config.ENABLE_AI_LAYER (still False - see config.py). This
module only makes it POSSIBLE for a future phase to wire a real LLM
in; constructing a LocalLLMBackend has zero effect on live JARVIS
behavior until BOTH register_backend() is called AND ENABLE_AI_LAYER
is flipped to True, neither of which happens here.

Built directly on the Phase 12.2.2 benchmark's own findings (a
standalone, scratchpad-only script - never part of this project) and
the Phase 12.2 Roman-Urdu few-shot refinement validated immediately
before this module was written: same model
(qwen2.5:3b-instruct-q4_K_M), same Ollama /api/chat tool-calling
endpoint, same "generate the tool schema from ai_tools.TOOL_REGISTRY,
never hand-copy it" approach.

SAFETY: this module never imports voice, any control module,
subprocess, os.system, or ctypes, and never calls
CommandProcessor.process() - it can only ever return an
ai_backend.AIResponse (a ToolCall carrying RAW, UNVALIDATED
arguments, or plain text), exactly like every AIBackend implementation
must (see ai_backend.py's own docstring). Whatever this module
returns is still independently validated by
ai_tools.validate_tool_call()/process_tool_call() in ai_router.py
before it can ever become a canonical command - this module has no
way to skip that boundary, and does not attempt to pre-validate
anything itself.
"""

import json
import urllib.request

import ai_backend
import ai_tools

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:3b-instruct-q4_K_M"
DEFAULT_TIMEOUT_SECONDS = 30

# The Phase 12.2 refinement's system prompt: the base instructions plus
# a small Roman-Urdu few-shot section. Re-running the 11-case Roman-
# Urdu benchmark with this addition raised CORRECT tool+args from 5/11
# (45%) to 7/11 (64%) - though honest breakdown showed most of that
# gain came from the literal examples below (4/5 correct) rather than
# genuine generalization to unseen Roman-Urdu phrasing (3/6 correct,
# ~50%, barely above the pre-refinement baseline). Kept anyway: it is a
# strict improvement with no observed downside (VALID tool-call rate
# also rose, 73% -> 91%, and no security/malformed-output regression),
# and Roman-Urdu phrases are handled primarily by the deterministic
# multilingual_normalizer.py layer BEFORE ever reaching this backend -
# this prompt only matters for whatever that layer doesn't catch.
SYSTEM_PROMPT = (
    "You are JARVIS, a voice-controlled desktop assistant. "
    "You have access to a fixed set of tools for controlling the computer. "
    "If the user's request clearly matches one of the available tools, call that tool with the correct arguments. "
    "If the request is conversational (a greeting, a question about you, small talk, thanks), respond with plain text - do not call a tool. "
    "If the request is ambiguous, vague, or does not clearly match any available tool (for example it names no specific target, or asks for something dangerous like shutting down, restarting, locking the computer, or running arbitrary commands/code), do NOT call a tool - respond with a short plain-text clarification or refusal instead. "
    "Never invent a tool that is not in your tool list. Never invent an argument value that is not explicitly allowed."
    "\n\nSome requests will be in Roman Urdu (Urdu written in Latin script). "
    "Here are examples of the correct response:\n"
    "- \"chrome kholo\" -> call open_application(application=\"chrome\")\n"
    "- \"naya tab kholo\" -> there is no tool for opening a new browser tab, "
    "so do NOT call a tool for this - respond with plain text instead\n"
    "- \"niche scroll karo\" -> call scroll(direction=\"down\")\n"
    "- \"wapas jao\" -> call browser_navigation(direction=\"back\")\n"
    "- \"aagay jao\" -> call browser_navigation(direction=\"forward\")\n"
)

# Human-readable descriptions ONLY, for the LLM's benefit - never a
# second copy of the actual tool/argument SCHEMA, which
# build_tool_schema() below derives entirely from ai_tools.
# TOOL_REGISTRY. A wrong or missing description here cannot make any
# tool do something it couldn't already do - ai_tools.validate_tool_
# call() enforces the real contract regardless of what this text says.
_TOOL_DESCRIPTIONS = {
    "open_application": "Open a known application or website by name.",
    "press_key": "Press a single fixed keyboard key.",
    "scroll": "Scroll the current window up or down.",
    "mouse_action": "Perform a mouse action: click, double-click, right-click, or move the cursor a small fixed distance in one direction.",
    "volume": "Adjust or mute/unmute the system volume.",
    "media": "Control media playback: play/pause, next track, or previous track.",
    "tab_navigation": "Switch to the next or previous browser tab.",
    "browser_navigation": "Navigate the browser back or forward in history.",
    "refresh": "Refresh (reload) the current browser page. Takes no arguments.",
    "search": "Search the web for a free-text query.",
}


class OllamaError(RuntimeError):
    """Raised for any Ollama-connectivity or malformed-response
    problem - unreachable server, timeout, non-JSON response, or a
    response with neither a tool call nor any text content. Never
    caught inside this module: ai_router.handle() already wraps every
    AIBackend.converse() call in try/except Exception and treats a
    raised exception as fail-closed "nothing to do" (see ai_router.
    py's own docstring), so LocalLLMBackend needs no fallback logic of
    its own - raising IS the complete, correct behavior."""


def build_tool_schema():
    """Generate Ollama's tool-calling schema directly from the live
    ai_tools.TOOL_REGISTRY. Every tool name, argument name, and
    allowed enum value below is READ from the registry, never hand-
    copied - if TOOL_REGISTRY ever changes, this schema changes with
    it automatically, with nothing here to keep in sync by hand."""

    tools = []
    for name, spec in ai_tools.TOOL_REGISTRY.items():
        properties = {}
        required = []
        for arg_name, allowed in spec.args.items():
            if allowed is ai_tools.FREE_TEXT:
                properties[arg_name] = {
                    "type": "string",
                    "description": "Free-text search query.",
                }
            else:
                properties[arg_name] = {
                    "type": "string",
                    "enum": sorted(allowed),
                }
            required.append(arg_name)

        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": _TOOL_DESCRIPTIONS.get(name, ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return tools


class LocalLLMBackend(ai_backend.AIBackend):
    """Talks to a local Ollama server's native tool-calling API
    (POST /api/chat with tools=[...], stream=False). NOT registered
    anywhere in production code - see this module's own docstring."""

    def __init__(self, model=DEFAULT_MODEL, url=DEFAULT_OLLAMA_URL,
                 timeout=DEFAULT_TIMEOUT_SECONDS):
        self.model = model
        self.url = url
        self.timeout = timeout
        self._tools = build_tool_schema()

    def converse(self, command, context):
        """See ai_backend.AIBackend.converse() for the full contract.
        Sends `command` to Ollama with the fixed system prompt and the
        TOOL_REGISTRY-derived tool schema. Returns exactly one
        AIResponse:

        - a ToolCall carrying RAW, UNVALIDATED arguments, if Ollama's
          response includes one or more tool calls (only the FIRST is
          ever used - a real voice assistant acts on one command per
          turn; extras are silently ignored, never merged or executed
          together);
        - plain TEXT otherwise, if Ollama's response has any non-empty
          content.

        Raises OllamaError - never returns None, never returns
        anything that isn't an AIResponse - if Ollama can't be
        reached, doesn't respond in time, returns something that isn't
        valid JSON, or returns neither a tool call nor any text
        content (an observed real failure mode during benchmarking:
        the model occasionally generates tokens that resolve to
        neither)."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": command},
            ],
            "tools": self._tools,
            "stream": False,
        }

        body = self._call_ollama(payload)
        message = body.get("message", {})
        tool_calls = message.get("tool_calls") or []
        content = message.get("content", "")

        if tool_calls:
            call = tool_calls[0].get("function", {})
            tool_name = call.get("name")
            arguments = call.get("arguments") or {}
            return ai_backend.AIResponse.tool(tool_name, arguments)

        if content.strip():
            return ai_backend.AIResponse.speak(content.strip())

        raise OllamaError(
            "Ollama returned neither a tool call nor any text content"
        )

    def _call_ollama(self, payload):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except OSError as e:
            raise OllamaError(f"could not reach Ollama at {self.url}: {e}") from e

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise OllamaError(f"Ollama returned invalid JSON: {e}") from e
