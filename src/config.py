"""Central configuration values for JARVIS."""

# Wake word. WAKE_WORD is the canonical/spoken name; WAKE_WORD_ALIASES is
# what's actually matched against - it includes WAKE_WORD plus a small,
# deliberately short list of common speech-recognition mishearings.
# Kept short on purpose: broader fuzzy matching risks accidental
# activation on unrelated speech.
WAKE_WORD = "jarvis"
WAKE_WORD_ALIASES = ["jarvis", "jervis"]

# Speech recognizer tuning (unchanged from the original single-file version)
ENERGY_THRESHOLD = 300
DYNAMIC_ENERGY_THRESHOLD = True
PAUSE_THRESHOLD = 0.8
NON_SPEAKING_DURATION = 0.5
RECOGNITION_LANGUAGE = "en-US"

# One-time ambient noise calibration at startup (seconds). Sets a better
# starting energy_threshold; DYNAMIC_ENERGY_THRESHOLD continues to adapt
# after this.
#
# Phase 11.9 (Step 5): raised from 1.0 to 2.0, based on measured
# evidence from the Phase 11.8 live validation session, not a guess -
# two separate 1.0s calibrations in the SAME room produced energy_
# thresholds of 385.96 and 570.17 (a ~48% swing), and that session's
# console log showed nearly every idle wake-word cycle registering
# "speech starting" on plain ambient noise (recognizer.listen()
# proceeding to a full recognition attempt almost every cycle, rather
# than timing out on true silence). A longer calibration window
# samples more of the room's actual noise floor before committing to a
# threshold, which SpeechRecognition's own adjust_for_ambient_noise()
# documentation identifies as the intended lever for a noisier or more
# variable environment. DYNAMIC_ENERGY_THRESHOLD (unchanged, still
# True) keeps adapting after this initial calibration regardless.
AMBIENT_NOISE_DURATION = 2.0

# Listening timeouts (seconds) / phrase limits
WAKE_LISTEN_TIMEOUT = 3
WAKE_PHRASE_LIMIT = 5

COMMAND_LISTEN_TIMEOUT = 5
COMMAND_PHRASE_LIMIT = 8

# Retries of the recognize_google() API call itself (same captured audio,
# no re-listening) - for transient network/API errors.
SPEECH_API_RETRIES = 1
SPEECH_API_RETRY_DELAY = 1.0

# Retries of listening again (asking the user to repeat) after the wake
# word, only used when nothing could be understood at all.
COMMAND_RECOGNITION_RETRIES = 1

# Minimum seconds between spoken "trouble connecting" warnings, so a
# prolonged outage doesn't repeat the announcement every listen cycle.
REQUEST_ERROR_ANNOUNCE_COOLDOWN = 30

# Text-to-speech
#
# TTS_RATE/TTS_VOLUME (unchanged since the original single-file
# version) configure the pyttsx3 (Windows SAPI5) fallback engine only -
# see voice.Voice.__init__(). TTS_VOLUME is ALSO applied to the neural
# backend's synthesized audio (see tts_backend.KokoroBackend.speak()),
# so both engines respect the same single volume knob; TTS_RATE has no
# neural-backend equivalent (see TTS_SPEED below instead - pyttsx3's
# "words per minute" and Kokoro's speech-rate multiplier are different
# units, so this project intentionally keeps them as two separate
# config values rather than trying to convert between them).
TTS_RATE = 175
TTS_VOLUME = 1.0

# Phase 11.13: pretrained neural TTS (Kokoro-82M, via kokoro-onnx - see
# tts_backend.py). "kokoro" tries the neural backend first and falls
# back to pyttsx3 on ANY failure (missing dependency, missing model
# files - never committed to this repo, see README.md - or a
# synthesis/playback error); "pyttsx3" skips the neural backend
# entirely and reproduces the exact original Phase 1-11.12 behavior.
# Default "kokoro" - safe even before the model is downloaded, since
# tts_backend.KokoroBackend.is_available() reports False (not an
# error) until both model files exist on disk, and voice.Voice falls
# back to pyttsx3 in that case exactly as if this were "pyttsx3".
TTS_BACKEND = "kokoro"

