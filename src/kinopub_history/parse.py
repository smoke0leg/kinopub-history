"""Разбор страниц kinopub. Чистые функции: HTML-строка на входе, модели на выходе, сети нет.

Вёрстка сайта меняется — каждая функция описывает, на что опирается, а тесты держат
синтетические страницы той же структуры (tests/fixtures).
"""
from __future__ import annotations

import html as _html
import re
import urllib.parse
from typing import Optional

from .models import Bookmark, Episode, HistoryEntry, Profile, Title, WatchlistEntry

ITEM = re.compile(r'href="(?:https?://[^"/]+)?/item/view/(\d+)(?:/s(\d+)e(\d+))?[^"]*"')
# Название и исходное название — ТЕКСТ ссылки (в профиле у ссылки нет атрибута title).
# Ссылки на жанры стоят в такой же <div class="item-author">, их пропускаем.
_NAME = re.compile(r'<div class="item-(?:title|author)[^"]*">\s*<a (?![^>]*genre=)[^>]*>(.*?)</a>', re.S)
# Оценка — число сразу за ссылкой; между ними бывает значок <i ...></i>
_RATED = r'"[^>]*>(?:\s*<i[^>]*>\s*</i>)?\s*([\d.]+)?'
_MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)}
_DAY = re.compile(r"<h4[^>]*>\s*(\d{1,2})\s+([A-Za-z]+)\s*<small>\s*(\d{4})\s*</small>\s*</h4>")
_CARD = re.compile(r'<div class="[^"]*" id="media-(\d+)">')
_EP = re.compile(r'<div class="item episode-thumbnail( active)?"\s+id="media-(\d+)"\s+'
                 r'data-snumber="(\d+)"\s+data-vnumber="(\d+)"')


def _text(fragment: str) -> str:
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _imdb(num: str) -> str:
    return f"tt{int(num):07d}"


def card(c: str, kp_id: int) -> Title:
    """Общие поля карточки тайтла из куска HTML."""
    names = [n for n in (_text(t) for t in _NAME.findall(c)) if n]
    year = re.search(r'text-muted">\s*(\d{4}),', c)
    director = re.search(r"реж\.\s*([^<]+)</span>", c)
    kp = re.search(r"kinopoisk\.ru/film/(\d+)" + _RATED, c)
    imdb = re.search(r"imdb\.com/title/tt(\d+)" + _RATED, c)
    thumbs = re.search(r'fa-thumbs-up"></i>\s*([\d.]+)', c)
    poster = re.search(r'src="(https?://[^"]+/poster/item/[^"]+)"', c)
    return Title(
        kp_id=kp_id,
        title=names[0] if names else None,
        original_title=names[1] if len(names) > 1 else None,
        year=int(year.group(1)) if year else None,
        director=" ".join(director.group(1).split()) if director else None,
        genres=[g.strip() for g in re.findall(r'genre=\d+"?>([^<]+)</a>', c)],
        imdb_id=_imdb(imdb.group(1)) if imdb else None,
        imdb_rating=float(imdb.group(2)) if imdb and imdb.group(2) else None,
        kinopoisk_id=int(kp.group(1)) if kp else None,
        kinopoisk_rating=float(kp.group(2)) if kp and kp.group(2) else None,
        kinopub_thumbs=thumbs.group(1) if thumbs else None,
        poster=poster.group(1) if poster else None,
    )


def cards(page: str) -> list[Title]:
    """Карточки страницы любой вёрстки (закладки, профиль). Одна карточка даёт несколько ссылок подряд
    (постер, название) — кусок от первой ссылки тайтла до первой ссылки следующего. Повторы по kp_id убираем."""
    starts: list[re.Match[str]] = []
    for m in ITEM.finditer(page):
        if not starts or starts[-1].group(1) != m.group(1):
            starts.append(m)
    out, seen = [], set()
    for k, m in enumerate(starts):
        end = starts[k + 1].start() if k + 1 < len(starts) else min(len(page), m.start() + 4000)
        kp_id = int(m.group(1))
        if kp_id not in seen:
            seen.add(kp_id)
            out.append(card(page[m.start():end], kp_id))
    return out


def history(page: str, tab: Optional[str] = None) -> list[HistoryEntry]:
    """Страница истории: заголовок дня <h4>15 October <small>2026</small></h4>, за ним карточки
    <div id="media-N"> этого дня. У серий в ссылке /sNeM. `tab` — вкладка-тип, попадает в `types`."""
    marks = sorted([(m.start(), True, m) for m in _DAY.finditer(page)] +
                   [(m.start(), False, m) for m in _CARD.finditer(page)], key=lambda x: x[0])
    out, day = [], None
    for k, (pos, is_day, m) in enumerate(marks):
        if is_day:
            mon = _MONTHS.get(m.group(2))
            day = f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}" if mon else None
            continue
        end = marks[k + 1][0] if k + 1 < len(marks) else len(page)
        c = page[pos:end]
        item = ITEM.search(c)
        if not item:
            continue
        t = card(c, int(item.group(1)))
        out.append(HistoryEntry(
            **vars(t), media_id=int(m.group(1)), watched_on=day,
            season=int(item.group(2)) if item.group(2) else None,
            episode=int(item.group(3)) if item.group(3) else None,
            types=[tab] if tab and tab != "episodes" else [],
        ))
    return out


