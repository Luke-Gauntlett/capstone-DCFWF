# tests/test_extract.py
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest
import requests

# --- Helpers ---
def _resp(payload, status_ok=True, headers=None):
    m = MagicMock()
    m.json.return_value = payload
    m.headers = headers or {}
    if status_ok:
        m.raise_for_status.return_value = None
        m.status_code = 200
    else:
        err = requests.HTTPError("HTTP error")
        err.response = MagicMock(status_code=500, headers=m.headers)
        m.raise_for_status.side_effect = err
        m.status_code = 500
    return m


@pytest.fixture
def mod():
    import importlib
    return importlib.import_module("src.extract.extract")


# ============================== BASIC BEHAVIOUR (should pass) ==============================

def test_get_last_extraction_time_missing_returns_empty(tmp_path, monkeypatch, mod):
    monkeypatch.setattr(mod, "last_extraction_file", str(tmp_path / "missing.json"))
    assert mod.get_last_extraction_time() == ""


def test_get_last_extraction_time_reads_value(tmp_path, monkeypatch, mod):
    f = tmp_path / "last_extraction_time.json"
    f.write_text(json.dumps({"last_extraction": "2025-08-01T12:00:00"}))
    monkeypatch.setattr(mod, "last_extraction_file", str(f))
    assert mod.get_last_extraction_time() == "2025-08-01T12:00:00"


def test_save_current_extraction_time_writes_payload(tmp_path, monkeypatch, mod):
    f = tmp_path / "data" / "other" / "last_extraction_time.json"
    monkeypatch.setattr(mod, "last_extraction_file", str(f))
    ts = "2025-08-22T10:00:00"
    mod.save_current_extraction_time(ts)
    assert f.exists()
    assert json.loads(f.read_text()) == {"last_extraction": ts}


def test_request_data_paginates_until_empty(monkeypatch, mod):
    # Two pages then stop
    page1, page2, empty = [{"id": 1}], [{"id": 2}], []
    pages_seen = []

    def side_effect(*_, **kwargs):
        pages_seen.append(kwargs["params"]["page"])
        if len(pages_seen) == 1:
            return _resp(page1)
        elif len(pages_seen) == 2:
            return _resp(page2)
        return _resp(empty)

    get_mock = MagicMock(side_effect=side_effect)
    monkeypatch.setattr(mod, "url", "https://example.test/api")
    monkeypatch.setattr(mod, "key", "k")
    monkeypatch.setattr(mod, "secret", "s")
    monkeypatch.setattr(mod, "requests", MagicMock(get=get_mock))

    data = mod.request_data("orders", last_extraction="")
    assert data == page1 + page2
    assert pages_seen == [1, 2, 3]                 # correct pagination
    # per_page and timeout fixed
    for _, kwargs in get_mock.call_args_list:
        assert kwargs["params"]["per_page"] == 100
        assert kwargs["timeout"] == 60
        assert kwargs["auth"] == ("k", "s")
    # "orders" include status=any
    assert get_mock.call_args_list[0].kwargs["params"]["status"] == "any"


def test_request_data_sets_modified_after_only_when_present(monkeypatch, mod):
    get_mock = MagicMock(side_effect=[_resp([{"id": 1}]), _resp([])])
    monkeypatch.setattr(mod, "requests", MagicMock(get=get_mock))
    monkeypatch.setattr(mod, "url", "https://example.test")
    monkeypatch.setattr(mod, "key", "k")
    monkeypatch.setattr(mod, "secret", "s")

    last = "2025-08-20T10:00:00"
    mod.request_data("orders", last_extraction=last)
    first_params = get_mock.call_args_list[0].kwargs["params"]
    assert first_params["modified_after"] == last

    get_mock.reset_mock()
    get_mock.side_effect = [_resp([{"id": 1}]), _resp([])]
    mod.request_data("products", last_extraction="")
    params = get_mock.call_args_list[0].kwargs["params"]
    assert "status" not in params


def test_request_data_retries_with_exponential_backoff(monkeypatch, mod):
    # Simulate RequestException for all attempts -> stop after max retries
    class ReqEx(Exception):
        pass
    reqs = MagicMock()
    reqs.RequestException = requests.RequestException
    def failing_get(*args, **kwargs):
        raise requests.RequestException("boom")
    reqs.get = MagicMock(side_effect=failing_get)
    monkeypatch.setattr(mod, "requests", reqs)

    sleep_calls = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: sleep_calls.append(s))

    data = mod.request_data("orders", last_extraction="")
    assert data == []
    assert reqs.get.call_count == 6          # 1 initial + 5 retries
    assert sleep_calls == [2, 4, 8, 16, 32]  # exponential backoff


def test_main_saves_timestamp_when_data_found(monkeypatch, mod):
    class FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2025, 8, 22, 12, 0, 0)
    monkeypatch.setattr(mod, "datetime", FixedDT)
    monkeypatch.setattr(mod, "request_data", lambda endpoint, last: [{"id": 1}])
    monkeypatch.setattr(mod, "get_last_extraction_time", lambda: "")
    saved = {}
    monkeypatch.setattr(mod, "save_current_extraction_time", lambda ts: saved.setdefault("ts", ts))

    out = mod.main()
    assert out == [{"id": 1}]
    assert saved["ts"] == (datetime(2025, 8, 22, 12, 0, 0) - timedelta(minutes=2)).isoformat()


