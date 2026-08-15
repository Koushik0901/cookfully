from __future__ import annotations

from cookfully.application.reference_data import (
    PINNED_RELEASES,
    PinnedRelease,
    install_input_hash,
)


def test_pinned_releases_cover_the_two_install_units() -> None:
    assert set(PINNED_RELEASES) == {"foundation_sr_legacy", "branded"}
    foundation = PINNED_RELEASES["foundation_sr_legacy"]
    assert [item.dataset_type for item in foundation] == ["foundation", "sr_legacy"]
    assert all(item.release_id.startswith(("foundation-", "sr-legacy-")) for item in foundation)
    assert PINNED_RELEASES["branded"][0].dataset_type == "branded_food"


def test_pinned_releases_use_the_fdc_bulk_download_pattern() -> None:
    for unit in PINNED_RELEASES.values():
        for release in unit:
            assert release.source_url.startswith("https://fdc.nal.usda.gov/fdc-datasets/")
            assert release.source_url.endswith(".zip")
            assert release.released_on is not None


def test_install_input_hash_is_deterministic_and_order_independent() -> None:
    first = install_input_hash(("foundation_sr_legacy", "branded"))
    second = install_input_hash(("branded", "foundation_sr_legacy"))
    assert first == second
    assert install_input_hash(("foundation_sr_legacy",)) != first
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64