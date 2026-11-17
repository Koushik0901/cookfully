from cookfully.application.login_throttle import LoginThrottle


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _throttle(clock: Clock, **overrides: float) -> LoginThrottle:
    return LoginThrottle(clock=clock, **overrides)  # type: ignore[arg-type]


def test_free_attempts_then_exponential_lock_capped() -> None:
    clock = Clock()
    throttle = _throttle(clock)
    for _ in range(4):
        throttle.record_failure("owner")
        assert throttle.retry_after("owner") == 0
    throttle.record_failure("owner")  # 5th failure
    assert throttle.retry_after("owner") == 31
    clock.now += 31
    assert throttle.retry_after("owner") == 0
    throttle.record_failure("owner")  # 6th: 60 s
    assert 59 <= throttle.retry_after("owner") <= 61
    for _ in range(10):
        clock.now += 1000
        throttle.record_failure("owner")
    assert throttle.retry_after("owner") <= 301


def test_success_resets_and_keys_are_independent() -> None:
    clock = Clock()
    throttle = _throttle(clock)
    for _ in range(5):
        throttle.record_failure("owner", "ip:1.1.1.1")
    assert throttle.retry_after("ip:2.2.2.2") == 0
    assert throttle.retry_after("ip:1.1.1.1") > 0
    clock.now += 500
    throttle.record_success("owner", "ip:1.1.1.1")
    assert throttle.retry_after("owner", "ip:1.1.1.1") == 0


def test_old_failures_are_forgotten() -> None:
    clock = Clock()
    throttle = _throttle(clock, forget_after_seconds=100)
    for _ in range(4):
        throttle.record_failure("owner")
    clock.now += 101
    throttle.record_failure("owner")  # counter restarted, so this is failure 1 not 5
    assert throttle.retry_after("owner") == 0


def test_full_table_never_evicts_locked_entries_or_blocks_the_global_key() -> None:
    clock = Clock()
    throttle = _throttle(clock, max_entries=3)
    for _ in range(5):
        throttle.record_failure("owner")
    for index in range(50):
        throttle.record_failure(f"ip:{index}")
    assert throttle.retry_after("owner") > 0
