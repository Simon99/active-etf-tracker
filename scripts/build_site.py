"""Build static site from holdings.db.

Pages live in two depth levels:
  root/         index.html, daily.html, changes.html, overlap.html, momentum.html, radar.html
  root/etfs/    {etf_id}.html
  root/stocks/  {stock_id}.html

Links use relative paths (`base=''` at root, `base='../'` in subdirs) so the
same files work both via local file:// / http://localhost AND on GitHub Pages
under any path.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'holdings.db'
OUT = ROOT / 'docs'
NA = '<span class="na">&lt;NA&gt;</span>'

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","SF Pro Text",sans-serif;background:#0d1117;color:#e6edf3;line-height:1.55;padding:20px;max-width:1500px;margin:0 auto}
h1{font-size:24px;font-weight:600;border-bottom:1px solid #30363d;padding-bottom:10px;margin-bottom:16px}
h2{font-size:18px;margin:28px 0 12px;color:#58a6ff;border-left:3px solid #58a6ff;padding-left:10px}
h3{font-size:15px;margin:18px 0 8px;color:#c9d1d9}
nav{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 14px;margin-bottom:16px;font-size:13px}
nav a{color:#58a6ff;margin-right:14px;text-decoration:none}
nav a:hover{text-decoration:underline}
nav a.cur{color:#fff;font-weight:600}
table{border-collapse:collapse;font-size:12px;margin:8px 0;background:#161b22;width:100%}
th{background:#21262d;color:#c9d1d9;padding:6px 8px;text-align:right;border:1px solid #30363d;cursor:pointer;user-select:none;font-weight:600;position:sticky;top:0}
th:first-child,td:first-child{text-align:left}
th:hover{background:#2d333b}
td{padding:5px 8px;border:1px solid #30363d;text-align:right;font-variant-numeric:tabular-nums}
tr:hover td{background:#1c2128}
.pos{color:#3fb950}.neg{color:#f85149}.mute{color:#6e7681}
.na{color:#6e7681;font-family:monospace}
a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}
.tag{display:inline-block;padding:2px 6px;border-radius:3px;background:#21262d;font-size:11px;margin-right:4px}
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:12px 0}
.metric{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:10px;font-size:12px}
.metric .v{font-size:18px;font-weight:600;color:#58a6ff;display:block;margin-top:2px}
.banner{background:#1c2128;border:1px solid #30363d;border-left:3px solid #d29922;border-radius:6px;padding:10px 14px;margin:12px 0;font-size:13px;color:#c9d1d9}
.toggle{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:4px;margin-bottom:12px}
.toggle a{display:inline-block;padding:5px 12px;border-radius:4px;font-size:13px}
.toggle a.cur{background:#1f6feb;color:#fff}
.foot{margin-top:32px;padding-top:12px;border-top:1px solid #30363d;color:#6e7681;font-size:11px}
"""

SORT_JS = """
function sortTable(table,col,asc){
  const rows=Array.from(table.querySelectorAll('tbody tr'));
  rows.sort((a,b)=>{
    let av=a.cells[col].getAttribute('data-sort')||a.cells[col].textContent;
    let bv=b.cells[col].getAttribute('data-sort')||b.cells[col].textContent;
    const an=parseFloat(av),bn=parseFloat(bv);
    if(!isNaN(an)&&!isNaN(bn))return asc?an-bn:bn-an;
    return asc?av.localeCompare(bv):bv.localeCompare(av);
  });
  const tb=table.querySelector('tbody');rows.forEach(r=>tb.appendChild(r));
}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('table.sortable').forEach(t=>{
    t.querySelectorAll('th').forEach((th,i)=>{
      let asc=true;
      th.addEventListener('click',()=>{sortTable(t,i,asc);asc=!asc;});
    });
  });
});
"""


def head(title: str, current: str = '', base: str = '') -> str:
    pages = [
        ('index.html', '總覽'),
        ('daily.html', '每日快照'),
        ('changes.html', '持股異動'),
        ('overlap.html', '持股重疊'),
        ('momentum.html', '同步加碼'),
        ('radar.html', '新增/賣出雷達'),
    ]
    nav = ' '.join(
        f'<a href="{base}{p}" class="{"cur" if p == current else ""}">{n}</a>'
        for p, n in pages
    )
    return f'''<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
<script>{SORT_JS}</script>
</head><body>
<nav>{nav}</nav>
<h1>{title}</h1>
'''


