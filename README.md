# JARVIS v2

A local, offline-triggered voice assistant for Windows. Listens for the wake
word "Jarvis", recognizes speech via Google's speech recognition API, and
executes a small set of commands (launching apps, opening web pages,
telling the time/date, and basic system power actions).

## Requirements

- Python 3.11.9
- A working microphone
- Windows (system/application commands use Windows-specific executables)

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```
python src\jarvis.py
```

Say "Jarvis" and then a command, e.g. "Jarvis open Chrome", or say "Jarvis"
alone and wait for "Yes?" before speaking your command.

## Speech recognition architecture

The voice pipeline, as it actually stands after Phase 10.5:

```
microphone → speech.py (Google online STT, offline Whisper fallback - Phase 10.1)
  → wake-word extraction (jarvis.py)
  → commands.CommandProcessor.process()
       1. pending dangerous-confirmation reply         (Phase 9)
       2. pending context/slot reply                    (Phase 10.3)
       3. dangerous-command confirmation gate            (Phase 9)
       4. natural-language clause splitting              (Phase 8)
       5. command_parser.normalize()
       6. fixed deterministic dispatch chain              (Phase 3-7)
       7. rule-based intent fallback                      (Phase 10.2)
            + pending-slot creation (follow-up question)   (Phase 10.3)
       8. contextual reference / repeat-search resolution (Phase 10.4/10.5)
       9. "I don't know how to do that yet."
  → action module (web/system/window/volume/media/screen/keyboard)
  → voice.py (pyttsx3 text-to-speech)
```

Every stage is deterministic - no LLM or AI service is used anywhere in
this pipeline, in any phase. Every flag-gated stage above (2, 3, 7, 8)
defaults **off**; with all of them off, the pipeline is exactly steps
1 (dead code, `_pending_confirmation` never set) → 5 → 6 → 9, i.e.
byte-for-byte the same behavior this project has had since Phase 7.

1. **`speech.Speech.calibrate_microphone()`** runs once at startup. It
   listens to ambient room noise for `config.AMBIENT_NOISE_DURATION`
   seconds and uses it to set a better starting `energy_threshold`.
   `dynamic_energy_threshold` (already on) keeps adapting after that.
   This never blocks startup - if no microphone is available, it's
   skipped with a printed warning, not a crash.
2. **`speech.Speech.listen()`** opens the microphone, records up to
   `phrase_limit` seconds (or until silence, per `pause_threshold`), and
   sends the captured audio to the backend abstraction in
   `stt_backend.py` (Phase 10.1) - `GoogleOnlineBackend.recognize()`
   (the original `recognize_google()` call, unchanged) is always tried
   first.
   - If the online backend fails with a transient error, it is
     retried up to `config.SPEECH_API_RETRIES` times **on the same
     captured audio** (no need to make the user repeat themselves) with
     `config.SPEECH_API_RETRY_DELAY` seconds between attempts. Only
     after all retries fail is "I am having trouble connecting to
     speech recognition." spoken - and at most once every
     `config.REQUEST_ERROR_ANNOUNCE_COOLDOWN` seconds, so a prolonged
     outage doesn't repeat the announcement on every listen cycle.
   - Either way (unintelligible audio or a network failure after
     retries), `OfflineWhisperBackend` is then tried as a fallback -
     but it has no `faster_whisper` installed, so `is_available()`
     reports `False` and this is a documented, tested, inert no-op in
     this project's current state (see "Phase 10.1" below).
   - `UnknownValueError`-equivalent (heard something, couldn't
     transcribe it) and `WaitTimeoutError` (heard nothing) both just
     return `""` - no announcement, no crash, no retry (see
     `listen_with_retry` below for where retrying-by-re-listening
     happens instead).
   - Any other microphone error (e.g. no device present) is caught
     broadly and also returns `""`.
3. **`speech.Speech.listen_with_retry()`** wraps `listen()` and is used
   specifically for the command capture *after* JARVIS says "Yes?" - if
   nothing was understood, it speaks "Sorry, I didn't catch that. Please
   repeat." and listens again, up to `config.COMMAND_RECOGNITION_RETRIES`
   extra times. This is *not* used for the idle wake-word-listening loop
   itself (that already retries implicitly, every ~0.2s, by design - see
   below), so JARVIS doesn't talk to itself over background noise.
4. **Wake-word extraction (`jarvis.extract_command_after_wake_word`)**
   matches the wake word as a **whole word** via regex (`\bjarvis\b`),
   not a bare substring - so words that merely *contain* "jarvis" (e.g.
   "jarvison") are correctly not treated as activation. It also strips
   any *immediately repeated* wake words ("jarvis jarvis open chrome" →
   "open chrome").
5. **`command_parser.normalize()`** rewrites natural-language variations
   into the canonical phrasing the handlers already understand (see
   "Natural-language command understanding" below for what's new in
   Phase 5).
6. **`intent_parser.classify()`** (new in Phase 5) additionally
   classifies the normalized text into one of a small, fixed set of
   `Intent` values, purely for diagnostics and as a directly-testable
   security boundary - see below.

## Natural-language command understanding (Phase 5)

`command_parser.py` remains the single source of truth for rewriting
messy natural language into the canonical strings the handler modules
already understand - it was extended, not replaced, in this phase:

- **Stacked politeness wrappers are now fully unwrapped.**
  `strip_filler()` used to run through its prefix/suffix list exactly
  once, so "could you please launch YouTube" was only partly cleaned up
  (the "could you" layer was stripped, but the newly-exposed leading
  "please" was left behind, which then blocked the "launch" → "open"
  rewrite). It now repeats until nothing more changes, so any stack of
  "could you" / "can you" / "would you" / "will you" / "please" /
  "... for me" / "... please" wrappers is fully removed.
- **New filler phrase:** "I want you to `<command>`".
- **Volume phrasing was extended**: "louder"/"quieter"/"softer" are now
  recognized alongside "up"/"down"/"increase"/"decrease"/etc, and a
  small, exact-match-only set of pronoun phrases ("turn it up/down",
  "make it louder/quieter/softer") is recognized even with no literal
  "volume"/"mute" word present. These are anchored to the *entire*
  normalized string (`^...$`), so they can only ever fire for that exact
  phrase, never as a fragment inside a longer, unrelated sentence.
- **Three new phrase rewrites**: "show me the desktop" → "show desktop",
  "skip this song"/"skip this track" → "next track", "capture my
  screen"/"capture the screen" → "screenshot".

### `src/intent_parser.py` (new)

A small, self-contained, closed-allow-list classifier: `classify(text)`
returns an `IntentResult(intent, target)` where `intent` is always one
of a fixed set of `Intent` values (never free-form), and `target` - for
the two intents that have one (`OPEN_APPLICATION`, `PRESS_KEY`) - is
always drawn from a fixed allow-list (`KNOWN_APPLICATIONS`,
`KNOWN_KEYS`). Anything not explicitly recognized is `Intent.UNKNOWN`.
`to_canonical_command(result)` renders a result back to the literal
command string the existing handlers expect, or `None` for `UNKNOWN` or
an out-of-allow-list target.

**How it's wired in (and why it can't cause a regression):** by the time
text reaches `intent_parser`, `command_parser.normalize()` has already
rewritten essentially every supported natural-language variation into
its canonical form. `commands.py` calls `intent_parser.classify()`
purely for `config.DEBUG` diagnostics - it does **not** drive routing.
Routing still runs through the exact same dispatch chain
(`web_control.handle()`, `system_control.handle_application()`, etc.)
on the same normalized string as before Phase 5. This means
`intent_parser` can be added, tested, and iterated on with zero risk of
changing behavior for any command that already worked - see
`tests/test_intent_parser.py` for direct unit tests of the classifier
itself (including a round-trip test proving `classify()` →
`to_canonical_command()` reproduces every canonical command exactly),
and `tests/test_security.py` for the allow-list/rejection guarantees.

## Absolute volume & true mute/unmute (Phase 7)

**Status: PHASE 7 COMPLETE.**

Volume up/down remain unchanged since Phase 3 - relative nudges via the
standard Windows multimedia keys (`input_control.py`), one step per
invocation. Everything else volume-related now goes through a new,
small Core Audio wrapper, `src/audio_endpoint.py`, built directly on
`comtypes` (already an installed, declared project dependency - no new
package was added for this phase) against the public
`IMMDeviceEnumerator`/`IMMDevice`/`IAudioEndpointVolume` COM interfaces:

- **True mute/unmute.** "mute" calls
  `IAudioEndpointVolume.SetMute(True, None)`; "unmute" calls
  `SetMute(False, None)`. Both are idempotent - each always produces
  the named state regardless of what the system's mute state already
  was. This replaces the Phase 6-and-earlier behavior, where both
  "mute" and "unmute" pressed the single Windows multimedia
  mute-*toggle* key, so "unmute" while already unmuted would mute the
  system instead.
