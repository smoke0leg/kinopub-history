"""Тесты на синтетических страницах той же структуры, что у kinopub (tests/fixtures). Сети нет."""
from __future__ import annotations

import csv
import io
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from kinopub_history import (Archive, Client, CodeRequired, Export, Grabber, LoginError, NotFound, assemble,
                             export, exporter, parse)
from kinopub_history.export import FORMATS

FX = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


class FakeSite:
    """Подменный транспорт: путь → страница. Пагинация как у сайта: после последней страницы — она же."""

    def __init__(self, routes: dict[str, "str | list[str]"], logged_in: bool = True):
        self.routes, self.logged_in, self.calls, self.posts = routes, logged_in, [], []

    def __call__(self, method: str, url: str, data):
        u = urlparse(url)
        self.calls.append((method, u.path + ("?" + u.query if u.query else "")))
        if method == "POST":
            self.posts.append(data)
            if "login-form[password]" in data:
                if data["login-form[password]"] != "secret":
                    return url, fx("login_bad.html")
                if self.routes.get("__need_code__"):
                    return url, fx("login_code.html")
            if "login-form[formcode]" in data and data["login-form[formcode]"] != "123456":
                return url, fx("login_bad.html")
            self.logged_in = True
            return "https://kino.test/", fx("home.html")
        if u.path == "/user/login":
            return (("https://kino.test/", fx("home.html")) if self.logged_in else (url, fx("login.html")))
        page = self.routes.get(u.path)
        if page is None:
            raise NotFound(url)
        if isinstance(page, list):
            n = int(parse_qs(u.query).get("page", ["1"])[0])
            page = page[min(n, len(page)) - 1]
        return url, page


def site(**extra) -> FakeSite:
    routes = {
        "/history/index": fx("history_films.html"),
        "/history/index/tester-1/episodes": fx("history_episodes.html"),
        "/history/index/tester-1/movie": fx("history_movie.html"),
        "/history/index/tester-1/serial": fx("history_episodes.html"),
        "/watchlist/tester-1": fx("watchlist.html"),
        "/favorites": fx("bookmarks.html"),
        "/favorites/view": fx("folder.html"),
        "/users/tester-1": fx("profile.html"),
        "/item/view/16918": fx("series_16918.html"),
        "/item/view/16918/s1e1": fx("series_16918_s01.html"),
        "/item/view/16918/s3e1": fx("series_16918_s03.html"),
        "/item/view/78667": fx("series_78667.html"),
    }
    routes.update(extra)
    return FakeSite(routes)


def grabbed(**kw) -> tuple[Archive, Export, FakeSite]:
    s = site()
    a = Archive()
    Grabber(Client(base="https://kino.test", pause=0, fetch=s), a, **kw).run()
    return a, assemble(a), s