def foot(latest_date: str | None) -> str:
    ts = dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    return f'''<div class="foot">資料最新日期 {latest_date or NA}　·　頁面生成 {ts}　·
<a href="https://github.com/Simon99/active-etf-tracker">原始碼</a></div>
</body></html>'''


def fmt_num(v, suffix=''):
    if v is None:
        return NA
    if isinstance(v, float):
        return f'{v:,.2f}{suffix}'
    return f'{v:,}{suffix}'


def fmt_pct(v):
    return NA if v is None else f'{v:.2f}%'


# ──────────────────────────────────────────────────────────
# Pages — base='' for root pages, base='../' for subdir pages
# ──────────────────────────────────────────────────────────
def page_index(con, latest_date, base=''):
    # 全 ETF 列表（即使尚未抓到資料也列出，以 NA 占位）
    rows = con.execute('''
        SELECT m.etf_id, m.etf_name, m.issuer, m.market,
               s.total_assets/1e9 AS aum_b, s.nav, s.holdings_n,
               (m.fetcher_module IS NOT NULL AND m.fetcher_module != '') AS fetcher_ready
        FROM etf_meta m
        LEFT JOIN fund_snapshot s ON s.etf_id = m.etf_id
            AND s.date = (SELECT MAX(date) FROM fund_snapshot WHERE etf_id = m.etf_id)
        ORDER BY (s.total_assets IS NULL), s.total_assets DESC, m.etf_id
    ''').fetchall()

    n_total = len(rows)
    n_ready = sum(1 for r in rows if r[7])
    aum_total = sum((r[4] or 0) for r in rows)

    html = [head('主動式 ETF 追蹤', 'index.html', base)]
    html.append(f'''<div class="metric-grid">
<div class="metric">universe 全量<span class="v">{n_total}</span></div>
<div class="metric">已接 fetcher<span class="v">{n_ready} / {n_total}</span></div>
<div class="metric">已抓 AUM (B)<span class="v">{aum_total:,.1f}</span></div>
<div class="metric">最新資料日期<span class="v">{latest_date or '&lt;NA&gt;'}</span></div>
</div>''')

    html.append('<div class="toggle">'
                '<a href="#" class="cur" onclick="document.querySelectorAll(\'#full tbody tr\').forEach(r=>r.style.display=\'\'); return false;">全部</a>'
                '<a href="#" onclick="document.querySelectorAll(\'#full tbody tr\').forEach((r,i)=>r.style.display=(i&lt;10?\'\':\'none\')); return false;">Top 10</a>'
                '<a href="#" onclick="document.querySelectorAll(\'#full tbody tr\').forEach(r=>r.style.display=(r.classList.contains(\'no-data\')?\'none\':\'\')); return false;">僅有資料</a>'
                '</div>')

    html.append('<table id="full" class="sortable"><thead><tr>'
                '<th>ETF</th><th>名稱</th><th>發行投信</th><th>市場</th>'
                '<th>AUM (B)</th><th>NAV</th><th>持股數</th><th>狀態</th></tr></thead><tbody>')
    for r in rows:
        etf_id, name, issuer, market, aum, nav, hn, fetcher_ready = r
        has_data = hn is not None
        status = ('<span class="pos">已抓</span>' if has_data
                  else ('<span class="mute">等明日</span>' if fetcher_ready
                        else '<span class="neg">未接</span>'))
        row_cls = '' if has_data else ' class="no-data"'
        html.append(f'<tr{row_cls}>'
                    f'<td><a href="{base}etfs/{etf_id}.html">{etf_id}</a></td>'
                    f'<td>{name or NA}</td>'
                    f'<td>{issuer or NA}</td>'
                    f'<td>{market or NA}</td>'
                    f'<td data-sort="{aum or 0}">{fmt_num(aum)}</td>'
                    f'<td>{fmt_num(nav)}</td>'
                    f'<td>{hn if hn is not None else NA}</td>'
                    f'<td>{status}</td>'
                    f'</tr>')
    html.append('</tbody></table>')

    html.append('<h2>各功能入口</h2>')
    html.append(f'''<ul style="font-size:13px;margin-left:20px;line-height:2">
<li><a href="{base}daily.html">每日快照</a> — 任一天成分股查詢</li>
<li><a href="{base}changes.html">持股異動</a> — 跟昨日比，新增/減持/清空</li>
<li><a href="{base}overlap.html">持股重疊</a> — 多 ETF 共同持股</li>
<li><a href="{base}momentum.html">同步加碼</a> — 近 N 日各家同步加碼股</li>
<li><a href="{base}radar.html">新增/賣出雷達</a> — 監測清單變動</li>
</ul>''')
    html.append(foot(latest_date))
    return '\n'.join(html)


