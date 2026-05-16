"""個股技術分析 chart：3-panel Plotly subplot
  Row 1: Candlestick + MA5/10/20/60/120/240
  Row 2: KD (9, 3, 3)
  Row 3: MACD (12, 26, 9) — DIF / DEA / OSC histogram

ticker 解析：
  - 純 4-6 位數字 → .TW (上市) → 失敗 .TWO (上櫃)
  - 含字母（英文 ticker） → 直接打 yfinance（美股 / 國際）
  - 失敗回 banner
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / 'data' / 'prices'
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_HOURS = 24   # 個股 cache 久一點，減少 yfinance 負擔

MA_SPECS = [
    (5,   '#58a6ff'),
    (10,  '#9ad1ff'),
    (20,  '#d29922'),
    (60,  '#f0883e'),
    (120, '#a371f7'),
    (240, '#f85149'),
]


def _resolve_ticker(stock_id: str) -> list[str]:
    """回傳要嘗試的 yfinance ticker 順序。

    - 純數字（台股）：.TW → .TWO
    - 含字母（國際）：先試純 ticker（美股），再依序試常見國際後綴
      (Bloomberg → yfinance 對照)：
      LN→.L  NA→.AS  IM→.MI  GR→.DE  FP→.PA  JP→.T  HK→.HK
    """
    sid = stock_id.strip()
    if re.fullmatch(r'\d{4,6}', sid):
        return [f'{sid}.TW', f'{sid}.TWO']
    # 字母 ticker — 先美股，再幾個主要歐洲市場
    return [sid, f'{sid}.L', f'{sid}.AS', f'{sid}.MI',
            f'{sid}.DE', f'{sid}.PA', f'{sid}.T', f'{sid}.HK']


def fetch_data(ticker: str, start: str = '2020-01-01') -> pd.DataFrame:
    cache = CACHE_DIR / f'{ticker.replace(".", "_")}.parquet'
    if cache.exists():
        age_h = (dt.datetime.now().timestamp() - cache.stat().st_mtime) / 3600
        if age_h < CACHE_TTL_HOURS:
            return pd.read_parquet(cache)
    df = yf.Ticker(ticker).history(start=start, auto_adjust=False)
    if not df.empty:
        df.to_parquet(cache)
    return df


def _compute_kd(df: pd.DataFrame, n: int = 9, k_smooth: int = 3, d_smooth: int = 3):
    """Stochastic Oscillator (KD)。標準參數 9, 3, 3。"""
    low_n = df['Low'].rolling(n).min()
    high_n = df['High'].rolling(n).max()
    rsv = (df['Close'] - low_n) / (high_n - low_n) * 100
    k = rsv.ewm(alpha=1 / k_smooth, adjust=False).mean()
    d = k.ewm(alpha=1 / d_smooth, adjust=False).mean()
    return k, d


def _compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD 標準參數 12 / 26 / 9。回傳 DIF, DEA, OSC histogram (DIF-DEA)*2。"""
    ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    osc = (dif - dea) * 2
    return dif, dea, osc