class ParseTest(unittest.TestCase):
    def test_history_films(self):
        h = parse.history(fx("history_films.html"))
        self.assertEqual([e.kp_id for e in h], [3685, 393])
        t = h[0]
        self.assertEqual((t.title, t.original_title, t.year), ("Тумстоун: Легенда дикого запада", "Tombstone", 1993))
        self.assertEqual(t.watched_on, "2026-10-15")
        self.assertEqual(t.media_id, 9838)
        self.assertEqual(t.imdb_id, "tt0108358")  # на сайте tt108358 — дополняем нулями
        self.assertEqual((t.imdb_rating, t.kinopoisk_id, t.kinopoisk_rating), (7.8, 2221, 7.2))
        self.assertEqual(t.kinopub_thumbs, "8.7")
        self.assertEqual(t.genres, ["Боевик", "Вестерн"])
        self.assertTrue(t.poster.endswith("/poster/item/small/3685.jpg"))
        self.assertIsNone(t.season)
        self.assertEqual(h[1].watched_on, "2024-03-02")

    def test_history_episodes(self):
        h = parse.history(fx("history_episodes.html"), "serial")
        self.assertEqual([(e.kp_id, e.season, e.episode, e.watched_on) for e in h][:2],
                         [(78667, 6, 1, "2026-10-14"), (16918, 3, 10, "2026-10-14")])
        self.assertEqual(h[0].original_title, "Slow Horses")
        self.assertTrue(all(e.is_episode and e.types == ["serial"] for e in h))

    def test_tabs(self):
        self.assertEqual(set(parse.history_tabs(fx("history_films.html"))), {"episodes", "movie", "serial"})

    def test_watchlist(self):
        (w,) = parse.watchlist(fx("watchlist.html"))
        self.assertEqual((w.kp_id, w.unwatched, w.imdb_id, w.imdb_rating, w.kinopoisk_rating, w.kinopub_views),
                         (16918, 5, "tt5712554", 8.7, 8.9, "7.9K"))
        self.assertEqual(w.original_title, "The Grand Tour")

    def test_profile(self):
        p = parse.profile(fx("profile.html"))
        self.assertEqual([t.title for t in p.like], ["Корона"])
        self.assertEqual(p.like[0].original_title, "The Crown")  # текст ссылки, атрибута title нет
        self.assertEqual(p.like[0].genres, ["Драма"])
        self.assertEqual([t.kp_id for t in p.watch], [16918, 78667])
        self.assertEqual((p.dislike, p.now), ([], []))

    def test_folders(self):
        self.assertEqual(parse.folders(fx("bookmarks.html")), {432790: "на потом"})

    def test_series_page(self):
        s = parse.series_page(fx("series_16918.html"))
        self.assertEqual((s["title"], s["original_title"], s["imdb_id"], s["kinopoisk_id"]),
                         ("Гранд тур", "The Grand Tour", "tt5712554", 982730))
        self.assertEqual((s["seasons"], s["season_shown"]), ([1, 2, 3], 2))
        e1, e2 = s["episodes"]
        self.assertEqual((e1.watched, e1.current, e2.watched, e2.progress, e2.current), (True, False, False, 21, True))

    def test_series_page_without_episodes(self):
        s = parse.series_page(fx("series_movie.html"))
        self.assertEqual((s["seasons"], s["episodes"], s["title"]), ([], [], "Купертино"))

    def test_sections(self):
        self.assertEqual(parse.sections(fx("home.html"), "https://kino.test"),
                         {"history": "/history", "watchlist": "/watchlist/tester-1", "bookmarks": "/favorites"})
        self.assertEqual(parse.login_name(fx("home.html")), "tester-1")


class LoginTest(unittest.TestCase):
    def test_saved_session(self):
        s = FakeSite({}, logged_in=True)
        Client(pause=0, fetch=s).login()
        self.assertEqual(s.posts, [])

    def test_password_and_code(self):
        s = FakeSite({"__need_code__": True}, logged_in=False)
        Client(pause=0, fetch=s).login("u", "secret", code=lambda: " 123456 ")
        self.assertEqual(s.posts[0]["_csrf"], "tok123")
        self.assertEqual(s.posts[1], {"_csrf": "tok456", "login-form[formcode]": "123456"})

    def test_code_required(self):
        s = FakeSite({"__need_code__": True}, logged_in=False)
        with self.assertRaises(CodeRequired):
            Client(pause=0, fetch=s).login("u", "secret")

    def test_bad_password(self):
        with self.assertRaisesRegex(LoginError, "Неверный логин"):
            Client(pause=0, fetch=FakeSite({}, logged_in=False)).login("u", "wrong")

    def test_no_credentials(self):
        with self.assertRaises(LoginError):
            Client(pause=0, fetch=FakeSite({}, logged_in=False)).login()


