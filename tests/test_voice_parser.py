from bs4 import BeautifulSoup
import pytest

from bwiki.voice_parser import VoiceTableParseError, parse_voice_table, rendered_text


def test_rendered_text_preserves_inline_adjacency_and_br() -> None:
    soup = BeautifulSoup(
        '<p>（<a>甲</a>，<span>乙</span>）正文<br>第二行</p>', "lxml"
    )
    assert rendered_text(soup.p) == "（甲，乙）正文\n第二行"


def test_each_block_owns_its_own_text_and_audio() -> None:
    soup = BeautifulSoup(
        """
        <table><tr><th>主界面</th><td>
          <div class="ship_word_block" data-key="main" data-key-i="1">
            <p class="ship_word_line" data-lang="zh">文字 A</p>
            <div class="sm-audio-src"><a href="/A.mp3">A</a></div>
          </div>
          <div class="ship_word_block" data-key="main" data-key-i="2">
            <p class="ship_word_line" data-lang="zh">文字 B</p>
            <div class="sm-audio-src"><a href="/B.mp3">B</a></div>
          </div>
        </td></tr></table>
        """,
        "lxml",
    )
    voices = parse_voice_table(soup.table, "https://example.test/ship")
    assert [(item.text, item.audio_url) for item in voices] == [
        ("文字 A", "https://example.test/A.mp3"),
        ("文字 B", "https://example.test/B.mp3"),
    ]


def test_empty_optional_row_is_ignored() -> None:
    soup = BeautifulSoup(
        """
        <table>
          <tr data-key="drop_descrip"><th>舰船型号</th><td></td></tr>
          <tr><th>登录台词</th><td>
            <div class="ship_word_block">
              <p class="ship_word_line" data-lang="zh">欢迎回来</p>
            </div>
          </td></tr>
        </table>
        """,
        "lxml",
    )

    voices = parse_voice_table(soup.table, "https://example.test/ship")
    assert [voice.text for voice in voices] == ["欢迎回来"]


def test_nonempty_unwrapped_row_still_fails_strictly() -> None:
    soup = BeautifulSoup(
        "<table><tr><th>未知结构</th><td>不能静默丢弃</td></tr></table>",
        "lxml",
    )

    with pytest.raises(VoiceTableParseError, match="没有 ship_word_block"):
        parse_voice_table(soup.table, "https://example.test/ship")