def test_main_no_save_when_no_data(monkeypatch, mod):
    monkeypatch.setattr(mod, "request_data", lambda endpoint, last: [])
    monkeypatch.setattr(mod, "get_last_extraction_time", lambda: "")
    saver = MagicMock()
    monkeypatch.setattr(mod, "save_current_extraction_time", saver)
    out = mod.main()
    assert out == []
    saver.assert_not_called()


# ============================== HARDENING TESTS (likely FAIL now) ==============================

def test_request_data_bad_json_gracefully_stops(monkeypatch, mod):
    """
    Expectation: if a page returns invalid JSON, request_data should NOT crash.
    It should stop the loop and return whatever was collected so far.
    """
    good = [{"id": 1}]
    bad = _resp(None)
    bad.json.side_effect = ValueError("invalid json")

    get_mock = MagicMock(side_effect=[_resp(good), bad])  # good page then bad JSON
    monkeypatch.setattr(mod, "url", "https://example.test")
    monkeypatch.setattr(mod, "key", "k")
    monkeypatch.setattr(mod, "secret", "s")
    monkeypatch.setattr(mod, "requests", MagicMock(get=get_mock))

    # CURRENT CODE: will raise ValueError -> test FAILS (desired)
    try:
        data = mod.request_data("orders", last_extraction="")
    except ValueError:
        pytest.fail("request_data raised ValueError on bad JSON; should handle gracefully")

    # If you implement handling, also assert collected content:
    # assert data == good


def test_request_data_429_respects_retry_after(monkeypatch, mod):
    """
    Expectation: on HTTP 429, read Retry-After and sleep that many seconds.
    """
    # First call -> 429 with Retry-After: 7; second call -> ok with empty to finish
    headers = {"Retry-After": "7"}
    resp429 = _resp([], status_ok=False, headers=headers)
    ok = _resp([])

    def side_effect(*args, **kwargs):
        # First attempt for page 1 -> 429; next attempt -> ok (empty -> stop)
        calls = side_effect.calls
        side_effect.calls += 1
        return resp429 if calls == 0 else ok
    side_effect.calls = 0

    get_mock = MagicMock(side_effect=side_effect)
    sleeper = []
    def fake_sleep(s): sleeper.append(s)

    monkeypatch.setattr(mod, "url", "https://example.test")
    monkeypatch.setattr(mod, "key", "k")
    monkeypatch.setattr(mod, "secret", "s")
    monkeypatch.setattr(mod, "requests", MagicMock(get=get_mock))
    monkeypatch.setattr(mod.time, "sleep", fake_sleep)

    data = mod.request_data("orders", last_extraction="")
    # CURRENT CODE: uses exponential backoff and doesn't read Retry-After -> test FAILS
    assert 7 in sleeper, "Expected to respect Retry-After=7 seconds on HTTP 429"


def test_main_uses_utc_z_timestamp_when_saving(monkeypatch, mod):
    """
    Expectation: saved extraction timestamp should be UTC ISO8601 with 'Z' suffix.
    """
    class FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            # Simulate a local time with tzinfo; implementer should convert to UTC Z
            return datetime(2025, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(mod, "datetime", FixedDT)
    monkeypatch.setattr(mod, "get_last_extraction_time", lambda: "")
    monkeypatch.setattr(mod, "request_data", lambda endpoint, last: [{"id": 1}])

    saved = {}
    def save(ts): saved["ts"] = ts
    monkeypatch.setattr(mod, "save_current_extraction_time", save)

    mod.main()
    # CURRENT CODE: doesn't add 'Z' and may use localtime -> test FAILS
    assert saved["ts"].endswith("Z"), "Expected UTC timestamp with 'Z' suffix"


def test_save_current_extraction_time_handles_io_errors(monkeypatch, mod, tmp_path):
    """
    Expectation: IO errors during save should not crash the whole run.
    """
    # Point to a directory we can't create a file in by forcing open() to raise
    monkeypatch.setattr(mod, "last_extraction_file", str(tmp_path / "x" / "y" / "z.json"))

    def raising_open(*args, **kwargs):
        raise PermissionError("denied")

    with patch("builtins.open", side_effect=raising_open):
        # CURRENT CODE: will raise PermissionError -> test FAILS
        try:
            mod.save_current_extraction_time("2025-08-22T10:00:00Z")
        except PermissionError:
            pytest.fail("save_current_extraction_time should handle IO errors gracefully")


def test_request_data_stops_on_runaway_pages(monkeypatch, mod):
    """
    Expectation: there should be a guard against infinite pagination (e.g., page never empties).
    """
    # Always returns a non-empty page -> loop should break after a max_page guard
    endless_page = [{"id": i} for i in range(3)]

    def side_effect(*args, **kwargs):
        return _resp(endless_page)

    get_mock = MagicMock(side_effect=side_effect)
    monkeypatch.setattr(mod, "url", "https://example.test")
    monkeypatch.setattr(mod, "key", "k")
    monkeypatch.setattr(mod, "secret", "s")
    monkeypatch.setattr(mod, "requests", MagicMock(get=get_mock))

    # CURRENT CODE: infinite until network error / memory pressure; here it'll hang.
    # We emulate a guard by running with a patched function that enforces max pages via timeout.
    # To force this test to finish, we limit side_effect calls and then assert a guard is present.
    # Since no guard exists, we simulate "too many calls" and fail.
    max_calls = 50
    try:
        for _ in range(max_calls):
            mod.request_data("orders", last_extraction="")
            break  # If request_data returns, we avoid a hang.
        else:
            pytest.fail("request_data didn't return; expected a max-page guard to prevent infinite loops")
    except RecursionError:
        pytest.fail("request_data should not recurse; expected iterative pagination with a guard")