# One of kokoro_onnx's ~54 built-in voices (American/British English,
# plus several other languages - see the Phase 11.13 audit report for
# the full list). "af_heart" was chosen after listening to several
# candidates as the warmest/most natural-sounding of Kokoro's American
# English voices for this project's "calm, pleasant, slightly warm"
# requirement - see tts_backend.KokoroBackend.synthesize()'s `voice`
# parameter.
TTS_VOICE = "af_heart"

# Kokoro's speech-rate multiplier (1.0 = the model's natural default
# pace, NOT the same unit as TTS_RATE's "words per minute" - see that
# constant's own comment above).
TTS_SPEED = 1.0

# ONNX Runtime execution provider for the neural backend. Deliberately
# "cpu", NOT "cuda", by default - matching OFFLINE_STT_DEVICE's own
# precedent and reasoning exactly (see that constant below): this
# machine's NVIDIA driver reports CUDA 13.2 support, but attempting the
# CUDAExecutionProvider fails with "Error loading ... which depends on
# 'cublasLt64_13.dll' which is missing" - the actual CUDA Toolkit
# runtime/cuDNN libraries aren't installed, only the driver. Measured
# CPU-only latency is already well within acceptable range for this
# project's short spoken responses (see the Phase 11.13 audit report),
# so this is not currently a blocker. Setting this to "cuda" is safe
# either way - tts_backend.KokoroBackend._load() lists
# CPUExecutionProvider as a fallback, and onnxruntime itself silently
# falls back (a console warning, not an exception) if CUDA can't
# actually load - but it won't actually use the GPU until the missing
# runtime libraries are installed, a separate, approval-gated
# dependency decision exactly like OFFLINE_STT_DEVICE's own.
TTS_DEVICE = "cpu"

# Phase 11.14: if voice.Voice.speak() is asked to speak the exact same
# text twice within this many seconds, the second call is not re-
# synthesized/re-played (defense against an accidental duplicate
# dispatch producing the same response twice in quick succession -
# never observed as an actual bug in this codebase, but cheap and safe
# to guard against). Deliberately short - this must never suppress a
# genuinely repeated command ("jarvis scroll down" said twice on
# purpose a few seconds apart must always both scroll) - same
# "cooldown, not a permanent block" shape as speech.
# REQUEST_ERROR_ANNOUNCE_COOLDOWN, just a much shorter window since
# this guards against near-simultaneous accidental duplicates, not a
# slow network retry loop.
DUPLICATE_SPEECH_SUPPRESS_SECONDS = 2.0

# Diagnostics - when True, prints extra pipeline details (normalized
# command, wake-word match info) to the console. Off by default so
# normal output stays clean.
DEBUG = False

# Phase 9: when True, "lock computer"/"shutdown computer"/"restart
# computer" speak a confirmation prompt and require an explicit "yes"/
# "confirm"/"confirmed" reply (the wake word must be said again, same
# as any other command) before actually executing - see
# commands.CommandProcessor. Default False reproduces the exact
# behavior these commands have had since Phase 3 (immediate execution,
# no confirmation) - existing tests rely on this default and must keep
# passing unmodified.
REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS = False

# Phase 10.1: offline speech-to-text fallback, used only when the
# online backend (Google) fails to produce text - see stt_backend.py.
# Safe to leave True unconditionally: stt_backend.OfflineWhisperBackend
# .is_available() reports False (a normal, expected, non-error result)
# whenever its optional `faster_whisper` dependency isn't installed,
# so this flag being True has no effect until that dependency is
# actually installed. Set False to skip the offline attempt entirely
# even if the dependency later becomes available.
OFFLINE_STT_ENABLED = True

