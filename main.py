"""Interactive CLI entry point for the BWiki voice downloader."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

from bwiki.client import BWikiClient
from bwiki.models import Ship, ShipReference
from bwiki.ship_index import ShipIndex
from bwiki.ship_parser import parse_ship_page
from downloader.audio import AudioDownloader
from downloader.manager import DownloadManager, DownloadSummary
from storage.paths import StorageLayout
from storage.state import FailedStore, TaskStateStore
from utils.logger import Reporter, configure_logging


PAGE_CONCURRENCY = 4
DOWNLOAD_CONCURRENCY = 8


def prompt_main_menu(
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str:
    output_fn("========================================")
    output_fn("     碧蓝航线 BWiki 语音下载工具")
    output_fn("========================================")
    output_fn("")
    output_fn("请选择操作：")
    output_fn("")
    output_fn("[1] 下载指定舰娘")
    output_fn("[2] 下载全部舰娘")
    output_fn("[0] 退出")
    output_fn("")
    while True:
        choice = input_fn("请输入选项：").strip()
        if choice in {"0", "1", "2"}:
            return choice
        output_fn("无效选项，请输入 0、1 或 2。")


def choose_suggestion(
    requested: str,
    suggestions: Sequence[ShipReference],
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> ShipReference | None:
    if not suggestions:
        output_fn(f"未找到舰娘“{requested}”。")
        output_fn("请检查名称后重新输入。")
        return None
    output_fn(f"未找到准确角色“{requested}”。")
    output_fn("")
    output_fn("是否是：")
    output_fn("")
    for index, ship in enumerate(suggestions, start=1):
        output_fn(f"{index}. {ship.name}")
    output_fn("0. 返回")
    while True:
        choice = input_fn("请输入选项：").strip()
        if choice == "0":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(suggestions):
            return suggestions[int(choice) - 1]
        output_fn(f"无效选项，请输入 0～{len(suggestions)}。")


class VoiceDownloaderApplication:
    def __init__(self, project_root: Path) -> None:
        self.layout = StorageLayout(project_root)
        self.layout.ensure_roots()
        self.reporter = Reporter(configure_logging(self.layout.logs_root))
        self.state_store = TaskStateStore(self.layout.task_state_path)
        self.failed_store = FailedStore(self.layout.failed_path)

    async def run(self) -> None:
        async with BWikiClient(
            page_concurrency=PAGE_CONCURRENCY,
            on_retry=self.reporter.warning,
        ) as client, AudioDownloader(
            concurrency=DOWNLOAD_CONCURRENCY,
            on_retry=self.reporter.warning,
        ) as audio_downloader:
            index = ShipIndex(client)
            manager = DownloadManager(
                self.layout, audio_downloader, self.reporter
            )
            while True:
                choice = prompt_main_menu()
                if choice == "0":
                    print("正在退出……")
                    return
                if choice == "1":
                    await self._download_one(index, client, manager)
                elif choice == "2":
                    await self._download_all(index, client, manager)
                print()

    async def _select_ship(self, index: ShipIndex) -> ShipReference | None:
        while True:
            requested = input("请输入舰娘名称（输入 0 返回）：").strip()
            if requested == "0":
                return None
            if not requested:
                print("舰娘名称不能为空。")
                continue
            print("正在获取 BWiki 舰娘列表……")
            exact = await index.find_exact(requested)
            if exact is not None:
                return exact
            suggestions = await index.suggest(requested)
            return choose_suggestion(requested, suggestions)

    async def _parse_ship(
        self, client: BWikiClient, reference: ShipReference
    ) -> Ship:
        html, final_url = await client.get_text(reference.page_url)
        return parse_ship_page(html, final_url, expected_name=reference.name)

    def _show_parse_result(self, ship: Ship) -> None:
        print(f"已找到舰娘：{ship.name}")
        if ship.display_name and ship.display_name != ship.name:
            print(f"BWiki 当前展示名：{ship.display_name}")
        print()
        print("正在解析页面……")
        print()
        print("本体语音：已发现")
        print(f"皮肤数量：{len(ship.skin_voice_sets)}")
        if ship.skin_voice_sets:
            print()
            print("皮肤：")
            for index, voice_set in enumerate(ship.skin_voice_sets, start=1):
                print(f"  {index}. {voice_set.name}")
        print()
        for voice_set in ship.voice_sets:
            audio_count = sum(
                voice.audio_url is not None for voice in voice_set.voices
            )
            print(
                f"[解析] {voice_set.name}：发现 {len(voice_set.voices)} 条，"
                f"其中 {audio_count} 条有 MP3"
            )

    @staticmethod
    def _show_summary(summary: DownloadSummary) -> None:
        print()
        print("下载完成：")
        print()
        print(f"成功：{summary.success}")
        print(f"跳过：{summary.skipped}")
        print(f"失败：{summary.failed}")
        print(f"无音频记录：{summary.no_audio}")

    async def _download_one(
        self,
        index: ShipIndex,
        client: BWikiClient,
        manager: DownloadManager,
    ) -> None:
        try:
            reference = await self._select_ship(index)
            if reference is None:
                return
            ship = await self._parse_ship(client, reference)
            self._show_parse_result(ship)
            print()
            print("开始下载……")
            self.state_store.update_ship(
                ship.name, "downloading", page_url=ship.page_url
            )
            summary = await manager.download_ship(ship)
            status = "complete" if summary.failed == 0 else "partial"
            self.state_store.update_ship(
                ship.name,
                status,
                page_url=ship.page_url,
                summary=summary.as_dict(),
            )
            self._show_summary(summary)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.reporter.error(f"处理舰娘失败：{type(exc).__name__}: {exc}")

    async def _download_all(
        self,
        index: ShipIndex,
        client: BWikiClient,
        manager: DownloadManager,
    ) -> None:
        print("正在获取 BWiki 舰娘列表……")
        try:
            ships = await index.fetch_all(refresh=True)
        except Exception as exc:
            self.reporter.error(f"获取舰娘列表失败：{type(exc).__name__}: {exc}")
            return
        print(f"共发现 {len(ships)} 名舰娘。")
        self.state_store.begin_all(len(ships))

        async def process(position: int, reference: ShipReference) -> None:
            print()
            print(f"当前舰娘：{position} / {len(ships)}")
            print(reference.name)
            if manager.is_ship_complete(reference.name):
                print(f"[跳过] {reference.name} 已完整下载")
                self.state_store.update_ship(
                    reference.name, "complete", page_url=reference.page_url
                )
                return
            self.state_store.update_ship(
                reference.name, "parsing", page_url=reference.page_url
            )
            try:
                ship = await self._parse_ship(client, reference)
                self.state_store.update_ship(
                    reference.name, "downloading", page_url=ship.page_url
                )
                summary = await manager.download_ship(ship)
                status = "complete" if summary.failed == 0 else "partial"
                self.state_store.update_ship(
                    reference.name,
                    status,
                    page_url=ship.page_url,
                    summary=summary.as_dict(),
                )
                print(
                    f"[舰娘完成] {reference.name}：成功 {summary.success}，"
                    f"跳过 {summary.skipped}，失败 {summary.failed}"
                )
            except asyncio.CancelledError:
                self.state_store.update_ship(
                    reference.name, "interrupted", page_url=reference.page_url
                )
                raise
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                self.reporter.error(f"[舰娘失败] {reference.name}：{message}")
                self.state_store.update_ship(
                    reference.name,
                    "failed",
                    page_url=reference.page_url,
                    error=message,
                )
                self.failed_store.replace_ship_failures(
                    reference.name,
                    [
                        {
                            "stage": "page_or_parse",
                            "url": reference.page_url,
                            "error": message,
                        }
                    ],
                )

        batch_size = PAGE_CONCURRENCY
        try:
            for start in range(0, len(ships), batch_size):
                batch = ships[start : start + batch_size]
                await asyncio.gather(
                    *(
                        process(start + offset + 1, reference)
                        for offset, reference in enumerate(batch)
                    )
                )
        except asyncio.CancelledError:
            raise


async def async_main() -> None:
    project_root = Path(__file__).resolve().parent
    application = VoiceDownloaderApplication(project_root)
    await application.run()


def main() -> int:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print()
        print("收到中断信号。")
        print("正在保存当前下载状态……")
        print("状态保存完成。")
        print("下次启动程序后可以继续未完成任务。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
