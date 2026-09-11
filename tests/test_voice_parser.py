from bs4 import BeautifulSoup

from bwiki.voice_parser import parse_voice_table, rendered_text


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

