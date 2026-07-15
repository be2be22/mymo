"""
Async HTTP client with retry, exponential backoff, rate limiting, and
MyMoviz cookie-based authentication support.

Built on top of :mod:`aiohttp` and :mod:`aiohttp_retry`. All scrapers and
external integrations should go through :class:`HttpClient` so that error
handling, timeouts, retries, and polite delays stay centralized.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp
from aiohttp_retry import ExponentialRetry, RetryClient

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


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

                # Success heuristics:
                # - 2xx status
                # - redirected to home or panel (not still on signin page)
                # - "خروج" (logout) link appears in navbar when logged in
                is_still_on_signin = (
                    "ورود به سایت" in text or "capcode" in text
                )
                is_logged_in = "خروج" in text or "/signout" in text or "/panel" in text

                if status < 400 and (is_logged_in or not is_still_on_signin):
                    logger.info("✅ MyMoviz login succeeded!")
                    return True

                logger.warning(
                    "❌ MyMoviz login failed (status={}, on_signin={}, logged_in={}). "
                    "Likely CAPTCHA blocked automated login. "
                    "Set MYMOVIZ_COOKIE env var manually.",
                    status, is_still_on_signin, is_logged_in,
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

        Raises:
            aiohttp.ClientError: if all retries are exhausted.
            asyncio.TimeoutError: on persistent timeouts.
        """
        await self.init()
        await self._respect_rate_limit()
        assert self._retry_client is not None

        logger.debug("GET {}", url)
        async with self._retry_client.get(url, **kwargs) as resp:
            if resp.status >= 400:
                logger.warning("HTTP {} for {}", resp.status, url)
                resp.raise_for_status()
            text = await resp.text(errors="replace")
            logger.debug("Response {} bytes from {}", len(text), url)
            return text

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