- **Absolute volume.** "set volume to `<N>` percent" / "set volume to
  `<N>%`" calls `IAudioEndpointVolume.SetMasterVolumeLevelScalar(N/100,
  None)`. Valid range is 0-100 inclusive: 0 -> scalar `0.0`, 40 ->
  scalar `0.4`, 100 -> scalar `1.0`. `command_parser.py` accepts only a
  plain 1-3 digit integer immediately followed by "percent" or "%"
  (case/whitespace variations handled) - negative numbers, values above
  100, huge numeric payloads, decimals, and spelled-out numbers are all
  rejected outright and left completely unrewritten, never clamped to
  the nearest valid value and never passed to the Core Audio setter.
- **No new execution surface.** Setting volume or mute/unmute never
  touches `subprocess.Popen`, `os.system`, or the keyboard-injection
  primitives - verified directly by dedicated tests in
  `tests/test_security.py`.
- **Test isolation.** Every automated test mocks the Core Audio
  boundary at its point of use
  (`volume_control.audio_endpoint.set_volume_percent`/`set_mute`, or
  lower still in `tests/test_audio_endpoint.py`) - no automated test
  ever creates a real `IMMDeviceEnumerator` COM object or touches a
  real audio device. See "Tests" below for the exact verified result.

README documentation was the last outstanding Phase 7 item before this
update - with this update, no further Phase 7 work remains outstanding.

## Phase 8 — Natural Language Intelligence & Conversational Layer

**Status: PHASE 8 COMPLETE.**

`command_parser.py` already *was* JARVIS's natural-language layer,
since Phase 5. Phase 8 extends it with a few new, narrow synonym
rules, plus one genuinely new capability - bounded multi-clause
command splitting (`src/natural_language.py`). Nothing here is a new
AI/NLU system: every rule is a small, explicit, hand-written
regex/substring check, exactly like every existing rule in
`command_parser.py`.

### Architecture

```
speech -> wake-word detection -> speech-to-text
       -> natural_language.split_into_clauses()   (Phase 8, optional)
       -> command_parser.normalize()               (per clause)
       -> commands.CommandProcessor dispatch chain (per clause, unchanged)
       -> existing safe control modules
```

`natural_language.split_into_clauses()` runs first, inside
`CommandProcessor.process()`, before `command_parser.normalize()`. If
the input doesn't cleanly split into multiple *already-known* clauses,
the single, unmodified original command flows through the exact same
code path as before Phase 8 - zero behavior change for any command
that isn't a chain.

### New natural-language examples supported

- "search google for python tutorials" / "search on google for python
  tutorials" -> `search for python tutorials` (previously produced the
  wrong query text, `search for google for python tutorials`)
- "make the volume 40 percent" / "turn the volume to 40 percent" /
  "change the volume to 0 percent" -> `set volume to <N>` (broadens the
  accepted verb/phrasing around the existing Phase 7 absolute-volume
  command; the 0-100 range validation and reject-never-clamp policy
  are completely unchanged)
- "stop the music" / "stop the song" / "stop playing" -> `pause`
  (there is no separate "stop" capability anywhere in this codebase,
  only the existing play/pause toggle, so this maps onto that
  already-supported command rather than inventing a new one)
- "open chrome and search for python" / "open notepad and mute" -
  bounded multi-clause chaining, see below

### Multi-clause chaining (bounded, all-or-nothing)

`src/natural_language.py` can split one utterance into multiple clauses
on "and"/"then", but only commits to the split if **every** resulting
clause independently classifies as an already-known command via
`intent_parser.classify()` (the existing, pure, side-effect-free
allow-list classifier). If even one clause doesn't resolve, the split
is discarded entirely and the original, unsplit text is processed as a
single command instead - exactly as before Phase 8.

This is what keeps ordinary phrases that merely contain the word "and"
safe: "search for bed and breakfast" never gets wrongly split (since
"breakfast" alone isn't a known command), and is instead processed
whole - which already works correctly, since it starts with "search
for". A chain with a dangerous-sounding but unrecognized second clause
("open chrome and delete everything") also never splits; the unsplit
phrase then follows the same "dangerous suffix is discarded" behavior
already true of non-chained commands since Phase 5 (e.g. "close chrome
and then format the c drive").

### Ambiguity handling - conservative by design

Phrases with no deterministic mapping are rejected, never guessed:
"do something", "make it better", "open something", "volume high" all
fall through to the standard "I don't know how to do that" response,
with zero real action of any kind triggered (verified directly by
tests mocking every real action primitive).

**One documented subtlety:** "maybe mute it" *is* handled (it triggers
mute) - not because Phase 8 guesses at it, but because
`canonicalize_volume_phrase()`'s `MUTE_WORD` rule has matched any text
containing the whole word "mute" since Phase 5, predating Phase 8
entirely. This is pre-existing, already-tested behavior that Phase 8
does not and should not change without a proven defect - documented
here so it isn't mistaken for a missed ambiguity case.

### Security boundary (unchanged, extended coverage)

Every guarantee below was true before Phase 8 and remains true,
verified by dedicated tests:

- The natural-language layer never executes shell commands, never
  calls `subprocess.Popen`/`os.system` directly, never touches
  `ctypes`/`user32`/Core Audio/`comtypes` directly, and never sends a
  keyboard-injection primitive directly - `src/natural_language.py`
  and the `command_parser.py` extensions only ever produce or split
  *text*; only the existing, unchanged control modules act on it.
- `natural_language.py` holds no reference to `voice`, `commands`, or
  any control module - it structurally cannot bypass
  `CommandProcessor` or call a handler directly.
- Out-of-range/malformed absolute-volume values (negative, >100, huge
  numeric payloads, decimals, spelled-out numbers) are rejected under
  every new Phase 8 verb form ("make"/"turn"/"change" the volume), not
  just the original Phase 7 "set volume to" form - never clamped,
  never reaching the Core Audio setter.
- A chain can never partially execute an unrecognized/dangerous clause
  - the all-or-nothing split guarantee is enforced at the splitting
  layer and re-verified end-to-end through the real `CommandProcessor`.

See `tests/test_security.py`'s "PHASE 8" section for the full test
list, and `tests/test_natural_language.py` for direct unit coverage of
the splitting module itself.

### Limitations

- No conversational memory/context system was introduced - deliberately
  out of scope for this phase. Every command, chained or not, is still
  evaluated statelessly.
- `intent_parser.classify()` (used to validate chain clauses) doesn't
  cover exit words or greetings, so a chain like "open chrome and exit"
  never splits - it fails closed (processed as one unrecognized phrase)
  rather than being guessed at. This is safe but means such chains
  simply don't work yet.
- Multi-clause splitting only recognizes "and"/"then" as conjunctions;
  no other punctuation or phrasing splits a chain.
- No confirmation/dangerous-command layer was added - Phase 8
  introduces no new dangerous capability, and lock/shutdown/restart
  remain exact-phrase-only, unchanged and un-loosened by any Phase 8
  natural-language rule.

## Phase 9 — Dangerous Command Confirmation

**Status: PHASE 9 COMPLETE.**

Closes the exact gap Phase 8's own "Limitations" section named above:
"lock computer"/"shutdown computer"/"restart computer" have executed
immediately, with no safeguard, since Phase 3. Phase 9 adds an
opt-in confirmation gate in front of those three commands only - no
new dangerous capability is introduced, `system_control.py` is
completely unmodified, and every action the gate can eventually
trigger is one of the same three already-fixed, already-tested
functions that existed before this phase.

### Configuration

`config.REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS` - **default
`False`**. With the default, behavior is byte-for-byte identical to
every prior phase (verified: every pre-existing lock/shutdown/restart
test runs completely unmodified, unpatched, against the real default).
Set to `True` to require confirmation.

### How it works

1. "lock computer" / "shutdown computer" / "restart computer" (plus
   the same politeness-wrapper variations already supported elsewhere,
   e.g. "please lock computer") speaks a confirmation prompt ("Are you
   sure you want to \<action\>? Say yes to confirm.") instead of
   executing, and stores the pending command.
2. The *next* utterance is treated purely as the reply - not split,
   not normalized, not dispatched as a new command. Saying the wake
   word again is required to reply, exactly like any other command;
   `jarvis.py`'s wake-word loop needed no changes.
3. Only "yes"/"confirm"/"confirmed" (an explicit, fixed, whole-word
   allow-list) executes the stored command, via the unmodified
   `system_control.handle_system()`. Anything else - "no", "yeah",
   "sure", "do it", or any unrelated command - cancels: JARVIS says
   "Cancelled.", the pending state is cleared, and nothing executes.

### Mixed dangerous/action phrase protection

A command combining a dangerous phrase with another recognized action
- "lock computer and open chrome", "shutdown computer and search
google", "restart computer and mute" - must never execute the other
action before confirmation, and must never execute it at all even
after confirmation (only the stored dangerous command runs). This
required two non-obvious fixes over the first implementation attempt,
both verified by dedicated tests:

- **Dispatch order.** The confirmation gate must be the very first
  check after the pending-confirmation check - before EXIT, GREETING,
  WEB, WINDOW, VOLUME, everything. `intent_parser.classify("lock
  computer")` is `UNKNOWN` (there is no SYSTEM category in that
  classifier), so `natural_language.split_into_clauses()` correctly
  refuses to split any phrase containing a dangerous command - the
  whole unsplit phrase reaches the single-command dispatch chain as
  one string. An earlier draft placed the gate immediately before the
  `SYSTEM` dispatch step (later than several other branches); with
  that ordering, `web_control.handle()`'s bare `"chrome" in command`
  substring check fired first and opened Chrome before the dangerous
  phrase was ever evaluated.
