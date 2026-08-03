"""Scope matching.

A scope is a set of patterns that decide which hosts are in bounds. Two styles:

* **domain** — ``example.com`` matches ``example.com`` and any subdomain of it
  (``api.example.com``, ``a.b.example.com``). This is the usual bug-bounty scope.
* **glob** — anything containing ``*``, ``?`` or ``[`` is matched with ``fnmatch``,
  so ``*.example.com`` matches subdomains only and ``*`` matches everything.

Excludes are checked first and win over includes.

This is built to hold *large* scope sets (tens of thousands of bug-bounty
wildcards) cheaply. The two common shapes — a plain domain and ``*.domain`` —
are indexed by suffix so a host is matched in O(number of labels) via set
lookups instead of scanning every pattern. Only exotic globs (``*dev*.x.com``)
fall back to per-pattern ``fnmatch``.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable

_GLOB_CHARS = set("*?[")


def _is_glob(pattern: str) -> bool:
    return any(c in _GLOB_CHARS for c in pattern)


def _suffixes(host: str) -> list[str]:
    """All parent suffixes of a host, longest first.

    ``a.b.example.com`` -> ['a.b.example.com', 'b.example.com', 'example.com', 'com']
    """
    parts = host.split(".")
    return [".".join(parts[i:]) for i in range(len(parts))]


class _Matcher:
    """Indexes a set of patterns for fast membership tests."""

    def __init__(self, patterns: Iterable[str]) -> None:
        self.match_all = False
        self.domains: dict[str, str] = {}      # plain domain -> pattern
        self.subdomains: dict[str, str] = {}   # base of '*.base' -> pattern
        self.globs: list[str] = []             # everything else, fnmatch'd

        for raw in patterns:
            p = raw.strip().lower().rstrip(".")
            if not p:
                continue
            if p == "*":
                self.match_all = True
            elif p.startswith("*.") and not _is_glob(p[2:]):
                self.subdomains.setdefault(p[2:], p)
            elif not _is_glob(p):
                self.domains.setdefault(p, p)
            else:
                self.globs.append(p)

    def __bool__(self) -> bool:
        return bool(self.match_all or self.domains or self.subdomains or self.globs)

    def match(self, host: str) -> str | None:
        if self.match_all:
            return "*"
        sufs = _suffixes(host)
        # plain domain: host == d, or host is a subdomain of d
        if self.domains:
            for s in sufs:
                hit = self.domains.get(s)
                if hit:
                    return hit
        # '*.base': subdomains only (exclude the base itself -> skip full host)
        if self.subdomains:
            for s in sufs[1:]:
                hit = self.subdomains.get(s)
                if hit:
                    return hit
        for g in self.globs:
            if fnmatch.fnmatch(host, g):
                return g
        return None


class Scope:
    def __init__(self, patterns: Iterable[str], excludes: Iterable[str] = ()) -> None:
        self._include = _Matcher(patterns)
        self._exclude = _Matcher(excludes)
        if not self._include:
            raise ValueError("scope needs at least one pattern (use '*' to match all)")

    def match(self, host: str) -> str | None:
        """Return the pattern the host matched, or ``None`` if out of scope."""
        host = host.strip().lower().rstrip(".")
        if not host:
            return None
        if self._exclude.match(host) is not None:
            return None
        return self._include.match(host)
