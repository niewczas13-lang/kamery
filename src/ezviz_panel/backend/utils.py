from __future__ import annotations

import re


SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = SLUG_RE.sub("_", value.lower()).strip("_")
    return slug or "item"
