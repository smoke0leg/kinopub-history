"""HTTP-клиент kinopub: вход формой сайта, cookie, вежливая пауза между запросами.

Транспорт подменяемый: `Client(fetch=...)` — любая функция `(method, url, data) -> (final_url, html)`.
Так клиент встраивается туда, где свой HTTP (прокси, aiohttp в потоке, браузерная сессия, тесты).
"""
from __future__ import annotations

import http.cookiejar
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from . import parse

DEFAULT_BASE = "https://kino.watch"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

Fetch = Callable[[str, str, Optional[dict]], "tuple[str, str]"]
CodeProvider = Callable[[], str]


class KinopubError(Exception):
    pass


class LoginError(KinopubError):
    """Вход не удался: неверный логин/пароль или форма изменилась."""


class CodeRequired(LoginError):
    """Сайт просит код из письма («Проверочный код для кинопаба») — вход с нового места."""


class NotFound(KinopubError):
    """404: тайтл сняли с сайта."""

    def __init__(self, url: str):
        super().__init__(f"HTTP 404: {url}")
        self.url = url


class Client:
    """Сессия на сайте kinopub.

    >>> c = Client(cookies="~/.config/kinopub-history/cookies.txt")
    >>> c.login("user", "secret", code=lambda: input("код из письма: "))
    >>> html = c.get("/history")

    cookies — файл LWP-cookie (создаётся с правами 0600); с ним повторный вход не просит ни пароль, ни код.
    pause — секунд между запросами (по умолчанию 1,5: сайт чужой, нагрузку держим человеческой).
    """

    def __init__(self, base: str = DEFAULT_BASE, cookies: "str | Path | None" = None,
                 pause: float = 1.5, fetch: Optional[Fetch] = None, timeout: float = 30):
        self.base = base.rstrip("/")
        self.pause = pause
        self.timeout = timeout
        self._last = 0.0
        self._cookie_path = Path(os.path.expanduser(str(cookies))) if cookies else None
        self.jar = http.cookiejar.LWPCookieJar(str(self._cookie_path) if self._cookie_path else None)
        if self._cookie_path and self._cookie_path.exists():
            self.jar.load(ignore_discard=True, ignore_expires=True)
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self._opener.addheaders = [("User-Agent", UA), ("Accept-Language", "ru-RU,ru;q=0.9")]
        self._fetch = fetch or self._urllib_fetch

    def url(self, path: str) -> str:
        return urllib.parse.urljoin(self.base + "/", path.lstrip("/")) if not path.startswith("http") else path

    def _urllib_fetch(self, method: str, url: str, data: Optional[dict]) -> "tuple[str, str]":
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers={"Referer": url} if body else {})
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                return r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFound(url) from None
            raise KinopubError(f"HTTP {e.code}: {url}") from None

    def _polite(self) -> None:
        wait = self.pause - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get(self, path: str) -> str:
        return self.get_url(path)[1]

    def get_url(self, path: str) -> "tuple[str, str]":
        self._polite()
        return self._fetch("GET", self.url(path), None)

    def post(self, path: str, data: dict) -> "tuple[str, str]":
        self._polite()
        return self._fetch("POST", self.url(path), data)

    def save_cookies(self) -> None:
        if self._cookie_path:
            self._cookie_path.parent.mkdir(parents=True, exist_ok=True)
            self.jar.save(ignore_discard=True, ignore_expires=True)
            self._cookie_path.chmod(0o600)

    def login(self, login: Optional[str] = None, password: Optional[str] = None,
              code: "CodeProvider | str | None" = None) -> str:
        """Вход формой /user/login (Yii, CSRF). Если cookie ещё живы — пароль не нужен.
        code — строка или функция без аргументов; спрашивается, только если сайт попросил код.
        Возвращает HTML страницы после входа (по ней ищутся разделы)."""
        url, page = self.get_url("/user/login")
        if "/user/login" not in url:
            return page  # сессия из cookie жива
        if not (login and password):
            raise LoginError("нужен логин и пароль (сохранённая сессия истекла или её нет)")
        token = parse.csrf(page)
        if not token:
            raise LoginError("на странице входа нет _csrf — вёрстка изменилась")
        url, page = self.post("/user/login", {
            "_csrf": token, "login-form[login]": login, "login-form[password]": password,
            "login-form[rememberMe]": "1"})
        if "login-form[formcode]" in page:
            value = code() if callable(code) else code
            if not value:
                raise CodeRequired("сайт просит код из письма «Проверочный код для кинопаба»")
            url, page = self.post("/user/login", {"_csrf": parse.csrf(page) or token,
                                                  "login-form[formcode]": value.strip()})
        if "/user/login" in url or 'id="login-form"' in page:
            raise LoginError("вход не удался: " + (parse.login_error(page) or "форма вернулась"))
        self.save_cookies()
        return page
