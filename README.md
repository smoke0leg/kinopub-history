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

## Установка

```bash
pip install kinopub-history          # или: pip install git+https://<репозиторий>
```

Нужен только Python ≥ 3.9, зависимостей нет.

## Быстрый старт

```bash
export KINOPUB_LOGIN=you@example.com
kinopub-history run -f json -o kinopub.json      # скачать и выгрузить всё
```

При первом входе с нового места сайт присылает код в письме «Проверочный код для кинопаба» — утилита
спросит его в терминале (или `--code 123456`). Сессия сохраняется в `~/.config/kinopub-history/cookies.txt`
(права 0600), повторные запуски пароль и код не спрашивают.

Скачивание и выгрузка разделены: страницы складываются в архив (`~/.config/kinopub-history/archive/`),
а выгрузку из архива можно делать сколько угодно раз и в любом формате — без сети:

```bash
kinopub-history grab                                   # скачать (≈ 15–30 мин, если сериалов много)
kinopub-history export -f csv -w history -o films.csv
kinopub-history export -f csv -w episodes -o episodes.csv
kinopub-history export -f letterboxd -w history -o letterboxd.csv
kinopub-history export -f trakt -o trakt.json
kinopub-history formats                                # все форматы и разделы
```

Архив — ваша страховка: если аккаунт удалят, а в разборе найдётся ошибка, новая версия переразберёт
сохранённые страницы.

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
from kinopub_history import Client, Grabber, DirArchive, assemble, export

client = Client(cookies="cookies.txt")                 # pause=1.5, base="https://kino.watch"
archive = DirArchive("archive/")                       # или Archive() — в памяти
Grabber(client, archive, log=print).run("login", "password", code=lambda: input("код: "))

data = assemble(archive)                               # Export: dataclass'ы
for s in data.series:
    if s.last_seen:
        print(s.title, s.imdb_id, f"S{s.last_seen.season}E{s.last_seen.episode}", s.last_seen.watched_on)

with open("films.csv", "w", newline="") as f:
    export(data, "csv", f, what="history")
```

- **Разбор без сети**: `kinopub_history.parse` — чистые функции HTML → модели (`parse.history`, `parse.series_page`, …).
- **Свой транспорт**: `Client(fetch=fn)`, где `fn(method, url, data) -> (final_url, html)` — прокси, `requests`,
  cookie из браузера, тесты. На 404 бросайте `NotFound`.
- **Свой формат**: декоратор `@exporter("name", "описание", ("history",))`, функция `(data, out, what) -> list[str]`.
- **Частичный проход**: `Grabber(..., sections=("history", "watchlist"), all_seasons=False)`.
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
```

## Лицензия

MIT.

---

## English summary

**kinopub-history** exports *your own* kinopub watch history (films and episodes with dates, watchlist,
bookmarks, likes, per-series progress) to JSON (with a JSON Schema), JSONL, CSV, Letterboxd import CSV and a
Trakt `/sync/history` body. kinopub has no public API, so the tool signs in with your credentials (including the
e-mailed one-time code) and reads the same pages you see in a browser, one request per 1.5 s. Pages are archived
locally so exports can be regenerated offline. Pure Python ≥ 3.9, no dependencies; usable as a CLI or as an SDK
(`Client`, `Grabber`, `assemble`, `export`, pluggable transport and exporters). Unofficial, not affiliated with
kinopub; for your own account only. MIT license.