# Model size passed to speech_recognition's recognize_faster_whisper()
# adapter - see https://github.com/SYSTRAN/faster-whisper for the full
# list ("tiny", "base", "small", "medium", "large-v3", ...). Only takes
# effect once the `faster_whisper` package is installed.
OFFLINE_STT_MODEL = "base"

# Device/compute type for the offline Whisper backend.
#
# Deliberately "cpu"/"int8", NOT "auto" or "cuda" - see the Phase 10.1
# faster-whisper validation report. On this machine, ctranslate2's
# CUDA device context initializes successfully (device="cuda" does
# not raise), but actual transcription then fails with
# "RuntimeError: Library cublas64_12.dll is not found or cannot be
# loaded" - the NVIDIA cuBLAS runtime is not present, and ctranslate2
# does NOT automatically fall back to CPU when this happens. Using
# "auto" would silently pick the broken CUDA path every time and the
# offline fallback would never actually produce text on this machine.
# "cpu"/"int8" is verified working (see the validation report) and
# requires no additional dependency beyond faster-whisper + soundfile.
# Revisit only after explicitly installing the missing NVIDIA cuBLAS
# runtime (a separate, approval-gated dependency decision).
OFFLINE_STT_DEVICE = "cpu"
OFFLINE_STT_COMPUTE_TYPE = "int8"

# Phase 11.4: Urdu STT fallback. When True, a SpeechUnintelligible
# result from the online English attempt (recognize_google() raised
# UnknownValueError - the service responded but couldn't transcribe
# the audio as English) triggers exactly one additional, non-retried
# recognize_google() attempt on the SAME captured audio with language=
# URDU_RECOGNITION_LANGUAGE, before falling through to the existing
# offline-Whisper fallback exactly as before - see speech.Speech.
# _try_urdu_fallback()/_recognize(). Deliberately NEVER attempted on a
# RecognitionNetworkError (RequestError) - a failed network/API call
# carries no information about the audio's language, and the existing
# SPEECH_API_RETRIES mechanism already owns retrying that specific
# failure on the same audio - see the Phase 11.4 architecture audit,
# section 6, for the full reasoning. No new dependency: recognize_
# google() and the "ur-PK" language code are both already supported by
# the already-installed SpeechRecognition package.
#
# Deliberately a SEPARATE flag from ENABLE_MULTILINGUAL_LAYER - input
# ACQUISITION (an extra network call) is a different risk category
# than TEXT NORMALIZATION of already-acquired text, the same "different
# risk profile deserves its own flag" reasoning ENABLE_REFERENCE_
# RESOLUTION already uses to justify its own flag distinct from
# ENABLE_CONTEXT_LAYER. The two flags are fully independent: Urdu
# speech can be transcribed with this flag alone (the resulting text
# simply won't match anything further downstream unless ENABLE_
# MULTILINGUAL_LAYER is also True), and ENABLE_MULTILINGUAL_LAYER works
# identically for any other text source regardless of this flag.
#
# Default False for initial rollout, matching how every Phase 9-11.3
# flag before it shipped default-off until dedicated validation.
ENABLE_URDU_STT_FALLBACK = False

# BCP-47 language code passed to recognize_google() for the Phase 11.4
# Urdu fallback attempt - externalized as its own constant, matching
# how RECOGNITION_LANGUAGE ("en-US") is already externalized rather
# than hardcoded inline.
URDU_RECOGNITION_LANGUAGE = "ur-PK"

# Phase 10.2: rule-based intent fallback layer (see intent_layer.py).
# Additive-only - only ever consulted after the existing deterministic
# command_parser.normalize() + dispatch chain has already failed to
# recognize a command (see commands.py's insertion point, immediately
# before the final "I don't know how to do that" fallback). Every
# intent it produces is rendered to a canonical command string and fed
# back into CommandProcessor.process() - never into a control module
# directly - so the Phase 9 dangerous-command gate cannot be bypassed.
# Default False for initial rollout, matching how
# REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS itself shipped
# default-off until dedicated validation - see the Phase 10.2 rollout
# report for what was actually verified before recommending a default.
ENABLE_INTENT_FALLBACK_LAYER = True

