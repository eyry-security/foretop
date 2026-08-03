"""Where matched hosts go.

Three sinks, all sharing one tiny interface (:meth:`Sink.emit` /
:meth:`Sink.close`):

* :class:`StdoutSink` / :class:`FileSink` — write the full JSONL record, so the
  feed is useful on its own (``foretop ... | jq`` or ``-o hosts.jsonl``).
* :class:`RedisSink` — push the bare hostname onto a Redis list that Vedette pops
  with ``BRPOP``. This is the wiring between the two tools.

Multiple sinks can run at once (e.g. archive to a file *and* feed the queue).
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod

from .models import Host


class Sink(ABC):
    @abstractmethod
    async def emit(self, host: Host) -> None: ...

    async def close(self) -> None:  # optional override
        return None


class StdoutSink(Sink):
    async def emit(self, host: Host) -> None:
        sys.stdout.write(host.to_json() + "\n")
        sys.stdout.flush()


class FileSink(Sink):
    def __init__(self, path: str) -> None:
        self._fh = open(path, "a", encoding="utf-8")

    async def emit(self, host: Host) -> None:
        self._fh.write(host.to_json() + "\n")
        self._fh.flush()

    async def close(self) -> None:
        self._fh.close()


class RedisSink(Sink):
    """Push hostnames onto a Redis list for a prober to consume.

    With ``dedup`` on, a Redis SET remembers everything already pushed so a
    restart doesn't re-enqueue the same hosts. Vedette reads bare host strings,
    so that is exactly what we push.
    """

    def __init__(
        self,
        url: str,
        queue: str = "vedette:hosts",
        dedup: bool = True,
        seen_key: str = "foretop:seen",
    ) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "the redis sink needs redis-py: pip install 'foretop[redis]'"
            ) from exc
        self._client = aioredis.from_url(url, decode_responses=True)
        self.queue = queue
        self.dedup = dedup
        self.seen_key = seen_key

    async def emit(self, host: Host) -> None:
        if self.dedup:
            added = await self._client.sadd(self.seen_key, host.host)
            if not added:
                return
        await self._client.lpush(self.queue, host.host)

    async def close(self) -> None:
        await self._client.aclose()