def page_daily(con, latest_date, base=''):
    rows = con.execute('''
        SELECT h.etf_id, m.etf_name, h.stock_id, h.stock_name, h.shares, h.weight
        FROM holdings h LEFT JOIN etf_meta m USING(etf_id)
        WHERE h.date = ?
        ORDER BY h.etf_id, h.weight DESC
    ''', (latest_date,)).fetchall() if latest_date else []

    html = [head(f'每日快照 — {latest_date or "&lt;NA&gt;"}', 'daily.html', base)]
    if not rows:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    html.append(f'<div class="banner">共 {len(set(r[0] for r in rows))} 檔 ETF / '
                f'{len(rows)} 持股 row。點 ETF 代碼看技術圖；點個股看反向追蹤。</div>')
    html.append('<table class="sortable"><thead><tr>'
                '<th>ETF</th><th>名稱</th><th>個股</th><th>個股名</th>'
                '<th>股數</th><th>權重 %</th></tr></thead><tbody>')
    for etf_id, etf_name, sid, sname, shares, w in rows:
        html.append(f'<tr>'
                    f'<td><a href="{base}etfs/{etf_id}.html">{etf_id}</a></td>'
                    f'<td>{etf_name or NA}</td>'
                    f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                    f'<td>{sname or NA}</td>'
                    f'<td data-sort="{shares or 0}">{fmt_num(shares)}</td>'
                    f'<td data-sort="{w or 0}">{fmt_pct(w)}</td>'
                    f'</tr>')
    html.append('</tbody></table>')
    html.append(foot(latest_date))
    return '\n'.join(html)


