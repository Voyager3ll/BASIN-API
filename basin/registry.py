"""In-memory registry of SWAT datasets, loaded once at startup.

Every subdirectory of BASIN_DATA_DIR that holds a dataset.json is loaded.
"""

from __future__ import annotations

import os
from pathlib import Path

from .swat.dataset import SwatDataset

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Registry:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir or os.environ.get("BASIN_DATA_DIR", DEFAULT_DATA_DIR))
        self.datasets: dict[str, SwatDataset] = {}

    def load(self) -> "Registry":
        for manifest in sorted(self.data_dir.glob("*/dataset.json")):
            ds = SwatDataset.load(manifest.parent)
            self.datasets[ds.name] = ds
        return self

    def get(self, name: str) -> SwatDataset:
        return self.datasets[name]