class GrabTest(unittest.TestCase):
    def test_full_run(self):
        a, d, s = grabbed()
        self.assertEqual([h.kp_id for h in d.history], [3685, 393])
        self.assertEqual(d.history[0].types, ["movie"])  # «Все фильмы» + вкладка movie склеены по media_id
        self.assertEqual(len(d.episodes), 4)  # «Все эпизоды» и «Сериалы» — одни и те же серии
        self.assertEqual(d.episodes[0].types, ["serial"])
        self.assertEqual([w.kp_id for w in d.watchlist], [16918])
        self.assertEqual([(b.kp_id, b.folder) for b in d.bookmarks], [(3685, "на потом")])
        self.assertEqual([t.title for t in d.profile.like], ["Корона"])

    def test_pagination_stops_on_repeat(self):
        _, _, s = grabbed()
        pages = [c for _, c in s.calls if c.startswith("/history/index?")]
        self.assertEqual(len(pages), 2)  # стр. 2 повторила стр. 1 — новых нет, стоп

    def test_series(self):
        _, d, _ = grabbed()
        gt = next(x for x in d.series if x.kp_id == 16918)
        self.assertEqual(gt.imdb_id, "tt5712554")
        self.assertEqual((gt.last_seen.season, gt.last_seen.episode, gt.last_seen.watched_on), (3, 10, "2026-10-14"))
        self.assertEqual(gt.last_seen.title, "The Youth Vote")
        self.assertEqual((gt.page_active.season, gt.page_active.episode), (2, 2))  # страница ≠ где остановились
        self.assertEqual(gt.seasons_loaded, [1, 2, 3])
        self.assertEqual((gt.episodes_total, gt.episodes_watched), (7, 6))
        self.assertEqual(gt.seasons_complete, [1, 3])
        self.assertEqual(sum(e.current for e in gt.episodes), 1)  # active со страниц /sNe1 сброшен
        self.assertEqual(gt.first_seen_on, "2026-10-13")

    def test_current_season_only(self):
        _, d, s = grabbed(all_seasons=False)
        self.assertNotIn(("GET", "/item/view/16918/s1e1"), s.calls)
        gt = next(x for x in d.series if x.kp_id == 16918)
        self.assertEqual(gt.seasons_loaded, [2])

    def test_missing_series_does_not_stop(self):
        s = site()
        del s.routes["/item/view/78667"]
        a = Archive()
        Grabber(Client(base="https://kino.test", pause=0, fetch=s), a).run()
        d = assemble(a)
        slow = next(x for x in d.series if x.kp_id == 78667)
        self.assertEqual(slow.missing, "HTTP 404")
        self.assertEqual(slow.title, "Медленные лошади")  # название — из истории серий
        self.assertTrue(any(x.kp_id == 16918 and x.episodes for x in d.series))

    def test_resume(self):
        a, _, _ = grabbed(sections=("history", "watchlist", "profile"))
        s = site()
        g = Grabber(Client(base="https://kino.test", pause=0, fetch=s), a)
        a.put("series-16918.html", fx("series_16918.html"))
        from kinopub_history import serials
        g.series(serials(assemble(a)), resume=True)
        self.assertNotIn(("GET", "/item/view/16918"), s.calls)
        self.assertIn(("GET", "/item/view/78667"), s.calls)


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = grabbed()[1]

    def run_fmt(self, fmt, what):
        buf = io.StringIO()
        notes = export(self.data, fmt, buf, what)
        return buf.getvalue(), notes

    def test_json_roundtrip(self):
        out, _ = self.run_fmt("json", "all")
        doc = json.loads(out)
        self.assertEqual(doc["schema_version"], 1)
        self.assertEqual(doc["history"][0]["imdb_id"], "tt0108358")
        self.assertEqual(len(doc["series"]), 2)

    def test_json_matches_schema_keys(self):
        schema = json.loads((Path(__file__).parents[1] / "schema" / "export.schema.json").read_text())
        doc = json.loads(self.run_fmt("json", "all")[0])
        self.assertEqual(set(doc), set(schema["properties"]))
        for section, ref in (("history", "HistoryEntry"), ("series", "Series"), ("watchlist", "WatchlistEntry")):
            self.assertEqual(set(doc[section][0]), set(schema["$defs"][ref]["properties"]), section)

    def test_jsonl(self):
        lines = [json.loads(x) for x in self.run_fmt("jsonl", "all")[0].splitlines()]
        self.assertEqual({x["kind"] for x in lines}, {"history", "episodes", "watchlist", "bookmarks", "series", "likes"})

    def test_csv(self):
        rows = list(csv.DictReader(io.StringIO(self.run_fmt("csv", "history")[0])))
        self.assertEqual(rows[0]["genres"], "Боевик; Вестерн")
        series = list(csv.DictReader(io.StringIO(self.run_fmt("csv", "series")[0])))
        self.assertIn("last_seen_episode", series[0])
        self.assertNotIn("episodes", series[0])

    def test_letterboxd(self):
        rows = list(csv.reader(io.StringIO(self.run_fmt("letterboxd", "history")[0])))
        self.assertEqual(rows[0], ["Title", "Year", "imdbID", "WatchedDate"])
        self.assertEqual(rows[1], ["Tombstone", "1993", "tt0108358", "2026-10-15"])

    def test_trakt(self):
        out, notes = self.run_fmt("trakt", "all")
        body = json.loads(out)
        self.assertEqual(body["movies"][0], {"watched_at": "2026-10-15T12:00:00.000Z", "title": "Tombstone",
                                             "year": 1993, "ids": {"imdb": "tt0108358"}})
        gt = next(s for s in body["shows"] if s["ids"]["imdb"] == "tt5712554")
        self.assertEqual([e["number"] for e in gt["seasons"][0]["episodes"]], [8, 9, 10])
        self.assertEqual(notes, [])

    def test_unknown_format_and_section(self):
        with self.assertRaises(ValueError):
            export(self.data, "nope", io.StringIO())
        with self.assertRaises(ValueError):
            export(self.data, "letterboxd", io.StringIO(), "series")

    def test_custom_exporter(self):
        @exporter("titles", "только названия", ("history",))
        def titles(data, out, what):
            out.write("\n".join(h.title for h in data.history))
            return []
        try:
            self.assertEqual(self.run_fmt("titles", "history")[0].splitlines()[1], "Водный мир")
        finally:
            FORMATS.pop("titles")


