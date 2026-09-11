"""Pure data models shared by the parser and downloader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ShipReference:
    name: str
    page_url: str
    page_id: int | None = None


@dataclass(frozen=True, slots=True)
class VoiceLine:
    category: str
    text: str
    audio_url: str | None
    data_key: str | None = None
    data_key_index: str | None = None
    ordinal: int = 1

    @property
    def source_key(self) -> str:
        key = self.data_key or self.category
        index = self.data_key_index or str(self.ordinal)
        return f"{key}:{index}"


@dataclass(frozen=True, slots=True)
class VoiceSet:
    name: str
    kind: Literal["base", "skin"]
    voices: tuple[VoiceLine, ...]


@dataclass(frozen=True, slots=True)
class Ship:
    name: str
    page_url: str
    voice_sets: tuple[VoiceSet, ...]
    display_name: str | None = None

    @property
    def base_voice_set(self) -> VoiceSet:
        for voice_set in self.voice_sets:
            if voice_set.kind == "base":
                return voice_set
        raise ValueError(f"舰娘 {self.name} 没有本体语音集")

    @property
    def skin_voice_sets(self) -> tuple[VoiceSet, ...]:
        return tuple(item for item in self.voice_sets if item.kind == "skin")