- **Normalization order.** The gate checks a *lightly*-normalized
  version of the raw command (lowercase + whitespace-collapse only) -
  **not** the output of `command_parser.normalize()`. `normalize()`
  can destroy a dangerous phrase before the gate would ever see it:
  `"restart computer and mute"` normalizes to just `"mute"`
  (`canonicalize_volume_phrase()` rewrites the *entire* string to
  `"mute"` whenever that word appears anywhere in it - a pre-existing
  Phase 5 behavior, not modified by Phase 9). Checking lightly-
  normalized raw text instead means the dangerous phrase is always
  seen intact, regardless of what `normalize()` would later do to the
  rest of the string.

### Development safety incident (disclosed honestly, not hidden)

While verifying the mixed-phrase scenario above with an ad hoc,
non-pytest diagnostic script, the input `"lock computer and open
chrome"` was passed through a real `CommandProcessor` with only
`system_control.os.system` mocked - `web_control`'s
`subprocess.Popen`/`webbrowser.open`/`os.path.exists` were **not**
mocked. Because of the dispatch-order defect above, `web_control.
handle()` matched the bare `"chrome"` substring and **Chrome was
actually launched** on the development machine. Process evidence
(`Get-Process chrome`, two fresh `chrome.exe` processes with matching
start timestamps) confirmed this. No lock, shutdown, or restart
occurred - `system_control.os.system` was correctly mocked and
recorded zero calls. Root cause: the diagnostic script mocked only
the primitives assumed relevant to what was being checked, not every
reachable real-action surface. Corrective action: no further manual
`CommandProcessor` scripts were run for the remainder of this phase;
all subsequent verification used pytest with every real-action
surface mocked (`mock_all_real_actions()` in `tests/test_commands.py`,
and the dedicated Phase 9 section of `tests/test_security.py`), plus
the project's existing strict safety-net backstop across the full
suite, which reported zero real/patched-through calls on the final run.

### Security guarantees

- No new execution primitive: `commands.py`'s confirmation logic
  contains no `subprocess`, `ctypes`, `comtypes`, `eval(`, or `exec(`,
  and never calls `os.system` directly - only the pre-existing,
  unmodified `system_control.handle_system()` can.
- Confirmation state (`self._pending_confirmation`) lives on the
  `CommandProcessor` instance, not at module level - one processor's
  pending confirmation is never visible to another.
- The confirm-word check is a fixed 3-word allow-list
  (yes/confirm/confirmed), not free-text interpretation - casual
  affirmatives ("yeah", "sure", "ok") do not confirm.
- A chained dangerous phrase can never partially execute the
  secondary action, before or after confirmation.

### Known limitations

- Dangerous-phrase matching mirrors `system_control.handle_system()`'s
  existing bare-substring semantics exactly (by design, to stay
  consistent with the rest of this codebase) - this means the same
  pre-existing substring-trap characteristic applies (e.g. "my lock
  computer test" or "restart computer settings" both match, exactly as
  `system_control.py` already would without confirmation). Phase 9
  does not change or improve this matching; it only adds a
  confirmation gate in front of whatever `system_control.py` would
  already have matched.
- Rejecting or giving an invalid confirmation reply discards that
  entire utterance - if it happened to also contain an unrelated valid
  command, that command is not executed either. The user simply
  repeats it.
- No timeout on a pending confirmation - it remains pending until the
  next utterance, however long that takes.

## Phase 10.1 — Offline Speech-to-Text Fallback

**Status: PHASE 10.1 COMPLETE.**

`src/stt_backend.py` introduces a small backend abstraction
(`STTBackend`) so `speech.Speech` is written against an interface, not
against `recognize_google()` directly. `Speech.listen()`'s public
contract (always returns a plain string, or `""` - never raises) is
completely unchanged.

Two backends exist:

- `GoogleOnlineBackend` - the original Phase 1-9 backend, unchanged
  behavior, still the primary/first-tried backend.
- `OfflineWhisperBackend` - a fallback, only ever tried after the
  online backend fails to produce text (`config.OFFLINE_STT_ENABLED`,
  default `True` - see below for why this is safe left on). It calls
  `speech_recognition`'s own bundled `recognize_faster_whisper()`
  adapter, which lazily imports the separate `faster_whisper` package
  only when actually invoked.

**`faster_whisper` is NOT installed in this project.**
`OfflineWhisperBackend.is_available()` correctly reports `False` until
it is, and every caller treats "offline backend unavailable" as a
normal, expected, non-error case - so `config.OFFLINE_STT_ENABLED`
being `True` by default has **no effect** until that separate,
not-yet-approved dependency is explicitly installed. `config.
OFFLINE_STT_DEVICE`/`OFFLINE_STT_COMPUTE_TYPE` are pinned to `"cpu"`/
`"int8"` (not `"auto"`/`"cuda"`) - validated during Phase 10.1
development that `"auto"` would silently pick a broken CUDA path on
this machine (missing NVIDIA cuBLAS runtime) and the offline fallback
would never actually produce text; `"cpu"`/`"int8"` is the verified-
working configuration and requires no dependency beyond
`faster_whisper` + `soundfile`.

### Known limitations
- No effect at all until `faster_whisper` is separately installed -
  that remains a deliberate, deferred, approval-gated decision.
- Offline recognition quality/latency has not been benchmarked in this
  project (no installed model to test against yet).

## Phase 10.2 — Rule-Based Intent Fallback Layer

**Status: PHASE 10.2 COMPLETE. `config.ENABLE_INTENT_FALLBACK_LAYER`
default `False`.**

`src/intent_layer.py` adds a rule-based fallback consulted only after
the entire existing deterministic pipeline (`natural_language.
split_into_clauses()` → `command_parser.normalize()` → the fixed
dispatch chain) has already failed to recognize a command - see
`commands.py`'s insertion point, immediately before the final "I don't
know how to do that" response. Every command that already worked
before Phase 10.2 is completely unaffected: zero added latency, zero
behavior change, since this module is never even called for them.

Rescues real, verified gaps in the existing dispatch chain: dangerous-
command paraphrases ("power off the computer", "reboot the machine" -
`intent_parser.py` has no representation of lock/shutdown/restart at
all), absolute-volume phrasings with the number before "volume" or a
missing verb, "search for X" appearing mid-sentence, and "hit enter"/
"tab key" style key-press phrasings. `intent_layer.py` does **not**
modify `intent_parser.py` (which stays diagnostics-only, fixed-shape,
untouched since Phase 5) - it's a separate module that reuses `intent_
parser`'s fixed allow-lists (`KNOWN_APPLICATIONS`, `KNOWN_KEYS`) by
import.

Every `IntentFrame` this layer produces is rendered to one of the
exact same canonical command strings the existing handlers already
understand and fed back into `CommandProcessor.process()` - the same
method, called recursively - never into a control module directly. The
Phase 9 dangerous-command confirmation gate is the unconditional first
check at the top of `process()` on every call, including recursive
ones, so nothing this layer produces can bypass it.

**Two defects were found and fixed during Phase 10.2's own validation**
before recommending any default: the original dangerous-phrase regexes
matched the verb and noun independently anywhere in the text (so
"computer shutdown information" and "shut down information about the
computer" both incorrectly matched) - fixed to require the verb, an
optional short article, then the noun, immediately adjacent. The
original volume-percentage regex captured only a bare 1-3 digit run,
so a leading `-` or a decimal point was silently ignored rather than
rejected ("-10 percent" matched "10") - fixed to capture the full
numeric token and explicitly reject anything that isn't a clean,
unsigned whole number (reject-not-clamp, matching `command_parser.
canonicalize_set_volume_phrase()`'s existing policy).

### Known limitations
- Because most existing control-module handlers already match very
  broad bare substrings (e.g. `web_control.handle()` treats "chrome"
  anywhere in the command as "open Chrome"), a targeted-window or
  open-application phrase that names a known application is usually
  already "handled" by an earlier dispatch step before this layer is
  ever reached - disclosed, not hidden, in the module's own docstring.
- No conversational memory/context - every command is still evaluated
  statelessly at this phase (added in 10.3-10.5, see below).

## Phase 10.3 — Conversational Context / Slot-Filling

**Status: PHASE 10.3 COMPLETE. `config.ENABLE_CONTEXT_LAYER` default
`False` - not yet recommended for default-on use.**

Adds a small, deliberately narrow conversational-context layer
(`src/context_manager.py`) on top of Phase 10.2's rule-based intent
fallback layer. JARVIS can now ask exactly one kind of follow-up
question - a missing search query - and use the next reply to
complete it:

```
User:  "Jarvis, search YouTube."
JARVIS: "What should I search for?"
User:  "Spider-Man."
JARVIS: "Searching for Spider-Man."
```

No other conversational behavior was added. "Make it louder" already
worked before this phase (a fixed pronoun idiom in
`command_parser.py`, unrelated to this layer) and is unaffected.

### Architecture

```
speech -> wake-word detection -> speech-to-text -> command extraction
       -> commands.CommandProcessor.process()
            1. pending dangerous-confirmation reply   (Phase 9, unchanged)
            2. pending context/slot reply              (Phase 10.3, NEW)
            3. dangerous-command safety gate            (Phase 9, unchanged)
            4. clause splitting                         (Phase 8, unchanged)
            5. normalization                            (unchanged)
            6. existing dispatch chain                  (unchanged)
            7. intent fallback                          (Phase 10.2, unchanged)
            8. context slot creation                    (Phase 10.3, NEW)
            9. "I don't know how to do that yet."
       -> existing control modules -> existing voice responses
