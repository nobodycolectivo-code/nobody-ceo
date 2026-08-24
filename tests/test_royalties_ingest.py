import csv
from functools import partial
from pathlib import Path

import pytest

import agents.capabilities.royalties_ingest as ingest_module
import brain.db as db_module
from agents.capabilities.royalties_ingest import ingest, read_facts
from brain.royalties.store import raw_row_count, revenue_by_dimension, revenue_total

HEADER = [
    "Date Inserted", "Reporting Date", "Sale Month", "Store", "Artist",
    "Title", "ISRC", "UPC", "Quantity", "Team Percentage", "Source Type",
    "Country of Sale", "Songwriter Royalties Withheld (USD)",
    "Earnings (USD)", "Recoup (USD)",
]


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_nobody.db"


@pytest.fixture(autouse=True)
def _patch_db_path(monkeypatch, db_path):
    """ingest() y este archivo de test llaman a brain.db.connect() sin
    argumentos (mismo patrón que el resto de capabilities) — se fija el
    default a un archivo temporal en vez de tocar data/nobody.db real."""
    patched_connect = partial(db_module.connect, db_path=db_path)
    monkeypatch.setattr(db_module, "connect", patched_connect)
    monkeypatch.setattr(ingest_module, "connect", patched_connect)


def connect():
    return db_module.connect()


def test_basic_ingest_inserts_rows(tmp_path):
    csv_path = write_csv(tmp_path / "results.csv", [
        ["2026-01-01", "2026-01-01", "2025-12", "Spotify", "NØBØĐ¥", "Track A",
         "ISRC001", "UPC001", "10", "100", "Song", "US", "0.00000", "1.500000", ""],
        ["2026-01-01", "2026-01-01", "2025-12", "Apple Music", "NØBØĐ¥", "Track B",
         "ISRC002", "UPC001", "5", "100", "Song", "MX", "0.00000", "0.750000", ""],
    ])
    report = ingest(csv_path, dry_run=False)
    assert report["inserted"] == 2
    assert report["skipped_duplicate"] == 0
    assert report["rows_rejected"] == 0


def test_reimporting_same_file_is_idempotent(tmp_path):
    csv_path = write_csv(tmp_path / "results.csv", [
        ["2026-01-01", "2026-01-01", "2025-12", "Spotify", "NØBØĐ¥", "Track A",
         "ISRC001", "UPC001", "10", "100", "Song", "US", "0.00000", "1.500000", ""],
    ])
    first = ingest(csv_path, dry_run=False)
    second = ingest(csv_path, dry_run=False)
    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped_duplicate"] == 1

    conn = connect()
    assert raw_row_count(conn) == 1
    conn.close()


def test_overlapping_later_export_does_not_duplicate_unchanged_rows(tmp_path):
    """Simula el caso real: un export nuevo re-reporta un mes ya visto sin
    cambios para una fila, pero trae una fila nueva. La fila sin cambios no
    debe duplicarse (mismo row_hash); la nueva sí debe insertarse."""
    row_unchanged = ["2026-01-01", "2026-01-01", "2025-12", "Spotify", "NØBØĐ¥",
                      "Track A", "ISRC001", "UPC001", "10", "100", "Song", "US",
                      "0.00000", "1.500000", ""]
    export1 = write_csv(tmp_path / "export1.csv", [row_unchanged])
    ingest(export1, dry_run=False)

    row_new = ["2026-02-01", "2026-02-01", "2026-01", "Spotify", "NØBØĐ¥",
               "Track C", "ISRC003", "UPC001", "3", "100", "Song", "US",
               "0.00000", "0.400000", ""]
    export2 = write_csv(tmp_path / "export2.csv", [row_unchanged, row_new])
    report2 = ingest(export2, dry_run=False)

    assert report2["inserted"] == 1
    assert report2["skipped_duplicate"] == 1

    conn = connect()
    assert raw_row_count(conn) == 2
    conn.close()


def test_restatement_resolves_to_latest_reporting_date(tmp_path):
    """Caso real encontrado en el CSV de producción: la misma combinación
    (mes, store, isrc, upc, país) se reporta dos veces en fechas distintas
    con cifras distintas — la vista resuelta debe quedarse solo con la más
    reciente, no sumar ambas."""
    older = ["2026-01-27", "2026-01-27", "2025-10", "Deezer", "NØBØĐ¥",
             "Track A", "ISRC001", "UPC001", "1", "100", "Song", "BR",
             "0.00000", "0.000230626324", ""]
    newer = ["2026-05-15", "2026-05-15", "2025-10", "Deezer", "NØBØĐ¥",
             "Track A", "ISRC001", "UPC001", "0", "100", "Song", "BR",
             "0.00000", "0.000012556375", ""]
    csv_path = write_csv(tmp_path / "results.csv", [older, newer])
    ingest(csv_path, dry_run=False)

    conn = connect()
    assert raw_row_count(conn) == 2  # ambas filas fuente se conservan (trazabilidad)
    total = revenue_total(conn)
    assert total == pytest.approx(0.000012556375)  # solo la más reciente cuenta
    conn.close()


def test_same_day_duplicate_dimensional_key_is_summed(tmp_path):
    """Caso real: dos líneas con la misma dimensión completa el mismo
    reporting_date (p. ej. NetEase/Apple Music en el CSV real) — son
    transacciones aditivas legítimas, no duplicados, y deben sumarse."""
    line1 = ["2026-07-31", "2026-07-31", "2026-04", "NetEase", "NØBØĐ¥",
             "Track A", "ISRC001", "UPC001", "1", "100", "Song", "US",
             "0.00000", "0.000464720624", ""]
    line2 = ["2026-07-31", "2026-07-31", "2026-04", "NetEase", "NØBØĐ¥",
             "Track A", "ISRC001", "UPC001", "3", "100", "Song", "US",
             "0.00000", "0.000350727760", ""]
    csv_path = write_csv(tmp_path / "results.csv", [line1, line2])
    ingest(csv_path, dry_run=False)

    conn = connect()
    total = revenue_total(conn)
    assert total == pytest.approx(0.000464720624 + 0.000350727760)
    conn.close()


def test_blank_isrc_is_handled_as_null_not_dropped(tmp_path):
    """Caso real: venta de álbum completo (Amazon Downloads) no trae ISRC."""
    row = ["2025-10-15", "2025-10-15", "2025-08", "Amazon (Downloads)", "NØBØĐ¥",
           "Album Title", "", "UPC999", "1", "100", "Album", "DE",
           "0.00000", "3.495516655261", ""]
    csv_path = write_csv(tmp_path / "results.csv", [row])
    report = ingest(csv_path, dry_run=False)
    assert report["inserted"] == 1

    conn = connect()
    assert revenue_total(conn) == pytest.approx(3.495516655261)
    conn.close()


def test_revenue_by_dimension_store(tmp_path):
    csv_path = write_csv(tmp_path / "results.csv", [
        ["2026-01-01", "2026-01-01", "2025-12", "Spotify", "NØBØĐ¥", "Track A",
         "ISRC001", "UPC001", "10", "100", "Song", "US", "0.00000", "2.000000", ""],
        ["2026-01-01", "2026-01-01", "2025-12", "Spotify", "NØBØĐ¥", "Track B",
         "ISRC002", "UPC001", "5", "100", "Song", "MX", "0.00000", "1.000000", ""],
        ["2026-01-01", "2026-01-01", "2025-12", "TikTok", "NØBØĐ¥", "Track A",
         "ISRC001", "UPC001", "100", "100", "Song", "US", "0.00000", "0.100000", ""],
    ])
    ingest(csv_path, dry_run=False)
    conn = connect()
    by_store = {r["key"]: r["revenue"] for r in revenue_by_dimension(conn, "store")}
    assert by_store["Spotify"] == pytest.approx(3.0)
    assert by_store["TikTok"] == pytest.approx(0.1)
    conn.close()


def test_missing_expected_column_raises_before_writing(tmp_path):
    csv_path = tmp_path / "bad.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("Not,The,Right,Columns\n1,2,3,4\n")
    with pytest.raises(ValueError, match="Columnas esperadas ausentes"):
        read_facts(csv_path)


def test_dry_run_does_not_write(tmp_path):
    csv_path = write_csv(tmp_path / "results.csv", [
        ["2026-01-01", "2026-01-01", "2025-12", "Spotify", "NØBØĐ¥", "Track A",
         "ISRC001", "UPC001", "10", "100", "Song", "US", "0.00000", "1.500000", ""],
    ])
    report = ingest(csv_path, dry_run=True)
    assert report["would_insert_at_most"] == 1

    conn = connect()
    assert raw_row_count(conn) == 0
    conn.close()
