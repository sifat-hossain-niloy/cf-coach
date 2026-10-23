import asyncio

from app.cf.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_first_call_does_not_wait():
    clock = FakeClock()
    limiter = RateLimiter(2.1, clock=clock, sleep=clock.sleep)
    await limiter.acquire()
    assert clock.sleeps == []


async def test_back_to_back_calls_are_spaced_by_min_interval():
    clock = FakeClock()
    limiter = RateLimiter(2.1, clock=clock, sleep=clock.sleep)
    stamps = []
    for _ in range(4):
        await limiter.acquire()
        stamps.append(clock.now)
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(abs(g - 2.1) < 1e-9 for g in gaps)


async def test_no_wait_when_enough_time_already_passed():
    clock = FakeClock()
    limiter = RateLimiter(2.1, clock=clock, sleep=clock.sleep)
    await limiter.acquire()
    clock.now += 5
    await limiter.acquire()
    assert clock.sleeps == []


async def test_partial_wait():
    clock = FakeClock()
    limiter = RateLimiter(2.1, clock=clock, sleep=clock.sleep)
    await limiter.acquire()
    clock.now += 1.6
    await limiter.acquire()
    assert len(clock.sleeps) == 1 and abs(clock.sleeps[0] - 0.5) < 1e-9


async def test_concurrent_callers_are_serialised_globally():
    clock = FakeClock()
    limiter = RateLimiter(2.1, clock=clock, sleep=clock.sleep)
    stamps: list[float] = []

    async def worker():
        await limiter.acquire()
        stamps.append(clock.now)

    await asyncio.gather(*(worker() for _ in range(5)))
    stamps.sort()
    assert all(b - a >= 2.1 - 1e-9 for a, b in zip(stamps, stamps[1:]))
