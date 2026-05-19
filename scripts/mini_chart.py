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


def _fmt_price(p) -> str:
    """股價標籤 (動態小數位)"""
    if p is None:
        return ''
    p = float(p)
    if p >= 100:
        return f'{p:.0f}'
    if p >= 10:
        return f'{p:.1f}'
    return f'{p:.2f}'


def _fmt_vol(v) -> str:
    """成交量縮寫 (10萬以上→K, 100萬以上→M, 10億以上→B)"""
    if v is None:
        return ''
    v = float(v)
    if v >= 1e9:
        return f'{v/1e9:.1f}B'
    if v >= 1e6:
        return f'{v/1e6:.1f}M'
    if v >= 1e3:
        return f'{v/1e3:.0f}K'
    return f'{int(v)}'


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

    # SVG 尺寸（高度加大放數字）
    W, H = 180, 110
    OHLC_TOP, OHLC_BOT = 4, 50    # 主圖
    PRICE_LABEL_Y = 60            # 收盤價文字
    VOL_TOP, VOL_BOT = 68, 92     # 量
    VOL_LABEL_Y = 102             # 成交量文字
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
    candle_w = max(4, slot_w * 0.55)

    def y_p(p):
        return OHLC_TOP + (p_max - p) / p_range * (OHLC_BOT - OHLC_TOP)

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
        # 收盤價標籤
        price_str = _fmt_price(c)
        parts.append(f'<text x="{cx:.1f}" y="{PRICE_LABEL_Y}" text-anchor="middle" '
                     f'fill="{color}" font-size="8" font-weight="600">{price_str}</text>')
        # 成交量條
        vh = max(1, (VOL_BOT - VOL_TOP) * vols[i] / v_max)
        parts.append(f'<rect x="{cx - candle_w/2:.1f}" y="{VOL_BOT - vh:.1f}" width="{candle_w:.1f}" height="{vh:.1f}" fill="{color}" opacity="0.55"/>')
        # 成交量標籤
        vol_str = _fmt_vol(vols[i])
        parts.append(f'<text x="{cx:.1f}" y="{VOL_LABEL_Y}" text-anchor="middle" '
                     f'fill="#8b949e" font-size="8">{vol_str}</text>')

    # 分隔線
    parts.append(f'<line x1="{PAD}" y1="64" x2="{W-PAD}" y2="64" stroke="#30363d" stroke-width="0.5"/>')
    parts.append(f'<line x1="{PAD}" y1="96" x2="{W-PAD}" y2="96" stroke="#30363d" stroke-width="0.5"/>')
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


