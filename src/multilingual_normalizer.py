"""Phase 11.1: deterministic Urdu-script + Roman-Urdu normalization layer.

Additive-only, same architectural shape as intent_layer.py (Phase 10.2)
and context_manager.py (Phase 10.3-10.5). understand() is only ever
consulted from commands.py AFTER the entire existing deterministic
pipeline (natural_language.split_into_clauses() -> command_parser.
normalize() -> the fixed if/elif dispatch chain -> the Phase 10.2
intent fallback layer) has already failed to recognize a command - see
commands.py's insertion point, immediately before the Phase 10.4/10.5
reference-resolution block.

Design (see the Phase 11.0 architecture audit, sections C/D/E):

- Presence-based, phrase-level matching, not grammar/word-order
  parsing. Each concept (open/close/mute/volume-up/...) is recognized
  by one or more fixed Urdu-script or Roman-Urdu marker PHRASES (never
  a single generic helper word like bare "karo") appearing anywhere in
  the text, deliberately mirroring this project's own existing
  substring-matching style (web_control.handle()'s bare "chrome" check,
  intent_parser.classify()'s own "name in text" checks). This also
  naturally supports mixed-language commands ("chrome کھولو") and
  Urdu's verb-final (SOV) word order without needing to parse grammar -
  order of the marker phrase and the entity (e.g. an application name)
  never matters. Phase 11.3.1: "presence" is word-boundary-anchored,
  not a bare substring - see _contains_any_bounded() below - so a
  marker can never accidentally match as part of a longer, unrelated
  word (e.g. "mute karo" must not match inside "mute karobar"). Phase
  11.3.2: a small, deliberately selective set of additional Roman-Urdu
  spelling/imperative variants ("khol dou"; a "kar do" split-imperative
  counterpart for mute/unmute/volume-up/volume-down only, each derived
  mechanically from an ALREADY-PRESENT "...karo" form in that same
  concept; "daba do" for all four PRESS_KEY_MARKERS; "chala do" for
  PLAY_MARKERS) were appended to the existing GENERAL-vocabulary
  tuples - never the frozen Phase 11.2 dangerous-command vocabulary,
  which this phase does not touch in any way.
- Every recognized concept is rendered via intent_parser.
  to_canonical_command() (reused, UNMODIFIED, exactly as intent_layer.py
  already does) wherever an intent_parser.Intent exists for it - never
  a hand-built string. This means every one of those outputs inherits
  intent_parser's own allow-list validation for free (KNOWN_APPLICATIONS
  for OPEN_APPLICATION, KNOWN_KEYS for PRESS_KEY, the 0-100 range check
  for SET_VOLUME) - this module cannot loosen or bypass any of those
  checks even by accident.
- Exactly two outputs ("hello" for a greeting, "exit" for an exit
  phrase) are NOT rendered through intent_parser, because intent_parser.
  Intent has no GREETING/EXIT category at all (documented, pre-existing
  limitation - see natural_language.py's own module docstring, "intent_
  parser.classify() does not cover exit words or greetings"). These two
  are returned as fixed Python string literals written directly in this
  module's source - not derived from, or containing, any user-supplied
  text - so they are trivially auditable.

SAFETY - what this module can NEVER produce, structurally, not just by
policy:

- Every non-dangerous concept below is rendered via intent_parser.
  to_canonical_command() (reused, UNMODIFIED - see intent_parser.py,
  which has NO LOCK_COMPUTER/SHUTDOWN_COMPUTER/RESTART_COMPUTER member
  and never will, by design - it stays diagnostics-only and fixed-shape
  since Phase 5). intent_parser itself remains structurally incapable
  of producing a dangerous command.
- Phase 11.2 ADDS dangerous-command (lock/shutdown/restart) recognition
  - see _check_dangerous()/understand_dangerous() below - as a
  DELIBERATE, NARROWLY SCOPED exception to "always render via
  intent_parser", because intent_parser structurally cannot represent
  these three commands at all (see above). This is the ONLY place in
  this module that does not render through intent_parser.
  _check_dangerous() can return ONLY one of three fixed Python string
  literals - "lock computer", "shutdown computer", "restart computer",
  written directly in this module's source, byte-for-byte identical to
  commands.DANGEROUS_COMMANDS (verified directly by tests/test_
  multilingual_normalizer.py, which imports commands.DANGEROUS_COMMANDS
  for exact parity, not just eyeballing string equality) - never built
  from user text via concatenation, f-string, or .format(). Recognition
  itself requires an explicit, multi-word, noun-plus-action regex (see
  _dangerous_pattern() below) - the Urdu/Roman-Urdu word for "computer"
  ("کمپیوٹر"/"computer") MUST be present alongside a specific two-word
  action+helper-verb phrase (e.g. "lock karo", "بند کرو") - never a
  single generic word like bare "lock"/"karo"/"کرو" alone, and never a
  bare substring match on the noun alone either (e.g. "chrome بند کرو"
  - no "computer"/"کمپیوٹر" noun present - is proven, by a dedicated
  test, to NOT be recognized as dangerous).
- This module is PURE: it never imports voice, any control module
  (web_control, system_control, window_control, volume_control,
  media_control, keyboard_control, screen_control), or `commands`
  itself (which would be a circular import in any case, since commands.
  py imports this module) - grep this file: none of those names appear
  anywhere below. It has no `subprocess`, `os.system`, `ctypes`,
  `comtypes`, `eval(`, or `exec(` anywhere in it either. It cannot
  execute anything by itself, even in principle - verified directly by
  tests/test_multilingual_normalizer.py's structural import test, not
  just by convention.
- Every string this module can return is handed back to
  CommandProcessor.process() by the CALLER (commands.py) - recursively,
  exactly like the Phase 10.2 intent-fallback loop and the Phase 10.3-
  10.5 context layer already do - so the Phase 9 dangerous-command
  gate (the unconditional first check on every process() call,
  including recursive ones) still sees every command this module
  produces. This module has no reference to a CommandProcessor and
  cannot call self.process() or anything resembling it - the recursion
  contract is enforced entirely by the caller, by construction (see
  commands.py's Phase 11.1 insertion point).

No LLM or external AI/translation service, no new third-party
dependency - plain deterministic string/regex matching, same style as
command_parser.py, intent_parser.py, and intent_layer.py.

WHAT IS SUPPORTED (Phase 11.1 + Phase 11.2):

- Dangerous commands (Phase 11.2): lock/shutdown/restart, recognized
  from an explicit "computer"/"کمپیوٹر" noun plus a two-word action+
  helper-verb phrase (optionally separated by "ko"/"کو") - see
  _check_dangerous() below for the exact supported phrasings. Rendered
  to ONLY "lock computer"/"shutdown computer"/"restart computer" - the
  exact same three phrases commands.DANGEROUS_COMMANDS already gates on
  - and handed back to CommandProcessor.process() exactly like every
  other output of this module, so the Phase 9 confirmation gate always
  sees it.
- OPEN_APPLICATION for all of intent_parser.KNOWN_APPLICATIONS.
- Volume up/down, mute/unmute, set-volume-to-<N>-percent.
- Window control: minimize/maximize/restore/close window/switch
  window/show desktop.
- Media: play/pause, next track, previous track.
- Screenshot.
- Keyboard: press enter/escape/space/tab, copy, paste, select all, undo.
- Scroll up/down (Phase 11.5) - rendered as the fixed literals "scroll
  up"/"scroll down", dispatched by the new keyboard_control.scroll_up()
  /scroll_down() (Page Up/Page Down), same fixed-shortcut pattern as
  every other keyboard_control.py action.
- A generic "browser" open (Phase 11.5, plus "brouser"/"broser"
  misspellings) - rendered as the fixed literal "open chrome"; not an
  intent_parser.KNOWN_APPLICATIONS entry.
- Search (free-text query, extracted from a suffix or prefix marker
  phrase - never executed, only ever URL-encoded downstream exactly
  like every other SEARCH command in this project, per intent_parser.
  py's own module docstring).
- Time, date, a greeting ("hello", including "kaise ho"/"kaisay ho"/
  "kese ho"/"kesay ho" - Phase 11.5), and an exit phrase ("exit",
  including "band ho jao"/"off ho jao"/bare "band karo" - Phase 11.5;
  never the dangerous shutdown/restart path).

WHAT IS EXPLICITLY OUT OF SCOPE (Phase 11.1/11.2/11.5) - see the Phase
11.0 architecture audit and the Phase 11.1/11.2 implementation reports:

- STT language fallback (speech.py/stt_backend.py changes) - Phase
  11.4, already implemented separately (see config.ENABLE_URDU_STT_
  FALLBACK) - unrelated to and untouched by this module.
- TTS/spoken-response localization (voice.py changes) - explicitly
  deferred per the Phase 11.0 audit, section G.
- An Urdu/Roman-Urdu wake-word alias (jarvis.py changes) - Phase 11.6.
- Any ML model, translation API, or browser automation.
- Vocabulary coverage is intentionally initial/bounded, not exhaustive
  of every possible Urdu/Roman-Urdu phrasing - the same incremental,
  narrowly-scoped discipline this project has used since Phase 8.
  Expanding coverage later is safe and additive: it only ever means
  adding more marker phrases to the existing dictionaries/regexes
  below, never changing this module's structure or its safety
  properties.
"""

