"""Scope matching.

A scope is a set of patterns that decide which hosts are in bounds. Two styles:

* **domain** — ``example.com`` matches ``example.com`` and any subdomain of it
  (``api.example.com``, ``a.b.example.com``). This is the usual bug-bounty scope.
* **glob** — anything containing ``*``, ``?`` or ``[``; ``*.example.com`` matches
  subdomains only and ``*`` matches everything. Wildcards are label-scoped (they
  don't cross dots), so ``*53.com`` matches ``3g53.com`` but not ``x.y.53.com``.

Excludes are checked first and win over includes.

This is built to hold *large* scope sets (tens of thousands of bug-bounty
wildcards) cheaply. The two common shapes — a plain domain and ``*.domain`` —
are indexed by suffix so a host is matched in O(number of labels) via set
lookups instead of scanning every pattern. Only exotic globs (``*dev*.x.com``)
fall back to per-pattern ``fnmatch``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_GLOB_CHARS = set("*?[")


def _is_glob(pattern: str) -> bool:
    return any(c in _GLOB_CHARS for c in pattern)


def _glob_to_regex(pattern: str) -> "re.Pattern[str]":
    """Compile a hostname glob so ``*`` and ``?`` stay within a single DNS label.

    This is stricter than shell ``fnmatch``: a scope of ``*53.com`` matches
    ``3g53.com`` but not ``www.299853.com``, since a wildcard shouldn't swallow
    dots and pull in arbitrary subdomains.
    """
    out = []
    for ch in pattern:
        if ch == "*":
            out.append("[^.]*")
        elif ch == "?":
            out.append("[^.]")
        else:
            out.append(re.escape(ch))
    return re.compile("^" + "".join(out) + "$")


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
        self.globs: list[tuple] = []           # (compiled regex, pattern), label-anchored

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
                self.globs.append((_glob_to_regex(p), p))

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
        for rx, pat in self.globs:
            if rx.match(host):
                return pat
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
