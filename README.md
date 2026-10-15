# kinopub-history

Выгрузка **своей** истории просмотров kinopub в нормальный формат: фильмы и серии с датами, «Я смотрю»,
закладки, лайки, где остановились в каждом сериале. Форматы: JSON (со схемой), JSONL, CSV,
импорт в **Letterboxd** и **Trakt**, свой — одной функцией.

API у kinopub закрыт, выгрузку поддержка не делает. Утилита заходит на сайт под вашим логином
и читает те же страницы, что вы видите в браузере.

*English summary below.*

> Неофициальный инструмент, с kinopub не связан. Только для своего аккаунта. Видео и потоки не трогает,
> запросы идут по одному раз в 1,5 с. Сайт меняет вёрстку — если разбор сломался, откройте issue
> (без своих страниц: в них ваш email и история).

## Как пользоваться — без программирования

1. Скачайте программу для своей системы со страницы
   [последнего релиза](https://github.com/smoke0leg/kinopub-history/releases/latest):
   - Windows — `kinopub-history-windows-x64.exe`
   - Mac на Apple M1/M2/M3/M4 — `kinopub-history-macos-arm64`, на Intel — `kinopub-history-macos-x64`
   - Linux — `kinopub-history-linux-x64`
2. Запустите её двойным щелчком (откроется окно с вопросами).
   - **Windows** предупредит «Windows защитила ваш компьютер» — программа без платной подписи.
     Нажмите «Подробнее» → «Выполнить в любом случае».
   - **macOS** не даст открыть программу неизвестного разработчика. Щёлкните по файлу правой кнопкой →
     «Открыть» → «Открыть». Если не помогло — Системные настройки → Конфиденциальность и безопасность →
     «Всё равно открыть». Или в Терминале: `xattr -d com.apple.quarantine ~/Downloads/kinopub-history-macos-*`
     и `chmod +x ~/Downloads/kinopub-history-macos-*`.
   - **Linux**: `chmod +x kinopub-history-linux-x64 && ./kinopub-history-linux-x64`.
3. Ответьте на вопросы: логин или email kinopub, пароль, **код из письма** «Проверочный код для кинопаба»
   (сайт присылает его при входе с нового устройства), быстро или полностью.
4. Через 5–10 минут рядом с программой появится папка `kinopub-export-<дата>`:

| Файл | Что внутри |
|---|---|
| `films.csv` | фильмы, докфильмы, концерты: день просмотра, IMDb, Кинопоиск, жанры, режиссёр |
| `episodes.csv` | просмотренные серии: сериал, сезон, серия, день |
| `series.csv` | сериалы: где остановились (`last_seen_*`), сколько серий досмотрено |
| `watchlist.csv` | «Я смотрю»: сколько серий ещё не смотрели |
| `bookmarks.csv` | закладки по папкам |
| `likes.csv` | «Понравились» |
| `letterboxd.csv` | для импорта в [Letterboxd](https://letterboxd.com/import/) |
| `trakt.json` | для импорта в Trakt (`POST /sync/history`) |
| `kinopub.json` | всё одним файлом |
| `README.txt` | что где и сколько записей |

CSV открываются в Excel, Numbers и Google Таблицах. Повторный запуск не спрашивает пароль и код —
сессия сохраняется. Скачанные страницы тоже сохраняются: файлы можно пересобрать без сайта
(мастер предложит «только сделать файлы из скачанного»).

**Быстро или полностью?** Быстро (5–10 минут) — вся история, «Я смотрю», закладки и где вы
остановились в каждом сериале. Полностью (20–40 минут) — плюс отметки «просмотрено» по каждой серии
всех сезонов. Сайт чужой, программа берёт по одной странице раз в 1,5 с.

## Командная строка

```bash
pip install kinopub-history        # Python ≥ 3.9, зависимостей нет
kinopub-history                    # тот же мастер с вопросами
```

Без вопросов (для скриптов и cron):

```bash
export KINOPUB_LOGIN=you@example.com KINOPUB_PASSWORD=…
kinopub-history run -o ./export                       # скачать и сложить все файлы в папку
kinopub-history run --full -o ./export                # то же, с отметками по всем сезонам
kinopub-history grab                                  # только скачать в архив (~/.config/kinopub-history/archive)
kinopub-history grab --resume                         # докачать сериалы после обрыва
kinopub-history export -o ./export                    # все файлы из архива, без сети
kinopub-history export -f csv -w episodes -o eps.csv  # один формат, один раздел
kinopub-history export -f jsonl | jq …                # в stdout
kinopub-history formats                               # все форматы и разделы
```

Код из письма CLI спрашивает в терминале (или `--code 123456`). Сессия — в
`~/.config/kinopub-history/cookies.txt` (права 0600). Другие флаги: `--only history,watchlist`,
`--pause 2`, `--archive DIR`, `--base https://новый.адрес` (если сайт снова переедет).

## Что выгружается

| Раздел (`-w`) | Что | Откуда |
|---|---|---|
| `history` | фильмы, докфильмы, концерты: день просмотра, IMDb/Кинопоиск с оценками, жанры, режиссёр, постер | «История» → все вкладки |
| `episodes` | серии: сериал, сезон, серия, день | «История» → «Сериалы», «ТВ шоу», «Докусериалы», «Все эпизоды» |
| `series` | сериалы целиком: IMDb, все серии с галочкой «просмотрено» и %, **где остановились** | страница сериала + история |
| `watchlist` | «Я смотрю»: сколько серий не смотрели | `/watchlist` |
| `bookmarks` | закладки по папкам | `/favorites/view?id=…` |
| `likes`, `dislikes` | «Понравились» / «Не понравились» — единственные явные оценки на kinopub | профиль |
| `all` | всё (для `json`, `jsonl`, `trakt`) | |

Разделы указываются в `export -f ФОРМАТ -w РАЗДЕЛ`; без `-f` выгружается всё в папку.

### Что важно знать о данных

- **Время просмотра сайт не показывает** — только день. Для Trakt ставится полдень UTC.
- **Пересмотры не сохраняются**: сайт хранит одну запись на фильм/серию с днём *последнего* просмотра.
  `media_id` — это id медиа, а не просмотра.
- **«Где остановились» — `series[].last_seen`** (последняя серия по истории). Серия, на которой сайт
  открывает страницу сериала (`page_active`), часто S1E1 и *не* является точкой остановки.
  `furthest_watched` — самая дальняя галочка; тоже не точка остановки (галочки ставят не по порядку).
- У серий в истории нет IMDb — он берётся со страницы сериала (раздел `series`), поэтому для Trakt
  нужен полный `grab`.
- Вкладка «Все фильмы», которую сайт открывает по умолчанию, — это не вся история: сериалы лежат
  в других вкладках. Утилита проходит все.
- Тайтл, снятый с сайта, отдаёт 404 — он попадает в `series` с `missing: "HTTP 404"`, проход не прерывается.

## Форматы

| `-f` | Что получится |
|---|---|
| `json` | весь документ или раздел. Схема: [`schema/export.schema.json`](schema/export.schema.json) (JSON Schema 2020-12) |
| `jsonl` | по записи на строку с полем `kind` — удобно для `jq`, БД, стриминга |
| `csv` | таблица раздела, UTF-8, списки через `; `, вложенные поля — `last_seen_season` и т.п. |
| `letterboxd` | CSV для [импорта Letterboxd](https://letterboxd.com/import/): `Title, Year, imdbID, WatchedDate` |
| `trakt` | тело запроса `POST https://api.trakt.tv/sync/history` (фильмы + серии по IMDb) |

Что не удалось сопоставить (нет IMDb и т.п.), печатается в stderr, а не теряется молча.

## SDK

```python
from kinopub_history import Client, Grabber, DirArchive, assemble, export, export_bundle

client = Client(cookies="cookies.txt")                 # pause=1.5, base="https://kino.watch"
archive = DirArchive("archive/")                       # или Archive() — в памяти
Grabber(client, archive, log=print).run("login", "password", code=lambda: input("код: "))

data = assemble(archive)                               # Export: dataclass'ы
for s in data.series:
    if s.last_seen:
        print(s.title, s.imdb_id, f"S{s.last_seen.season}E{s.last_seen.episode}", s.last_seen.watched_on)

with open("films.csv", "w", newline="") as f:
    export(data, "csv", f, what="history")

export_bundle(data, "export/")                         # все файлы + README.txt, как у мастера
```

- **Разбор без сети**: `kinopub_history.parse` — чистые функции HTML → модели (`parse.history`, `parse.series_page`, …).
- **Свой транспорт**: `Client(fetch=fn)`, где `fn(method, url, data) -> (final_url, html)` — прокси, `requests`,
  cookie из браузера, тесты. На 404 бросайте `NotFound`.
- **Свой формат**: декоратор `@exporter("name", "описание", ("history",))`, функция `(data, out, what) -> list[str]`.
- **Частичный проход**: `Grabber(..., sections=("history", "watchlist"), all_seasons=False)`
  (`all_seasons=True` — страницы всех сезонов, как `--full`).
- **Докачка после обрыва**: `grabber.series(serials(assemble(archive)), resume=True)` / `kinopub-history grab --resume`.
- Пример целиком: [`examples/embed.py`](examples/embed.py).

**Другие языки.** CLI пишет JSON/JSONL по опубликованной схеме — встраивается в Node, Go, Kotlin и т.д.
вызовом `kinopub-history export -f jsonl` и чтением stdout; по схеме генерируются типы (quicktype и т.п.).

## Приватность

Архив и cookie-файл содержат ваш email, логин и историю просмотров. Не публикуйте их и не прикладывайте
к issue. Для отчёта об ошибке разбора опишите, что изменилось в вёрстке, или приложите кусок HTML
с вымаранными данными. Тесты работают только на синтетических страницах (`tests/fixtures`).

## Разработка

```bash
python -m unittest discover -s tests -v
python scripts/gen_schema.py      # после правки models.py
pyinstaller --onefile --console --name kinopub-history packaging/entry.py   # программа
```

CI собирает программы для Windows, macOS и Linux на каждый push (`binaries.yml`) и прикрепляет их к релизу;
релиз публикует пакет на PyPI (`publish.yml`, Trusted Publishing).

## Лицензия

MIT.

---

## English summary

**kinopub-history** exports *your own* kinopub watch history (films and episodes with dates, watchlist,
bookmarks, likes, per-series progress) to JSON (with a JSON Schema), JSONL, CSV, Letterboxd import CSV and a
Trakt `/sync/history` body. kinopub has no public API, so the tool signs in with your credentials (including the
e-mailed one-time code) and reads the same pages you see in a browser, one request per 1.5 s. Pages are archived
locally so exports can be regenerated offline. Pure Python ≥ 3.9, no dependencies; usable as a CLI or as an SDK
(`Client`, `Grabber`, `assemble`, `export`, pluggable transport and exporters), or as a standalone
executable for Windows/macOS/Linux with a step-by-step wizard that writes CSV/JSON files into a folder. Unofficial, not affiliated with
kinopub; for your own account only. MIT license.