import re

import intent_parser


# ---------------------------------------------------------------------
# Phase 11.2: dangerous-command (lock/shutdown/restart) recognition.
#
# Deliberately its OWN, more restrictive pattern shape than every other
# concept in this module - see the module docstring's SAFETY section.
# Requires the "computer"/"کمپیوٹر" NOUN, word-boundary-anchored, plus a
# two-word ACTION+HELPER-VERB phrase (also word-boundary-anchored, so
# "lock karo" can never partially match inside a longer word like
# "karobar") - an optional "ko"/"کو" (a grammatical object marker, not
# meaningful on its own) may sit between them. Both orderings verified
# by tests: noun-then-action (every example in the Phase 11.2 spec) is
# the only order supported - this is NOT a bare "contains all of these
# words anywhere" check, unlike the presence-based style used
# everywhere else in this module, precisely because a single-word or
# unordered check here would make "chrome بند کرو" ("close chrome")
# indistinguishable from a shutdown command. That distinction is the
# reason this concept gets a dedicated regex-builder instead of reusing
# _contains_any_bounded().
# ---------------------------------------------------------------------

_DANGEROUS_NOUN = r"\b(?:computer|کمپیوٹر)\b"
_DANGEROUS_KO = r"(?:\b(?:ko|کو)\b\s+)?"

