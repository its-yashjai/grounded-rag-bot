"""Tiny JSON file persistence with atomic writes. Stands in for Postgres/
Redis in this MVP — same interface shape (load/save), swap-in later without
touching business logic above it."""
from __future__ import annotations

import json
import os
import tempfile
from threading import Lock


class JsonStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def load(self, default):
        if not os.path.exists(self.path):
            return default
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default

    def save(self, data) -> None:
        with self._lock:
            dir_ = os.path.dirname(self.path) or "."
            fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, self.path)
            except OSError:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise
