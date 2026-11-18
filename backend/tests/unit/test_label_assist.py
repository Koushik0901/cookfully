from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts" / "decision-model-eval"
sys.path.insert(0, str(SCRIPTS))
import label_assist  # noqa: E402

D = Decimal


def _task_file(tmp_path: Path, **overrides: object) -> Path:
    body: dict[str, object] = {
        "name": "t",
        "question": "Which?",
        "options": {"a": "first", "b": "second"},
        "items": [["x | y", "a"], ["z", "b"]],
    }
    body.update(overrides)
    path = tmp_path / "task.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_a_task_file_loads_and_validates_labels(tmp_path: Path) -> None:
    task = label_assist.load_task(_task_file(tmp_path))
    assert task.name == "t"
    assert task.items == [("x | y", "a"), ("z", "b")]
    with pytest.raises(SystemExit):
        label_assist.load_task(_task_file(tmp_path, items=[["x", "nope"]]))
    with pytest.raises(SystemExit):
        label_assist.load_task(_task_file(tmp_path, options={"only": "one"}))


def test_the_review_sheet_lists_only_flagged_items_and_escapes_table_characters(
    tmp_path: Path,
) -> None:
    task = label_assist.load_task(_task_file(tmp_path))
    findings = [
        label_assist.Finding("x | y", "a", "b", D("0.9"), True, ("panel says b",)),
        label_assist.Finding("z", "b", "b", D("0.95"), True, ()),
    ]
    sheet = label_assist.review_sheet(task, findings)
    assert "Confirmed by the panel: 1. Needs a human: 1" in sheet
    assert "x \\| y" in sheet
    assert "| 2 |" not in sheet  # the confirmed item is not listed
    clean = label_assist.review_sheet(task, [findings[1]])
    assert "nothing flagged" in clean


def test_the_built_in_tasks_wrap_the_repository_gold_sets() -> None:
    for name in ("shelf-life", "cook-commands"):
        task = label_assist.builtin_task(name)
        assert len(task.items) > 20
        assert {label for _, label in task.items} <= set(task.options)
    with pytest.raises(SystemExit):
        label_assist.builtin_task("nope")