# Each entry is a full two-word "<action> <helper-verb>" phrase - never
# a single generic word (no bare "lock"/"shutdown"/"restart"/"band"/
# "karo"/"کرو" anywhere in this module, per the Phase 11.2 architecture
# constraint). Covers the exact-language, Roman-Urdu, Urdu-script, and
# mixed-language forms given in the Phase 11.2 specification, plus the
# small number of directly symmetric variants (e.g. "shutdown karo"
# alongside the given "band karo"/"computer شٹ ڈاؤن کرو"-style mixed
# form) needed so the EN-action/UR-verb and UR-action/EN-verb mixed
# shapes are both covered for all three actions, not just the two the
# spec happened to give worked examples for.
LOCK_ACTION_PHRASES = ("lock karo", "lock کرو", "لاک کرو", "لاک karo")
SHUTDOWN_ACTION_PHRASES = (
    "band karo", "band کرو", "بند کرو", "بند karo",
    "shutdown karo", "shutdown کرو",
)
RESTART_ACTION_PHRASES = (
    "restart karo", "restart کرو", "ری اسٹارٹ کرو", "ری اسٹارٹ karo",
)


def _dangerous_pattern(action_phrases):
    alternation = "|".join(re.escape(phrase) for phrase in action_phrases)
    return re.compile(
        _DANGEROUS_NOUN + r"\s+" + _DANGEROUS_KO + r"\b(?:" + alternation + r")\b"
    )


LOCK_DANGEROUS_RE = _dangerous_pattern(LOCK_ACTION_PHRASES)
SHUTDOWN_DANGEROUS_RE = _dangerous_pattern(SHUTDOWN_ACTION_PHRASES)
RESTART_DANGEROUS_RE = _dangerous_pattern(RESTART_ACTION_PHRASES)


# ---------------------------------------------------------------------
# Vocabulary - Urdu-script and Roman-Urdu marker phrases per concept.
#
# Deliberately PHRASE-level (two or more words), not single generic
# helper words like bare "karo"/"کرو" - so unrelated concepts that
# happen to share a common helper verb (e.g. "band karo" for close and
# "khamosh karo" for mute both use "karo") never collide. Presence of
# the FULL marker phrase anywhere in the text is what's checked, not
# word order relative to any entity (like an application name) also
# present in the text - this is what makes both "chrome کھولو" and
# "کھولو chrome" (and the mixed-language "chrome kholo") resolve the
# same way, without needing to parse Urdu's verb-final (SOV) grammar.
# ---------------------------------------------------------------------

OPEN_MARKERS = (
    "کھولو", "کھول دو", "کھول دیں", "کھول دیجیے",
    "kholo", "khol do", "khol dein", "khol den", "khol dijiye",
    "khol dou",  # Phase 11.3.2: common casual misspelling of "khol do"
    # Phase 11.5: mixed-language "<English open verb> karo" imperative -
    # a distinct two-word marker (never bare "karo" alone, same
    # discipline as every other marker in this module), needed for
    # phrases like "browser open karo"/"chrome open karo" that use the
    # English verb "open" with the Urdu helper verb "karo" instead of
    # any "kholo"/"khol do" form.
    "open karo",
)

# Phase 11.5: generic "browser" word (plus two common STT misspellings,
# "brouser"/"broser") - NOT an intent_parser.KNOWN_APPLICATIONS entry
# (that allow-list stays untouched), so a browser phrase is rendered as
# the fixed literal "open chrome" directly (see _check_open_browser()
# below) - same "fixed Python literal, not derived from user text"
# pattern already used for "hello"/"exit". Phase 11.7: added the
# Urdu-script transliteration "براؤزر".
BROWSER_WORD_MARKERS = ("browser", "brouser", "broser", "براؤزر")

# Phase 11.7: safe, targeted "close <application>" - routes through the
# EXISTING, already-tested window_control.handle_targeted() mechanism
# (Phase 6) by rendering the plain canonical string "close <app>" (or
# "close chrome" for a generic browser word - see _check_close_
# application() below), exactly the same canonical shape English
# phrases like "close chrome" already produce. This is what keeps
# "chrome band karo"/"chrome close karo"/"browser band karo" etc. from
# ever being confused with EXIT: they now resolve to a real, correct,
# safe action instead of either exiting JARVIS or silently doing
# nothing. "band karo"/"band kar do"/"بند کرو" are shared with the
# Phase 11.2 dangerous SHUTDOWN_ACTION_PHRASES vocabulary - never a
# collision in practice, because _check_dangerous() (which requires the
# "computer"/"کمپیوٹر" noun immediately adjacent) is always checked
# FIRST in _CHECKERS, so "computer band karo" is already claimed as a
# shutdown before this marker is ever reached; only when the noun is
# NOT "computer" (e.g. "chrome") does this marker apply.
CLOSE_APP_MARKERS = (
    "band karo", "band kar do", "close karo", "close kar do",
    "بند کرو", "بند کر دو",
)

MINIMIZE_MARKERS = (
    "چھوٹا کرو", "مینیمائز کرو",
    "chota karo", "minimize karo",
)
MAXIMIZE_MARKERS = (
    "بڑا کرو", "میکسیمائز کرو",
    "bara karo", "maximize karo",
)
RESTORE_MARKERS = (
    "بحال کرو", "ریسٹور کرو",
    "bahal karo", "restore karo",
)
CLOSE_WINDOW_MARKERS = (
    "ونڈو بند کرو",
    "window band karo",
)
SWITCH_WINDOW_MARKERS = (
    "ونڈو تبدیل کرو", "دوسری ونڈو",
    "window tabdeel karo", "switch window karo", "dusri window",
)
SHOW_DESKTOP_MARKERS = (
    "ڈیسک ٹاپ دکھاؤ",
    "desktop dikhao",
)

