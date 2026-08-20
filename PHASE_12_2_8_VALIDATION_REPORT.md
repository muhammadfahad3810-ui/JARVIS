# Phase 12.2.8 — Production Hardening & Final Validation Report

**Date:** 2026-08-20
**HEAD at start and end of this phase:** `bdbf092` — "Phase 12.2.7: add two-stage local LLM backend" (unchanged; nothing committed this phase)
**Scope:** Verify and strengthen Phase 12.2.7's `TwoStageLocalLLMBackend` implementation. No production behavior files (`ai_tools.py`, `ai_router.py`, `commands.py`, `two_stage_llm_backend.py`, `jarvis.py`) were modified — only new regression tests were added, because inspection found no defect requiring a code change.

---

## 1. Files changed

| File | Change |
|---|---|
| `tests/test_commands.py` | +1 test: `test_ai_layer_disabled_never_calls_ai_router_handle_at_all` |
| `tests/test_ai_startup_wiring.py` | +1 test: `test_real_backend_construction_failure_via_broken_registry_fails_closed` |

No other files changed. `src/ai_tools.py`, `src/ai_router.py`, `src/commands.py`, `src/two_stage_llm_backend.py`, `src/jarvis.py`, `src/config.py` are all byte-for-byte identical to `bdbf092`. `git status --short` confirms only the two test files above are modified; nothing is staged or committed.

`config.py`: `ENABLE_AI_LAYER = False` (unchanged, verified below).

---

## 2. Architecture verification

**Registration gating (Task 2/3).** `jarvis._initialize_ai_backend()`:
```python
if not config.ENABLE_AI_LAYER:
    ai_backend.register_backend(None)
    return
try:
    backend = two_stage_llm_backend.TwoStageLocalLLMBackend()
except Exception:
    ai_backend.register_backend(None)
    return
ai_backend.register_backend(backend)
```
- `ENABLE_AI_LAYER=False` → explicitly registers `None` (clears any leftover state) and returns before `TwoStageLocalLLMBackend` is ever constructed. Verified live: `test_ai_disabled_backend_is_not_registered`, `test_ai_disabled_clears_a_previously_registered_backend`, `test_ai_disabled_never_instantiates_structured_backend`.
- `ENABLE_AI_LAYER=True` → constructs and registers exactly once. Verified: `test_ai_enabled_registers_structured_local_llm_backend_exactly_once`, `test_ai_enabled_constructs_backend_exactly_once`.
- Construction never makes a network call (only reads `ai_tools.TOOL_REGISTRY` to build the Stage-2 schema): `test_ai_enabled_backend_init_makes_no_network_call`.

**Router consultation gating (Task 3).** `commands.py`'s *only* call site of `ai_router.handle()` is guarded by `if config.ENABLE_AI_LAYER:` (unmodified since Phase 12.1). New test added this phase, `test_ai_layer_disabled_never_calls_ai_router_handle_at_all`, patches `ai_router.handle` directly (not a registered backend) and asserts zero calls with the flag at its default — this is a stronger, more direct proof of the guard itself than the pre-existing "registered backend not consulted" tests, since it can't be masked by a coincidentally-absent backend registration.

**Two-stage decision flow**, unchanged from Phase 12.2.7:
- Stage 1: Ollama call constrained to `{"decision": "tool"|"text"}` only — structurally cannot select a tool or arguments.
- Conservative rule: only an exact `{"decision": "tool"}` proceeds to Stage 2's tool schema; every other outcome (including malformed-but-parseable data) defaults to the text branch.
- Stage 2 (tool branch): schema built live from `ai_tools.TOOL_REGISTRY` each call, closed `oneOf`, no text variant present.
- Stage 2 (text branch): a real generation call, never a canned string.

---

## 3. Security verification

