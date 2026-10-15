"""Форматы выгрузки. Реестр: имя → функция `(data: Export, out: TextIO, what: str) -> list[str]`
(возвращает замечания: что пропущено и почему).

Свой формат:
    from kinopub_history.export import exporter
    @exporter("mine", "мой формат")
    def mine(data, out, what):
        ...
        return []
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

from .models import Export

ExportFn = Callable[[Export, TextIO, str], "list[str]"]
WHAT = ("history", "episodes", "watchlist", "bookmarks", "series", "likes", "dislikes")


@dataclass
class Format:
    name: str
    description: str
    fn: ExportFn
    whats: tuple[str, ...] = WHAT  # какие разделы формат умеет; "all" — весь документ


FORMATS: dict[str, Format] = {}


def exporter(name: str, description: str, whats: tuple[str, ...] = WHAT) -> Callable[[ExportFn], ExportFn]:
    def wrap(fn: ExportFn) -> ExportFn:
        FORMATS[name] = Format(name, description, fn, whats)
        return fn
    return wrap


def export(data: Export, fmt: str, out: TextIO, what: str = "history") -> list[str]:
    """Записать `what` из `data` в формате `fmt`. Возвращает замечания (пропущенное)."""
    if fmt not in FORMATS:
        raise ValueError(f"нет формата {fmt!r}; есть: {', '.join(FORMATS)}")
    f = FORMATS[fmt]
    if what not in f.whats:
        raise ValueError(f"формат {fmt} не умеет {what!r}; умеет: {', '.join(f.whats)}")
    return f.fn(data, out, what)


def records(data: Export, what: str) -> list[dict[str, Any]]:
    """Раздел как список словарей. likes/dislikes — из профиля."""
    if what in ("likes", "dislikes"):
        items = getattr(data.profile, what[:-1], []) if data.profile else []
    else:
        items = getattr(data, what)
    return [i.to_dict() for i in items]


# --- JSON ---------------------------------------------------------------------------------------

@exporter("json", "весь документ или раздел, JSON (схема: schema/export.schema.json)", ("all",) + WHAT)
def _json(data: Export, out: TextIO, what: str) -> list[str]:
    doc = data.to_dict() if what == "all" else records(data, what)
    json.dump(doc, out, ensure_ascii=False, indent=1)
    out.write("\n")
    return []


@exporter("jsonl", "по записи на строку, с полем kind", ("all",) + WHAT)
def _jsonl(data: Export, out: TextIO, what: str) -> list[str]:
    for w in (WHAT if what == "all" else (what,)):
        for r in records(data, w):
            out.write(json.dumps({"kind": w, **r}, ensure_ascii=False) + "\n")
    return []


# --- CSV ----------------------------------------------------------------------------------------

def _flat(r: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in r.items():
        if k == "episodes" and isinstance(v, list):  # серии сериала — отдельной таблицей (what=episodes)
            continue
        if isinstance(v, dict):
            out.update(_flat(v, f"{prefix}{k}_"))
        elif isinstance(v, list):
            out[prefix + k] = "; ".join(str(x) for x in v)
        else:
            out[prefix + k] = v
    return out


@exporter("csv", "таблица одного раздела (UTF-8, заголовок; списки через «; »)")
def _csv(data: Export, out: TextIO, what: str) -> list[str]:
    rows = [_flat(r) for r in records(data, what)]
    cols: list[str] = []
    for r in rows:
        cols += [c for c in r if c not in cols]
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return []


# --- Letterboxd ---------------------------------------------------------------------------------

@exporter("letterboxd", "CSV для импорта в Letterboxd (фильмы: дневник; закладки/«Я смотрю»: watchlist)",
          ("history", "bookmarks", "likes"))
def _letterboxd(data: Export, out: TextIO, what: str) -> list[str]:
    """Колонки импорта Letterboxd: Title, Year, imdbID, WatchedDate (только у истории).
    Letterboxd — про фильмы: сериалы и записи без года и IMDb он не сопоставит, их пропускаем с замечанием."""
    items = {"history": data.history, "bookmarks": data.bookmarks,
             "likes": data.profile.like if data.profile else []}[what]
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["Title", "Year", "imdbID", "WatchedDate"] if what == "history" else ["Title", "Year", "imdbID"])
    skipped = []
    for t in items:
        if not (t.imdb_id or (t.year and (t.original_title or t.title))):
            skipped.append(t.title or str(t.kp_id))
            continue
        row = [t.original_title or t.title, t.year or "", t.imdb_id or ""]
        w.writerow(row + [getattr(t, "watched_on", None) or ""] if what == "history" else row)
    return ([f"letterboxd.csv: {len(skipped)} без IMDb и года не попали: {', '.join(skipped[:10])}"]
            if skipped else [])


# --- Trakt --------------------------------------------------------------------------------------

@exporter("trakt", "JSON-тело для POST https://api.trakt.tv/sync/history (фильмы + серии по IMDb)",
          ("all", "history", "episodes"))
def _trakt(data: Export, out: TextIO, what: str) -> list[str]:
    """Trakt сопоставляет по ids.imdb. Время просмотра сайт не показывает — ставим полдень UTC дня
    просмотра. У серий в истории IMDb нет — берём IMDb сериала со страницы сериала (series)."""
    notes, body = [], {"movies": [], "shows": []}
    at = lambda day: f"{day}T12:00:00.000Z"  # noqa: E731
    if what in ("all", "history"):
        miss = [h for h in data.history if not h.imdb_id or not h.watched_on]
        body["movies"] = [{"watched_at": at(h.watched_on), "title": h.original_title or h.title, "year": h.year,
                           "ids": {"imdb": h.imdb_id}} for h in data.history if h.imdb_id and h.watched_on]
        if miss:
            notes.append(f"trakt.json: {len(miss)} фильмов без IMDb не попали (Trakt находит фильмы по IMDb)")
    if what in ("all", "episodes"):
        show_ids = {s.kp_id: s for s in data.series if s.imdb_id}
        shows: dict[int, dict] = {}
        lost = set()
        for e in data.episodes:
            s = show_ids.get(e.kp_id)
            if not s or not e.watched_on:
                lost.add(e.title or str(e.kp_id))
                continue
            show = shows.setdefault(e.kp_id, {"title": s.original_title or s.title, "ids": {"imdb": s.imdb_id},
                                              "seasons": {}})
            show["seasons"].setdefault(e.season, []).append({"number": e.episode, "watched_at": at(e.watched_on)})
        body["shows"] = [{**v, "seasons": [{"number": n, "episodes": sorted(eps, key=lambda x: x["number"])}
                                           for n, eps in sorted(v["seasons"].items())]} for v in shows.values()]
        if lost:
            notes.append(f"trakt.json: не попали серии {len(lost)} сериалов — у них не нашёлся IMDb "
                         "(сериал сняли с сайта или его страницу не скачивали)")
    json.dump(body, out, ensure_ascii=False, indent=1)
    out.write("\n")
    return notes


# --- Папка со всем сразу ------------------------------------------------------------------------

BUNDLE = (
    # файл, формат, раздел, что внутри (для README.txt)
    ("films.csv", "csv", "history", "фильмы, докфильмы, концерты: день просмотра, IMDb, Кинопоиск, жанры"),
    ("episodes.csv", "csv", "episodes", "просмотренные серии: сериал, сезон, серия, день"),
    ("series.csv", "csv", "series", "сериалы: где остановились (last_seen_*), сколько серий досмотрено"),
    ("watchlist.csv", "csv", "watchlist", "«Я смотрю»: сколько серий ещё не смотрели"),
    ("bookmarks.csv", "csv", "bookmarks", "закладки по папкам"),
    ("likes.csv", "csv", "likes", "«Понравились» из профиля"),
    ("letterboxd.csv", "letterboxd", "history", "импорт в Letterboxd: letterboxd.com/import"),
    ("trakt.json", "trakt", "all", "тело запроса для Trakt: POST /sync/history"),
    ("kinopub.json", "json", "all", "всё одним файлом (схема — schema/export.schema.json в репозитории)"),
)


def export_bundle(data: Export, folder: "str | os.PathLike[str]") -> list[str]:
    """Записать все разделы во всех основных форматах в папку + README.txt «что где».
    Возвращает замечания (что пропущено). Пустые разделы тоже пишутся — с одним заголовком."""
    out_dir = Path(folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    for name, fmt, what, _ in BUNDLE:
        # BOM — чтобы Excel узнал UTF-8 и не показал кириллицу кракозябрами; Letterboxd и JSON — без BOM
        with open(out_dir / name, "w", encoding="utf-8-sig" if fmt == "csv" else "utf-8", newline="") as f:
            notes += export(data, fmt, f, what)
    counts = {"фильмов": len(data.history), "серий": len(data.episodes), "сериалов": len(data.series),
              "в «Я смотрю»": len(data.watchlist), "закладок": len(data.bookmarks),
              "лайков": len(data.profile.like) if data.profile else 0}
    lines = ["Выгрузка истории kinopub (kinopub-history)", f"Сделана: {data.exported_at or ''}", "",
             ", ".join(f"{k}: {v}" for k, v in counts.items()), "", "Файлы:"]
    lines += [f"  {name:15} {about}" for name, _, _, about in BUNDLE]
    lines += ["", "CSV открываются в Excel, Numbers, Google Таблицах.",
              "Время просмотра сайт не хранит — только день; пересмотры не помнит (только последний).",
              "«Где остановились» в сериале — колонки last_seen_* в series.csv."]
    if notes:
        lines += ["", "Замечания:"] + [f"  {n}" for n in notes]
    (out_dir / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return notes
