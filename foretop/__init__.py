"""Foretop — a pluggable live feed of new hosts for your scope.

The lookout aloft of the Eyry recon suite: it watches a source (certstream
first), keeps only the hosts inside your scope, and hands them off — to stdout,
a file, or straight into a Redis queue for Vedette to probe.
"""

from .models import Host
from .scope import Scope

__version__ = "0.1.0"
__all__ = ["Host", "Scope", "__version__"]
