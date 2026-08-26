from agents.capabilities.content import REEL_FRAME_WIDTH, TEXT_SAFE_MARGIN, _wrap_for_drawtext


def test_short_text_stays_on_one_line():
    result = _wrap_for_drawtext("Hook corto", fontsize=52)
    assert "\n" not in result
    assert result == "Hook corto"


def test_empty_text_returns_empty():
    assert _wrap_for_drawtext("", fontsize=40) == ""


def test_long_text_wraps_into_multiple_lines():
    long_body = "528 Hz es la frecuencia que dicen que repara el ADN del alma y nos invita a recordar quiénes somos"
    result = _wrap_for_drawtext(long_body, fontsize=38)
    assert "\n" in result
    lines = result.split("\n")
    usable_width = REEL_FRAME_WIDTH - 2 * TEXT_SAFE_MARGIN
    avg_char_width = 38 * 0.58
    max_chars = int(usable_width / avg_char_width)
    for line in lines:
        assert len(line) <= max_chars + 15  # textwrap puede exceder un poco por palabras largas


def test_no_word_is_split_mid_word():
    long_body = "Una historia del alma que invita a recordar algo importante sobre el presente"
    result = _wrap_for_drawtext(long_body, fontsize=38)
    original_words = set(long_body.split())
    wrapped_words = set(result.replace("\n", " ").split())
    assert original_words == wrapped_words
