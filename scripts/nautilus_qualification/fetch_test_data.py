"""Descarcă datele istorice folosite de exemplul oficial NautilusTrader de backtest.

Sursă: `tests/test_data/binance/ethusdt-trades.csv` din repo-ul oficial
nautechsystems/nautilus_trader, la commit-ul asociat tag-ului `v1.231.0`
(vezi PINNED_COMMIT). Fișierul e static (istoric, nu un feed live) și e
verificat prin sha256 după descărcare — nu e o conexiune către niciun broker.

Rulare: python -m scripts.nautilus_qualification.fetch_test_data
Rezultat: fișierul e scris în .cache/ (exclus din git) și reutilizat la
rulările ulterioare fără rețea, dacă hash-ul se potrivește deja.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

PINNED_COMMIT = "27a8e54e7ac3c57d6cbf8891f0283dfbaee97317"  # tag v1.231.0
SOURCE_URL = (
    f"https://raw.githubusercontent.com/nautechsystems/nautilus_trader/"
    f"{PINNED_COMMIT}/tests/test_data/binance/ethusdt-trades.csv"
)
EXPECTED_SHA256 = "a90fd7b0a83d32190258651eca7ecb0ecdcaf3deb54f73a17ce028bfe49fdd74"

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "nautilus_qualification" / "binance"
DEST_PATH = CACHE_DIR / "ethusdt-trades.csv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_test_data() -> Path:
    """Return the local path to the pinned test data, downloading it if absent/corrupt."""
    if DEST_PATH.exists() and _sha256(DEST_PATH) == EXPECTED_SHA256:
        return DEST_PATH

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:  # noqa: S310 (pinned raw.githubusercontent.com URL, static historical fixture)
        data = response.read()

    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        raise RuntimeError(
            f"Integritate compromisă pentru fixture-ul de calificare: "
            f"sha256 așteptat={EXPECTED_SHA256}, obținut={actual_sha256}",
        )

    DEST_PATH.write_bytes(data)
    return DEST_PATH


if __name__ == "__main__":
    path = fetch_test_data()
    print(f"Fixture disponibil local: {path} (sha256={_sha256(path)})")