# Minimum confidence (0.0-1.0) an intent_layer.IntentFrame must have to
# be acted on. Below this, the frame is dropped and the existing
# "I don't know how to do that" response is used instead - the same
# fail-closed philosophy already used throughout this project (e.g.
# natural_language.split_into_clauses()'s all-or-nothing split,
# command_parser.canonicalize_set_volume_phrase()'s reject-not-clamp
# policy for out-of-range volume).
INTENT_CONFIDENCE_THRESHOLD = 0.6

# Phase 10.3: conversational context / pending-slot-filling layer (see
# context_manager.py). Additive-only, deliberately narrow - only
# SEARCH's missing query is ever slot-filled ("search youtube" ->
# "What should I search for?" -> "Spider-Man" -> the existing
# "search for <query>" command, fed back through CommandProcessor.
# process() exactly like every other layer in this project - never
# executed directly). Only takes effect when config.ENABLE_INTENT_
# FALLBACK_LAYER is ALSO True, since intent_layer.understand() is what
# discovers an incomplete SEARCH frame in the first place. Default
# False for initial rollout, same rollout discipline as
# ENABLE_INTENT_FALLBACK_LAYER itself - see the Phase 10.3
# implementation report for what was actually verified before
# recommending a default.
ENABLE_CONTEXT_LAYER = False

# How many CommandProcessor.process() calls a pending slot request
# (see context_manager.PendingSlotRequest) stays valid for before it's
# treated as expired and the next utterance is processed as a fresh
# command instead. 1 means "must be answered by the very next command"
# - matching the worked example (ask, then the immediate next reply
# answers it). Purely a UX bound, not a safety boundary - see
# context_manager.is_pending_expired()'s docstring.
CONTEXT_SLOT_MAX_TURNS = 1

# How many seconds a pending slot request stays valid for, regardless
# of turn count - guards against a long real-world pause between the
# question and an eventual, now-stale reply. Purely a UX bound, not a
# safety boundary - see context_manager.is_pending_expired()'s
# docstring.
CONTEXT_SLOT_TTL_SECONDS = 30

# Phase 10.4: contextual reference resolution (see context_manager.py)
# - "it"/"that"/"this" resolved against the last-named application
# only (e.g. "open chrome" ... later ... "close it" -> "close
# chrome"). Deliberately narrow - no other reference (a previous
# search result, a previous website) is resolved by this phase; see
# the Phase 10.4 architecture audit for why those are out of scope.
# Independent of ENABLE_CONTEXT_LAYER on purpose - this is a
# different, separately-validated capability with a different risk
# profile (it can render into a real window/application action, not
# just a search string), so it gets its own flag and its own rollout
# decision. Default False for initial rollout, same rollout discipline
# as every flag before it - see the Phase 10.4 implementation report
# for what was actually verified before recommending a default.
ENABLE_REFERENCE_RESOLUTION = False

# How many CommandProcessor.process() calls the last-named-application
# record (see context_manager.ConversationContext.record()) stays
# valid for before a reference ("it"/"that"/"this") to it is treated
# as expired. Deliberately conservative/short - unlike CONTEXT_SLOT_
# MAX_TURNS above, this IS load-bearing for safety, not just UX, since
# a resolved reference can trigger a real window/application action -
# see context_manager.is_reference_expired()'s docstring.
REFERENCE_MAX_TURNS = 3

# How many seconds the last-named-application record stays valid for,
# regardless of turn count. Same safety rationale as REFERENCE_MAX_
# TURNS above - see context_manager.is_reference_expired()'s
# docstring.
REFERENCE_TTL_SECONDS = 45

