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
AMBIENT_NOISE_DURATION = 1.0

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
TTS_RATE = 175
TTS_VOLUME = 1.0

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
