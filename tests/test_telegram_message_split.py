from integrations.telegram.bot import TELEGRAM_MESSAGE_LIMIT, _split_long_message


def test_short_text_is_single_chunk():
    text = "Reporte corto."
    assert _split_long_message(text) == [text]


def test_long_text_is_split_on_paragraph_boundaries():
    paragraph = "x" * 1000
    text = "\n\n".join([paragraph] * 6)  # 6000+ chars, supera el límite
    chunks = _split_long_message(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= TELEGRAM_MESSAGE_LIMIT
    # ningún párrafo se pierde ni se corta a la mitad
    assert "\n\n".join(chunks) == text


def test_single_paragraph_longer_than_limit_is_kept_whole():
    """No hay forma de partirlo sin cortar una oración a la mitad — se
    mantiene entero antes que truncar contenido silenciosamente."""
    huge_paragraph = "y" * (TELEGRAM_MESSAGE_LIMIT + 500)
    chunks = _split_long_message(huge_paragraph)
    assert chunks == [huge_paragraph]
