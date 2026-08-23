from cookfully.infrastructure.config import Settings


def test_inline_settings_defaults():
    s = Settings(_env_file=None)
    assert s.intelligence_inline_enabled is False
    assert s.intelligence_inline_threshold == 0.80
    assert s.intelligence_inline_timeout_ms == 600
    assert s.intelligence_timeout_seconds == 2.0
