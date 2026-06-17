"""M2: retry on 429 then succeed; cache hit skips network; rate limiter spaces calls."""


import httpx
import respx

from signal_connector.http.cache import ResponseCache
from signal_connector.http.client import HttpClient
from signal_connector.http.ratelimit import PerHostRateLimiter


def _client(tmp_path, **kw):
    cache = ResponseCache(tmp_path / "cache", ttl_s=3600)
    limiter = PerHostRateLimiter(0.0)  # no real sleeping in tests
    return HttpClient(cache=cache, limiter=limiter, **kw)


@respx.mock
def test_retries_then_succeeds(tmp_path):
    route = respx.get("https://api.example.com/jobs").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.Response(200, text='{"ok": true}'),
        ]
    )
    c = _client(tmp_path)
    body = c.get("https://api.example.com/jobs", use_cache=False)
    assert body == '{"ok": true}'
    assert route.call_count == 3  # two retries then success


@respx.mock
def test_cache_skips_second_network_call(tmp_path):
    route = respx.get("https://api.example.com/board").mock(
        return_value=httpx.Response(200, text="cached-body")
    )
    c = _client(tmp_path)
    first = c.get("https://api.example.com/board")
    second = c.get("https://api.example.com/board")
    assert first == second == "cached-body"
    assert route.call_count == 1  # second served from disk cache


def test_rate_limiter_spaces_calls():
    slept = []
    # call A (last is None) consumes one tick=0.0 → last=0.0.
    # call B reads now=0.2 (0.2s later) → delta 0.2 < 1.0 → sleeps 0.8; post-sleep tick arbitrary.
    ticks = iter([0.0, 0.2, 1.0])

    def fake_clock():
        return next(ticks)

    limiter = PerHostRateLimiter(1.0)
    limiter.wait("https://h.com/a", sleep=lambda s: slept.append(s), clock=fake_clock)
    limiter.wait("https://h.com/b", sleep=lambda s: slept.append(s), clock=fake_clock)
    assert slept and abs(slept[0] - 0.8) < 1e-9
