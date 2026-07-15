"""
Async HTTP client with retry, exponential backoff, rate limiting, and
MyMoviz cookie-based authentication support.

Built on top of :mod:`aiohttp` and :mod:`aiohttp_retry`. All scrapers and
external integrations should go through :class:`HttpClient` so that error
handling, timeouts, retries, and polite delays stay centralized.

When the primary aiohttp transport receives a small/error page that looks
like Cloudflare's anti-bot block (e.g. "Error 404, Page not found" inside
a 200 response of <20KB), the client transparently falls back to
``curl_cffi`` which impersonates a real Chrome browser and can bypass
Cloudflare's bot detection. This is essential for Railway/datacenter IPs.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp
from aiohttp_retry import ExponentialRetry, RetryClient

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import curl_cffi for Cloudflare bypass
try:
    from curl_cffi import requests as cffi_requests

    _HAS_CFFI = True
except ImportError:  # pragma: no cover
    _HAS_CFFI = False
    logger.warning("curl_cffi not installed - Cloudflare bypass fallback disabled")


class HttpClient:
    """A polite, retry-aware async HTTP client.

    The same instance is reused across scrapers (see ``main.py``). Closing
    it during shutdown ensures underlying TCP connectors are released.

    MyMoviz authentication:
    * If ``MYMOVIZ_COOKIE`` is set in env, it is sent as the ``Cookie``
      header on every request to ``mymoviz.co``.
    * If only ``MYMOVIZ_EMAIL`` / ``MYMOVIZ_PASSWORD`` are set, the bot
      performs a login at startup and reuses the returned session cookie
      jar.
    """

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._retry_client: Optional[RetryClient] = None
        self._last_request_at: float = 0.0
        self._rate_lock = asyncio.Lock()
        self._cookie_jar: Optional[aiohttp.CookieJar] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def init(self) -> None:
        """Initialize the underlying aiohttp session and retry wrapper."""
        if self._session is not None and not self._session.closed:
            return

        timeout = aiohttp.ClientTimeout(total=settings.request_timeout)
        headers = {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
            # IMPORTANT: do NOT include 'br' here unless the brotli library is
            # installed, otherwise aiohttp will fail to decode the response.
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": settings.classic_base_url,
        }

        # If a raw cookie string is provided, send it on every request
        if settings.mymoviz_cookie:
            headers["Cookie"] = settings.mymoviz_cookie
            logger.info("HttpClient initialized with raw Cookie header from env.")

        # Persistent cookie jar - captures Set-Cookie from login responses
        self._cookie_jar = aiohttp.CookieJar(unsafe=True)

        connector = aiohttp.TCPConnector(
            limit=20,
            limit_per_host=5,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector,
            cookie_jar=self._cookie_jar,
        )

        retry_options = ExponentialRetry(
            attempts=settings.request_max_retries,
            start_timeout=settings.request_backoff_factor,
            max_timeout=10.0,
            factor=2.0,
            statuses={500, 502, 503, 504, 429},
            exceptions={
                aiohttp.ClientError,
                aiohttp.ClientResponseError,
                asyncio.TimeoutError,
            },
        )
        self._retry_client = RetryClient(client_session=self._session, retry_options=retry_options)
        logger.info(
            "HttpClient initialized (timeout={}s, retries={})",
            settings.request_timeout,
            settings.request_max_retries,
        )

    async def close(self) -> None:
        """Close the underlying session."""
        if self._retry_client is not None:
            await self._retry_client.close()
            self._retry_client = None
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None
        logger.info("HttpClient closed.")

    # ------------------------------------------------------------------
    # MyMoviz login
    # ------------------------------------------------------------------
    async def login_to_mymoviz(self) -> bool:
        """Perform a login to MyMoviz with the configured credentials.

        Returns True on success. Stores the session cookie in the cookie jar.
        Skipped if no credentials are configured or if a raw cookie is set.

        MyMoviz uses CSRF tokens + optional CAPTCHA, so this may fail.
        In that case, the bot will continue to function for public pages but
        download links may not be accessible. Use MYMOVIZ_COOKIE env var to
        supply a pre-authenticated cookie string as a workaround.
        """
        if settings.mymoviz_cookie:
            logger.info("Skipping MyMoviz login - raw MYMOVIZ_COOKIE already set.")
            return True

        if not settings.mymoviz_email or not settings.mymoviz_password:
            logger.info("Skipping MyMoviz login - no credentials configured.")
            return False

        await self.init()
        assert self._session is not None

        login_url = f"{settings.classic_base_url}/signin"

        # Step 1: GET the signin page to fetch the CSRF token
        try:
            logger.info("Fetching MyMoviz signin page for CSRF token: {}", login_url)
            async with self._session.get(login_url) as resp:
                html = await resp.text(errors="replace")
                if resp.status >= 400:
                    logger.warning("Signin page returned status {}", resp.status)
                    return False
        except Exception as exc:
            logger.warning("Failed to fetch signin page: {}", exc)
            return False

        # Step 2: Extract CSRF token from the form
        import re
        csrf_match = re.search(
            r'name="_csrf"\s+value="([^"]+)"', html
        )
        if not csrf_match:
            logger.warning("CSRF token not found on signin page.")
            return False
        csrf_token = csrf_match.group(1)
        logger.info("CSRF token acquired from signin page.")

        # Step 3: Detect CAPTCHA requirement
        has_captcha = "capcode" in html
        if has_captcha:
            logger.warning(
                "⚠ MyMoviz signin page has a CAPTCHA. Automated login may fail. "
                "Consider setting MYMOVIZ_COOKIE env var with a manually-obtained cookie."
            )

        # Step 4: Submit login form
        try:
            logger.info("Submitting MyMoviz login form to: {}", login_url)
            payload = {
                "_csrf": csrf_token,
                "email": settings.mymoviz_email,
                "password": settings.mymoviz_password,
                "random_param": "1",
                # If CAPTCHA present, we cannot solve it - submit anyway and check response
                "capcode": "",
            }
            async with self._session.post(
                login_url,
                data=payload,
                allow_redirects=True,
            ) as resp:
                text = await resp.text(errors="replace")
                status = resp.status

                # Capture all cookies that were set during this request
                cookies_after = self.get_cookie_string()
                logger.info(
                    "Login POST status={}, response_size={}, cookies_acquired='{}'",
                    status, len(text), cookies_after[:200] if cookies_after else "(none)",
                )

                # SUCCESS heuristics (must be DEFINITIVE):
                # 1. "خروج" (logout) link appears in navbar when logged in
                # 2. "/panel" link appears in navbar
                # 3. "/signout" link appears
                # We do NOT use "not on signin page" because a failed login
                # still shows the signin form without the "ورود به سایت" header
                # (it shows the form with an error message instead).
                is_logged_in = (
                    "خروج" in text
                    or "/signout" in text
                    or "/panel/" in text
                    or "panel/watchlist" in text
                )

                # FAILURE indicators:
                # - "capcode" present (signin form shown again)
                # - Response is small (< 15000 bytes = likely the signin form)
                # - Contains "کلمه عبور" (password field) = signin form
                is_signin_form = (
                    "capcode" in text
                    or "کلمه عبور" in text
                    or len(text) < 15000
                )

                if is_logged_in and not is_signin_form:
                    logger.info("✅ MyMoviz login succeeded! (verified)")
                    return True

                logger.warning(
                    "❌ MyMoviz login FAILED (status={}, logged_in={}, signin_form={}, "
                    "response_size={}). Likely CAPTCHA blocked automated login. "
                    "Set MYMOVIZ_COOKIE env var manually.",
                    status, is_logged_in, is_signin_form, len(text),
                )
                return False
        except Exception as exc:
            logger.warning("MyMoviz login POST failed: {}", exc)
            return False

    def get_cookie_string(self) -> str:
        """Return the current cookies as a Cookie header string."""
        if not self._cookie_jar:
            return ""
        cookies = []
        for cookie in self._cookie_jar:
            cookies.append(f"{cookie.key}={cookie.value}")
        return "; ".join(cookies)

    # ------------------------------------------------------------------
    # Polite delay between requests
    # ------------------------------------------------------------------
    async def _respect_rate_limit(self) -> None:
        if settings.rate_limit_delay <= 0:
            return
        async with self._rate_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_at
            wait = settings.rate_limit_delay - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = asyncio.get_event_loop().time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def get(self, url: str, **kwargs: Any) -> str:
        """Perform a GET request with retry; return response text.

        Uses aiohttp first. If the response looks like a Cloudflare anti-bot
        block (small page with "Error 404" or similar), falls back to
        curl_cffi which impersonates Chrome and can bypass the block.

        Raises:
            aiohttp.ClientError: if all retries are exhausted.
            asyncio.TimeoutError: on persistent timeouts.
        """
        await self.init()
        await self._respect_rate_limit()
        assert self._retry_client is not None

        # Log cookies being sent for mymoviz.co requests (debug)
        if "mymoviz.co" in url:
            cookies_str = self.get_cookie_string()
            logger.info("GET {} | cookies='{}'", url, cookies_str[:100] if cookies_str else "(none)")
        else:
            logger.debug("GET {}", url)

        async with self._retry_client.get(url, **kwargs) as resp:
            if resp.status >= 400:
                logger.warning("HTTP {} for {}", resp.status, url)
                resp.raise_for_status()
            text = await resp.text(errors="replace")
            logger.debug("Response {} bytes from {}", len(text), url)

            # Detect Cloudflare anti-bot block on mymoviz.co:
            # The block returns a small (~14KB) 200 page with "Error 404" inside
            if (
                "mymoviz.co" in url
                and len(text) < 20000
                and ("Error 404" in text or "Page not found" in text)
                and _HAS_CFFI
            ):
                logger.warning(
                    "Cloudflare block detected ({} bytes, contains 'Error 404') - "
                    "falling back to curl_cffi for {}", len(text), url,
                )
                fallback_text = await self._cffi_get(url)
                if fallback_text and len(fallback_text) > 20000:
                    logger.info(
                        "curl_cffi fallback succeeded: {} bytes from {}",
                        len(fallback_text), url,
                    )
                    return fallback_text
                logger.warning("curl_cffi fallback also returned small/empty response")

            return text

    async def _cffi_get(self, url: str) -> Optional[str]:
        """Fetch URL using curl_cffi (Chrome impersonation) in a thread.

        This bypasses Cloudflare's anti-bot detection that blocks aiohttp
        on datacenter IPs (Railway, Heroku, etc.).
        """
        if not _HAS_CFFI:
            return None

        # Get current cookies from aiohttp's jar and pass them to curl_cffi
        cookies_dict: dict[str, str] = {}
        if self._cookie_jar is not None:
            for cookie in self._cookie_jar:
                cookies_dict[cookie.key] = cookie.value

        def _do_request() -> Optional[str]:
            try:
                # impersonate="chrome120" tells curl_cffi to send TLS fingerprint
                # and HTTP/2 settings matching Chrome 120, which Cloudflare accepts.
                r = cffi_requests.get(
                    url,
                    impersonate="chrome120",
                    cookies=cookies_dict,
                    timeout=settings.request_timeout,
                    allow_redirects=True,
                )
                return r.text
            except Exception as exc:
                logger.warning("curl_cffi request failed: {}", exc)
                return None

        # Run blocking curl_cffi in a thread to not block the event loop
        return await asyncio.get_event_loop().run_in_executor(None, _do_request)

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        """Fetch and parse JSON with retry semantics."""
        await self.init()
        await self._respect_rate_limit()
        assert self._retry_client is not None
        async with self._retry_client.get(url, **kwargs) as resp:
            if resp.status >= 400:
                logger.warning("HTTP {} for {}", resp.status, url)
                resp.raise_for_status()
            return await resp.json()

    async def post(self, url: str, data: Any = None, **kwargs: Any) -> str:
        """Perform a POST request with retry; return response text."""
        await self.init()
        await self._respect_rate_limit()
        assert self._retry_client is not None
        logger.debug("POST {}", url)
        async with self._retry_client.post(url, data=data, **kwargs) as resp:
            if resp.status >= 400:
                logger.warning("HTTP {} for {}", resp.status, url)
                resp.raise_for_status()
            return await resp.text(errors="replace")


# Module-level singleton
http_client = HttpClient()
