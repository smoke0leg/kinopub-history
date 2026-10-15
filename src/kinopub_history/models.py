"""Модели данных выгрузки. Всё — dataclass'ы с `to_dict()`; поля, которых сайт не дал, — None.

Ничего не выдумываем: если значение не нашлось на странице, его нет и в выгрузке.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 1


class _Dict:
    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)  # type: ignore[call-overload]


@dataclass
class Title(_Dict):
    """Карточка тайтла: одинакова в истории, «Я смотрю», закладках и профиле."""
    kp_id: int  # id тайтла на kinopub (/item/view/<kp_id>)
    title: Optional[str] = None  # русское название
    original_title: Optional[str] = None
    year: Optional[int] = None
    director: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    imdb_id: Optional[str] = None  # tt0108358 (на сайте без ведущих нулей — нормализуем до 7 знаков)
    imdb_rating: Optional[float] = None
    kinopoisk_id: Optional[int] = None
    kinopoisk_rating: Optional[float] = None
    kinopub_thumbs: Optional[str] = None  # число у 👍 как есть: в истории оценка 0–10, в профиле целое
    poster: Optional[str] = None


@dataclass
class HistoryEntry(Title):
    """Запись истории. `media_id` — id медиа (фильма или серии), а не просмотра: сайт хранит одну
    запись на медиа с днём ПОСЛЕДНЕГО просмотра, пересмотры не помнит."""
    media_id: int = 0
    watched_on: Optional[str] = None  # YYYY-MM-DD; время сайт не показывает
    season: Optional[int] = None  # есть только у серий
    episode: Optional[int] = None
    types: list[str] = field(default_factory=list)  # вкладки-типы, где нашлась запись: movie, serial, tvshow…

    @property
    def is_episode(self) -> bool:
        return self.season is not None


@dataclass
class WatchlistEntry(Title):
    """«Я смотрю»: сериал и сколько серий ещё не смотрели (красная цифра на постере)."""
    unwatched: int = 0
    kinopub_views: Optional[str] = None  # «7.9K» у ✔ — как на сайте


@dataclass
class Bookmark(Title):
    folder_id: int = 0
    folder: Optional[str] = None


@dataclass
class Profile(_Dict):
    """Вкладки профиля /users/<логин>. like/dislike — единственные явные оценки на kinopub."""
    like: list[Title] = field(default_factory=list)
    dislike: list[Title] = field(default_factory=list)
    watch: list[Title] = field(default_factory=list)  # «Сериалы»
    now: list[Title] = field(default_factory=list)  # «Сейчас смотрю»


@dataclass
class Episode(_Dict):
    season: int
    episode: int
    media_id: int
    title: Optional[str] = None
    watched: bool = False  # галочка «просмотрено»
    progress: Optional[int] = None  # «Просмотрено N%»
    current: bool = False  # серия помечена active на странице по умолчанию


@dataclass
class EpisodeRef(_Dict):
    season: int
    episode: int
    title: Optional[str] = None
    watched_on: Optional[str] = None


@dataclass
class Series(_Dict):
    """Сериал целиком: ID со страницы, серии всех скачанных сезонов, где остановились.

    `last_seen` — последняя серия по ИСТОРИИ: это и есть «где остановились».
    `page_active` — серия, на которой сайт открывает страницу; НЕ точка остановки (без отметки сайт
    показывает S1E1). `furthest_watched` — самая дальняя галочка; тоже не точка остановки."""
    kp_id: int
    title: Optional[str] = None
    original_title: Optional[str] = None
    imdb_id: Optional[str] = None
    kinopoisk_id: Optional[int] = None
    seasons: list[int] = field(default_factory=list)
    seasons_loaded: list[int] = field(default_factory=list)
    seasons_complete: list[int] = field(default_factory=list)
    episodes_total: int = 0
    episodes_watched: int = 0
    last_seen: Optional[EpisodeRef] = None
    first_seen_on: Optional[str] = None
    episodes_in_history: int = 0
    page_active: Optional[Episode] = None
    furthest_watched: Optional[EpisodeRef] = None
    missing: Optional[str] = None  # «HTTP 404» — тайтл сняли с сайта
    episodes: list[Episode] = field(default_factory=list)


@dataclass
class Export(_Dict):
    """Всё, что удалось выгрузить. Разделы, которые не качали, — пустые списки / None."""
    history: list[HistoryEntry] = field(default_factory=list)  # тайтлы: фильмы, докфильмы, концерты
    episodes: list[HistoryEntry] = field(default_factory=list)  # серии
    watchlist: list[WatchlistEntry] = field(default_factory=list)
    bookmarks: list[Bookmark] = field(default_factory=list)
    profile: Optional[Profile] = None
    series: list[Series] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    source: Optional[str] = None  # адрес сайта
    exported_at: Optional[str] = None  # ISO 8601, UTC
