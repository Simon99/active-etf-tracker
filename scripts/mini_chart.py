"""小型 inline SVG OHLC + Volume chart for momentum card。

每檔股票 5 交易日（K 線含上下引線 + 成交量柱），約 140×70 px。
另回傳「ETF 吸收量 / 5 日市場成交量」比率，用來判斷 ETF 對價格影響力。
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from stock_chart import fetch_data, _resolve_ticker  # noqa: E402


def fetch_stock_df(stock_id: str, n_days: int = 10):
    """fetcher with ticker fallback"""
    for cand in _resolve_ticker(stock_id):
        try:
            df = fetch_data(cand)
            if not df.empty:
                return df.tail(n_days), cand
        except Exception:
            continue
    return None, None


def render_mini_ohlc(stock_id: str, daily_absorbed: list | None = None,
                     absorbed_date_labels: list | None = None) -> dict:
    """回傳 {svg, stats, ticker}
    daily_absorbed = 5 日逐日 ETF 吸量 list（最舊到最新），用來算 ratio + 趨勢圖
    absorbed_date_labels = 每個 bar 對應的日期 (例如 ['05-15','05-16','05-17','05-18','05-19'])，
      若 None 則 fallback 用 D-N 相對標籤
    """
    df, ticker = fetch_stock_df(stock_id, n_days=5)
    if df is None or len(df) < 2:
        return {'svg': '<span class="mute" style="font-size:10px">N/A</span>',
                'absorbed_svg': '',
                'stats': None, 'ticker': None}

    last5 = df.tail(5)
    has5 = len(last5) == 5

    # SVG 尺寸
    W, H = 150, 64
    OHLC_TOP, OHLC_BOT = 4, 44     # 主圖
    VOL_TOP, VOL_BOT = 48, 60      # 量
    PAD = 4

    highs = last5['High'].values
    lows = last5['Low'].values
    opens = last5['Open'].values
    closes = last5['Close'].values
    vols = last5['Volume'].values

    p_max = float(highs.max())
    p_min = float(lows.min())
    p_range = p_max - p_min or 1
    v_max = float(vols.max()) or 1

    n = len(last5)
    slot_w = (W - 2 * PAD) / n
    candle_w = max(4, slot_w * 0.6)

    def y_p(p):
        return OHLC_TOP + (p_max - p) / p_range * (OHLC_BOT - OHLC_TOP)

    def y_v(v):
        return VOL_BOT - v / v_max * (VOL_BOT - VOL_TOP)

    parts = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="display:block">']
    for i in range(n):
        cx = PAD + slot_w * (i + 0.5)
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        is_up = c >= o
        color = '#3fb950' if is_up else '#f85149'
        # wick
        parts.append(f'<line x1="{cx:.1f}" y1="{y_p(h):.1f}" x2="{cx:.1f}" y2="{y_p(l):.1f}" stroke="{color}" stroke-width="0.8"/>')
        # body
        body_top = min(y_p(o), y_p(c))
        body_h = max(1, abs(y_p(o) - y_p(c)))
        parts.append(f'<rect x="{cx - candle_w/2:.1f}" y="{body_top:.1f}" width="{candle_w:.1f}" height="{body_h:.1f}" fill="{color}"/>')
        # volume
        vh = max(1, (VOL_BOT - VOL_TOP) * vols[i] / v_max)
        parts.append(f'<rect x="{cx - candle_w/2:.1f}" y="{VOL_BOT - vh:.1f}" width="{candle_w:.1f}" height="{vh:.1f}" fill="{color}" opacity="0.55"/>')

    # 分隔線
    parts.append(f'<line x1="{PAD}" y1="46" x2="{W-PAD}" y2="46" stroke="#30363d" stroke-width="0.5"/>')
    parts.append('</svg>')

    market_vol_5d = int(vols.sum())

    # 5 日吸量 SVG（與 K 圖同寬，獨立顯示）
    absorbed_svg = ''
    total_absorbed = 0
    if daily_absorbed:
        absorbed_svg, total_absorbed = _render_absorbed_svg(daily_absorbed, absorbed_date_labels)
    ratio_pct = (total_absorbed / market_vol_5d * 100) if (market_vol_5d > 0 and total_absorbed) else None

    last_close = float(closes[-1])
    chg_pct = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0

    return {
        'svg': ''.join(parts),
        'absorbed_svg': absorbed_svg,
        'stats': {
            'market_vol_5d': market_vol_5d,
            'total_absorbed': total_absorbed,
            'ratio_pct': ratio_pct,
            'last_close': last_close,
            'chg_pct_5d': chg_pct,
            'has_full_5d': has5,
        },
        'ticker': ticker,
    }


def _render_absorbed_svg(daily_absorbed: list,
                         date_labels: list | None = None) -> tuple[str, int]:
    """逐日吸量 bar chart SVG。daily_absorbed 是 [oldest...newest] list of int。
    date_labels = 對應日期字串 list，例如 ['05-15','05-16','05-17','05-18','05-19']
    回 (svg_html, total_absorbed)
    """
    vals = [int(v or 0) for v in daily_absorbed]
    total = sum(vals)
    if total == 0:
        return ('<svg viewBox="0 0 150 64" width="150" height="64"><text x="75" y="36" text-anchor="middle" '
                'fill="#6e7681" font-size="10">無吸量</text></svg>'), 0

    W, H = 150, 64
    PAD = 4
    AXIS_Y = H - 12
    LABEL_Y = H - 2
    n = max(len(vals), 1)
    slot_w = (W - 2 * PAD) / n
    bar_w = max(5, slot_w * 0.65)
    mx = max(vals) or 1

    parts = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="display:block">']
    for i, v in enumerate(vals):
        cx = PAD + slot_w * (i + 0.5)
        bh = (v / mx) * (AXIS_Y - PAD) if v > 0 else 0
        if bh > 0:
            parts.append(f'<rect x="{cx - bar_w/2:.1f}" y="{AXIS_Y - bh:.1f}" '
                         f'width="{bar_w:.1f}" height="{bh:.1f}" fill="#3fb950"/>')
        # x 軸 label：優先用日期；fallback 用 D-N 相對標籤
        if date_labels and i < len(date_labels) and date_labels[i]:
            label = date_labels[i]
        else:
            label = f'D-{n-1-i}' if i < n - 1 else 'D'
        parts.append(f'<text x="{cx:.1f}" y="{LABEL_Y}" text-anchor="middle" '
                     f'fill="#6e7681" font-size="8">{label}</text>')
    # x 軸線
    parts.append(f'<line x1="{PAD}" y1="{AXIS_Y}" x2="{W-PAD}" y2="{AXIS_Y}" stroke="#30363d" stroke-width="0.5"/>')
    parts.append('</svg>')
    return ''.join(parts), total