def history_tabs(page: str) -> dict[str, str]:
    """Вкладки истории из её меню: {вкладка: путь}. Сайт отдаёт /history/index/<логин>/<вкладка>:
    episodes («Все эпизоды»), movie, serial, tvshow, docuserial, documovie, concert, 3d."""
    return {tab: path for path, tab in re.findall(r'href="(/history/index/[^/"]+/(\w+))"', page)}


def watchlist(page: str) -> list[WatchlistEntry]:
    """«Я смотрю» (/watchlist/<логин>): постер с красной цифрой — сколько серий ещё не смотрели."""
    out = []
    for c in re.split(r'<div class="item-poster">', page)[1:]:
        item = ITEM.search(c)
        if not item:
            continue
        unwatched = re.search(r'<span class="label" style="background-color: red">\s*(\d+)', c)
        views = re.search(r'fa-check-circle"></i>\s*([\d.]+K?)', c)
        out.append(WatchlistEntry(**vars(card(c, int(item.group(1)))),
                                  unwatched=int(unwatched.group(1)) if unwatched else 0,
                                  kinopub_views=views.group(1) if views else None))
    return out


def profile(page: str) -> Profile:
    """Профиль /users/<логин>: вкладки-панели прямо в странице (like, dislike, watch, now, comment)."""
    panes = re.split(r'<div class="tab-pane[^"]*" id="(\w+)">', page)
    got = {name: cards(body) for name, body in zip(panes[1::2], panes[2::2])}
    return Profile(like=got.get("like", []), dislike=got.get("dislike", []),
                   watch=got.get("watch", []), now=got.get("now", []))


def folders(page: str) -> dict[int, str]:
    """Индекс закладок /favorites: папки /favorites/view?id=N → название. Тайтлы — только внутри папок."""
    out: dict[int, str] = {}
    for m in re.finditer(r'href="/favorites/view\?id=(\d+)"[^>]*>(.*?)</a>', page, re.S):
        name = _text(m.group(2))
        if name and int(m.group(1)) not in out:
            out[int(m.group(1))] = name
    return out


def bookmarks(page: str, folder_id: int, folder: Optional[str]) -> list[Bookmark]:
    return [Bookmark(**vars(t), folder_id=folder_id, folder=folder) for t in cards(page)]


def series_page(page: str) -> dict:
    """Страница сериала /item/view/<id>[/sNe1]: сезоны (ссылки iv-spill), серии показанного сезона
    с галочкой «просмотрено» (checked у marktime-checkbox) и полоской «Просмотрено N%», серия active,
    название и ID (<title>RU / Original</title>, IMDb, Кинопоиск)."""
    marks = list(_EP.finditer(page))
    eps = []
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else m.end() + 4000
        c = page[m.start():end]
        prog = re.search(r'title="Просмотрено (\d+)%"', c)
        name = re.search(r'<div class="item-title[^"]*">\s*<a [^>]*>([^<]*)</a>', c)
        eps.append(Episode(
            season=int(m.group(3)), episode=int(m.group(4)), media_id=int(m.group(2)),
            title=_html.unescape(name.group(1)).strip() if name else None,
            watched=bool(re.search(r'class="marktime-checkbox"[^>]*\bchecked\b', c)),
            progress=int(prog.group(1)) if prog else None,
            current=bool(m.group(1)),
        ))
    seasons = {int(x) for x in re.findall(r'class="iv-spill[^"]*" href="/item/view/\d+/s(\d+)e1"', page)}
    if eps:
        seasons.add(eps[0].season)
    t = re.search(r"<title>([^<]*)</title>", page)
    ru, _, orig = _html.unescape(t.group(1)).partition(" / ") if t else ("", "", "")
    imdb = re.search(r"imdb\.com/title/tt(\d+)", page)
    kp = re.search(r"kinopoisk\.ru/film/(\d+)", page)
    return {
        "title": ru.strip() or None,
        "original_title": orig.strip() or None,
        "imdb_id": _imdb(imdb.group(1)) if imdb else None,
        "kinopoisk_id": int(kp.group(1)) if kp else None,
        "seasons": sorted(seasons),
        "season_shown": eps[0].season if eps else None,
        "episodes": eps,
    }


SECTIONS = {
    "history": (r"histor", r"истори"),
    "watchlist": (r"watching|watchlist", r"буду смотреть|я смотрю"),
    "bookmarks": (r"favorites|bookmark", r"закладк"),
}


def sections(page: str, base: str) -> dict[str, str]:
    """Разделы из меню: {history|watchlist|bookmarks: путь}. Адреса не зашиты — сайт уже переезжал."""
    found: dict[str, str] = {}
    for m in re.finditer(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', page, flags=re.S):
        href, text = _html.unescape(m.group(1)), _text(m.group(2))
        path = urllib.parse.urlparse(urllib.parse.urljoin(base, href)).path
        if not path.startswith("/") or "item/view" in path:
            continue
        for name, (url_re, text_re) in SECTIONS.items():
            if name not in found and (re.search(url_re, path, re.I) or re.search(text_re, text, re.I)):
                found[name] = path
    return found


def login_name(page: str) -> Optional[str]:
    """Логин из ссылки на профиль /users/<логин> в меню."""
    m = re.search(r'href="/users/([^/"]+)"', page)
    return m.group(1) if m else None


def csrf(page: str) -> Optional[str]:
    m = re.search(r'name="_csrf" value="([^"]+)"', page)
    return m.group(1) if m else None


def login_error(page: str) -> Optional[str]:
    m = re.search(r'class="help-block[^"]*">([^<]+)<', page)
    return m.group(1).strip() if m else None
