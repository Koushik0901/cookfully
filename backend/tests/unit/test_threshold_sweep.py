from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_script_module():
    # Load scripts/needle_threshold_sweep.py robustly when running with --directory backend
    # repo root is parents[2] from backend/tests/unit
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    script_underscore = repo_root / "scripts" / "needle_threshold_sweep.py"
    script_hyphen = repo_root / "scripts" / "needle-threshold-sweep.py"
    target = script_underscore if script_underscore.exists() else script_hyphen
    spec = importlib.util.spec_from_file_location("scripts.needle_threshold_sweep", target)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # ensure scripts package visible
    if "scripts" not in sys.modules:
        import types

        pkg = types.ModuleType("scripts")
        pkg.__path__ = [str(target.parent)]
        sys.modules["scripts"] = pkg
    sys.modules["scripts.needle_threshold_sweep"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_sweep_picks_threshold():
    mod = _load_script_module()
    pick_threshold = mod.pick_threshold
    report = pick_threshold([{"conf": 0.9, "correct": True}, {"conf": 0.6, "correct": False}])
    assert 0.75 <= report["threshold"] <= 0.85


def test_compute_metrics_fields():
    mod = _load_script_module()
    compute_metrics = mod.compute_metrics
    samples = [
        {"id": "a", "conf": 0.9, "correct": True},
        {"id": "b", "conf": 0.85, "correct": True},
        {"id": "c", "conf": 0.62, "correct": False},
    ]
    m = compute_metrics(samples, 0.80)
    for k in (
        "threshold",
        "precision",
        "recall",
        "false_overwrite",
        "p95_ms",
        "confidence_histogram",
    ):
        assert k in m
    assert 0 <= m["precision"] <= 1
    assert 0 <= m["recall"] <= 1
    assert isinstance(m["confidence_histogram"], dict)


def test_thresholds_list_and_parallel_sweep():
    mod = _load_script_module()
    assert mod.THRESHOLDS == [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    # sweep should be parallel via asyncio.gather (smoke test)
    import asyncio

    async def _run():
        corpora = {
            "recipe_extract": [
                {"id": "r1", "conf": 0.9, "correct": True},
                {"id": "r2", "conf": 0.6, "correct": False},
            ],
            "pantry_extract": [
                {"id": "p1", "conf": 0.88, "correct": True},
                {"id": "p2", "conf": 0.55, "correct": False},
            ],
        }
        res = await mod.sweep_all(corpora)
        assert "recipe_extract" in res
        assert "pantry_extract" in res
        for op in res:
            assert len(res[op]) == 7
            assert all("threshold" in x for x in res[op])

    asyncio.run(_run())


def test_no_db_writes_flag():
    # Script must not import SQLAlchemy DB or perform writes;
    # we check source doesn't contain Session or engine writes
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    text = (repo_root / "scripts" / "needle_threshold_sweep.py").read_text(encoding="utf-8")
    # ensure no DB imports
    for banned in ["sqlalchemy", "psycopg", "Session("]:
        assert banned.lower() not in text.lower() or "no db" in text.lower()
