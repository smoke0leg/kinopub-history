"""Генерирует schema/export.schema.json из моделей (dataclass'ы → JSON Schema 2020-12).

Запуск: python scripts/gen_schema.py   (после любой правки models.py; тест сверяет ключи схемы с выгрузкой)
"""
from __future__ import annotations

import dataclasses
import json
import sys
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kinopub_history import models  # noqa: E402

DOCS = {
    "Export": "Выгрузка истории kinopub (kinopub-history, формат json, раздел all).",
    "HistoryEntry": "Запись истории: тайтл (history) или серия (episodes). media_id — id медиа, не просмотра.",
    "Series": "Сериал: серии всех скачанных сезонов. «Где остановились» — last_seen (по истории), не page_active.",
}


def schema_of(tp, defs: dict) -> dict:
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Union:
        inner = [a for a in args if a is not type(None)]
        return {"anyOf": [schema_of(inner[0], defs), {"type": "null"}]}
    if origin is list:
        return {"type": "array", "items": schema_of(args[0], defs)}
    if dataclasses.is_dataclass(tp):
        name = tp.__name__
        if name not in defs:
            defs[name] = {}
            defs[name] = obj(tp, defs)
        return {"$ref": f"#/$defs/{name}"}
    return {int: {"type": "integer"}, float: {"type": "number"}, str: {"type": "string"},
            bool: {"type": "boolean"}}[tp]


def obj(cls, defs: dict) -> dict:
    hints = typing.get_type_hints(cls)
    fields = dataclasses.fields(cls)
    out = {"type": "object", "properties": {f.name: schema_of(hints[f.name], defs) for f in fields},
           "required": [f.name for f in fields], "additionalProperties": False}
    if cls.__name__ in DOCS:
        out["description"] = DOCS[cls.__name__]
    return out


def main() -> None:
    defs: dict = {}
    root = obj(models.Export, defs)
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
              "$id": "https://github.com/kinopub-history/kinopub-history/schema/export.schema.json",
              "title": "kinopub-history export", **root, "$defs": dict(sorted(defs.items()))}
    out = ROOT / "schema" / "export.schema.json"
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
