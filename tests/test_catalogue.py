from agents.capabilities.catalogue import guess_genre, slugify


def test_slugify_basic():
    assert slugify("ALTIPLANO ANDINO") == "altiplano-andino"
    assert slugify("528 HZ vol 1") == "528-hz-vol-1"


def test_slugify_never_empty():
    assert slugify("   ") == "sin-nombre"
    assert slugify("###") == "sin-nombre"


def test_guess_genre_matches_keyword():
    assert guess_genre("ALTIPLANO ANDINO") == "ANDINO"
    assert guess_genre("528 HZ vol 1") == "FRECUENCIAS"
    assert guess_genre("Cumbia Hipnótica") == "CUMBIA"


def test_guess_genre_none_when_no_match():
    assert guess_genre("Sobre la Olas") is None
