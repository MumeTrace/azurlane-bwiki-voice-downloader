from io import BytesIO, TextIOWrapper

from utils.console import configure_console_output


def test_unsupported_console_character_does_not_raise() -> None:
    buffer = BytesIO()
    stream = TextIOWrapper(buffer, encoding="gbk", errors="strict")

    configure_console_output((stream,))
    stream.write("皮肤♪")
    stream.flush()

    assert buffer.getvalue().decode("gbk") == "皮肤?"
