"""Inspect the live BWiki voice DOM without downloading audio files.

This is deliberately a Phase 1 diagnostic, not the production parser.  It
anchors all inspection to the real ``舰船台词`` section and validates the
local text/audio relationship inside each ``ship_word_block``.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx
from bs4 import BeautifulSoup, Tag


DEFAULT_URL = "https://wiki.biligame.com/blhx/%E6%AC%A7%E6%A0%B9%E4%BA%B2%E7%8E%8B"
USER_AGENT = (
    "azurlane-bwiki-voice-downloader/0.1 "
    "(Phase 1 DOM research; local archival tool)"
)


class DomInspectionError(RuntimeError):
    """Raised when the live page no longer satisfies an observed invariant."""


@dataclass(frozen=True, slots=True)
class VoiceBlockEvidence:
    category: str
    text: str
    audio_url: str | None
    data_key: str | None
    data_key_index: str | None


@dataclass(frozen=True, slots=True)
class VoiceSetEvidence:
    name: str
    target: str | None
    rows: int
    voices: tuple[VoiceBlockEvidence, ...]

    @property
    def audio_count(self) -> int:
        return sum(voice.audio_url is not None for voice in self.voices)


def fetch_html(url: str) -> tuple[str, str]:
    """Fetch one HTML page; production retries intentionally belong to Phase 5."""

    with httpx.Client(
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30.0),
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text, str(response.url)


def write_fixture_atomic(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(html, encoding="utf-8", newline="")
    temporary.replace(path)


def direct_child_with_classes(
    parent: Tag, tag_name: str, required_classes: set[str]
) -> Tag | None:
    for child in parent.find_all(tag_name, recursive=False):
        if required_classes.issubset(set(child.get("class", []))):
            return child
    return None


def iter_section_siblings(heading: Tag) -> Iterable[Tag]:
    """Yield nodes in one h2 section, stopping before the next h2."""

    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if sibling.name == "h2":
            return
        yield sibling


def find_voice_section(soup: BeautifulSoup) -> tuple[Tag, Tag]:
    # The page currently contains duplicate id="舰船台词" values.  Restricting
    # the selector to the h2 headline avoids accidentally selecting an inner a.
    headline = soup.select_one("h2 > span.mw-headline#舰船台词")
    if headline is None:
        raise DomInspectionError("未找到 h2 > span.mw-headline#舰船台词")

    heading = headline.find_parent("h2")
    if heading is None:
        raise DomInspectionError("舰船台词标题不在 h2 中")

    panels = [
        node
        for node in iter_section_siblings(heading)
        if node.name == "div" and "panel-shiptable" in node.get("class", [])
    ]
    base_panels = [panel for panel in panels if panel.select_one("ul.nav-tabs") is None]
    skin_panels = [panel for panel in panels if panel.select_one("ul.nav-tabs") is not None]

    if len(base_panels) != 1 or len(skin_panels) != 1:
        raise DomInspectionError(
            "舰船台词区面板数量异常："
            f"本体候选={len(base_panels)}，皮肤候选={len(skin_panels)}"
        )
    return base_panels[0], skin_panels[0]


def find_voice_table(container: Tag) -> Tag:
    tables = container.select("table.table-ShipWordsTable")
    if len(tables) != 1:
        raise DomInspectionError(f"语音容器中应有 1 张表，实际为 {len(tables)} 张")
    return tables[0]


def extract_text(line: Tag) -> str:
    """Preserve inline-node adjacency instead of injecting separator spaces."""

    return "".join(line.strings).strip()


def inspect_table(name: str, target: str | None, table: Tag) -> VoiceSetEvidence:
    rows = table.find_all("tr")
    voices: list[VoiceBlockEvidence] = []

    for row in rows:
        category_cell = row.find("th", recursive=False)
        if category_cell is None:
            raise DomInspectionError(f"{name} 中存在没有直接 th 类别单元的行")
        category = extract_text(category_cell)

        blocks = row.select(".ship_word_block")
        if not blocks:
            raise DomInspectionError(f"{name}/{category} 中没有 ship_word_block")

        for block in blocks:
            line = block.select_one(".ship_word_line[data-lang='zh']")
            if line is None:
                line = block.select_one(".ship_word_line")
            if line is None:
                raise DomInspectionError(f"{name}/{category} 中存在没有台词节点的语音块")

            audio_links = block.select(".sm-audio-src a[href]")
            if len(audio_links) > 1:
                raise DomInspectionError(
                    f"{name}/{category} 的单个语音块内发现 {len(audio_links)} 个音频链接"
                )

            voices.append(
                VoiceBlockEvidence(
                    category=category,
                    text=extract_text(line),
                    audio_url=audio_links[0]["href"] if audio_links else None,
                    data_key=block.get("data-key"),
                    data_key_index=block.get("data-key-i"),
                )
            )

    return VoiceSetEvidence(
        name=name,
        target=target,
        rows=len(rows),
        voices=tuple(voices),
    )


def inspect_document(html: str) -> tuple[BeautifulSoup, list[VoiceSetEvidence]]:
    soup = BeautifulSoup(html, "lxml")
    base_panel, skin_panel = find_voice_section(soup)
    results = [inspect_table("本体", None, find_voice_table(base_panel))]

    navigation = direct_child_with_classes(skin_panel, "ul", {"nav", "nav-tabs"})
    content = direct_child_with_classes(skin_panel, "div", {"tab-content"})
    if navigation is None or content is None:
        raise DomInspectionError("皮肤面板缺少直接 nav-tabs 或 tab-content 子节点")

    headers: list[Tag] = []
    for item in navigation.find_all("li", recursive=False):
        header = item.find(attrs={"data-toggle": "tab", "data-target": True})
        if header is not None:
            headers.append(header)

    panes = content.find_all("div", class_="tab-pane", recursive=False)
    if len(headers) != len(panes):
        raise DomInspectionError(
            f"皮肤 Tab 与 Pane 数量不一致：Tab={len(headers)}，Pane={len(panes)}"
        )

    for header in headers:
        target = str(header["data-target"])
        if not target.startswith("#"):
            raise DomInspectionError(f"皮肤 Tab data-target 不是 id selector：{target}")
        pane = content.find("div", id=target[1:], recursive=False)
        if pane is None or "tab-pane" not in pane.get("class", []):
            raise DomInspectionError(f"皮肤 Tab 找不到对应 Pane：{target}")
        name = extract_text(header)
        results.append(inspect_table(name, target, find_voice_table(pane)))

    return soup, results


def mediawiki_page_name(html: str) -> str | None:
    match = re.search(r'"wgPageName":"([^"]+)"', html)
    return match.group(1) if match else None


def print_report(
    source_url: str, html: str, soup: BeautifulSoup, voice_sets: list[VoiceSetEvidence]
) -> None:
    print(f"实际页面 URL：{source_url}")
    print(f"MediaWiki 页名：{mediawiki_page_name(html) or '未识别'}")
    print(f"HTML title：{soup.title.get_text(strip=True) if soup.title else '未识别'}")
    print(
        "原始 HTML 媒体节点："
        f"audio={len(soup.find_all('audio'))}，"
        f"source={len(soup.find_all('source'))}，"
        f".sm-audio-src={len(soup.select('.sm-audio-src a[href]'))}"
    )
    print()

    for voice_set in voice_sets:
        mapping = f" -> {voice_set.target}" if voice_set.target else ""
        missing = len(voice_set.voices) - voice_set.audio_count
        print(
            f"[{voice_set.name}]{mapping}："
            f"行={voice_set.rows}，语音块={len(voice_set.voices)}，"
            f"MP3={voice_set.audio_count}，无 MP3={missing}"
        )

    print()
    base = voice_sets[0]
    multi_categories: dict[str, int] = {}
    for voice in base.voices:
        multi_categories[voice.category] = multi_categories.get(voice.category, 0) + 1
    print("本体中含多个局部语音块的类别：")
    for category, count in multi_categories.items():
        if count > 1:
            print(f"  {category}：{count} 条")
            for voice in (item for item in base.voices if item.category == category):
                print(f"    [{voice.data_key}/{voice.data_key_index}] {voice.text}")
                print(f"      {voice.audio_url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="调查 BWiki 舰船台词的真实 DOM")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--html", type=Path, help="读取已保存的 HTML，不访问网络")
    source.add_argument("--url", default=DEFAULT_URL, help="要调查的 BWiki 页面 URL")
    parser.add_argument("--save-fixture", type=Path, help="原子保存抓取到的原始 HTML")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.html is not None:
        html = args.html.read_text(encoding="utf-8")
        source_url = args.html.resolve().as_uri()
    else:
        html, source_url = fetch_html(args.url)
        if args.save_fixture is not None:
            write_fixture_atomic(args.save_fixture, html)
            print(f"已保存 fixture：{args.save_fixture.resolve()}")

    soup, voice_sets = inspect_document(html)
    print_report(source_url, html, soup, voice_sets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

