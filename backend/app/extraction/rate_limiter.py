"""Client-side token-bucket rate limiter: RPM + TPM.

Goal: never trip an avoidable 429. Two independent gates, both enforced
on every request:

  RPM — a minimum inter-request INTERVAL (60/RPM seconds) measured from
        the START of one request to the start of the next, so time
        already spent inside a slow API call counts toward the interval
        (a 20s call adds no idle on top of a 7.5s interval). ±jitter so
        retries across a fleet don't re-align.

  TPM — a rolling 60-second window of admitted input tokens. A request
        that would push the window over `max_tpm` is held until enough
        old tokens age out. This is what actually binds on full text
        (a 99k-token paper is well under 8 RPM but can breach 250k TPM).

Thread-safe: a single shared instance guards concurrent callers with a
lock. Clock/sleep are injectable so tests run with no real sleeping.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class WaitInfo:
    rpm_wait_s: float = 0.0
    tpm_wait_s: float = 0.0

    @property
    def total_s(self) -> float:
        return self.rpm_wait_s + self.tpm_wait_s

    @property
    def tpm_bound(self) -> bool:
        """True if TPM was the dominant reason for waiting — lets the
        caller log which limit is actually binding."""
        return self.tpm_wait_s > self.rpm_wait_s and self.tpm_wait_s > 0


class RateLimiter:
    def __init__(
        self,
        *,
        max_rpm: int,
        max_tpm: int,
        jitter_frac: float = 0.10,
        clock=time.monotonic,
        sleep=time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        if max_rpm <= 0 or max_tpm <= 0:
            raise ValueError("max_rpm and max_tpm must be positive")
        self._max_rpm = max_rpm
        self._max_tpm = max_tpm
        self._base_interval = 60.0 / max_rpm
        self._jitter_frac = jitter_frac
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._lock = threading.Lock()

        self._next_allowed = 0.0  # earliest clock time the next request may start
        self._window: deque[tuple[float, int]] = deque()  # (admit_time, tokens)
        self.total_wait_s = 0.0

    def _interval(self) -> float:
        j = 1.0 + self._rng.uniform(-self._jitter_frac, self._jitter_frac)
        return self._base_interval * j

    def _window_tokens(self, now: float) -> int:
        while self._window and now - self._window[0][0] >= 60.0:
            self._window.popleft()
        return sum(t for _, t in self._window)

    def acquire(self, est_tokens: int) -> WaitInfo:
        """Block until both gates allow a request of `est_tokens` input
        tokens, then admit it. Returns how long we waited and why."""
        info = WaitInfo()
        with self._lock:
            now = self._clock()

            # --- RPM gate: honor the min inter-request interval.
            if now < self._next_allowed:
                info.rpm_wait_s = self._next_allowed - now
                self._sleep(info.rpm_wait_s)
                now = self._clock()

            # --- TPM gate: hold until the rolling window has room.
            # A single request larger than the whole budget can never
            # fit; admit it alone once the window is empty (it will
            # briefly exceed, but there's no other way to send it).
            while True:
                in_window = self._window_tokens(now)
                if in_window + est_tokens <= self._max_tpm or in_window == 0:
                    break
                # Wait until the oldest entry ages out of the 60s window.
                oldest_admit = self._window[0][0]
                wait = max(0.0, 60.0 - (now - oldest_admit))
                # guard against zero-wait spin
                wait = wait if wait > 0 else 0.001
                info.tpm_wait_s += wait
                self._sleep(wait)
                now = self._clock()

            # Admit: record start time for the next RPM interval and add
            # tokens to the window. Interval is measured from THIS start,
            # so a slow call consumes it.
            self._next_allowed = now + self._interval()
            self._window.append((now, est_tokens))
            self.total_wait_s += info.total_s
            return info


def estimate_tokens(text: str, *, chars_per_token: int = 4) -> int:
    """Conservative input-token estimate (chars/4). Used to gate TPM
    before sending — deliberately rough and slightly over, so we hold
    early rather than breach."""
    return max(1, len(text) // chars_per_token)


__all__ = ["RateLimiter", "WaitInfo", "estimate_tokens"]
