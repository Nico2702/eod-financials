import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NaroIX · Fundamentals Viewer",
    page_icon="📊",
    layout="wide",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #0f1117; }
    [data-testid="stSidebar"] { background: #161b27; }
    .metric-card {
        background: #1e2535;
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 10px;
    }
    .metric-label { color: #8892a4; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
    .metric-value { color: #e2e8f0; font-size: 22px; font-weight: 700; margin-top: 4px; }
    .metric-delta { font-size: 13px; margin-top: 2px; }
    .section-header {
        color: #6c8ebf;
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: .08em;
        border-bottom: 1px solid #2d3748;
        padding-bottom: 6px;
        margin: 24px 0 14px 0;
    }
    .company-name { color: #e2e8f0; font-size: 28px; font-weight: 800; }
    .company-meta { color: #8892a4; font-size: 14px; }
    .tag {
        display: inline-block;
        background: #1e3a5f;
        color: #6c8ebf;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 12px;
        margin-right: 6px;
    }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_num(val, prefix="", suffix="", decimals=2):
    if val is None or val == "" or val == "NA":
        return "—"
    try:
        v = float(val)
        if abs(v) >= 1e12:
            return f"{prefix}{v/1e12:.{decimals}f}T{suffix}"
        if abs(v) >= 1e9:
            return f"{prefix}{v/1e9:.{decimals}f}B{suffix}"
        if abs(v) >= 1e6:
            return f"{prefix}{v/1e6:.{decimals}f}M{suffix}"
        return f"{prefix}{v:,.{decimals}f}{suffix}"
    except:
        return str(val)

def fmt_pct(val, decimals=2):
    if val is None or val == "" or val == "NA":
        return "—"
    try:
        return f"{float(val)*100:.{decimals}f}%"
    except:
        return str(val)

def metric_card(label, value, delta=None):
    delta_html = ""
    if delta:
        color = "#48bb78" if not str(delta).startswith("-") else "#fc8181"
        delta_html = f'<div class="metric-delta" style="color:{color}">{delta}</div>'
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def fetch_fundamentals(ticker: str, api_token: str) -> dict:
    url = f"https://eodhd.com/api/fundamentals/{ticker}?api_token={api_token}&fmt=json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

def parse_financials(data: dict, statement: str, period: str) -> pd.DataFrame:
    """Extract annual or quarterly financial statement into a DataFrame."""
    try:
        raw = data["Financials"][statement][period]
        if not raw:
            return pd.DataFrame()
        rows = []
        for date_key, fields in sorted(raw.items(), reverse=True):
            row = {"Date": date_key}
            row.update(fields)
            rows.append(row)
        df = pd.DataFrame(rows)
        df = df.set_index("Date")
        # drop non-numeric / metadata columns
        drop_cols = [c for c in df.columns if c in ("date", "filing_date", "currency_symbol", "type", "period")]
        df = df.drop(columns=drop_cols, errors="ignore")
        df = df.apply(pd.to_numeric, errors="coerce")
        return df.head(8)
    except Exception:
        return pd.DataFrame()

def plot_financials(df: pd.DataFrame, cols: list, title: str, yformat="$B"):
    fig = go.Figure()
    colors = ["#6c8ebf", "#48bb78", "#fc8181", "#f6ad55", "#b794f4"]
    for i, col in enumerate(cols):
        if col in df.columns:
            vals = df[col] / 1e9 if yformat == "$B" else df[col]
            fig.add_trace(go.Bar(
                name=col.replace("_", " ").title(),
                x=df.index[::-1],
                y=vals[::-1],
                marker_color=colors[i % len(colors)],
            ))
    fig.update_layout(
        title=title,
        paper_bgcolor="#1e2535",
        plot_bgcolor="#1e2535",
        font_color="#e2e8f0",
        barmode="group",
        height=340,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(bgcolor="#1e2535", bordercolor="#2d3748", borderwidth=1),
        xaxis=dict(gridcolor="#2d3748"),
        yaxis=dict(gridcolor="#2d3748", title=yformat),
    )
    return fig

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 NaroIX Fundamentals")
    st.markdown("---")
    ticker_input = st.text_input("Ticker (Exchange)", value="AAPL.US", placeholder="z.B. AAPL.US, SAP.XETRA")
    api_token = st.text_input("API Token", value="demo", type="password")
    fetch_btn = st.button("🔍 Laden", use_container_width=True, type="primary")
    st.markdown("---")
    st.markdown("**Beispiel-Ticker**")
    for ex in ["AAPL.US", "MSFT.US", "SAP.XETRA", "VOW3.XETRA", "7203.TSE"]:
        if st.button(ex, use_container_width=True):
            st.session_state["ticker"] = ex
            fetch_btn = True

    period_type = st.radio("Periode", ["annual", "quarterly"], horizontal=True)
    st.markdown("---")
    st.caption("Powered by EODHD API")

# ── Resolve ticker ─────────────────────────────────────────────────────────────
if "ticker" in st.session_state:
    ticker_input = st.session_state["ticker"]

# ── Main ──────────────────────────────────────────────────────────────────────
if not fetch_btn and "fundamentals_data" not in st.session_state:
    st.markdown("""
    <div style="text-align:center; padding: 80px 0; color: #8892a4;">
        <div style="font-size: 48px;">📊</div>
        <div style="font-size: 22px; color: #e2e8f0; font-weight: 700; margin: 16px 0 8px;">NaroIX Fundamentals Viewer</div>
        <div>Ticker eingeben und API Token hinterlegen, dann <strong>Laden</strong> klicken.</div>
        <div style="margin-top:8px; font-size:13px;">Demo-Modus: Ticker <code>AAPL.US</code>, Token <code>demo</code></div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Fetch
if fetch_btn or "fundamentals_data" not in st.session_state:
    with st.spinner(f"Lade Daten für **{ticker_input}** …"):
        try:
            data = fetch_fundamentals(ticker_input, api_token)
            st.session_state["fundamentals_data"] = data
            st.session_state["fundamentals_ticker"] = ticker_input
        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")
            st.stop()

data = st.session_state["fundamentals_data"]
g = data.get("General", {})
hl = data.get("Highlights", {})
val = data.get("Valuation", {})
tech = data.get("Technicals", {})
rat = data.get("AnalystRatings", {})
earn = data.get("Earnings", {})

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_info = st.columns([1, 5])
with col_logo:
    logo = g.get("LogoURL", "")
    if logo:
        st.markdown(f'<img src="{logo}" width="80" style="border-radius:8px;">', unsafe_allow_html=True)
with col_info:
    st.markdown(f'<div class="company-name">{g.get("Name","—")}</div>', unsafe_allow_html=True)
    tags = "".join([
        f'<span class="tag">{g.get("Ticker","")}</span>',
        f'<span class="tag">{g.get("Exchange","")}</span>',
        f'<span class="tag">{g.get("Sector","")}</span>',
        f'<span class="tag">{g.get("Industry","")}</span>',
        f'<span class="tag">{g.get("CurrencyCode","")}</span>',
    ])
    st.markdown(f'<div class="company-meta" style="margin-top:6px;">{tags}</div>', unsafe_allow_html=True)
    desc = g.get("Description", "")
    if desc:
        with st.expander("Unternehmensbeschreibung"):
            st.write(desc[:1500] + ("…" if len(desc) > 1500 else ""))

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Highlights", "💰 Financials", "📊 Earnings", "🔬 Valuation", "🌐 Info"])

# ── TAB 1: Highlights ─────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="section-header">Marktdaten & Kennzahlen</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    metrics = [
        ("Market Cap", fmt_num(hl.get("MarketCapitalization"), prefix="$")),
        ("EV", fmt_num(hl.get("EnterpriseValue"), prefix="$")),
        ("52W High", fmt_num(hl.get("52WeekHigh"), prefix="$")),
        ("52W Low", fmt_num(hl.get("52WeekLow"), prefix="$")),
        ("Revenue TTM", fmt_num(hl.get("RevenueTTM"), prefix="$")),
        ("Gross Profit TTM", fmt_num(hl.get("GrossProfitTTM"), prefix="$")),
        ("EPS", fmt_num(hl.get("DilutedEpsTTM"), prefix="$")),
        ("Dividend/Share", fmt_num(hl.get("DividendShare"), prefix="$")),
        ("Dividend Yield", fmt_pct(hl.get("DividendYield"))),
        ("P/E Ratio", fmt_num(hl.get("PERatio"), decimals=1)),
        ("PEG Ratio", fmt_num(hl.get("PEGRatio"), decimals=2)),
        ("Beta", fmt_num(tech.get("Beta"), decimals=2)),
        ("Profit Margin", fmt_pct(hl.get("ProfitMargin"))),
        ("Operating Margin", fmt_pct(hl.get("OperatingMarginTTM"))),
        ("ROA", fmt_pct(hl.get("ReturnOnAssetsTTM"))),
        ("ROE", fmt_pct(hl.get("ReturnOnEquityTTM"))),
    ]
    for i, (label, value) in enumerate(metrics):
        with cols[i % 4]:
            metric_card(label, value)

    st.markdown('<div class="section-header">Analyst Ratings</div>', unsafe_allow_html=True)
    if rat:
        rc = st.columns(5)
        for col, (k, label) in zip(rc, [
            ("Rating","Rating"), ("TargetPrice","Target Price"),
            ("StrongBuy","Strong Buy"), ("Buy","Buy"), ("Hold","Hold"),
        ]):
            with col:
                v = rat.get(k, "—")
                metric_card(label, fmt_num(v, prefix="$") if k == "TargetPrice" else str(v))

# ── TAB 2: Financials ─────────────────────────────────────────────────────────
with tab2:
    stmt_choice = st.selectbox("Statement", ["Income_Statement", "Balance_Sheet", "Cash_Flow"])
    df_fin = parse_financials(data, stmt_choice, period_type)

    if df_fin.empty:
        st.info("Keine Daten verfügbar.")
    else:
        # Chart for key metrics
        chart_cols_map = {
            "Income_Statement": ["totalRevenue", "grossProfit", "ebitda", "netIncome"],
            "Balance_Sheet": ["totalAssets", "totalLiab", "totalStockholderEquity", "cash"],
            "Cash_Flow": ["totalCashFromOperatingActivities", "capitalExpenditures", "freeCashFlow", "dividendsPaid"],
        }
        chart_cols = [c for c in chart_cols_map[stmt_choice] if c in df_fin.columns]
        if chart_cols:
            st.plotly_chart(
                plot_financials(df_fin, chart_cols, stmt_choice.replace("_", " "), yformat="$B"),
                use_container_width=True
            )

        # Full table
        st.markdown('<div class="section-header">Rohdaten</div>', unsafe_allow_html=True)
        display_df = df_fin.T.copy()
        display_df = display_df.applymap(lambda x: fmt_num(x) if pd.notna(x) else "—")
        st.dataframe(display_df, use_container_width=True)

# ── TAB 3: Earnings ───────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-header">Earnings History</div>', unsafe_allow_html=True)
    hist = earn.get("History", {})
    if hist:
        rows = []
        for k, v in sorted(hist.items(), reverse=True):
            rows.append({
                "Date": k,
                "EPS Actual": v.get("epsActual"),
                "EPS Estimate": v.get("epsEstimate"),
                "EPS Surprise": v.get("epsDifference"),
                "Surprise %": v.get("surprisePercent"),
            })
        df_earn = pd.DataFrame(rows).head(16)
        df_earn_num = df_earn.copy()
        for col in ["EPS Actual", "EPS Estimate", "EPS Surprise"]:
            df_earn_num[col] = pd.to_numeric(df_earn_num[col], errors="coerce")
        df_earn_num["Surprise %"] = pd.to_numeric(df_earn_num["Surprise %"], errors="coerce")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_earn_num["Date"][::-1],
            y=df_earn_num["EPS Actual"][::-1],
            name="EPS Actual",
            marker_color="#6c8ebf",
        ))
        fig.add_trace(go.Scatter(
            x=df_earn_num["Date"][::-1],
            y=df_earn_num["EPS Estimate"][::-1],
            name="EPS Estimate",
            mode="lines+markers",
            line=dict(color="#f6ad55", width=2, dash="dot"),
        ))
        fig.update_layout(
            paper_bgcolor="#1e2535", plot_bgcolor="#1e2535",
            font_color="#e2e8f0", height=320,
            margin=dict(l=10,r=10,t=20,b=10),
            legend=dict(bgcolor="#1e2535"),
            xaxis=dict(gridcolor="#2d3748"),
            yaxis=dict(gridcolor="#2d3748", title="EPS ($)"),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Colorize surprise
        def color_surprise(val):
            try:
                v = float(val)
                color = "#48bb78" if v > 0 else "#fc8181"
                return f"color: {color}"
            except:
                return ""

        st.dataframe(
            df_earn.style.applymap(color_surprise, subset=["Surprise %"]),
            use_container_width=True, hide_index=True,
        )

    # Upcoming
    st.markdown('<div class="section-header">Upcoming Earnings</div>', unsafe_allow_html=True)
    trend = earn.get("Trend", {})
    if trend:
        rows2 = []
        for k, v in sorted(trend.items()):
            rows2.append({
                "Period": k,
                "EPS Estimate": v.get("epsEstimateAvg"),
                "Revenue Estimate": v.get("revenueEstimateAvg"),
                "EPS Low": v.get("epsEstimateLow"),
                "EPS High": v.get("epsEstimateHigh"),
            })
        st.dataframe(pd.DataFrame(rows2), use_container_width=True, hide_index=True)

# ── TAB 4: Valuation ─────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-header">Bewertungsmultiples</div>', unsafe_allow_html=True)
    vc = st.columns(3)
    val_metrics = [
        ("Forward P/E", fmt_num(val.get("ForwardPE"), decimals=1)),
        ("Trailing P/E", fmt_num(val.get("TrailingPE"), decimals=1)),
        ("P/S (TTM)", fmt_num(val.get("PriceSalesTTM"), decimals=2)),
        ("P/B (MRQ)", fmt_num(val.get("PriceBookMRQ"), decimals=2)),
        ("EV/Revenue", fmt_num(val.get("EnterpriseValueRevenue"), decimals=2)),
        ("EV/EBITDA", fmt_num(val.get("EnterpriseValueEbitda"), decimals=1)),
    ]
    for i, (label, value) in enumerate(val_metrics):
        with vc[i % 3]:
            metric_card(label, value)

    # Shares stats
    ss = data.get("SharesStats", {})
    if ss:
        st.markdown('<div class="section-header">Shares & Float</div>', unsafe_allow_html=True)
        sc = st.columns(3)
        shares_metrics = [
            ("Shares Outstanding", fmt_num(ss.get("SharesOutstanding"))),
            ("Float", fmt_num(ss.get("SharesFloat"))),
            ("Insider Ownership", fmt_pct(ss.get("PercentInsiders"))),
            ("Institutional Ownership", fmt_pct(ss.get("PercentInstitutions"))),
            ("Shares Short", fmt_num(ss.get("SharesShort"))),
            ("Short % Float", fmt_pct(ss.get("ShortPercentFloat"))),
        ]
        for i, (label, value) in enumerate(shares_metrics):
            with sc[i % 3]:
                metric_card(label, value)

# ── TAB 5: Info ───────────────────────────────────────────────────────────────
with tab5:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section-header">Allgemein</div>', unsafe_allow_html=True)
        info_fields = [
            ("ISIN", g.get("ISIN", "—")),
            ("CUSIP", g.get("CUSIP", "—")),
            ("CIK", g.get("CIK", "—")),
            ("Ticker", g.get("Ticker", "—")),
            ("Exchange", g.get("Exchange", "—")),
            ("Country", g.get("CountryName", "—")),
            ("Currency", g.get("CurrencyName", "—")),
            ("IPO Date", g.get("IPODate", "—")),
            ("Fiscal Year End", g.get("FiscalYearEnd", "—")),
        ]
        for label, value in info_fields:
            st.markdown(f"**{label}:** {value}")
    with c2:
        st.markdown('<div class="section-header">Kontakt & Links</div>', unsafe_allow_html=True)
        addr = g.get("Address", "—")
        phone = g.get("Phone", "—")
        web = g.get("WebURL", "")
        st.markdown(f"**Adresse:** {addr}")
        st.markdown(f"**Telefon:** {phone}")
        if web:
            st.markdown(f"**Website:** [{web}]({web})")

    # Officers
    officers = g.get("Officers", {})
    if officers:
        st.markdown('<div class="section-header">Management</div>', unsafe_allow_html=True)
        rows = []
        for o in officers.values():
            rows.append({
                "Name": o.get("Name", "—"),
                "Title": o.get("Title", "—"),
                "YearBorn": o.get("YearBorn", "—"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
