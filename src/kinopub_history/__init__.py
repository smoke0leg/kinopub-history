"""kinopub-history — выгрузка своей истории просмотров kinopub (неофициально).

SDK:
    from kinopub_history import Client, Grabber, DirArchive, assemble, export

    client = Client(cookies="cookies.txt")
    archive = DirArchive("archive/")
    Grabber(client, archive, log=print).run("login", "password", code=lambda: input("код: "))
    data = assemble(archive)                    # Export: history, episodes, watchlist, bookmarks, profile, series
    with open("history.csv", "w") as f:
        export(data, "csv", f, what="history")

Разбор без сети — `kinopub_history.parse` (HTML → модели).
"""
from .archive import Archive, DirArchive
from .client import Client, CodeRequired, KinopubError, LoginError, NotFound
from .export import FORMATS, export, exporter
from .grab import Grabber, assemble, serials
from .models import (Bookmark, Episode, EpisodeRef, Export, HistoryEntry, Profile, Series, Title,
                     WatchlistEntry)

__version__ = "0.1.0"

__all__ = [
    "Archive", "DirArchive", "Client", "CodeRequired", "KinopubError", "LoginError", "NotFound",
    "FORMATS", "export", "exporter", "Grabber", "assemble", "serials",
    "Bookmark", "Episode", "EpisodeRef", "Export", "HistoryEntry", "Profile", "Series", "Title", "WatchlistEntry",
]