PLAY_MARKERS = (
    "چلاؤ", "پلے کرو", "chalao", "play karo",
    "chala do",  # Phase 11.3.2: split-imperative form of "chalao"
)
PAUSE_MARKERS = ("روکو", "پاز کرو", "roko", "pause karo")
NEXT_TRACK_MARKERS = (
    "اگلا گانا", "اگلا ٹریک",
    "agla gana", "agla gaana", "next track",
)
PREVIOUS_TRACK_MARKERS = (
    "پچھلا گانا", "پچھلا ٹریک",
    "pichla gana", "pichla gaana", "previous track",
)

SCREENSHOT_MARKERS = (
    "اسکرین شاٹ لو", "اسکرین شاٹ", "تصویر لو",
    "screenshot lo", "tasveer lo",
)

UNMUTE_MARKERS = (
    "غیر خاموش کرو", "آواز واپس لاؤ", "ان میوٹ کرو",
    "unmute karo", "awaz wapas lao", "un mute karo",
    # Phase 11.3.2: split-imperative ("kar do") counterparts of the two
    # existing "...karo" forms above - "awaz wapas lao" uses a
    # different verb ("lao", not "karo") and has no "kar do" analog.
    "unmute kar do", "un mute kar do",
)
MUTE_MARKERS = (
    "خاموش کرو", "میوٹ کرو",
    "khamosh karo", "mute karo",
    # Phase 11.3.2: split-imperative ("kar do") counterparts of the two
    # existing "...karo" forms above.
    "khamosh kar do", "mute kar do",
)
VOLUME_UP_MARKERS = (
    "آواز بڑھاؤ", "آواز زیادہ کرو",
    "awaz barhao", "awaz zyada karo", "volume barhao",
    # Phase 11.3.2: split-imperative ("kar do") counterpart of "awaz
    # zyada karo" - "awaz barhao"/"volume barhao" use a different verb
    # ("barhao", not "karo") and have no "kar do" analog.
    "awaz zyada kar do",
    # Phase 11.5: additional Roman-Urdu "raise the volume" phrasings
    # and common STT misspellings ("barha"/"bara" for "badha", "jyada"
    # for "zyada") - each spelled out as its own explicit marker phrase
    # rather than a substring find/replace pass, matching this module's
    # existing enumerate-the-variant style.
    "volume badha do", "volume barha do", "volume bara do",
    "volume zyada kar do", "volume jyada kar do",
    "awaaz badha do", "awaz barha do",
    # Phase 11.7: "thora"/"zara" ("a little"/"a bit") intensifier
    # variants - explicit, bounded literal phrases (never a generic
    # "optional word in the middle" regex, which could let arbitrary
    # words slip in between and widen this into a broad substring
    # rule), same enumerate-the-variant discipline as every other
    # marker in this module.
    "volume thora barha do", "volume thora badha do",
    "awaaz zara zyada karo", "awaz zara zyada karo",
)
VOLUME_DOWN_MARKERS = (
    "آواز کم کرو",
    "awaz kam karo", "volume kam karo",
    # Phase 11.3.2: split-imperative ("kar do") counterparts of the two
    # existing "...karo" forms above.
    "awaz kam kar do", "volume kam kar do",
    # Phase 11.5: additional Roman-Urdu "lower the volume" phrasings.
    "volume neeche karo", "awaaz kam kar do",
    # Phase 11.7: "thora" ("a little") intensifier variants.
    "volume thora kam karo", "volume thora kam kar do",
)
VOLUME_WORD_MARKERS = ("آواز", "volume", "awaz", "awaaz")
PERCENT_MARKERS = ("فیصد", "percent", "%")

# Bug-fix-shaped policy, same reject-not-clamp reasoning as
# intent_layer.VOLUME_NUMBER_RE: capture the FULL numeric token
# (including any leading "-" or decimal point), then explicitly reject
# anything that isn't a clean, unsigned whole number - "-10 فیصد" and
# "40.5 percent" must never be silently reinterpreted as 10 or 5.
SET_VOLUME_NUMBER_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(?:" + "|".join(re.escape(p) for p in PERCENT_MARKERS) + r")"
)

# Phase 11.3.2: each key gained a "daba do" (split-imperative)
# counterpart of its existing "...dabao" form, for consistency across
# all four keys rather than partial coverage of just one.
# Phase 11.7: each key also gained an "<key> key dabao" form - English
# "key" inserted before the Roman-Urdu "dabao" verb (e.g. "enter key
# dabao"), a real, distinct phrasing from the existing "<key> dabao"
# form above, not a substring of it.
PRESS_KEY_MARKERS = {
    "enter": (
        "انٹر دباؤ", "enter dabao", "enter daba do", "enter key dabao",
    ),
    "escape": (
        "ایسکیپ دباؤ", "escape dabao", "escape daba do", "escape key dabao",
    ),
    "space": (
        "اسپیس دباؤ", "space dabao", "space daba do", "space key dabao",
    ),
    "tab": (
        "ٹیب دباؤ", "tab dabao", "tab daba do", "tab key dabao",
    ),
}
COPY_MARKERS = ("کاپی کرو", "copy karo")
PASTE_MARKERS = ("پیسٹ کرو", "paste karo")
SELECT_ALL_MARKERS = ("سب منتخب کرو", "sab select karo", "sab muntakhib karo")
UNDO_MARKERS = ("واپس کرو", "wapas karo", "undo karo")

