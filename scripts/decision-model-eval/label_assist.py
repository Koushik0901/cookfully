"""Model-assisted labeling: a two-model panel pre-screens gold labels so a human reviews only the doubtful ones.

Gold sets here were written by one labeler (often an LLM). This script asks the Jev + Clef panel the same
question for every item and flags only the items where a human's eyes are worth the time:

- the panel's top answer differs from the current label;
- the two models disagree with each other; or
- the panel's top probability is below ``--min-confidence`` (default 0.6).

Everything else is "confirmed by the panel". The output is a Markdown review sheet with a verdict column
for the reviewer. Nothing is rewritten: the script never edits a gold file.

A task is a JSON file::

    {"name": "shelf-life", "question": "Roughly how long does this keep?",
     "options": {"week": "About a week", "month": "About a month"},
     "field": "item", "items": [["kimchi", "month"], ["fresh dill", "week"]]}

Built-in tasks wrap the repository's own gold sets (``--builtin shelf-life|cook-commands``).

Usage (from the repo root)::

    uv run --directory backend python ../scripts/decision-model-eval/label_assist.py \\
        --workdir <dir> --builtin cook-commands --out review.md
    uv run --directory backend python ../scripts/decision-model-eval/label_assist.py \\
        --workdir <dir> --task my_task.json

The OpenRouter key is read only by the transport from ``$OPENROUTER_API_KEY``. Answers are cached in
``<workdir>/decision_cache.jsonl``, so a rerun is free; ``--offline`` reports misses instead of calling.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app_eval import PANELS, ROOT, FileDecisionStore, Harness  # noqa: E402

from cookfully.domain.decisions import Ask, Choice, Purpose  # noqa: E402

GOLD = ROOT / "docs/decision-model-experiments/gold"
MIN_CONFIDENCE = Decimal("0.6")
MAX_ITEMS = 2000


@dataclass(frozen=True, slots=True)
class Task:
    name: str
    question: str
    options: Mapping[str, str]
    field: str
    items: Sequence[tuple[str, str]]


@dataclass(frozen=True, slots=True)
class Finding:
    text: str
    label: str
    top: str | None
    probability: Decimal | None
    models_agree: bool
    reasons: tuple[str, ...]


def load_task(path: Path) -> Task:
    raw = json.loads(path.read_text(encoding="utf-8"))
    options = raw["options"]
    items = [(str(text), str(label)) for text, label, *_ in raw["items"]]
    if not isinstance(options, dict) or len(options) < 2:
        raise SystemExit("A task needs at least two options.")
    if len(items) > MAX_ITEMS:
        raise SystemExit(f"At most {MAX_ITEMS} items per run.")
    unknown = sorted({label for _, label in items if label not in options})
    if unknown:
        raise SystemExit(f"Labels not among the options: {unknown}")
    return Task(
        str(raw.get("name", path.stem)),
        str(raw["question"]),
        {str(k): str(v) for k, v in options.items()},
        str(raw.get("field", "text")),
        items,
    )


def builtin_task(name: str) -> Task:
    if name == "shelf-life":
        from cookfully.application.shelf_life import INSTRUCTIONS
        from cookfully.domain.expiry_lifespans import SHELF_LIFE_BUCKETS

        gold = json.loads((GOLD / "shelf_life.json").read_text(encoding="utf-8"))
        return Task(
            "shelf-life",
            INSTRUCTIONS,
            {key: description for key, (_, description) in SHELF_LIFE_BUCKETS.items()},
            "pantry_item",
            [(text, label) for text, label in gold["items"]],
        )
    if name == "cook-commands":
        from cookfully.application.cook_command import INSTRUCTIONS
        from cookfully.domain.cook_command import INTENTS

        gold = json.loads((GOLD / "cook_commands.json").read_text(encoding="utf-8"))
        return Task(
            "cook-commands",
            INSTRUCTIONS,
            INTENTS,
            "utterance",
            [(text, label) for text, label in gold["items"]],
        )
    raise SystemExit(f"Unknown built-in task {name!r}; use shelf-life or cook-commands.")


def screen(harness: Harness, task: Task, min_confidence: Decimal) -> list[Finding]:
    """Ask the panel about every item; return one finding per item (empty ``reasons`` = confirmed)."""

    engine = harness.engine(Purpose.RECIPE_FACETS, PANELS["jev+clef"])
    asks = [
        Ask(
            Purpose.RECIPE_FACETS,
            {"labeling_task": task.name, task.field: text},
            {"label": Choice(task.question, dict(task.options))},
        )
        for text, _ in task.items
    ]
    findings: list[Finding] = []
    for (text, label), answers in zip(task.items, engine.ask(asks), strict=True):
        top = answers.top("label")
        probabilities = answers.choice("label") or {}
        probability = probabilities.get(top) if top else None
        agree = answers.agree("label")
        reasons: list[str] = []
        if top is None:
            reasons.append("no answer")
        else:
            if top != label:
                reasons.append(f"panel says {top}")
            if probability is not None and probability < min_confidence:
                reasons.append(f"low confidence ({probability:.2f})")
        if top is not None and not agree:
            reasons.append("the two models disagree")
        findings.append(Finding(text, label, top, probability, bool(agree), tuple(reasons)))
    return findings


def review_sheet(task: Task, findings: Sequence[Finding]) -> str:
    flagged = [item for item in findings if item.reasons]
    confirmed = len(findings) - len(flagged)
    differs = sum(1 for item in findings if item.top is not None and item.top != item.label)
    out = [
        f"# Label review: {task.name}",
        "",
        f"{len(findings)} items. Confirmed by the panel: {confirmed}. "
        f"Needs a human: {len(flagged)} (panel differs from the label on {differs}).",
        "",
        "Edit the label only where you are sure; leave the rest. This sheet never changes the gold file.",
        "",
        "| # | item | current label | panel | why flagged | your verdict |",
        "|---|------|---------------|-------|-------------|--------------|",
    ]
    for number, item in enumerate(findings, start=1):
        if not item.reasons:
            continue
        panel = "-" if item.top is None else f"{item.top} ({item.probability:.2f})"
        text = item.text.replace("|", "\\|").replace("\n", " ")
        out.append(f"| {number} | {text} | {item.label} | {panel} | {'; '.join(item.reasons)} | |")
    if not flagged:
        out.append("| | nothing flagged | | | | |")
    return "\n".join(out) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--task", type=Path, help="task JSON file")
    parser.add_argument("--builtin", choices=["shelf-life", "cook-commands"])
    parser.add_argument("--out", type=Path, help="write the review sheet here (default: stdout)")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--budget", type=Decimal, default=Decimal("1.00"))
    parser.add_argument("--min-confidence", type=Decimal, default=MIN_CONFIDENCE)
    args = parser.parse_args(argv)
    if (args.task is None) == (args.builtin is None):
        parser.error("give exactly one of --task or --builtin")
    task = load_task(args.task) if args.task else builtin_task(args.builtin)
    args.workdir.mkdir(parents=True, exist_ok=True)
    harness = Harness(
        FileDecisionStore(args.workdir / "decision_cache.jsonl"), args.offline, args.budget
    )
    sheet = review_sheet(task, screen(harness, task, args.min_confidence))
    if args.out:
        args.out.write_text(sheet, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(sheet)
    print(
        f"cache: {len(harness.store.rows)} answers, ${harness.store.total_cost():.4f} total; "
        f"offline misses: {harness.offline_transport.misses}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
