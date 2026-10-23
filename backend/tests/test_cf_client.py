import httpx
import pytest

from app.cf.client import CFError, CFNotFound, CFUnavailable, CodeforcesClient, backoff_delay
from app.cf.ratelimit import RateLimiter
from tests.conftest import load_fixture


class Recorder:
    def __init__(self) -> None:
        self.sleeps: list[float] = []
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    async def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def make_client(handler, rec: Recorder) -> CodeforcesClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    limiter = RateLimiter(2.1, clock=rec.clock, sleep=rec.sleep)
    return CodeforcesClient(http, limiter, sleep=rec.sleep)


async def test_ok_returns_result_and_sends_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=load_fixture("user_info_tourist.json"))

    users = await make_client(handler, Recorder()).user_info(["TOURIST"])
    assert users[0]["handle"] == "tourist"
    assert "handles=TOURIST" in seen["url"]


async def test_handle_not_found_raises_not_found():
    fx = load_fixture("user_info_not_found.json")

    def handler(request):
        return httpx.Response(fx["http_status"], json=fx["body"])

    with pytest.raises(CFNotFound) as err:
        await make_client(handler, Recorder()).user_info(["thishandledoesnotexist123zz"])
    assert "not found" in err.value.comment


async def test_other_failed_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"status": "FAILED", "comment": "count: Field should be positive"})

    with pytest.raises(CFError) as err:
        await make_client(handler, Recorder()).user_status("tourist", 1, 0)
    assert not isinstance(err.value, (CFNotFound, CFUnavailable))
    assert len(calls) == 1


async def test_call_limit_then_plain_text_502_then_ok_retries_with_backoff():
    responses = [
        httpx.Response(503, json={"status": "FAILED", "comment": "Call limit exceeded"}),
        httpx.Response(502, text="error code: 502"),
        httpx.Response(200, json={"status": "OK", "result": [1, 2]}),
    ]

    def handler(request):
        return responses.pop(0)

    rec = Recorder()
    result = await make_client(handler, rec).user_rating("tourist")
    assert result == [1, 2]
    # backoff 2s, then the limiter tops it up to its 2.1s minimum gap, then backoff 4s.
    assert rec.sleeps == [backoff_delay(0), pytest.approx(0.1), backoff_delay(1)]


async def test_timeouts_exhaust_after_five_retries():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(CFUnavailable):
        await make_client(handler, Recorder()).problemset_problems()
    assert len(calls) == 6  # first attempt + 5 retries


def test_backoff_grows_exponentially_and_caps():
    assert [backoff_delay(i) for i in range(4)] == [2, 4, 8, 16]
    assert backoff_delay(20) == 60
