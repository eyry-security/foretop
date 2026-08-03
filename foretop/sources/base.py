"""The source plugin interface.

A source is anything that produces a stream of candidate hosts. It knows nothing
about scope, dedup, or where the hosts go — it just yields :class:`Host` records
as fast as it can. The runner does the filtering and fan-out.

To add a source: subclass :class:`Source`, set a ``name``, implement
``candidates()`` as an async generator, and register it in ``sources/__init__.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ..models import Host


class Source(ABC):
    #: short identifier used on the CLI (``--source <name>``)
    name: str = "source"

    def __init__(self, **opts) -> None:
        self.opts = opts

    @abstractmethod
    async def candidates(self) -> AsyncIterator[Host]:
        """Yield candidate hosts forever (or until the stream ends).

        Implementations should be resilient: reconnect on transient network
        errors rather than raising, so a long-running feed stays up.
        """
        raise NotImplementedError
        yield  # pragma: no cover  (marks this as an async generator)
