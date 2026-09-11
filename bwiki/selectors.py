"""Selectors observed from live BWiki HTML on 2026-09-11."""

VOICE_SECTION_HEADING = "h2 > span.mw-headline#舰船台词"
SHIP_TABLE_CLASS = "table-ShipWordsTable"
SHIP_TABLE_SELECTOR = f"table.{SHIP_TABLE_CLASS}"
VOICE_BLOCK_SELECTOR = ".ship_word_block"
VOICE_TEXT_SELECTOR = ".ship_word_line[data-lang='zh']"
VOICE_TEXT_FALLBACK_SELECTOR = ".ship_word_line"
AUDIO_LINK_SELECTOR = ".sm-audio-src a[href]"
SKIN_TAB_CLASSES = frozenset({"nav", "nav-tabs"})
SKIN_CONTENT_CLASSES = frozenset({"tab-content"})
SHIP_PANEL_CLASS = "panel-shiptable"

