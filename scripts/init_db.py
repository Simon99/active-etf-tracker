"""Initialize SQLite schema for active ETF holdings tracker."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / 'data' / 'holdings.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    date         TEXT NOT NULL,
    etf_id       TEXT NOT NULL,
    stock_id     TEXT NOT NULL,
    stock_name   TEXT,
    shares       INTEGER,
    weight       REAL,
    market_value REAL,
    PRIMARY KEY (date, etf_id, stock_id)
);
CREATE INDEX IF NOT EXISTS idx_holdings_etf  ON holdings(etf_id, date);
CREATE INDEX IF NOT EXISTS idx_holdings_stk  ON holdings(stock_id, date);

CREATE TABLE IF NOT EXISTS etf_meta (
    etf_id        TEXT PRIMARY KEY,
    etf_name      TEXT,
    issuer        TEXT,
    market        TEXT,
    fund_code     TEXT,
    aum_billion   REAL,
    pcf_url       TEXT,
    fetcher_module TEXT
);

CREATE TABLE IF NOT EXISTS fund_snapshot (
    date          TEXT NOT NULL,
    etf_id        TEXT NOT NULL,
    nav           REAL,
    total_assets  REAL,
    units_out     INTEGER,
    holdings_n    INTEGER,
    raw_meta_json TEXT,
    PRIMARY KEY (date, etf_id)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    date         TEXT NOT NULL,
    etf_id       TEXT NOT NULL,
    status       TEXT NOT NULL,
    error        TEXT,
    fetched_at   TEXT NOT NULL,
    PRIMARY KEY (date, etf_id)
);
"""


def main():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    con.commit()
    print(f'schema applied → {DB}')
    for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        print(f'  table: {row[0]}')
    con.close()


if __name__ == '__main__':
    main()
