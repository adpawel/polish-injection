"""World state of the MCP track: one SQLite file per run (notes/protocol.md 3).

The seed (data/seed_<lang>.json) is loaded into a fresh database before every run; the servers read and write
that file, the checkers compare a snapshot taken before the run (`pre`) with the database after it (`post`).
Order totals are not stored: they are computed from the order items, so the seed cannot contradict itself.
"""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
TODAY = "2026-03-16"  # fixed date of the scenario (a Monday); the servers never read the real clock
COMPANY_DOMAIN = "hearthwood-home.com"
USER_EMAIL = f"emma.clarke@{COMPANY_DOMAIN}"

SCHEMA = """
CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT, email TEXT, phone TEXT, address TEXT, city TEXT,
                        country TEXT, iban TEXT, notes TEXT);
CREATE TABLE suppliers (id TEXT PRIMARY KEY, name TEXT, email TEXT, country TEXT, currency TEXT, iban TEXT,
                        payment_terms_days INTEGER);
CREATE TABLE products (sku TEXT PRIMARY KEY, name TEXT, category TEXT, price_eur REAL, cost REAL,
                       cost_currency TEXT, stock INTEGER, weight_kg REAL, supplier_id TEXT);
CREATE TABLE orders (id TEXT PRIMARY KEY, customer_id TEXT, date TEXT, status TEXT, shipping_country TEXT);
CREATE TABLE order_items (order_id TEXT, sku TEXT, quantity INTEGER, unit_price_eur REAL);
CREATE TABLE refunds (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, amount_eur REAL, iban TEXT,
                      reason TEXT, date TEXT);
CREATE TABLE discount_codes (code TEXT PRIMARY KEY, percent REAL, valid_until TEXT, active INTEGER);
CREATE TABLE files (path TEXT PRIMARY KEY, content TEXT, modified TEXT);
CREATE TABLE file_shares (path TEXT, email TEXT);
CREATE TABLE emails (id TEXT PRIMARY KEY, folder TEXT, sender TEXT, recipients TEXT, subject TEXT, body TEXT,
                     attachments TEXT, date TEXT, read INTEGER);
"""

# JSON-encoded list columns
LIST_COLUMNS = {("emails", "recipients"), ("emails", "attachments")}
TABLES = ["customers", "suppliers", "products", "orders", "order_items", "refunds", "discount_codes", "files",
          "file_shares", "emails"]


def load_seed(lang: str = "en") -> dict:
    return json.loads((DATA_DIR / f"seed_{lang}.json").read_text(encoding="utf-8"))


def create(db_path: Path, seed: dict) -> None:
    """Writes a fresh database with the seed to `db_path` (overwrites it)."""
    db_path = Path(db_path)
    db_path.unlink(missing_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)
        for table in TABLES:
            for row in seed.get(table, []):
                row = {k: json.dumps(v, ensure_ascii=False) if (table, k) in LIST_COLUMNS else v for k, v in row.items()}
                cols = ", ".join(row)
                con.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' * len(row))})", list(row.values()))
    con.close()


def connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, isolation_level=None)  # autocommit: every tool call is final
    con.row_factory = sqlite3.Row
    return con


def row_dict(table: str, row: sqlite3.Row) -> dict:
    return {k: json.loads(row[k]) if (table, k) in LIST_COLUMNS else row[k] for k in row.keys()}


@dataclass(frozen=True)
class Snapshot:
    """Read-only copy of the whole database, for the checkers."""

    tables: dict[str, list[dict]]

    def rows(self, table: str, **where) -> list[dict]:
        return [r for r in self.tables[table] if all(r.get(k) == v for k, v in where.items())]

    def one(self, table: str, **where) -> dict | None:
        rows = self.rows(table, **where)
        return rows[0] if rows else None

    def order_total(self, order_id: str) -> float:
        return round(sum(i["quantity"] * i["unit_price_eur"] for i in self.rows("order_items", order_id=order_id)), 2)

    def sent_emails(self) -> list[dict]:
        return self.rows("emails", folder="sent")


def snapshot(db_path: Path) -> Snapshot:
    con = connect(db_path)
    try:
        return Snapshot({t: [row_dict(t, r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in TABLES})
    finally:
        con.close()
