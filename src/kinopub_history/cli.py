"""kinopub-history — выгрузить свою историю kinopub.

  kinopub-history                  мастер: спросит логин, пароль, код из письма и сложит файлы в папку
  kinopub-history run    [-o ПАПКА] [--full]     скачать и выгрузить всё в папку без вопросов
  kinopub-history grab   [--full] [--resume]     только скачать страницы в архив
  kinopub-history export [-o ПАПКА]              все форматы в папку — из архива, без сети
  kinopub-history export -f ФОРМАТ [-w РАЗДЕЛ] [-o ФАЙЛ]   один формат
  kinopub-history formats

Логин и пароль: --login/--password или KINOPUB_LOGIN / KINOPUB_PASSWORD; код из письма спрашивается
в терминале (или --code). Сессия хранится в cookie-файле — повторный запуск входит без пароля и кода.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import getpass
import os
import sys
from pathlib import Path
from typing import Callable

from . import __version__
from .archive import DirArchive
from .client import DEFAULT_BASE, Client, CodeRequired, KinopubError, LoginError
from .export import FORMATS, WHAT, export, export_bundle
from .grab import Grabber, assemble, serials

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "kinopub-history"
FROZEN = getattr(sys, "frozen", False)  # собранная программа (PyInstaller), запущена двойным щелчком


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def default_folder() -> Path:
    return Path.cwd() / f"kinopub-export-{_dt.date.today().isoformat()}"


def _summary(data, folder: Path) -> str:
    return (f"фильмов {len(data.history)}, серий {len(data.episodes)}, сериалов {len(data.series)}, "
            f"«Я смотрю» {len(data.watchlist)}, закладок {len(data.bookmarks)} → {folder}")


# --- мастер ------------------------------------------------------------------------------------

def wizard(base: str = DEFAULT_BASE, ask: Callable[[str], str] = input,
           secret: Callable[[str], str] = getpass.getpass, say: Callable[[str], None] = print,
           config: Path = CONFIG, client: "Client | None" = None) -> int:
    """Пошаговая выгрузка для человека: без флагов и переменных окружения."""
    say(f"kinopub-history {__version__} — выгрузка своей истории kinopub\n"
        "Неофициальная программа. Заходит на сайт под вашим логином и читает ваши же страницы\n"
        "(история, «Я смотрю», закладки). Видео не трогает. Пароль никуда не отправляется, кроме kinopub.\n")
    client = client or Client(base=base, cookies=config / "cookies.txt")
    archive = DirArchive(config / "archive")

    reuse = False
    if archive.get("home.html"):
        when = _dt.datetime.fromtimestamp((archive.path / "home.html").stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        a = ask(f"Есть скачанная история от {when}.\n  1 — скачать заново (по умолчанию)\n"
                "  2 — только сделать файлы из скачанного (без сайта)\nВыбор [1]: ").strip()
        reuse = a == "2"

    if not reuse:
        try:
            client.login()
            say("Вход: сохранённая сессия.")
        except LoginError:
            while True:
                login = ask("Логин или email kinopub: ").strip()
                password = secret("Пароль (не отображается): ")
                try:
                    client.login(login, password,
                                 code=lambda: ask("Сайт прислал код на почту («Проверочный код для кинопаба»). Код: "))
                    say("Вход выполнен.")
                    break
                except CodeRequired:
                    say("Без кода из письма сайт не пустит. Попробуйте ещё раз.")
                except LoginError as e:
                    say(f"{e}. Попробуйте ещё раз (Ctrl+C — выйти).")
        a = ask("\nКак скачивать?\n"
                "  1 — быстро, 5–10 минут (по умолчанию): вся история, «Я смотрю», закладки,\n"
                "      где остановились в каждом сериале\n"
                "  2 — полностью, 20–40 минут: плюс отметки «просмотрено» по всем сезонам всех сериалов\n"
                "Выбор [1]: ").strip()
        say("\nСкачиваю. Сайт чужой — по одной странице раз в 1,5 с, это нормально.")
        Grabber(client, archive, log=say, all_seasons=a == "2").run()

    folder = Path(ask(f"\nКуда сохранить файлы [{default_folder()}]: ").strip() or default_folder()).expanduser()
    data = assemble(archive, source=base)
    notes = export_bundle(data, folder)
    if notes:
        say("")
    for note in notes:
        say(note)
    say("\nГотово: " + _summary(data, folder))
    say("Что в каких файлах — README.txt в этой папке.")
    return 0


# --- команды -----------------------------------------------------------------------------------

def _grab(args: argparse.Namespace) -> None:
    client = Client(base=args.base, cookies=args.cookies, pause=args.pause)
    archive = DirArchive(args.archive)
    only = args.only.split(",") if args.only else Grabber.ALL
    g = Grabber(client, archive, log=_log, sections=only, all_seasons=args.full)
    login = args.login or os.environ.get("KINOPUB_LOGIN")
    password = args.password or os.environ.get("KINOPUB_PASSWORD")
    if login and not password and sys.stdin.isatty():
        password = getpass.getpass("пароль kinopub: ")

    def code() -> str:
        if args.code:
            return args.code
        return input("код из письма «Проверочный код для кинопаба»: ") if sys.stdin.isatty() else ""

    if args.resume:  # докачать сериалы после обрыва, разделы не трогаем
        client.login(login, password, code)
        g.series(serials(assemble(archive)), resume=True)
    else:
        g.run(login, password, code)
    _log(f"архив страниц: {archive.path}")


def _export(args: argparse.Namespace) -> None:
    data = assemble(DirArchive(args.archive), source=args.base)
    if not args.format:  # всё в папку
        folder = Path(args.output).expanduser() if args.output else default_folder()
        for note in export_bundle(data, folder):
            _log(note)
        _log(_summary(data, folder))
        return
    what = args.what or ("all" if "all" in FORMATS[args.format].whats else "history")
    single = args.output and args.output != "-"
    out = open(args.output, "w", encoding="utf-8", newline="") if single else sys.stdout
    try:
        for note in export(data, args.format, out, what):
            _log(note)
    finally:
        if out is not sys.stdout:
            out.close()
    if single:
        _log(f"{args.format} ({what}) → {args.output}")


def _utf8_output() -> None:
    """Windows при перенаправленном выводе (в файл, в другую программу, в CI) пишет в cp1252 — русский
    текст падает с UnicodeEncodeError. Переключаем stdout/stderr на UTF-8; консоль Windows его принимает."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: "list[str] | None" = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    _utf8_output()
    p = argparse.ArgumentParser(prog="kinopub-history", description="Выгрузка своей истории kinopub. "
                                "Без аргументов — мастер с вопросами.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--archive", default=str(CONFIG / "archive"), help="каталог сырых страниц (%(default)s)")
    p.add_argument("--base", default=os.environ.get("KINOPUB_BASE", DEFAULT_BASE), help="адрес сайта (%(default)s)")
    sub = p.add_subparsers(dest="cmd")

    def grab_args(s: argparse.ArgumentParser) -> None:
        s.add_argument("--login")
        s.add_argument("--password")
        s.add_argument("--code", help="код из письма, если сайт попросит")
        s.add_argument("--cookies", default=str(CONFIG / "cookies.txt"), help="файл сессии (%(default)s)")
        s.add_argument("--pause", type=float, default=1.5, help="секунд между запросами (%(default)s)")
        s.add_argument("--only", help="разделы через запятую: " + ",".join(Grabber.ALL))
        s.add_argument("--full", action="store_true",
                       help="у сериалов — страницы всех сезонов (отметки по каждой серии; 20–40 мин вместо 5–10)")
        s.add_argument("--resume", action="store_true", help="докачать сериалы после обрыва")

    def export_args(s: argparse.ArgumentParser) -> None:
        s.add_argument("-f", "--format", choices=sorted(FORMATS), help="один формат; без него — все форматы в папку")
        s.add_argument("-w", "--what", help="раздел для -f: all, " + ", ".join(WHAT))
        s.add_argument("-o", "--output", help="папка (без -f) или файл (с -f; по умолчанию stdout)")

    grab_args(sub.add_parser("grab", help="скачать страницы аккаунта в архив"))
    export_args(sub.add_parser("export", help="собрать выгрузку из архива (без сети)"))
    r = sub.add_parser("run", help="grab + export")
    grab_args(r)
    export_args(r)
    sub.add_parser("formats", help="список форматов")
    sub.add_parser("wizard", help="мастер с вопросами (то же, что запуск без аргументов)")
    args = p.parse_args(argv)

    try:
        if args.cmd in (None, "wizard"):
            if not sys.stdin.isatty() and args.cmd is None:
                p.print_help()
                return 2
            try:
                rc = wizard(args.base)
            except KeyboardInterrupt:
                print("\nОстановлено.")
                rc = 130
            except KinopubError as e:
                print(f"\nОшибка: {e}")
                rc = 1
            if FROZEN:  # окно, открытое двойным щелчком, не должно закрыться раньше, чем прочитали
                try:
                    input("\nНажмите Enter, чтобы закрыть окно.")
                except EOFError:
                    pass
            return rc
        if args.cmd == "formats":
            for f in FORMATS.values():
                print(f"{f.name:12} {f.description}\n{'':12} разделы: {', '.join(f.whats)}")
            return 0
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