```

Only SEARCH is slot-fillable, and only for one bare phrasing: "search
youtube" (naming a site with no query). Everything else that reaches
step 8 behaves exactly as it did before this phase.

### How it works

1. `command_parser.canonicalize_search_phrase()` gained one narrow
   exception (`SEARCH_BARE_SITE_RE`): "search youtube" is left
   unrewritten, instead of being incorrectly turned into a literal
   Google search for the word "youtube" (its previous, wrong
   behavior - "search youtube" was never a correctly-handled command
   before this phase).
2. `intent_layer.py` gained one new rule (`SEARCH_INCOMPLETE_RE`) that
   recognizes this bare phrasing as an **incomplete** SEARCH
   `IntentFrame` (`frame.incomplete = True`) instead of falling
   through to `OPEN_APPLICATION`. Every other phrasing naming
   "youtube" ("open youtube", "launch youtube", "search youtube for
   cats") is completely unaffected.
3. `commands.CommandProcessor` parks a `context_manager.
   PendingSlotRequest` (`self._pending_slot`) and speaks the question,
   instead of silently doing nothing (the old dead-code fallthrough)
   or opening YouTube.
4. The next call to `process()` treats the new utterance as the
   reply: `context_manager.resolve_pending_slot()` decides whether it
   (a) fills the slot -> renders `"search for <reply>"` and calls
   `self.process()` again, (b) independently looks like its own
   recognized command (including a dangerous one) -> drops the stale
   slot and calls `self.process()` with the ORIGINAL text unmodified,
   or (c) is empty/expired -> says "Never mind." and does nothing.

`context_manager.py` is pure: it never imports a control module, never
imports `voice`, and has no `subprocess`/`ctypes`/`comtypes`/`os.system`
anywhere in it (enforced by dedicated tests, not just by convention -
see `tests/test_security.py`'s Phase 10.3 section and
`tests/test_context_manager.py`'s import-list test). Every canonical
command it can produce is handed back to `CommandProcessor.process()`
- recursively, exactly like the Phase 8 clause loop and the Phase 10.2
intent-fallback loop already work - so the Phase 9 dangerous-command
gate (the unconditional first check on every `process()` call,
including recursive ones) can never be bypassed by anything this layer
produces.

### Dangerous commands remain protected

```
JARVIS: "What should I search for?"
User:  "Lock my computer."
JARVIS: "Are you sure you want to lock the computer? Say yes to confirm."
```

A reply to a pending search question is never blindly poured into the
search query - `resolve_pending_slot()` checks it against the existing
deterministic classifiers first (`intent_parser.classify()`, then
`intent_layer.understand()`, which includes the Phase 10.2 dangerous-
paraphrase rules). If it independently looks like a real command, the
pending slot is dropped and the original text is re-processed from the
top of `process()` - so the Phase 9 gate sees it normally, exactly as
if no question had ever been asked.

### Expiry

A pending slot request is only valid for `config.CONTEXT_SLOT_MAX_TURNS`
(default 1 - the very next command) or `config.CONTEXT_SLOT_TTL_SECONDS`
(default 30 real-world seconds), whichever comes first. Past either
bound, it's treated as gone and the new utterance is processed as a
fresh command. This is a UX bound, not a safety boundary: even a
wrongly-still-valid slot can only ever render into a `"search for
<text>"` command - never anything dangerous.

### Configuration

- `config.ENABLE_CONTEXT_LAYER` (default `False`) - master switch.
  Only has an effect when `config.ENABLE_INTENT_FALLBACK_LAYER` is
  ALSO `True`, since that layer is what discovers an incomplete SEARCH
  frame in the first place.
- `config.CONTEXT_SLOT_MAX_TURNS`, `config.CONTEXT_SLOT_TTL_SECONDS` -
  expiry bounds, see above.

### Security guarantees

- `context_manager.py` contains no `subprocess`, `ctypes`, `comtypes`,
  `eval(`, or `exec(`, never calls `os.system`, and imports none of
  `web_control`/`system_control`/`window_control`/`volume_control`/
  `media_control`/`keyboard_control`/`screen_control`/`voice` -
  verified directly by inspecting its import list, not just by
  convention.
- Every canonical command this layer can produce is fed back through
  `CommandProcessor.process()`, never executed directly.
- A dangerous phrase said while a search slot is pending still reaches
  the Phase 9 confirmation gate, with every real-action primitive
  mocked in tests proving nothing executes without it.
- Pending-slot state (`self._pending_slot`) lives on the
  `CommandProcessor` instance, exactly like `self._pending_confirmation`
  - never at module level.

### Known limitations

- Only SEARCH is slot-fillable, and only for the bare "search youtube"
  phrasing - no other intent asks a follow-up question in this phase.
- No general conversational memory - `self._context` only exists to
  bound a pending slot's expiry; JARVIS does not "remember" anything
  about earlier turns beyond that one pending question.
- No pronoun/reference resolution beyond the pre-existing, unrelated
  "turn it up"/"make it louder" volume idiom in `command_parser.py`.
- A rejected/expired slot reply that happened to also be a valid new
  command is still processed as that new command (by design - see
  "How it works" above) - but a reply that's neither a recognized
  command nor empty is always treated as free-text search input, even
  if that wasn't the user's intent (e.g. a genuinely misheard, garbled
  reply becomes a nonsense search query rather than being rejected).
- Extending slot-filling to other intents, adding real multi-turn
  memory, or a dedicated response-generation layer are explicitly out
  of scope for this phase - not yet implemented.

## Phase 10.4 — Contextual Reference Resolution ("it"/"that"/"this")

**Status: PHASE 10.4 COMPLETE. `config.ENABLE_REFERENCE_RESOLUTION`
default `False` - not yet recommended for default-on use.**

Adds one narrow capability on top of Phase 10.3's context layer:
JARVIS can resolve "it"/"that"/"this" against the last application it
heard named, across separate turns:

```
User:  "Jarvis, open Chrome."
JARVIS: "Opening Chrome."
...
User:  "Jarvis, close it."
JARVIS: "Closing Chrome."
```

Scoped deliberately to exactly this one reference type. Per the Phase
10.4 architecture audit, other references requested for a future phase
- "the previous search result", "first/second/last result", true
browser-history "previous website" navigation - are **not
implemented** and are not implementable with this project's current
capabilities: JARVIS has no way to read back a web page's content or
navigate browser history (`web_control.search()` only ever calls
`webbrowser.open(url)` - fire-and-forget, no DOM/page access anywhere
in this codebase). Building those would require a new, unapproved,
dependency-heavy subsystem (e.g. browser automation) and was
deliberately not attempted here.

### How it works

1. `commands.py` now reuses the same pure `intent_parser.classify()`
   call it has used for `DEBUG` diagnostics since Phase 8 - computed
   once per command (whenever `DEBUG` or `config.ENABLE_REFERENCE_
   RESOLUTION` is on) - to recognize when the command about to be
   dispatched names a known application. After a successful dispatch,
   `CommandProcessor._finish_dispatch()` records that application name
   onto `self._context` (`context_manager.ConversationContext.record()`).
2. A later, standalone command matching exactly `"<verb> it"` /
   `"<verb> that"` / `"<verb> this"` (verbs: open, close, minimize,
   maximize, restore, switch, switch to) - and ONLY that exact shape,
   anchored whole-string, the same "exact-phrase-only" discipline
   `command_parser.py`'s existing "turn it up"/"make it louder" rule
   already uses - is resolved by `context_manager.resolve_reference()`
   against the recorded application and rendered into the existing
   canonical command string (`"close chrome"`, `"open chrome"`, ...).
3. That canonical string is handed back to `self.process()`,
   recursively, exactly like every other layer in this project - so
   the Phase 9 dangerous-command gate (the unconditional first check
   on every `process()` call, including recursive ones) still sees it
   normally.

`context_manager.py` remains import-clean (no control module, no
`voice`, no execution primitive) - verified by the same structural
tests as Phase 10.3, re-run after these additions.

### Known, disclosed limitation: three verbs are currently unreachable