def render_stock_chart(stock_id: str) -> str:
    """3-panel chart for one stock. 回 HTML div。"""
    df = None
    ticker = None
    for cand in _resolve_ticker(stock_id):
        try:
            d = fetch_data(cand)
            if not d.empty:
                df, ticker = d, cand
                break
        except Exception:
            continue

    if df is None or df.empty or ticker is None:
        return ('<div class="banner">⚠ yfinance 無資料（'
                + ' / '.join(_resolve_ticker(stock_id))
                + ' 都查不到）</div>')

    # 留全長 (~5 年)，rangeselector 切換 xaxis；KD / MACD 用全段算好讓切換時數值連續
    df = df.tail(1300)
    k_line, d_line = _compute_kd(df)
    dif, dea, osc = _compute_macd(df)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.6, 0.2, 0.2],
        vertical_spacing=0.03,
        subplot_titles=('', 'KD (9,3,3)', 'MACD (12,26,9)'),
    )

    # Row 1: candlestick + MAs
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name='OHLC',
        increasing_line_color='#3fb950', decreasing_line_color='#f85149',
        showlegend=False,
    ), row=1, col=1)
    for window, color in MA_SPECS:
        if len(df) >= window:
            ma = df['Close'].rolling(window).mean()
            fig.add_trace(go.Scatter(
                x=df.index, y=ma, name=f'MA{window}',
                line=dict(color=color, width=1.2), mode='lines',
                hovertemplate='%{x|%Y-%m-%d}<br>MA' + str(window) + ': %{y:.2f}<extra></extra>',
            ), row=1, col=1)

    # Row 2: KD
    fig.add_trace(go.Scatter(x=df.index, y=k_line, name='K', line=dict(color='#58a6ff', width=1.3),
                             hovertemplate='K: %{y:.1f}<extra></extra>'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=d_line, name='D', line=dict(color='#d29922', width=1.3),
                             hovertemplate='D: %{y:.1f}<extra></extra>'), row=2, col=1)
    # 80 / 20 參考線
    fig.add_hline(y=80, line=dict(color='#30363d', width=1, dash='dot'), row=2, col=1)
    fig.add_hline(y=20, line=dict(color='#30363d', width=1, dash='dot'), row=2, col=1)

    # Row 3: MACD
    fig.add_trace(go.Bar(x=df.index, y=osc, name='OSC',
                         marker_color=['#3fb950' if v >= 0 else '#f85149' for v in osc],
                         showlegend=False,
                         hovertemplate='OSC: %{y:.3f}<extra></extra>'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=dif, name='DIF', line=dict(color='#58a6ff', width=1.3),
                             hovertemplate='DIF: %{y:.3f}<extra></extra>'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=dea, name='DEA', line=dict(color='#d29922', width=1.3),
                             hovertemplate='DEA: %{y:.3f}<extra></extra>'), row=3, col=1)

    last_close = df['Close'].iloc[-1]
    last_date = df.index[-1].strftime('%Y-%m-%d')

    # 預設顯示最近 1 年
    last_dt = df.index[-1]
    default_start = last_dt - pd.Timedelta(days=365)

    fig.update_layout(
        template='plotly_dark',
        plot_bgcolor='#0d1117', paper_bgcolor='#0d1117',
        font=dict(color='#c9d1d9', size=11),
        xaxis_rangeslider_visible=False,
        height=740,
        margin=dict(l=10, r=10, t=80, b=10),
        legend=dict(orientation='h', yanchor='bottom', y=1.13, xanchor='right', x=1,
                    bgcolor='rgba(0,0,0,0)'),
        # title 移到 chart 上方獨立一行（top-right），rangeselector 占 top-left
        title=dict(text=f'<span style="font-size:13px">{ticker}　收盤 {last_close:.2f}　({last_date})</span>',
                   x=1, xanchor='right', y=0.99, yanchor='top'),
        hovermode='x unified',
    )
    fig.update_xaxes(gridcolor='#21262d', rangeslider_visible=False, autorange=False)
    fig.update_yaxes(gridcolor='#21262d', autorange=True, fixedrange=False)

    # Row 1 xaxis 上加 rangeselector 按鈕（shared_xaxes 會同步到 row 2/3）
    fig.update_layout(
        xaxis=dict(
            rangeselector=dict(
                buttons=[
                    dict(count=3,  label='3M', step='month', stepmode='backward'),
                    dict(count=6,  label='6M', step='month', stepmode='backward'),
                    dict(count=1,  label='1Y', step='year',  stepmode='backward'),
                    dict(count=3,  label='3Y', step='year',  stepmode='backward'),
                    dict(count=5,  label='5Y', step='year',  stepmode='backward'),
                    dict(label='ALL', step='all'),
                ],
                bgcolor='#161b22',
                activecolor='#1f6feb',
                bordercolor='#30363d',
                borderwidth=1,
                font=dict(color='#c9d1d9', size=12),
                x=0, xanchor='left', y=1.08, yanchor='bottom',
            ),
            type='date',
            range=[default_start, last_dt],
            rangeslider=dict(visible=False),
        ),
    )

    div_id = f'stockchart_{stock_id}'
    chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn',
                              div_id=div_id,
                              config={'displayModeBar': False})
    # 切換 rangeselector 時手動觸發 yaxis autorange（Plotly 預設不做）
    rescale_js = f'''
<script>
(function(){{
  var tries=0;
  var iv=setInterval(function(){{
    var gd=document.getElementById('{div_id}');
    if(gd && gd.on){{
      clearInterval(iv);
      gd.on('plotly_relayout', function(ev){{
        var x = Object.keys(ev).some(function(k){{return k.indexOf('xaxis')===0;}});
        if(x) Plotly.relayout(gd, {{'yaxis.autorange':true,'yaxis2.autorange':true,'yaxis3.autorange':true}});
      }});
    }}
    if(++tries>50) clearInterval(iv);
  }}, 100);
}})();
</script>'''
    return chart_html + rescale_js


if __name__ == '__main__':
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else '2330'
    html = render_stock_chart(sid)
    print(f'rendered {len(html)} chars for {sid}')
