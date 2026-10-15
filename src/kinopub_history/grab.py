"""Обход разделов и сборка выгрузки.

Два шага, разделённых архивом сырых страниц:
  Grabber(client, archive).run()  — качает страницы в архив (сеть);
  assemble(archive)               — собирает Export из архива (без сети, повторяемо).
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable, Iterable, Optional

from . import parse
from .archive import Archive
from .client import Client, NotFound
from .models import Bookmark, Episode, EpisodeRef, Export, HistoryEntry, Series, Title

MAX_PAGES = 1000
SERIAL_TYPES = {"serial", "docuserial", "tvshow"}
Log = Callable[[str], None]
# progress(event, **info) — для интерфейса: «page» (stage, section, n), «stage_done» (stage, pages),
# «series» (i, total, title, missing), «warning» (text). log — подробный текстовый журнал.
Progress = Callable[..., None]


class Grabber:
    """Качает разделы аккаунта в архив.

    sections: какие разделы брать (по умолчанию все): history, watchlist, bookmarks, profile, series.
    all_seasons: для сериалов качать страницы всех сезонов (галочки по каждой серии) — по странице
                 на сезон; False — только страница по умолчанию (быстро, без отметок прочих сезонов).
    """

    ALL = ("history", "watchlist", "bookmarks", "profile", "series")

    def __init__(self, client: Client, archive: Archive, log: Log = lambda s: None,
                 sections: Iterable[str] = ALL, all_seasons: bool = True,
                 progress: Progress = lambda event, **info: None):
        self.c, self.a, self.log, self.progress = client, archive, log, progress
        self.pages = 0  # страниц разделов за этап — для итога в progress
        self.want = set(sections)
        self.all_seasons = all_seasons
        self.home = ""

    # --- обход раздела: ?page=N, пока появляются новые записи -------------------------------
    def walk(self, name: str, path: str, parse_page: Callable[[str], list], key: Callable,
             stage: str = "") -> int:
        """Сайт игнорирует per-page и после последней страницы повторяет её — останавливаемся,
        когда новых записей нет."""
        self.a.clear(name + "-0")  # старые страницы этого раздела (другой нарезки) не смешиваем
        seen: set = set()
        sep = "&" if "?" in path else "?"
        for n in range(1, MAX_PAGES + 1):
            page = self.c.get(f"{path}{sep}page={n}&per-page=50")
            self.a.put(f"{name}-{n:04d}.html", page)
            items = parse_page(page)
            self.pages += 1
            self.progress("page", stage=stage or name, section=name, n=self.pages)
            if n == 1 and not items and parse.ITEM.search(page):
                warn = f"⚠ {name}: ссылки на тайтлы есть, а разбор пуст — вёрстка другая?"
                self.log(warn)
                self.progress("warning", text=warn)
            new = [k for k in map(key, items) if k not in seen]
            self.log(f"{name} стр. {n}: записей {len(items)}, новых {len(new)}")
            if not new:
                return len(seen)
            seen.update(new)
        return len(seen)

    def run(self, login: Optional[str] = None, password: Optional[str] = None, code=None) -> None:
        self.home = self.c.login(login, password, code)
        self.a.put("home.html", self.home)
        secs = parse.sections(self.home, self.c.base)
        user = parse.login_name(self.home)
        self.log(f"разделы: {secs}, логин: {user}")
        if "history" in self.want:
            self.pages = 0
            self.history()
            self.progress("stage_done", stage="history", pages=self.pages)
        self.pages = 0
        if "watchlist" in self.want and "watchlist" in secs:
            self.walk("watchlist", secs["watchlist"], parse.watchlist, lambda i: i.kp_id, "lists")
        if "bookmarks" in self.want:
            self.bookmarks(secs.get("bookmarks", "/favorites"))
        if "profile" in self.want and user:
            self.a.put("profile-0001.html", self.c.get(f"/users/{user}"))
            self.pages += 1
        if self.want & {"watchlist", "bookmarks", "profile"}:
            self.progress("stage_done", stage="lists", pages=self.pages)
        if "series" in self.want:
            self.series(serials(assemble(self.a)))

    def history(self) -> None:
        """«Все фильмы» (по умолчанию) + все вкладки из её меню. Вкладки «Сериалы»/«ТВ шоу»/«Докусериалы»
        посерийные и уходят глубже, чем «Все эпизоды», — поэтому берём все."""
        self.walk("history", "/history/index", parse.history, lambda i: i.media_id, "history")
        first = self.a.get("history-0001.html") or ""
        for tab, path in parse.history_tabs(first).items():
            self.walk(f"history-{tab}", path, lambda p, t=tab: parse.history(p, t), lambda i: i.media_id, "history")

    def bookmarks(self, path: str) -> None:
        index = self.c.get(path)
        self.a.put("bookmarks-0001.html", index)
        self.pages += 1
        found = parse.folders(index)
        self.log(f"закладки: папок {len(found)}")
        for fid in found:
            self.walk(f"folder-{fid}", f"/favorites/view?id={fid}", parse.cards, lambda i: i.kp_id, "lists")

    def series(self, items: Iterable[Title], resume: bool = False) -> None:
        """Страница сериала + (all_seasons) по странице на каждый остальной сезон /sNe1.
        404 (тайтл сняли) пишется в архив как series-<id>.missing и не роняет проход."""
        items = list(items)
        for i, t in enumerate(items, 1):
            if resume and (self.a.get(f"series-{t.kp_id}.html") or self.a.get(f"series-{t.kp_id}.missing")):
                continue
            try:
                page = self.c.get(f"/item/view/{t.kp_id}")
            except NotFound:
                self.a.put(f"series-{t.kp_id}.missing", "HTTP 404\n")
                self.log(f"[{i}/{len(items)}] {t.title}: страницы нет (404)")
                self.progress("series", i=i, total=len(items), title=t.title, missing=True)
                continue
            self.a.put(f"series-{t.kp_id}.html", page)
            info = parse.series_page(page)
            if self.all_seasons:
                for s in info["seasons"]:
                    if s == info["season_shown"]:
                        continue
                    try:
                        self.a.put(f"series-{t.kp_id}-s{s:02d}.html", self.c.get(f"/item/view/{t.kp_id}/s{s}e1"))
                    except NotFound:
                        self.log(f"   сезон {s}: 404")
            self.log(f"[{i}/{len(items)}] {t.title}: сезонов {len(info['seasons'])}")
            self.progress("series", i=i, total=len(items), title=t.title, missing=False)
        self.progress("stage_done", stage="series", pages=len(items))


def serials(data: Export) -> list[Title]:
    """Какие тайтлы — сериалы: «Я смотрю», профиль («Сериалы», «Сейчас смотрю»), всё из истории серий."""
    out: dict[int, Title] = {}
    for t in data.watchlist:
        out.setdefault(t.kp_id, t)
    if data.profile:
        for t in data.profile.watch + data.profile.now:
            out.setdefault(t.kp_id, t)
    for e in data.episodes:
        out.setdefault(e.kp_id, e)
    for h in data.history:
        if SERIAL_TYPES & set(h.types):
            out.setdefault(h.kp_id, h)
    return list(out.values())


def _newest(e: HistoryEntry) -> tuple:
    return (e.watched_on or "", e.season or 0, e.episode or 0)


def assemble(archive: Archive, source: Optional[str] = None) -> Export:
    """Всё из архива → Export. Единственное место сборки: и после обхода, и при переразборе."""
    titles: dict[int, HistoryEntry] = {}
    episodes: dict[int, HistoryEntry] = {}
    for section in ["history"] + archive.sections("history-"):
        tab = section.split("-", 1)[1] if "-" in section else None
        for page in archive.pages(section):
            for e in parse.history(page, tab):
                into = episodes if e.is_episode else titles  # делим по серии в ссылке, а не по вкладке
                rec = into.setdefault(e.media_id, e)
                for t in e.types:
                    if t not in rec.types:
                        rec.types.append(t)

    def uniq(section: str, fn: Callable[[str], list]) -> list:
        out, seen = [], set()
        for page in archive.pages(section):
            for i in fn(page):
                if i.kp_id not in seen:
                    seen.add(i.kp_id)
                    out.append(i)
        return out

    index = archive.get("bookmarks-0001.html")
    names = parse.folders(index) if index else {}
    marks: list[Bookmark] = []
    for section in archive.sections("folder-"):
        fid = int(section.split("-")[1])
        marks += uniq(section, lambda p, f=fid: parse.bookmarks(p, f, names.get(f)))
    prof = archive.get("profile-0001.html")

    data = Export(
        history=sorted(titles.values(), key=_newest, reverse=True),
        episodes=sorted(episodes.values(), key=_newest, reverse=True),
        watchlist=uniq("watchlist", parse.watchlist),
        bookmarks=marks,
        profile=parse.profile(prof) if prof else None,
        source=source,
        exported_at=_dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
    )
    data.series = _series(archive, data)
    return data


def _series(archive: Archive, data: Export) -> list[Series]:
    last: dict[int, HistoryEntry] = {}
    days: dict[int, list[str]] = {}
    for e in data.episodes:
        if e.kp_id not in last or _newest(e) > _newest(last[e.kp_id]):
            last[e.kp_id] = e
        if e.watched_on:
            days.setdefault(e.kp_id, []).append(e.watched_on)
    known = {t.kp_id: t for t in data.watchlist + data.episodes}

    out = []
    for name in archive.names():
        parts = name[:-len(".html")].split("-") if name.endswith(".html") else []
        if name.endswith(".missing"):
            kp_id = int(name.split("-")[1].split(".")[0])
            t = known.get(kp_id)
            out.append(Series(kp_id=kp_id, title=t.title if t else None,
                              original_title=t.original_title if t else None,
                              imdb_id=t.imdb_id if t else None, kinopoisk_id=t.kinopoisk_id if t else None,
                              missing=(archive.get(name) or "").strip()))
            continue
        if len(parts) != 2 or parts[0] != "series":
            continue
        kp_id = int(parts[1])
        first = parse.series_page(archive.get(name) or "")
        eps = {(e.season, e.episode): e for e in first["episodes"]}
        for other in archive.names():
            if other.startswith(f"series-{kp_id}-s") and other.endswith(".html"):
                for e in parse.series_page(archive.get(other) or "")["episodes"]:
                    # /sNe1 помечает active свою первую серию, а не точку — сбрасываем
                    eps.setdefault((e.season, e.episode), Episode(**{**vars(e), "current": False}))
        ordered = [eps[k] for k in sorted(eps)]
        watched = [e for e in ordered if e.watched]
        active = next((e for e in first["episodes"] if e.current), None)
        le = last.get(kp_id)
        out.append(Series(
            kp_id=kp_id, title=first["title"], original_title=first["original_title"],
            imdb_id=first["imdb_id"], kinopoisk_id=first["kinopoisk_id"],
            seasons=first["seasons"], seasons_loaded=sorted({e.season for e in ordered}),
            seasons_complete=[s for s in first["seasons"]
                              if (se := [e for e in ordered if e.season == s]) and all(e.watched for e in se)],
            episodes_total=len(ordered), episodes_watched=len(watched),
            last_seen=EpisodeRef(le.season or 0, le.episode or 0,
                                 (eps.get((le.season or 0, le.episode or 0)) or Episode(0, 0, 0)).title,
                                 le.watched_on) if le else None,
            first_seen_on=min(days[kp_id]) if kp_id in days else None,
            episodes_in_history=len(days.get(kp_id, [])),
            page_active=active,
            furthest_watched=EpisodeRef(watched[-1].season, watched[-1].episode, watched[-1].title) if watched else None,
            episodes=ordered,
        ))
    return sorted(out, key=lambda s: (s.last_seen.watched_on if s.last_seen and s.last_seen.watched_on else ""),
                  reverse=True)

