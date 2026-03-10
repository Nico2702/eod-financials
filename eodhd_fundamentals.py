import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fundamentals Viewer",
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
def fmt_num(v, prefix="", suffix="", decimals=2):
    if v is None or v == "" or v == "NA":
        return "—"
    try:
        n = float(v)
        if abs(n) >= 1e12: return f"{prefix}{n/1e12:.{decimals}f}T{suffix}"
        if abs(n) >= 1e9:  return f"{prefix}{n/1e9:.{decimals}f}B{suffix}"
        if abs(n) >= 1e6:  return f"{prefix}{n/1e6:.{decimals}f}M{suffix}"
        return f"{prefix}{n:,.{decimals}f}{suffix}"
    except:
        return str(v)

def fmt_pct(v, decimals=2):
    if v is None or v == "" or v == "NA":
        return "—"
    try:
        return f"{float(v)*100:.{decimals}f}%"
    except:
        return str(v)

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

def safe_dict(d, key):
    v = d.get(key)
    return v if isinstance(v, dict) else {}

# ── API ───────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fundamentals(ticker: str, api_token: str) -> dict:
    url = f"https://eodhd.com/api/fundamentals/{ticker}?api_token={api_token}&fmt=json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

# ── Financials Parser ─────────────────────────────────────────────────────────
def parse_financials(data: dict, statement: str, period: str) -> pd.DataFrame:
    # EODHD uses "yearly" for annual data, "quarterly" for quarterly
    period_key = "yearly" if period == "Annual" else "quarterly"
    try:
        raw = data["Financials"][statement][period_key]
        if not raw:
            return pd.DataFrame()
        rows = []
        for date_key, fields in sorted(raw.items(), reverse=True):
            row = {"Date": date_key}
            row.update(fields)
            rows.append(row)
        df = pd.DataFrame(rows).set_index("Date")
        drop_cols = [c for c in df.columns if c in ("date", "filing_date", "currency_symbol", "type", "period")]
        df = df.drop(columns=drop_cols, errors="ignore")
        df = df.apply(pd.to_numeric, errors="coerce")
        return df.head(8)
    except Exception:
        return pd.DataFrame()

