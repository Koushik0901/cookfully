"""Durations written in recipe steps ("simmer 20-25 minutes", "1 1/2 hours").

Finding the numbers is deterministic. Deciding which of them is a timed wait the cook should set a
timer for (and whether the cook is free meanwhile) is left to the decision panel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

MIN_MINUTES = 1
MAX_MINUTES = 720  # twelve hours; longer is "overnight", not a kitchen timer
MAX_CANDIDATES = 6

_NUMBER = r"(?:\d+\s+\d/\d|\d+/\d+|\d+(?:\.\d+)?|[½¼¾⅓⅔]|\d+[½¼¾⅓⅔])"
_UNIT = r"(?P<unit>hours?|hrs?|minutes?|mins?)(?![a-z])"
_RANGE = re.compile(
    rf"(?<![\w/.])(?P<low>{_NUMBER})(?:\s*(?:-|\u2013|\u2014|to|or)\s*(?P<high>{_NUMBER}))?\s*{_UNIT}",
    re.IGNORECASE,
)
_WORD = re.compile(
    r"\b(?P<word>half an hour|an hour and a half|an hour|a minute|half a minute"
    r"|a couple of minutes)\b",
    re.IGNORECASE,
)
_WORD_MINUTES = {
    "half an hour": Decimal(30),
    "an hour and a half": Decimal(90),
    "an hour": Decimal(60),
    "a minute": Decimal(1),
    "half a minute": Decimal(0),
    "a couple of minutes": Decimal(2),
}
_VULGAR = {"½": "0.5", "¼": "0.25", "¾": "0.75", "⅓": "0.3333", "⅔": "0.6667"}


@dataclass(frozen=True, slots=True)
class Duration:
    """One duration found in a step: the text as written and its shortest length in minutes."""

    text: str
    minutes: int
    longest_minutes: int


def _number(raw: str) -> Decimal | None:
    raw = raw.strip()
    if raw in _VULGAR:
        return Decimal(_VULGAR[raw])
    if raw[-1] in _VULGAR and raw[:-1].isdigit():
        return Decimal(raw[:-1]) + Decimal(_VULGAR[raw[-1]])
    parts = raw.split()
    try:
        if len(parts) == 2 and "/" in parts[1]:
            top, bottom = parts[1].split("/")
            return Decimal(parts[0]) + Decimal(top) / Decimal(bottom)
        if "/" in raw:
            top, bottom = raw.split("/")
            return Decimal(top) / Decimal(bottom)
        return Decimal(raw)
    except (ArithmeticError, ValueError):
        return None


def _to_minutes(value: Decimal, unit: str) -> Decimal:
    return value * 60 if unit.casefold().startswith("h") else value


def durations(step: str) -> list[Duration]:
    """Every timer-sized duration in ``step`` (a minute to twelve hours), in reading order."""

    found: list[tuple[int, Duration]] = []
    for match in _RANGE.finditer(step):
        low = _number(match["low"])
        high = _number(match["high"]) if match["high"] else low
        if low is None or high is None or low <= 0 or high < low:
            continue
        unit = match["unit"]
        low_minutes = _to_minutes(low, unit)
        high_minutes = _to_minutes(high, unit)
        minutes = int(low_minutes.to_integral_value(rounding="ROUND_HALF_UP"))
        longest = int(high_minutes.to_integral_value(rounding="ROUND_HALF_UP"))
        if minutes < MIN_MINUTES or longest > MAX_MINUTES:
            continue
        found.append((match.start(), Duration(match[0].strip(), minutes, longest)))
    for match in _WORD.finditer(step):
        minutes = int(_WORD_MINUTES[match["word"].casefold()])
        if minutes >= MIN_MINUTES:
            found.append((match.start(), Duration(match["word"], minutes, minutes)))
    found.sort(key=lambda item: item[0])
    unique: list[Duration] = []
    for _, duration in found:
        if duration not in unique:
            unique.append(duration)
    return unique[:MAX_CANDIDATES]
