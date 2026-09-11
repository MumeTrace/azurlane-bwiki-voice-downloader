import asyncio
import json
import logging
from pathlib import Path

from bwiki.models import Ship, VoiceLine, VoiceSet
from downloader.audio import AudioDownloadResult
from downloader.manager import DownloadManager
from storage.paths import StorageLayout
from utils.logger import Reporter


MP3 = b"\xff\xfb\x90\x64" + (b"data" * 100)


class FakeDownloader:
    async def download(self, _url: str, destination: Path, *, force: bool = False):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(MP3)
        return AudioDownloadResult(status="success", size=len(MP3))


def test_manager_writes_text_metadata_and_duplicate_names(tmp_path: Path) -> None:
    ship = Ship(
        name="测试舰娘",
        display_name="测试舰娘",
        page_url="https://example.test/ship",
        voice_sets=(
            VoiceSet(
                name="本体",
                kind="base",
                voices=(
                    VoiceLine("主界面", "嗯？", "https://example.test/1.mp3", "main", "1"),
                    VoiceLine("主界面", "嗯？", "https://example.test/2.mp3", "main", "2"),
                    VoiceLine("触摸", "指挥官/你好？", "https://example.test/3.mp3", "touch", "1"),
                    VoiceLine("礼物台词", "谢谢", None, "gift", "1"),
                ),
            ),
        ),
    )
    logger = logging.getLogger("manager-test")
    logger.handlers[:] = [logging.NullHandler()]
    manager = DownloadManager(
        StorageLayout(tmp_path), FakeDownloader(), Reporter(logger)  # type: ignore[arg-type]
    )
    summary = asyncio.run(manager.download_ship(ship))
    assert summary.as_dict() == {
        "success": 3,
        "skipped": 0,
        "failed": 0,
        "no_audio": 1,
    }

    base = tmp_path / "voices" / "测试舰娘" / "本体"
    assert (base / "嗯？.mp3").exists()
    assert (base / "嗯？_2.mp3").exists()
    assert (base / "指挥官／你好？.txt").read_text(encoding="utf-8") == "指挥官/你好？"
    metadata = json.loads(
        (tmp_path / "voices" / "测试舰娘" / "metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["complete"] is True
    assert metadata["voice_sets"]["本体"][-1]["download_status"] == "no_audio"
    assert manager.is_ship_complete("测试舰娘") is True