# Phase 10.5: repeat-search ("search that again" -> "search for
# <previous_query>" - see context_manager.py). Reuses config.
# ENABLE_REFERENCE_RESOLUTION above - deliberately NOT a separate flag
# - this is the same "resolve a reference to something recently named"
# capability family as Phase 10.4, just a second, independently-
# tracked kind of memory (a search query, not an application) rather
# than a materially different risk profile that would justify its own
# rollout decision. See the Phase 10.5 architecture audit.
#
# How many CommandProcessor.process() calls the last-search-query
# record (see context_manager.ConversationContext.record_search())
# stays valid for before "search that again" is treated as expired.
# Tracked entirely independently of REFERENCE_MAX_TURNS above (see
# context_manager.is_search_expired()'s docstring) - naming an
# application and searching never share or reset each other's expiry
# clock.
SEARCH_REPEAT_MAX_TURNS = 3

# How many seconds the last-search-query record stays valid for,
# regardless of turn count. Same independence rationale as SEARCH_
# REPEAT_MAX_TURNS above - see context_manager.is_search_expired()'s
# docstring.
SEARCH_REPEAT_TTL_SECONDS = 45

# Phase 11.1: deterministic Urdu-script + Roman-Urdu normalization layer
# (see multilingual_normalizer.py). Additive-only, same architectural
# shape as ENABLE_INTENT_FALLBACK_LAYER (Phase 10.2) - only ever
# consulted after the entire existing deterministic pipeline (clause
# splitting, command_parser.normalize(), the fixed dispatch chain, AND
# the Phase 10.2 intent fallback) has already failed to recognize a
# command - see commands.py's insertion point. Every phrase it
# recognizes is rendered to one of the exact same fixed canonical
# command strings the existing handlers already understand (almost
# entirely via intent_parser.to_canonical_command()'s own allow-list-
# gated rendering, reused unmodified) and fed back into
# CommandProcessor.process() - never into a control module directly -
# so the Phase 9 dangerous-command gate cannot be bypassed by anything
# this layer produces.
#
# Deliberately independent of ENABLE_INTENT_FALLBACK_LAYER/
# ENABLE_CONTEXT_LAYER/ENABLE_REFERENCE_RESOLUTION - a new input
# *language* is a different risk/capability category than a new
# phrasing of an already-supported language, so it gets its own flag
# and its own rollout decision, matching how ENABLE_REFERENCE_
# RESOLUTION already got its own flag distinct from ENABLE_CONTEXT_
# LAYER for the same reasoning.
#
# Phase 11.1 deliberately implements NO dangerous-command
# (lock/shutdown/restart) recognition of any kind, in any language -
# see multilingual_normalizer.py's module docstring and the Phase 11.0
# architecture audit, section D. That is explicit, separate, future
# Phase 11.2 scope, not silently included here.
#
# Default False for initial rollout, matching how every Phase 9-10.5
# flag before it shipped default-off until dedicated validation - see
# the Phase 11.1 implementation report for what was actually verified
# before recommending any default.
ENABLE_MULTILINGUAL_LAYER = True

