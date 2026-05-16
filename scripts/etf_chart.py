"""ETF 技術線型 chart 渲染：yfinance 抓 2 年日線 + MA5/20/60/120/240，回 Plotly HTML div。

Cache 在 data/prices/<ticker>.parquet（12 小時 TTL），避免每次 build 都打 yfinance。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / 'data' / 'prices'
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_HOURS = 12

MA_SPECS = [
    (5,   '#58a6ff'),
    (20,  '#d29922'),
    (60,  '#f0883e'),
    (120, '#a371f7'),
    (240, '#f85149'),
]


def fetch_data(ticker: str, start: str = '2020-01-01') -> pd.DataFrame:
    """yfinance 抓日線，含 12 小時 parquet cache。"""
    cache = CACHE_DIR / f'{ticker.replace(".", "_")}.parquet'
    if cache.exists():
        age_h = (dt.datetime.now().timestamp() - cache.stat().st_mtime) / 3600
        if age_h < CACHE_TTL_HOURS:
            return pd.read_parquet(cache)
    df = yf.Ticker(ticker).history(start=start, auto_adjust=False)
    if not df.empty:
        df.to_parquet(cache)
    return df


def render_chart(etf_id: str) -> str:
    """主動式 ETF (TWSE 或 TPEx) candlestick + 5 條 MA。回傳 HTML div。

    先試 .TW (上市)，失敗再試 .TWO (上櫃)。
    """
    df = None
    ticker = None
    for suffix in ('.TW', '.TWO'):
        try:
            cand = etf_id + suffix
            df = fetch_data(cand)
            if not df.empty:
                ticker = cand
                break
        except Exception:
            continue
    if df is None or df.empty or ticker is None:
        return '<div class="banner">⚠ yfinance 無資料（ETF 可能剛上市，或 .TW / .TWO 都查不到）</div>'
    df = df.tail(1300)   # ~5 年，給 rangeselector 用

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name='OHLC',
        increasing_line_color='#3fb950', decreasing_line_color='#f85149',
        showlegend=False,
    ))
    for window, color in MA_SPECS:
        if len(df) >= window:
            ma = df['Close'].rolling(window).mean()
            fig.add_trace(go.Scatter(
                x=df.index, y=ma, name=f'MA{window}',
                line=dict(color=color, width=1.3), mode='lines',
                hovertemplate='%{x|%Y-%m-%d}<br>MA' + str(window) + ': %{y:.2f}<extra></extra>',
            ))

    last_close = df['Close'].iloc[-1]
    last_dt = df.index[-1]
    last_date = last_dt.strftime('%Y-%m-%d')
    import pandas as _pd
    default_start = last_dt - _pd.Timedelta(days=365)

    fig.update_layout(
        template='plotly_dark',
        plot_bgcolor='#0d1117', paper_bgcolor='#0d1117',
        font=dict(color='#c9d1d9', size=11),
        height=480,
        margin=dict(l=10, r=10, t=80, b=10),
        legend=dict(orientation='h', yanchor='bottom', y=1.13, xanchor='right', x=1, bgcolor='rgba(0,0,0,0)'),
        title=dict(text=f'<span style="font-size:13px">{ticker}　收盤 {last_close:.2f}　({last_date})</span>',
                   x=1, xanchor='right', y=0.99, yanchor='top'),
        xaxis=dict(
            gridcolor='#21262d',
            rangeslider=dict(visible=False),
            type='date',
            range=[default_start, last_dt],
            autorange=False,
            rangeselector=dict(
                buttons=[
                    dict(count=3, label='3M', step='month', stepmode='backward'),
                    dict(count=6, label='6M', step='month', stepmode='backward'),
                    dict(count=1, label='1Y', step='year',  stepmode='backward'),
                    dict(count=3, label='3Y', step='year',  stepmode='backward'),
                    dict(count=5, label='5Y', step='year',  stepmode='backward'),
                    dict(label='ALL', step='all'),
                ],
                bgcolor='#161b22', activecolor='#1f6feb',
                bordercolor='#30363d', borderwidth=1,
                font=dict(color='#c9d1d9', size=12),
                x=0, xanchor='left', y=1.08, yanchor='bottom',
            ),
        ),
        yaxis=dict(gridcolor='#21262d', autorange=True, fixedrange=False),
    )
    div_id = f'chart_{etf_id}'
    chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn',
                              div_id=div_id,
                              config={'displayModeBar': False})
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
        if(x) Plotly.relayout(gd, {{'yaxis.autorange':true}});
      }});
    }}
    if(++tries>50) clearInterval(iv);
  }}, 100);
}})();
</script>'''
    return chart_html + rescale_js


if __name__ == '__main__':
    import sys
    etf = sys.argv[1] if len(sys.argv) > 1 else '00981A'
    html = render_chart(etf)
    print(f'rendered {len(html)} chars for {etf}')
