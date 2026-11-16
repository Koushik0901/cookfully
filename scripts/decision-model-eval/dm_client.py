"""Minimal OpenRouter Decisions API client for offline Cookfully experiments.

* Reads ``OPENROUTER_API_KEY`` from the environment or from the env file named by
  ``COOKFULLY_ENV_FILE``. The key is never printed or logged.
* Every response is cached on disk (keyed by model + request hash), so reruns are free,
  reproducible and resumable.
* A hard spend cap (``DM_EVAL_BUDGET_USD``, default 3.00) aborts before overspending.

Experiment-only code: it is not imported by the Cookfully application.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
_lock = threading.Lock()


def _load_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    env_file = os.environ.get("COOKFULLY_ENV_FILE")
    if env_file and Path(env_file).is_file():
        match = re.search(
            r"^\s*OPENROUTER_API_KEY\s*=\s*[\"']?([^\"'\r\n]+)",
            Path(env_file).read_text(encoding="utf-8"),
            re.M,
        )
        if match:
            return match.group(1).strip()
    raise RuntimeError("OPENROUTER_API_KEY not found in env or COOKFULLY_ENV_FILE")


class BudgetExceeded(RuntimeError):
    pass


class DecisionClient:
    def __init__(self, workdir: Path, budget_usd: float | None = None) -> None:
        self._key = _load_key()
        self.workdir = workdir
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.cache_path = workdir / "dm_cache.jsonl"
        self.budget = float(os.environ.get("DM_EVAL_BUDGET_USD", budget_usd or 3.0))
        self.spent = 0.0
        self.calls = 0
        self.cache_hits = 0
        self._cache: dict[str, dict[str, Any]] = {}
        if self.cache_path.is_file():
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._cache[row["key"]] = row["response"]
                    self.spent += float(row["response"].get("usage", {}).get("cost") or 0)

    @staticmethod
    def _key_for(model: str, state: Any, questions: dict[str, Any]) -> str:
        blob = json.dumps([model, state, questions], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()

    def decide(
        self, model: str, state: Any, questions: dict[str, Any], *, retries: int = 3
    ) -> dict[str, Any]:
        """Return the raw response, or ``{"error": ...}`` after retries."""

        key = self._key_for(model, state, questions)
        with _lock:
            if key in self._cache:
                self.cache_hits += 1
                return self._cache[key]
            if self.spent >= self.budget:
                raise BudgetExceeded(f"spent ${self.spent:.4f} >= cap ${self.budget:.2f}")
        body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
        request = urllib.request.Request(
            ENDPOINT,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        last_error = "unknown"
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(request, timeout=90) as handle:
                    response = json.load(handle)
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                last_error = f"HTTP {exc.code}: {detail}"
                if exc.code in (400, 401, 402, 403, 404, 422):
                    return {"error": last_error, "model_requested": model}
            except Exception as exc:  # network hiccup
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5 * (attempt + 1))
        else:
            return {"error": last_error, "model_requested": model}
        response["model_requested"] = model
        with _lock:
            self._cache[key] = response
            self.spent += float(response.get("usage", {}).get("cost") or 0)
            self.calls += 1
            with self.cache_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"key": key, "response": response}, ensure_ascii=False) + "\n")
        return response

    def summary(self) -> str:
        return (
            f"calls={self.calls} cache_hits={self.cache_hits} "
            f"spent=${self.spent:.4f} cap=${self.budget:.2f}"
        )


def choice_probs(response: dict[str, Any], question: str) -> dict[str, float] | None:
    """Probabilities for a ``choice`` question, or None if it was not answered."""

    answer = (response.get("answers") or {}).get(question)
    if not answer or answer.get("type") != "choice":
        return None
    probs = answer.get("probabilities")
    if probs:
        return {str(k): float(v) for k, v in probs.items()}
    if answer.get("choice") is not None:
        return {str(answer["choice"]): float(answer.get("confidence") or 1.0)}
    return None


def noul_prob(response: dict[str, Any], question: str) -> float | None:
    """Probability of 'yes' for a ``noul`` question, or None if it was not answered."""

    answer = (response.get("answers") or {}).get(question)
    if not answer or answer.get("type") != "noul":
        return None
    return float(answer["noul"])