# Phrase-final ("X <marker>") and phrase-initial ("<marker> X") search
# forms - Urdu is verb-final ("spider man تلاش کرو"), casual Roman Urdu
# sometimes puts the verb first ("search karo cats"). Both are checked;
# whichever matches extracts the remaining text, stripped, as the
# search query - never executed, only ever handed to web_control.
# search() as a URL-encoded query string downstream, exactly like every
# other SEARCH command in this project (see intent_parser.py's module
# docstring).
SEARCH_SUFFIX_MARKERS = ("تلاش کرو", "ڈھونڈو", "talash karo", "dhoondo", "search karo")
SEARCH_PREFIX_MARKERS = ("تلاش کرو", "search karo", "talash karo")

TIME_MARKERS = (
    "وقت کیا ہے", "waqt kya hai", "kitne baje hain",
    # Phase 11.7: mixed English noun + Urdu "kya hai" wrapper.
    "time kya hai",
)
DATE_MARKERS = (
    "تاریخ کیا ہے", "tareekh kya hai",
    # Phase 11.7: mixed English noun + Urdu "kya hai" wrapper - also
    # matches as a substring of "aaj ki date kya hai" (word-boundary
    # anchored, so the leading "aaj ki" prefix doesn't need its own
    # marker entry).
    "date kya hai",
)

# Phase 11.5: scroll up/down. Neither intent_parser.Intent nor
# intent_layer.py has a SCROLL category at all (this project had no
# scroll capability whatsoever, in any language, before this phase -
# see keyboard_control.scroll_up()/scroll_down(), the new fixed
# Page-Up/Page-Down keyboard shortcuts these two literals dispatch to),
# so - exactly like "hello"/"exit" - these are rendered as fixed Python
# string literals directly in this module's source, not through
# intent_parser.to_canonical_command(). "scroll up"/"scroll down" are
# also plain English, recognized directly by keyboard_control.handle()
# itself (part of the PRIMARY dispatch chain, before this layer is ever
# reached) - the markers below only need to cover the Roman-Urdu/mixed
# phrasings that chain wouldn't already catch.
SCROLL_UP_MARKERS = (
    "scroll upar", "scroll up", "upar scroll karo", "upar scroll kar do",
    # Phase 11.7: "oopar" spelling variant of "upar", and the Urdu-script
    # transliteration ("اسکرول" = scroll, "اوپر" = upar/up).
    "scroll oopar", "oopar scroll karo", "oopar scroll kar do",
    "اسکرول اوپر", "اوپر اسکرول کرو",
)
SCROLL_DOWN_MARKERS = (
    "scroll neeche", "scroll down", "neeche scroll karo", "neeche scroll kar do",
    # "niche" spelling variant of "neeche" (both common Roman-Urdu
    # spellings of the same word).
    "scroll niche", "niche scroll karo", "niche scroll kar do",
    # Phase 11.7: Urdu-script transliteration ("نیچے" = neeche/down).
    "اسکرول نیچے", "نیچے اسکرول کرو",
)

# Browser tab management (Roman-Urdu). "new tab"/"close tab"/"next
# tab"/"previous tab" are plain English, recognized directly by
# web_control.handle() itself (part of the PRIMARY dispatch chain,
# before this layer is ever reached) - only the Roman-Urdu phrasings
# need markers here, same "English already covered upstream" reasoning
# SCROLL_UP_MARKERS/SCROLL_DOWN_MARKERS above already use.
NEW_TAB_MARKERS = ("naya tab kholo", "nya tab kholo", "new tab kholo")
# "tab band" (Phase 11.12): a common clipped/STT-truncated form with no
# trailing helper verb ("karo"/"kar do") - still a distinct, unambiguous
# two-word phrase (never bare "band" alone), same "phrase, not a single
# generic helper word" discipline this module's docstring requires of
# every marker here.
CLOSE_TAB_MARKERS = ("tab band karo", "tab band kar do", "tab band")

# Browser navigation (Roman-Urdu). Phase 11.12: added "aage jao" (a
# common alternate spelling of "aagay jao"), "aglay page par jao"
# ("go to the next page" - a distinct, longer phrasing of the same
# GO_FORWARD intent) and, symmetrically, "peechay jao"/"peeche jao"
# (alternate spellings of "back") alongside the existing "wapas jao".
REFRESH_MARKERS = ("refresh karo",)
GO_BACK_MARKERS = ("wapas jao", "peechay jao", "peeche jao")
GO_FORWARD_MARKERS = (
    "aagay jao", "agay jao", "aage jao", "aglay page par jao",
)

GREETING_MARKERS = (
    "سلام", "السلام علیکم", "ہیلو", "salaam", "assalam", "hello",
    # Phase 11.5: "how are you" - each spelling variant is its own
    # marker phrase (word-boundary-anchored, via _contains_any_bounded()
    # below), so it's also matched as a substring of a longer greeting
    # like "aap kaise ho"/"tum kaise ho" without needing a separate
    # entry for every possible leading pronoun.
    "kaise ho", "kaisay ho", "kese ho", "kesay ho",
    # Phase 11.7: Urdu-script "how are you".
    "کیسے ہو",
)
EXIT_MARKERS = (
    "خدا حافظ", "الوداع", "khuda hafiz", "allah hafiz", "alvida",
    # Phase 11.5: safe JARVIS exit phrasings - equivalent to the
    # existing "exit"/"quit" path (see commands.EXIT_WORDS), never the
    # dangerous shutdown/restart path. "computer band karo" is already
    # claimed by the dangerous-command gate (_check_dangerous(), always
    # checked FIRST in _CHECKERS) before this marker is ever reached, so
    # this can never weaken that gate.
    "band ho jao", "band hojayo", "off ho jao", "off hojayo",
    # Phase 11.7: Urdu-script equivalents of the two phrases above.
    "بند ہو جاؤ", "آف ہو جاؤ",
)

