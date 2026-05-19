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
sys.path.insert(0, str(ROOT / 'scripts'))
from etf_chart import render_chart  # noqa: E402
from stock_chart import render_stock_chart  # noqa: E402
from etf_indicators import fetch_etf_df, compute_indicators  # noqa: E402
from mini_chart import render_mini_ohlc, render_net_flow_svg  # noqa: E402

DB = ROOT / 'data' / 'holdings.db'
OUT = ROOT / 'docs'
NA = '<span class="na">&lt;NA&gt;</span>'

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","SF Pro Text",sans-serif;background:#0d1117;color:#e6edf3;line-height:1.55;padding:20px;max-width:1500px;margin:0 auto}
h1{font-size:24px;font-weight:600;border-bottom:1px solid #30363d;padding-bottom:10px;margin-bottom:16px}
h2{font-size:18px;margin:28px 0 12px;color:#58a6ff;border-left:3px solid #58a6ff;padding-left:10px}
h3{font-size:15px;margin:18px 0 8px;color:#c9d1d9}
nav{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 14px;margin-bottom:16px;font-size:13px;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
nav a{color:#58a6ff;margin-right:14px;text-decoration:none}
nav a:hover{text-decoration:underline}
nav a.cur{color:#fff;font-weight:600}
.freshness{font-size:12px;color:#8b949e;white-space:nowrap}
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

/* ---- 大型 metric cards (新版) ---- */
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:14px 0}
.metric{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px;font-size:12px;position:relative}
.metric .label{color:#8b949e;font-size:12px;display:flex;align-items:center;gap:6px}
.metric .v{font-size:26px;font-weight:700;color:#58a6ff;display:block;margin-top:6px;line-height:1.1;font-variant-numeric:tabular-nums}
.metric.pos .v{color:#3fb950}.metric.neg .v{color:#f85149}.metric.warn .v{color:#d29922}.metric.info .v{color:#a371f7}
.metric.lg .v{font-size:30px}
.metric .sub{color:#6e7681;font-size:11px;margin-top:4px}

/* ---- action pill (加碼 / 減碼 / 新增 / 出清) ---- */
.pill{display:inline-block;padding:2px 9px;border-radius:4px;font-size:11px;font-weight:600;border:1px solid transparent}
.pill-add{background:rgba(63,185,80,.15);color:#3fb950;border-color:rgba(63,185,80,.3)}
.pill-cut{background:rgba(248,81,73,.15);color:#f85149;border-color:rgba(248,81,73,.3)}
.pill-up{background:rgba(63,185,80,.15);color:#3fb950;border-color:rgba(63,185,80,.3)}
.pill-down{background:rgba(210,153,34,.15);color:#d29922;border-color:rgba(210,153,34,.3)}
.pill-new{background:rgba(31,111,235,.15);color:#58a6ff;border-color:rgba(31,111,235,.3)}
.pill-flat{background:rgba(110,118,129,.15);color:#8b949e;border-color:rgba(110,118,129,.3)}

/* ---- bar 進度條 (table cell 內) ---- */
.bar{display:inline-block;height:6px;background:#1f6feb;border-radius:3px;vertical-align:middle;min-width:1px}
.bar-cell{display:flex;align-items:center;gap:6px;justify-content:flex-start}
.bar-cell .bar{flex:0 0 auto}

/* ---- sparkline (近 N 日趨勢迷你 bar) ---- */
.sparkline{display:inline-flex;align-items:flex-end;gap:1px;height:18px;min-width:30px}
.sparkline span{width:3px;background:#30363d;border-radius:1px 1px 0 0}
.sparkline span.up{background:#3fb950}.sparkline span.down{background:#f85149}

/* ---- filter tabs ---- */
.filter-tabs{display:inline-flex;gap:6px;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:4px;margin:10px 0;flex-wrap:wrap}
.filter-tabs button{background:transparent;color:#8b949e;border:none;padding:6px 14px;border-radius:6px;font-size:13px;cursor:pointer;font-family:inherit}
.filter-tabs button:hover{color:#c9d1d9}
.filter-tabs button.cur{background:#1f6feb;color:#fff}

/* ---- 已存在 ---- */
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


# 全站共用一個 build 時間戳（UTC ISO）— 給每頁的 freshness chip + index 大字
BUILD_UTC = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
BUILD_UTC_ISO = BUILD_UTC.isoformat()

FRESHNESS_JS = """
(function(){
  function tick(){
    document.querySelectorAll('[data-build-utc]').forEach(function(el){
      var u = el.getAttribute('data-build-utc');
      var d = new Date(u);
      var now = new Date();
      var diffMin = Math.floor((now - d) / 60000);
      var diffH = diffMin / 60;
      var diffD = diffH / 24;
      var rel;
      if (diffMin < 1) rel = '剛剛';
      else if (diffMin < 60) rel = diffMin + ' 分鐘前';
      else if (diffH < 24) rel = Math.floor(diffH) + ' 小時前';
      else rel = Math.floor(diffD) + ' 天前';

      var color = '#3fb950';      // 綠 < 12h
      if (diffH >= 12) color = '#d29922';   // 黃 12h-3d
      if (diffD >= 3)  color = '#f85149';   // 紅 > 3d

      var local = d.toLocaleString('zh-TW', {hour12:false});
      el.innerHTML = '<span style="color:' + color + '">●</span> ' +
                     '<span title="' + local + ' (本機時區)">' + rel + '</span>';
    });
  }
  document.addEventListener('DOMContentLoaded', function(){
    tick();
    setInterval(tick, 60000);   // 每分鐘更新「N 分鐘前」
  });
})();
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
    nav_links = ' '.join(
        f'<a href="{base}{p}" class="{"cur" if p == current else ""}">{n}</a>'
        for p, n in pages
    )
    nav_freshness = f'<span class="freshness" data-build-utc="{BUILD_UTC_ISO}">●</span>'
    return f'''<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
<script>{SORT_JS}</script>
<script>{FRESHNESS_JS}</script>
<script>{FILTER_TABS_JS}</script>
</head><body>
<nav><span class="nav-links">{nav_links}</span>{nav_freshness}</nav>
<h1>{title}</h1>
'''


def foot(latest_date: str | None) -> str:
    return f'''<div class="foot">資料最新日期 {latest_date or NA}　·
頁面生成 {BUILD_UTC.strftime('%Y-%m-%d %H:%M')} UTC　·
<a href="https://github.com/Simon99/active-etf-tracker">原始碼</a>　·
<a href="https://github.com/Simon99/active-etf-tracker/actions">Actions 歷史</a></div>
</body></html>'''


def fmt_num(v, suffix=''):
    if v is None:
        return NA
    if isinstance(v, float):
        return f'{v:,.2f}{suffix}'
    return f'{v:,}{suffix}'


def fmt_pct(v):
    return NA if v is None else f'{v:.2f}%'


# ───────────────── 共用 render helpers ─────────────────
def metric_card(label: str, value: str, cls: str = '', sub: str = '', emoji: str = '') -> str:
    em = f'<span>{emoji}</span> ' if emoji else ''
    sub_html = f'<div class="sub">{sub}</div>' if sub else ''
    return (f'<div class="metric {cls}"><div class="label">{em}{label}</div>'
            f'<span class="v">{value}</span>{sub_html}</div>')


def pill(action: str) -> str:
    """加碼/減碼/新增/出清/不變 → 帶色 pill"""
    cls = {
        '加碼': 'pill-add', '減碼': 'pill-down',
        '新增': 'pill-new', '出清': 'pill-cut',
        '不變': 'pill-flat',
    }.get(action, 'pill-flat')
    return f'<span class="pill {cls}">{action}</span>'


def bar_cell(percent: float, max_pct: float = 10.0, txt: str = '') -> str:
    """權重比視覺化（max_pct 用來把最大值映射到 100% 寬，bar 最大 120px）"""
    if percent is None or percent <= 0:
        width = 0
    else:
        width = min(120, int(percent / max_pct * 120))
    color = '#1f6feb' if percent < max_pct * 0.5 else '#a371f7' if percent < max_pct * 0.8 else '#d29922'
    txt = txt or f'{percent:.2f}%'
    return (f'<div class="bar-cell"><span class="bar" '
            f'style="width:{width}px;background:{color}"></span>'
            f'<span style="color:#c9d1d9">{txt}</span></div>')


def clean_etf_name(name: str | None) -> str:
    """剝掉「主動式」「主動」前綴"""
    if not name:
        return ''
    for prefix in ('主動式', '主動'):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def sparkline(values: list, max_h: int = 18) -> str:
    """近 N 日 mini bar chart。values list 含 None/數值。"""
    if not values or all(v is None for v in values):
        return '<span class="mute" style="font-size:10px">N/A</span>'
    nums = [v if v is not None else 0 for v in values]
    if all(v == 0 for v in nums):
        return ''.join(f'<span style="height:1px"></span>' for _ in nums)
    mx = max(abs(v) for v in nums) or 1
    spans = []
    for v in nums:
        if v is None:
            spans.append('<span style="height:2px;background:#30363d"></span>')
            continue
        h = max(2, int(abs(v) / mx * max_h))
        cls = 'up' if v >= 0 else 'down'
        spans.append(f'<span class="{cls}" style="height:{h}px"></span>')
    return f'<span class="sparkline">{"".join(spans)}</span>'


FILTER_TABS_JS = """
function setupFilterTabs(tabsId, tableId) {
  var tabs = document.getElementById(tabsId);
  var table = document.getElementById(tableId);
  if (!tabs || !table) return;
  tabs.querySelectorAll('button').forEach(function(btn) {
    btn.addEventListener('click', function() {
      tabs.querySelectorAll('button').forEach(function(b){b.classList.remove('cur');});
      btn.classList.add('cur');
      var f = btn.getAttribute('data-filter');
      table.querySelectorAll('tbody tr').forEach(function(tr) {
        if (f === 'all' || tr.getAttribute('data-action') === f) {
          tr.style.display = '';
        } else {
          tr.style.display = 'none';
        }
      });
    });
  });
}
"""


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
<div class="metric">上次自動更新
  <span class="v" data-build-utc="{BUILD_UTC_ISO}" style="font-size:14px">●</span>
  <small style="color:#8b949e;display:block;margin-top:4px;font-size:11px">{BUILD_UTC.strftime('%Y-%m-%d %H:%M')} UTC</small>
</div>
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
    html = [head('每日成分股快照', 'daily.html', base)]
    if not latest_date:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    html.append('<p class="mute" style="margin:-8px 0 16px">查看特定日期的完整持股清單（切換 ETF 看不同基金）</p>')

    # 取所有有資料的日期 + ETF
    dates = [r[0] for r in con.execute('SELECT DISTINCT date FROM holdings ORDER BY date DESC LIMIT 30')]
    etf_rows = con.execute('''
        SELECT DISTINCT h.etf_id, m.etf_name FROM holdings h
        LEFT JOIN etf_meta m USING(etf_id)
        WHERE h.date=?
        ORDER BY h.etf_id
    ''', (latest_date,)).fetchall()
    etfs = [(e, n or e) for e, n in etf_rows]

    # 預設選最大 AUM 的 ETF（若無 snapshot 就用第一個）
    default_etf = None
    if etfs:
        biggest = con.execute('''
            SELECT etf_id FROM fund_snapshot
            WHERE date=(SELECT MAX(date) FROM fund_snapshot)
            ORDER BY total_assets DESC NULLS LAST LIMIT 1
        ''').fetchone()
        default_etf = (biggest[0] if biggest else etfs[0][0])

    # 控制列：日期 + ETF 兩個 dropdown
    html.append('<div style="display:flex;gap:12px;align-items:center;margin:12px 0 16px;flex-wrap:wrap">')
    html.append('<label style="color:#8b949e;font-size:13px">日期：'
                '<select id="dateSel" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:5px 10px;font-size:13px">')
    for d in dates:
        sel = ' selected' if d == latest_date else ''
        html.append(f'<option value="{d}"{sel}>{d}</option>')
    html.append('</select></label>')
    html.append('<label style="color:#8b949e;font-size:13px">ETF：'
                '<select id="etfSel" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:5px 10px;font-size:13px;min-width:240px">')
    for e, n in etfs:
        sel = ' selected' if e == default_etf else ''
        html.append(f'<option value="{e}"{sel}>{e}　{n}</option>')
    html.append('</select></label>')
    html.append('<span class="mute" style="font-size:11px">日期切換需要該日 ETF 有資料；空 banner 即代表該日未抓到</span>')
    html.append('</div>')

    # 為每個 (date, etf) 組合預先 render 一個 section（display:none 切換）
    # 但這會爆量 — 限定 default_etf × 所有 dates + latest_date × 所有 ETFs，
    # 點到沒 pre-render 的組合時 JS 顯示 placeholder
    html.append('<div id="snapshots">')

    rendered_combos = set()

    def _render_snapshot(date, etf_id, etf_name, hide=True):
        rows = con.execute('''
            SELECT stock_id, stock_name, shares, weight
            FROM holdings WHERE date=? AND etf_id=?
            ORDER BY weight DESC
        ''', (date, etf_id)).fetchall()
        if not rows:
            return f'<div class="snapshot" data-date="{date}" data-etf="{etf_id}" style="display:{"none" if hide else "block"}"><div class="banner">{date} / {etf_id} 無資料。</div></div>'

        weights = [r[3] or 0 for r in rows]
        total_w = sum(weights)
        top5 = sum(sorted(weights, reverse=True)[:5])
        max_w = max(weights)
        max_pct_for_bar = max_w  # 把最大持股映射成滿格

        out = [f'<div class="snapshot" data-date="{date}" data-etf="{etf_id}" style="display:{"none" if hide else "block"}">']
        out.append('<div class="metric-grid">')
        out.append(metric_card('權重加總', f'{total_w:.2f}%',
                               'pos' if total_w > 90 else 'warn' if total_w > 70 else 'neg',
                               sub=f'剩 {100-total_w:.2f}% 為現金/期貨'))
        out.append(metric_card('前 5 大佔比', f'{top5:.2f}%', 'info',
                               sub=f'共 {len(rows)} 檔持股'))
        out.append(metric_card('最大持股', f'{max_w:.2f}%', 'warn' if max_w > 15 else '',
                               sub=rows[0][1] or rows[0][0]))
        out.append('</div>')

        out.append(f'<h3 style="margin-top:18px">{etf_id}　{etf_name}　<span class="mute" style="font-size:12px;font-weight:400">{date}</span></h3>')
        out.append('<table class="sortable"><thead><tr>'
                   '<th>代號</th><th>名稱</th><th>股數</th>'
                   '<th>權重 %</th><th>權重比視覺</th></tr></thead><tbody>')
        for sid, sname, sh, w in rows:
            out.append(f'<tr>'
                       f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                       f'<td>{sname or NA}</td>'
                       f'<td data-sort="{sh or 0}">{fmt_num(sh)}</td>'
                       f'<td data-sort="{w or 0}">{fmt_pct(w)}</td>'
                       f'<td>{bar_cell(w or 0, max_pct=max_pct_for_bar, txt="")}</td>'
                       f'</tr>')
        out.append('</tbody></table>')
        out.append('</div>')
        return '\n'.join(out)

    # 對所有可用 (date, etf) 組合都 pre-render；資料量不大（22 ETF × 2 日 ≈ 44 sections）
    for d in dates:
        for e, n in etfs:
            if (d, e) in rendered_combos:
                continue
            rendered_combos.add((d, e))
            is_default = (d == latest_date and e == default_etf)
            html.append(_render_snapshot(d, e, n, hide=not is_default))
    html.append('</div>')

    # JS 切換 snapshot
    html.append('''<script>
document.addEventListener('DOMContentLoaded', function(){
  var d = document.getElementById('dateSel');
  var e = document.getElementById('etfSel');
  function show(){
    var dv = d.value, ev = e.value;
    document.querySelectorAll('.snapshot').forEach(function(s){
      s.style.display = (s.dataset.date===dv && s.dataset.etf===ev) ? 'block' : 'none';
    });
  }
  d.addEventListener('change', show);
  e.addEventListener('change', show);
});
</script>''')

    html.append(foot(latest_date))
    return '\n'.join(html)


def page_changes(con, latest_date, base=''):
    html = [head(f'持股異動偵測', 'changes.html', base)]
    if not latest_date:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    html.append('<p class="mute" style="margin:-8px 0 16px">今日 vs 前一交易日的成分股變化</p>')

    prev = con.execute('SELECT MAX(date) FROM holdings WHERE date < ?', (latest_date,)).fetchone()[0]
    if not prev:
        html.append(f'<div class="banner">需累積至少 2 個交易日資料才能比對。目前只有 {latest_date} 一天。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    rows = con.execute('''
        WITH curr AS (SELECT etf_id, stock_id, stock_name, shares, weight FROM holdings WHERE date=?),
             prev AS (SELECT etf_id, stock_id, shares AS sh_prev, weight AS w_prev FROM holdings WHERE date=?)
        SELECT COALESCE(c.etf_id, p.etf_id) AS etf,
               COALESCE(c.stock_id, p.stock_id) AS sid,
               COALESCE(c.stock_name, '') AS sname,
               COALESCE(c.shares, 0) AS sh,
               COALESCE(c.weight, 0) AS w,
               COALESCE(p.sh_prev, 0) AS sh_p,
               COALESCE(p.w_prev, 0) AS w_p
        FROM curr c FULL OUTER JOIN prev p ON c.etf_id=p.etf_id AND c.stock_id=p.stock_id
    ''', (latest_date, prev)).fetchall()

    # 分類統計 + 取近 5 日權重序列 for sparkline
    last5_dates = [r[0] for r in con.execute(
        'SELECT DISTINCT date FROM holdings WHERE date<=? ORDER BY date DESC LIMIT 5', (latest_date,)
    )]
    last5_dates.reverse()   # 由舊到新

    counts = {'新增': 0, '出清': 0, '加碼': 0, '減碼': 0, '不變': 0}
    table_rows = []
    for etf, sid, sname, sh, w, sh_p, w_p in rows:
        sh = sh or 0
        sh_p = sh_p or 0
        diff_sh = sh - sh_p
        diff_w = (w or 0) - (w_p or 0)
        if sh_p == 0 and sh > 0:
            action = '新增'
        elif sh > 0 and sh_p > 0 and diff_sh == 0:
            action = '不變'
        elif sh == 0 and sh_p > 0:
            action = '出清'
        elif diff_sh > 0:
            action = '加碼'
        elif diff_sh < 0:
            action = '減碼'
        else:
            action = '不變'
        counts[action] += 1
        # 近 5 日權重 sparkline
        ts_rows = con.execute(
            'SELECT date, weight FROM holdings WHERE etf_id=? AND stock_id=? AND date IN ({})'.format(
                ','.join('?' * len(last5_dates))),
            (etf, sid, *last5_dates)
        ).fetchall()
        ts_map = {d: w for d, w in ts_rows}
        spark_vals = [ts_map.get(d) for d in last5_dates]
        table_rows.append((etf, sid, sname, sh, sh_p, diff_sh, w, w_p, diff_w, action, spark_vals))

    # 5 個 metric cards
    html.append('<div class="metric-grid">')
    html.append(metric_card('新增', str(counts['新增']), 'info',
                            emoji='🟢' if counts['新增'] else '⚪'))
    html.append(metric_card('出清', str(counts['出清']), 'neg',
                            emoji='🔴' if counts['出清'] else '⚪'))
    html.append(metric_card('加碼', str(counts['加碼']), 'pos',
                            emoji='📈' if counts['加碼'] else '⚪'))
    html.append(metric_card('減碼', str(counts['減碼']), 'warn',
                            emoji='📉' if counts['減碼'] else '⚪'))
    html.append(metric_card('不變', str(counts['不變']), 'mute'))
    html.append('</div>')

    # ETF dropdown filter
    etfs_in_data = sorted(set(r[0] for r in table_rows))
    html.append(f'<div style="margin:18px 0 8px">'
                f'<span style="color:#8b949e;font-size:13px">比對 <b style="color:#c9d1d9">{prev}</b> → '
                f'<b style="color:#c9d1d9">{latest_date}</b>&nbsp;&nbsp;</span>'
                f'<label style="color:#8b949e;font-size:13px;margin-left:14px">ETF：'
                f'<select id="etfFilter" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:5px 10px;font-size:13px">'
                f'<option value="all">全部 ({len(etfs_in_data)} 檔)</option>')
    for e in etfs_in_data:
        html.append(f'<option value="{e}">{e}</option>')
    html.append('</select></label></div>')

    # Filter tabs
    html.append('<div class="filter-tabs" id="actionTabs">')
    total = sum(counts.values())
    html.append(f'<button class="cur" data-filter="all">全部 ({total})</button>')
    for act in ['新增', '加碼', '減碼', '出清', '不變']:
        if counts[act]:
            html.append(f'<button data-filter="{act}">{act} ({counts[act]})</button>')
    html.append('</div>')

    # 表格
    html.append('<table id="changesTable" class="sortable"><thead><tr>'
                '<th>狀態</th><th>ETF</th><th>代號</th><th>名稱</th>'
                '<th>今日 %</th><th>前日 %</th><th>權重變動</th>'
                '<th>股數變動</th><th>近 5 日趨勢</th></tr></thead><tbody>')
    # 排序：先 |diff_sh| 大的，再加碼/減碼 在前
    table_rows.sort(key=lambda r: (r[9] == '不變', -abs(r[5])))
    for etf, sid, sname, sh, sh_p, diff_sh, w, w_p, diff_w, action, spark in table_rows:
        cls_diff = 'pos' if diff_sh > 0 else ('neg' if diff_sh < 0 else 'mute')
        diff_w_cls = 'pos' if diff_w > 0 else ('neg' if diff_w < 0 else 'mute')
        html.append(f'<tr data-action="{action}" data-etf="{etf}">'
                    f'<td>{pill(action)}</td>'
                    f'<td><a href="{base}etfs/{etf}.html">{etf}</a></td>'
                    f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                    f'<td>{sname or NA}</td>'
                    f'<td>{fmt_pct(w)}</td>'
                    f'<td class="mute">{fmt_pct(w_p)}</td>'
                    f'<td class="{diff_w_cls}" data-sort="{diff_w}">{diff_w:+.2f}%</td>'
                    f'<td class="{cls_diff}" data-sort="{diff_sh}">{diff_sh:+,}</td>'
                    f'<td>{sparkline(spark)}</td>'
                    f'</tr>')
    html.append('</tbody></table>')

    # 啟用 filter tabs + ETF dropdown（合併兩 filter 的統一 handler）
    html.append('''<script>
document.addEventListener('DOMContentLoaded', function(){
  var table = document.getElementById('changesTable');
  var tabs = document.getElementById('actionTabs');
  var sel = document.getElementById('etfFilter');
  var st = {action: 'all', etf: 'all'};
  function apply(){
    table.querySelectorAll('tbody tr').forEach(function(tr){
      var okA = (st.action === 'all') || (tr.getAttribute('data-action') === st.action);
      var okE = (st.etf === 'all') || (tr.getAttribute('data-etf') === st.etf);
      tr.style.display = (okA && okE) ? '' : 'none';
    });
  }
  tabs.querySelectorAll('button').forEach(function(btn){
    btn.addEventListener('click', function(){
      tabs.querySelectorAll('button').forEach(function(b){b.classList.remove('cur');});
      btn.classList.add('cur');
      st.action = btn.getAttribute('data-filter');
      apply();
    });
  });
  sel.addEventListener('change', function(){
    st.etf = sel.value;
    apply();
  });
});
</script>''')

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
    html = [head('多家投信同步加碼', 'momentum.html', base)]
    if not latest_date:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    n_etf_universe = con.execute(
        'SELECT COUNT(DISTINCT etf_id) FROM holdings WHERE date=?', (latest_date,)
    ).fetchone()[0]

    html.append(f'<p class="mute" style="margin:-8px 0 16px">'
                f'跨 {n_etf_universe} 檔主動式 ETF，偵測短期內被多家投信同步增持的個股</p>')

    n_days = con.execute('SELECT COUNT(DISTINCT date) FROM holdings').fetchone()[0]
    if n_days < 2:
        html.append(f'<div class="banner">需累積至少 2 個交易日資料。目前 {n_days} 天。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    # 取 N 天前的日期（N = 觀察窗口）
    dates_all = [r[0] for r in con.execute('SELECT DISTINCT date FROM holdings ORDER BY date DESC')]
    # 預設找最早 ~5 天前的可用日期，不夠就用最早的
    idx = min(5, len(dates_all) - 1)
    cmp_date = dates_all[idx] if idx < len(dates_all) else dates_all[-1]
    # 實際時間差 (用日期差不是 dataframe index)
    import datetime as _dt
    actual_days = (_dt.date.fromisoformat(latest_date) - _dt.date.fromisoformat(cmp_date)).days
    window_days = actual_days
    min_etf_default = 2  # 預設 ≥2 家

    # 控制列
    html.append('<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:12px 0">')
    html.append('<label style="color:#8b949e;font-size:13px">觀察天數：'
                '<select id="winSel" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:5px 10px;font-size:13px">')
    for n in [3, 5, 7, 14]:
        sel = ' selected' if n == window_days else ''
        avail = ' (不足)' if n > len(dates_all) - 1 else ''
        html.append(f'<option value="{n}"{sel}>{n} 天{avail}</option>')
    html.append('</select></label>')
    html.append('<label style="color:#8b949e;font-size:13px">最少幾家：'
                '<select id="minSel" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:5px 10px;font-size:13px">')
    for n in [2, 3, 5, 8]:
        sel = ' selected' if n == min_etf_default else ''
        html.append(f'<option value="{n}"{sel}>≥ {n} 家</option>')
    html.append('</select></label>')
    html.append('<span class="mute" style="font-size:11px">JS 純前端 filter（不重新 query）</span>')
    html.append('</div>')

    # color legend
    html.append('<div style="display:flex;gap:14px;flex-wrap:wrap;margin:10px 0 16px;font-size:12px;color:#8b949e">'
                '<span><span style="display:inline-block;width:12px;height:12px;background:#d29922;border-radius:50%;vertical-align:middle"></span> ≥ 8 家</span>'
                '<span><span style="display:inline-block;width:12px;height:12px;background:#f0883e;border-radius:50%;vertical-align:middle"></span> 5-7 家</span>'
                '<span><span style="display:inline-block;width:12px;height:12px;background:#3fb950;border-radius:50%;vertical-align:middle"></span> 3-4 家</span>'
                '<span><span style="display:inline-block;width:12px;height:12px;background:#a371f7;border-radius:50%;vertical-align:middle"></span> 2 家</span>'
                '</div>')

    # 對每個 stock，找出在 (cmp_date, latest_date) 區間內，哪些 ETF 真的「加碼」(shares 增加)
    # 不用 weight，避免「淨值跌導致 weight 上升但 shares 沒動」的偽加碼
    rows = con.execute('''
        WITH curr AS (SELECT etf_id, stock_id, stock_name, weight AS w_curr, shares AS sh_curr FROM holdings WHERE date=?),
             base AS (SELECT etf_id, stock_id, weight AS w_base, shares AS sh_base FROM holdings WHERE date=?)
        SELECT c.stock_id, c.stock_name,
               c.etf_id,
               c.w_curr - COALESCE(b.w_base, 0) AS w_diff,
               c.sh_curr - COALESCE(b.sh_base, 0) AS sh_diff
        FROM curr c LEFT JOIN base b ON c.etf_id=b.etf_id AND c.stock_id=b.stock_id
        WHERE c.sh_curr > COALESCE(b.sh_base, 0)
    ''', (latest_date, cmp_date)).fetchall()

    # 各 ETF 名稱
    etf_names = dict(con.execute('SELECT etf_id, etf_name FROM etf_meta').fetchall())

    # ── 計算逐日吸量（最近 5 個交易日）給卡片 bar chart 用 ──
    last_n_dates = [r[0] for r in con.execute(
        'SELECT DISTINCT date FROM holdings WHERE date<=? ORDER BY date DESC LIMIT 6',
        (latest_date,)
    )]
    last_n_dates.reverse()   # oldest first
    # n_dates-1 pairs of consecutive days
    from collections import defaultdict
    daily_absorbed_per_stock = defaultdict(lambda: [0] * (len(last_n_dates) - 1))
    for i in range(1, len(last_n_dates)):
        prev_d, curr_d = last_n_dates[i - 1], last_n_dates[i]
        diff_rows = con.execute('''
            WITH c AS (SELECT etf_id, stock_id, shares FROM holdings WHERE date=?),
                 p AS (SELECT etf_id, stock_id, shares AS sh_p FROM holdings WHERE date=?)
            SELECT c.stock_id, SUM(c.shares - COALESCE(p.sh_p, 0)) AS absorbed
            FROM c LEFT JOIN p ON c.etf_id=p.etf_id AND c.stock_id=p.stock_id
            WHERE c.shares > COALESCE(p.sh_p, 0)
            GROUP BY c.stock_id
        ''', (curr_d, prev_d)).fetchall()
        for sid, v in diff_rows:
            daily_absorbed_per_stock[sid][i - 1] = int(v or 0)

    # 按 stock_id 聚合 (含股數差)
    from collections import defaultdict as _defdict  # noqa
    by_stock = defaultdict(list)
    sname_map = {}
    sh_added_map = defaultdict(int)
    for sid, sname, etf, w_diff, sh_diff in rows:
        by_stock[sid].append((etf, w_diff, sh_diff))
        sname_map[sid] = sname
        if sh_diff and sh_diff > 0:
            sh_added_map[sid] += sh_diff

    # 過濾 ≥ min_etf_default + 排序
    aggregated = []
    for sid, etf_list in by_stock.items():
        n = len(etf_list)
        if n < 2:
            continue
        sum_w = sum(d[1] for d in etf_list)
        max_w = max(d[1] for d in etf_list)
        aggregated.append((sid, sname_map.get(sid, ''), n, sum_w, max_w, etf_list))
    aggregated.sort(key=lambda x: (-x[2], -x[3]))

    if not aggregated:
        html.append('<div class="banner">尚無 ≥ 2 家同步加碼的個股。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    # 摘要 banner
    n_total = len(aggregated)
    html.append(f'<div class="banner" style="border-left-color:#3fb950">'
                f'過去 <b style="color:#3fb950">{window_days} 天</b> 內，'
                f'找到 <b style="color:#58a6ff">{n_total} 檔</b>個股被 '
                f'<b style="color:#3fb950">{min_etf_default} 家以上</b> 投信同步增持</div>')

    # 卡片 grid
    def _color(n):
        if n >= 8: return '#d29922'
        if n >= 5: return '#f0883e'
        if n >= 3: return '#3fb950'
        return '#a371f7'

    # 並行抓 mini chart (yfinance) — N 卡片 × 1 call
    from concurrent.futures import ThreadPoolExecutor
    # 每個 bar 對應的日期 label (curr_date of each pair，MM-DD 格式)
    absorbed_labels = [d[5:] for d in last_n_dates[1:]] if len(last_n_dates) >= 2 else []
    mini_cache = {}
    def _mini(sid):
        try:
            return sid, render_mini_ohlc(sid,
                                          daily_absorbed=daily_absorbed_per_stock.get(sid),
                                          absorbed_date_labels=absorbed_labels)
        except Exception:
            return sid, {'svg': '', 'absorbed_svg': '', 'stats': None, 'ticker': None}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for sid, mini in ex.map(_mini, [r[0] for r in aggregated]):
            mini_cache[sid] = mini

    html.append('<div id="momentumGrid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:12px">')
    for sid, sname, n, sum_w, max_w, etf_list in aggregated:
        color = _color(n)
        # etf_list 內為 (etf, w_diff, sh_diff) — 排序按 w_diff
        etf_list_sorted = sorted(etf_list, key=lambda x: -x[1])
        max_diff = etf_list_sorted[0][1] or 0.01
        top3 = etf_list_sorted[:3]
        rest = etf_list_sorted[3:]

        mini = mini_cache.get(sid, {})
        mini_svg = mini.get('svg', '')
        absorbed_svg = mini.get('absorbed_svg', '')
        stats = mini.get('stats') or {}

        # 吸量比率配色
        ratio_html = ''
        r = stats.get('ratio_pct') if stats else None
        if r is not None:
            if r >= 10:
                rc, rlabel = '#f85149', '大量吸籌'
            elif r >= 3:
                rc, rlabel = '#d29922', '顯著'
            elif r >= 1:
                rc, rlabel = '#3fb950', '中等'
            else:
                rc, rlabel = '#8b949e', '輕微'
            ratio_html = (f'<div style="font-size:11px"><span class="mute">吸量比</span> '
                          f'<b style="color:{rc}">{r:.2f}%</b> '
                          f'<span style="color:{rc};font-size:10px">({rlabel})</span></div>')

        # 趨勢方向：日吸量是漸增還是漸減
        trend_html = ''
        daily = daily_absorbed_per_stock.get(sid, [])
        if daily and sum(daily) > 0:
            half = len(daily) // 2
            early = sum(daily[:half]) if half else 0
            late = sum(daily[half:]) if half else sum(daily)
            if late > early * 1.3:
                trend_html = '<span style="color:#3fb950;font-size:10px">📈 加速</span>'
            elif early > late * 1.3:
                trend_html = '<span style="color:#d29922;font-size:10px">📉 衰退</span>'
            else:
                trend_html = '<span class="mute" style="font-size:10px">→ 持平</span>'

        # 5 日股價漲跌
        chg5d_html = ''
        if stats:
            ch = stats.get('chg_pct_5d', 0)
            cc = '#3fb950' if ch >= 0 else '#f85149'
            chg5d_html = (f'<span style="color:{cc};font-size:10px;margin-left:4px">'
                          f'5日 {"+" if ch >= 0 else ""}{ch:.2f}%</span>')

        # total absorbed
        total_absorbed = stats.get('total_absorbed', 0) if stats else 0
        market_vol_5d = stats.get('market_vol_5d', 0) if stats else 0

        html.append(f'<div class="mom-card" data-n="{n}" '
                    f'style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:10px">'
                    f'<div>'
                    f'<div style="font-size:18px;font-weight:700"><a href="{base}stocks/{sid}.html">{sid}</a>{chg5d_html}</div>'
                    f'<div class="mute" style="font-size:13px">{sname or NA}</div>'
                    f'</div>'
                    f'<div style="color:{color};border:2px solid {color};'
                    f'border-radius:50%;width:50px;height:50px;display:flex;flex-direction:column;'
                    f'align-items:center;justify-content:center;font-weight:700;flex-shrink:0">'
                    f'<div style="font-size:18px">{n}</div>'
                    f'<div style="font-size:9px">家</div>'
                    f'</div></div>')

        # K 圖 + 吸量趨勢圖 並排
        if mini_svg or absorbed_svg:
            html.append('<div style="display:flex;gap:8px;margin-bottom:10px">'
                        '<div style="flex:1;text-align:center">'
                        '<div class="mute" style="font-size:10px;margin-bottom:2px">近 5 日 K + 量</div>'
                        f'{mini_svg}'
                        '</div>'
                        '<div style="flex:1;text-align:center">'
                        '<div class="mute" style="font-size:10px;margin-bottom:2px">'
                        f'5 日吸量趨勢 {trend_html}</div>'
                        f'{absorbed_svg}'
                        '</div></div>')

        # 吸量 + 市場量比較
        sh_added = sh_added_map.get(sid)
        absorbed_html = ''
        if total_absorbed:
            mkt_str = f'{market_vol_5d/1e6:.1f}M' if market_vol_5d >= 1e6 else f'{market_vol_5d:,}'
            absorbed_html = (
                f'<div style="background:rgba(63,185,80,.06);border:1px solid #30363d;border-radius:6px;'
                f'padding:6px 10px;margin-bottom:10px;font-size:11px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px">'
                f'<div><span class="mute">5日總吸</span> <b style="color:#3fb950">{total_absorbed:,}</b> 股</div>'
                f'<div><span class="mute">5日市場</span> <b>{mkt_str}</b></div>'
                f'{ratio_html}'
                f'</div>'
            )
        html.append(absorbed_html)

        # 合計增幅 + 最大單筆 + 觀察窗口的累積加碼
        sh_html = f'<div><span class="mute">窗口加碼</span> <b style="color:#3fb950">+{sh_added:,}</b> 股</div>' if sh_added else ''
        html.append(f'<div style="display:flex;flex-wrap:wrap;gap:14px;margin-bottom:10px;font-size:12px">'
                    f'<div><span class="mute">合計增幅</span> '
                    f'<b style="color:#3fb950">+{sum_w:.2f}%</b></div>'
                    f'<div><span class="mute">最大單筆</span> '
                    f'<b style="color:#3fb950">+{max_w:.2f}%</b></div>'
                    f'{sh_html}'
                    f'</div>'
                    f'<div style="display:flex;flex-direction:column;gap:6px">')
        def _etf_row(etf, w_diff, extra_style=''):
            bar_w = int(w_diff / max_diff * 180)
            ename_clean = clean_etf_name(etf_names.get(etf, ''))[:8]
            etf_short = etf[2:] if etf.startswith('00') else etf
            ename_label = f'{etf_short} {ename_clean}'.strip()
            return (f'<div style="display:flex;align-items:center;gap:8px;font-size:11px;{extra_style}">'
                    f'<a href="{base}etfs/{etf}.html" '
                    f'style="min-width:135px;max-width:160px;overflow:hidden;'
                    f'text-overflow:ellipsis;white-space:nowrap" title="{ename_label}">{ename_label}</a>'
                    f'<div style="flex:1;background:#1c2128;border-radius:3px;height:6px;position:relative">'
                    f'<div style="position:absolute;left:0;top:0;bottom:0;width:{bar_w}px;'
                    f'background:linear-gradient(90deg,#3fb950,#58a6ff);border-radius:3px"></div></div>'
                    f'<span style="color:#3fb950;min-width:55px;text-align:right">+{w_diff:.2f}%</span>'
                    f'</div>')

        for etf, w_diff, _sh in top3:
            html.append(_etf_row(etf, w_diff))
        if rest:
            html.append(f'<details><summary class="mute" style="cursor:pointer;font-size:12px;text-align:center;padding:4px">▼ 展開全部 {n} 家</summary>')
            for etf, w_diff, _sh in rest:
                html.append(_etf_row(etf, w_diff, 'margin-top:4px'))
            html.append('</details>')
        html.append(f'</div>'
                    f'<div class="mute" style="font-size:10px;margin-top:10px;text-align:right">'
                    f'{cmp_date} → {latest_date}</div>'
                    f'</div>')
    html.append('</div>')

    # JS: minSel filter cards by data-n
    html.append('''<script>
document.addEventListener('DOMContentLoaded', function(){
  var ms = document.getElementById('minSel');
  var grid = document.getElementById('momentumGrid');
  if(ms && grid){
    ms.addEventListener('change', function(){
      var min = parseInt(ms.value, 10);
      grid.querySelectorAll('.mom-card').forEach(function(c){
        c.style.display = parseInt(c.dataset.n, 10) >= min ? '' : 'none';
      });
    });
  }
});
</script>''')

    html.append(foot(latest_date))
    return '\n'.join(html)


def page_radar(con, latest_date, base=''):
    html = [head('新增 / 賣出雷達', 'radar.html', base)]
    if not latest_date:
        html.append('<div class="banner">尚無資料。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    prev = con.execute('SELECT MAX(date) FROM holdings WHERE date < ?', (latest_date,)).fetchone()[0]
    n_etf_universe = con.execute(
        'SELECT COUNT(DISTINCT etf_id) FROM holdings WHERE date=?', (latest_date,)
    ).fetchone()[0]

    html.append(f'<p class="mute" style="margin:-8px 0 16px">'
                f'全部 {n_etf_universe} 檔主動式 ETF · '
                f'比對 {prev or "&lt;NA&gt;"} → {latest_date}</p>')

    if not prev:
        html.append(f'<div class="banner">需累積至少 2 個交易日資料。目前只有 {latest_date} 一天。</div>')
        html.append(foot(latest_date))
        return '\n'.join(html)

    # 新增 (D-1 沒 + D 有)
    new_rows = con.execute('''
        SELECT c.etf_id, c.stock_id, c.stock_name, c.shares, c.weight
        FROM holdings c LEFT JOIN holdings p
          ON p.etf_id=c.etf_id AND p.stock_id=c.stock_id AND p.date=?
        WHERE c.date=? AND p.stock_id IS NULL
        ORDER BY c.etf_id, c.weight DESC
    ''', (prev, latest_date)).fetchall()

    # 出清 (D-1 有 + D 沒)
    sold_rows = con.execute('''
        SELECT p.etf_id, p.stock_id, p.stock_name, p.shares, p.weight
        FROM holdings p LEFT JOIN holdings c
          ON c.etf_id=p.etf_id AND c.stock_id=p.stock_id AND c.date=?
        WHERE p.date=? AND c.stock_id IS NULL
        ORDER BY p.etf_id, p.weight DESC
    ''', (latest_date, prev)).fetchall()

    # 減持 (D-1 + D 都有，weight 降)
    cut_rows = con.execute('''
        SELECT c.etf_id, c.stock_id, c.stock_name,
               c.shares AS sh_c, p.shares AS sh_p,
               c.weight AS w_c, p.weight AS w_p
        FROM holdings c JOIN holdings p
          ON p.etf_id=c.etf_id AND p.stock_id=c.stock_id
        WHERE c.date=? AND p.date=? AND c.shares < p.shares
    ''', (latest_date, prev)).fetchall()

    # 分組：每個 ETF 的新增、出清、減持各幾筆
    from collections import defaultdict
    new_by_etf = defaultdict(list)
    for etf, sid, sname, sh, w in new_rows:
        new_by_etf[etf].append((sid, sname, sh, w))
    sold_by_etf = defaultdict(list)
    for etf, sid, sname, sh, w in sold_rows:
        sold_by_etf[etf].append((sid, sname, sh, w))
    cut_by_etf = defaultdict(list)
    for etf, sid, sname, sh_c, sh_p, w_c, w_p in cut_rows:
        cut_by_etf[etf].append((sid, sname, sh_c, sh_p, w_c, w_p))

    n_etf_with_new = len(new_by_etf)
    n_etf_with_sold = len(sold_by_etf) | len(cut_by_etf)  # noqa — placeholder
    n_etf_with_sold = len(set(list(sold_by_etf.keys()) + list(cut_by_etf.keys())))

    # 同步增 / 減 = 多家 ETF 同時對同一檔股票做相同動作
    from collections import Counter
    synced_new = Counter(sid for _e, sid, *_ in new_rows)
    synced_sold = Counter(sid for _e, sid, *_ in sold_rows)
    # 減持也算「同步減碼」一部分
    synced_cut = Counter(sid for _e, sid, *_ in cut_rows)
    synced_sold_or_cut = Counter()
    for sid, c in (synced_sold + synced_cut).items():
        synced_sold_or_cut[sid] = c

    n_synced_new = sum(1 for c in synced_new.values() if c >= 2)
    n_synced_sold = sum(1 for c in synced_sold_or_cut.values() if c >= 2)

    # ───────── 新增雷達 section ─────────
    html.append('<h2>🟢 新增雷達</h2>')
    html.append('<div class="metric-grid">')
    html.append(metric_card('有新增的 ETF', f'{n_etf_with_new} 檔', 'pos', emoji='🟢'))
    html.append(metric_card('新增個股筆數', f'{len(new_rows)} 筆', 'pos'))
    html.append(metric_card('多家同步新增', f'{n_synced_new} 檔', 'info', emoji='🎯',
                            sub='≥ 2 家 ETF 同時新增'))
    html.append('</div>')

    # 多家同步新增 list
    if n_synced_new:
        html.append('<h3 style="color:#3fb950">多家同步新增 (≥ 2 家)</h3>')
        sname_map = {sid: sname for _e, sid, sname, *_ in new_rows}
        synced_list = sorted([(c, sid) for sid, c in synced_new.items() if c >= 2], reverse=True)
        html.append('<table class="sortable"><thead><tr>'
                    '<th>排名</th><th>共幾家</th><th>個股</th><th>名稱</th></tr></thead><tbody>')
        for i, (n, sid) in enumerate(synced_list, 1):
            html.append(f'<tr><td>#{i}</td>'
                        f'<td><b style="color:#3fb950">{n}</b> 家</td>'
                        f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                        f'<td>{sname_map.get(sid, NA)}</td></tr>')
        html.append('</tbody></table>')

    # 各 ETF 新增明細卡片
    if new_by_etf:
        html.append('<h3>各 ETF 新增明細</h3>')
        html.append('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:10px">')
        for etf in sorted(new_by_etf.keys()):
            stocks = new_by_etf[etf]
            etf_meta = con.execute('SELECT etf_name FROM etf_meta WHERE etf_id=?', (etf,)).fetchone()
            ename = etf_meta[0] if etf_meta else ''
            html.append(f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
                        f'<div><a href="{base}etfs/{etf}.html" style="font-weight:600">{etf}</a> '
                        f'<span class="mute" style="font-size:12px">{ename}</span></div>'
                        f'<span class="pill pill-add">+{len(stocks)} 檔</span></div>'
                        f'<div style="display:flex;flex-wrap:wrap;gap:6px">')
            for sid, sname, sh, w in stocks:
                html.append(f'<a href="{base}stocks/{sid}.html" class="tag" '
                            f'style="background:rgba(63,185,80,.1);color:#3fb950;border:1px solid rgba(63,185,80,.2)">'
                            f'{sid} {sname or ""} <span class="mute">+{w:.2f}%</span></a>')
            html.append('</div></div>')
        html.append('</div>')
    else:
        html.append('<div class="banner">本日無新增。</div>')

    # ───────── 賣出雷達 section ─────────
    html.append('<h2 style="margin-top:32px">🔴 賣出雷達</h2>')
    html.append('<div class="metric-grid">')
    html.append(metric_card('有減碼的 ETF', f'{n_etf_with_sold} 檔', 'warn', emoji='🔴'))
    html.append(metric_card('移除個股', f'{len(sold_rows)} 筆', 'neg',
                            sub='完全出清'))
    html.append(metric_card('減持個股', f'{len(cut_rows)} 筆', 'warn',
                            sub='股數降低'))
    html.append(metric_card('多家同步減碼', f'{n_synced_sold} 檔', 'info', emoji='🎯',
                            sub='≥ 2 家 ETF 同時'))
    html.append('</div>')

    # 多家同步減碼 ranking
    if n_synced_sold:
        html.append('<h3 style="color:#f85149">多家同步減碼 (≥ 2 家，含出清 + 減持)</h3>')
        sname_map_all = {sid: sname for _e, sid, sname, *_ in (sold_rows + [(e, s, sn, c, p, wc, wp) for e, s, sn, c, p, wc, wp in cut_rows])}
        synced_list = sorted([(c, sid) for sid, c in synced_sold_or_cut.items() if c >= 2], reverse=True)
        # 算總減持百分比
        max_n = synced_list[0][0] if synced_list else 1
        html.append('<table class="sortable"><thead><tr>'
                    '<th>排名</th><th>共幾家</th><th>個股</th><th>名稱</th><th>視覺</th></tr></thead><tbody>')
        for i, (n, sid) in enumerate(synced_list[:20], 1):
            bar_w = int(n / max_n * 200)
            html.append(f'<tr><td>#{i}</td>'
                        f'<td><b style="color:#f85149">{n}</b> 家</td>'
                        f'<td><a href="{base}stocks/{sid}.html">{sid}</a></td>'
                        f'<td>{sname_map_all.get(sid, NA)}</td>'
                        f'<td><div class="bar-cell"><span class="bar" style="width:{bar_w}px;'
                        f'background:linear-gradient(90deg,#f85149,#d29922)"></span>'
                        f'<span class="mute" style="font-size:11px">{n} ETF</span></div></td>'
                        f'</tr>')
        html.append('</tbody></table>')

    # 出清明細
    if sold_rows:
        html.append('<h3>各 ETF 出清明細</h3>')
        html.append('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:10px">')
        for etf in sorted(sold_by_etf.keys()):
            stocks = sold_by_etf[etf]
            etf_meta = con.execute('SELECT etf_name FROM etf_meta WHERE etf_id=?', (etf,)).fetchone()
            ename = etf_meta[0] if etf_meta else ''
            html.append(f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
                        f'<div><a href="{base}etfs/{etf}.html" style="font-weight:600">{etf}</a> '
                        f'<span class="mute" style="font-size:12px">{ename}</span></div>'
                        f'<span class="pill pill-cut">-{len(stocks)} 檔</span></div>'
                        f'<div style="display:flex;flex-wrap:wrap;gap:6px">')
            for sid, sname, sh, w in stocks:
                html.append(f'<a href="{base}stocks/{sid}.html" class="tag" '
                            f'style="background:rgba(248,81,73,.1);color:#f85149;border:1px solid rgba(248,81,73,.2)">'
                            f'{sid} {sname or ""} <span class="mute">原 {w:.2f}%</span></a>')
            html.append('</div></div>')
        html.append('</div>')

    html.append(foot(latest_date))
    return '\n'.join(html)


def page_stock(con, sid, latest_date, base='../'):
    name_row = con.execute(
        'SELECT stock_name FROM holdings WHERE stock_id=? ORDER BY date DESC LIMIT 1', (sid,)
    ).fetchone()
    sname = (name_row[0] if name_row else '') or sid

    html = [head(f'{sid} {sname} — 技術分析 + ETF 持有狀況', '', base)]

    # ── 過去 5 日 ETF 整體加減碼 bar chart ──
    last_dates = [r[0] for r in con.execute(
        'SELECT DISTINCT date FROM holdings WHERE date<=? ORDER BY date DESC LIMIT 6',
        (latest_date,)
    )]
    last_dates.reverse()   # oldest first
    if len(last_dates) >= 2:
        daily_net = []
        for i in range(1, len(last_dates)):
            prev_d, curr_d = last_dates[i-1], last_dates[i]
            curr_rows = dict(con.execute(
                'SELECT etf_id, shares FROM holdings WHERE date=? AND stock_id=?',
                (curr_d, sid)
            ).fetchall())
            prev_rows = dict(con.execute(
                'SELECT etf_id, shares FROM holdings WHERE date=? AND stock_id=?',
                (prev_d, sid)
            ).fetchall())
            all_etfs = set(curr_rows) | set(prev_rows)
            net = sum((curr_rows.get(e) or 0) - (prev_rows.get(e) or 0) for e in all_etfs)
            daily_net.append(net)

        date_labels = [d[5:] for d in last_dates[1:]]
        total_net = sum(daily_net)
        n_pos = sum(1 for v in daily_net if v > 0)
        n_neg = sum(1 for v in daily_net if v < 0)

        html.append('<h2>📊 過去 5 日 ETF 整體加減碼</h2>')
        net_cls = 'pos' if total_net > 0 else ('neg' if total_net < 0 else 'mute')
        net_sign = '+' if total_net > 0 else ''
        html.append(f'<div class="banner">'
                    f'過去 <b>{len(daily_net)}</b> 個交易日內，所有主動式 ETF 對此股的整體加減碼：'
                    f'<b class="{net_cls}">{net_sign}{total_net:,} 股</b>　'
                    f'（加碼 <b class="pos">{n_pos}</b> 天 / 減碼 <b class="neg">{n_neg}</b> 天）'
                    f'</div>')
        html.append(f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;margin:8px 0">'
                    f'{render_net_flow_svg(daily_net, date_labels)}'
                    f'</div>')

    # 技術分析（candlestick + MA + KD + MACD）
    html.append('<h2>📈 技術分析（最近 2 年日線）</h2>')
    html.append(render_stock_chart(sid))

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

    # 規模警示（< 10 億）
    aum_warn = ''
    if aum is not None and aum < 1.0:
        aum_warn = ('<div class="banner" style="border-left-color:#f85149;background:rgba(248,81,73,.08)">'
                    f'⚠ 基金規模僅 <b>{aum:.2f} B</b>（不到 10 億），流動性可能不足，建議審慎評估</div>')
    elif aum is not None and aum < 5.0:
        aum_warn = ('<div class="banner" style="border-left-color:#d29922">'
                    f'ℹ 基金規模 <b>{aum:.2f} B</b>，規模偏小（< 50 億），請留意流動性</div>')
    if aum_warn:
        html.append(aum_warn)

    # ──── 技術指標 metric cards（從 yfinance 算）────
    df = fetch_etf_df(etf_id)
    ind = compute_indicators(df) if df is not None else {}

    def _fmt_signed(v, suffix='', decimals=2):
        if v is None:
            return NA
        sign = '+' if v >= 0 else ''
        return f'{sign}{v:.{decimals}f}{suffix}'

    def _ind_cls(v, pos_thr=0, neg_thr=0):
        if v is None:
            return ''
        if v > pos_thr:
            return 'pos'
        if v < neg_thr:
            return 'neg'
        return ''

    html.append('<h2>📊 即時技術指標</h2>')
    html.append('<div class="metric-grid">')
    if ind:
        # 收盤 + 漲跌
        chg_html = (f'<span style="color:{"#3fb950" if ind["chg"] >= 0 else "#f85149"}">'
                    f'{_fmt_signed(ind["chg"])} ({_fmt_signed(ind["chg_pct"], "%")})</span>'
                    f'<span class="mute" style="margin-left:8px">{ind["last_date"]}</span>')
        html.append(metric_card('收盤價', f'{ind["last_close"]:.2f}',
                                _ind_cls(ind['chg']), sub=chg_html))
        # 資產規模
        if aum is not None:
            html.append(metric_card('資產規模', f'{aum:.2f}B',
                                    'neg' if aum < 1.0 else ('warn' if aum < 5.0 else 'pos'),
                                    sub=f'{snap_date or "&lt;NA&gt;"} 資料'))
        # 布林位階
        if ind.get('bb_pos') is not None:
            bb_cls = ('neg' if ind['bb_label'] == '極高' else
                      'warn' if ind['bb_label'] == '偏高' else
                      'pos' if ind['bb_label'] == '極低' else '')
            html.append(metric_card('布林位階',
                                    f'{ind["bb_pos"]*100:.0f}%',
                                    bb_cls, emoji='📏',
                                    sub=ind['bb_label']))
        # BIAS20
        bias = ind.get('bias20')
        if bias is not None:
            bias_label = '超買警戒' if bias > 8 else '偏高' if bias > 3 else '中性' if abs(bias) <= 3 else '偏低' if bias > -8 else '超賣警戒'
            html.append(metric_card('BIAS20 (月線乖離)',
                                    f'{bias:+.2f}%',
                                    _ind_cls(bias, 3, -3),
                                    sub=bias_label))
        # RSI(14)
        rsi = ind.get('rsi')
        if rsi is not None:
            rsi_cls = ('neg' if ind['rsi_label'] == '超買區' else
                       'pos' if ind['rsi_label'] == '超賣區' else
                       'warn' if '偏' in ind['rsi_label'] else '')
            html.append(metric_card('RSI(14)', f'{rsi:.1f}', rsi_cls, sub=ind['rsi_label']))
        # MACD 柱
        osc = ind.get('osc')
        if osc is not None:
            macd_cls = 'pos' if osc > 0 else 'neg'
            html.append(metric_card('MACD 柱',
                                    f'{osc:+.3f}',
                                    macd_cls, sub=ind['macd_label']))
        # 成交額
        amt = ind.get('amount_5d_avg')
        if amt:
            html.append(metric_card('5 日均成交額',
                                    f'{amt/1e8:.2f} 億',
                                    sub='close × volume 估算'))
    else:
        # 沒指標 fallback 顯示既有 fund_snapshot
        html.append(metric_card('NAV', fmt_num(nav)))
        html.append(metric_card('基金規模 (B)', fmt_num(aum)))
        html.append(metric_card('受益權單位', fmt_num(units)))
    html.append(metric_card('持股數', str(hn) if hn is not None else NA, sub=f'快照 {snap_date or "&lt;NA&gt;"}'))
    html.append('</div>')

    html.append('<h2>📈 技術線型（最近 2 年日線）</h2>')
    html.append(render_chart(etf_id))

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
    # 個股頁含 yfinance fetch (chart) → 並行加速。每 worker 開獨立 sqlite 連線。
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time as _t

    def _render(sid):
        c = sqlite3.connect(DB)
        try:
            return sid, page_stock(c, sid, latest)
        finally:
            c.close()

    t0 = _t.time()
    n_done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in as_completed([ex.submit(_render, s) for s in stocks]):
            sid, html = fut.result()
            (OUT / 'stocks' / f'{sid}.html').write_text(html, encoding='utf-8')
            n_done += 1
            if n_done % 50 == 0:
                print(f'  個股頁 {n_done}/{len(stocks)} ({_t.time()-t0:.1f}s)', flush=True)
    print(f'  個股頁完成 {n_done}/{len(stocks)} 總耗時 {_t.time()-t0:.1f}s')

    print('━━━ 完成 ━━━')
    print(f'  6 主頁 + {len(etfs)} ETF 頁 + {len(stocks)} 個股頁')
    print(f'  → {OUT}/')
    con.close()


if __name__ == '__main__':
    main()
