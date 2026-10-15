"""kinopub-history — выгрузить свою историю kinopub в удобном формате.

  kinopub-history grab   [--archive DIR] [--only history,watchlist,…] [--current-season-only] [--resume]
  kinopub-history export [--archive DIR] --format FMT [--what РАЗДЕЛ] [-o ФАЙЛ]
  kinopub-history run    — grab + export одной командой
  kinopub-history formats

Логин и пароль: --login/--password или KINOPUB_LOGIN / KINOPUB_PASSWORD. Код из письма спрашивается в
терминале (или --code). Сессия хранится в cookie-файле, повторный запуск входит без пароля и кода.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from . import __version__
from .archive import DirArchive
from .client import DEFAULT_BASE, Client, KinopubError
from .export import FORMATS, WHAT, export
from .grab import Grabber, assemble, serials

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "kinopub-history"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _grab(args: argparse.Namespace) -> None:
    client = Client(base=args.base, cookies=args.cookies, pause=args.pause)
    archive = DirArchive(args.archive)
    only = args.only.split(",") if args.only else Grabber.ALL
    g = Grabber(client, archive, log=_log, sections=only, all_seasons=not args.current_season_only)
    login = args.login or os.environ.get("KINOPUB_LOGIN")
    password = args.password or os.environ.get("KINOPUB_PASSWORD")
    if login and not password and sys.stdin.isatty():
        password = getpass.getpass("пароль kinopub: ")

    def code() -> str:
        if args.code:
            return args.code
        if not sys.stdin.isatty():
            return ""
        return input("код из письма «Проверочный код для кинопаба»: ")

    if args.resume:  # докачать сериалы после обрыва, разделы не трогаем
        client.login(login, password, code)
        g.series(serials(assemble(archive)), resume=True)
    else:
        g.run(login, password, code)
    _log(f"архив страниц: {archive.path}")


def _export(args: argparse.Namespace) -> None:
    data = assemble(DirArchive(args.archive), source=args.base)
    out = open(args.output, "w", encoding="utf-8", newline="") if args.output and args.output != "-" else sys.stdout
    try:
        for note in export(data, args.format, out, args.what):
            _log(note)
    finally:
        if out is not sys.stdout:
            out.close()
    if args.output and args.output != "-":
        _log(f"{args.format} ({args.what}) → {args.output}")


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(prog="kinopub-history", description="Выгрузка своей истории kinopub.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--archive", default=str(CONFIG / "archive"), help="каталог сырых страниц (по умолчанию %(default)s)")
    p.add_argument("--base", default=os.environ.get("KINOPUB_BASE", DEFAULT_BASE), help="адрес сайта (%(default)s)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def grab_args(s: argparse.ArgumentParser) -> None:
        s.add_argument("--login")
        s.add_argument("--password")
        s.add_argument("--code", help="код из письма, если сайт попросит")
        s.add_argument("--cookies", default=str(CONFIG / "cookies.txt"), help="файл сессии (%(default)s)")
        s.add_argument("--pause", type=float, default=1.5, help="секунд между запросами (%(default)s)")
        s.add_argument("--only", help="разделы через запятую: " + ",".join(Grabber.ALL))
        s.add_argument("--current-season-only", action="store_true",
                       help="у сериалов только страница по умолчанию (быстрее, без галочек прочих сезонов)")
        s.add_argument("--resume", action="store_true", help="докачать сериалы после обрыва")

    def export_args(s: argparse.ArgumentParser) -> None:
        s.add_argument("-f", "--format", default="json", choices=sorted(FORMATS))
        s.add_argument("-w", "--what", default="all", help="раздел: all, " + ", ".join(WHAT) + " (по умолчанию all)")
        s.add_argument("-o", "--output", help="файл (по умолчанию stdout)")

    grab_args(sub.add_parser("grab", help="скачать страницы аккаунта в архив"))
    export_args(sub.add_parser("export", help="собрать выгрузку из архива (без сети)"))
    r = sub.add_parser("run", help="grab + export")
    grab_args(r)
    export_args(r)
    sub.add_parser("formats", help="список форматов")
    args = p.parse_args(argv)

    if args.cmd == "formats":
        for f in FORMATS.values():
            print(f"{f.name:12} {f.description}\n{'':12} разделы: {', '.join(f.whats)}")
        return 0
    if getattr(args, "what", None) == "all" and args.format in FORMATS and "all" not in FORMATS[args.format].whats:
        args.what = "history"
    try:
        if args.cmd in ("grab", "run"):
            _grab(args)
        if args.cmd in ("export", "run"):
            _export(args)
    except (KinopubError, ValueError) as e:
        _log(f"ошибка: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
