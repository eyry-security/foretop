"""certstream source — new hosts from Certificate Transparency logs.

Every TLS certificate issued by a public CA is published to CT logs. Certstream
aggregates those logs into one websocket firehose, so the moment someone gets a
cert for ``new-thing.example.com`` it shows up here — often before DNS or the
service is fully live. That makes it a great early-warning feed for a scope.

This talks to any certstream-compatible websocket server. The old public
Calidog firehose is effectively dead, so the default points at a locally
self-hosted server — run certstream-server-rust or certstream-server-go (a
single binary or one ``docker run``) and Foretop connects to it. Point it
elsewhere with ``--certstream-url``.

The wire format is a JSON ``certificate_update`` message with
``data.leaf_cert.all_domains``; we pull the names out of each one.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Iterator

import websockets

from ..models import Host
from .base import Source

# A locally self-hosted certstream server (certstream-server-rust / -go).
# See the README for the one-line Docker command to start one.
DEFAULT_URL = "ws://localhost:8080/"


def parse_message(raw: str | bytes, include_wildcards: bool = True) -> Iterator[Host]:
    """Turn one raw certstream frame into :class:`Host` records.

    Pure and side-effect free so it can be exercised without a live socket.
    Wildcard names (``*.example.com``) are flattened to their base domain when
    ``include_wildcards`` is set, since that base is a real host worth probing.
    """
    try:
        msg = json.loads(raw)
    except (ValueError, TypeError):
        return
    if msg.get("message_type") != "certificate_update":
        return

    leaf = (msg.get("data") or {}).get("leaf_cert") or {}
    domains = leaf.get("all_domains") or []
    issuer = (leaf.get("issuer") or {}).get("O")
    src = ((msg.get("data") or {}).get("source") or {}).get("name")

    emitted: set[str] = set()
    for name in domains:
        if not isinstance(name, str):
            continue
        host = name.strip().lower().rstrip(".")
        if not host:
            continue
        if host.startswith("*."):
            if not include_wildcards:
                continue
            host = host[2:]
        if not host or host in emitted:
            continue
        emitted.add(host)
        meta = {}
        if issuer:
            meta["issuer"] = issuer
        if src:
            meta["ct_log"] = src
        yield Host(host=host, source="certstream", meta=meta)


class CertstreamSource(Source):
    name = "certstream"

    def __init__(
        self,
        url: str = DEFAULT_URL,
        include_wildcards: bool = True,
        reconnect_delay: float = 5.0,
        quiet: bool = False,
        **opts,
    ) -> None:
        super().__init__(**opts)
        self.url = url
        self.include_wildcards = include_wildcards
        self.reconnect_delay = reconnect_delay
        self.quiet = quiet

    def _log(self, msg: str) -> None:
        if not self.quiet:
            print(f"[foretop:certstream] {msg}", file=sys.stderr, flush=True)

    async def candidates(self) -> AsyncIterator[Host]:
        while True:
            try:
                self._log(f"connecting to {self.url}")
                async with websockets.connect(
                    self.url,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=None,
                    open_timeout=30,
                ) as ws:
                    self._log("connected, streaming certificates")
                    async for raw in ws:
                        for host in parse_message(raw, self.include_wildcards):
                            yield host
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep the feed alive
                self._log(f"connection dropped ({exc!s}); reconnecting in {self.reconnect_delay}s")
                await asyncio.sleep(self.reconnect_delay)