# ── TTM Calculator ────────────────────────────────────────────────────────────
def calculate_ttm(data: dict, statement: str) -> pd.Series:
    """
    Trailing Twelve Months from last 4 quarterly reports.
    - FLOW fields  → sum of last 4 quarters
    - POINT fields → most recent quarter only
    - MARGINS      → recalculated from TTM base values
    """
    SUM_FIELDS = {
        "totalRevenue", "costOfRevenue", "grossProfit",
        "researchDevelopment", "sellingGeneralAdministrative",
        "totalOperatingExpenses", "operatingIncome", "ebitda",
        "interestExpense", "totalOtherIncomeExpensenet",
        "incomeBeforeTax", "incomeTaxExpense", "netIncome",
        "netIncomeApplicableToCommonShares",
        "depreciation", "depreciationAndAmortization",
        "totalCashFromOperatingActivities", "capitalExpenditures",
        "freeCashFlow", "dividendsPaid",
        "totalCashflowsFromInvestingActivities",
        "totalCashFromFinancingActivities",
    }
    LATEST_FIELDS = {
        "totalAssets", "totalCurrentAssets", "cash", "shortTermInvestments",
        "netReceivables", "inventory", "otherCurrentAssets",
        "totalCurrentLiabilities", "shortLongTermDebt", "longTermDebt",
        "totalLiab", "totalStockholderEquity", "retainedEarnings",
        "commonStock", "goodWill", "intangibleAssets",
        "propertyPlantEquipment", "otherAssets",
    }
    try:
        quarterly = data["Financials"][statement].get("quarterly", {})
        if not quarterly:
            return pd.Series(dtype=float)

        sorted_q = sorted(quarterly.keys(), reverse=True)
        last4  = sorted_q[:4]
        latest = sorted_q[0]

        all_fields = set()
        for q in last4:
            all_fields.update(quarterly[q].keys())
        all_fields -= {"date", "filing_date", "currency_symbol", "type", "period"}

        ttm_data = {}
        for field in all_fields:
            if field in SUM_FIELDS:
                vals = []
                for q in last4:
                    try: vals.append(float(quarterly[q].get(field)))
                    except (TypeError, ValueError): pass
                ttm_data[field] = sum(vals) if vals else None
            elif field in LATEST_FIELDS:
                try: ttm_data[field] = float(quarterly[latest].get(field))
                except (TypeError, ValueError): ttm_data[field] = None
            else:
                vals = []
                for q in last4:
                    try: vals.append(float(quarterly[q].get(field)))
                    except (TypeError, ValueError): pass
                ttm_data[field] = sum(vals) if len(vals) == len(last4) else None

        # Derived margins & ratios
        rev    = ttm_data.get("totalRevenue")
        ni     = ttm_data.get("netIncome")
        gp     = ttm_data.get("grossProfit")
        oi     = ttm_data.get("operatingIncome")
        ebitda = ttm_data.get("ebitda")
        cfo    = ttm_data.get("totalCashFromOperatingActivities")
        capex  = ttm_data.get("capitalExpenditures")
        assets = ttm_data.get("totalAssets")
        equity = ttm_data.get("totalStockholderEquity")
        debt   = ttm_data.get("longTermDebt")

        ttm_data["grossMargin"]      = gp  / rev    if rev and gp     else None
        ttm_data["operatingMargin"]  = oi  / rev    if rev and oi     else None
        ttm_data["netMargin"]        = ni  / rev    if rev and ni     else None
        ttm_data["ebitdaMargin"]     = ebitda / rev if rev and ebitda else None
        ttm_data["roa"]              = ni / assets  if assets and ni  else None
        ttm_data["roe"]              = ni / equity  if equity and ni  else None
        fcf = (cfo + capex) if (cfo is not None and capex is not None) else cfo
        ttm_data["freeCashFlowCalc"] = fcf
        ttm_data["fcfMargin"]        = fcf / rev    if rev and fcf    else None
        ttm_data["debtToEquity"]     = debt / equity if equity and debt else None
        ttm_data["_quarters_used"]   = len(last4)
        ttm_data["_latest_quarter"]  = latest

        return pd.Series(ttm_data)
    except Exception:
        return pd.Series(dtype=float)

# ── Chart helper ──────────────────────────────────────────────────────────────
def plot_financials(df: pd.DataFrame, cols: list, title: str):
    fig = go.Figure()
    colors = ["#6c8ebf", "#48bb78", "#fc8181", "#f6ad55", "#b794f4"]
    for i, col in enumerate(cols):
        if col in df.columns:
            fig.add_trace(go.Bar(
                name=col.replace("_", " ").title(),
                x=df.index[::-1],
                y=(df[col] / 1e9)[::-1],
                marker_color=colors[i % len(colors)],
            ))
    fig.update_layout(
        title=title, paper_bgcolor="#1e2535", plot_bgcolor="#1e2535",
        font_color="#e2e8f0", barmode="group", height=340,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(bgcolor="#1e2535", bordercolor="#2d3748", borderwidth=1),
        xaxis=dict(gridcolor="#2d3748"),
        yaxis=dict(gridcolor="#2d3748", title="$B"),
    )
    return fig

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Fundamentals Viewer")
    st.markdown("---")
    ticker_input = st.text_input("Ticker (Exchange)", value="AAPL.US", placeholder="z.B. AAPL.US, SAP.XETRA")
    api_token    = st.text_input("API Token", value="demo", type="password")
    fetch_btn    = st.button("🔍 Laden", use_container_width=True, type="primary")
    st.markdown("---")
    st.markdown("**Beispiel-Ticker**")
    for ex in ["AAPL.US", "MSFT.US", "SAP.XETRA", "VOW3.XETRA", "7203.TSE"]:
        if st.button(ex, use_container_width=True):
            st.session_state["quick_ticker"] = ex
            fetch_btn = True
    period_type = st.radio("Periode", ["TTM", "Annual", "Quarterly"], horizontal=True)
    st.markdown("---")
    st.caption("Powered by EODHD API")