`window_control.handle()`'s existing, untargeted "minimize this
window"/"maximize"/"restore" bare-substring checks run earlier in
`commands.py`'s dispatch chain and already match "minimize it"/
"maximize it"/"restore it" first (acting on whichever window currently
has focus) - so in the live dispatch chain, reference resolution's own
minimize/maximize/restore handling is never actually reached for those
three verbs. It's included anyway for completeness, direct unit
testing, and defensive value against any future dispatch reordering -
the same disclosed-rather-than-hidden approach `intent_layer.py`
already uses for its own analogous case. "close it"/"switch it"/
"switch to it"/"open it" are the phrasings that actually reach this
layer in practice.

### Expiration and safety

A recorded application stays referenceable for `config.
REFERENCE_MAX_TURNS` (default 3) `CommandProcessor.process()` calls or
`config.REFERENCE_TTL_SECONDS` (default 45 real-world seconds),
whichever comes first - then it's treated as gone and the utterance
falls through to the standard "I don't know how to do that" response.
Unlike Phase 10.3's pending-slot TTL (a UX bound only, since a stale
slot can only ever become a search string), this expiry **is** a
safety bound: a resolved reference can trigger a real window/
application action, so it defaults tighter and is treated as
load-bearing.

### Configuration

- `config.ENABLE_REFERENCE_RESOLUTION` (default `False`) - master
  switch. Independent of `config.ENABLE_CONTEXT_LAYER` on purpose -
  different capability, different risk profile, separately validated.
- `config.REFERENCE_MAX_TURNS`, `config.REFERENCE_TTL_SECONDS` -
  expiry bounds, see above.

### Security guarantees

- `context_manager.py` still contains no `subprocess`, `ctypes`,
  `comtypes`, `eval(`, or `exec(`, never calls `os.system`, and
  imports none of the control modules or `voice`.
- `resolve_reference()` can only ever render `"open <app>"` or
  `"<minimize|maximize|restore|close|switch> <app>"` for an app
  already in `intent_parser.KNOWN_APPLICATIONS` - structurally
  incapable of producing `"lock computer"`/`"shutdown computer"`/
  `"restart computer"` or any other dangerous phrase (checked directly
  against every known application and every recognized verb).
- Naming an application and then giving a real dangerous command still
  reaches the Phase 9 confirmation gate, with every real-action
  primitive mocked in tests proving nothing executes without it.
- A stale/expired recorded application is never used to resolve a
  reference - proven with every window-control primitive mocked and
  asserted uncalled.

### Known limitations

- Only application/window references are resolved - no previous
  search result, no previous website, no general pronoun grammar.
- No entity history beyond the single most-recently-named application
  - saying two application names in a row only keeps the second.
- "minimize it"/"maximize it"/"restore it" are shadowed by the
  pre-existing untargeted window handling (see above) - not a defect
  introduced by this phase, but worth knowing if it seems like nothing
  happened, since the fallback behavior it silently receives is "act
  on whichever window currently has focus," not "act on the named app."
- No dedicated response-generation layer, no general conversational
  memory, no multi-turn planning - all explicitly out of scope, per
  the Phase 10.4 architecture audit.

## Phase 10.5 — Repeat-Search + "Again"/"Once More" Phrasing

**Status: PHASE 10.5 COMPLETE. Reuses `config.ENABLE_REFERENCE_
RESOLUTION` (default `False`) - deliberately no second flag.**

Two small, additive extensions to Phase 10.4's reference-resolution
layer:

```
User:  "Jarvis, open YouTube."
JARVIS: "Opening YouTube."
...
User:  "Jarvis, open it again."
JARVIS: "Opening YouTube."

User:  "Jarvis, search for cats."
JARVIS: "Searching for cats."
...
User:  "Jarvis, search that again."
JARVIS: "Searching for cats."
```

1. **"again"/"once more" phrasing widening**: `context_manager.
   REFERENCE_COMMAND_RE` now accepts an optional trailing `"again"`/
   `"once more"` ("open it again", "open that once more") - existing
   bare "open it" (no trailing word) is completely unaffected.
2. **Repeat-search**: exactly one new trigger phrase, `"search that
   again"`, resolved against the last search query and rendered to
   `"search for <query>"`.

The last-search-query is tracked in **fields on `ConversationContext`
kept completely separate from the Phase 10.4 last-named-application
fields** - recording a search never overwrites/erases the remembered
application, and vice versa. This was the key design question this
phase had to answer (see the Phase 10.5 architecture audit): a shared
single-dict design would have let `"open chrome"` → `"search for
cats"` → `"open it"` wrongly fail (the search recording would have
erased the application memory); the two-slot design keeps both
independently correct and independently expiring (`config.
SEARCH_REPEAT_MAX_TURNS`/`SEARCH_REPEAT_TTL_SECONDS`, separate
constants from `REFERENCE_MAX_TURNS`/`REFERENCE_TTL_SECONDS`).

A Phase 10.3 slot-filled search (`"search youtube"` → `"Spider-Man"` →
`"search for spider-man"`) is automatically repeatable too, with no
extra wiring - that resolution recurses through `CommandProcessor.
process()` and reaches the same recording point as any other search.

One small, disclosed fix was required in `command_parser.py`: the
existing generic `"search X"` → `"search for X"` rewrite would
otherwise have mangled the literal trigger phrase into `"search for
that again"`, which `web_control.handle()` would then have
immediately (and wrongly) executed as a search for the literal text
"that again" before ever reaching the resolver - the same class of
fix Phase 10.3 needed for `"search youtube"`, applied here to exactly
one additional phrase.

### Known limitations
- Exactly one repeat-search trigger phrase and one phrasing widening -
  no other synonyms ("do that search again," "repeat it") were added.
- Still only the single most-recently-searched query is remembered -
  no multi-item search history.
- Same out-of-scope boundaries as Phase 10.4: no browser history, no
  search-result reading, no "previous website" stack.

## Configuration options (`src/config.py`)

