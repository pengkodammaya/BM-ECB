"""Malaysian data source connectors: OpenDOSM, BNM, ARC."""

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.bnm import (
    fetch_interest_rate_history,
    fetch_exchange_rate_history,
)
from nowcasting_toolbox.data.sources.arc import ARCParser
from nowcasting_toolbox.data.sources.cache import DataCache

__all__ = [
    "OpenDOSMClient",
    "fetch_interest_rate_history",
    "fetch_exchange_rate_history",
    "ARCParser",
    "DataCache",
]