# Phase 11.5/11.7: "band karo"/"بند کرو" ALONE are deliberately kept out
# of EXIT_MARKERS above and checked separately in _check_exit() - unlike
# every other exit phrase, they collide with a plausible unrelated
# meaning when a known application (or generic "browser") word is also
# present: "chrome band karo" most naturally reads as "close chrome",
# not "exit JARVIS". As of Phase 11.7, that case is no longer just
# suppressed - _check_close_application() (checked BEFORE this
# function in _CHECKERS) now resolves it to the real, correct, safe
# "close chrome" action via the existing window_control.
# handle_targeted() mechanism. By the time _check_exit() ever sees
# "band karo"/"بند کرو", any app-name/browser-word combination has
# therefore ALREADY been claimed by _check_close_application() - so the
# guard below (never treat "band karo" as exit when a known application
# name is present) is now redundant-but-harmless defense in depth,
# intentionally left in place rather than removed, exactly the same
# "revalidate even though the caller already validated" discipline
# volume_control.set_volume() already uses for its own range check.
_AMBIGUOUS_EXIT_MARKERS = ("band karo", "بند کرو")


def _contains_any_bounded(text, phrases):
    """Like a plain substring check, but requires each phrase to occur
    as a whole, word-boundary-anchored unit - never as a mid-word
    substring of a longer, unrelated token. Phase 11.3.1: closes the
    general-vocabulary equivalent of the false-positive class Phase
    11.2's _dangerous_pattern() already guards against for the
    dangerous vocabulary (e.g. "computer lock karobar" must not match
    "lock karo") - same rationale, same \\b-anchoring technique,
    applied here to the GENERAL (non-dangerous) vocabulary only.
    Concretely: "mute karo" must match in "mute karo" but not in "mute
    karobar" (a real Urdu/Roman-Urdu word meaning "business", sharing a
    prefix with "karo") - an empirically verified gap (see the Phase
    11.3 architecture audit) before this function existed.

    Used by every checker below EXCEPT _check_dangerous(), which has
    its own, separate, already-boundary-safe regex machinery
    (LOCK_DANGEROUS_RE/SHUTDOWN_DANGEROUS_RE/RESTART_DANGEROUS_RE) -
    frozen since Phase 11.2, not replaced, shared, or otherwise touched
    by this function's introduction.
    """

    return any(
        re.search(r"\b" + re.escape(phrase) + r"\b", text)
        for phrase in phrases
    )


def _render(intent, target=None):
    """Render via intent_parser.to_canonical_command() (reused,
    UNMODIFIED) - see module docstring for why this is the primary
    safety mechanism in this file."""

    return intent_parser.to_canonical_command(intent_parser.IntentResult(intent, target))


# ---------------------------------------------------------------------
# Per-concept checkers - each takes already-lowercased text and returns
# a canonical command string, or None. Order matters only where marker
# phrases could otherwise both be present in the same utterance (e.g.
# "agla gana chalao" contains both a PLAY marker and a NEXT_TRACK
# marker - NEXT_TRACK must win, exactly mirroring intent_parser.
# classify()'s own ordering for the equivalent English case).
# ---------------------------------------------------------------------

def _check_dangerous(text):
    """Phase 11.2. Returns ONLY one of the three fixed literal strings
    below (never built from `text`) or None. Checked FIRST in
    _CHECKERS - deliberately, mirroring intent_layer.py's own "DANGEROUS
    (checked first...)" ordering rationale - so a dangerous phrase is
    never shadowed by a broader, later rule. See the module docstring's
    SAFETY section and _dangerous_pattern() above for what is and is
    not required to match."""

    if LOCK_DANGEROUS_RE.search(text):
        return "lock computer"

    if SHUTDOWN_DANGEROUS_RE.search(text):
        return "shutdown computer"

    if RESTART_DANGEROUS_RE.search(text):
        return "restart computer"

    return None


def _check_screenshot(text):
    if _contains_any_bounded(text, SCREENSHOT_MARKERS):
        return _render(intent_parser.Intent.SCREENSHOT)
    return None


def _check_window_control(text):
    if _contains_any_bounded(text, MINIMIZE_MARKERS):
        return _render(intent_parser.Intent.MINIMIZE_WINDOW)
    if _contains_any_bounded(text, MAXIMIZE_MARKERS):
        return _render(intent_parser.Intent.MAXIMIZE_WINDOW)
    if _contains_any_bounded(text, RESTORE_MARKERS):
        return _render(intent_parser.Intent.RESTORE_WINDOW)
    if _contains_any_bounded(text, CLOSE_WINDOW_MARKERS):
        return _render(intent_parser.Intent.CLOSE_WINDOW)
    if _contains_any_bounded(text, SHOW_DESKTOP_MARKERS):
        return _render(intent_parser.Intent.SHOW_DESKTOP)
    if _contains_any_bounded(text, SWITCH_WINDOW_MARKERS):
        return _render(intent_parser.Intent.SWITCH_WINDOW)
    return None


