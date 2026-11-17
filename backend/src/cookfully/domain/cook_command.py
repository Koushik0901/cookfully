"""Spoken cook-mode commands: intents the panel chooses among, and durations said aloud.

Which intent a transcript means is the panel's call (speech-to-text is noisy and people phrase
things freely). The one number a command can carry, a timer length, is read by rule from the
words, so a model never invents minutes.
"""

from __future__ import annotations

import re

from cookfully.domain.step_timers import MAX_MINUTES, durations

INTENTS: dict[str, str] = {
    "next": "Go to the next step.",
    "previous": "Go back to the previous step.",
    "repeat": "Read or show this step again.",
    "timer": "Start a kitchen timer.",
    "ingredient": "Ask how much of an ingredient to use, or what an ingredient is.",
    "none": "Not a command for the app (chatting, a question about something else, or unclear).",
}
MAX_UTTERANCE_CHARS = 200

_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}  # fmt: skip
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}  # fmt: skip
_SPOKEN = re.compile(
    r"\b(?P<tens>twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[\s-]+(?P<ones>one|two|three|four|five|six|seven|eight|nine))?"
    r"|\b(?P<unit>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen"
    r"|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)\b",
    re.IGNORECASE,
)
_SPOKEN_MINUTES = re.compile(
    rf"(?:{_SPOKEN.pattern})\s*(?P<unit_word>minutes?|mins?|hours?|hrs?)\b", re.IGNORECASE
)


def clean(utterance: str) -> str:
    return " ".join(utterance.split())[:MAX_UTTERANCE_CHARS]


def spoken_minutes(utterance: str) -> int | None:
    """The timer length in an utterance ("ten minutes", "25 min", "an hour"), or ``None``."""

    text = clean(utterance)
    found = durations(text)
    if found:
        return found[0].minutes
    match = _SPOKEN_MINUTES.search(text)
    if match is None:
        return None
    if match["tens"]:
        value = _TENS[match["tens"].casefold()] + _UNITS.get((match["ones"] or "").casefold(), 0)
    else:
        value = _UNITS[match["unit"].casefold()]
    if match["unit_word"].casefold().startswith("h"):
        value *= 60
    return value if 1 <= value <= MAX_MINUTES else None
