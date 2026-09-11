"""Parse the base and skin voice-set boundaries from one ship page."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from bs4 import BeautifulSoup, Tag

from .models import Ship, VoiceSet
from .selectors import (
    SHIP_PANEL_CLASS,
    SHIP_TABLE_SELECTOR,
    SKIN_CONTENT_CLASSES,
    SKIN_TAB_CLASSES,
    VOICE_SECTION_HEADING,
)
from .voice_parser import parse_voice_table, rendered_text


class ShipPageParseError(ValueError):
    """The page does not contain an unambiguous BWiki ship voice structure."""


def _direct_child_with_classes(
    parent: Tag, name: str, required_classes: frozenset[str]
) -> Tag | None:
    for child in parent.find_all(name, recursive=False):
        if required_classes.issubset(set(child.get("class", []))):
            return child
    return None


def _section_siblings(heading: Tag) -> Iterable[Tag]:
    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if sibling.name == "h2":
            return
        yield sibling


def _page_name(html: str) -> str | None:
    match = re.search(r'"wgPageName":"((?:\\.|[^"\\])*)"', html)
    if match is None:
        return None
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return match.group(1)


def _display_name(soup: BeautifulSoup) -> str | None:
    if soup.title is None:
        return None
    title = soup.title.get_text(strip=True)
    for suffix in (
        " - 碧蓝航线WIKI_BWIKI_哔哩哔哩",
        " - 碧蓝航线WIKI",
    ):
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title or None


def _one_table(container: Tag, context: str) -> Tag:
    tables = container.select(SHIP_TABLE_SELECTOR)
    if len(tables) != 1:
        raise ShipPageParseError(
            f"{context} 应包含 1 张语音表，实际找到 {len(tables)} 张"
        )
    return tables[0]


def _parse_skin_panel(panel: Tag, page_url: str) -> list[VoiceSet]:
    navigation = _direct_child_with_classes(panel, "ul", SKIN_TAB_CLASSES)
    content = _direct_child_with_classes(panel, "div", SKIN_CONTENT_CLASSES)
    if navigation is None or content is None:
        raise ShipPageParseError("皮肤面板缺少直接 nav-tabs 或 tab-content 子节点")

    headers: list[Tag] = []
    for item in navigation.find_all("li", recursive=False):
        header = item.find(attrs={"data-toggle": "tab", "data-target": True})
        if header is not None:
            headers.append(header)

    panes = [
        pane
        for pane in content.find_all("div", class_="tab-pane", recursive=False)
        if pane.select_one(SHIP_TABLE_SELECTOR) is not None
    ]
    if len(headers) != len(panes):
        raise ShipPageParseError(
            f"皮肤 Tab 与含语音表 Pane 数量不一致：{len(headers)} != {len(panes)}"
        )

    voice_sets: list[VoiceSet] = []
    seen_targets: set[str] = set()
    for header in headers:
        target = str(header["data-target"])
        if not target.startswith("#") or target in seen_targets:
            raise ShipPageParseError(f"皮肤 Tab data-target 无效或重复：{target}")
        seen_targets.add(target)
        pane = content.find("div", id=target[1:], recursive=False)
        if pane is None or "tab-pane" not in pane.get("class", []):
            raise ShipPageParseError(f"皮肤 Tab 找不到对应 Pane：{target}")
        name = rendered_text(header)
        if not name:
            raise ShipPageParseError(f"皮肤 Tab {target} 没有可用名称")
        voice_sets.append(
            VoiceSet(
                name=name,
                kind="skin",
                voices=parse_voice_table(_one_table(pane, name), page_url),
            )
        )
    return voice_sets


def parse_ship_page(html: str, page_url: str, expected_name: str | None = None) -> Ship:
    soup = BeautifulSoup(html, "lxml")
    headline = soup.select_one(VOICE_SECTION_HEADING)
    if headline is None:
        raise ShipPageParseError(f"未找到语音区标题：{VOICE_SECTION_HEADING}")
    heading = headline.find_parent("h2")
    if heading is None:
        raise ShipPageParseError("舰船台词标题不在 h2 内")

    panels = [
        node
        for node in _section_siblings(heading)
        if node.name == "div"
        and SHIP_PANEL_CLASS in node.get("class", [])
        and node.select_one(SHIP_TABLE_SELECTOR) is not None
    ]
    base_panels = [
        panel for panel in panels if _direct_child_with_classes(panel, "ul", SKIN_TAB_CLASSES) is None
    ]
    skin_panels = [
        panel for panel in panels if _direct_child_with_classes(panel, "ul", SKIN_TAB_CLASSES) is not None
    ]
    if len(base_panels) != 1:
        raise ShipPageParseError(f"本体语音面板应为 1 个，实际为 {len(base_panels)} 个")
    if len(skin_panels) > 1:
        raise ShipPageParseError(f"皮肤语音面板超过 1 个：{len(skin_panels)}")

    base_table = _one_table(base_panels[0], "本体")
    voice_sets = [
        VoiceSet(
            name="本体",
            kind="base",
            voices=parse_voice_table(base_table, page_url),
        )
    ]
    if skin_panels:
        voice_sets.extend(_parse_skin_panel(skin_panels[0], page_url))
    names = [voice_set.name for voice_set in voice_sets]
    if len(names) != len(set(names)):
        raise ShipPageParseError("同一舰娘页面出现重复语音集名称，拒绝静默覆盖")

    canonical_name = _page_name(html) or expected_name
    if not canonical_name:
        raise ShipPageParseError("无法识别舰娘规范页名")
    return Ship(
        name=canonical_name,
        display_name=_display_name(soup),
        page_url=page_url,
        voice_sets=tuple(voice_sets),
    )
