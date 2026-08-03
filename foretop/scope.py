"""Scope matching.

A scope is a set of patterns that decide which hosts are in bounds. Two styles:

* **domain** — ``example.com`` matches ``example.com`` and any subdomain of it
  (``api.example.com``, ``a.b.example.com``). This is the usual bug-bounty scope.
* **glob** — anything containing ``*``, ``?`` or ``[`` is matched with ``fnmatch``,
  so ``*.example.com`` matches subdomains only and ``*`` matches everything.

Excludes are checked first and win over includes.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable

_GLOB_CHARS = set("*?[")


def _is_glob(pattern: str) -> bool:
    return any(c in _GLOB_CHARS for c in pattern)


def _match_one(host: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    if _is_glob(pattern):
        return fnmatch.fnmatch(host, pattern)
    return host == pattern or host.endswith("." + pattern)


class Scope:
    def __init__(self, patterns: Iterable[str], excludes: Iterable[str] = ()) -> None:
        self.patterns = [p.strip().lower().rstrip(".") for p in patterns if p.strip()]
        self.excludes = [e.strip().lower().rstrip(".") for e in excludes if e.strip()]
        if not self.patterns:
            raise ValueError("scope needs at least one pattern (use '*' to match all)")

    def match(self, host: str) -> str | None:
        """Return the pattern the host matched, or ``None`` if out of scope."""
        host = host.strip().lower().rstrip(".")
        if not host:
            return None
        for ex in self.excludes:
            if _match_one(host, ex):
                return None
        for p in self.patterns:
            if _match_one(host, p):
                return p
        return None
