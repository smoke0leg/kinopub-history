"""Встраивание kinopub-history в своё приложение.

1. Свой транспорт (прокси, requests, браузерные cookie) — fetch=.
2. Архив в памяти — без файлов на диске.
3. Свой формат выгрузки — @exporter.
4. Свои данные из Export — обычные dataclass'ы.
"""
from __future__ import annotations

import os
import sys

from kinopub_history import Archive, Client, Grabber, assemble, export, exporter


def requests_fetch(session):
    """Транспорт поверх requests.Session (например, с прокси или cookie из браузера)."""
    from kinopub_history import NotFound

    def fetch(method, url, data):
        r = session.request(method, url, data=data, timeout=30)
        if r.status_code == 404:
            raise NotFound(url)
        r.raise_for_status()
        return r.url, r.text
    return fetch


@exporter("todo", "Markdown-список: что досмотреть", ("series",))
def todo(data, out, what):
    for s in data.series:
        if s.last_seen and s.episodes_watched < s.episodes_total:
            out.write(f"- [ ] {s.title}: остановились на S{s.last_seen.season:02d}E{s.last_seen.episode:02d} "
                      f"({s.last_seen.watched_on}), не смотрели {s.episodes_total - s.episodes_watched}\n")
    return []


def main() -> None:
    client = Client(cookies="cookies.txt")  # или Client(fetch=requests_fetch(my_session))
    archive = Archive()  # в памяти; DirArchive("archive/") — на диске, с переразбором без сети
    grabber = Grabber(client, archive, log=lambda m: print(m, file=sys.stderr),
                      sections=("history", "watchlist", "series"), all_seasons=False)
    grabber.run(os.environ.get("KINOPUB_LOGIN"), os.environ.get("KINOPUB_PASSWORD"),
                code=lambda: input("код из письма: "))
    data = assemble(archive)

    print(f"фильмов {len(data.history)}, серий {len(data.episodes)}, сериалов {len(data.series)}")
    export(data, "todo", sys.stdout, "series")


if __name__ == "__main__":
    main()
