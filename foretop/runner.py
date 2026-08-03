"""The pump: source → scope filter → dedup → sinks.

Keeps the moving parts dumb. The source only knows how to produce hosts; the
sinks only know how to write them. Everything in between — deciding what's in
scope, not emitting the same host twice, counting, stopping — lives here.
"""

from __future__ import annotations

import sys
from collections import deque
from collections.abc import Sequence

from .models import Host
from .scope import Scope
from .sinks import Sink
from .sources.base import Source


class Runner:
    def __init__(
        self,
        source: Source,
        scope: Scope,
        sinks: Sequence[Sink],
        max_items: int | None = None,
        dedup_cap: int = 200_000,
        quiet: bool = False,
        progress_every: int = 100,
    ) -> None:
        self.source = source
        self.scope = scope
        self.sinks = list(sinks)
        self.max_items = max_items
        self.dedup_cap = dedup_cap
        self.quiet = quiet
        self.progress_every = progress_every
        self.emitted = 0
        self.seen_total = 0

    def _log(self, msg: str) -> None:
        if not self.quiet:
            print(f"[foretop] {msg}", file=sys.stderr, flush=True)

    async def run(self) -> int:
        seen: set[str] = set()
        order: deque[str] = deque()
        try:
            async for host in self.source.candidates():
                self.seen_total += 1
                matched = self.scope.match(host.host)
                if matched is None:
                    continue
                if host.host in seen:
                    continue
                seen.add(host.host)
                order.append(host.host)
                if len(order) > self.dedup_cap:
                    seen.discard(order.popleft())

                host.scope = matched
                for sink in self.sinks:
                    await sink.emit(host)
                self.emitted += 1

                if not self.quiet and self.emitted % self.progress_every == 0:
                    self._log(
                        f"{self.emitted} in-scope hosts "
                        f"(seen {self.seen_total} candidates)"
                    )
                if self.max_items is not None and self.emitted >= self.max_items:
                    self._log(f"reached --max {self.max_items}, stopping")
                    break
        finally:
            for sink in self.sinks:
                await sink.close()
        return self.emitted
