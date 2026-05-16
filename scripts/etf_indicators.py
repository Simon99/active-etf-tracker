"""ETF 技術指標數字計算（給詳情頁 metric cards 用）。

從 etf_chart 的 fetch_data 拿日線後算：
  - 收盤價
  - 漲跌、漲跌幅
  - 布林位階 (close vs Bollinger 20,2)
  - BIAS20 (close - MA20) / MA20 × 100
  - RSI(14)
  - MACD 柱 (OSC = (DIF-DEA) × 2)
"""
from __future__ import annotations

import pandas as pd
from etf_chart import fetch_data as _fetch_etf_data


def _ticker_candidates(etf_id: str):
    return [f'{etf_id}.TW', f'{etf_id}.TWO']


def fetch_etf_df(etf_id: str) -> pd.DataFrame | None:
    for c in _ticker_candidates(etf_id):
        try:
            df = _fetch_etf_data(c)
            if not df.empty:
                return df
        except Exception:
            continue
    return None


def compute_indicators(df: pd.DataFrame) -> dict:
    """從 OHLCV 算出所有指標的最後一筆數值 + 文字註釋。"""
    if df is None or df.empty or len(df) < 20:
        return {}
    close = df['Close']
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) >= 2 else last
    chg = last - prev
    chg_pct = (chg / prev * 100) if prev else 0

    # Bollinger 20, 2
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    last_ma20 = float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None
    last_bb_u = float(bb_upper.iloc[-1]) if not pd.isna(bb_upper.iloc[-1]) else None
    last_bb_l = float(bb_lower.iloc[-1]) if not pd.isna(bb_lower.iloc[-1]) else None
    # 位階：close 在 BB 中的位置 (0=下軌, 1=上軌)
    bb_pos = None
    bb_label = '–'
    if last_bb_u and last_bb_l and last_bb_u > last_bb_l:
        bb_pos = (last - last_bb_l) / (last_bb_u - last_bb_l)
        if bb_pos < 0.2:
            bb_label = '極低'
        elif bb_pos < 0.4:
            bb_label = '偏低'
        elif bb_pos < 0.6:
            bb_label = '中位'
        elif bb_pos < 0.8:
            bb_label = '偏高'
        else:
            bb_label = '極高'

    # BIAS20
    bias20 = ((last - last_ma20) / last_ma20 * 100) if last_ma20 else None

    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - 100 / (1 + rs)
    last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None
    rsi_label = '–'
    if last_rsi is not None:
        if last_rsi >= 70:
            rsi_label = '超買區'
        elif last_rsi <= 30:
            rsi_label = '超賣區'
        elif last_rsi >= 55:
            rsi_label = '偏多'
        elif last_rsi <= 45:
            rsi_label = '偏空'
        else:
            rsi_label = '中性'

    # MACD 12/26/9
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=9, adjust=False).mean()
    osc = (dif - dea) * 2
    last_osc = float(osc.iloc[-1]) if not pd.isna(osc.iloc[-1]) else None
    last_dif = float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else None
    macd_label = '–'
    if last_osc is not None:
        if last_osc > 0 and last_osc > float(osc.iloc[-2]) if len(osc) >= 2 else False:
            macd_label = '多方動能'
        elif last_osc > 0:
            macd_label = '多方'
        elif last_osc < 0 and last_osc < float(osc.iloc[-2]) if len(osc) >= 2 else False:
            macd_label = '空方動能'
        else:
            macd_label = '空方'

    # 5 日平均成交額（amount）
    if 'Volume' in df.columns:
        # 沒有 amount 欄位 → 用 close × volume
        amount = (close * df['Volume']).tail(5).mean()
    else:
        amount = None

    return {
        'last_close': last, 'chg': chg, 'chg_pct': chg_pct,
        'bb_pos': bb_pos, 'bb_label': bb_label, 'bb_upper': last_bb_u, 'bb_lower': last_bb_l,
        'bias20': bias20, 'ma20': last_ma20,
        'rsi': last_rsi, 'rsi_label': rsi_label,
        'osc': last_osc, 'dif': last_dif, 'macd_label': macd_label,
        'amount_5d_avg': amount,
        'last_date': df.index[-1].strftime('%Y-%m-%d'),
    }
