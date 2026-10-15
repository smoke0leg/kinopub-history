"""Архив сырых страниц. Зачем: если аккаунт удалят, а разбор окажется неполным — страницы останутся
и переразберутся новой версией без сайта (`assemble(archive)`).

Имена: <раздел>-NNNN.html, страницы сериалов series-<kp_id>.html / series-<kp_id>-sNN.html,
снятые с сайта тайтлы — series-<kp_id>.missing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional


class Archive:
    """Хранилище страниц. Базовая реализация — в памяти; DirArchive — в каталоге."""

    def __init__(self) -> None:
        self._pages: dict[str, str] = {}

    def put(self, name: str, text: str) -> None:
        self._pages[name] = text

    def get(self, name: str) -> Optional[str]:
        return self._pages.get(name)

    def names(self) -> list[str]:
        return sorted(self._pages)

    def pages(self, section: str) -> Iterator[str]:
        """Страницы раздела по порядку: <section>-0001.html, -0002.html…"""
        pat = re.compile(re.escape(section) + r"-\d{4}\.html")
        for n in self.names():
            if pat.fullmatch(n):
                text = self.get(n)
                if text is not None:
                    yield text

    def sections(self, prefix: str) -> list[str]:
        """Разделы с данным префиксом: history-episodes, history-serial… (по именам страниц)."""
        out = {m.group(1) for n in self.names() if (m := re.fullmatch(r"(" + re.escape(prefix) + r"[\w-]*?)-\d{4}\.html", n))}
        return sorted(out)

    def clear(self, prefix: str) -> None:
        for n in self.names():
            if n.startswith(prefix):
                self.delete(n)

    def delete(self, name: str) -> None:
        self._pages.pop(name, None)


class DirArchive(Archive):
    def __init__(self, path: "str | Path") -> None:
        super().__init__()
        self.path = Path(path).expanduser()
        self.path.mkdir(parents=True, exist_ok=True)

    def put(self, name: str, text: str) -> None:
        (self.path / name).write_text(text, encoding="utf-8")

    def get(self, name: str) -> Optional[str]:
        f = self.path / name
        return f.read_text(encoding="utf-8") if f.exists() else None

    def names(self) -> list[str]:
        return sorted(f.name for f in self.path.iterdir() if f.is_file())

    def delete(self, name: str) -> None:
        (self.path / name).unlink(missing_ok=True)
