from main import choose_suggestion, prompt_main_menu
from bwiki.models import ShipReference


def test_invalid_main_menu_input_keeps_prompting() -> None:
    answers = iter(["abc", "7", "1"])
    output: list[str] = []
    result = prompt_main_menu(lambda _prompt: next(answers), output.append)
    assert result == "1"
    assert output.count("无效选项，请输入 0、1 或 2。") == 2


def test_fuzzy_result_requires_explicit_selection() -> None:
    suggestions = [
        ShipReference("欧根亲王", "https://example.test/eugen"),
        ShipReference("小欧根", "https://example.test/little-eugen"),
    ]
    output: list[str] = []
    selected = choose_suggestion(
        "欧根", suggestions, lambda _prompt: "2", output.append
    )
    assert selected == suggestions[1]
    assert "未找到准确角色“欧根”。" in output
