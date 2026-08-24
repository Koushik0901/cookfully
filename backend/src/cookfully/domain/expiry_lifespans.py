from __future__ import annotations
from datetime import date, datetime, timezone
from cookfully.domain.common import utc_now

FRESH_LIFESPANS: dict[str, int] = {
    "tomato": 5, "cherry tomato": 5, "lettuce": 4, "spinach": 3, "kale": 5, "arugula": 3,
    "carrot": 14, "cucumber": 5, "zucchini": 5, "broccoli": 5, "cauliflower": 7, "celery": 10,
    "pepper": 7, "bell pepper": 7, "mushroom": 4, "onion": 21, "potato": 21, "sweet potato": 14,
    "avocado": 4, "banana": 4, "apple": 21, "berries": 3, "strawberry": 3, "blueberry": 5,
    "raspberry": 3, "grapes": 7, "lemon": 14, "lime": 14, "orange": 14, "herbs": 3, "cilantro": 3,
    "parsley": 4, "basil": 3, "asparagus": 4, "green beans": 5, "peas": 4, "corn": 3,
    "cabbage": 14, "eggplant": 5, "garlic": 30, "ginger": 14, "leek": 7, "radish": 7,
}
LABEL_REQUIRED_KEYWORDS: set[str] = {"milk","cream","yogurt","cheese","chicken","beef","pork","fish","salmon","turkey","egg","tofu","juice"}

def _norm(name: str) -> str:
    n = name.casefold().strip()
    # singular fallback
    if n in FRESH_LIFESPANS:
        return n
    if n.endswith("es") and n[:-2] in FRESH_LIFESPANS:
        return n[:-2]
    if n.endswith("s") and n[:-1] in FRESH_LIFESPANS:
        return n[:-1]
    return n

def is_label_required(display_name: str) -> bool:
    low = display_name.casefold()
    return any(kw in low for kw in LABEL_REQUIRED_KEYWORDS)

def resolve_expiry(display_name: str, requested_expires_on: date | None = None, today: date | None = None):
    now = utc_now()
    cur_today = today or now.date()
    if requested_expires_on is not None:
        # caller will decide label vs manual; first prompt = label, later edits = manual (service decides)
        return requested_expires_on, "label", now, False
    norm = _norm(display_name)
    if norm in FRESH_LIFESPANS:
        return date.fromordinal(cur_today.toordinal() + FRESH_LIFESPANS[norm]), "auto", now, False
    if is_label_required(display_name):
        return None, None, None, True
    return None, None, None, False
