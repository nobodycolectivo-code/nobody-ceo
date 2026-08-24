from agents.capabilities.link_royalties_catalogue import (
    CatalogueTrack,
    build_exact_index,
    match_title,
    normalize_title,
)


def test_normalize_title_strips_accents_and_case():
    assert normalize_title("Corazón de Arena") == "corazon de arena"
    assert normalize_title("  Múltiples   Espacios  ") == "multiples espacios"


def catalogue(*titles_with_album: tuple[str, str, str]) -> list[CatalogueTrack]:
    return [
        CatalogueTrack(track_id=tid, album_id=aid, title=title, normalized_title=normalize_title(title))
        for tid, aid, title in titles_with_album
    ]


def test_unique_exact_match():
    cat = catalogue(("t1", "a1", "Cumbia del Eclipse"))
    index = build_exact_index(cat)
    track_id, album_id, method, conf = match_title(normalize_title("Cumbia del Eclipse"), index, cat)
    assert (track_id, album_id, method, conf) == ("t1", "a1", "exact_title", 1.0)


def test_exact_match_ignores_accents_and_case():
    cat = catalogue(("t1", "a1", "Corazón de Arena"))
    index = build_exact_index(cat)
    track_id, album_id, method, conf = match_title(normalize_title("corazon DE arena"), index, cat)
    assert track_id == "t1"
    assert method == "exact_title"


def test_same_title_two_formats_same_album_links_album_not_track():
    cat = catalogue(
        ("528-hz-vol-1/solar-pulse-1", "528-hz-vol-1", "Solar Pulse (1)"),
        ("528-hz-vol-1/wav-solar-pulse-1", "528-hz-vol-1", "Solar Pulse (1)"),
    )
    index = build_exact_index(cat)
    track_id, album_id, method, conf = match_title(normalize_title("Solar Pulse (1)"), index, cat)
    assert track_id is None
    assert album_id == "528-hz-vol-1"
    assert method == "exact_title_ambiguous_format"
    assert 0 < conf < 1


def test_same_title_different_albums_is_fully_ambiguous():
    cat = catalogue(
        ("t1", "album-a", "Fuego Sagrado"),
        ("t2", "album-b", "Fuego Sagrado"),
    )
    index = build_exact_index(cat)
    track_id, album_id, method, conf = match_title(normalize_title("Fuego Sagrado"), index, cat)
    assert track_id is None
    assert album_id is None
    assert method == "exact_title_ambiguous_album"


def test_fuzzy_match_above_threshold():
    cat = catalogue(("t1", "a1", "Semilla Divina"))
    index = build_exact_index(cat)
    # variante con typo leve, no matchea exacto
    track_id, album_id, method, conf = match_title(normalize_title("Semila Divina"), index, cat)
    assert track_id == "t1"
    assert method == "fuzzy_title"
    assert conf >= 0.82


def test_no_match_below_threshold_is_unmatched():
    cat = catalogue(("t1", "a1", "Amanecer en el Altiplano"))
    index = build_exact_index(cat)
    track_id, album_id, method, conf = match_title(normalize_title("Completely Different Song"), index, cat)
    assert track_id is None
    assert method == "unmatched"
    assert conf == 0.0


def test_fuzzy_ambiguous_when_two_candidates_equally_close():
    # mismo largo, un solo carácter distinto cada uno respecto a la
    # consulta -> misma ratio de similitud para ambos candidatos.
    cat = catalogue(
        ("t1", "a1", "cancion azul"),
        ("t2", "a2", "cancion azur"),
    )
    index = build_exact_index(cat)
    track_id, album_id, method, conf = match_title("cancion azum", index, cat)
    assert method == "fuzzy_title"
    # gana un candidato (empate se resuelve por orden), pero la confianza
    # baja porque el segundo mejor queda igual de cerca (match ambiguo).
    assert conf <= 0.6