| Setting | Purpose |
|---|---|
| `WAKE_WORD` | Canonical wake word ("jarvis") |
| `WAKE_WORD_ALIASES` | Whole-word variations that also activate JARVIS (currently `["jarvis", "jervis"]`, plus a possessive `'s` suffix is always allowed) |
| `ENERGY_THRESHOLD` / `DYNAMIC_ENERGY_THRESHOLD` | Microphone sensitivity baseline and auto-adjustment |
| `PAUSE_THRESHOLD` / `NON_SPEAKING_DURATION` | How much silence ends a phrase |
| `AMBIENT_NOISE_DURATION` | Seconds spent calibrating room noise at startup |
| `WAKE_LISTEN_TIMEOUT` / `WAKE_PHRASE_LIMIT` | Timeout/length for the idle wake-word listen |
| `COMMAND_LISTEN_TIMEOUT` / `COMMAND_PHRASE_LIMIT` | Timeout/length for command capture after "Yes?" |
| `SPEECH_API_RETRIES` / `SPEECH_API_RETRY_DELAY` | Retries of the recognition API call itself on the same audio (network blips) |
| `COMMAND_RECOGNITION_RETRIES` | Times JARVIS asks you to repeat yourself after "Yes?" before giving up |
| `REQUEST_ERROR_ANNOUNCE_COOLDOWN` | Minimum seconds between spoken "trouble connecting" warnings |
| `DEBUG` | When `True`, prints extra pipeline diagnostics (see below). Off by default. |
| `REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS` | (Phase 9) Speak-a-confirmation-prompt gate for lock/shutdown/restart. **Default `False`.** |
| `OFFLINE_STT_ENABLED` / `OFFLINE_STT_MODEL` / `OFFLINE_STT_DEVICE` / `OFFLINE_STT_COMPUTE_TYPE` | (Phase 10.1) Offline Whisper fallback config - has no effect until `faster_whisper` is separately installed (it isn't). |
| `ENABLE_INTENT_FALLBACK_LAYER` | (Phase 10.2) Rule-based fallback for commands the deterministic chain misses. **Default `False`.** |
| `INTENT_CONFIDENCE_THRESHOLD` | (Phase 10.2) Minimum confidence an `intent_layer.IntentFrame` needs to be acted on (`0.6`). |
| `ENABLE_CONTEXT_LAYER` | (Phase 10.3) Pending-slot follow-up questions (currently only SEARCH's missing query). **Default `False`.** Only has an effect when `ENABLE_INTENT_FALLBACK_LAYER` is also `True`. |
| `CONTEXT_SLOT_MAX_TURNS` / `CONTEXT_SLOT_TTL_SECONDS` | (Phase 10.3) Expiry bounds for a pending slot request (`1` turn / `30` seconds). |
| `ENABLE_REFERENCE_RESOLUTION` | (Phase 10.4/10.5) "it"/"that"/"this" (+ "again"/"once more") resolved against the last-named application, and "search that again" against the last search query. **Default `False`.** One flag covers both Phase 10.4 and Phase 10.5 by design. |
| `REFERENCE_MAX_TURNS` / `REFERENCE_TTL_SECONDS` | (Phase 10.4) Expiry bounds for the last-named-application record (`3` turns / `45` seconds). |
| `SEARCH_REPEAT_MAX_TURNS` / `SEARCH_REPEAT_TTL_SECONDS` | (Phase 10.5) Expiry bounds for the last-search-query record - tracked independently of `REFERENCE_MAX_TURNS`/`REFERENCE_TTL_SECONDS` (`3` turns / `45` seconds). |

All Phase 9-10.5 feature flags default to `False` - every capability
they gate is opt-in, not silently active. See each phase's section
above for the specific rollout status and validation behind that
default.

## Wake-word behavior

- "Jarvis `<command>`" → command runs immediately.
- "Jarvis" alone → JARVIS says "Yes?" and listens for a follow-up
  command (retried per `COMMAND_RECOGNITION_RETRIES` if unclear).
- Recognized variations: "jervis" (common mishearing), "jarvis's"
  (possessive), and any number of immediately repeated wake words
  ("jarvis jarvis jarvis open chrome" → "open chrome").
- Words that merely *contain* "jarvis" (e.g. "jarvison", "myjarvis") do
  **not** activate JARVIS - matching is whole-word only, intentionally
  not broadened further to avoid accidental activation on unrelated
  speech.

### Diagnostics (`config.DEBUG`)

Set `DEBUG = True` in `src/config.py` to print extra lines showing what
the pipeline actually did at each stage:

```
[DEBUG] heard='jarvis jarvis open chrome' wake_word_detected=True extracted='jarvis open chrome'
[DEBUG] raw='jarvis open chrome' normalized='open chrome'
```

This is off by default - normal console output stays limited to
`Listening...` / `Processing...` / `You: ...` / `JARVIS: ...` as before.

## Known speech-recognition limitations

- **Requires internet access** - `recognize_google()` is a network call
  to Google's free speech API. There is no offline fallback.
- **"Could not understand the speech" is expected sometimes**, not a
  bug - background noise, mumbled speech, or a slow start of the
  sentence can all cause it. Retrying (see `COMMAND_RECOGNITION_RETRIES`)
  helps but doesn't eliminate this.
- **Ambient noise calibration is one-time, at startup.** If your room
  gets significantly noisier later in the session, recognition quality
  can degrade until `dynamic_energy_threshold` catches up on its own.
- **Wake-word aliases are intentionally narrow.** Only "jervis" and the
  possessive "'s" form are recognized alongside "jarvis" - this is a
  deliberate tradeoff to avoid accidentally activating on unrelated
  speech.

## Troubleshooting microphone problems

- **"Microphone error: ..." printed at startup or every listen cycle** -
  no microphone is detected, or it's in use by another application.
  Check Windows Settings → Privacy → Microphone, and that the correct
  input device is set as default.
- **JARVIS never seems to hear anything** - check `ENERGY_THRESHOLD`
  isn't set too high for a quiet room, or too low for a noisy one; try
  increasing `AMBIENT_NOISE_DURATION` for a more accurate calibration.
- **Frequent "Could not understand the speech"** - speak clearly right
  after the wake word, reduce background noise, or increase
  `PAUSE_THRESHOLD` slightly if your sentences are being cut off.
- **"I am having trouble connecting to speech recognition."** - this is
  a network/API problem (`RequestError`), not a microphone problem;
  check your internet connection.

## Project layout

```
JARVIS/
├── src/
│   ├── jarvis.py             # Entry point, wake-word loop, module wiring
│   ├── speech.py             # Microphone input + speech-to-text
│   ├── voice.py               # Text-to-speech (pyttsx3)
│   ├── command_parser.py      # Deterministic natural-language normalization
│   ├── natural_language.py    # Bounded multi-clause command splitting (Phase 8)
│   ├── intent_parser.py       # Fixed-allow-list intent classifier (diagnostics/testing)
│   ├── intent_layer.py        # Rule-based intent fallback (Phase 10.2)
│   ├── context_manager.py     # Slot-filling (10.3), reference resolution (10.4), repeat-search (10.5)
│   ├── stt_backend.py         # STT backend abstraction: online + offline Whisper fallback (Phase 10.1)
│   ├── commands.py            # Command routing (time/date, greetings, exit)
│   ├── system_control.py      # Windows apps + power commands
│   ├── web_control.py         # Browser / web commands
│   ├── window_control.py      # Minimize/maximize/restore/close/switch/desktop
│   ├── volume_control.py      # Volume up/down (multimedia keys); true mute/unmute + absolute volume (Core Audio, Phase 7)
│   ├── audio_endpoint.py      # Windows Core Audio (IAudioEndpointVolume) COM wrapper (Phase 7)
│   ├── media_control.py       # Play/pause, next/previous track
│   ├── screen_control.py      # Screenshot capture
│   ├── keyboard_control.py    # Fixed keyboard shortcuts (copy/paste/etc.)
│   ├── input_control.py       # Low-level ctypes key-press primitives
│   └── config.py              # Central configuration (wake word, timeouts, feature flags, etc.)
├── screenshots/                # Timestamped screenshots (created on first use)
├── tests/
│   ├── test_commands.py
│   ├── test_command_parser.py
│   ├── test_natural_language.py
│   ├── test_system_control.py
│   ├── test_window_control.py
│   ├── test_volume_control.py
│   ├── test_audio_endpoint.py
│   ├── test_media_control.py
│   ├── test_screen_control.py
│   ├── test_keyboard_control.py
│   ├── test_speech.py         # Mocked recognizer/microphone reliability tests
│   ├── test_stt_backend.py    # Online/offline STT backend abstraction tests (Phase 10.1)
│   ├── test_wake_word.py      # Wake-word matching, aliases, repeats
│   ├── test_pipeline.py       # Full mic-text -> command -> mocked-action tests
│   ├── test_intent_parser.py  # Intent classifier + allow-list enforcement
│   ├── test_intent_layer.py   # Rule-based intent fallback tests (Phase 10.2)
│   ├── test_context_manager.py # Slot-filling/reference-resolution/repeat-search unit tests (10.3-10.5)
│   └── test_security.py       # Shell/PowerShell/keyboard-injection rejection tests
├── PHASE_7_9_COMPLETE_VALIDATION_REPORT.md
├── PHASE_10_COMPLETE_VALIDATION_REPORT.md
├── requirements.txt
└── README.md
```

Natural-language variations (e.g. "launch YouTube", "go to YouTube",
"google Python", "run Notepad") are rewritten by `command_parser.py` into
the canonical phrasing the handlers below already understand, before
routing. This is plain deterministic string/regex normalization - no
LLM or external API is involved.

## Supported commands

### Web / browsers
- "Jarvis open Chrome" / "open up Chrome" / "launch Chrome" / "go to Chrome"
- "Jarvis open Edge"
- "Jarvis open YouTube" / "Jarvis open Google" / "Jarvis open GitHub"
- "Jarvis search for `<query>`" / "google `<query>`" / "look up `<query>`" /
  "find information about `<query>`" / "search the web for `<query>`" /
  "search Google for `<query>`" / "search on Google for `<query>`" (Phase 8)
- Politeness wrappers all work, including stacked ones: "could you open
  Chrome for me", "can you open YouTube", "please open YouTube", "would
  you open Chrome", "I want you to open Chrome", "could you please
  launch YouTube"

### Applications
- "Jarvis open Notepad" / "Jarvis open Calculator" / "Jarvis open Command Prompt" /
  "Jarvis open PowerShell" / "Jarvis open File Explorer" / "Jarvis open Settings" /
  "Jarvis open Task Manager"
- Variations: "open", "launch", "start", "run" all work (e.g. "Jarvis run Notepad"),
  plus politeness wrappers ("could you open File Explorer", "please launch PowerShell")

### Window control
- "Jarvis minimize this window" / "maximize this window" / "restore this window"
  (also works with "can you minimize this window", etc.)
- "Jarvis close this window"
- "Jarvis switch window" / "switch to next window"
- "Jarvis show desktop" / "show me the desktop"

### Volume
- "Jarvis volume up" / "increase volume" / "turn the volume up" /
  "make the volume louder" / "turn it up" / "make it louder"
- "Jarvis volume down" / "decrease volume" / "turn the volume down" /
  "make the volume quieter" / "turn it down" / "make it quieter" / "make it softer"
- "Jarvis set volume to 40 percent" / "set volume to 40%" / "make the volume
  40 percent" / "turn the volume to 40 percent" / "change the volume to 40
  percent" (verb forms other than "set" added in Phase 8) - true, absolute
  system volume via Windows Core Audio. Valid range is 0-100 inclusive
  (0 -> scalar 0.0, 40 -> scalar 0.4, 100 -> scalar 1.0); anything
  outside that range, or not a plain 1-3 digit integer, is rejected
  outright rather than clamped - see Safety & Limitations below.
- "Jarvis mute the computer" / "Jarvis unmute" - true, absolute mute/unmute
  via Core Audio (Phase 7), idempotent: "mute" always mutes and "unmute"
  always unmutes, regardless of the system's current state - see Safety
  & Limitations below.

### Media
- "Jarvis play" / "Jarvis pause" (toggles play/pause), "play the music", "pause the music"
- "Jarvis next track" / "Jarvis previous track" / "skip this song" / "go to the next track"
- "Jarvis stop the music" / "stop the song" / "stop playing" (Phase 8) - maps
  onto the existing play/pause toggle above; there is no separate "stop"
  capability

### Screenshot
- "Jarvis take a screenshot" / "Jarvis screenshot" / "Jarvis capture screen" /
  "capture my screen"
- Saved to `screenshots/screenshot_<timestamp>.png` (microsecond-precision
  timestamp, so repeated screenshots never overwrite each other)

### Keyboard (fixed shortcuts only - not free text typing)
- "Jarvis press enter" / "press escape" / "press space" / "press tab"
- "Jarvis copy" / "paste" / "select all" / "undo"

### System power
- "Jarvis lock computer" / "Jarvis shutdown computer" / "Jarvis restart computer"
  - Execute immediately by default (unchanged since v2). If
    `config.REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS` is set to
    `True` (Phase 9, off by default), each speaks a confirmation prompt
    and waits for a follow-up "yes"/"confirm"/"confirmed" (say the wake
    word again) before executing - anything else cancels. See "Phase 9"
    above.

### Info / conversation
- "Jarvis what time is it" / "Jarvis what's the date" / "Jarvis what day is it"
- "Jarvis hello"
- "Jarvis exit" / "quit" / "goodbye" / "go offline"

## Safety & limitations

- **Mute/unmute is true and idempotent (Phase 7).** "mute" and "unmute"
  call `IAudioEndpointVolume.SetMute(True/False, None)` directly via the
  Windows Core Audio COM API (`comtypes` - already a project dependency,
  no new package was added) - each does exactly what it says regardless
  of the system's current mute state. This replaced the old
  multimedia-key-toggle behavior from Phase 6 and earlier, where
  "unmute" while already unmuted would mute the system instead.
- **Absolute volume is validated, never silently clamped (Phase 7).**
  "set volume to `<N>` percent"/"`<N>`%" only accepts a plain 1-3 digit
  integer in the 0-100 range. Negative values, values above 100, huge
  numeric payloads, decimals, and spelled-out numbers are all rejected
  outright and never reach the Core Audio setter - the command is
  treated as unrecognized rather than guessing at, clamping, or
  rounding the requested value.
- **The Core Audio volume/mute path introduces no new execution
  surface.** Setting volume or mute/unmute never touches
  `subprocess.Popen`, `os.system`, or the keyboard-injection primitives
  - verified directly by dedicated tests in `tests/test_security.py`.
- **Window/keyboard commands act on whatever currently has focus.** There is
  no window targeting by name (e.g. you can't say "close Notepad" while
  focused on Chrome - it closes whatever window is focused).
- **Keyboard control is a fixed allow-list.** JARVIS never types arbitrary
  spoken text - only Enter/Escape/Space/Tab and Ctrl+C/V/A/Z can be sent.
- **No destructive commands are implemented**: no file deletion, no drive
  formatting, no registry edits, and no arbitrary shell command execution.
  Lock/shutdown/restart are the only "system power" actions, unchanged from
  earlier phases, and remain behind explicit wake-word-triggered phrases.
- Application/window/browser matching uses substring checks (consistent
  with earlier phases), so phrasing outside the documented examples isn't
  guaranteed to route correctly.
- **No arbitrary command execution, ever - proven, not just claimed.**
  Every `subprocess.Popen`/`os.system` call anywhere in this codebase
  uses a hardcoded argument list (e.g. `["powershell.exe"]`,
  `["cmd.exe"]`) - spoken text is never passed as an argument, even when
  a dangerous-sounding phrase happens to contain a trigger word like
  "powershell". `tests/test_security.py` verifies this directly: e.g.
  "open powershell and then run del /f /s /q c:\windows" still only
  ever calls `Popen(["powershell.exe"], shell=False)` - the rest of the
  sentence is discarded, never reaches the subprocess call.
- **No arbitrary keyboard text injection.** `keyboard_control.py` has no
  "type this text" capability at all - only the fixed shortcuts listed
  above. `intent_parser.PRESS_KEY` targets are restricted to the fixed
  `KNOWN_KEYS` allow-list (enter/escape/space/tab); anything else (e.g.
  "press delete") is `UNKNOWN`, not a fabricated key press.
- **Unknown applications/intents are rejected, not guessed.**
  `intent_parser.OPEN_APPLICATION` targets only ever come from the fixed
  `KNOWN_APPLICATIONS` allow-list; anything outside it is classified
  `UNKNOWN` rather than partially matched.

### Phase 9-10.5 layers: all default off, all fail-closed by construction

- **Every flag defaults `False`** (`REQUIRE_CONFIRMATION_FOR_DANGEROUS_
  COMMANDS`, `ENABLE_INTENT_FALLBACK_LAYER`, `ENABLE_CONTEXT_LAYER`,
  `ENABLE_REFERENCE_RESOLUTION`) - see "Configuration options" above.
  With all four off, behavior is byte-for-byte identical to this
  project's pre-Phase-9 state.
- **Nothing added since Phase 9 can execute a control module directly.**
  `intent_layer.py` and `context_manager.py` (Phases 10.2-10.5) are
  both pure: they only ever render one of the existing, already-safe
  canonical command strings and hand it back to `CommandProcessor.
  process()` - the same method, called recursively - never call
  `web_control`/`system_control`/`window_control`/`volume_control`/
  `media_control`/`keyboard_control`/`screen_control`/`voice` directly.
  Verified structurally (import-list inspection, not just convention)
  by dedicated tests in `tests/test_security.py`.
- **The Phase 9 dangerous-command gate is unconditional and runs on
  every `process()` call, including every recursive one** - it is the
  first behavioral check performed, before the Phase 10.2-10.5 layers
  ever get a chance to run. A dangerous phrase or paraphrase reached
  through a pending slot reply, a resolved reference, or a repeated
  search still hits this gate before anything executes. Verified
  end-to-end, with every real-action primitive mocked simultaneously,
  across all combinations of these layers - including all four flags
  enabled at once (see `PHASE_10_COMPLETE_VALIDATION_REPORT.md`).
- **Conversational state never clobbers itself.** Phase 10.4's
  last-named-application memory and Phase 10.5's last-search-query
  memory are stored in completely separate fields on the same
  `ConversationContext` object - naming an application and then
  searching (or vice versa) never erases the other's memory. Directly
  proven by a regression test: "open chrome" → "search for cats" →
  "open it" still resolves to Chrome.
- **All conversational state expires.** A pending slot request
  (Phase 10.3), a remembered application (Phase 10.4), and a
  remembered search query (Phase 10.5) each expire on their own
  independent turn-count/wall-clock bounds
  (`CONTEXT_SLOT_MAX_TURNS`/`TTL_SECONDS`, `REFERENCE_MAX_TURNS`/
  `TTL_SECONDS`, `SEARCH_REPEAT_MAX_TURNS`/`TTL_SECONDS`) - a stale
  record is never silently reused.
- **No LLM, no external AI service, no new third-party dependency** in
  any Phase 9-10.5 layer - `intent_layer.py`/`context_manager.py` are
  plain deterministic regex/dict-based rule modules, the same style as
  `command_parser.py` since Phase 5. The only Phase 10 dependency
  decision (`faster_whisper` for offline STT, Phase 10.1) was
  explicitly deferred and remains uninstalled.

## Tests

Tests mock `webbrowser.open`, `subprocess.Popen`, `os.system`, the
`ctypes`/`user32` calls used for window/keyboard/volume/media control,
the Windows Core Audio (`IAudioEndpointVolume`/`comtypes`) calls used
for absolute volume and true mute/unmute (Phase 7), `PIL.ImageGrab.grab`,
and `speech_recognition`'s `Recognizer`/`Microphone`, so no microphone,
real window manipulation, actual screen capture, actual Core Audio
device change, or actual destructive Windows action happens during
automated tests:

```
python -m pytest -q
```

**Exact result as of the last verified run (Phase 10.6):** `677
passed, 2 warnings` - `0 failed`, `0 skipped`. The 2 warnings are
pre-existing, unrelated `DeprecationWarning`s from inside the
`speech_recognition` package itself (`aifc`, `audioop`), not from this
project's code. A dedicated safety-net verification pass - mocking
every real Windows/COM entry point independently of what each test
patches itself - confirmed zero real Core Audio COM calls, zero real
Windows API (`user32`) calls, zero `subprocess.Popen`/`os.system`
calls, and zero keyboard-injection calls across the full suite. (An
equivalent, non-pytest, manual diagnostic script incompletely mocked
during Phase 8 development caught one real, unmocked `keybd_event`
call, and a similar manual script during Phase 9 development caught a
real, unmocked Chrome launch - see the Phase 9 section above for the
full incident disclosure. Neither happened inside the actual pytest
suite itself; both are documented as development-process findings that
led directly to the fully-mocked tests now in place.)

Phase 5 baseline was `170 passed` (verified before any Phase 5 change
was made); Phase 5 finished at `259 passed`. Phase 6 (targeted window
control by application name) finished at `288 passed`. Phase 7
(absolute volume + true mute/unmute via Core Audio) finished at `346
passed`. Phase 8 (natural-language synonym extensions + bounded
multi-clause chaining) finished at `405 passed`. Phase 9 (dangerous-
command confirmation layer) added 30 tests, finishing at `435 passed`.
Phase 10.1 (offline STT backend abstraction) and Phase 10.2 (rule-
based intent fallback layer, including two bug-fixes found during its
own validation) together brought the suite to `531 passed`. Phase 10.3
(conversational context / slot-filling) finished at `589 passed`.
Phase 10.4 (contextual reference resolution) finished at `626 passed`.
Phase 10.5 (repeat-search + "again"/"once more" phrasing) finished at
`675 passed`. Phase 10.6 (final integration audit + two new end-to-end
pipeline tests, documentation-only otherwise) finished at `677
passed` - none removed or weakened, 0 failures at any phase boundary
from Phase 5 through Phase 10.6.

### Manual tests actually performed (Phase 5)

- `python src\jarvis.py` run for ~15 seconds. Observed real output:
  `Calibrating microphone for ambient noise...`, then `JARVIS: JARVIS
  online. Say my name when you need me.`, then normal `Listening...`
  cycles with no crash.
- **No live voice commands were spoken into the microphone during this
  phase.** None of the new natural-language phrases ("could you open
  Chrome for me", "make the volume louder", "show me the desktop", etc.)
  were verified by actually speaking them - only by automated tests that
  call `command_parser.normalize()` / `commands.CommandProcessor.process()`
  directly with the exact text strings, mocking every real action
  (`subprocess.Popen`, `os.system`, `webbrowser.open`, the `ctypes`/
  `user32` calls, `PIL.ImageGrab.grab`). If you want live confirmation
  that a specific phrase is actually recognized by Google's speech API
  and routed correctly, that requires running `python src\jarvis.py`
  and speaking it yourself.

## Phase 11.13 — Pretrained Neural TTS

`voice.Voice` now tries a pretrained neural TTS backend (Kokoro-82M,
via the `kokoro-onnx` package - MIT-licensed wrapper, Apache-2.0-licensed
model weights) before falling back to the original pyttsx3 (Windows
SAPI5) engine every phase before this one used exclusively. The
fallback is unconditional: a missing dependency, missing model files,
or any synthesis/playback error all fall straight through to pyttsx3 -
see `voice.py`/`tts_backend.py`'s own docstrings. No other module
changed - every `voice.speak(text)` call site in the codebase is
untouched.

### Setup (the neural voice is optional)

`kokoro-onnx`/`onnxruntime` are in `requirements.txt` and installed by
`pip install -r requirements.txt` like everything else, but the
**pretrained model weights are NOT committed to this repository** (see
`.gitignore`'s `models/` entry) - without them, JARVIS runs exactly as
it always has, on pyttsx3 alone; nothing breaks. To enable the neural
voice, download these two files (Apache 2.0 licensed) into
`models/tts/`:

```
models/tts/kokoro-v1.0.onnx   <- https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
models/tts/voices-v1.0.bin    <- https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

### Configuration (`src/config.py`)

- `TTS_BACKEND` - `"kokoro"` (default) or `"pyttsx3"` (skips the neural
  backend entirely, byte-for-byte the original behavior).
- `TTS_VOICE` - one of kokoro-onnx's ~54 built-in voices (default
  `"af_heart"` - chosen as the warmest/most natural of the American
  English options for this project's "calm, pleasant" requirement).
- `TTS_SPEED` - Kokoro's speech-rate multiplier (1.0 = natural pace) -
  a different unit from `TTS_RATE`'s pyttsx3 "words per minute", kept
  as a separate setting rather than converted between the two engines.
- `TTS_DEVICE` - `"cpu"` (default) or `"cuda"`. See that constant's own
  comment in `config.py`: this machine's NVIDIA driver reports CUDA
  13.2 support, but the CUDA Toolkit/cuDNN runtime libraries aren't
  installed, so `CUDAExecutionProvider` fails to load and onnxruntime
  silently falls back to CPU (a console warning, not a crash) - the
  exact same situation `OFFLINE_STT_DEVICE` already documents for
  faster-whisper. Measured CPU-only latency is already acceptable for
  this project's short spoken responses (see below).
- `TTS_VOLUME` - shared between both engines (pyttsx3's own volume
  property, and applied as a gain multiplier to Kokoro's synthesized
  audio before playback).

### Measured latency (this machine, CPU-only, `af_heart`)

Synthesis time for the project's own short spoken responses, first
call included (pays model-load + provider warmup once):

| Phrase | Synthesis time |
|---|---|
| "Yes?" (first call, cold) | ~2.7s |
| "Opening Chrome." | ~0.7-1.0s |
| "Closing tab." | ~0.8s |
| "Going back." | ~0.7s |
| A ~35-word sentence | ~6s (audio itself is ~11s long - faster than real-time) |

Every typical JARVIS response (a handful of words) synthesizes in
under a second after the one-time model-load cost, which is comparable
to pyttsx3's own already-blocking `runAndWait()` latency.

## Phase 12.1 — AI Tool Router (infrastructure only, no LLM connected)

`ai_tools.py`/`ai_backend.py`/`ai_router.py` are safe infrastructure
for a *future* AI reasoning layer - **no LLM is installed, downloaded,
or connected anywhere in this codebase as of Phase 12.1.**
`config.ENABLE_AI_LAYER` defaults to `False`, and even if set `True`,
`ai_backend.get_backend()` has nothing registered, so the layer is
inert either way until a future phase explicitly wires a real provider
in.

### Security model

- **LLM output is untrusted.** Every function that accepts a tool name
  or arguments treats them as hostile input by default, exactly like
  every other externally-derived input in this project (spoken text,
  STT transcripts).
- **Only explicitly allow-listed tools can execute.** `ai_tools.
  TOOL_REGISTRY` is a fixed, closed dict - `open_application`,
  `press_key`, `scroll`, `mouse_action`, `volume`, `media`,
  `tab_navigation`, `browser_navigation`, `refresh`, `search`. An
  unrecognized tool name is rejected (`UnknownToolError`), never
  guessed at.
- **Python validates all tool names and arguments.** `ai_tools.
  validate_tool_call()` is the one validation boundary every tool
  request must pass through - closed-enum arguments reuse this
  project's existing allow-lists (`intent_parser.KNOWN_APPLICATIONS`,
  `intent_parser.KNOWN_KEYS` - "delete" is not and will not be added to
  the latter) wherever one already exists, rather than defining a
  second list that could drift.
- **The LLM cannot execute arbitrary OS commands.** No tool exists for
  shell/PowerShell/Python execution, arbitrary file paths, or arbitrary
  URLs-as-actions. Every tool's `render()` function reuses an
  EXISTING, already-tested deterministic handler's canonical command
  string - this layer never implements a second copy of any action,
  and never calls a control module directly.
- **Existing Phase 9 security remains authoritative.** A validated tool
  call is rendered to a canonical command string and handed back to
  `CommandProcessor.process()` - the exact same recursive pattern
  `intent_layer.py`/`multilingual_normalizer.py` already use - so the
  Phase 9 dangerous-command gate (the unconditional first check on
  every `process()` call, including recursive ones) sees it too. No
  tool in `TOOL_REGISTRY` can render `"lock computer"`/`"shutdown
  computer"`/`"restart computer"` - lock/shutdown/restart remain
  deterministic-phrase-only, by construction, not by policy alone (see
  `tests/test_ai_tools.py`'s exhaustive sweep proving this).
- **Search is the only free-form argument and is URL-encoded.**
  `search(query)` is the sole intentional exception to closed-enum
  arguments - `query` is free text because `web_control.search()`
  already only ever URL-encodes it into a Google search link and hands
  it to `webbrowser.open()`, never to `subprocess`/`os.system`/`eval`/
  `exec`. A shell-injection-shaped query (e.g. `"; rm -rf / #"`)
  becomes nothing more than an unusual-looking search query string -
  see `tests/test_ai_tools.py`'s and `tests/test_security.py`'s
  dedicated tests proving this directly, not just asserting it.
- **Deterministic-first, structurally.** The AI router (`ai_router.
  handle()`) is only ever consulted from the LAST position in
  `commands.py`'s dispatch chain, after clause splitting, normalize(),
  the fixed dispatch chain, the intent fallback layer, the
  multilingual layer, and reference resolution have all already failed
  to recognize the command. "open chrome", "scroll down", "close tab",
  "next tab", "press enter" (and everything else the deterministic
  chain already handles) never reach the AI layer at all - proven by a
  spy backend in `tests/test_commands.py` that would record any
  consultation.
- **A text response is spoken, never executed.** If a future backend
  returns plain conversational text (`AIResponse.speak()`), it is
  handed straight to `voice.speak()` and is NEVER fed back through
  `CommandProcessor.process()` - even if the text happens to contain a
  phrase that looks like a command, it cannot self-execute.