**Task 5 — closed `TOOL_REGISTRY` cannot produce arbitrary shell commands.**
Live registry contents (`sorted(ai_tools.TOOL_REGISTRY.keys())`):
```
browser_navigation, media, mouse_action, open_application, press_key,
refresh, scroll, search, tab_navigation, volume
```
No tool executes a shell command, PowerShell command, arbitrary Python, or unrestricted browser automation — `open_application`/`press_key`/etc. only ever render one of a small set of fixed, pre-existing canonical strings (`"open chrome"`, `"press enter"`, ...) that the deterministic dispatch chain already handles identically to a typed/spoken command. Verified by pre-existing, unmodified `tests/test_ai_tools.py`:
- `test_dangerous_action_tool_names_are_all_unknown` — `run_shell`, `run_powershell`, `execute_python`, `exec`, `eval`, `os_system`, `subprocess_run`, `shutdown_computer`, `lock_computer`, `restart_computer`, `delete` are all `UnknownToolError`.
- `test_hostile_application_values_are_all_rejected` — shell-metacharacter/path-traversal-looking `application` values (`cmd.exe & del ...`, `` `whoami` ``, `$(whoami)`, `../../../windows/system32`, etc.) are all `InvalidArgumentValueError`.
- `test_search_accepts_shell_looking_queries_as_plain_text` — shell-looking search queries are only ever URL-encoded into a Google search link, never executed.
- `test_module_imports_no_control_module_no_voice_no_execution_primitive` — `ai_tools.py` itself imports no `subprocess`/`os`/`ctypes`/`eval`/`exec`.

Also directly re-verified this phase: `test_registry_structurally_cannot_render_dangerous_commands` (from Phase 12.2.7) exhaustively renders every enum combination of every registered tool against the live registry and confirms none equals `"lock computer"`/`"shutdown computer"`/`"restart computer"`.

**Task 6 — `TwoStageLocalLLMBackend` never directly executes a tool.**
- `test_module_never_imports_dangerous_capabilities` — no `subprocess`/`os`/`ctypes`/`voice`/any control module import, no `eval(`/`exec(`, checked against the module's actual source.
- Both `converse()` code paths only ever `return ai_backend.AIResponse.tool(...)` or `AIResponse.speak(...)` — inert data, never a call.

**Task 7 — `ai_tools` remains the sole validation authority.**
- `test_module_never_calls_ai_tools_validate_or_process_itself` (AST-walk, not substring match, so it can't false-positive on the module's own docstring prose) — confirms no call node in the module targets `validate_tool_call`, `process_tool_call`, or `resolve_to_canonical_command`.
- Every `AIResponse.tool(...)` this backend returns carries raw, unvalidated `tool_name`/`arguments`; `ai_router.py`'s unmodified `_resolve()` is the only code path in the codebase that calls `ai_tools.process_tool_call()`.
- Unknown tool / invalid enum / missing argument / extra argument / dangerous-enum-smuggled-into-a-real-tool are all proven to fail closed *through the real, unmodified router*, not by the backend itself: `test_backend_passes_through_invalid_tool_name_raw_and_router_rejects_it`, `test_invalid_enum_is_passed_through_raw_and_router_rejects_it`, `test_missing_argument_is_passed_through_raw_and_router_rejects_it`, `test_extra_argument_is_passed_through_raw_and_router_rejects_it`, `test_dangerous_enum_value_smuggled_into_a_real_tool_fails_closed`, `test_hallucinated_dangerous_tool_name_fails_closed_via_router`.

**Task 8 — deterministic/security behavior unchanged.** Confirmed by full regression (below): 1508/1508. `ai_tools.py`, `ai_router.py`, `commands.py` untouched this phase.

---

## 4. Regression coverage added/confirmed (Task 4)

Every category requested was already covered by Phase 12.2.7's 54-test `test_two_stage_llm_backend.py` plus the pre-existing `test_ai_startup_wiring.py`/`test_ai_tools.py`/`test_commands.py` suites. This phase closed two precise gaps against the task's literal wording rather than duplicating existing coverage:

| Requirement | Status | Test(s) |
|---|---|---|
| AI disabled by default | pre-existing | `test_ai_disabled_backend_is_not_registered`, `test_ai_layer_disabled_by_default_never_consults_any_backend` |
| Deterministic commands never reach the LLM | pre-existing | `test_deterministic_commands_never_reach_the_startup_registered_backend`, `test_deterministic_command_never_reaches_this_backend_via_router` |
| Guard on `ai_router.handle()` itself | **new** | `test_ai_layer_disabled_never_calls_ai_router_handle_at_all` |
| Backend construction failure fails closed (mocked) | pre-existing | `test_backend_initialization_failure_{still_starts_jarvis,registers_nothing,does_not_propagate}` |
| Backend construction failure fails closed (real code path) | **new** | `test_real_backend_construction_failure_via_broken_registry_fails_closed` |
| Malformed Stage-1 output | pre-existing | `test_stage1_non_json_content_raises_ollama_error`, `..._json_array...`, `..._empty_content...`, `..._missing_message_key...`, plus the conservative-fallback tests |
| Malformed Stage-2 output | pre-existing | `test_stage2_tool_{non_json_content,missing_tool_field,non_object_arguments,content_that_is_a_json_array,empty_content}_raises_ollama_error`, `test_stage2_text_{missing_text_field,blank_text,non_string_text}_raises_ollama_error` |
| Unknown tool | pre-existing | `test_backend_passes_through_invalid_tool_name_raw_and_router_rejects_it` |
| Invalid enum | pre-existing | `test_invalid_enum_is_passed_through_raw_and_router_rejects_it` |
| Dangerous/nonexistent tool attempts | pre-existing | `test_hallucinated_dangerous_tool_name_fails_closed_via_router`, `test_dangerous_enum_value_smuggled_into_a_real_tool_fails_closed` |
| Text/refusal responses | pre-existing | `test_valid_text_classification_and_generation`, `test_dangerous_prompt_resolved_as_text_never_reaches_tool_schema`, `test_arbitrary_shell_command_prompt_resolved_as_text`, `test_arbitrary_python_execution_prompt_resolved_as_text` |
| Backend timeout/connection failure | pre-existing | `test_stage1_ollama_{connection_failure,timeout}_raises_ollama_error`, `test_stage2_ollama_{connection_failure,timeout}_raises_ollama_error` |
| Empty/malformed Ollama response | pre-existing | `test_stage1_empty_content_raises_ollama_error`, `test_stage1_missing_message_key_raises_ollama_error`, `test_stage2_tool_empty_content_raises_ollama_error` |

---

## 5. Focused test count

```
pytest tests/test_two_stage_llm_backend.py tests/test_ai_tools.py tests/test_ai_backend.py tests/test_ai_router.py tests/test_ai_startup_wiring.py -q
136 passed (135 pre-existing + 1 new)
```

## 6. Full regression count

```
pytest tests/ -q
1508 passed (1506 pre-existing + 2 new)
```

## 7. Failures

None.

## 8. Final recommendation

**PASS.**

- `ENABLE_AI_LAYER` confirmed `False` in `src/config.py` (unchanged from `bdbf092`).
- Registration and router-consultation gating verified both observationally (spy backends never called) and structurally (the guard itself, and the real `TwoStageLocalLLMBackend()` construction path under a corrupted registry, both directly tested this phase).
- `ai_tools.TOOL_REGISTRY` is confirmed to contain no shell/PowerShell/Python-execution/unrestricted-browser-automation capability, exhaustively swept against dangerous canonical strings.
- `TwoStageLocalLLMBackend` is confirmed to never import an execution primitive and never call `ai_tools` validation itself (AST-verified) — `ai_router.py`'s unmodified `_resolve()` remains the sole validation authority.
- Deterministic-first routing and the existing security/dangerous-command architecture are unchanged and fully covered by the passing full regression suite.
- Nothing was committed; no live dangerous command was executed; no new capability (shell/PowerShell/filesystem/unrestricted browser automation) was added.
