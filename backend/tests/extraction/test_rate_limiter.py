"""RateLimiter tests — mocked clock/sleep, no real waiting."""

from __future__ import annotations

import random

from backend.app.extraction.rate_limiter import (
    RateLimiter,
    estimate_tokens,
)


class FakeClock:
    """Virtual clock; sleep() advances it. No real time passes."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s

    def advance(self, s: float) -> None:
        self.t += s


def _no_jitter_rng():
    r = random.Random()
    r.uniform = lambda a, b: 0.0
    return r


def _limiter(clock, *, max_rpm=8, max_tpm=200_000):
    return RateLimiter(
        max_rpm=max_rpm, max_tpm=max_tpm,
        clock=clock.now, sleep=clock.sleep, rng=_no_jitter_rng(),
    )


# --- RPM interval -------------------------------------------------------


def test_rpm_enforces_min_interval():
    """8 RPM → 7.5s interval. Back-to-back requests are spaced 7.5s."""
    clk = FakeClock()
    lim = _limiter(clk)
    lim.acquire(10)            # t=0, no wait (first request)
    info = lim.acquire(10)     # must wait 7.5s
    assert abs(info.rpm_wait_s - 7.5) < 1e-6
    assert abs(clk.now() - 7.5) < 1e-6


def test_rpm_accounts_for_time_already_spent():
    """A slow call that already consumed the interval adds NO idle."""
    clk = FakeClock()
    lim = _limiter(clk)
    lim.acquire(10)            # t=0, next allowed at 7.5
    clk.advance(20.0)          # simulate a 20s API call
    info = lim.acquire(10)     # 20 > 7.5 → no wait
    assert info.rpm_wait_s == 0.0
    assert clk.now() == 20.0


# --- TPM window ---------------------------------------------------------


def test_tpm_holds_when_window_would_overflow():
    """Two large requests that together exceed TPM: the second is held
    until the first ages out of the 60s window."""
    clk = FakeClock()
    lim = _limiter(clk, max_rpm=1000, max_tpm=200_000)  # RPM not binding
    lim.acquire(150_000)            # t=0, window=150k
    info = lim.acquire(100_000)     # 250k > 200k → hold ~60s
    assert info.tpm_wait_s > 0
    assert info.tpm_bound is True
    assert abs(clk.now() - 60.0) < 1e-6  # waited for the first to age out


def test_tpm_no_hold_when_under_budget():
    clk = FakeClock()
    lim = _limiter(clk, max_rpm=1000, max_tpm=200_000)
    lim.acquire(50_000)
    info = lim.acquire(50_000)      # 100k < 200k → no TPM wait
    assert info.tpm_wait_s == 0.0


def test_tpm_admits_oversized_single_request_alone():
    """A request bigger than the whole budget can't fit anything; once
    the window is empty it is admitted alone rather than deadlocking."""
    clk = FakeClock()
    lim = _limiter(clk, max_rpm=1000, max_tpm=200_000)
    info = lim.acquire(300_000)     # > budget, window empty → admit now
    assert info.tpm_wait_s == 0.0


def test_tpm_window_ages_out():
    """Tokens older than 60s no longer count against the window."""
    clk = FakeClock()
    lim = _limiter(clk, max_rpm=1000, max_tpm=200_000)
    lim.acquire(180_000)            # t=0
    clk.advance(61.0)               # older than 60s window
    info = lim.acquire(180_000)     # old tokens expired → no wait
    assert info.tpm_wait_s == 0.0


def test_estimate_tokens_is_chars_over_4():
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 1  # floor of 1
