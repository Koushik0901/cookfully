from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

NUTRIENT_SCALE = Decimal("0.000001")
SERVING_SCALE = Decimal("0.001")
DISPLAY_MACRO_SCALE = Decimal("0.1")
DISPLAY_CALORIE_SCALE = Decimal("1")


def uuid7() -> UUID:
    """Create an RFC 9562 UUIDv7 using a millisecond UTC timestamp."""

    timestamp_ms = int(time.time_ns() // 1_000_000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def require_local_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        raise ValueError("calendar dates must not contain a time component")
    return value


def quantize_decimal(value: Decimal | str | int, scale: Decimal) -> Decimal:
    try:
        return Decimal(value).quantize(scale, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid decimal value") from exc


def canonical_decimal(value: Decimal | str | int, *, places: int = 6) -> str:
    quantized = quantize_decimal(value, Decimal(1).scaleb(-places))
    rendered = format(quantized, "f").rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def display_calories(value: Decimal | str | int) -> str:
    return format(quantize_decimal(value, DISPLAY_CALORIE_SCALE), "f")


def display_macro(value: Decimal | str | int) -> str:
    return format(quantize_decimal(value, DISPLAY_MACRO_SCALE), ".1f")


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    safe_message: str
    status: int = 400
    field_errors: tuple[dict[str, str], ...] = ()

    def __str__(self) -> str:
        return self.safe_message


class OptimisticConcurrencyError(DomainError):
    def __init__(self) -> None:
        super().__init__("stale_version", "The resource changed. Reload and try again.", 409)


def require_version(expected: int, actual: int) -> None:
    if expected != actual:
        raise OptimisticConcurrencyError()


def canonical_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return require_utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    return value