def page_changes(con, latest_date, base=''):
    html = [head(f'持股異動 — {latest_date or "&lt;NA&gt;"} vs 前一交易日', 'changes.html', base)]
    if not latest_date:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    prev = con.execute('SELECT MAX(date) FROM holdings WHERE date < ?', (latest_date,)).fetchone()[0]
    if not prev:
        html.append(f'<div class="banner">需累積至少 2 個交易日資料才能比對。目前只有 {latest_date} 一天。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    html.append(f'<div class="banner">比對 {prev} → {latest_date}</div>')
    rows = con.execute('''
        WITH curr AS (SELECT etf_id, stock_id, stock_name, shares, weight FROM holdings WHERE date=?),
             prev AS (SELECT etf_id, stock_id, shares AS sh_prev, weight AS w_prev FROM holdings WHERE date=?)
        SELECT COALESCE(c.etf_id, p.etf_id) AS etf,
               COALESCE(c.stock_id, p.stock_id) AS sid,
               c.stock_name,
               c.shares, c.weight, p.sh_prev, p.w_prev
        FROM curr c FULL OUTER JOIN prev p ON c.etf_id=p.etf_id AND c.stock_id=p.stock_id
        WHERE COALESCE(c.shares,0) != COALESCE(p.sh_prev,0)
    ''', (latest_date, prev)).fetchall()

    if not rows:
        html.append('<div class="banner">無變動。</div>')
    else:
        html.append('<table class="sortable"><thead><tr>'
                    '<th>類型</th><th>ETF</th><th>個股</th><th>個股名</th>'
                    '<th>前股數</th><th>今股數</th><th>差</th></tr></thead><tbody>')
        for etf, sid, sname, sh, w, sh_p, w_p in rows:
            sh = sh or 0
            sh_p = sh_p or 0
            diff = sh - sh_p
            kind = '新增' if sh_p == 0 else ('清空' if sh == 0 else ('加碼' if diff > 0 else '減碼'))
            cls = 'pos' if diff > 0 else 'neg'
            html.append(f'<tr><td>{kind}</td><td>{etf}</td>'
                        f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                        f'<td>{sname or NA}</td>'
                        f'<td>{fmt_num(sh_p)}</td>'
                        f'<td>{fmt_num(sh)}</td>'
                        f'<td class="{cls}" data-sort="{diff}">{diff:+,}</td></tr>')
        html.append('</tbody></table>')
    html.append(foot(latest_date))
    return '\n'.join(html)


def page_overlap(con, latest_date, base=''):
    html = [head(f'持股重疊 — {latest_date or "&lt;NA&gt;"}', 'overlap.html', base)]
    if not latest_date:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    n_etf_universe = con.execute(
        'SELECT COUNT(DISTINCT etf_id) FROM holdings WHERE date=?',
        (latest_date,)
    ).fetchone()[0]

    rows = con.execute('''
        SELECT h.stock_id, h.stock_name,
               COUNT(DISTINCT h.etf_id) AS n_etf,
               GROUP_CONCAT(h.etf_id, ', ') AS etfs,
               AVG(h.weight) AS avg_w,
               SUM(h.weight) AS sum_w
        FROM holdings h
        WHERE h.date = ?
        GROUP BY h.stock_id, h.stock_name
        ORDER BY n_etf DESC, sum_w DESC
    ''', (latest_date,)).fetchall()

    n_total = len(rows)
    n_multi = sum(1 for r in rows if r[2] >= 2)
    html.append(f'<div class="banner">共 {n_total} 檔個股被持有，其中 {n_multi} 檔被 ≥2 家 ETF 持有。'
                f'分母 {n_etf_universe} = 本日有抓到資料的主動式 ETF 檔數。</div>')

    # 衍生欄位算法說明
    html.append('''<div class="banner" style="border-left-color:#58a6ff">
<strong>📐 衍生欄位怎麼算（重要）</strong>
<ul style="margin-top:6px;padding-left:20px;line-height:1.8">
<li><b>覆蓋率 %</b> = 持有它的 ETF 數 ÷ 本日全部主動 ETF 數
  → 越高代表越多基金經理人「共識」買進，最直接的受歡迎度指標</li>
<li><b>平均 weight (僅參考)</b> = 該股在「持有它的 ETF」內 weight 的算術平均
  → 粗略代表「對持有它的 ETF 是不是大部位」，但**忽略各 ETF AUM 大小差異**</li>
<li><b>合計 weight (僅供排序)</b> = 把 N 個 weight 直接加總
  → ⚠ <b>數學上沒物理意義</b>。weight 的基數（各 ETF 淨資產）不同不能直接加。
  保留只是因為剛好能反映「N × avg_w」的視覺重量，但別當實際比例看</li>
</ul>
<small>真正有意義的「綜合權重 = Σ(weight × AUM) / Σ(AUM)」需先補 AUM 入庫（部分 fetcher 還沒寫），等做完功能 5 一起補。</small>
</div>''')

    html.append('<table class="sortable"><thead><tr>'
                '<th>個股</th><th>名稱</th><th>持有 ETF 數</th>'
                '<th>覆蓋率 %</th><th>持有 ETF</th>'
                '<th>平均 weight</th><th>合計 weight</th></tr></thead><tbody>')
    for sid, sname, n, etfs, avg_w, sum_w in rows:
        coverage = (n / n_etf_universe * 100) if n_etf_universe else 0
        html.append(f'<tr>'
                    f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                    f'<td>{sname or NA}</td>'
                    f'<td data-sort="{n}">{n}</td>'
                    f'<td data-sort="{coverage}">{coverage:.1f}%</td>'
                    f'<td>{etfs}</td>'
                    f'<td data-sort="{avg_w or 0}">{fmt_pct(avg_w)}</td>'
                    f'<td data-sort="{sum_w or 0}" class="mute">{fmt_pct(sum_w)}</td>'
                    f'</tr>')
    html.append('</tbody></table>')
    html.append(foot(latest_date))
    return '\n'.join(html)


def page_momentum(con, latest_date, base=''):
    html = [head('同步加碼', 'momentum.html', base)]
    if not latest_date:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    n_days = con.execute('SELECT COUNT(DISTINCT date) FROM holdings').fetchone()[0]
    if n_days < 2:
        html.append(f'<div class="banner">需累積至少 2 個交易日資料。目前 {n_days} 天。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    cmp_date = con.execute('''SELECT MIN(date) FROM (
        SELECT DISTINCT date FROM holdings WHERE date <= ? ORDER BY date DESC LIMIT 7
    )''', (latest_date,)).fetchone()[0]
    html.append(f'<div class="banner">比對窗口：{cmp_date} → {latest_date}（多家 ETF 同步加碼的股票）</div>')

    rows = con.execute('''
        WITH curr AS (SELECT etf_id, stock_id, stock_name, shares FROM holdings WHERE date=?),
             base AS (SELECT etf_id, stock_id, shares AS sh_base FROM holdings WHERE date=?)
        SELECT c.stock_id, c.stock_name,
               COUNT(*) AS n_etf_added,
               GROUP_CONCAT(c.etf_id, ', ') AS etfs,
               SUM(c.shares - COALESCE(b.sh_base,0)) AS total_added
        FROM curr c LEFT JOIN base b ON c.etf_id=b.etf_id AND c.stock_id=b.stock_id
        WHERE c.shares > COALESCE(b.sh_base, 0)
        GROUP BY c.stock_id, c.stock_name
        HAVING n_etf_added >= 2
        ORDER BY n_etf_added DESC, total_added DESC
    ''', (latest_date, cmp_date)).fetchall()

    if not rows:
        html.append('<div class="banner">尚無 ≥2 家同步加碼。</div>')
    else:
        html.append('<table class="sortable"><thead><tr>'
                    '<th>個股</th><th>名稱</th><th>加碼 ETF 數</th>'
                    '<th>ETF</th><th>合計加碼股數</th></tr></thead><tbody>')
        for sid, sname, n, etfs, ta in rows:
            html.append(f'<tr>'
                        f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                        f'<td>{sname or NA}</td>'
                        f'<td data-sort="{n}">{n}</td>'
                        f'<td>{etfs}</td>'
                        f'<td class="pos" data-sort="{ta}">+{ta:,}</td>'
                        f'</tr>')
        html.append('</tbody></table>')
    html.append(foot(latest_date))
    return '\n'.join(html)


def page_radar(con, latest_date, base=''):
    html = [head(f'新增 / 賣出雷達 — {latest_date or "&lt;NA&gt;"}', 'radar.html', base)]
    if not latest_date:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    prev = con.execute('SELECT MAX(date) FROM holdings WHERE date < ?', (latest_date,)).fetchone()[0]
    if not prev:
        html.append(f'<div class="banner">需累積至少 2 個交易日資料。目前只有 {latest_date} 一天。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    html.append(f'<div class="banner">{prev} → {latest_date}</div>')

    new_rows = con.execute('''
        SELECT c.etf_id, c.stock_id, c.stock_name, c.shares, c.weight
        FROM holdings c LEFT JOIN holdings p
          ON p.etf_id=c.etf_id AND p.stock_id=c.stock_id AND p.date=?
        WHERE c.date=? AND p.stock_id IS NULL
        ORDER BY c.etf_id, c.weight DESC
    ''', (prev, latest_date)).fetchall()

    sold_rows = con.execute('''
        SELECT p.etf_id, p.stock_id, p.stock_name, p.shares, p.weight
        FROM holdings p LEFT JOIN holdings c
          ON c.etf_id=p.etf_id AND c.stock_id=p.stock_id AND c.date=?
        WHERE p.date=? AND c.stock_id IS NULL
        ORDER BY p.etf_id, p.weight DESC
    ''', (latest_date, prev)).fetchall()

    html.append(f'<h2>新增雷達 ({len(new_rows)} 筆)</h2>')
    if not new_rows:
        html.append('<div class="banner">無新增。</div>')
    else:
        html.append('<table class="sortable"><thead><tr>'
                    '<th>ETF</th><th>個股</th><th>名稱</th>'
                    '<th>建倉股數</th><th>權重 %</th></tr></thead><tbody>')
        for etf, sid, sname, sh, w in new_rows:
            html.append(f'<tr><td>{etf}</td>'
                        f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                        f'<td>{sname or NA}</td>'
                        f'<td class="pos">{fmt_num(sh)}</td>'
                        f'<td>{fmt_pct(w)}</td></tr>')
        html.append('</tbody></table>')

    html.append(f'<h2>賣出雷達 ({len(sold_rows)} 筆)</h2>')
    if not sold_rows:
        html.append('<div class="banner">無清空。</div>')
    else:
        html.append('<table class="sortable"><thead><tr>'
                    '<th>ETF</th><th>個股</th><th>名稱</th>'
                    '<th>清倉前股數</th><th>原權重 %</th></tr></thead><tbody>')
        for etf, sid, sname, sh, w in sold_rows:
            html.append(f'<tr><td>{etf}</td>'
                        f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                        f'<td>{sname or NA}</td>'
                        f'<td class="neg">{fmt_num(sh)}</td>'
                        f'<td>{fmt_pct(w)}</td></tr>')
        html.append('</tbody></table>')

    html.append(foot(latest_date))
    return '\n'.join(html)


def page_stock(con, sid, latest_date, base='../'):
    name_row = con.execute(
        'SELECT stock_name FROM holdings WHERE stock_id=? ORDER BY date DESC LIMIT 1', (sid,)
    ).fetchone()
    sname = (name_row[0] if name_row else '') or sid

    html = [head(f'{sid} {sname} — ETF 持有狀況', '', base)]
    html.append(f'<div class="banner">追蹤所有主動式 ETF 對 {sid} 的持有時序</div>')

    rows = con.execute('''
        SELECT h.etf_id, m.etf_name, h.shares, h.weight
        FROM holdings h LEFT JOIN etf_meta m USING(etf_id)
        WHERE h.stock_id=? AND h.date=?
        ORDER BY h.weight DESC
    ''', (sid, latest_date)).fetchall()
    html.append(f'<h2>最新持有 ETF（{latest_date}）</h2>')
    if not rows:
        html.append('<div class="banner">目前無 ETF 持有。</div>')
    else:
        html.append('<table class="sortable"><thead><tr>'
                    '<th>ETF</th><th>名稱</th><th>股數</th><th>權重 %</th></tr></thead><tbody>')
        for etf, en, sh, w in rows:
            html.append(f'<tr>'
                        f'<td><a href="{base}etfs/{etf}.html">{etf}</a></td>'
                        f'<td>{en or NA}</td>'
                        f'<td>{fmt_num(sh)}</td>'
                        f'<td>{fmt_pct(w)}</td>'
                        f'</tr>')
        html.append('</tbody></table>')

    n_days = con.execute('SELECT COUNT(DISTINCT date) FROM holdings WHERE stock_id=?', (sid,)).fetchone()[0]
    html.append('<h2>持有規模時序</h2>')
    if n_days < 2:
        html.append(f'<div class="banner">需累積至少 2 天才有時序資料。目前 {n_days} 天。</div>')
    else:
        ts_rows = con.execute('''
            SELECT date, SUM(shares) FROM holdings
            WHERE stock_id=? GROUP BY date ORDER BY date
        ''', (sid,)).fetchall()
        html.append('<table><thead><tr><th>日期</th><th>合計被持有股數</th></tr></thead><tbody>')
        for d, sh in ts_rows:
            html.append(f'<tr><td>{d}</td><td>{fmt_num(sh)}</td></tr>')
        html.append('</tbody></table>')

    html.append(foot(latest_date))
    return '\n'.join(html)


def page_etf(con, etf_id, latest_date, base='../'):
    meta = con.execute(
        "SELECT etf_name, issuer, fund_code, NULLIF(fetcher_module,'') FROM etf_meta WHERE etf_id=?",
        (etf_id,)
    ).fetchone() or ('', '', None, None)
    etf_name, issuer, fund_code, fetcher_mod = meta
    snap = con.execute('''SELECT nav, total_assets/1e9, units_out, holdings_n, MAX(date)
                          FROM fund_snapshot WHERE etf_id=? AND date<=?''',
                       (etf_id, latest_date or '9999-99-99')).fetchone() or (None,)*5
    nav, aum, units, hn, snap_date = snap

    html = [head(f'{etf_id} {etf_name or ""} — {issuer or "&lt;NA&gt;"}', '', base)]
    if not fetcher_mod:
        html.append('<div class="banner">⚠ 此 ETF 尚未接 fetcher，所有資料以 &lt;NA&gt; 顯示。</div>')
    elif hn is None:
        html.append('<div class="banner">fetcher 已接但尚未抓到當日資料。</div>')

    html.append(f'''<div class="metric-grid">
<div class="metric">NAV<span class="v">{fmt_num(nav)}</span></div>
<div class="metric">基金規模 (B)<span class="v">{fmt_num(aum)}</span></div>
<div class="metric">受益權單位<span class="v">{fmt_num(units)}</span></div>
<div class="metric">持股數<span class="v">{hn if hn is not None else NA}</span></div>
<div class="metric">快照日期<span class="v">{snap_date or NA}</span></div>
</div>''')

    html.append('<h2>① 技術線型（功能 5）</h2>')
    html.append('<div class="banner">技術圖表（MA5/20/60/120/240 + Bollinger + RSI + MACD）→ '
                '待接 yfinance / FinMind ETF 報價，本階段以 &lt;NA&gt; 顯示。</div>')

    html.append(f'<h2>② 最新持股（{snap_date or "&lt;NA&gt;"}）</h2>')
    rows = []
    if snap_date:
        rows = con.execute('''
            SELECT stock_id, stock_name, shares, weight
            FROM holdings WHERE etf_id=? AND date=? ORDER BY weight DESC
        ''', (etf_id, snap_date)).fetchall()

    if not rows:
        html.append('<div class="banner">無持股資料。</div>')
    else:
        html.append('<table class="sortable"><thead><tr>'
                    '<th>個股</th><th>名稱</th><th>股數</th><th>權重 %</th></tr></thead><tbody>')
        for sid, sname, sh, w in rows:
            html.append(f'<tr>'
                        f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                        f'<td>{sname or NA}</td>'
                        f'<td>{fmt_num(sh)}</td>'
                        f'<td>{fmt_pct(w)}</td>'
                        f'</tr>')
        html.append('</tbody></table>')

    html.append(foot(latest_date))
    return '\n'.join(html)


# ──────────────────────────────────────────────────────────
def main():
    if not DB.exists():
        print(f'no DB at {DB} — run scripts/run_daily.py first')
        sys.exit(1)
    con = sqlite3.connect(DB)
    latest = con.execute('SELECT MAX(date) FROM holdings').fetchone()[0]
    OUT.mkdir(exist_ok=True)
    (OUT / 'etfs').mkdir(exist_ok=True)
    (OUT / 'stocks').mkdir(exist_ok=True)

    (OUT / 'index.html').write_text(page_index(con, latest), encoding='utf-8')
    (OUT / 'daily.html').write_text(page_daily(con, latest), encoding='utf-8')
    (OUT / 'changes.html').write_text(page_changes(con, latest), encoding='utf-8')
    (OUT / 'overlap.html').write_text(page_overlap(con, latest), encoding='utf-8')
    (OUT / 'momentum.html').write_text(page_momentum(con, latest), encoding='utf-8')
    (OUT / 'radar.html').write_text(page_radar(con, latest), encoding='utf-8')

    # 全 universe（含尚未抓到資料的）都生成 ETF 頁
    etfs = [r[0] for r in con.execute('SELECT etf_id FROM etf_meta')]
    for etf_id in etfs:
        (OUT / 'etfs' / f'{etf_id}.html').write_text(page_etf(con, etf_id, latest), encoding='utf-8')

    stocks = [r[0] for r in con.execute('SELECT DISTINCT stock_id FROM holdings WHERE date=?', (latest,))]
    for sid in stocks:
        (OUT / 'stocks' / f'{sid}.html').write_text(page_stock(con, sid, latest), encoding='utf-8')

    print('━━━ 完成 ━━━')
    print(f'  6 主頁 + {len(etfs)} ETF 頁 + {len(stocks)} 個股頁')
    print(f'  → {OUT}/')
    con.close()


if __name__ == '__main__':
    main()
