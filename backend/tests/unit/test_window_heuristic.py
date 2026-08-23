from cookfully.application.inline_repair import _window


def test_window_first_100tok():
    short = "x" * 100
    w, more = _window(short)
    assert w == short[:256]  # no chunk when ≤100 toks (~400 chars)
    assert more is False


def test_window_long_splits():
    long = "a" * 900
    w, more = _window(long)
    assert len(w) <= 256
    assert more is True  # has second window


def test_window_heuristic_no_tiktoken():
    # fallback //4 when tiktoken missing must not raise
    assert _window("hello world")[1] is False
