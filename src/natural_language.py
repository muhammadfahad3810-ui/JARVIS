"""Phase 8: bounded, deterministic multi-clause command splitting.

Splits a single spoken utterance into multiple independent command
clauses on a narrow, fixed set of conjunctions ("and", "then"), so
JARVIS can handle simple chained requests like "open chrome and search
for python" as two separate commands.

This module NEVER executes anything itself - it only decides how to
split text, and only commits to a split when it can prove (via
intent_parser.classify(), the existing pure, side-effect-free,
allow-list classifier already used for diagnostics elsewhere in this
project) that EVERY resulting clause independently resolves to an
already-known command. If even one clause doesn't resolve, the split
is discarded entirely and the original, unsplit text is returned as a
single clause - this is what keeps ordinary phrases that merely
contain the word "and" safe (e.g. "search for bed and breakfast":
"breakfast" alone isn't a known command, so the split is rejected and
the original phrase is processed whole, exactly as it always has
been - "search for bed and breakfast" is itself a valid, unaffected
SEARCH command since it already starts with "search for").

Wired in by commands.CommandProcessor.process(), BEFORE
command_parser.normalize() runs - each resulting clause is
independently passed back through the entire existing pipeline
(normalize -> dispatch), so no validation is ever bypassed and this
module has zero effect on any single-clause command (the exact
original text is used, unmodified, whenever no split is committed to).

Known, deliberate limitation: intent_parser.classify() does not cover
exit words ("exit"/"quit"/...) or greetings ("hello"/...), so a phrase
like "open chrome and exit" will never split (the "exit" clause
classifies as UNKNOWN) - this fails closed (falls back to processing
the whole phrase as one unrecognized command) rather than guessing,
which is the safe direction for this project's architecture.
"""

import re

import command_parser
import intent_parser


CONJUNCTION_PATTERN = re.compile(r"\s+(?:and then|and|then)\s+")


def split_into_clauses(text):
    """Split `text` into command clauses on "and"/"then", but only if
    EVERY resulting clause independently classifies as a known command
    once normalized. Otherwise returns [text] unchanged - a single-
    element result means "do not split"; callers must treat it that
    way (process `text` exactly as before, not `result[0]`).
    """

    if not text:
        return [text]

    candidates = [
        clause.strip()
        for clause in CONJUNCTION_PATTERN.split(text)
        if clause.strip()
    ]

    if len(candidates) < 2:
        return [text]

    for clause in candidates:

        normalized = command_parser.normalize(clause)
        result = intent_parser.classify(normalized)

        if result.intent == intent_parser.Intent.UNKNOWN:
            return [text]

    return candidates
