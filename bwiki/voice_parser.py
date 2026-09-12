"""Parse one BWiki voice table into local, strictly paired voice objects."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import NavigableString, Tag

from .models import VoiceLine
from .selectors import (
    AUDIO_LINK_SELECTOR,
    VOICE_BLOCK_SELECTOR,
    VOICE_TEXT_FALLBACK_SELECTOR,
    VOICE_TEXT_SELECTOR,
)


class VoiceTableParseError(ValueError):
    """The voice table violates the local block structure expected by the parser."""


def rendered_text(node: Tag) -> str:
    """Extract rendered text without inserting spaces around inline tags.

    ``get_text(" ")`` corrupts lines such as linked easter-egg conditions by
    inserting spaces around every nested ``span`` and ``a``.  BWiki uses real
    ``br`` elements for intentional line breaks, so those are handled explicitly.
    """

    pieces: list[str] = []

    def visit(current: Tag | NavigableString) -> None:
        if isinstance(current, NavigableString):
            pieces.append(str(current))
            return
        if current.name == "br":
            pieces.append("\n")
            return
        if current.name in {"script", "style"}:
            return
        for child in current.children:
            if isinstance(child, (Tag, NavigableString)):
                visit(child)

    visit(node)
    text = "".join(pieces).replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _is_empty_optional_row(row: Tag) -> bool:
    """Return whether a row has category metadata but no payload to archive."""

    data_cells = row.find_all("td", recursive=False)
    if not data_cells:
        return False
    return all(
        not rendered_text(cell)
        and cell.select_one(".ship_word_block, [href], [src]") is None
        for cell in data_cells
    )


def parse_voice_table(table: Tag, page_url: str) -> tuple[VoiceLine, ...]:
    voices: list[VoiceLine] = []

    for row in table.find_all("tr"):
        if row.find_parent("table") is not table:
            continue
        category_cell = row.find("th", recursive=False)
        if category_cell is None:
            raise VoiceTableParseError("语音表中存在没有直接 th 类别单元的行")
        category = rendered_text(category_cell)
        blocks = row.select(VOICE_BLOCK_SELECTOR)
        if not blocks:
            if _is_empty_optional_row(row):
                continue
            raise VoiceTableParseError(f"类别“{category}”中没有 ship_word_block")

        for ordinal, block in enumerate(blocks, start=1):
            line = block.select_one(VOICE_TEXT_SELECTOR)
            if line is None:
                line = block.select_one(VOICE_TEXT_FALLBACK_SELECTOR)
            if line is None:
                raise VoiceTableParseError(
                    f"类别“{category}”第 {ordinal} 个语音块没有 ship_word_line"
                )

            audio_links = block.select(AUDIO_LINK_SELECTOR)
            if len(audio_links) > 1:
                raise VoiceTableParseError(
                    f"类别“{category}”第 {ordinal} 个语音块包含多个 MP3，无法安全配对"
                )

            href = str(audio_links[0]["href"]).strip() if audio_links else None
            voices.append(
                VoiceLine(
                    category=category,
                    text=rendered_text(line),
                    audio_url=urljoin(page_url, href) if href else None,
                    data_key=block.get("data-key"),
                    data_key_index=block.get("data-key-i"),
                    ordinal=ordinal,
                )
            )

    if not voices:
        raise VoiceTableParseError("语音表中没有可解析的 ship_word_block")
    return tuple(voices)
