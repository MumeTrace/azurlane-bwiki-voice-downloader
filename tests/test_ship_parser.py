from pathlib import Path

import pytest

from bwiki.ship_parser import ShipPageParseError, parse_ship_page


FIXTURES = Path(__file__).parent / "fixtures"


def load_ship(filename: str):
    html = (FIXTURES / filename).read_text(encoding="utf-8")
    return parse_ship_page(html, f"https://example.test/{filename}")


def test_prinz_eugen_base_skins_and_local_pairing() -> None:
    ship = load_ship("prinz_eugen.html")

    assert ship.name == "欧根亲王"
    assert ship.display_name == "萨沃伊亲王"
    assert len(ship.voice_sets) == 9
    assert len(ship.base_voice_set.voices) == 33
    assert sum(v.audio_url is not None for v in ship.base_voice_set.voices) == 29
    assert [item.name for item in ship.skin_voice_sets] == [
        "永不褪色的笑容",
        "百花缭乱",
        "【誓约】命运交响曲",
        "Wein Kornblume",
        "Final Lap",
        "沉醉于夜",
        "闪耀达阵！",
        "微醺与试探的距离",
    ]

    main_lines = [
        voice for voice in ship.base_voice_set.voices if voice.category == "主界面"
    ]
    assert len(main_lines) == 3
    assert main_lines[0].text == "工作不要太过度哦~不然的话……会——死——的"
    assert main_lines[0].audio_url == (
        "https://patchwiki.biligame.com/images/blhx/4/47/"
        "mgive3n9hnlfuins8wsgx59zljxiaoi.mp3"
    )
    assert len({voice.audio_url for voice in main_lines}) == 3


def test_nested_easter_egg_text_does_not_gain_spaces() -> None:
    ship = load_ship("prinz_eugen.html")
    easter_eggs = [
        voice for voice in ship.base_voice_set.voices if voice.category == "彩蛋台词"
    ]
    assert easter_eggs[0].text == "（格里德利，莫里）呵，白鹰记者跑的也挺快嘛……"
    assert easter_eggs[-1].text == "（阿鸡分队2只）阿鸡队……算了，陪陪你们"
    assert easter_eggs[-1].audio_url is None


def test_oath_skin_does_not_need_description_category() -> None:
    ship = load_ship("prinz_eugen.html")
    oath = next(item for item in ship.skin_voice_sets if item.name.startswith("【誓约】"))
    assert oath.voices[0].category == "获取台词"
    assert all(voice.category != "皮肤描述" for voice in oath.voices)


@pytest.mark.parametrize(
    ("filename", "expected_name", "expected_display", "minimum_sets"),
    [
        ("javelin.html", "标枪", "标枪", 10),
        ("admiral_zenker.html", "曾克海军上将", "泽特", 2),
    ],
)
def test_additional_real_pages(
    filename: str, expected_name: str, expected_display: str, minimum_sets: int
) -> None:
    ship = load_ship(filename)
    assert ship.name == expected_name
    assert ship.display_name == expected_display
    assert len(ship.voice_sets) >= minimum_sets
    assert all(voice_set.voices for voice_set in ship.voice_sets)


def test_javelin_has_missing_audio_inside_a_skin() -> None:
    ship = load_ship("javelin.html")
    assert any(
        voice.audio_url is None
        for voice_set in ship.skin_voice_sets
        for voice in voice_set.voices
    )


def test_missing_voice_section_fails_instead_of_guessing() -> None:
    with pytest.raises(ShipPageParseError, match="未找到语音区标题"):
        parse_ship_page("<html><title>普通页面</title></html>", "https://example.test")
