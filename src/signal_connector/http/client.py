"""Resilient HTTP client: retry/backoff + per-host rate limit + on-disk cache.

One shared client for all sources. GETs only (we scrape public read-only endpoints).
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from signal_connector.http.cache import ResponseCache
from signal_connector.http.ratelimit import PerHostRateLimiter
from signal_connector.observability.logging import get_logger
from signal_connector.settings import settings

log = get_logger("http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RetryableStatus(Exception):
    def __init__(self, status: int, url: str):
        self.status = status
        self.url = url
        super().__init__(f"retryable status {status} for {url}")


class HttpClient:
    def __init__(
        self,
        *,
        cache: ResponseCache | None = None,
        limiter: PerHostRateLimiter | None = None,
        client: httpx.Client | None = None,
    ):
        self.cache = cache or ResponseCache(settings.http_cache_dir, settings.http_cache_ttl_s)
        self.limiter = limiter or PerHostRateLimiter(settings.http_rate_limit_per_host_s)
        self._client = client or httpx.Client(
            timeout=settings.http_timeout_s,
            follow_redirects=True,
            headers={"User-Agent": "signalbase-location-connector/0.1 (+demo; contact: abhishek)"},
        )

    def get(self, url: str, *, use_cache: bool = True, params: dict | None = None) -> str:
        cache_key = url + ("?" + httpx.QueryParams(params).__str__() if params else "")
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                log.debug("cache_hit", url=url)
                return cached

        body = self._get_with_retry(url, params)
        if use_cache:
            self.cache.set(cache_key, body)
        return body

    @retry(
        retry=retry_if_exception_type((RetryableStatus, httpx.TransportError)),
        wait=wait_exponential_jitter(initial=0.5, max=8.0),
        stop=stop_after_attempt(settings.http_max_retries),
        reraise=True,
    )
    def _get_with_retry(self, url: str, params: dict | None) -> str:
        self.limiter.wait(url)
        resp = self._client.get(url, params=params)
        if resp.status_code in RETRYABLE_STATUS:
            log.warning("retryable_status", url=url, status=resp.status_code)
            raise RetryableStatus(resp.status_code, url)
        resp.raise_for_status()
        return resp.text

    def close(self) -> None:
        self._client.close()
