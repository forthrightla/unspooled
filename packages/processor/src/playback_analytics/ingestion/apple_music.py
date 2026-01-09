"""Apple Music ingestion placeholder."""

from __future__ import annotations

import plistlib
from pathlib import Path
from typing import Any, Dict, List

from playback_analytics.config import Settings


class AppleMusicIngestor:
    """Parses Apple Music library XML exports (future support)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.library_xml = settings.ingestion.apple_music.library_xml_path

    def load_library(self) -> Dict[str, Any]:
        """Load the Apple Music library XML file if configured."""
        if not self.library_xml:
            raise FileNotFoundError("Apple Music library XML path is not configured.")
        path = Path(self.library_xml)
        with path.open("rb") as fh:
            return plistlib.load(fh)

    def extract_play_history(self) -> List[dict[str, Any]]:
        """Placeholder for extracting plays once XML format is defined."""
        _ = self.load_library()  # Load but don't process yet
        # Future implementation will map data["Tracks"] entries into raw plays.
        return []
