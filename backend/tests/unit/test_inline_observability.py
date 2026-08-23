import logging

from cookfully.application.inline_repair import InlineRepairGateway
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


class FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def infer(self, req, timeout_seconds=None):
        return self._resp


ok_resp = InferenceResponse(
    requestId="inline-req-1",
    status="ok",
    confidence=0.88,
    reasoning="ten minutes -> 10",
    functionCalls=(
        ToolCall(
            name="recipe",
            arguments={"ingredients": ["1 tsp salt"], "steps": ["Mix"]},
        ),
    ),
    prefill_tps=123.4,
    decode_tps=45.6,
    peak_ram_mb=28.0,
    latency_ms=42,
)

legacy = {"ingredients": [], "steps": []}


def test_log_no_pii(caplog):
    gw = InlineRepairGateway(FakeClient(ok_resp), threshold=0.8, timeout_ms=600)
    # legacy contains sensitive text that must not appear in logs
    secret_legacy = {"ingredients": [], "steps": [], "password": "s3cr3t", "prompt": "my secret"}
    with caplog.at_level(logging.INFO, logger="cookfully.inline_repair"):
        gw.merge_recipe(secret_legacy, ok_resp)
    assert any("needle_inline" in r.message for r in caplog.records)
    combined = "".join(r.message for r in caplog.records)
    # ensure no user text / secret appears in message or extra-derived string
    assert "password" not in combined
    assert "s3cr3t" not in combined
    # also check structured extra does not contain user prompt
    for r in caplog.records:
        if "needle_inline" in r.message:
            # extra fields are on record
            assert getattr(r, "request_id", None) == "inline-req-1"
            # user text must not be in any extra value
            extra_vals = " ".join(str(v) for v in r.__dict__.values() if isinstance(v, str))
            assert "s3cr3t" not in extra_vals


def test_log_contains_fields(caplog):
    gw = InlineRepairGateway(FakeClient(ok_resp), threshold=0.8, timeout_ms=600)
    with caplog.at_level(logging.INFO, logger="cookfully.inline_repair"):
        gw.merge_recipe(legacy, ok_resp)
    needle_records = [r for r in caplog.records if "needle_inline" in r.message]
    assert needle_records, "expected needle_inline log"
    r = needle_records[0]
    # required fields per brief: request_id, confidence, reasoning, applied, latency_ms, prefill, decode, peak_ram
    assert hasattr(r, "request_id")
    assert hasattr(r, "confidence")
    assert hasattr(r, "reasoning")
    assert hasattr(r, "applied")
    assert hasattr(r, "latency_ms")
    assert hasattr(r, "prefill")
    assert hasattr(r, "decode")
    assert hasattr(r, "peak_ram")
    assert r.confidence == 0.88
    assert r.reasoning == "ten minutes -> 10"
    assert r.applied is True
    # perf envelope pass-through
    assert r.prefill == 123.4
    assert r.decode == 45.6
    assert r.peak_ram == 28.0
    assert isinstance(r.latency_ms, int)


def test_log_skipped_low_conf_no_pii(caplog):
    low = InferenceResponse(
        requestId="inline-low",
        status="ok",
        confidence=0.5,
        reasoning="low",
        functionCalls=(
            ToolCall(name="recipe", arguments={"ingredients": ["x"], "steps": ["y"]}),
        ),
    )
    gw = InlineRepairGateway(FakeClient(low), threshold=0.8, timeout_ms=600)
    with caplog.at_level(logging.INFO, logger="cookfully.inline_repair"):
        gw.merge_recipe(legacy, low)
    needle_records = [r for r in caplog.records if "needle_inline" in r.message]
    assert needle_records
    assert needle_records[0].applied is False
    assert needle_records[0].confidence == 0.5


def test_service_perf_envelope_logged(caplog):
    # verify intelligence service logs perf envelope without PII
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    from cookfully.intelligence.service import ModelEngine
    from cookfully.intelligence.contracts import InferenceRequest

    # simulate needle returning perf metrics
    fake_needle = MagicMock()
    fake_needle.Needle.return_value.complete.return_value = {
        "function_calls": [{"name": "recipe", "arguments": {"ingredients": ["a"], "steps": ["b"]}}],
        "confidence": 0.9,
        "reasoning": "ok",
        "prefill_tps": 100.0,
        "decode_tps": 50.0,
        "peak_ram_mb": 28.0,
    }

    engine = ModelEngine()
    engine._needle = fake_needle
    engine._error = None
    req = InferenceRequest(requestId="svc-1", operation="recipe_extract", prompt="secret prompt should not be logged")
    with patch.object(Path, "is_file", return_value=True):
        with caplog.at_level(logging.INFO, logger="cookfully.intelligence"):
            resp = engine.complete(req)
            # ensure pass-through for p95 envelope
            assert resp.prefill_tps == 100.0
            assert resp.decode_tps == 50.0
            assert resp.peak_ram_mb == 28.0
    svc_records = [r for r in caplog.records if "needle_infer" in r.message]
    assert svc_records, "expected needle_infer log"
    r = svc_records[0]
    assert hasattr(r, "prefill")
    assert hasattr(r, "decode")
    assert hasattr(r, "peak_ram")
    # ensure user prompt not in log message
    assert "secret prompt" not in r.message
    # also ensure extra strings do not contain prompt
    extra_vals = " ".join(str(v) for v in r.__dict__.values() if isinstance(v, str))
    assert "secret prompt" not in extra_vals
