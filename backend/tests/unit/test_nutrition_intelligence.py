from decimal import Decimal

from cookfully.application.nutrition_intelligence import (
    HostCapacity,
    ModelMetadata,
    estimate_resources,
)


def test_hashing_estimate_is_small_and_safe_at_default_concurrency() -> None:
    estimate = estimate_resources(
        backend="hashing",
        model_name="BAAI/bge-small-en-v1.5",
        concurrency=1,
        metadata=None,
        capacity=HostCapacity(cpu_cores=8, memory_bytes=8 * 1024**3, disk_free_bytes=20 * 1024**3),
        active_food_count=8_100,
    )

    assert estimate.download_bytes == 0
    assert estimate.model_memory_bytes < 128 * 1024**2
    assert estimate.total_memory_bytes > estimate.model_memory_bytes
    assert estimate.status == "safe"


def test_fastembed_estimate_warns_when_concurrency_exceeds_cpu_headroom() -> None:
    estimate = estimate_resources(
        backend="fastembed",
        model_name="BAAI/bge-small-en-v1.5",
        concurrency=4,
        metadata=ModelMetadata(
            revision="abc123",
            download_bytes=133_466_304,
            parameter_count=33_360_512,
            dimensions=384,
        ),
        capacity=HostCapacity(
            cpu_cores=2, memory_bytes=256 * 1024**2, disk_free_bytes=20 * 1024**3
        ),
        active_food_count=8_100,
    )

    assert estimate.status == "blocked"
    assert estimate.required_cpu_cores == 4
    assert estimate.total_memory_bytes > 256 * 1024**2
    assert estimate.warnings
    assert estimate.memory_headroom_bytes < Decimal(0)
