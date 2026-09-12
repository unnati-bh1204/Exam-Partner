from unittest.mock import MagicMock

import pytest

from app.retry import with_retries


def test_with_retries_returns_result_on_first_success():
    fn = MagicMock(return_value="ok")
    result = with_retries(fn, max_attempts=3, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 1


def test_with_retries_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    fn = MagicMock(side_effect=[RuntimeError("timeout"), RuntimeError("timeout"), "ok"])
    result = with_retries(fn, max_attempts=3, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 3


def test_with_retries_raises_last_exception_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    fn = MagicMock(side_effect=RuntimeError("still failing"))
    with pytest.raises(RuntimeError, match="still failing"):
        with_retries(fn, max_attempts=3, base_delay=0)
    assert fn.call_count == 3
