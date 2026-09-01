"""
The one HTTP client. Every outbound request in this project goes through here.

Why it is centralised:
  - the providers need different headers to answer at all (BSE returns 403
    without a Referer; Moneycontrol wants a browser User-Agent), and that
    knowledge belongs in one table rather than sprinkled through five modules
  - we are a guest on someone else's infrastructure, so a per-host rate limit
    is not optional politeness, it is the condition of continuing to work
  - DATA_MODE=fixtures must be able to guarantee that no socket opens, and one
    chokepoint is the only way to actually guarantee that
"""
import asyncio
import time
from typing import Optional
from urllib.parse import urlsplit

import httpx

import feeds

TIMEOUT_S = 8.0
MIN_INTERVAL_S = 0.35         # per host; we are a guest, not a customer. Roughly
                              # 3/sec, and every response is cached, so a warm
                              # request path issues no traffic at all.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Headers each host needs. Discovered by trying: bseindia returns 403 Access
# Denied without the Referer, and moneycontrol rejects a bare python UA.
HOST_HEADERS = {
    "api.bseindia.com":              {"Referer": "https://www.bseindia.com/",
                                      "Accept": "application/json"},
    "www.bseindia.com":              {"Referer": "https://www.bseindia.com/"},
    "priceapi.moneycontrol.com":     {"Referer": "https://www.moneycontrol.com/"},
    "www.moneycontrol.com":          {"Referer": "https://www.moneycontrol.com/"},
}

_client: Optional[httpx.AsyncClient] = None
_last_hit: dict[str, float] = {}
_host_locks: dict[str, asyncio.Lock] = {}


class OfflineError(RuntimeError):
    """Raised when something tries to reach the network in DATA_MODE=fixtures."""


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=TIMEOUT_S,
            follow_redirects=True,
            headers={"User-Agent": _UA, "Accept-Language": "en-IN,en;q=0.9"},
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def _throttle(host: str) -> None:
    lock = _host_locks.setdefault(host, asyncio.Lock())
    async with lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_hit.get(host, 0.0))
        if wait > 0:
            await asyncio.sleep(wait)
        _last_hit[host] = time.monotonic()


async def fetch(url: str, *, params: dict | None = None,
                retries: int = 1) -> httpx.Response:
    """
    GET with per-host headers, throttling and one retry on a transient failure.

    Raises rather than returning a sentinel: every caller is already inside an
    agent wrapped by safety.run_agent_safely, or inside a provider that has its
    own fallback chain. Swallowing the error here would hide which provider
    broke from data_quality.warnings.
    """
    if feeds.offline():
        raise OfflineError(f"DATA_MODE=fixtures forbids network access ({url})")

    host = urlsplit(url).netloc
    headers = HOST_HEADERS.get(host, {})

    last: Exception | None = None
    for attempt in range(retries + 1):
        await _throttle(host)
        try:
            r = await _get_client().get(url, params=params, headers=headers)
            if r.status_code >= 500 and attempt < retries:
                last = httpx.HTTPStatusError(f"{r.status_code} from {host}",
                                             request=r.request, response=r)
                continue
            r.raise_for_status()
            return r
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
            if attempt >= retries:
                break
    raise last if last else RuntimeError(f"fetch failed: {url}")


async def fetch_json(url: str, *, params: dict | None = None) -> dict | list:
    r = await fetch(url, params=params)
    # Several of these endpoints answer with text/html or text/plain while the
    # body is perfectly good JSON, so parse the body rather than trusting the
    # declared content type.
    return r.json()


async def fetch_text(url: str, *, params: dict | None = None) -> str:
    return (await fetch(url, params=params)).text


async def fetch_bytes(url: str, *, params: dict | None = None) -> bytes:
    return (await fetch(url, params=params)).content