# Phase 11.9 (Step 3): wake-word-omission tolerance. The Phase 11.8
# live validation session directly observed Google STT twice dropping
# the word "jarvis" from an otherwise-correctly-transcribed utterance
# ("jarvis time kya hai" -> "time kya hai"; "jarvis volume kam kar do"
# -> "awaaz kam kar do") - with the current architecture (wake-word
# detection is a post-hoc word-boundary search over ONE already-
# recognized transcript - see jarvis.extract_command_after_wake_word()),
# that silently discards the ENTIRE utterance, including an otherwise-
# perfectly-usable command, with no recovery at all.
#
# When True, jarvis.Jarvis._maybe_recover_omitted_wake_word() is
# consulted whenever the wake word is NOT found in a heard utterance:
# it resolves the utterance through the SAME two existing, already-PURE
# fallback resolvers CommandProcessor.process() itself uses (intent_
# layer.py, multilingual_normalizer.py - see jarvis.resolve_wake_word_
# omission(), never a new/parallel classifier) and, ONLY if that
# produces a single, confident, non-dangerous canonical command, speaks
# a "Did you mean: <command>? Say yes to confirm." prompt and waits for
# an explicit affirmative reply before executing anything - through the
# exact same CommandProcessor.process() path every other command uses,
# so the Phase 9 dangerous-command gate and every other existing safety
# check still applies to the actual execution. JARVIS never silently
# executes a command that arrived without its wake word, with this flag
# on or off. See resolve_wake_word_omission()'s own docstring for the
# additional, structural (not just policy) guarantee that a dangerous
# command is never even offered this way, regardless of this flag.
#
# Deliberately narrower than the full primary if/elif dispatch chain:
# a plain command already recognized by that chain's own bare-substring
# handlers (e.g. "open chrome" with no wake word, caught by web_
# control.handle()) is NOT specifically targeted by this path - it
# reuses only the two PURE fallback resolvers, precisely because
# reusing them (rather than building a new dry-run mode for the entire
# primary dispatch chain) is the smallest safe extension that directly
# covers both live-observed failures, without duplicating or modifying
# any existing control-module dispatch logic.
#
# Default False for initial rollout, matching how every Phase 9-11.7
# flag before it shipped default-off until dedicated validation.
ENABLE_WAKE_WORD_OMISSION_TOLERANCE = False

# Phase 11.11 (Step 5/6): Whisper confidence gate. faster-whisper's own
# transcribe() call (reached via speech_recognition's recognize_faster_
# whisper(..., show_dict=True) - see stt_backend.OfflineWhisperBackend.
# recognize()) returns, per segment, avg_logprob (average log-
# probability of the decoded tokens - higher/less-negative is more
# confident) and no_speech_prob (the model's own probability that the
# segment contains no speech at all - higher means more likely
# silence/noise). When this flag is True, stt_backend._whisper_result_
# is_low_confidence() rejects (raises SpeechUnintelligible instead of
# returning text) a transcription whose segments are, on average, at or
# beyond the thresholds below - turning an obviously unreliable
# hallucination (the Phase 11.10 live session repeatedly observed
# Whisper inventing fluent-sounding but entirely unrelated text from
# ambient noise/silence - Finnish, Japanese, Devanagari, repeated
# stock phrases) into the same "nothing recognized" outcome silence
# already produces, rather than a string that reaches wake-word
# matching or the Phase 11.9 recovery path.
#
# IMPORTANT: this does not change JARVIS's ability to safely reject
# uncertain input to begin with - the wake-word requirement (and, for
# ENABLE_WAKE_WORD_OMISSION_TOLERANCE's narrow recovery path, the
# explicit spoken confirmation) already prevent a hallucination from
# ever becoming an executed command on their own; this flag only
# improves SIGNAL QUALITY earlier in the pipeline (fewer false "Did you
# mean...?" prompts caused by hallucinated text that happens to
# resemble a known command).
#
# Default False, and the two threshold constants below are explicitly
# PROVISIONAL - chosen from faster-whisper's own community-documented
# "likely not real speech" ranges, not from live-measured data specific
# to this project's microphone/room/model - Phase 11.11 was explicitly
# scoped to NOT perform a live validation round (see the Phase 11.11
# report). Tuning these two values with real audio-energy/confidence
# data from a live session is exactly the kind of measurement Phase
# 11.9's AMBIENT_NOISE_DURATION change was held to, and is recommended
# as Phase 11.12's first task before this flag is ever turned on.
ENABLE_WHISPER_CONFIDENCE_GATE = False
WHISPER_MAX_NO_SPEECH_PROB = 0.6
WHISPER_MIN_AVG_LOGPROB = -1.0
