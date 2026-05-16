"""Daily orchestrator — fetch all registered ETFs and insert into SQLite.

Usage:
    python scripts/run_daily.py            # fetch today
    python scripts/run_daily.py 2026-05-16 # fetch specific date
"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetchers import REGISTRY, fetch  # noqa: E402

DB = ROOT / 'data' / 'holdings.db'


def insert_result(con, res):
    now = dt.datetime.now().isoformat(timespec='seconds')
    if not res.ok:
        con.execute(
            'INSERT OR REPLACE INTO fetch_log(date, etf_id, status, error, fetched_at) VALUES (?,?,?,?,?)',
            (res.date.isoformat(), res.etf_id, 'fail', res.error, now),
        )
        return

    # holdings 用 INSERT OR REPLACE 以便重跑覆蓋
    con.executemany(
        'INSERT OR REPLACE INTO holdings(date, etf_id, stock_id, stock_name, shares, weight, market_value) VALUES (:date,:etf_id,:stock_id,:stock_name,:shares,:weight,:market_value)',
        res.holdings,
    )
    con.execute(
        'INSERT OR REPLACE INTO fund_snapshot(date, etf_id, nav, total_assets, units_out, holdings_n, raw_meta_json) VALUES (?,?,?,?,?,?,?)',
        (
            res.date.isoformat(),
            res.etf_id,
            _money(res.meta.get('每受益權單位淨資產價值(元)')) or _meta_lookup_nav(res.meta),
            _money(res.meta.get('基金淨資產價值(元)')),
            _int(res.meta.get('已發行受益權單位總數')),
            len(res.holdings),
            json.dumps(res.meta, ensure_ascii=False),
        ),
    )
    con.execute(
        'INSERT OR REPLACE INTO fetch_log(date, etf_id, status, error, fetched_at) VALUES (?,?,?,?,?)',
        (res.date.isoformat(), res.etf_id, 'ok', None, now),
    )


def _money(s):
    """'NTD 257,218,842,106' → 257218842106.0"""
    if not s:
        return None
    s = str(s).replace('NTD', '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def _int(s):
    if not s:
        return None
    s = str(s).replace(',', '').strip()
    try:
        return int(s)
    except ValueError:
        return None


def _meta_lookup_nav(meta):
    """NAV 的 key 含日期前綴（'115/05/15 每受益權單位淨資產價值(元)'），需 fuzzy 找。"""
    for k, v in meta.items():
        if '每受益權單位淨資產價值' in k:
            return _money(v)
    return None


def main():
    target = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
    print(f'fetching {len(REGISTRY)} ETFs for {target}\n')

    con = sqlite3.connect(DB)
    ok_n = fail_n = 0
    for etf_id in sorted(REGISTRY.keys()):
        res = fetch(etf_id, target)
        if res.ok:
            ok_n += 1
            print(f'  ✓ {etf_id}  {len(res.holdings):>3} holdings')
        else:
            fail_n += 1
            print(f'  ✗ {etf_id}  {res.error}')
        insert_result(con, res)
    con.commit()

    # 報告
    print(f'\n━━━ {target} ━━━')
    print(f'  ok:   {ok_n}')
    print(f'  fail: {fail_n}')
    cur = con.execute('SELECT COUNT(*) FROM holdings WHERE date = ?', (target.isoformat(),))
    print(f'  rows in holdings: {cur.fetchone()[0]}')
    con.close()


if __name__ == '__main__':
    main()
