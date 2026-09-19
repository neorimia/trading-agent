"""Protocol-uri comune pentru asset discovery (design §1, §2) — o implementare per clasă de active.

`KrakenAssetUniverseProvider` (Faza 1) implementează ambele pentru crypto; un
`StockAssetUniverseProvider` (Faza 4) le va implementa separat, fără cod partajat forțat.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from src.discovery.models import DiscoveredInstrument, InstrumentSnapshot


class AssetUniverseProvider(Protocol):
    def discover(self) -> list[DiscoveredInstrument]: ...


class InstrumentMetadataProvider(Protocol):
    def snapshot(self, exchange_pairs: Sequence[str]) -> dict[str, InstrumentSnapshot]: ...
