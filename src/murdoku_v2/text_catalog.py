from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any


@lru_cache(maxsize=None)
def text_catalog(locale: str = "es") -> dict[str, Any]:
    path = files("murdoku_v2").joinpath("assets", "text", f"{locale}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def clue_text(key: str, **values: object) -> str:
    return str(text_catalog()[key]).format(**values)