def _check_close_application(text):
    """Phase 11.7. Not rendered via intent_parser (intent_parser.Intent
    has no "close a specific named application" category - only the
    untargeted CLOSE_WINDOW above), but still only ever produces a
    plain "close <app>" string built from an ALREADY-VALIDATED
    intent_parser.KNOWN_APPLICATIONS key (or the fixed literal "close
    chrome" for a generic browser word) - the exact same canonical
    shape English phrases like "close chrome" already produce and
    window_control.handle_targeted() (Phase 6, unmodified) already
    knows how to route safely. Checked AFTER _check_window_control()
    above, so an UNTARGETED "window band karo" (-> "close this window")
    is never shadowed by this targeted check."""

    if not _contains_any_bounded(text, CLOSE_APP_MARKERS):
        return None

    for name in intent_parser.KNOWN_APPLICATIONS:
        if name in text:
            return f"close {name}"

    if _contains_any_bounded(text, BROWSER_WORD_MARKERS):
        return "close chrome"

    return None


def _check_media(text):
    if _contains_any_bounded(text, NEXT_TRACK_MARKERS):
        return _render(intent_parser.Intent.NEXT_TRACK)
    if _contains_any_bounded(text, PREVIOUS_TRACK_MARKERS):
        return _render(intent_parser.Intent.PREVIOUS_TRACK)
    if _contains_any_bounded(text, PLAY_MARKERS) or _contains_any_bounded(text, PAUSE_MARKERS):
        return _render(intent_parser.Intent.PLAY_PAUSE)
    return None


def _check_mute_unmute(text):
    if _contains_any_bounded(text, UNMUTE_MARKERS):
        return _render(intent_parser.Intent.UNMUTE)
    if _contains_any_bounded(text, MUTE_MARKERS):
        return _render(intent_parser.Intent.MUTE)
    return None


def _check_set_volume(text):
    if not _contains_any_bounded(text, VOLUME_WORD_MARKERS):
        return None

    match = SET_VOLUME_NUMBER_RE.search(text)

    if not match:
        return None

    raw_number = match.group(1)

    if not raw_number.isdigit():
        return None

    percent = int(raw_number)

    if not (0 <= percent <= 100):
        return None

    return _render(intent_parser.Intent.SET_VOLUME, target=percent)


def _check_volume_up_down(text):
    if _contains_any_bounded(text, VOLUME_UP_MARKERS):
        return _render(intent_parser.Intent.VOLUME_UP)
    if _contains_any_bounded(text, VOLUME_DOWN_MARKERS):
        return _render(intent_parser.Intent.VOLUME_DOWN)
    return None


def _check_keyboard(text):
    if _contains_any_bounded(text, SELECT_ALL_MARKERS):
        return _render(intent_parser.Intent.SELECT_ALL)
    if _contains_any_bounded(text, COPY_MARKERS):
        return _render(intent_parser.Intent.COPY)
    if _contains_any_bounded(text, PASTE_MARKERS):
        return _render(intent_parser.Intent.PASTE)
    if _contains_any_bounded(text, UNDO_MARKERS):
        return _render(intent_parser.Intent.UNDO)

    for key, markers in PRESS_KEY_MARKERS.items():
        if _contains_any_bounded(text, markers):
            return _render(intent_parser.Intent.PRESS_KEY, target=key)

    return None


def _check_scroll(text):
    """Phase 11.5. Not rendered via intent_parser - see SCROLL_UP_
    MARKERS/SCROLL_DOWN_MARKERS above: intent_parser.Intent has no
    SCROLL category at all. "scroll up"/"scroll down" are fixed Python
    string literals, not derived from any user-supplied text - same
    pattern as _check_greeting()/_check_exit() below."""

    if _contains_any_bounded(text, SCROLL_UP_MARKERS):
        return "scroll up"
    if _contains_any_bounded(text, SCROLL_DOWN_MARKERS):
        return "scroll down"
    return None


def _check_tab_browser(text):
    """Roman-Urdu browser tab-management and navigation. Not rendered
    via intent_parser - it has no NEW_TAB/CLOSE_TAB/REFRESH/GO_BACK/
    GO_FORWARD category at all (this project had no browser-tab
    capability whatsoever, in any language, before this addition - see
    web_control.new_tab()/close_tab()/next_tab()/previous_tab()/
    refresh()/go_back()/go_forward()). Fixed Python string literals,
    not derived from `text` - same pattern as _check_scroll() above.
    Checked BEFORE _check_search()/_check_open_application()/_check_
    exit() below: "naya tab kholo" would otherwise be claimed by the
    generic OPEN_MARKERS "kholo" fallback attempt (harmlessly - it
    requires a KNOWN_APPLICATIONS name too, which "tab" isn't, so it
    would actually fall through unmatched) and "tab band karo"
    contains the generic _AMBIGUOUS_EXIT_MARKERS phrase "band karo",
    which _check_exit() would otherwise incorrectly resolve as EXIT
    (quitting JARVIS) instead of closing a browser tab."""

    if _contains_any_bounded(text, NEW_TAB_MARKERS):
        return "new tab"
    if _contains_any_bounded(text, CLOSE_TAB_MARKERS):
        return "close tab"
    if _contains_any_bounded(text, REFRESH_MARKERS):
        return "refresh"
    if _contains_any_bounded(text, GO_BACK_MARKERS):
        return "go back"
    if _contains_any_bounded(text, GO_FORWARD_MARKERS):
        return "go forward"
    return None


def _check_search(text):
    for marker in SEARCH_SUFFIX_MARKERS:

        suffix = " " + marker

        if text.endswith(suffix):

            query = text[: -len(suffix)].strip()

            if query:
                return _render(intent_parser.Intent.SEARCH, target=query)

    for marker in SEARCH_PREFIX_MARKERS:

        prefix = marker + " "

        if text.startswith(prefix):

            query = text[len(prefix):].strip()

            if query:
                return _render(intent_parser.Intent.SEARCH, target=query)

    return None


def _check_open_application(text):
    if not _contains_any_bounded(text, OPEN_MARKERS):
        return None

    for name in intent_parser.KNOWN_APPLICATIONS:
        if name in text:
            return _render(intent_parser.Intent.OPEN_APPLICATION, target=name)

    return None


def _check_open_browser(text):
    """Phase 11.5. Generic "(mera) browser/brouser/broser kholo/open
    karo" - not rendered via intent_parser, since "browser" is
    deliberately NOT added to intent_parser.KNOWN_APPLICATIONS (that
    allow-list stays untouched). "open chrome" is a fixed Python string
    literal - the exact same already-existing canonical command
    _check_open_application() above would itself produce for "chrome" -
    not built from `text`. Checked AFTER _check_open_application() so a
    specific browser name (e.g. "edge kholo") is never shadowed by this
    generic fallback."""

    if _contains_any_bounded(text, OPEN_MARKERS) and _contains_any_bounded(
        text, BROWSER_WORD_MARKERS
    ):
        return "open chrome"
    return None


def _check_time_date(text):
    if _contains_any_bounded(text, TIME_MARKERS):
        return _render(intent_parser.Intent.TIME)
    if _contains_any_bounded(text, DATE_MARKERS):
        return _render(intent_parser.Intent.DATE)
    return None


def _check_greeting(text):
    """Not rendered via intent_parser - see module docstring: intent_
    parser.Intent has no GREETING category at all. "hello" is a fixed
    Python string literal, not derived from any user-supplied text."""

    if _contains_any_bounded(text, GREETING_MARKERS):
        return "hello"
    return None


def _check_exit(text):
    """Not rendered via intent_parser - see module docstring: intent_
    parser.Intent has no EXIT category at all. "exit" is a fixed
    Python string literal, not derived from any user-supplied text."""

    if _contains_any_bounded(text, EXIT_MARKERS):
        return "exit"

    # See _AMBIGUOUS_EXIT_MARKERS' own comment above: "band karo"/
    # "بند کرو" only map to exit when no known application name is also
    # present (in practice, by the time _check_exit() runs, an
    # app-name/browser-word combination has already been claimed by
    # _check_close_application() earlier in _CHECKERS - this is
    # defense-in-depth, not the primary guard).
    if _contains_any_bounded(text, _AMBIGUOUS_EXIT_MARKERS):
        if not any(name in text for name in intent_parser.KNOWN_APPLICATIONS):
            return "exit"

    return None


# Order: DANGEROUS first (highest safety priority, mirroring
# intent_layer.py's own ordering), then concepts with the most
# specific/distinctive marker phrases, broader ones (OPEN_APPLICATION,
# which only requires a generic open-verb marker plus ANY known
# application name) later - mirrors intent_layer.understand()'s own
# "specific rules before broad fallback-shaped ones" ordering
# discipline.
_CHECKERS = (
    _check_dangerous,
    _check_screenshot,
    _check_window_control,
    _check_close_application,
    _check_media,
    _check_mute_unmute,
    _check_set_volume,
    _check_volume_up_down,
    _check_keyboard,
    _check_scroll,
    _check_tab_browser,
    _check_search,
    _check_open_application,
    _check_open_browser,
    _check_time_date,
    _check_greeting,
    _check_exit,
)


def understand(text):
    """Recognize a single Urdu-script, Roman-Urdu, or mixed-language
    utterance and return the canonical command string the existing
    dispatch chain already understands, or None if nothing matched.

    Pure - performs no I/O, calls no control module, never executes
    anything, never raises for any string input. `text` is expected to
    be the same already-normalized (lowercased, whitespace-collapsed)
    text command_parser.normalize() would have already produced by the
    time commands.py reaches this layer's insertion point - the same
    contract intent_parser.classify() and intent_layer.understand()
    already use (see their own docstrings).

    Callers MUST feed a non-None result back through
    CommandProcessor.process() - never execute it directly - see this
    module's docstring for why that is what keeps the Phase 9
    dangerous-command gate intact.
    """

    if not text:
        return None

    lowered = text.lower()

    for checker in _CHECKERS:

        result = checker(lowered)

        if result:
            return result

    return None


def understand_dangerous(text):
    """Phase 11.2. A narrower sibling of understand() that recognizes
    ONLY a dangerous-command (lock/shutdown/restart) paraphrase -
    exposed separately so context_manager.py's _looks_like_new_command()
    can check specifically for a dangerous-command diversion while a
    search slot is pending, without depending on this module's much
    broader general vocabulary (which would divert a pending slot reply
    for reasons well beyond "this might be a dangerous command in
    disguise" - out of scope for that function's narrow safety purpose).

    Same contract as understand(): pure, never raises, never executes
    anything. Returns one of "lock computer"/"shutdown computer"/
    "restart computer" (fixed Python literals, not derived from `text`)
    or None. `text` is expected to already be normalized, same contract
    as understand().
    """

    if not text:
        return None

    return _check_dangerous(text.lower())
