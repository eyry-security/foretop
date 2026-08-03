"""The record Foretop emits. One host, with provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Host:
    """A single hostname spotted by a source.

    Only ``host`` flows downstream to a prober; the rest is provenance that
    rides along in the standalone JSONL output.
    """

    host: str
    source: str
    scope: str | None = None
    seen_at: str = field(default_factory=_now)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "host": self.host,
            "source": self.source,
            "scope": self.scope,
            "seen_at": self.seen_at,
        }
        if self.meta:
            d["meta"] = self.meta
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)
