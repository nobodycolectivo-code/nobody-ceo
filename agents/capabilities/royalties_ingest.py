"""Ingesta de solo lectura de exports de royalties de DistroKid (results.csv)
hacia NOBODY_BRAIN.

Nunca modifica el CSV original — solo lee y escribe en la base propia del
proyecto (data/nobody.db). Idempotente: reimportar el mismo archivo, o un
export nuevo que solape meses ya vistos, no duplica filas — ver
brain/royalties/store.py (row_hash) y brain/schema.sql para el porqué.

Uso:
    python -m agents.capabilities.royalties_ingest --file "D:\\Users\\Santiago\\Desktop\\NOBODY\\results.csv"
    python -m agents.capabilities.royalties_ingest --file ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from brain.db import connect
from brain.royalties.store import RoyaltyFact, insert_facts_raw

REQUIRED_COLUMNS = [
    "Date Inserted", "Reporting Date", "Sale Month", "Store", "Artist",
    "Title", "ISRC", "UPC", "Quantity", "Team Percentage", "Source Type",
    "Country of Sale", "Songwriter Royalties Withheld (USD)",
    "Earnings (USD)", "Recoup (USD)",
]


def _to_float(value: str) -> float:
    value = value.strip()
    return float(value) if value else 0.0


def _to_optional_float(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def _to_optional_str(value: str) -> str | None:
    value = value.strip()
    return value or None


def parse_row(row: dict[str, str], source_file: str, row_num: int) -> RoyaltyFact:
    return RoyaltyFact(
        source_file=source_file,
        source_row_num=row_num,
        date_inserted=row["Date Inserted"].strip(),
        reporting_date=row["Reporting Date"].strip(),
        sale_month=row["Sale Month"].strip(),
        store=row["Store"].strip(),
        artist=row["Artist"].strip(),
        title=row["Title"].strip(),
        isrc=_to_optional_str(row["ISRC"]),
        upc=row["UPC"].strip(),
        quantity=int(row["Quantity"].strip() or 0),
        team_percentage=_to_float(row["Team Percentage"]),
        source_type=row["Source Type"].strip(),
        country_of_sale=row["Country of Sale"].strip(),
        songwriter_withheld_usd=_to_float(row["Songwriter Royalties Withheld (USD)"]),
        earnings_usd=_to_float(row["Earnings (USD)"]),
        recoup_usd=_to_optional_float(row["Recoup (USD)"]),
    )


def read_facts(csv_path: Path) -> tuple[list[RoyaltyFact], list[dict]]:
    """Devuelve (facts parseados, filas rechazadas con su motivo). Nunca
    lanza por una fila individual mal formada — la aísla y sigue, para
    que un export con una línea corrupta no bloquee todo el import."""
    facts: list[RoyaltyFact] = []
    rejected: list[dict] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"Columnas esperadas ausentes en {csv_path.name}: {missing}. "
                f"El schema real no coincide con el esperado — revisar antes de importar."
            )
        for row_num, row in enumerate(reader, start=2):  # 1 = encabezado
            try:
                facts.append(parse_row(row, csv_path.name, row_num))
            except Exception as e:
                rejected.append({"row_num": row_num, "error": str(e), "raw": row})
    return facts, rejected


def ingest(csv_path: Path, dry_run: bool = False) -> dict:
    facts, rejected = read_facts(csv_path)

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(csv_path),
        "dry_run": dry_run,
        "rows_read": len(facts) + len(rejected),
        "rows_rejected": len(rejected),
        "rejected_detail": rejected[:20],
    }

    if dry_run:
        report["would_insert_at_most"] = len(facts)
        return report

    conn = connect()
    before = conn.execute("SELECT COUNT(*) FROM royalty_facts_raw").fetchone()[0]
    result = insert_facts_raw(conn, facts)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM royalty_facts_raw").fetchone()[0]
    conn.close()

    report.update(result)
    report["raw_rows_before"] = before
    report["raw_rows_after"] = after
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingesta de solo lectura de un export de royalties de DistroKid"
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="No escribe en NOBODY_BRAIN, solo reporta qué haría",
    )
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"No existe el archivo: {args.file}")

    report = ingest(args.file, dry_run=args.dry_run)
    import json

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not args.dry_run:
        print(
            f"\n{report['inserted']} filas nuevas, "
            f"{report['skipped_duplicate']} ya existían (idempotente), "
            f"{report['rows_rejected']} rechazadas."
        )


if __name__ == "__main__":
    main()