# Resolve quick-ticker clicks
if "quick_ticker" in st.session_state:
    ticker_input = st.session_state.pop("quick_ticker")

# ── Welcome screen ────────────────────────────────────────────────────────────
if not fetch_btn and "fund_data" not in st.session_state:
    st.markdown("""
    <div style="text-align:center; padding: 80px 0; color: #8892a4;">
        <div style="font-size: 48px;">📊</div>
        <div style="font-size: 22px; color: #e2e8f0; font-weight: 700; margin: 16px 0 8px;">
            Fundamentals Viewer
        </div>
        <div>Ticker eingeben und API Token hinterlegen, dann <strong>Laden</strong> klicken.</div>
        <div style="margin-top:8px; font-size:13px;">
            Demo-Modus: Ticker <code>AAPL.US</code>, Token <code>demo</code>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Fetch — always reload on button click ─────────────────────────────────────
if fetch_btn:
    st.session_state.pop("fund_data", None)
    st.session_state.pop("fund_ticker", None)

if "fund_data" not in st.session_state:
    with st.spinner(f"Lade Daten für **{ticker_input}** …"):
        try:
            result = fetch_fundamentals(ticker_input, api_token)
            st.session_state["fund_data"]   = result
            st.session_state["fund_ticker"] = ticker_input
        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")
            st.stop()

data = st.session_state["fund_data"]

g    = safe_dict(data, "General")
hl   = safe_dict(data, "Highlights")
val  = safe_dict(data, "Valuation")
tech = safe_dict(data, "Technicals")
rat  = safe_dict(data, "AnalystRatings")
earn = safe_dict(data, "Earnings")

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_info = st.columns([1, 5])
with col_logo:
    logo = g.get("LogoURL", "")
    if logo:
        st.markdown(f'<img src="{logo}" width="80" style="border-radius:8px;">', unsafe_allow_html=True)
with col_info:
    st.markdown(f'<div class="company-name">{g.get("Name", "—")}</div>', unsafe_allow_html=True)
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

# ═══════════════════════════════════════════════════════════════════
# TAB 1 · Highlights
# ═══════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">Marktdaten & Kennzahlen</div>', unsafe_allow_html=True)
    highlights = [
        ("Market Cap",       fmt_num(hl.get("MarketCapitalization"), prefix="$")),
        ("EV",               fmt_num(hl.get("EnterpriseValue"),       prefix="$")),
        ("52W High",         fmt_num(hl.get("52WeekHigh"),            prefix="$")),
        ("52W Low",          fmt_num(hl.get("52WeekLow"),             prefix="$")),
        ("Revenue TTM",      fmt_num(hl.get("RevenueTTM"),            prefix="$")),
        ("Gross Profit TTM", fmt_num(hl.get("GrossProfitTTM"),        prefix="$")),
        ("EPS",              fmt_num(hl.get("DilutedEpsTTM"),         prefix="$")),
        ("Dividend/Share",   fmt_num(hl.get("DividendShare"),         prefix="$")),
        ("Dividend Yield",   fmt_pct(hl.get("DividendYield"))),
        ("P/E Ratio",        fmt_num(hl.get("PERatio"),               decimals=1)),
        ("PEG Ratio",        fmt_num(hl.get("PEGRatio"),              decimals=2)),
        ("Beta",             fmt_num(tech.get("Beta"),                decimals=2)),
        ("Profit Margin",    fmt_pct(hl.get("ProfitMargin"))),
        ("Operating Margin", fmt_pct(hl.get("OperatingMarginTTM"))),
        ("ROA",              fmt_pct(hl.get("ReturnOnAssetsTTM"))),
        ("ROE",              fmt_pct(hl.get("ReturnOnEquityTTM"))),
    ]
    cols4 = st.columns(4)
    for i, (label, value) in enumerate(highlights):
        with cols4[i % 4]:
            metric_card(label, value)

    if rat:
        st.markdown('<div class="section-header">Analyst Ratings</div>', unsafe_allow_html=True)
        rc = st.columns(5)
        for col, (k, label) in zip(rc, [
            ("Rating","Rating"), ("TargetPrice","Target Price"),
            ("StrongBuy","Strong Buy"), ("Buy","Buy"), ("Hold","Hold"),
        ]):
            rv = rat.get(k, "—")
            with col:
                metric_card(label, fmt_num(rv, prefix="$") if k == "TargetPrice" else str(rv))

# ═══════════════════════════════════════════════════════════════════
# TAB 2 · Financials  (TTM + Historical)
# ═══════════════════════════════════════════════════════════════════
with tab2:
    stmt_choice = st.selectbox("Statement", ["Income_Statement", "Balance_Sheet", "Cash_Flow"])

    TTM_FIELDS = {
        "Income_Statement": [
            ("Revenue TTM",          "totalRevenue",                      "$"),
            ("Gross Profit TTM",     "grossProfit",                       "$"),
            ("Operating Income TTM", "operatingIncome",                   "$"),
            ("EBITDA TTM",           "ebitda",                            "$"),
            ("Net Income TTM",       "netIncome",                         "$"),
            ("Gross Margin TTM",     "grossMargin",                       "%"),
            ("Operating Margin TTM", "operatingMargin",                   "%"),
            ("Net Margin TTM",       "netMargin",                         "%"),
            ("EBITDA Margin TTM",    "ebitdaMargin",                      "%"),
        ],
        "Cash_Flow": [
            ("CFO TTM",              "totalCashFromOperatingActivities",  "$"),
            ("CapEx TTM",            "capitalExpenditures",               "$"),
            ("Free Cash Flow TTM",   "freeCashFlowCalc",                  "$"),
            ("FCF Margin TTM",       "fcfMargin",                         "%"),
        ],
        "Balance_Sheet": [
            ("Total Assets",         "totalAssets",                       "$"),
            ("Total Equity",         "totalStockholderEquity",            "$"),
            ("Long-term Debt",       "longTermDebt",                      "$"),
            ("Cash",                 "cash",                              "$"),
            ("ROA TTM",              "roa",                               "%"),
            ("ROE TTM",              "roe",                               "%"),
            ("Debt / Equity TTM",    "debtToEquity",                      "x"),
        ],
    }

    # ── TTM view ──────────────────────────────────────────────────────
    if period_type == "TTM":
        ttm_series = calculate_ttm(data, stmt_choice)
        if not ttm_series.empty:
            q_used = int(ttm_series.get("_quarters_used", 0))
            q_date = ttm_series.get("_latest_quarter", "—")
            st.markdown(
                f'<div class="section-header">TTM — Trailing Twelve Months '
                f'<span style="font-weight:400; color:#8892a4;">'
                f'(basierend auf {q_used} Quartalen · letztes: {q_date})</span></div>',
                unsafe_allow_html=True
            )
            fields_to_show = TTM_FIELDS.get(stmt_choice, [])
            n_cols = min(len(fields_to_show), 5)
            ttm_cols = st.columns(n_cols)
            for i, (lbl, field, fmt) in enumerate(fields_to_show):
                raw_val = ttm_series.get(field)
                if fmt == "$":
                    display = fmt_num(raw_val, prefix="$")
                elif fmt == "%":
                    display = fmt_pct(raw_val)
                else:
                    display = fmt_num(raw_val, suffix="x", decimals=2) if raw_val is not None else "—"
                with ttm_cols[i % n_cols]:
                    metric_card(lbl, display)
            # ── TTM Rohdaten-Tabelle ──────────────────────────────────
            st.markdown('<div class="section-header">Rohdaten (TTM)</div>', unsafe_allow_html=True)
            # Filter out internal meta fields, build single-column DataFrame
            ttm_raw = {
                k: v for k, v in ttm_series.items()
                if not str(k).startswith("_") and v is not None
            }
            df_ttm = pd.DataFrame.from_dict(ttm_raw, orient="index", columns=["TTM"])
            df_ttm.index.name = "Field"
            # Format values for display
            def fmt_ttm_val(v):
                try:
                    n = float(v)
                    # Detect if likely a ratio/margin (between -10 and 10)
                    if -10 < n < 10 and n != 0:
                        return f"{n*100:.2f}%" if abs(n) < 1 else f"{n:.2f}x"
                    return fmt_num(n)
                except:
                    return str(v)
            df_ttm["TTM"] = df_ttm["TTM"].apply(fmt_ttm_val)
            st.dataframe(df_ttm, use_container_width=True)

        else:
            st.info("Keine Quartalsdaten für TTM-Berechnung verfügbar.")

    # ── Annual / Quarterly view ───────────────────────────────────────
    else:
        df_fin = parse_financials(data, stmt_choice, period_type)
        st.markdown(
            f'<div class="section-header">Historical · {period_type}</div>',
            unsafe_allow_html=True
        )
        if df_fin.empty:
            st.info("Keine Daten verfügbar.")
        else:
            chart_cols_map = {
                "Income_Statement": ["totalRevenue", "grossProfit", "ebitda", "netIncome"],
                "Balance_Sheet":    ["totalAssets", "totalLiab", "totalStockholderEquity", "cash"],
                "Cash_Flow":        ["totalCashFromOperatingActivities", "capitalExpenditures", "freeCashFlow", "dividendsPaid"],
            }
            chart_cols = [c for c in chart_cols_map[stmt_choice] if c in df_fin.columns]
            if chart_cols:
                st.plotly_chart(
                    plot_financials(df_fin, chart_cols, stmt_choice.replace("_", " ")),
                    use_container_width=True
                )
            st.markdown('<div class="section-header">Rohdaten</div>', unsafe_allow_html=True)
            display_df = df_fin.T.copy()
            display_df = display_df.applymap(lambda x: fmt_num(x) if pd.notna(x) else "—")
            st.dataframe(display_df, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 3 · Earnings
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">Earnings History</div>', unsafe_allow_html=True)
    hist = earn.get("History") if isinstance(earn.get("History"), dict) else {}
    if hist:
        rows = []
        for k, v in sorted(hist.items(), reverse=True):
            rows.append({
                "Date":         k,
                "EPS Actual":   v.get("epsActual"),
                "EPS Estimate": v.get("epsEstimate"),
                "EPS Surprise": v.get("epsDifference"),
                "Surprise %":   v.get("surprisePercent"),
            })
        df_earn     = pd.DataFrame(rows).head(16)
        df_earn_num = df_earn.copy()
        for col in ["EPS Actual", "EPS Estimate", "EPS Surprise", "Surprise %"]:
            df_earn_num[col] = pd.to_numeric(df_earn_num[col], errors="coerce")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_earn_num["Date"][::-1], y=df_earn_num["EPS Actual"][::-1],
            name="EPS Actual", marker_color="#6c8ebf",
        ))
        fig.add_trace(go.Scatter(
            x=df_earn_num["Date"][::-1], y=df_earn_num["EPS Estimate"][::-1],
            name="EPS Estimate", mode="lines+markers",
            line=dict(color="#f6ad55", width=2, dash="dot"),
        ))
        fig.update_layout(
            paper_bgcolor="#1e2535", plot_bgcolor="#1e2535",
            font_color="#e2e8f0", height=320,
            margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(bgcolor="#1e2535"),
            xaxis=dict(gridcolor="#2d3748"),
            yaxis=dict(gridcolor="#2d3748", title="EPS ($)"),
        )
        st.plotly_chart(fig, use_container_width=True)

        def color_surprise(v):
            try: return f"color: {'#48bb78' if float(v) > 0 else '#fc8181'}"
            except: return ""

        st.dataframe(
            df_earn.style.applymap(color_surprise, subset=["Surprise %"]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Keine Earnings-History verfügbar.")

    st.markdown('<div class="section-header">Upcoming Earnings</div>', unsafe_allow_html=True)
    trend = earn.get("Trend") if isinstance(earn.get("Trend"), dict) else {}
    if trend:
        rows2 = []
        for k, v in sorted(trend.items()):
            rows2.append({
                "Period":           k,
                "EPS Estimate":     v.get("epsEstimateAvg"),
                "Revenue Estimate": v.get("revenueEstimateAvg"),
                "EPS Low":          v.get("epsEstimateLow"),
                "EPS High":         v.get("epsEstimateHigh"),
            })
        st.dataframe(pd.DataFrame(rows2), use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 4 · Valuation
# ═══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">Bewertungsmultiples</div>', unsafe_allow_html=True)
    vc = st.columns(3)
    val_metrics = [
        ("Forward P/E",  fmt_num(val.get("ForwardPE"),              decimals=1)),
        ("Trailing P/E", fmt_num(val.get("TrailingPE"),             decimals=1)),
        ("P/S (TTM)",    fmt_num(val.get("PriceSalesTTM"),          decimals=2)),
        ("P/B (MRQ)",    fmt_num(val.get("PriceBookMRQ"),           decimals=2)),
        ("EV/Revenue",   fmt_num(val.get("EnterpriseValueRevenue"), decimals=2)),
        ("EV/EBITDA",    fmt_num(val.get("EnterpriseValueEbitda"),  decimals=1)),
    ]
    for i, (label, value) in enumerate(val_metrics):
        with vc[i % 3]:
            metric_card(label, value)

    ss = safe_dict(data, "SharesStats")
    if ss:
        st.markdown('<div class="section-header">Shares & Float</div>', unsafe_allow_html=True)
        sc = st.columns(3)
        shares_metrics = [
            ("Shares Outstanding",      fmt_num(ss.get("SharesOutstanding"))),
            ("Float",                   fmt_num(ss.get("SharesFloat"))),
            ("Insider Ownership",       fmt_pct(ss.get("PercentInsiders"))),
            ("Institutional Ownership", fmt_pct(ss.get("PercentInstitutions"))),
            ("Shares Short",            fmt_num(ss.get("SharesShort"))),
            ("Short % Float",           fmt_pct(ss.get("ShortPercentFloat"))),
        ]
        for i, (label, value) in enumerate(shares_metrics):
            with sc[i % 3]:
                metric_card(label, value)

# ═══════════════════════════════════════════════════════════════════
# TAB 5 · Info
# ═══════════════════════════════════════════════════════════════════
with tab5:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section-header">Allgemein</div>', unsafe_allow_html=True)
        for label, key in [
            ("ISIN", "ISIN"), ("CUSIP", "CUSIP"), ("CIK", "CIK"),
            ("Ticker", "Ticker"), ("Exchange", "Exchange"),
            ("Country", "CountryName"), ("Currency", "CurrencyName"),
            ("IPO Date", "IPODate"), ("Fiscal Year End", "FiscalYearEnd"),
        ]:
            st.markdown(f"**{label}:** {g.get(key, '—')}")
    with c2:
        st.markdown('<div class="section-header">Kontakt & Links</div>', unsafe_allow_html=True)
        st.markdown(f"**Adresse:** {g.get('Address','—')}")
        st.markdown(f"**Telefon:** {g.get('Phone','—')}")
        web = g.get("WebURL", "")
        if web:
            st.markdown(f"**Website:** [{web}]({web})")

    officers = g.get("Officers", {})
    if isinstance(officers, dict) and officers:
        st.markdown('<div class="section-header">Management</div>', unsafe_allow_html=True)
        rows = [
            {"Name": o.get("Name","—"), "Title": o.get("Title","—"), "YearBorn": o.get("YearBorn","—")}
            for o in officers.values()
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