if __name__ == "__main__":
    unittest.main()


class BundleAndWizardTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_bundle(self):
        from kinopub_history import export_bundle
        export_bundle(grabbed()[1], self.tmp / "out")
        names = {f.name for f in (self.tmp / "out").iterdir()}
        self.assertEqual(names, {"films.csv", "episodes.csv", "series.csv", "watchlist.csv", "bookmarks.csv",
                                 "likes.csv", "letterboxd.csv", "trakt.json", "kinopub.json", "README.txt"})
        self.assertTrue((self.tmp / "out/films.csv").read_bytes().startswith(b"\xef\xbb\xbf"))  # BOM для Excel
        self.assertTrue((self.tmp / "out/letterboxd.csv").read_bytes().startswith(b"Title,"))  # без BOM
        self.assertIn("фильмов: 2, серий: 4, сериалов: 2", (self.tmp / "out/README.txt").read_text())

    def run_wizard(self, answers, logged_in=False, **site_kw):
        from kinopub_history.cli import wizard
        s = site(**site_kw)
        s.logged_in = logged_in
        said = []
        rc = wizard(ask=lambda q: answers.pop(0), secret=lambda q: "secret", say=said.append,
                    config=self.tmp / "cfg", client=Client(base="https://kino.test", pause=0, fetch=s))
        return rc, s, "\n".join(said)

    def test_wizard_login_with_code_fast(self):
        out = self.tmp / "export"
        rc, s, said = self.run_wizard(["user", "123456", "", str(out)], __need_code__=True)
        self.assertEqual(rc, 0)
        self.assertIn("Вход выполнен", said)
        self.assertNotIn(("GET", "/item/view/16918/s1e1"), s.calls)  # быстро — без прочих сезонов
        self.assertTrue((out / "series.csv").exists())

    def test_wizard_wrong_code_then_ok(self):
        out = self.tmp / "export"
        rc, _, said = self.run_wizard(["user", "000000", "user", "123456", "2", str(out)], __need_code__=True)
        self.assertEqual(rc, 0)
        self.assertIn("Попробуйте ещё раз", said)

    def test_wizard_full_and_reuse(self):
        out1, out2 = self.tmp / "e1", self.tmp / "e2"
        _, s, _ = self.run_wizard(["2", str(out1)], logged_in=True)
        self.assertIn(("GET", "/item/view/16918/s1e1"), s.calls)  # полностью — все сезоны
        rc, s2, said = self.run_wizard(["2", str(out2)], logged_in=True)  # «2» — только файлы из скачанного
        self.assertEqual((rc, s2.calls), (0, []))
        self.assertEqual((out1 / "kinopub.json").read_text().count('"kp_id"'),
                         (out2 / "kinopub.json").read_text().count('"kp_id"'))

    def test_no_args_without_terminal_prints_help(self):
        import contextlib
        from kinopub_history.cli import main
        from unittest import mock
        with contextlib.redirect_stdout(io.StringIO()) as buf, mock.patch("sys.stdin", io.StringIO()):
            rc = main([])  # stdin не терминал (StringIO.isatty() — False): мастер не запускается
        self.assertEqual(rc, 2)
        self.assertIn("мастер", buf.getvalue())

    def test_network_failure_is_clean_error(self):
        from kinopub_history import KinopubError
        with self.assertRaisesRegex(KinopubError, "сайт не отвечает"):
            Client(base="http://127.0.0.1:9", pause=0, retries=0, timeout=2).get("/")
