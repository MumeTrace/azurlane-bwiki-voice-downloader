import json
from pathlib import Path

from storage.state import FailedStore, TaskStateStore


def test_corrupt_task_state_does_not_block_filesystem_recovery(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("{broken", encoding="utf-8")
    store = TaskStateStore(state_path)
    store.update_ship("欧根亲王", "downloading", page_url="https://example.test")
    value = json.loads(state_path.read_text(encoding="utf-8"))
    assert value["ships"]["欧根亲王"]["status"] == "downloading"


def test_resolved_failures_are_removed(tmp_path: Path) -> None:
    path = tmp_path / "failed.json"
    store = FailedStore(path)
    store.replace_ship_failures("欧根亲王", [{"error": "temporary"}])
    store.replace_ship_failures("欧根亲王", [])
    value = json.loads(path.read_text(encoding="utf-8"))
    assert "欧根亲王" not in value["ships"]
