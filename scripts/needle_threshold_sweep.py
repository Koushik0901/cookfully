#!/usr/bin/env python3
"""Sweep T 0.60->0.90 in parallel workers over corpora, emit JSON report.

Deterministic, no network, no DB writes. Uses FakeClient-style synthetic
responses from fixtures under backend/tests/fixtures/needle-corpus/ if present,
otherwise generates deterministic synthetic samples.

Parallel via asyncio.gather with 8 workers (semaphore).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

THRESHOLDS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]

# ---------------------------------------------------------------------------
# metrics helpers
# ---------------------------------------------------------------------------

def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    # ceil(0.95*n)-1
    idx = max(0, min(len(s) - 1, int((len(s) * 95 + 99) // 100) - 1))
    # also use statistics.quantiles for reference but keep deterministic index method
    return float(s[idx])


def confidence_histogram(samples: list[dict]) -> dict[str, int]:
    """10-bin histogram 0.0-1.0 step 0.1 as strings."""
    bins = {f"{i/10:.1f}-{(i+1)/10:.1f}": 0 for i in range(10)}
    for s in samples:
        conf = s.get("conf")
        if conf is None:
            continue
        try:
            c = float(conf)
        except Exception:
            continue
        idx = min(9, max(0, int(c * 10)))
        key = f"{idx/10:.1f}-{(idx+1)/10:.1f}"
        bins[key] += 1
    return bins


def compute_metrics(samples: list[dict], threshold: float) -> dict:
    """Compute precision, recall, false_overwrite, p95_ms, confidence_histogram for threshold.

    Gate: conf is not None and conf >= threshold.
    correct=True means the repair would be accurate if applied.
    """
    tp = fp = fn = tn = 0
    applied_latencies: list[float] = []
    all_latencies: list[float] = []
    for s in samples:
        conf = s.get("conf")
        correct = bool(s.get("correct"))
        # deterministic simulated latency 12ms base + conf*20 + tiny id hash
        latency = s.get("latency_ms")
        if latency is None:
            # deterministic from conf and id
            base = 12.0
            c = float(conf) if conf is not None else 0.5
            # hash id deterministically
            sid = str(s.get("id", ""))
            h = sum(ord(ch) for ch in sid) % 10
            latency = base + c * 18 + h * 0.3
        all_latencies.append(float(latency))
        gated = conf is not None and float(conf) >= threshold
        if gated:
            applied_latencies.append(float(latency))
            if correct:
                tp += 1
            else:
                fp += 1
        else:
            if correct:
                fn += 1
            else:
                tn += 1

    applied = tp + fp
    precision = (tp / applied) if applied else 1.0 if tp == 0 and fp == 0 else 0.0
    # when no applied, precision defined as 1.0 (no false overwrite) to avoid penalising
    # but if we have zero applied we treat as 1.0
    recall = (tp / (tp + fn)) if (tp + fn) else (1.0 if tp == 0 else 0.0)
    false_overwrite = (fp / applied) if applied else 0.0
    # also false_overwrite rate overall if desired: fp/len(samples) alternative
    # expose both but keep primary as fp/applied which equals 1-precision when applied>0

    p95_ms = _p95(applied_latencies if applied_latencies else all_latencies)
    # Round to 2 decimals for report stability
    return {
        "threshold": threshold,
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "false_overwrite": round(float(false_overwrite), 4),
        "p95_ms": round(float(p95_ms), 2),
        "confidence_histogram": confidence_histogram(samples),
        "support": len(samples),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def pick_threshold(samples: list[dict], thresholds: list[float] | None = None) -> dict:
    """Pick best threshold that maximises F1, tie-break closest to 0.80 then higher.

    Returns dict with at least threshold key.
    """
    if thresholds is None:
        thresholds = THRESHOLDS
    if not samples:
        return {"threshold": 0.80, "precision": 1.0, "recall": 0.0, "false_overwrite": 0.0, "p95_ms": 0.0, "confidence_histogram": {}}

    best = None
    best_f1 = -1.0
    # evaluate all
    scored = []
    for t in thresholds:
        m = compute_metrics(samples, t)
        p = m["precision"]
        r = m["recall"]
        f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
        scored.append((t, m, f1))
        if f1 > best_f1 + 1e-9:
            best_f1 = f1
            best = (t, m, f1)
        elif abs(f1 - best_f1) < 1e-9:
            # tie-break: closest to 0.80, then higher threshold
            cur_dist = abs(t - 0.80)
            assert best is not None
            best_dist = abs(best[0] - 0.80)
            if cur_dist < best_dist - 1e-9 or (abs(cur_dist - best_dist) < 1e-9 and t > best[0]):
                best = (t, m, f1)
    assert best is not None
    out = dict(best[1])
    out["f1"] = round(float(best_f1), 4)
    return out


# ---------------------------------------------------------------------------
# corpus loading
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def load_corpora(root: Path | None = None) -> dict[str, list[dict]]:
    """Load corpora from backend/tests/fixtures/needle-corpus/.

    Returns dict operation -> samples.
    """
    # root defaults to repo root inferred from this file
    if root is None:
        # scripts/needle_threshold_sweep.py -> repo root is parent of scripts
        root = Path(__file__).resolve().parents[1]
    corpus_dir = root / "backend" / "tests" / "fixtures" / "needle-corpus"
    recipes = _load_jsonl(corpus_dir / "recipes_sparse.jsonl")
    pantry = _load_jsonl(corpus_dir / "pantry_pastes.jsonl")
    # fallback synthetic if empty
    if not recipes and not pantry:
        # deterministic synthetic corpora seeded
        import random
        random.seed(0xC0FFEE)
        recipes = []
        for i in range(50):
            correct = random.random() > 0.3
            conf = round(random.uniform(0.75, 0.98) if correct else random.uniform(0.40, 0.82), 3)
            recipes.append({"id": f"syn-r{i:03d}", "conf": conf, "correct": correct, "operation": "recipe_extract"})
        pantry = []
        for i in range(200):
            correct = random.random() > 0.25
            conf = round(random.uniform(0.78, 0.96) if correct else random.uniform(0.45, 0.80), 3)
            pantry.append({"id": f"syn-p{i:03d}", "conf": conf, "correct": correct, "operation": "pantry_extract"})
    # tag operation if missing
    for s in recipes:
        s.setdefault("operation", "recipe_extract")
    for s in pantry:
        s.setdefault("operation", "pantry_extract")
    return {"recipe_extract": recipes, "pantry_extract": pantry}


# ---------------------------------------------------------------------------
# async parallel sweep
# ---------------------------------------------------------------------------

async def _evaluate_one(threshold: float, samples: list[dict], sem: asyncio.Semaphore) -> dict:
    async with sem:
        # yield to event loop to emulate parallel workers, no sleep needed
        await asyncio.sleep(0)
        # simulate small deterministic compute
        return compute_metrics(samples, threshold)


async def sweep_operation(operation: str, samples: list[dict], thresholds: list[float] | None = None) -> list[dict]:
    if thresholds is None:
        thresholds = THRESHOLDS
    sem = asyncio.Semaphore(8)
    tasks = [asyncio.create_task(_evaluate_one(t, samples, sem)) for t in thresholds]
    results = await asyncio.gather(*tasks)
    # sort by threshold for deterministic report
    results.sort(key=lambda x: x["threshold"])
    return results


async def sweep_all(corpora: dict[str, list[dict]] | None = None, thresholds: list[float] | None = None) -> dict:
    if thresholds is None:
        thresholds = THRESHOLDS
    if corpora is None:
        corpora = load_corpora()
    # parallel over operations as well
    sem = asyncio.Semaphore(8)
    # create tasks per operation+threshold via gather
    async def _op(op: str, samples: list[dict]) -> tuple[str, list[dict]]:
        res = await sweep_operation(op, samples, thresholds)
        return op, res

    tasks = [asyncio.create_task(_op(op, samps)) for op, samps in corpora.items()]
    pairs = await asyncio.gather(*tasks)
    out: dict[str, list[dict]] = {op: res for op, res in pairs}
    return out


def build_report(corpora: dict[str, list[dict]] | None = None) -> dict:
    """Synchronous wrapper to build full report."""
    if corpora is None:
        corpora = load_corpora()
    # run async sweep
    results = asyncio.run(sweep_all(corpora))
    # choose best per operation
    chosen: dict[str, float] = {}
    for op, samps in corpora.items():
        best = pick_threshold(samps)
        chosen[op] = best["threshold"]
    # overall chosen: pick on combined samples, fallback to 0.80
    all_samples = [s for samps in corpora.values() for s in samps]
    overall = pick_threshold(all_samples)
    chosen["overall"] = overall["threshold"]

    # build flat thresholds summary for convenience
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "thresholds": THRESHOLDS,
        "operations": results,
        "chosen": chosen,
        "overall_pick": overall,
        "note": "deterministic, no DB writes, FakeClient synthetic/conf from fixtures",
    }
    return report


def _try_real_needle_sample(prompt: str, operation: str, threshold: float) -> dict | None:
    """Attempt one real Needle call if model artifact exists; return synthetic dict or None if unavailable.

    Graceful fallback: if needle runtime or /models/needle2.cact missing, return None so caller keeps FakeClient synthetic.
    """
    import os

    model_path = os.getenv("COOKFULLY_INTELLIGENCE_MODEL_PATH", "/models/needle2.cact")
    if not Path(model_path).exists():
        return None
    try:
        import needle  # type: ignore[import-not-found]

        # minimal tool per operation
        from cookfully.application.inline_repair import PantryExtractSchema, RecipeExtractSchema

        schema_map = {"recipe_extract": RecipeExtractSchema, "pantry_extract": PantryExtractSchema}
        schema = schema_map.get(operation)
        if schema is None:
            return None
        from cookfully.intelligence.contracts import ToolDefinition

        tool = ToolDefinition(name="probe", description="probe", parameters=schema.model_json_schema())
        agent = needle.Needle(weights=model_path, tools=[tool.model_json_schema()])  # type: ignore[attr-defined]
        t0 = time.perf_counter()
        res = agent.complete(prompt)
        latency = int((time.perf_counter() - t0) * 1000)
        conf = res.get("confidence")
        # real mode emits envelope prefill/decode/peak_ram if present
        return {
            "conf": conf,
            "correct": True,  # real correctness requires label; caller will fallback to synthetic correctness
            "latency_ms": latency,
            "prefill_tps": res.get("prefill_tps"),
            "decode_tps": res.get("decode_tps"),
            "peak_ram_mb": res.get("peak_ram_mb"),
            "mode": "real",
        }
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel needle threshold sweep 0.60->0.90")
    parser.add_argument("--dry-run", action="store_true", help="use synthetic data, don't require fixtures")
    parser.add_argument("--real", action="store_true", help="if /models/needle2.cact present, run real needle for latency envelope (else synthetic)")
    parser.add_argument("--output", type=str, default="artifacts/needle-threshold-report.json", help="output JSON path")
    parser.add_argument("--corpora-dir", type=str, default=None, help="override corpora dir")
    args = parser.parse_args()

    if args.dry_run:
        # dry-run uses in-memory synthetic but still builds report; ensures no DB writes
        corpora = None
        # force synthetic if fixtures missing is already handled, but dry-run explicitly uses tiny synthetic for speed
        # keep corpora None to reuse load_corpora fallback; still deterministic
        # if --real and model exists, enrich first sample per operation with real latency envelope
        if args.real:
            corpora = load_corpora()
            for op, samps in list(corpora.items()):
                if samps:
                    probe = _try_real_needle_sample(samps[0].get("prompt") or str(samps[0].get("id")), op, 0.80)
                    if probe and probe.get("latency_ms"):
                        # annotate report note but keep synthetic correctness for threshold math
                        samps[0]["latency_ms"] = probe["latency_ms"]
                        samps[0]["mode"] = "real_probed"
        report = build_report(corpora)
    else:
        corpora = load_corpora()
        report = build_report(corpora)

    # handle custom corpora dir if provided
    if args.corpora_dir:
        from pathlib import Path as _P
        p = _P(args.corpora_dir)
        # attempt to load from custom dir (expects recipes_sparse.jsonl etc.)
        custom = {}
        if p.exists():
            # try to load both
            r = _load_jsonl(p / "recipes_sparse.jsonl")
            pp = _load_jsonl(p / "pantry_pastes.jsonl")
            if r:
                custom["recipe_extract"] = r
            if pp:
                custom["pantry_extract"] = pp
            if custom:
                report = build_report(custom)

    out_path = Path(args.output)
    # ensure parent exists
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # no DB writes - only filesystem JSON
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # also emit concise stdout
    print(json.dumps({"chosen": report.get("chosen"), "output": str(out_path)}, indent=2))


if __name__ == "__main__":
    main()
