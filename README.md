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

The voice pipeline is: **microphone → `speech.py` → wake-word extraction
(`jarvis.py`) → `command_parser.normalize()` → `commands.CommandProcessor`
→ action module**. Every stage is deterministic - no LLM or AI service is
used anywhere in this pipeline.

1. **`speech.Speech.calibrate_microphone()`** runs once at startup. It
   listens to ambient room noise for `config.AMBIENT_NOISE_DURATION`
   seconds and uses it to set a better starting `energy_threshold`.
   `dynamic_energy_threshold` (already on) keeps adapting after that.
   This never blocks startup - if no microphone is available, it's
   skipped with a printed warning, not a crash.
2. **`speech.Speech.listen()`** opens the microphone, records up to
   `phrase_limit` seconds (or until silence, per `pause_threshold`), and
   sends the captured audio to `recognize_google()`.
   - If the API call fails with a transient error (`RequestError`), it
     is retried up to `config.SPEECH_API_RETRIES` times **on the same
     captured audio** (no need to make the user repeat themselves) with
     `config.SPEECH_API_RETRY_DELAY` seconds between attempts. Only
     after all retries fail is "I am having trouble connecting to
     speech recognition." spoken - and at most once every
     `config.REQUEST_ERROR_ANNOUNCE_COOLDOWN` seconds, so a prolonged
     outage doesn't repeat the announcement on every listen cycle.
   - `UnknownValueError` (heard something, couldn't transcribe it) and
     `WaitTimeoutError` (heard nothing) both just return `""` - no
     announcement, no crash, no retry (see `listen_with_retry` below for
     where retrying-by-re-listening happens instead).
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
│   ├── intent_parser.py       # Fixed-allow-list intent classifier (diagnostics/testing)
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
│   └── config.py              # Central configuration (wake word, timeouts, etc.)
├── screenshots/                # Timestamped screenshots (created on first use)
├── tests/
│   ├── test_commands.py
│   ├── test_command_parser.py
│   ├── test_system_control.py
│   ├── test_window_control.py
│   ├── test_volume_control.py
│   ├── test_audio_endpoint.py
│   ├── test_media_control.py
│   ├── test_screen_control.py
│   ├── test_keyboard_control.py
│   ├── test_speech.py         # Mocked recognizer/microphone reliability tests
│   ├── test_wake_word.py      # Wake-word matching, aliases, repeats
│   ├── test_pipeline.py       # Full mic-text -> command -> mocked-action tests
│   ├── test_intent_parser.py  # Intent classifier + allow-list enforcement
│   └── test_security.py       # Shell/PowerShell/keyboard-injection rejection tests
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
  "find information about `<query>`" / "search the web for `<query>`"
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
- "Jarvis set volume to 40 percent" / "set volume to 40%" (Phase 7) - true,
  absolute system volume via Windows Core Audio. Valid range is 0-100
  inclusive (0 -> scalar 0.0, 40 -> scalar 0.4, 100 -> scalar 1.0);
  anything outside that range, or not a plain 1-3 digit integer, is
  rejected outright rather than clamped - see Safety & Limitations below.
- "Jarvis mute the computer" / "Jarvis unmute" - true, absolute mute/unmute
  via Core Audio (Phase 7), idempotent: "mute" always mutes and "unmute"
  always unmutes, regardless of the system's current state - see Safety
  & Limitations below.

### Media
- "Jarvis play" / "Jarvis pause" (toggles play/pause), "play the music", "pause the music"
- "Jarvis next track" / "Jarvis previous track" / "skip this song" / "go to the next track"

### Screenshot
- "Jarvis take a screenshot" / "Jarvis screenshot" / "Jarvis capture screen" /
  "capture my screen"
- Saved to `screenshots/screenshot_<timestamp>.png` (microsecond-precision
  timestamp, so repeated screenshots never overwrite each other)

### Keyboard (fixed shortcuts only - not free text typing)
- "Jarvis press enter" / "press escape" / "press space" / "press tab"
- "Jarvis copy" / "paste" / "select all" / "undo"

### System power (unchanged since v2)
- "Jarvis lock computer" / "Jarvis shutdown computer" / "Jarvis restart computer"

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

**Exact result as of the last verified run (Phase 7):** `346 passed, 2
warnings in 0.50s` - `0 failed`, `0 skipped`. The 2 warnings are
pre-existing, unrelated `DeprecationWarning`s from inside the
`speech_recognition` package itself (`aifc`, `audioop`), not from this
project's code. A dedicated safety-net verification pass - mocking
every real Windows/COM entry point independently of what each test
patches itself - confirmed zero real Core Audio COM calls, zero real
Windows API (`user32`) calls, zero `subprocess.Popen`/`os.system`
calls, and zero keyboard-injection calls across the full suite.

Phase 5 baseline was `170 passed` (verified before any Phase 5 change
was made); Phase 5 finished at `259 passed`. Phase 6 (targeted window
control by application name) finished at `288 passed`. Phase 7
(absolute volume + true mute/unmute via Core Audio) added 58 tests,
finishing at `346 passed` - none removed or weakened, 0 failures at
any phase boundary.

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