def render_net_flow_svg(daily_net: list, date_labels: list | None = None,
                        width: int = 460, height: int = 180) -> str:
    """淨流入 bar chart (正綠負紅，含 0 軸)。
    daily_net = list of int/None (oldest→newest)，正數=加碼、負數=減碼
    date_labels = 對應每根 bar 的日期 (MM-DD)
    """
    vals = [int(v) if v is not None else 0 for v in daily_net]
    if not vals:
        return '<div class="mute" style="text-align:center;padding:20px">資料不足</div>'

    W, H = width, height
    PAD_X = 12
    LABEL_TOP = 14    # 數值標籤頂部空間
    LABEL_BOT = 24    # 日期 + 數值（負）標籤空間
    plot_top = LABEL_TOP
    plot_bot = H - LABEL_BOT
    plot_h = plot_bot - plot_top
    mid_y = plot_top + plot_h / 2

    mx = max((abs(v) for v in vals), default=1) or 1
    n = len(vals)
    slot_w = (W - 2 * PAD_X) / n
    bar_w = max(8, slot_w * 0.5)

    parts = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="display:block">']
    # 0 軸
    parts.append(f'<line x1="{PAD_X}" y1="{mid_y}" x2="{W-PAD_X}" y2="{mid_y}" '
                 f'stroke="#30363d" stroke-width="0.8"/>')

    for i, v in enumerate(vals):
        cx = PAD_X + slot_w * (i + 0.5)
        bar_h = abs(v) / mx * (plot_h / 2 - 2)
        if v > 0:
            bar_y = mid_y - bar_h
            color = '#3fb950'
            label_y = bar_y - 3
            label_color = '#3fb950'
        elif v < 0:
            bar_y = mid_y
            color = '#f85149'
            label_y = mid_y + bar_h + 9
            label_color = '#f85149'
        else:
            bar_y = mid_y - 0.5
            bar_h = 1
            color = '#30363d'
            label_y = mid_y - 3
            label_color = '#6e7681'

        if bar_h > 0:
            parts.append(f'<rect x="{cx - bar_w/2:.1f}" y="{bar_y:.1f}" '
                         f'width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{color}"/>')

        # 數值標籤（正 = bar 頂、負 = bar 底）
        if v != 0:
            sign = '+' if v > 0 else '−'
            parts.append(f'<text x="{cx:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                         f'fill="{label_color}" font-size="10" font-weight="600">'
                         f'{sign}{_fmt_vol(abs(v))}</text>')
        else:
            parts.append(f'<text x="{cx:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                         f'fill="#6e7681" font-size="10">—</text>')

        # 日期 label (固定底部)
        if date_labels and i < len(date_labels) and date_labels[i]:
            d_label = date_labels[i]
        else:
            d_label = f'D-{n-1-i}' if i < n - 1 else 'D'
        parts.append(f'<text x="{cx:.1f}" y="{H-6}" text-anchor="middle" '
                     f'fill="#8b949e" font-size="10">{d_label}</text>')

    parts.append('</svg>')
    return ''.join(parts)


def _render_absorbed_svg(daily_absorbed: list,
                         date_labels: list | None = None) -> tuple[str, int]:
    """逐日吸量 bar chart SVG。daily_absorbed 是 [oldest...newest] list of int。
    date_labels = 對應日期字串 list，例如 ['05-15','05-16','05-17','05-18','05-19']
    回 (svg_html, total_absorbed)
    """
    vals = [int(v or 0) for v in daily_absorbed]
    total = sum(vals)
    if total == 0:
        return ('<svg viewBox="0 0 180 110" width="180" height="110"><text x="90" y="60" text-anchor="middle" '
                'fill="#6e7681" font-size="10">無吸量</text></svg>'), 0

    W, H = 180, 110
    BAR_TOP = 16     # 頂端留 label 空間
    BAR_BOT = 88     # 主圖底（軸）
    DATE_LABEL_Y = 100
    PAD = 4
    n = max(len(vals), 1)
    slot_w = (W - 2 * PAD) / n
    bar_w = max(5, slot_w * 0.6)
    mx = max(vals) or 1

    parts = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="display:block">']
    for i, v in enumerate(vals):
        cx = PAD + slot_w * (i + 0.5)
        bh = (v / mx) * (BAR_BOT - BAR_TOP) if v > 0 else 0
        if bh > 0:
            parts.append(f'<rect x="{cx - bar_w/2:.1f}" y="{BAR_BOT - bh:.1f}" '
                         f'width="{bar_w:.1f}" height="{bh:.1f}" fill="#3fb950"/>')
        # 數值標籤 (bar 頂端)
        if v > 0:
            val_str = _fmt_vol(v)
            label_y = max(BAR_TOP + 4, BAR_BOT - bh - 2)
            parts.append(f'<text x="{cx:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                         f'fill="#3fb950" font-size="8" font-weight="600">{val_str}</text>')
        # 日期 label
        if date_labels and i < len(date_labels) and date_labels[i]:
            d_label = date_labels[i]
        else:
            d_label = f'D-{n-1-i}' if i < n - 1 else 'D'
        parts.append(f'<text x="{cx:.1f}" y="{DATE_LABEL_Y}" text-anchor="middle" '
                     f'fill="#6e7681" font-size="8">{d_label}</text>')
    # x 軸線
    parts.append(f'<line x1="{PAD}" y1="{BAR_BOT}" x2="{W-PAD}" y2="{BAR_BOT}" stroke="#30363d" stroke-width="0.5"/>')
    parts.append('</svg>')
    return ''.join(parts), total
