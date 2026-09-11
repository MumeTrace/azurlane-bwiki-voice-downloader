from utils.filename import safe_component, unique_stem


def test_windows_illegal_characters_use_fullwidth_equivalents() -> None:
    original = '<>:\"/\\|?*'
    assert safe_component(original) == "＜＞：＂／＼｜？＊"


def test_trailing_space_dot_and_reserved_names_are_safe() -> None:
    assert safe_component("台词.  ") == "台词"
    assert safe_component("CON") == "_CON"
    assert safe_component("lpt9.anything") == "_lpt9.anything"


def test_long_name_is_deterministic_and_hashed() -> None:
    original = "很长的台词" * 50
    first = safe_component(original, max_length=100)
    second = safe_component(original, max_length=100)
    assert first == second
    assert len(first) <= 100
    assert len(first.rsplit("_", 1)[-1]) == 8


def test_duplicate_names_get_incrementing_suffixes_case_insensitively() -> None:
    used: set[str] = set()
    assert unique_stem("嗯？", used) == "嗯？"
    assert unique_stem("嗯？", used) == "嗯？_2"
    assert unique_stem("ABC", used) == "ABC"
    assert unique_stem("abc", used) == "abc_2"

