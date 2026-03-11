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
    .kz-table { width: 100%; border-collapse: collapse; }
    .kz-header {
        display: flex; justify-content: space-between; align-items: center;
        padding: 10px 14px; border-bottom: 1px solid #2d3748; margin-bottom: 4px;
    }
    .kz-header-title { color: #e2e8f0; font-size: 15px; font-weight: 700; }
    .kz-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 7px 14px; border-bottom: 1px solid #1e2535;
    }
    .kz-row:hover { background: #1e2535; }
    .kz-label { color: #c4cdd8; font-size: 13px; }
    .kz-value { color: #e2e8f0; font-size: 13px; font-weight: 600; margin-left: auto; margin-right: 10px; }
    .grade {
        display: inline-block; border-radius: 4px; padding: 1px 7px;
        font-size: 11px; font-weight: 700; min-width: 28px; text-align: center;
    }
    .grade-ap  { background:#1a3a2a; color:#48bb78; }
    .grade-a   { background:#1a3a2a; color:#68d391; }
    .grade-am  { background:#1c3a1a; color:#9ae6b4; }
    .grade-bp  { background:#2a3a1a; color:#b7eb8f; }
    .grade-b   { background:#2a3520; color:#d3f261; }
    .grade-bm  { background:#3a3010; color:#ffd666; }
    .grade-cp  { background:#3a2810; color:#ffa940; }
    .grade-c   { background:#3a2010; color:#ff7a45; }
    .grade-cm  { background:#3a1a10; color:#ff4d4f; }
    .grade-d   { background:#3a1010; color:#ff4d4f; }
    .grade-na  { background:#2d3748; color:#8892a4; }
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

# ── Grading ───────────────────────────────────────────────────────────────────
def get_grade(value, thresholds):
    """
    thresholds: list of (threshold, grade_key) sorted best→worst.
    For 'higher is better' metrics pass ascending=True (default).
    For 'lower is better' metrics (like P/E) pass ascending=False.
    """
    if value is None:
        return "na", "N/A"
    grades_map = {
        "ap": ("grade-ap", "A+"), "a":  ("grade-a",  "A"),
        "am": ("grade-am", "A-"), "bp": ("grade-bp", "B+"),
        "b":  ("grade-b",  "B"),  "bm": ("grade-bm", "B-"),
        "cp": ("grade-cp", "C+"), "c":  ("grade-c",  "C"),
        "cm": ("grade-cm", "C-"), "d":  ("grade-d",  "D"),
        "na": ("grade-na", "—"),
    }
    for threshold, gkey in thresholds:
        if value >= threshold:
            css, label = grades_map.get(gkey, grades_map["na"])
            return css, label
    css, label = grades_map.get(thresholds[-1][1], grades_map["na"])
    return css, label

def grade_badge(css_class, label):
    return f'<span class="grade {css_class}">{label}</span>'

def compute_kennzahlen(data, hl, val, tech):
    """Compute all kennzahlen from available data. Returns dict of {key: (value, formatted, grade_css, grade_label)}"""
    ttm_is  = calculate_ttm_history(data, "Income_Statement")
    ttm_bs  = calculate_ttm_history(data, "Balance_Sheet")
    ttm_cf  = calculate_ttm_history(data, "Cash_Flow")

    # Raw quarterly data for QoQ growth
    q_is = parse_financials(data, "Income_Statement", "Quarterly")
    q_cf = parse_financials(data, "Cash_Flow",        "Quarterly")

    def latest(df, col):
        try:
            v = df[col].dropna().iloc[0]
            return float(v)
        except:
            return None

    def fv(v): return float(v) if v not in (None, "", "NA") else None
    def pct(v): return fv(v) * 100 if fv(v) is not None else None

    # Raw values
    mcap    = fv(hl.get("MarketCapitalization"))
    ev      = fv(hl.get("EnterpriseValue"))
    revenue = fv(hl.get("RevenueTTM"))
    gp_ttm  = fv(hl.get("GrossProfitTTM"))
    pe      = fv(hl.get("PERatio"))
    fwd_pe  = fv(val.get("ForwardPE"))
    ps      = fv(val.get("PriceSalesTTM"))
    ev_rev  = fv(val.get("EnterpriseValueRevenue"))
    ev_ebit = fv(val.get("EnterpriseValueEbitda"))  # proxy
    roe     = pct(hl.get("ReturnOnEquityTTM"))
    roa     = pct(hl.get("ReturnOnAssetsTTM"))
    op_mar  = pct(hl.get("OperatingMarginTTM"))
    net_mar = pct(hl.get("ProfitMargin"))

    # From TTM history
    ebitda   = latest(ttm_is, "ebitda")
    ebit     = latest(ttm_is, "ebit")
    fcf      = latest(ttm_cf, "freeCashFlowCalc")
    cfo      = latest(ttm_cf, "totalCashFromOperatingActivities")
    rev_ttm  = latest(ttm_is, "totalRevenue") or revenue
    gp       = latest(ttm_is, "grossProfit") or gp_ttm
    ni       = latest(ttm_is, "netIncome")

    # Balance sheet
    assets   = latest(ttm_bs, "totalAssets")
    equity   = latest(ttm_bs, "totalStockholderEquity")
    lt_debt  = latest(ttm_bs, "longTermDebt")
    st_debt  = latest(ttm_bs, "shortLongTermDebt")
    cash     = latest(ttm_bs, "cash")
    cur_ass  = latest(ttm_bs, "totalCurrentAssets")
    cur_lia  = latest(ttm_bs, "totalCurrentLiabilities")
    inv      = latest(ttm_bs, "inventory")
    total_debt = (lt_debt or 0) + (st_debt or 0) if lt_debt or st_debt else None

    # EV: use Highlights value, fallback to MarketCap + Debt - Cash
    if not ev and mcap:
        ev = mcap + (total_debt or 0) - (cash or 0)

    # Computed ratios
    p_fcf      = mcap / fcf         if mcap and fcf and fcf > 0       else None
    ev_ebit_c  = ev   / ebit        if ev and ebit and ebit > 0       else None
    earn_yield = (1/pe * 100)        if pe and pe > 0                  else None
    fcf_yield  = (fcf / mcap * 100)  if fcf and mcap and mcap > 0     else None
    gross_mar  = (gp  / rev_ttm * 100) if gp and rev_ttm              else None
    ebit_mar   = (ebit / rev_ttm * 100) if ebit and rev_ttm           else None
    ebitda_mar = (ebitda / rev_ttm * 100) if ebitda and rev_ttm       else None
    fcf_mar    = (fcf / rev_ttm * 100) if fcf and rev_ttm             else None
    roce       = (ebit / (assets - cur_lia) * 100) if ebit and assets and cur_lia else None
    roic       = (ni / (equity + (total_debt or 0)) * 100) if ni and equity else None
    # ROE: NI TTM / avg(equity now, equity 1Y ago) — fallback to EOD value
    try:
        eq_series = ttm_bs["totalStockholderEquity"].dropna()
        eq_now  = eq_series.iloc[0] if len(eq_series) >= 1 else None
        eq_prev = eq_series.iloc[4] if len(eq_series) >= 5 else (eq_series.iloc[-1] if len(eq_series) >= 2 else None)
        eq_avg  = (eq_now + eq_prev) / 2 if eq_now and eq_prev else eq_now
        roe_calc = (ni / eq_avg * 100) if ni and eq_avg and eq_avg > 0 else None
    except:
        roe_calc = None
    roe = roe_calc if roe_calc is not None else roe
    de_ratio   = (total_debt / equity)  if total_debt and equity and equity > 0 else None
    da_ratio   = (total_debt / assets)  if total_debt and assets and assets > 0 else None
    ea_ratio   = (equity / assets)      if equity and assets and assets > 0     else None
    fcf_debt   = (fcf / total_debt)     if fcf and total_debt and total_debt > 0 else None
    cur_ratio  = (cur_ass / cur_lia)    if cur_ass and cur_lia and cur_lia > 0   else None
    quick_r    = ((cur_ass - (inv or 0)) / cur_lia) if cur_ass and cur_lia and cur_lia > 0 else None
    cash_r     = (cash / cur_lia)       if cash and cur_lia and cur_lia > 0      else None

    # Growth helpers
    def ttm_growth(df, col):
        """TTM: TTM[0] vs TTM[4] (same quarter last year), fallback TTM[1]"""
        try:
            s = df[col].dropna()
            if len(s) >= 5 and s.iloc[4] != 0:
                return (s.iloc[0] / s.iloc[4] - 1) * 100
            elif len(s) >= 2 and s.iloc[1] != 0:
                return (s.iloc[0] / s.iloc[1] - 1) * 100
        except: pass
        return None

    def qoq_growth(df, col):
        """QoQ: Q[0] vs Q[1] — raw quarterly data"""
        try:
            s = df[col].dropna()
            if len(s) >= 2 and s.iloc[1] != 0:
                return (s.iloc[0] / s.iloc[1] - 1) * 100
        except: pass
        return None

    def yoy_growth(df, col):
        """YoY: Q[0] vs Q[4] if available, fallback to Q[1]"""
        try:
            s = df[col].dropna()
            if len(s) >= 5 and s.iloc[4] != 0:
                return (s.iloc[0] / s.iloc[4] - 1) * 100
            elif len(s) >= 2 and s.iloc[1] != 0:
                return (s.iloc[0] / s.iloc[1] - 1) * 100
        except: pass
        return None

    # TTM growth — from TTM history
    rev_gr_ttm    = ttm_growth(ttm_is, "totalRevenue")
    earn_gr_ttm   = ttm_growth(ttm_is, "netIncome")
    eps_gr_ttm    = ttm_growth(ttm_is, "epsCalc")
    ebit_gr_ttm   = ttm_growth(ttm_is, "ebit")
    ebitda_gr_ttm = ttm_growth(ttm_is, "ebitda")
    fcf_gr_ttm    = ttm_growth(ttm_cf, "freeCashFlowCalc")

    # QoQ growth — from raw quarterly data
    rev_gr_qoq    = qoq_growth(q_is, "totalRevenue")
    earn_gr_qoq   = qoq_growth(q_is, "netIncome")
    eps_gr_qoq    = (qoq_growth(q_is, "netIncomeApplicableToCommonShares")
                     or qoq_growth(q_is, "netIncome"))
    ebit_gr_qoq   = qoq_growth(q_is, "ebit")
    ebitda_gr_qoq = qoq_growth(q_is, "ebitda")
    fcf_gr_qoq    = (qoq_growth(q_cf, "freeCashFlow")
                     or qoq_growth(q_cf, "freeCashFlowCalc"))

    # YoY growth — from raw quarterly data (Q[0] vs Q[4])
    rev_gr_yoy    = yoy_growth(q_is, "totalRevenue")
    earn_gr_yoy   = yoy_growth(q_is, "netIncome")
    eps_gr_yoy    = (yoy_growth(q_is, "netIncomeApplicableToCommonShares")
                     or yoy_growth(q_is, "netIncome"))
    ebit_gr_yoy   = ttm_growth(ttm_is, "ebit")
    ebitda_gr_yoy = ttm_growth(ttm_is, "ebitda")
    fcf_gr_yoy    = ttm_growth(ttm_cf, "freeCashFlowCalc")

    # aliases for Key Facts
    ebit_gr    = ebit_gr_yoy
    ebitda_gr  = ebitda_gr_yoy
    fcf_gr     = fcf_gr_yoy

    def fmt_x(v, decimals=2):
        if v is None: return "—"
        return f"{v:.{decimals}f}x"
    def fmt_p(v, decimals=2):
        if v is None: return "—"
        return f"{v:.{decimals}f}%"
    def fmt_n(v, decimals=2):
        if v is None: return "—"
        return f"{v:.{decimals}f}"

    # (value, display, grade_thresholds, higher_is_better)
    results = {
        # VALUE
        "fwd_pe":    (fwd_pe,    fmt_n(fwd_pe,1),   [(0,"ap"),(15,"a"),(20,"am"),(25,"bp"),(30,"b"),(35,"bm"),(40,"cp"),(50,"c")], False),
        "pe":        (pe,        fmt_n(pe,2),        [(0,"ap"),(15,"a"),(20,"am"),(25,"bp"),(30,"b"),(35,"bm"),(40,"cp"),(50,"c")], False),
        "p_fcf":     (p_fcf,     fmt_n(p_fcf,2),     [(0,"ap"),(15,"a"),(20,"am"),(25,"bp"),(30,"b"),(40,"bm"),(50,"cp"),(60,"c")], False),
        "ps":        (ps,        fmt_n(ps,2),        [(0,"ap"),(1,"a"),(2,"am"),(3,"bp"),(5,"b"),(7,"bm"),(10,"cp")],               False),
        "ev_rev":    (ev_rev,    fmt_n(ev_rev,2),    [(0,"ap"),(1,"a"),(2,"am"),(3,"bp"),(5,"b"),(7,"bm"),(10,"cp")],               False),
        "ev_ebit":   (ev_ebit_c, fmt_n(ev_ebit_c,2), [(0,"ap"),(8,"a"),(12,"am"),(16,"bp"),(20,"b"),(25,"bm"),(30,"cp")],          False),
        "ev_ebitda": (ev_ebit,   fmt_n(ev_ebit,2),   [(0,"ap"),(8,"a"),(12,"am"),(16,"bp"),(20,"b"),(25,"bm"),(30,"cp")],          False),
        "earn_yield":(earn_yield,fmt_p(earn_yield),  [(8,"ap"),(6,"a"),(4,"am"),(3,"bp"),(2,"b"),(1,"bm")],                         True),
        "fcf_yield": (fcf_yield, fmt_p(fcf_yield),   [(8,"ap"),(6,"a"),(4,"am"),(3,"bp"),(2,"b"),(1,"bm")],                        True),
        # PROFITABILITY
        "roe":       (roe,       fmt_p(roe),         [(25,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-5,"cp")],           True),
        "roce":      (roce,      fmt_p(roce),        [(25,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm")],                     True),
        "roic":      (roic,      fmt_p(roic),        [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(5,"b"),(0,"bm")],                      True),
        "gross_mar": (gross_mar, fmt_p(gross_mar),   [(70,"ap"),(50,"a"),(40,"am"),(30,"bp"),(20,"b"),(10,"bm"),(0,"cp")],          True),
        "op_mar":    (op_mar,    fmt_p(op_mar),      [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-5,"cp")],           True),
        "net_mar":   (net_mar,   fmt_p(net_mar),     [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(5,"b"),(0,"bm"),(-5,"cp")],            True),
        "ebit_mar":  (ebit_mar,  fmt_p(ebit_mar),    [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm")],                     True),
        "ebitda_mar":(ebitda_mar,fmt_p(ebitda_mar),  [(35,"ap"),(25,"a"),(20,"am"),(15,"bp"),(10,"b"),(5,"bm"),(0,"cp")],           True),
        "fcf_mar":   (fcf_mar,   fmt_p(fcf_mar),     [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(5,"b"),(0,"bm"),(-5,"cp")],            True),
        # GROWTH
        "rev_gr_ttm":    (rev_gr_ttm,    fmt_p(rev_gr_ttm),    [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-5,"cp")], True),
        "rev_gr_qoq":    (rev_gr_qoq,    fmt_p(rev_gr_qoq),    [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-5,"cp")], True),
        "rev_gr_yoy":    (rev_gr_yoy,    fmt_p(rev_gr_yoy),    [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-5,"cp")], True),
        "earn_gr_ttm":   (earn_gr_ttm,   fmt_p(earn_gr_ttm),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "earn_gr_qoq":   (earn_gr_qoq,   fmt_p(earn_gr_qoq),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "earn_gr_yoy":   (earn_gr_yoy,   fmt_p(earn_gr_yoy),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "eps_gr_ttm":    (eps_gr_ttm,    fmt_p(eps_gr_ttm),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "eps_gr_qoq":    (eps_gr_qoq,    fmt_p(eps_gr_qoq),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "eps_gr_yoy":    (eps_gr_yoy,    fmt_p(eps_gr_yoy),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebit_gr_ttm":   (ebit_gr_ttm,   fmt_p(ebit_gr_ttm),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebit_gr_qoq":   (ebit_gr_qoq,   fmt_p(ebit_gr_qoq),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebit_gr_yoy":   (ebit_gr_yoy,   fmt_p(ebit_gr_yoy),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebitda_gr_ttm": (ebitda_gr_ttm, fmt_p(ebitda_gr_ttm), [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebitda_gr_qoq": (ebitda_gr_qoq, fmt_p(ebitda_gr_qoq), [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebitda_gr_yoy": (ebitda_gr_yoy, fmt_p(ebitda_gr_yoy), [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "fcf_gr_ttm":    (fcf_gr_ttm,    fmt_p(fcf_gr_ttm),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "fcf_gr_qoq":    (fcf_gr_qoq,    fmt_p(fcf_gr_qoq),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "fcf_gr_yoy":    (fcf_gr_yoy,    fmt_p(fcf_gr_yoy),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        # aliases for Key Facts
        "ebit_gr":       (ebit_gr_yoy,   fmt_p(ebit_gr_yoy),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebitda_gr":     (ebitda_gr_yoy, fmt_p(ebitda_gr_yoy), [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "fcf_gr":        (fcf_gr_yoy,    fmt_p(fcf_gr_yoy),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        # HEALTH
        "cash_r":    (cash_r,    fmt_n(cash_r),      [(1.5,"ap"),(1.0,"a"),(0.75,"am"),(0.5,"bp"),(0.25,"b"),(0,"bm")],        True),
        "cur_ratio": (cur_ratio, fmt_n(cur_ratio),   [(3,"ap"),(2,"a"),(1.5,"am"),(1.2,"bp"),(1.0,"b"),(0.75,"bm"),(0,"cp")],  True),
        "quick_r":   (quick_r,   fmt_n(quick_r),     [(2,"ap"),(1.5,"a"),(1.0,"am"),(0.75,"bp"),(0.5,"b"),(0.25,"bm"),(0,"cp")],True),
        "ea_ratio":  (ea_ratio,  fmt_n(ea_ratio),    [(0.6,"ap"),(0.4,"a"),(0.3,"am"),(0.2,"bp"),(0.1,"b"),(0,"bm")],          True),
        "de_ratio":  (de_ratio,  fmt_n(de_ratio),    [(0,"ap"),(0.3,"a"),(0.5,"am"),(0.8,"bp"),(1.0,"b"),(1.5,"bm"),(2,"cp")], False),
        "da_ratio":  (da_ratio,  fmt_n(da_ratio),    [(0,"ap"),(0.2,"a"),(0.3,"am"),(0.4,"bp"),(0.5,"b"),(0.6,"bm"),(0.7,"cp")],False),
        "fcf_debt":  (fcf_debt,  fmt_n(fcf_debt),    [(0.5,"ap"),(0.3,"a"),(0.2,"am"),(0.1,"bp"),(0.05,"b"),(0,"bm")],         True),
    }
    return results

def render_kz_col(title, rows, results):
    """Render a kennzahlen column as HTML table."""
    # Compute overall grade for column header
    grades_order = {"ap":10,"a":9,"am":8,"bp":7,"b":6,"bm":5,"cp":4,"c":3,"cm":2,"d":1,"na":0}
    scores = []
    for _, key in rows:
        if key in results:
            v, disp, thresh, higher = results[key]
            if v is not None:
                css, lbl = get_grade(v if higher else -v if v is not None else None,
                                     [(t if higher else -t, g) for t,g in thresh] if not higher else thresh)
                scores.append(grades_order.get(css.replace("grade-",""), 0))

    avg = sum(scores)/len(scores) if scores else 0
    overall_key = max(grades_order, key=lambda k: grades_order[k] if grades_order[k] <= avg else -1)
    overall_labels = {"ap":"A+","a":"A","am":"A-","bp":"B+","b":"B","bm":"B-","cp":"C+","c":"C","cm":"C-","d":"D","na":"—"}
    overall_css = f"grade-{overall_key}"
    overall_lbl = overall_labels.get(overall_key, "—")

    html = f'''
    <div style="background:#1e2535; border:1px solid #2d3748; border-radius:10px; overflow:hidden; height:100%;">
        <div class="kz-header">
            <span class="kz-header-title">{title}</span>
            {grade_badge(overall_css, overall_lbl)}
        </div>'''
    for label, key in rows:
        if key in results:
            v, disp, thresh, higher = results[key]
            if v is not None:
                if higher:
                    css, lbl = get_grade(v, thresh)
                else:
                    rev_thresh = [(-t, g) for t, g in thresh]
                    css, lbl = get_grade(-v, rev_thresh)
            else:
                css, lbl = "grade-na", "—"
            html += f'''
        <div class="kz-row">
            <span class="kz-label">{label}</span>
            <span class="kz-value">{disp}</span>
            {grade_badge(css, lbl)}
        </div>'''
    html += "</div>"
    return html


# ── Value Score ───────────────────────────────────────────────────────────────
def compute_value_score(data: dict, hl: dict, val: dict, price_data: dict = None) -> dict:
    """Compute all Value tab ratios, grades, historical averages and chart data."""
    price_data = price_data or {}

    def fv(v):
        try: return float(v) if v not in (None, "", "NA", "None") else None
        except: return None

    def ratio_grade(v, thresholds, higher_is_better=False):
        """Returns (css_class, label)"""
        if v is None: return "grade-na", "—"
        if higher_is_better:
            return get_grade(v, thresholds)
        # lower is better: negate thresholds
        neg = [(-t, g) for t, g in thresholds]
        return get_grade(-v, neg)

    # ── Market data ──────────────────────────────────────────────────
    mcap   = fv(hl.get("MarketCapitalization"))
    ev_raw = fv(val.get("EnterpriseValue"))

    # Annual data
    a_is = data["Financials"]["Income_Statement"].get("yearly", {})
    a_cf = data["Financials"]["Cash_Flow"].get("yearly", {})
    a_bs = data["Financials"]["Balance_Sheet"].get("yearly", {})
    years_is = sorted(a_is.keys(), reverse=True)
    years_cf = sorted(a_cf.keys(), reverse=True)
    years_bs = sorted(a_bs.keys(), reverse=True)

    def yr(statement, key, idx=0):
        years = sorted(statement.keys(), reverse=True)
        if idx >= len(years): return None
        return fv(statement[years[idx]].get(key))

    # Annual latest fundamentals
    ni_yr    = yr(a_is, "netIncome")
    rev_yr   = yr(a_is, "totalRevenue")
    ebit_yr  = yr(a_is, "ebit")
    ebitda_yr= yr(a_is, "ebitda")
    fcf_yr   = yr(a_cf, "freeCashFlow") or (
        (yr(a_cf, "totalCashFromOperatingActivities") or 0) - abs(yr(a_cf, "capitalExpenditures") or 0)
    )
    equity_yr= yr(a_bs, "totalStockholderEquity")
    lt_debt  = yr(a_bs, "longTermDebt")
    st_debt  = yr(a_bs, "shortLongTermDebt")
    cash_yr  = yr(a_bs, "cash") or yr(a_bs, "cashAndEquivalents")
    total_debt = (lt_debt or 0) + (st_debt or 0)

    # EV: from Valuation, fallback calculated
    ev = ev_raw or (mcap + total_debt - (cash_yr or 0) if mcap else None)

    # TTM from Highlights
    rev_ttm = fv(hl.get("RevenueTTM"))
    eps_ttm = fv(hl.get("EarningsShare"))

    # ── Current Ratios ───────────────────────────────────────────────
    pe_fwd   = fv(val.get("ForwardPE"))
    pe_cur   = fv(val.get("TrailingPE")) or fv(hl.get("PERatio"))
    pe_yr    = (mcap / ni_yr)     if mcap and ni_yr  and ni_yr  > 0 else None
    ps_fwd   = None  # EODHD doesn't provide forward P/S
    ps_cur   = fv(val.get("PriceSalesTTM"))
    ps_yr    = (mcap / rev_yr)    if mcap and rev_yr and rev_yr > 0 else None
    pb_cur   = fv(val.get("PriceBookMRQ"))
    pb_yr    = (mcap / equity_yr) if mcap and equity_yr and equity_yr > 0 else None

    # P/FCF (Cur) — TTM FCF from latest 4 quarters
    q_cf_data = data["Financials"]["Cash_Flow"].get("quarterly", {})
    sorted_qcf = sorted(q_cf_data.keys(), reverse=True)
    fcf_ttm_vals = []
    for q in sorted_qcf[:4]:
        f = fv(q_cf_data[q].get("freeCashFlow"))
        if f is None:
            cfo   = fv(q_cf_data[q].get("totalCashFromOperatingActivities"))
            capex = fv(q_cf_data[q].get("capitalExpenditures"))
            f = cfo - abs(capex) if cfo and capex else None
        if f is not None:
            fcf_ttm_vals.append(f)
    fcf_ttm = sum(fcf_ttm_vals) if len(fcf_ttm_vals) == 4 else None
    pfcf_cur = (mcap / fcf_ttm) if mcap and fcf_ttm and fcf_ttm > 0 else None
    pfcf_yr  = (mcap / fcf_yr)  if mcap and fcf_yr  and fcf_yr  > 0 else None

    ev_rev_cur = fv(val.get("EnterpriseValueRevenue"))
    ev_rev_yr  = (ev / rev_yr)    if ev and rev_yr   and rev_yr  > 0 else None
    ev_ebit_cur= (ev / ebit_yr)   if ev and ebit_yr  and ebit_yr > 0 else None
    ev_ebit_yr = ev_ebit_cur  # same annual basis
    ev_ebitda_cur = fv(val.get("EnterpriseValueEbitda"))
    ev_ebitda_yr  = (ev / ebitda_yr) if ev and ebitda_yr and ebitda_yr > 0 else None

    earn_yield_cur = (1 / pe_cur * 100)      if pe_cur and pe_cur > 0 else None
    earn_yield_yr  = (ni_yr / mcap * 100)    if ni_yr and mcap and mcap > 0 else None
    fcf_yield_ttm  = (fcf_ttm / mcap * 100)  if fcf_ttm and mcap and mcap > 0 else None
    fcf_yield_yr   = (fcf_yr  / mcap * 100)  if fcf_yr  and mcap and mcap > 0 else None

    # PEG Ratio = P/E / EPS Growth Rate (%)
    # Growth rate: YoY EPS growth from annual NI
    ni_cur  = yr(a_is, "netIncome", 0)
    ni_prev = yr(a_is, "netIncome", 1)
    eps_gr_yr = ((ni_cur / ni_prev - 1) * 100) if ni_cur and ni_prev and ni_prev > 0 else None
    peg_fwd  = (pe_fwd / eps_gr_yr)  if pe_fwd  and eps_gr_yr and eps_gr_yr > 0 else None
    peg_cur  = (pe_cur / eps_gr_yr)  if pe_cur  and eps_gr_yr and eps_gr_yr > 0 else None
    peg_yr   = (pe_yr  / eps_gr_yr)  if pe_yr   and eps_gr_yr and eps_gr_yr > 0 else None

    # ── Historical averages using real year-end prices ────────────────
    # price_data: {YYYY: adjusted_close} — last trading day of each year
    def hist_multiple(statement, key, n, use_ev=False, invert_fcf=False):
        """Return n-year average multiple using real year-end prices."""
        years = sorted(statement.keys(), reverse=True)
        vals = []
        for y in years[:n]:
            yr_str = y[:4]
            price  = price_data.get(yr_str)
            fund   = fv(statement[y].get(key))
            if price is None or not fund or fund <= 0:
                continue
            if use_ev:
                # For EV multiples: approximate EV per year as price * shares + debt - cash
                bs_y   = data["Financials"]["Balance_Sheet"]["yearly"].get(y, {})
                ltd    = fv(bs_y.get("longTermDebt")) or 0
                std    = fv(bs_y.get("shortLongTermDebt")) or 0
                csh    = fv(bs_y.get("cash")) or fv(bs_y.get("cashAndEquivalents")) or 0
                shs    = fv(bs_y.get("commonStockSharesOutstanding"))
                if not shs: continue
                ev_y   = price * shs + ltd + std - csh
                vals.append(ev_y / fund)
            else:
                shs = fv(data["Financials"]["Balance_Sheet"]["yearly"].get(y, {}).get("commonStockSharesOutstanding"))
                if not shs: continue
                mcap_y = price * shs
                vals.append(mcap_y / fund)
        return sum(vals) / len(vals) if vals else None

    def fcf_hist_real(n):
        years = sorted(a_cf.keys(), reverse=True)
        vals = []
        for y in years[:n]:
            yr_str = y[:4]
            price  = price_data.get(yr_str)
            f = fv(a_cf[y].get("freeCashFlow"))
            if not f:
                cfo   = fv(a_cf[y].get("totalCashFromOperatingActivities"))
                capex = fv(a_cf[y].get("capitalExpenditures"))
                f = cfo - abs(capex) if cfo and capex else None
            if price is None or not f or f <= 0: continue
            shs = fv(data["Financials"]["Balance_Sheet"]["yearly"].get(y, {}).get("commonStockSharesOutstanding"))
            if not shs: continue
            vals.append(price * shs / f)
        return sum(vals) / len(vals) if vals else None

    def yield_hist_real(statement, key, n):
        years = sorted(statement.keys(), reverse=True)
        vals = []
        for y in years[:n]:
            yr_str = y[:4]
            price  = price_data.get(yr_str)
            fund   = fv(statement[y].get(key))
            if price is None or not fund: continue
            shs = fv(data["Financials"]["Balance_Sheet"]["yearly"].get(y, {}).get("commonStockSharesOutstanding"))
            if not shs: continue
            mcap_y = price * shs
            if mcap_y > 0: vals.append(fund / mcap_y * 100)
        return sum(vals) / len(vals) if vals else None

    pe_3y   = hist_multiple(a_is, "netIncome",             3)
    pe_5y   = hist_multiple(a_is, "netIncome",             5)
    pe_10y  = hist_multiple(a_is, "netIncome",            10)
    ps_3y   = hist_multiple(a_is, "totalRevenue",          3)
    ps_5y   = hist_multiple(a_is, "totalRevenue",          5)
    ps_10y  = hist_multiple(a_is, "totalRevenue",         10)
    pb_3y   = hist_multiple(a_bs, "totalStockholderEquity",3)
    pb_5y   = hist_multiple(a_bs, "totalStockholderEquity",5)
    pb_10y  = hist_multiple(a_bs, "totalStockholderEquity",10)
    pfcf_3y = fcf_hist_real(3)
    pfcf_5y = fcf_hist_real(5)
    pfcf_10y= fcf_hist_real(10)
    ev_rev_3y   = hist_multiple(a_is, "totalRevenue", 3,  use_ev=True)
    ev_rev_5y   = hist_multiple(a_is, "totalRevenue", 5,  use_ev=True)
    ev_rev_10y  = hist_multiple(a_is, "totalRevenue", 10, use_ev=True)
    ev_ebit_3y  = hist_multiple(a_is, "ebit",         3,  use_ev=True)
    ev_ebit_5y  = hist_multiple(a_is, "ebit",         5,  use_ev=True)
    ev_ebit_10y = hist_multiple(a_is, "ebit",         10, use_ev=True)
    ev_ebitda_3y = hist_multiple(a_is, "ebitda",      3,  use_ev=True)
    ev_ebitda_5y = hist_multiple(a_is, "ebitda",      5,  use_ev=True)
    ev_ebitda_10y= hist_multiple(a_is, "ebitda",      10, use_ev=True)
    earn_yield_3y = yield_hist_real(a_is, "netIncome",    3)
    earn_yield_5y = yield_hist_real(a_is, "netIncome",    5)
    earn_yield_10y= yield_hist_real(a_is, "netIncome",   10)
    fcf_yield_3y  = yield_hist_real(a_cf, "freeCashFlow", 3)
    fcf_yield_5y  = yield_hist_real(a_cf, "freeCashFlow", 5)
    fcf_yield_10y = yield_hist_real(a_cf, "freeCashFlow",10)

    # PEG historical averages: avg(P/E_year / EPS_growth_year) per rolling window
    def peg_hist_avg(n):
        years = sorted(a_is.keys(), reverse=True)
        vals = []
        for i in range(min(n, len(years) - 1)):
            y_cur  = years[i]
            y_prev = years[i + 1]
            ni_c = fv(a_is[y_cur].get("netIncome"))
            ni_p = fv(a_is[y_prev].get("netIncome"))
            if not ni_c or not ni_p or ni_p <= 0: continue
            gr = (ni_c / ni_p - 1) * 100
            if gr <= 0: continue
            yr_str = y_cur[:4]
            price  = price_data.get(yr_str)
            shs    = fv(a_bs.get(y_cur, {}).get("commonStockSharesOutstanding"))
            if not price or not shs: continue
            pe_y = price * shs / ni_c if ni_c > 0 else None
            if pe_y: vals.append(pe_y / gr)
        return sum(vals) / len(vals) if vals else None

    peg_3y  = peg_hist_avg(3)
    peg_5y  = peg_hist_avg(5)
    peg_10y = peg_hist_avg(10)

    # ── Grade thresholds ─────────────────────────────────────────────
    PE_T    = [(0,"ap"),(10,"a"),(15,"am"),(20,"bp"),(25,"b"),(30,"bm"),(40,"cp"),(50,"c")]
    PS_T    = [(0,"ap"),(1,"a"),(2,"am"),(3,"bp"),(5,"b"),(7,"bm"),(10,"cp")]
    PB_T    = [(0,"ap"),(1,"a"),(2,"am"),(3,"bp"),(5,"b"),(7,"bm"),(10,"cp")]
    PFCF_T  = [(0,"ap"),(10,"a"),(15,"am"),(20,"bp"),(25,"b"),(35,"bm"),(50,"cp"),(60,"c")]
    EVR_T   = [(0,"ap"),(1,"a"),(2,"am"),(3,"bp"),(5,"b"),(7,"bm"),(10,"cp")]
    EVEBIT_T= [(0,"ap"),(8,"a"),(12,"am"),(16,"bp"),(20,"b"),(25,"bm"),(30,"cp")]
    EVEBDA_T= [(0,"ap"),(8,"a"),(12,"am"),(16,"bp"),(20,"b"),(25,"bm"),(30,"cp")]
    EY_T    = [(12,"ap"),(10,"a"),(8,"am"),(6,"bp"),(4,"b"),(3,"bm"),(2,"cp"),(0,"c")]
    FCFY_T  = [(12,"ap"),(10,"a"),(8,"am"),(6,"bp"),(4,"b"),(3,"bm"),(2,"cp"),(0,"c")]

    def fmt(v, pct=False, decimals=2):
        if v is None: return "—"
        if pct: return f"{v:.{decimals}f} %"
        return f"{v:.{decimals}f}"

    # ── Build rows ───────────────────────────────────────────────────
    # Each row: (label, cur_val, cur_fmt, grade_css, grade_lbl, avg3y, avg5y, avg10y, thresholds, higher)
    def row(label, cur, avg3, avg5, avg10, T, higher=False, pct=False):
        css, lbl = ratio_grade(cur, T, higher_is_better=higher)
        return {
            "label":  label,
            "cur":    cur,
            "fmt":    fmt(cur, pct),
            "css":    css,
            "lbl":    lbl,
            "avg3":   fmt(avg3,  pct),
            "avg5":   fmt(avg5,  pct),
            "avg10":  fmt(avg10, pct),
            "group":  label.split(" ")[0],
            "higher": higher,
        }

    PEG_T   = [(0,"ap"),(0.5,"a"),(1,"am"),(1.5,"bp"),(2,"b"),(3,"bm"),(4,"cp"),(5,"c")]

    rows = [
        row("P/Earnings (Fwd)",      pe_fwd,         None,         None,         None,          PE_T),
        row("P/Earnings (Cur)",      pe_cur,         pe_3y,        pe_5y,        pe_10y,        PE_T),
        row("P/Earnings (Year)",     pe_yr,          pe_3y,        pe_5y,        pe_10y,        PE_T),
        row("P/Sales (Cur)",         ps_cur,         ps_3y,        ps_5y,        ps_10y,        PS_T),
        row("P/Sales (Year)",        ps_yr,          ps_3y,        ps_5y,        ps_10y,        PS_T),
        row("P/Book (Cur)",          pb_cur,         pb_3y,        pb_5y,        pb_10y,        PB_T),
        row("P/Book (Year)",         pb_yr,          pb_3y,        pb_5y,        pb_10y,        PB_T),
        row("P/FCF (Cur)",           pfcf_cur,       pfcf_3y,      pfcf_5y,      pfcf_10y,      PFCF_T),
        row("P/FCF (Year)",          pfcf_yr,        pfcf_3y,      pfcf_5y,      pfcf_10y,      PFCF_T),
        row("PEG Ratio (Fwd)",       peg_fwd,        peg_3y,       peg_5y,       peg_10y,       PEG_T),
        row("PEG Ratio (Cur)",       peg_cur,        peg_3y,       peg_5y,       peg_10y,       PEG_T),
        row("PEG Ratio (Year)",      peg_yr,         peg_3y,       peg_5y,       peg_10y,       PEG_T),
        row("EV/Revenue (Cur)",      ev_rev_cur,     ev_rev_3y,    ev_rev_5y,    ev_rev_10y,    EVR_T),
        row("EV/Revenue (Year)",     ev_rev_yr,      ev_rev_3y,    ev_rev_5y,    ev_rev_10y,    EVR_T),
        row("EV/EBIT (Cur)",         ev_ebit_cur,    ev_ebit_3y,   ev_ebit_5y,   ev_ebit_10y,   EVEBIT_T),
        row("EV/EBIT (Year)",        ev_ebit_yr,     ev_ebit_3y,   ev_ebit_5y,   ev_ebit_10y,   EVEBIT_T),
        row("EV/EBITDA (Cur)",       ev_ebitda_cur,  ev_ebitda_3y, ev_ebitda_5y, ev_ebitda_10y, EVEBDA_T),
        row("EV/EBITDA (Year)",      ev_ebitda_yr,   ev_ebitda_3y, ev_ebitda_5y, ev_ebitda_10y, EVEBDA_T),
        row("Earnings Yield (Cur)",  earn_yield_cur, earn_yield_3y,earn_yield_5y,earn_yield_10y, EY_T,   higher=True, pct=True),
        row("Earnings Yield (Year)", earn_yield_yr,  earn_yield_3y,earn_yield_5y,earn_yield_10y, EY_T,   higher=True, pct=True),
        row("FCF Yield (TTM)",       fcf_yield_ttm,  fcf_yield_3y, fcf_yield_5y, fcf_yield_10y,  FCFY_T, higher=True, pct=True),
        row("FCF Yield (Year)",      fcf_yield_yr,   fcf_yield_3y, fcf_yield_5y, fcf_yield_10y,  FCFY_T, higher=True, pct=True),
    ]

    # ── Overall Score ────────────────────────────────────────────────
    grade_score = {"ap":100,"a":92,"am":84,"bp":76,"b":68,"bm":60,"cp":52,"c":44,"cm":36,"d":28,"na":0}
    scores = [grade_score.get(r["css"].replace("grade-",""), 0) for r in rows if r["css"] != "grade-na"]
    overall_score = sum(scores) / len(scores) if scores else 0
    # For overall score: higher is better → pass as ascending thresholds
    overall_css, overall_lbl = get_grade(overall_score, [
        (96,"ap"),(92,"a"),(84,"am"),(76,"bp"),(68,"b"),(60,"bm"),(52,"cp"),(44,"c"),(36,"cm"),(0,"d")
    ])

    # ── Chart data ───────────────────────────────────────────────────
    chart_rows = []
    for y in sorted(years_is, reverse=False):
        rev  = fv(a_is[y].get("totalRevenue"))
        ni   = fv(a_is[y].get("netIncome"))
        cf_d = a_cf.get(y, {})
        fcf  = fv(cf_d.get("freeCashFlow"))
        if not fcf:
            cfo   = fv(cf_d.get("totalCashFromOperatingActivities"))
            capex = fv(cf_d.get("capitalExpenditures"))
            fcf   = cfo - abs(capex) if cfo and capex else None
        if rev:
            chart_rows.append({
                "Year":      y[:4],
                "Revenue":   round(rev / 1e6) if rev else None,
                "Net Income":round(ni  / 1e6) if ni  else None,
                "FCF":       round(fcf / 1e6) if fcf else None,
            })

    return {
        "rows":          rows,
        "overall_score": overall_score,
        "overall_css":   overall_css,
        "overall_lbl":   overall_lbl,
        "chart_data":    chart_rows,
    }







# ── Drill-Down Engine ─────────────────────────────────────────────────────────
def compute_drilldown(label: str, data: dict, hl: dict, val: dict, price_data: dict) -> dict:
    """
    Returns { formula, components: [(name, value, note)], result, unit }
    for any known metric label.
    """
    def fv(v):
        try: return float(v) if v not in (None, "", "NA", "None") else None
        except: return None
    def pct(v): return f"{v*100:.2f} %" if v is not None else "—"
    def num(v, d=2): return f"{v:.{d}f}" if v is not None else "—"
    def bn(v): return f"{v/1e9:.3f} B" if v is not None else "—"
    def safe(a, b): return a/b if a is not None and b and b != 0 else None

    a_is = data["Financials"]["Income_Statement"].get("yearly", {})
    a_cf = data["Financials"]["Cash_Flow"].get("yearly", {})
    a_bs = data["Financials"]["Balance_Sheet"].get("yearly", {})
    q_is = data["Financials"]["Income_Statement"].get("quarterly", {})
    q_cf = data["Financials"]["Cash_Flow"].get("quarterly", {})
    q_bs = data["Financials"]["Balance_Sheet"].get("quarterly", {})

    years   = sorted(a_is.keys(), reverse=True)
    years_bs= sorted(a_bs.keys(), reverse=True)
    qis     = sorted(q_is.keys(), reverse=True)
    qcf_s   = sorted(q_cf.keys(), reverse=True)
    qbs_s   = sorted(q_bs.keys(), reverse=True)

    def ttm(stmt, key):
        qs = sorted(stmt.keys(), reverse=True)
        vals = [fv(stmt[q].get(key)) for q in qs[:4]]
        return sum(v for v in vals if v is not None) if sum(1 for v in vals if v is not None)==4 else None

    def get_fcf_ttm():
        qs = sorted(q_cf.keys(), reverse=True)
        vals = []
        for q in qs[:4]:
            f = fv(q_cf[q].get("freeCashFlow"))
            if f is None:
                c  = fv(q_cf[q].get("totalCashFromOperatingActivities"))
                cx = fv(q_cf[q].get("capitalExpenditures"))
                f  = c - abs(cx) if c and cx else None
            if f is not None: vals.append(f)
        return sum(vals) if len(vals)==4 else None

    def get_fcf_annual(y):
        cf = a_cf.get(y, {})
        f  = fv(cf.get("freeCashFlow"))
        if f is None:
            c  = fv(cf.get("totalCashFromOperatingActivities"))
            cx = fv(cf.get("capitalExpenditures"))
            f  = c - abs(cx) if c and cx else None
        return f

    mcap   = fv(hl.get("MarketCapitalization"))
    shares = fv(hl.get("SharesOutstanding")) or fv(q_bs[qbs_s[0]].get("commonStockSharesOutstanding")) if qbs_s else None
    price  = mcap / shares if mcap and shares else None
    ev     = fv(val.get("EnterpriseValue"))
    bsQ    = q_bs.get(qbs_s[0], {}) if qbs_s else {}
    bsA    = a_bs.get(years_bs[0], {}) if years_bs else {}
    isA    = a_is.get(years[0], {}) if years else {}
    cfA    = a_cf.get(years[0], {}) if years else {}

    # TTM values
    rev_ttm    = ttm(q_is, "totalRevenue")
    ni_ttm     = ttm(q_is, "netIncome")
    ebit_ttm   = ttm(q_is, "ebit")
    ebitda_ttm = ttm(q_is, "ebitda")
    gp_ttm     = ttm(q_is, "grossProfit")
    oi_ttm     = ttm(q_is, "operatingIncome")
    fcf_ttm    = get_fcf_ttm()
    cfo_ttm    = ttm(q_cf, "totalCashFromOperatingActivities")
    int_ttm    = ttm(q_is, "interestExpense")

    # Annual values
    rev_a    = fv(isA.get("totalRevenue"))
    ni_a     = fv(isA.get("netIncome"))
    ebit_a   = fv(isA.get("ebit"))
    ebitda_a = fv(isA.get("ebitda"))
    gp_a     = fv(isA.get("grossProfit"))
    oi_a     = fv(isA.get("operatingIncome"))
    fcf_a    = get_fcf_annual(years[0]) if years else None
    int_a    = fv(isA.get("interestExpense"))

    # BS quarterly
    cash_q   = fv(bsQ.get("cashAndEquivalents")) or fv(bsQ.get("cash"))
    ltd_q    = fv(bsQ.get("longTermDebt")) or 0
    std_q    = fv(bsQ.get("shortLongTermDebt")) or 0
    debt_q   = ltd_q + std_q
    eq_q     = fv(bsQ.get("totalStockholderEquity"))
    ta_q     = fv(bsQ.get("totalAssets"))
    ca_q     = fv(bsQ.get("totalCurrentAssets"))
    cl_q     = fv(bsQ.get("totalCurrentLiabilities"))

    # BS annual
    cash_a   = fv(bsA.get("cashAndEquivalents")) or fv(bsA.get("cash"))
    ltd_a    = fv(bsA.get("longTermDebt")) or 0
    std_a    = fv(bsA.get("shortLongTermDebt")) or 0
    debt_a   = ltd_a + std_a
    eq_a     = fv(bsA.get("totalStockholderEquity"))
    ta_a     = fv(bsA.get("totalAssets"))
    ca_a     = fv(bsA.get("totalCurrentAssets"))
    cl_a     = fv(bsA.get("totalCurrentLiabilities"))
    eq_prev  = fv(a_bs.get(years_bs[1], {}).get("totalStockholderEquity")) if len(years_bs)>1 else None
    ta_prev  = fv(a_bs.get(years_bs[1], {}).get("totalAssets")) if len(years_bs)>1 else None
    eq_avg   = (eq_a + eq_prev)/2 if eq_a and eq_prev else eq_a
    ta_avg   = (ta_a + ta_prev)/2 if ta_a and ta_prev else ta_a
    tl_q     = fv(bsQ.get("totalLiab"))
    tl_a     = fv(bsA.get("totalLiab"))

    nd_q = debt_q - (cash_q or 0)
    nd_a = debt_a - (cash_a or 0)
    cap_emp_ttm = (ta_q - cl_q) if ta_q and cl_q else None
    ic_ttm = (eq_q or 0) + debt_q
    ic_a   = (eq_a or 0) + debt_a

    UNKNOWN = {"formula": "—", "components": [], "result": "—", "unit": ""}

    # ── lookup table ──────────────────────────────────────────────────
    L = label  # shorthand

    # ── VALUE ─────────────────────────────────────────────────────────
    if "P/Earnings" in L or "P/E" in L:
        pe = safe(mcap, ni_ttm) if "TTM" in L or "Cur" in L else safe(mcap, ni_a)
        ni = ni_ttm if "TTM" in L or "Cur" in L else ni_a
        return {"formula": "Market Cap ÷ Net Income", "fields": ["Highlights.MarketCapitalization", "Income_Statement.netIncome (quarterly, TTM sum)"], "unit": "x",
                "components": [("Market Cap", bn(mcap)), ("Net Income", bn(ni))],
                "result": num(pe)}

    if "P/Sales" in L:
        rev = rev_ttm if "TTM" in L or "Cur" in L else rev_a
        ps  = safe(mcap, rev)
        return {"formula": "Market Cap ÷ Revenue", "fields": ["Highlights.MarketCapitalization", "Income_Statement.totalRevenue (quarterly, TTM sum)"], "unit": "x",
                "components": [("Market Cap", bn(mcap)), ("Revenue", bn(rev))],
                "result": num(ps)}

    if "P/Book" in L:
        pb = safe(mcap, eq_q) if "Cur" in L or "Quarterly" in L else safe(mcap, eq_a)
        eq = eq_q if "Cur" in L or "Quarterly" in L else eq_a
        return {"formula": "Market Cap ÷ Stockholder Equity", "fields": ["Highlights.MarketCapitalization", "Balance_Sheet.totalStockholderEquity"], "unit": "x",
                "components": [("Market Cap", bn(mcap)), ("Stockholder Equity", bn(eq))],
                "result": num(pb)}

    if "P/FCF" in L:
        fcf = fcf_ttm if "TTM" in L or "Cur" in L else fcf_a
        pf  = safe(mcap, fcf)
        return {"formula": "Market Cap ÷ Free Cash Flow", "fields": ["Highlights.MarketCapitalization", "Cash_Flow.freeCashFlow → fallback: totalCashFromOperatingActivities − |capitalExpenditures|"], "unit": "x",
                "components": [("Market Cap", bn(mcap)), ("FCF", bn(fcf)),
                                ("FCF = CFO − CapEx" if fcf_a else "", "")],
                "result": num(pf)}

    if "EV/Revenue" in L:
        rev = rev_ttm if "Cur" in L or "TTM" in L else rev_a
        evr = safe(ev, rev)
        return {"formula": "Enterprise Value ÷ Revenue", "fields": ["Valuation.EnterpriseValue", "Income_Statement.totalRevenue"], "unit": "x",
                "components": [("Enterprise Value", bn(ev)), ("Revenue", bn(rev))],
                "result": num(evr)}

    if "EV/EBIT" in L and "EBITDA" not in L:
        ebit = ebit_ttm if "Cur" in L or "TTM" in L else ebit_a
        r    = safe(ev, ebit)
        return {"formula": "Enterprise Value ÷ EBIT", "fields": ["Valuation.EnterpriseValue", "Income_Statement.ebit"], "unit": "x",
                "components": [("Enterprise Value", bn(ev)), ("EBIT (TTM)", bn(ebit))],
                "result": num(r)}

    if "EV/EBITDA" in L:
        ebitda = ebitda_ttm if "Cur" in L or "TTM" in L else ebitda_a
        r      = safe(ev, ebitda)
        return {"formula": "Enterprise Value ÷ EBITDA", "fields": ["Valuation.EnterpriseValue", "Income_Statement.ebitda"], "unit": "x",
                "components": [("Enterprise Value", bn(ev)), ("EBITDA", bn(ebitda))],
                "result": num(r)}

    if "Earnings Yield" in L:
        ni = ni_ttm if "Cur" in L or "TTM" in L else ni_a
        r  = safe(ni, mcap)
        return {"formula": "Net Income ÷ Market Cap × 100", "unit": "%", "fields": ["Income_Statement.netIncome", "Highlights.MarketCapitalization"],
                "components": [("Net Income", bn(ni)), ("Market Cap", bn(mcap))],
                "result": pct(r)}

    if "FCF Yield" in L:
        fcf = fcf_ttm if "TTM" in L or "Cur" in L else fcf_a
        r   = safe(fcf, mcap)
        return {"formula": "Free Cash Flow ÷ Market Cap × 100", "fields": ["Cash_Flow.freeCashFlow", "Highlights.MarketCapitalization"], "unit": "%",
                "components": [("FCF", bn(fcf)), ("Market Cap", bn(mcap))],
                "result": pct(r)}

    if "PEG" in L:
        fwd_pe = safe(mcap, ni_a)
        trends = data.get("Earnings",{}).get("Trend",{})
        p1y = next((v for v in trends.values() if v.get("period")=="+1y"),{})
        eg  = fv(p1y.get("earningsEstimateGrowth"))
        peg = safe(fwd_pe, (eg*100) if eg else None)
        return {"formula": "Forward P/E ÷ EPS Growth Rate (%)", "fields": ["Highlights.MarketCapitalization", "Income_Statement.netIncome (annual)", "Earnings.Trend[+1y].earningsEstimateGrowth"], "unit": "x",
                "components": [("Forward P/E", num(fwd_pe)), ("EPS Growth (Fwd)", pct(eg))],
                "result": num(peg)}

    # ── PROFITABILITY ──────────────────────────────────────────────────
    if "Return on Assets" in L:
        ni   = ni_ttm if "TTM" in L else ni_a
        ta   = ta_q   if "TTM" in L else ta_avg
        lbl  = "Avg(Assets Y0, Y-1)" if "Year" in L else "Total Assets (latest Q)"
        return {"formula": "Net Income ÷ Total Assets × 100", "fields": ["Income_Statement.netIncome", "Balance_Sheet.totalAssets"], "unit": "%",
                "components": [("Net Income", bn(ni)), (lbl, bn(ta))],
                "result": pct(safe(ni, ta))}

    if "Return on Equity" in L and "Cap" not in L and "Inv" not in L:
        ni   = ni_ttm if "TTM" in L else ni_a
        eq   = eq_q   if "TTM" in L else eq_avg
        lbl  = "Avg(Equity Y0, Y-1)" if "Year" in L else "Equity (latest Q)"
        return {"formula": "Net Income ÷ Stockholder Equity × 100", "fields": ["Income_Statement.netIncome", "Balance_Sheet.totalStockholderEquity"], "unit": "%",
                "components": [("Net Income", bn(ni)), (lbl, bn(eq))],
                "result": pct(safe(ni, eq))}

    if "Return on Cap. Empl" in L or "Return on Capital Empl" in L:
        ebit = ebit_ttm if "TTM" in L else ebit_a
        ce   = cap_emp_ttm if "TTM" in L else ((ta_a - cl_a) if ta_a and cl_a else None)
        return {"formula": "EBIT ÷ Capital Employed × 100\n(Capital Employed = Total Assets − Current Liabilities)", "fields": ["Income_Statement.ebit", "Balance_Sheet.totalAssets", "Balance_Sheet.totalCurrentLiabilities"], "unit": "%",
                "components": [("EBIT", bn(ebit)), ("Total Assets", bn(ta_q if "TTM" in L else ta_a)),
                                ("Current Liabilities", bn(cl_q if "TTM" in L else cl_a)),
                                ("Capital Employed", bn(ce))],
                "result": pct(safe(ebit, ce))}

    if "Return on Inv" in L or "ROIC" in L:
        ni  = ni_ttm if "TTM" in L else ni_a
        inv = ic_ttm if "TTM" in L else ic_a
        return {"formula": "Net Income ÷ Invested Capital × 100\n(Invested Capital = Equity + Total Debt)", "fields": ["Income_Statement.netIncome", "Balance_Sheet.totalStockholderEquity", "Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt"], "unit": "%",
                "components": [("Net Income", bn(ni)), ("Equity", bn(eq_q if "TTM" in L else eq_a)),
                                ("Total Debt", bn(debt_q if "TTM" in L else debt_a)),
                                ("Invested Capital", bn(inv))],
                "result": pct(safe(ni, inv))}

    if "Return on Capital" in L and "Empl" not in L:
        ni  = ni_ttm if "TTM" in L else ni_a
        inv = ic_ttm if "TTM" in L else ic_a
        return {"formula": "Net Income ÷ (Equity + Debt) × 100", "fields": ["Income_Statement.netIncome", "Balance_Sheet.totalStockholderEquity", "Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt"], "unit": "%",
                "components": [("Net Income", bn(ni)), ("Equity + Debt", bn(inv))],
                "result": pct(safe(ni, inv))}

    if "Gross Margin" in L:
        gp  = gp_ttm if "TTM" in L else gp_a
        rev = rev_ttm if "TTM" in L else rev_a
        return {"formula": "Gross Profit ÷ Revenue × 100", "fields": ["Income_Statement.grossProfit", "Income_Statement.totalRevenue"], "unit": "%",
                "components": [("Gross Profit", bn(gp)), ("Revenue", bn(rev))],
                "result": pct(safe(gp, rev))}

    if "Operating Margin" in L:
        oi  = oi_ttm if "TTM" in L else oi_a
        rev = rev_ttm if "TTM" in L else rev_a
        return {"formula": "Operating Income ÷ Revenue × 100", "fields": ["Income_Statement.operatingIncome", "Income_Statement.totalRevenue"], "unit": "%",
                "components": [("Operating Income", bn(oi)), ("Revenue", bn(rev))],
                "result": pct(safe(oi, rev))}

    if "EBIT Margin" in L:
        rev = rev_ttm if "TTM" in L else rev_a
        return {"formula": "EBIT ÷ Revenue × 100", "fields": ["Income_Statement.ebit", "Income_Statement.totalRevenue"], "unit": "%",
                "components": [("EBIT", bn(ebit_ttm if "TTM" in L else ebit_a)), ("Revenue", bn(rev))],
                "result": pct(safe(ebit_ttm if "TTM" in L else ebit_a, rev))}

    if "EBITDA Margin" in L:
        rev = rev_ttm if "TTM" in L else rev_a
        return {"formula": "EBITDA ÷ Revenue × 100", "fields": ["Income_Statement.ebitda", "Income_Statement.totalRevenue"], "unit": "%",
                "components": [("EBITDA", bn(ebitda_ttm if "TTM" in L else ebitda_a)), ("Revenue", bn(rev))],
                "result": pct(safe(ebitda_ttm if "TTM" in L else ebitda_a, rev))}

    if "Net Margin" in L:
        ni  = ni_ttm if "TTM" in L else ni_a
        rev = rev_ttm if "TTM" in L else rev_a
        return {"formula": "Net Income ÷ Revenue × 100", "fields": ["Income_Statement.netIncome", "Income_Statement.totalRevenue"], "unit": "%",
                "components": [("Net Income", bn(ni)), ("Revenue", bn(rev))],
                "result": pct(safe(ni, rev))}

    if "FCF Margin" in L:
        fcf = fcf_ttm if "TTM" in L else fcf_a
        rev = rev_ttm if "TTM" in L else rev_a
        cfo_label = bn(cfo_ttm) if "TTM" in L else bn(fv(cfA.get("totalCashFromOperatingActivities")))
        capex_label = bn(ttm(q_cf,"capitalExpenditures")) if "TTM" in L else bn(fv(cfA.get("capitalExpenditures")))
        return {"formula": "Free Cash Flow ÷ Revenue × 100\n(FCF = CFO − |CapEx|)", "fields": ["Cash_Flow.freeCashFlow → fallback: totalCashFromOperatingActivities − |capitalExpenditures|", "Income_Statement.totalRevenue"], "unit": "%",
                "components": [("FCF", bn(fcf)), ("CFO", cfo_label),
                                ("CapEx", capex_label), ("Revenue", bn(rev))],
                "result": pct(safe(fcf, rev))}

    if "Asset Turnover" in L:
        rev = rev_ttm if "TTM" in L else rev_a
        ta  = ta_q   if "TTM" in L else ta_avg
        return {"formula": "Revenue ÷ Total Assets", "fields": ["Income_Statement.totalRevenue", "Balance_Sheet.totalAssets"], "unit": "x",
                "components": [("Revenue", bn(rev)), ("Total Assets", bn(ta))],
                "result": num(safe(rev, ta))}

    # ── GROWTH ────────────────────────────────────────────────────────
    def growth_dd(field_label, q_stmt, a_stmt, key, q_cf_stmt=None, cf_key=None):
        use_cf = q_cf_stmt is not None
        stmt_q = q_cf_stmt if use_cf else q_stmt
        stmt_a = a_cf if use_cf else a_stmt
        if "TTM" in L:
            qs = sorted(stmt_q.keys(), reverse=True)
            def get_ttm(start):
                vals = [fv(stmt_q[qs[i]].get(cf_key if use_cf else key)) for i in range(start, start+4)]
                return sum(v for v in vals if v is not None) if sum(1 for v in vals if v is not None)==4 else None
            t0 = get_ttm(0); t4 = get_ttm(4)
            gr = safe(t0, t4) - 1 if t0 and t4 else None
            return {"formula": f"(TTM[now] ÷ TTM[1Y ago] − 1) × 100", "fields": ["Income_Statement / Cash_Flow — 4-quarter rolling sum, window[0:4] vs window[4:8]"], "unit": "%",
                    "components": [(f"{field_label} TTM (now)", bn(t0)), (f"{field_label} TTM (1Y ago)", bn(t4))],
                    "result": pct(gr)}
        elif "YoY" in L:
            qs = sorted(stmt_q.keys(), reverse=True)
            v0 = fv(stmt_q[qs[0]].get(cf_key if use_cf else key)) if qs else None
            v4 = fv(stmt_q[qs[4]].get(cf_key if use_cf else key)) if len(qs)>4 else None
            gr = safe(v0, v4) - 1 if v0 and v4 else None
            return {"formula": f"(Q[latest] ÷ Q[same quarter -1Y] − 1) × 100", "fields": ["Income_Statement / Cash_Flow — Q[0] vs Q[4]"], "unit": "%",
                    "components": [(f"{field_label} {qs[0][:7]}", bn(v0)), (f"{field_label} {qs[4][:7] if len(qs)>4 else '—'}", bn(v4))],
                    "result": pct(gr)}
        elif "Year" in L:
            ys = sorted(stmt_a.keys(), reverse=True)
            v0 = fv(stmt_a[ys[0]].get(cf_key if use_cf else key)) if ys else None
            v1 = fv(stmt_a[ys[1]].get(cf_key if use_cf else key)) if len(ys)>1 else None
            gr = safe(v0, v1) - 1 if v0 and v1 else None
            return {"formula": f"(Year[0] ÷ Year[-1] − 1) × 100", "fields": ["Income_Statement / Cash_Flow — yearly[0] vs yearly[1]"], "unit": "%",
                    "components": [(f"{field_label} {ys[0][:4]}", bn(v0)), (f"{field_label} {ys[1][:4] if len(ys)>1 else '—'}", bn(v1))],
                    "result": pct(gr)}
        elif "Fwd" in L:
            trends = data.get("Earnings",{}).get("Trend",{})
            p1y = next((v for v in trends.values() if v.get("period")=="+1y"),{})
            g = fv(p1y.get("revenueEstimateGrowth" if "Revenue" in L else "earningsEstimateGrowth"))
            return {"formula": "Analyst consensus estimate (Earnings.Trend +1y)", "fields": ["Earnings.Trend[+1y].revenueEstimateGrowth", "Earnings.Trend[+1y].earningsEstimateGrowth"], "unit": "%",
                    "components": [("Source", "EODHD Earnings Trend"), ("Period", "+1y"),
                                   ("Estimate", pct(g))],
                    "result": pct(g)}
        return UNKNOWN

    if "Revenue Growth" in L:
        return growth_dd("Revenue", q_is, a_is, "totalRevenue")
    if "Net Income Growth" in L:
        return growth_dd("Net Income", q_is, a_is, "netIncome")
    if "EPS Growth" in L and "Fwd" not in L:
        return growth_dd("Net Inc (EPS proxy)", q_is, a_is, "netIncomeApplicableToCommonShares")
    if "EPS Growth (Fwd)" in L:
        return growth_dd("EPS", None, None, None)
    if "EBIT Growth" in L:
        return growth_dd("EBIT", q_is, a_is, "ebit")
    if "EBITDA Growth" in L:
        return growth_dd("EBITDA", q_is, a_is, "ebitda")
    if "FCF Growth" in L:
        return growth_dd("FCF", q_cf, a_cf, "freeCashFlow", q_cf, "freeCashFlow")

    if "Rule of 40" in L:
        rev_gr = safe(rev_ttm, rev_a) - 1 if rev_ttm and rev_a else None
        fcfm   = safe(fcf_ttm, rev_ttm) if "TTM" in L else safe(fcf_a, rev_a)
        r40    = ((rev_gr or 0)*100 + (fcfm or 0)*100) if rev_gr is not None and fcfm is not None else None
        return {"formula": "Revenue Growth (%) + FCF Margin (%)", "fields": ["Income_Statement.totalRevenue (TTM growth)", "Cash_Flow.freeCashFlow ÷ Income_Statement.totalRevenue"], "unit": "%",
                "components": [("Revenue Growth TTM", pct(rev_gr)),
                                ("FCF Margin TTM", pct(fcfm)),
                                ("= Rule of 40", f"{r40:.2f} %" if r40 else "—")],
                "result": f"{r40:.2f} %" if r40 else "—"}

    # ── HEALTH ─────────────────────────────────────────────────────────
    def _debt(q=True): return debt_q if q else debt_a
    def _cash(q=True): return cash_q if q else cash_a
    def _eq(q=True):   return eq_q   if q else eq_a
    def _ta(q=True):   return ta_q   if q else ta_a
    def _cl(q=True):   return cl_q   if q else cl_a
    def _nd(q=True):   return nd_q   if q else nd_a
    is_q = "Quarterly" in L or "TTM" in L

    if "Cash/Debt" in L:
        c=_cash(is_q); d=_debt(is_q)
        return {"formula": "Cash & Equivalents ÷ Total Debt", "fields": ["Balance_Sheet.cashAndEquivalents", "Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt"], "unit": "x",
                "components": [("Cash", bn(c)), ("Long-Term Debt", bn(ltd_q if is_q else ltd_a)),
                                ("Short-Term Debt", bn(std_q if is_q else std_a)), ("Total Debt", bn(d))],
                "result": num(safe(c,d))}

    if "Debt/Capital" in L:
        d=_debt(is_q); e=_eq(is_q)
        return {"formula": "Total Debt ÷ (Total Debt + Equity)", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Balance_Sheet.totalStockholderEquity"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("Equity", bn(e)), ("Capital", bn(d+(e or 0)))],
                "result": num(safe(d, d+(e or 0)))}

    if "FCF/Debt" in L:
        d=_debt(is_q); f=fcf_ttm if is_q else fcf_a
        return {"formula": "Free Cash Flow ÷ Total Debt", "fields": ["Cash_Flow.freeCashFlow", "Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt"], "unit": "x",
                "components": [("FCF", bn(f)), ("Total Debt", bn(d))],
                "result": num(safe(f,d))}

    if "Interest Coverage" in L:
        e=ebit_ttm if "TTM" in L else ebit_a; i=int_ttm if "TTM" in L else int_a
        return {"formula": "EBIT ÷ Interest Expense", "fields": ["Income_Statement.ebit", "Income_Statement.interestExpense"], "unit": "x",
                "components": [("EBIT", bn(e)), ("Interest Expense", bn(i))],
                "result": num(safe(e, abs(i) if i else None))}

    if "Cash Ratio" in L or "Cash/Ratio" in L:
        c=_cash(is_q); cl=_cl(is_q)
        return {"formula": "Cash & Equivalents ÷ Current Liabilities", "fields": ["Balance_Sheet.cashAndEquivalents", "Balance_Sheet.totalCurrentLiabilities"], "unit": "x",
                "components": [("Cash", bn(c)), ("Current Liabilities", bn(cl))],
                "result": num(safe(c,cl))}

    if "Debt/Equity" in L and "Net" not in L:
        d=_debt(is_q); e=_eq(is_q)
        return {"formula": "Total Debt ÷ Stockholder Equity", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Balance_Sheet.totalStockholderEquity"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("Equity", bn(e))],
                "result": num(safe(d,e))}

    if "NetDebt/Equity" in L:
        nd=_nd(is_q); e=_eq(is_q)
        c=_cash(is_q); d=_debt(is_q)
        return {"formula": "Net Debt ÷ Equity\n(Net Debt = Total Debt − Cash)", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Balance_Sheet.cashAndEquivalents", "Balance_Sheet.totalStockholderEquity"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("Cash", bn(c)), ("Net Debt", bn(nd)), ("Equity", bn(e))],
                "result": num(safe(nd,e))}

    if "Equity/Assets" in L:
        e=_eq(is_q); ta=_ta(is_q)
        return {"formula": "Stockholder Equity ÷ Total Assets", "fields": ["Balance_Sheet.totalStockholderEquity", "Balance_Sheet.totalAssets"], "unit": "x",
                "components": [("Equity", bn(e)), ("Total Assets", bn(ta))],
                "result": num(safe(e,ta))}

    if "Debt/Asset" in L and "Net" not in L:
        d=_debt(is_q); ta=_ta(is_q)
        return {"formula": "Total Debt ÷ Total Assets", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Balance_Sheet.totalAssets"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("Total Assets", bn(ta))],
                "result": num(safe(d,ta))}

    if "NetDebt/Asset" in L:
        nd=_nd(is_q); ta=_ta(is_q)
        c=_cash(is_q); d=_debt(is_q)
        return {"formula": "Net Debt ÷ Total Assets\n(Net Debt = Total Debt − Cash)", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Balance_Sheet.cashAndEquivalents", "Balance_Sheet.totalAssets"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("Cash", bn(c)), ("Net Debt", bn(nd)), ("Total Assets", bn(ta))],
                "result": num(safe(nd,ta))}

    if "Debt/EBIT" in L and "EBITDA" not in L and "Net" not in L:
        d=_debt(is_q); e=ebit_ttm if "TTM" in L else ebit_a
        return {"formula": "Total Debt ÷ EBIT", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Income_Statement.ebit"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("EBIT", bn(e))],
                "result": num(safe(d,e))}

    if "NetDebt/EBIT" in L and "EBITDA" not in L:
        nd=_nd(is_q); e=ebit_ttm if "TTM" in L else ebit_a
        c=_cash(is_q); d=_debt(is_q)
        return {"formula": "Net Debt ÷ EBIT\n(Net Debt = Total Debt − Cash)", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Balance_Sheet.cashAndEquivalents", "Income_Statement.ebit"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("Cash", bn(c)), ("Net Debt", bn(nd)), ("EBIT", bn(e))],
                "result": num(safe(nd,e))}

    if "Debt/EBITDA" in L and "Net" not in L:
        d=_debt(is_q); e=ebitda_ttm if "TTM" in L else ebitda_a
        return {"formula": "Total Debt ÷ EBITDA", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Income_Statement.ebitda"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("EBITDA", bn(e))],
                "result": num(safe(d,e))}

    if "NetDebt/EBITDA" in L:
        nd=_nd(is_q); e=ebitda_ttm if "TTM" in L else ebitda_a
        c=_cash(is_q); d=_debt(is_q)
        return {"formula": "Net Debt ÷ EBITDA\n(Net Debt = Total Debt − Cash)", "fields": ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Balance_Sheet.cashAndEquivalents", "Income_Statement.ebitda"], "unit": "x",
                "components": [("Total Debt", bn(d)), ("Cash", bn(c)), ("Net Debt", bn(nd)), ("EBITDA", bn(e))],
                "result": num(safe(nd,e))}

    if "Current Ratio" in L:
        ca=ca_q if is_q else ca_a; cl=cl_q if is_q else cl_a
        return {"formula": "Current Assets ÷ Current Liabilities", "fields": ["Balance_Sheet.totalCurrentAssets", "Balance_Sheet.totalCurrentLiabilities"], "unit": "x",
                "components": [("Current Assets", bn(ca)), ("Current Liabilities", bn(cl))],
                "result": num(safe(ca,cl))}

    if "Quick Ratio" in L:
        ca=ca_q if is_q else ca_a; cl=cl_q if is_q else cl_a
        inv=fv(bsQ.get("inventory") if is_q else bsA.get("inventory")) or 0
        return {"formula": "(Current Assets − Inventory) ÷ Current Liabilities", "fields": ["Balance_Sheet.totalCurrentAssets", "Balance_Sheet.inventory", "Balance_Sheet.totalCurrentLiabilities"], "unit": "x",
                "components": [("Current Assets", bn(ca)), ("Inventory", bn(inv)),
                                ("Current Liabilities", bn(cl))],
                "result": num(safe((ca-inv) if ca else None, cl))}

    if "Altman Z" in L:
        wc=(ca_q-cl_q) if ca_q and cl_q else None
        re=fv(bsQ.get("retainedEarnings"))
        x1=safe(wc,ta_q); x2=safe(re,ta_q); x3=safe(ebit_ttm,ta_q)
        x4=safe(mcap,tl_q); x5=safe(rev_ttm,ta_q)
        z = 1.2*(x1 or 0)+1.4*(x2 or 0)+3.3*(x3 or 0)+0.6*(x4 or 0)+1.0*(x5 or 0) if all([x1,x2,x3,x4,x5]) else None
        return {"formula": "1.2×(WC/TA) + 1.4×(RE/TA) + 3.3×(EBIT/TA) + 0.6×(MCap/TL) + 1.0×(Rev/TA)\n>2.99 = Safe | 1.81–2.99 = Grey | <1.81 = Distress", "fields": ["Balance_Sheet.totalCurrentAssets", "Balance_Sheet.totalCurrentLiabilities", "Balance_Sheet.retainedEarnings", "Balance_Sheet.totalAssets", "Balance_Sheet.totalLiab", "Income_Statement.ebit (TTM)", "Income_Statement.totalRevenue (TTM)", "Highlights.MarketCapitalization"],
                "unit": "",
                "components": [("Working Capital / Total Assets (X1)", f"{x1:.4f}" if x1 else "—"),
                                ("Retained Earnings / Total Assets (X2)", f"{x2:.4f}" if x2 else "—"),
                                ("EBIT / Total Assets (X3)", f"{x3:.4f}" if x3 else "—"),
                                ("Market Cap / Total Liabilities (X4)", f"{x4:.4f}" if x4 else "—"),
                                ("Revenue / Total Assets (X5)", f"{x5:.4f}" if x5 else "—")],
                "result": num(z)}

    if "Piotroski" in L:
        return {"formula": "9-Point Score: Profitability (F1–F4) + Leverage (F5–F6) + Efficiency (F7–F9)\n8–9 Strong | 5–7 Neutral | 0–4 Weak", "fields": ["Income_Statement.netIncome", "Cash_Flow.totalCashFromOperatingActivities", "Balance_Sheet.totalAssets", "Balance_Sheet.longTermDebt", "Balance_Sheet.totalCurrentAssets", "Balance_Sheet.totalCurrentLiabilities", "Balance_Sheet.commonStockSharesOutstanding", "Income_Statement.grossProfit", "Income_Statement.totalRevenue"],
                "unit": "/9",
                "components": [
                    ("F1: ROA > 0", "✓/✗"),
                    ("F2: CFO > 0", "✓/✗"),
                    ("F3: ΔROA > 0", "✓/✗"),
                    ("F4: CFO > Net Income (accrual)", "✓/✗"),
                    ("F5: Δ Long-Term Debt ratio < 0", "✓/✗"),
                    ("F6: Δ Current Ratio > 0", "✓/✗"),
                    ("F7: No share dilution", "✓/✗"),
                    ("F8: Δ Gross Margin > 0", "✓/✗"),
                    ("F9: Δ Asset Turnover > 0", "✓/✗"),
                ],
                "result": "See Health tab for score"}

    return UNKNOWN


# ── Quality Score ─────────────────────────────────────────────────────────────
def compute_quality_score(data: dict, hl: dict, price_data: dict = None) -> dict:
    """
    Quality = composite of Growth + Profitability + Health rows,
    re-labelled to match the screenshot (no period suffix on some labels).
    Two charts: ROIC | Gross Margin | FCF Margin  and  Debt/Equity & Cash Ratio.
    """
    # Re-use the three sub-score functions
    gs = compute_growth_score(data, hl)
    ps = compute_profitability_score(data, hl, price_data)
    hs = compute_health_score(data, hl, price_data)

    # ── Select & rename rows from each module ─────────────────────────
    def pick(rows, *labels):
        lmap = {r["label"]: r for r in rows}
        result = []
        for lbl in labels:
            r = lmap.get(lbl)
            if r:
                result.append(r)
        return result

    # Growth rows (keep Fwd / TTM / YoY / Year for Rev, NI, FCF)
    q_growth = pick(gs["rows"],
        "Revenue Growth (Fwd)",  "Revenue Growth (TTM)",
        "Revenue Growth (YoY)",  "Revenue Growth (Year)",
        "Net Income Growth (Fwd)","Net Income Growth (TTM)",
        "Net Income Growth (YoY)","Net Income Growth (Year)",
        "FCF Growth (TTM)",       "FCF Growth (YoY)",
        "FCF Growth (Year)",
    )
    # Rename: strip parentheses for cleaner look in Quality tab
    def relabel(rows, strip_parens=False):
        out = []
        for r in rows:
            nr = dict(r)
            if strip_parens:
                import re
                nr["label"] = re.sub(r"\s*\(.*?\)", "", nr["label"]).strip()
            out.append(nr)
        return out

    # Profitability rows selected for Quality
    q_profit = pick(ps["rows"],
        "Return on Equity (TTM)",          "Return on Equity (Year)",
        "Return on Cap. Empl. (TTM)",      "Return on Cap. Empl. (Year)",
        "Return on Inv. Capital (TTM)",    "Return on Inv. Capital (Year)",
        "Gross Margin (TTM)",              "Gross Margin (Year)",
        "Net Margin (TTM)",                "Net Margin (Year)",
        "FCF Margin (TTM)",                "FCF Margin (Year)",
    )

    # Health rows selected for Quality (drop "(Quarterly)" label noise)
    q_health = pick(hs["rows"],
        "Cash/Debt (Quarterly)",   "Cash/Debt (Year)",
        "Debt/Capital (Quarterly)","Debt/Capital (Year)",
        "FCF/Debt (Quarterly)",    "FCF/Debt (Year)",
        "Interest Coverage (TTM)", "Interest Coverage (Year)",
        "Debt/Equity (Quarterly)", "Debt/Equity (Year)",
        "NetDebt/Equity (Quarterly)","NetDebt/Equity (Year)",
        "Cash Ratio (Quarterly)",  "Cash Ratio (Year)",
        "Debt/Asset (Quarterly)",  "Debt/Asset (Year)",
        "NetDebt/Asset (Quarterly)","NetDebt/Asset (Year)",
        "Debt/EBIT (TTM)",         "Debt/EBIT (Year)",
        "NetDebt/EBIT (TTM)",      "NetDebt/EBIT (Year)",
    )
    # Simplify health labels: "(Quarterly)" → "" , keep "(Year)" and "(TTM)"
    for r in q_health:
        r["label"] = r["label"].replace(" (Quarterly)", "")

    rows = q_growth + q_profit + q_health

    # ── Overall Score (avg of all grade scores) ───────────────────────
    grade_score = {"ap":100,"a":92,"am":84,"bp":76,"b":68,"bm":60,"cp":52,"c":44,"cm":36,"d":28,"na":0}
    scores = [grade_score.get(r["css"].replace("grade-",""), 0) for r in rows if r["css"] != "grade-na"]
    overall_score = sum(scores) / len(scores) if scores else 0
    overall_css, overall_lbl = get_grade(overall_score, [
        (96,"ap"),(92,"a"),(84,"am"),(76,"bp"),(68,"b"),(60,"bm"),(52,"cp"),(44,"c"),(36,"cm"),(0,"d")
    ])

    # ── Chart 1: ROIC | Gross Margin | FCF Margin (annual) ───────────
    def fv(v):
        try: return float(v) if v not in (None,"","NA","None") else None
        except: return None

    a_is = data["Financials"]["Income_Statement"].get("yearly", {})
    a_cf = data["Financials"]["Cash_Flow"].get("yearly", {})
    a_bs = data["Financials"]["Balance_Sheet"].get("yearly", {})

    chart1 = []
    for y in sorted(a_is.keys()):
        is_d = a_is[y]; cf_d = a_cf.get(y, {}); bs_d = a_bs.get(y, {})
        rev  = fv(is_d.get("totalRevenue"))
        gp   = fv(is_d.get("grossProfit"))
        ni   = fv(is_d.get("netIncome"))
        fcf  = fv(cf_d.get("freeCashFlow"))
        if not fcf:
            cfo  = fv(cf_d.get("totalCashFromOperatingActivities"))
            capex= fv(cf_d.get("capitalExpenditures"))
            fcf  = cfo - abs(capex) if cfo and capex else None
        eq   = fv(bs_d.get("totalStockholderEquity"))
        ltd  = fv(bs_d.get("longTermDebt")) or 0
        std  = fv(bs_d.get("shortLongTermDebt")) or 0
        ic   = (eq or 0) + ltd + std
        roic = ni/ic if ni and ic and ic != 0 else None
        gm   = gp/rev if gp and rev and rev != 0 else None
        fcfm = fcf/rev if fcf is not None and rev and rev != 0 else None
        if rev:
            chart1.append({
                "Year":        y[:4],
                "ROIC":        round(roic*100, 2) if roic is not None else None,
                "Gross Margin":round(gm*100,   2) if gm   is not None else None,
                "FCF Margin":  round(fcfm*100, 2) if fcfm is not None else None,
            })

    # ── Chart 2: Debt/Equity & Cash Ratio (annual) ───────────────────
    chart2 = []
    for y in sorted(a_bs.keys()):
        bs_d = a_bs[y]; cf_d = a_cf.get(y, {}); is_d = a_is.get(y, {})
        eq   = fv(bs_d.get("totalStockholderEquity"))
        ltd  = fv(bs_d.get("longTermDebt")) or 0
        std  = fv(bs_d.get("shortLongTermDebt")) or 0
        debt = ltd + std
        ca   = fv(bs_d.get("totalCurrentAssets"))
        cl   = fv(bs_d.get("totalCurrentLiabilities"))
        cash = fv(bs_d.get("cashAndEquivalents")) or fv(bs_d.get("cash"))
        de   = debt/eq   if eq   and eq   != 0 else None
        cr   = cash/cl   if cl   and cl   != 0 and cash is not None else None
        if de is not None or cr is not None:
            chart2.append({
                "Year":         y[:4],
                "Debt Equity":  round(de, 3) if de is not None else None,
                "Cash Ratio":   round(cr, 3) if cr is not None else None,
            })

    return {
        "rows":          rows,
        "overall_score": overall_score,
        "overall_css":   overall_css,
        "overall_lbl":   overall_lbl,
        "chart1":        chart1,
        "chart2":        chart2,
    }


# ── Health Score ──────────────────────────────────────────────────────────────
def compute_health_score(data: dict, hl: dict, price_data: dict = None) -> dict:
    price_data = price_data or {}

    def fv(v):
        try: return float(v) if v not in (None, "", "NA", "None") else None
        except: return None

    a_is = data["Financials"]["Income_Statement"].get("yearly", {})
    a_cf = data["Financials"]["Cash_Flow"].get("yearly", {})
    a_bs = data["Financials"]["Balance_Sheet"].get("yearly", {})
    q_is = data["Financials"]["Income_Statement"].get("quarterly", {})
    q_cf = data["Financials"]["Cash_Flow"].get("quarterly", {})
    q_bs = data["Financials"]["Balance_Sheet"].get("quarterly", {})

    years   = sorted(a_is.keys(), reverse=True)
    years_bs= sorted(a_bs.keys(), reverse=True)
    qis     = sorted(q_is.keys(), reverse=True)
    qcf     = sorted(q_cf.keys(), reverse=True)
    qbs     = sorted(q_bs.keys(), reverse=True)

    def ttm_sum(stmt, key):
        qs = sorted(stmt.keys(), reverse=True)
        vals = [fv(stmt[q].get(key)) for q in qs[:4]]
        return sum(v for v in vals if v is not None) if sum(1 for v in vals if v is not None) == 4 else None

    def safe(a, b): return a / b if a is not None and b and b != 0 else None

    # ── Latest quarterly snapshot ─────────────────────────────────────
    bsQ  = q_bs.get(qbs[0], {}) if qbs else {}
    cash_q  = fv(bsQ.get("cashAndEquivalents")) or fv(bsQ.get("cash"))
    ltd_q   = fv(bsQ.get("longTermDebt"))  or 0
    std_q   = fv(bsQ.get("shortLongTermDebt")) or 0
    debt_q  = ltd_q + std_q
    eq_q    = fv(bsQ.get("totalStockholderEquity"))
    ta_q    = fv(bsQ.get("totalAssets"))
    ca_q    = fv(bsQ.get("totalCurrentAssets"))
    cl_q    = fv(bsQ.get("totalCurrentLiabilities"))
    inv_q   = fv(bsQ.get("inventory")) or 0
    tl_q    = fv(bsQ.get("totalLiab"))
    re_q    = fv(bsQ.get("retainedEarnings"))
    nd_q    = debt_q - (cash_q or 0)
    ncl_q   = fv(bsQ.get("nonCurrentLiabilitiesTotal")) or (tl_q - cl_q if tl_q and cl_q else None)

    # ── Latest annual snapshot ────────────────────────────────────────
    bsA  = a_bs.get(years_bs[0], {}) if years_bs else {}
    isA  = a_is.get(years[0], {}) if years else {}
    cfA  = a_cf.get(years[0], {}) if years else {}
    cash_a  = fv(bsA.get("cashAndEquivalents")) or fv(bsA.get("cash"))
    ltd_a   = fv(bsA.get("longTermDebt"))  or 0
    std_a   = fv(bsA.get("shortLongTermDebt")) or 0
    debt_a  = ltd_a + std_a
    eq_a    = fv(bsA.get("totalStockholderEquity"))
    ta_a    = fv(bsA.get("totalAssets"))
    ca_a    = fv(bsA.get("totalCurrentAssets"))
    cl_a    = fv(bsA.get("totalCurrentLiabilities"))
    inv_a   = fv(bsA.get("inventory")) or 0
    tl_a    = fv(bsA.get("totalLiab"))
    re_a    = fv(bsA.get("retainedEarnings"))
    nd_a    = debt_a - (cash_a or 0)
    ncl_a   = fv(bsA.get("nonCurrentLiabilitiesTotal")) or (tl_a - cl_a if tl_a and cl_a else None)

    # FCF helpers
    def get_fcf_annual(y):
        cf = a_cf.get(y, {})
        f  = fv(cf.get("freeCashFlow"))
        if f is None:
            c  = fv(cf.get("totalCashFromOperatingActivities"))
            cx = fv(cf.get("capitalExpenditures"))
            f  = c - abs(cx) if c and cx else None
        return f

    def get_fcf_ttm():
        qs = sorted(q_cf.keys(), reverse=True)
        vals = []
        for q in qs[:4]:
            f = fv(q_cf[q].get("freeCashFlow"))
            if f is None:
                c  = fv(q_cf[q].get("totalCashFromOperatingActivities"))
                cx = fv(q_cf[q].get("capitalExpenditures"))
                f  = c - abs(cx) if c and cx else None
            if f is not None: vals.append(f)
        return sum(vals) if len(vals) == 4 else None

    fcf_ttm = get_fcf_ttm()
    fcf_a   = get_fcf_annual(years[0]) if years else None

    # Annual income
    ebit_a   = fv(isA.get("ebit"))
    ebitda_a = fv(isA.get("ebitda"))
    int_a    = fv(isA.get("interestExpense"))
    ni_a     = fv(isA.get("netIncome"))
    rev_a    = fv(isA.get("totalRevenue"))
    cfo_a    = fv(cfA.get("totalCashFromOperatingActivities"))

    # TTM income
    ebit_ttm   = ttm_sum(q_is, "ebit")
    ebitda_ttm = ttm_sum(q_is, "ebitda")
    int_ttm    = ttm_sum(q_is, "interestExpense")
    ni_ttm     = ttm_sum(q_is, "netIncome")
    rev_ttm    = ttm_sum(q_is, "totalRevenue")

    # ── Current ratios ────────────────────────────────────────────────
    # Cash/Debt
    cd_q  = safe(cash_q, debt_q)
    cd_a  = safe(cash_a, debt_a)
    # Debt/Capital
    dc_q  = safe(debt_q, (debt_q + (eq_q or 0))) if eq_q else None
    dc_a  = safe(debt_a, (debt_a + (eq_a or 0))) if eq_a else None
    # FCF/Debt
    fd_q  = safe(fcf_ttm, debt_q)
    fd_a  = safe(fcf_a,   debt_a)
    # Interest Coverage
    ic_ttm = safe(ebit_ttm, abs(int_ttm) if int_ttm else None)
    ic_a   = safe(ebit_a,   abs(int_a)   if int_a   else None)
    # Cash Ratio
    cr_q  = safe(cash_q, cl_q)
    cr_a  = safe(cash_a, cl_a)
    # Debt/Equity
    de_q  = safe(debt_q, eq_q)
    de_a  = safe(debt_a, eq_a)
    # NetDebt/Equity
    nde_q = safe(nd_q, eq_q)
    nde_a = safe(nd_a, eq_a)
    # Equity/Assets
    ea_q  = safe(eq_q, ta_q)
    ea_a  = safe(eq_a, ta_a)
    # Debt/Assets
    da_q  = safe(debt_q, ta_q)
    da_a  = safe(debt_a, ta_a)
    # NetDebt/Assets
    nda_q = safe(nd_q, ta_q)
    nda_a = safe(nd_a, ta_a)
    # Debt/EBIT
    debit_ttm = safe(debt_q, ebit_ttm)
    debit_a   = safe(debt_a, ebit_a)
    ndebit_ttm= safe(nd_q,   ebit_ttm)
    ndebit_a  = safe(nd_a,   ebit_a)
    # Debt/EBITDA
    debitda_ttm = safe(debt_q,  ebitda_ttm)
    debitda_a   = safe(debt_a,  ebitda_a)
    ndebitda_ttm= safe(nd_q,    ebitda_ttm)
    ndebitda_a  = safe(nd_a,    ebitda_a)
    # Current Ratio
    cur_q = safe(ca_q, cl_q)
    cur_a = safe(ca_a, cl_a)
    # Quick Ratio
    qr_q  = safe((ca_q - inv_q) if ca_q is not None else None, cl_q)
    qr_a  = safe((ca_a - inv_a) if ca_a is not None else None, cl_a)

    # ── Altman Z-Score ────────────────────────────────────────────────
    mcap = fv(hl.get("MarketCapitalization"))
    def altman_z(ta, ca, cl, re, ebit_v, rev, tl, mcap_v):
        if not all([ta, ca, cl is not None, ebit_v, rev, tl, mcap_v]): return None
        wc = (ca or 0) - (cl or 0)
        x1 = wc  / ta
        x2 = (re or 0) / ta
        x3 = ebit_v / ta
        x4 = mcap_v / tl if tl and tl != 0 else None
        x5 = rev / ta
        if x4 is None: return None
        return 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5

    az_cur = altman_z(ta_q, ca_q, cl_q, re_q, ebit_ttm, rev_ttm, tl_q, mcap)
    az_q   = altman_z(ta_q, ca_q, cl_q, re_q, ebit_ttm, rev_ttm, tl_q, mcap)
    az_a   = altman_z(ta_a, ca_a, cl_a, re_a, ebit_a,   rev_a,   tl_a, mcap)

    # ── Piotroski F-Score ─────────────────────────────────────────────
    def piotroski(is_d, cf_d, bs_d, bs_prev):
        score = 0
        ni  = fv(is_d.get("netIncome"))
        cfo = fv(cf_d.get("totalCashFromOperatingActivities"))
        ta  = fv(bs_d.get("totalAssets"))
        ta_p= fv(bs_prev.get("totalAssets")) if bs_prev else None
        ta_avg = (ta + ta_p)/2 if ta and ta_p else ta
        re  = fv(bs_d.get("retainedEarnings"))
        ltd = (fv(bs_d.get("longTermDebt")) or 0)
        ltd_p=(fv(bs_prev.get("longTermDebt")) or 0) if bs_prev else ltd
        ca  = fv(bs_d.get("totalCurrentAssets"))
        cl  = fv(bs_d.get("totalCurrentLiabilities"))
        ca_p= fv(bs_prev.get("totalCurrentAssets")) if bs_prev else None
        cl_p= fv(bs_prev.get("totalCurrentLiabilities")) if bs_prev else None
        eq  = fv(bs_d.get("totalStockholderEquity"))
        eq_p= fv(bs_prev.get("totalStockholderEquity")) if bs_prev else None
        rev = fv(is_d.get("totalRevenue"))
        gp  = fv(is_d.get("grossProfit"))
        rev_p= fv(a_is.get(years[1], {}).get("totalRevenue")) if len(years)>1 else None
        gp_p = fv(a_is.get(years[1], {}).get("grossProfit")) if len(years)>1 else None
        shares = fv(bs_d.get("commonStockSharesOutstanding"))
        shares_p = fv(bs_prev.get("commonStockSharesOutstanding")) if bs_prev else None
        # F1: ROA > 0
        if ni and ta_avg and ta_avg != 0 and ni/ta_avg > 0: score += 1
        # F2: CFO > 0
        if cfo and cfo > 0: score += 1
        # F3: ΔROA > 0
        if ni and ta_avg and ta_avg != 0:
            roa_c = ni/ta_avg
            ni_p = fv(a_is.get(years[1], {}).get("netIncome")) if len(years)>1 else None
            ta_pp = fv(a_bs.get(years[2], {}).get("totalAssets")) if len(years_bs)>2 else None
            ta_avg_p = (ta_p+ta_pp)/2 if ta_p and ta_pp else ta_p
            if ni_p and ta_avg_p and ta_avg_p != 0 and roa_c > ni_p/ta_avg_p: score += 1
        # F4: CFO > NI (accrual)
        if cfo and ni and cfo > ni: score += 1
        # F5: Δleverage < 0 (lower debt ratio)
        if ta and ta_p:
            lev_c = ltd/ta; lev_p = ltd_p/ta_p
            if lev_c < lev_p: score += 1
        # F6: Δliquidity > 0 (current ratio improved)
        if ca and cl and ca_p and cl_p:
            if (ca/cl) > (ca_p/cl_p): score += 1
        # F7: No new shares issued
        if shares and shares_p and shares <= shares_p: score += 1
        # F8: Δgross margin > 0
        if rev and gp and rev_p and gp_p:
            if (gp/rev) > (gp_p/rev_p): score += 1
        # F9: Δasset turnover > 0
        if rev and ta_avg and ta_avg!=0 and rev_p and ta_p and ta_p!=0:
            if (rev/ta_avg) > (rev_p/ta_p): score += 1
        return score

    bs_prev_a = a_bs.get(years_bs[1], {}) if len(years_bs) > 1 else None
    pf_a = piotroski(isA, cfA, bsA, bs_prev_a) if years else None
    # Current (uses latest quarterly data with annual income/cf)
    pf_cur = pf_a  # best proxy without full quarterly prior year

    # ── Historical averages (annual) ──────────────────────────────────
    def hist_avg(fn, n):
        vals = [fn(i) for i in range(min(n, len(years_bs)))]
        valid = [v for v in vals if v is not None]
        return sum(valid)/len(valid) if valid else None

    def yr_cd(i):
        bs = a_bs.get(years_bs[i], {}); cf = a_cf.get(years_bs[i], {})
        c = fv(bs.get("cashAndEquivalents")) or fv(bs.get("cash"))
        d = (fv(bs.get("longTermDebt")) or 0) + (fv(bs.get("shortLongTermDebt")) or 0)
        return safe(c, d)
    def yr_dc(i):
        bs = a_bs.get(years_bs[i], {})
        d = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        e = fv(bs.get("totalStockholderEquity"))
        return safe(d, d+(e or 0)) if e else None
    def yr_fd(i):
        bs = a_bs.get(years_bs[i], {})
        d  = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        fc = get_fcf_annual(years_bs[i])
        return safe(fc, d)
    def yr_ic(i):
        is_d= a_is.get(years_bs[i], {}); bs= a_bs.get(years_bs[i], {})
        e   = fv(is_d.get("ebit")); ie = fv(is_d.get("interestExpense"))
        return safe(e, abs(ie)) if ie else None
    def yr_cr(i):
        bs  = a_bs.get(years_bs[i], {})
        c   = fv(bs.get("cashAndEquivalents")) or fv(bs.get("cash"))
        cl  = fv(bs.get("totalCurrentLiabilities"))
        return safe(c, cl)
    def yr_de(i):
        bs  = a_bs.get(years_bs[i], {})
        d   = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        e   = fv(bs.get("totalStockholderEquity"))
        return safe(d, e)
    def yr_nde(i):
        bs  = a_bs.get(years_bs[i], {})
        c   = fv(bs.get("cashAndEquivalents")) or fv(bs.get("cash"))
        d   = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        e   = fv(bs.get("totalStockholderEquity"))
        return safe(d-(c or 0), e)
    def yr_ea(i):
        bs  = a_bs.get(years_bs[i], {})
        return safe(fv(bs.get("totalStockholderEquity")), fv(bs.get("totalAssets")))
    def yr_da(i):
        bs  = a_bs.get(years_bs[i], {})
        d   = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d, fv(bs.get("totalAssets")))
    def yr_nda(i):
        bs  = a_bs.get(years_bs[i], {})
        c   = fv(bs.get("cashAndEquivalents")) or fv(bs.get("cash"))
        d   = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d-(c or 0), fv(bs.get("totalAssets")))
    def yr_debit(i):
        bs = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {})
        d  = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d, fv(is_d.get("ebit")))
    def yr_ndebit(i):
        bs = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {})
        c  = fv(bs.get("cashAndEquivalents")) or fv(bs.get("cash"))
        d  = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d-(c or 0), fv(is_d.get("ebit")))
    def yr_debitda(i):
        bs = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {})
        d  = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d, fv(is_d.get("ebitda")))
    def yr_ndebitda(i):
        bs = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {})
        c  = fv(bs.get("cashAndEquivalents")) or fv(bs.get("cash"))
        d  = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d-(c or 0), fv(is_d.get("ebitda")))
    def yr_cur(i):
        bs = a_bs.get(years_bs[i], {})
        return safe(fv(bs.get("totalCurrentAssets")), fv(bs.get("totalCurrentLiabilities")))
    def yr_qr(i):
        bs  = a_bs.get(years_bs[i], {})
        ca  = fv(bs.get("totalCurrentAssets")); cl = fv(bs.get("totalCurrentLiabilities"))
        inv = fv(bs.get("inventory")) or 0
        return safe((ca-inv) if ca else None, cl)
    def yr_az(i):
        bs  = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {}); cf_d= a_cf.get(years_bs[i], {})
        return altman_z(
            fv(bs.get("totalAssets")), fv(bs.get("totalCurrentAssets")),
            fv(bs.get("totalCurrentLiabilities")), fv(bs.get("retainedEarnings")),
            fv(is_d.get("ebit")), fv(is_d.get("totalRevenue")),
            fv(bs.get("totalLiab")), mcap)

    def h(fn, n): return hist_avg(fn, n)

    # ── Grade thresholds ─────────────────────────────────────────────
    # Higher = better
    CD_T    = [(3,"ap"),(2,"a"),(1.5,"am"),(1,"bp"),(0.5,"b"),(0.2,"bm"),(0,"cp")]
    # Debt/Capital: Lower = better → invert
    DC_T    = [(0,"ap"),(0.1,"a"),(0.15,"am"),(0.25,"bp"),(0.35,"b"),(0.5,"bm"),(0.7,"cp")]
    DCi_T   = [(0.7,"cp"),(0.5,"bm"),(0.35,"b"),(0.25,"bp"),(0.15,"am"),(0.1,"a"),(0,"ap")]
    FD_T    = [(2,"ap"),(1,"a"),(0.5,"am"),(0.3,"bp"),(0.1,"b"),(0,"bm")]
    IC_T    = [(20,"ap"),(10,"a"),(5,"am"),(3,"bp"),(1.5,"b"),(1,"bm"),(0,"cp")]
    CR_T    = [(1,"ap"),(0.7,"a"),(0.5,"am"),(0.3,"bp"),(0.2,"b"),(0,"bm")]
    # DE: lower = better
    DE_T    = [(0,"ap"),(0.3,"a"),(0.5,"am"),(1,"bp"),(1.5,"b"),(2,"bm"),(3,"cp")]
    DEi_T   = [(3,"cp"),(2,"bm"),(1.5,"b"),(1,"bp"),(0.5,"am"),(0.3,"a"),(0,"ap")]
    # NDE can be negative (good)
    NDE_T   = [(-1,"ap"),(-0.3,"a"),(0,"am"),(0.5,"bp"),(1,"b"),(2,"bm"),(3,"cp")]
    NDEi_T  = [(3,"cp"),(2,"bm"),(1,"b"),(0.5,"bp"),(0,"am"),(-0.3,"a"),(-1,"ap")]
    # EA: higher = better
    EA_T    = [(0.7,"ap"),(0.6,"a"),(0.5,"am"),(0.4,"bp"),(0.3,"b"),(0.2,"bm"),(0,"cp")]
    # DA: lower = better
    DA_T    = [(0,"ap"),(0.1,"a"),(0.2,"am"),(0.3,"bp"),(0.4,"b"),(0.5,"bm"),(0.7,"cp")]
    DAi_T   = [(0.7,"cp"),(0.5,"bm"),(0.4,"b"),(0.3,"bp"),(0.2,"am"),(0.1,"a"),(0,"ap")]
    # DEBIT, DEBITDA: lower = better
    DEBIT_T = [(0,"ap"),(0.5,"a"),(1,"am"),(2,"bp"),(3,"b"),(5,"bm"),(7,"cp")]
    DEBITi_T= [(7,"cp"),(5,"bm"),(3,"b"),(2,"bp"),(1,"am"),(0.5,"a"),(0,"ap")]
    # CurR, QR: higher = better, but too high can mean inefficiency
    CURR_T  = [(2.5,"ap"),(2,"a"),(1.5,"am"),(1.2,"bp"),(1,"b"),(0.5,"bm"),(0,"cp")]
    # Altman Z: higher = better (>2.99 safe, 1.81-2.99 grey, <1.81 distress)
    AZ_T    = [(5,"ap"),(3,"a"),(2.5,"am"),(2,"bp"),(1.8,"b"),(1,"bm"),(0,"cp")]
    # Piotroski: 8-9=strong, 5-7=avg, 0-4=weak
    PF_T    = [(8,"ap"),(7,"a"),(6,"am"),(5,"bp"),(4,"b"),(2,"bm"),(0,"cp")]

    def fmt_r(v, decimals=2):
        return f"{v:.{decimals}f}" if v is not None else "—"

    def row(label, cur, avg3, avg5, avg10, T, invert=False, decimals=2):
        css, lbl = get_grade(cur, T) if cur is not None else ("grade-na", "—")
        f = lambda v: fmt_r(v, decimals) if v is not None else "—"
        return {
            "label": label, "fmt": f(cur),
            "css": css, "lbl": lbl,
            "avg3": f(avg3), "avg5": f(avg5), "avg10": f(avg10),
            "group": label.split("/")[0].split(" ")[0],
        }

    rows = [
        row("Cash/Debt (Quarterly)",      cd_q,        h(yr_cd,3),    h(yr_cd,5),    h(yr_cd,10),    CD_T),
        row("Cash/Debt (Year)",           cd_a,        h(yr_cd,3),    h(yr_cd,5),    h(yr_cd,10),    CD_T),
        row("Debt/Capital (Quarterly)",   dc_q,        h(yr_dc,3),    h(yr_dc,5),    h(yr_dc,10),    DCi_T),
        row("Debt/Capital (Year)",        dc_a,        h(yr_dc,3),    h(yr_dc,5),    h(yr_dc,10),    DCi_T),
        row("FCF/Debt (Quarterly)",       fd_q,        h(yr_fd,3),    h(yr_fd,5),    h(yr_fd,10),    FD_T),
        row("FCF/Debt (Year)",            fd_a,        h(yr_fd,3),    h(yr_fd,5),    h(yr_fd,10),    FD_T),
        row("Interest Coverage (TTM)",    ic_ttm,      h(yr_ic,3),    h(yr_ic,5),    h(yr_ic,10),    IC_T),
        row("Interest Coverage (Year)",   ic_a,        h(yr_ic,3),    h(yr_ic,5),    h(yr_ic,10),    IC_T),
        row("Cash Ratio (Quarterly)",     cr_q,        h(yr_cr,3),    h(yr_cr,5),    h(yr_cr,10),    CR_T),
        row("Cash Ratio (Year)",          cr_a,        h(yr_cr,3),    h(yr_cr,5),    h(yr_cr,10),    CR_T),
        row("Debt/Equity (Quarterly)",    de_q,        h(yr_de,3),    h(yr_de,5),    h(yr_de,10),    DEi_T),
        row("Debt/Equity (Year)",         de_a,        h(yr_de,3),    h(yr_de,5),    h(yr_de,10),    DEi_T),
        row("NetDebt/Equity (Quarterly)", nde_q,       h(yr_nde,3),   h(yr_nde,5),   h(yr_nde,10),   NDEi_T),
        row("NetDebt/Equity (Year)",      nde_a,       h(yr_nde,3),   h(yr_nde,5),   h(yr_nde,10),   NDEi_T),
        row("Equity/Assets (Quarterly)",  ea_q,        h(yr_ea,3),    h(yr_ea,5),    h(yr_ea,10),    EA_T),
        row("Equity/Assets (Year)",       ea_a,        h(yr_ea,3),    h(yr_ea,5),    h(yr_ea,10),    EA_T),
        row("Debt/Asset (Quarterly)",     da_q,        h(yr_da,3),    h(yr_da,5),    h(yr_da,10),    DAi_T),
        row("Debt/Asset (Year)",          da_a,        h(yr_da,3),    h(yr_da,5),    h(yr_da,10),    DAi_T),
        row("NetDebt/Asset (Quarterly)",  nda_q,       h(yr_nda,3),   h(yr_nda,5),   h(yr_nda,10),   NDEi_T),
        row("NetDebt/Asset (Year)",       nda_a,       h(yr_nda,3),   h(yr_nda,5),   h(yr_nda,10),   NDEi_T),
        row("Debt/EBIT (TTM)",            debit_ttm,   h(yr_debit,3), h(yr_debit,5), h(yr_debit,10), DEBITi_T),
        row("Debt/EBIT (Year)",           debit_a,     h(yr_debit,3), h(yr_debit,5), h(yr_debit,10), DEBITi_T),
        row("NetDebt/EBIT (TTM)",         ndebit_ttm,  h(yr_ndebit,3),h(yr_ndebit,5),h(yr_ndebit,10),NDEi_T),
        row("NetDebt/EBIT (Year)",        ndebit_a,    h(yr_ndebit,3),h(yr_ndebit,5),h(yr_ndebit,10),NDEi_T),
        row("Debt/EBITDA (TTM)",          debitda_ttm, h(yr_debitda,3),h(yr_debitda,5),h(yr_debitda,10),DEBITi_T),
        row("Debt/EBITDA (Year)",         debitda_a,   h(yr_debitda,3),h(yr_debitda,5),h(yr_debitda,10),DEBITi_T),
        row("NetDebt/EBITDA (TTM)",       ndebitda_ttm,h(yr_ndebitda,3),h(yr_ndebitda,5),h(yr_ndebitda,10),NDEi_T),
        row("NetDebt/EBITDA (Year)",      ndebitda_a,  h(yr_ndebitda,3),h(yr_ndebitda,5),h(yr_ndebitda,10),NDEi_T),
        row("Current Ratio (Quarterly)",  cur_q,       h(yr_cur,3),   h(yr_cur,5),   h(yr_cur,10),   CURR_T),
        row("Current Ratio (Year)",       cur_a,       h(yr_cur,3),   h(yr_cur,5),   h(yr_cur,10),   CURR_T),
        row("Quick Ratio (Quarterly)",    qr_q,        h(yr_qr,3),    h(yr_qr,5),    h(yr_qr,10),    CURR_T),
        row("Quick Ratio (Year)",         qr_a,        h(yr_qr,3),    h(yr_qr,5),    h(yr_qr,10),    CURR_T),
        row("Altman Z-Score (Cur)",       az_cur,      h(yr_az,3),    h(yr_az,5),    h(yr_az,10),    AZ_T),
        row("Altman Z-Score (Quarterly)", az_q,        h(yr_az,3),    h(yr_az,5),    h(yr_az,10),    AZ_T),
        row("Altman Z-Score (Year)",      az_a,        h(yr_az,3),    h(yr_az,5),    h(yr_az,10),    AZ_T),
    ]

    def yr_pf(i):
        if i + 1 >= len(years_bs): return None
        y    = years_bs[i]
        is_d = a_is.get(y, {}); cf_d = a_cf.get(y, {}); bs_d = a_bs.get(y, {})
        bs_p = a_bs.get(years_bs[i + 1], {})
        return piotroski(is_d, cf_d, bs_d, bs_p)

    rows += [
        row("Piotroski F-Score (Cur)",  pf_cur, h(yr_pf,3), h(yr_pf,5), h(yr_pf,10), PF_T, decimals=0),
        row("Piotroski F-Score (Year)", pf_a,   h(yr_pf,3), h(yr_pf,5), h(yr_pf,10), PF_T, decimals=0),
    ]

    # ── Overall Score ─────────────────────────────────────────────────
    grade_score = {"ap":100,"a":92,"am":84,"bp":76,"b":68,"bm":60,"cp":52,"c":44,"cm":36,"d":28,"na":0}
    scores = [grade_score.get(r["css"].replace("grade-",""), 0) for r in rows if r["css"] != "grade-na"]
    overall_score = sum(scores) / len(scores) if scores else 0
    overall_css, overall_lbl = get_grade(overall_score, [
        (96,"ap"),(92,"a"),(84,"am"),(76,"bp"),(68,"b"),(60,"bm"),(52,"cp"),(44,"c"),(36,"cm"),(0,"d")
    ])

    # ── Chart data: annual balance sheet breakdown ────────────────────
    chart_rows = []
    for y in sorted(a_bs.keys()):
        bs  = a_bs[y]
        eq  = fv(bs.get("totalStockholderEquity"))
        cl  = fv(bs.get("totalCurrentLiabilities"))
        ncl = fv(bs.get("nonCurrentLiabilitiesTotal")) or \
              ((fv(bs.get("totalLiab")) or 0) - (cl or 0)) or None
        if eq is not None:
            chart_rows.append({
                "Year": y[:4],
                "Total Stockholder Equity":  round(eq  / 1e6, 1) if eq  else None,
                "Total Current Liabilities": round(cl  / 1e6, 1) if cl  else None,
                "Non-current Liabilities":   round(ncl / 1e6, 1) if ncl else None,
            })

    return {
        "rows":          rows,
        "overall_score": overall_score,
        "overall_css":   overall_css,
        "overall_lbl":   overall_lbl,
        "chart_data":    chart_rows,
    }


# ── Growth Score ──────────────────────────────────────────────────────────────
def compute_growth_score(data: dict, hl: dict) -> dict:

    def fv(v):
        try: return float(v) if v not in (None, "", "NA", "None") else None
        except: return None

    a_is = data["Financials"]["Income_Statement"].get("yearly", {})
    a_cf = data["Financials"]["Cash_Flow"].get("yearly", {})
    q_is = data["Financials"]["Income_Statement"].get("quarterly", {})
    q_cf = data["Financials"]["Cash_Flow"].get("quarterly", {})

    years_is = sorted(a_is.keys(), reverse=True)
    years_cf = sorted(a_cf.keys(), reverse=True)

    # ── TTM growth: TTM[0] vs TTM[4] ─────────────────────────────────
    def ttm_gr(stmt, key):
        qs = sorted(stmt.keys(), reverse=True)
        rows = []
        for i in range(len(qs) - 3):
            w = qs[i:i+4]
            vals = [fv(stmt[q].get(key)) for q in w]
            if all(v is not None for v in vals):
                rows.append(sum(vals))
        if len(rows) >= 5 and rows[4] and rows[4] != 0:
            return (rows[0] / rows[4] - 1) * 100
        return None

    # ── YoY: Q[0] vs Q[4] ────────────────────────────────────────────
    def yoy_gr(stmt, key):
        qs = sorted(stmt.keys(), reverse=True)
        if len(qs) < 5: return None
        v0 = fv(stmt[qs[0]].get(key))
        v4 = fv(stmt[qs[4]].get(key))
        if v0 is None or not v4 or v4 == 0: return None
        return (v0 / v4 - 1) * 100

    # ── Annual YoY: year[0] vs year[1] ───────────────────────────────
    def yr_gr(stmt, key):
        ys = sorted(stmt.keys(), reverse=True)
        if len(ys) < 2: return None
        v0 = fv(stmt[ys[0]].get(key))
        v1 = fv(stmt[ys[1]].get(key))
        if v0 is None or not v1 or v1 == 0: return None
        return (v0 / v1 - 1) * 100

    # ── Historical rolling YoY avg ────────────────────────────────────
    def hist_yoy_avg(stmt, key, n):
        ys = sorted(stmt.keys(), reverse=True)
        vals = []
        for i in range(min(n, len(ys) - 1)):
            v0 = fv(stmt[ys[i]].get(key))
            v1 = fv(stmt[ys[i+1]].get(key))
            if v0 is not None and v1 and v1 != 0:
                vals.append((v0 / v1 - 1) * 100)
        return sum(vals) / len(vals) if vals else None

    def fcf_yr(y):
        d = a_cf.get(y, {})
        f = fv(d.get("freeCashFlow"))
        if f is None:
            cfo  = fv(d.get("totalCashFromOperatingActivities"))
            capex= fv(d.get("capitalExpenditures"))
            f = cfo - abs(capex) if cfo and capex else None
        return f

    def fcf_ttm_sum():
        qs = sorted(q_cf.keys(), reverse=True)
        vals = []
        for q in qs[:4]:
            f = fv(q_cf[q].get("freeCashFlow"))
            if f is None:
                cfo  = fv(q_cf[q].get("totalCashFromOperatingActivities"))
                capex= fv(q_cf[q].get("capitalExpenditures"))
                f = cfo - abs(capex) if cfo and capex else None
            if f is not None: vals.append(f)
        return sum(vals) if len(vals) == 4 else None

    def fcf_gr_ttm():
        qs = sorted(q_cf.keys(), reverse=True)
        rows = []
        for i in range(len(qs) - 3):
            w = qs[i:i+4]
            vals = []
            for q in w:
                f = fv(q_cf[q].get("freeCashFlow"))
                if f is None:
                    cfo  = fv(q_cf[q].get("totalCashFromOperatingActivities"))
                    capex= fv(q_cf[q].get("capitalExpenditures"))
                    f = cfo - abs(capex) if cfo and capex else None
                if f is not None: vals.append(f)
            if len(vals) == 4: rows.append(sum(vals))
        if len(rows) >= 5 and rows[4] and rows[4] != 0:
            return (rows[0] / rows[4] - 1) * 100
        return None

    def fcf_yoy():
        qs = sorted(q_cf.keys(), reverse=True)
        if len(qs) < 5: return None
        def get_fcf(q):
            f = fv(q_cf[q].get("freeCashFlow"))
            if f is None:
                cfo  = fv(q_cf[q].get("totalCashFromOperatingActivities"))
                capex= fv(q_cf[q].get("capitalExpenditures"))
                f = cfo - abs(capex) if cfo and capex else None
            return f
        v0 = get_fcf(qs[0]); v4 = get_fcf(qs[4])
        if v0 is None or not v4 or v4 == 0: return None
        return (v0 / v4 - 1) * 100

    def fcf_hist_yoy(n):
        ys = sorted(a_cf.keys(), reverse=True)
        vals = []
        for i in range(min(n, len(ys) - 1)):
            f0 = fcf_yr(ys[i]); f1 = fcf_yr(ys[i+1])
            if f0 is not None and f1 and f1 != 0:
                vals.append((f0 / f1 - 1) * 100)
        return sum(vals) / len(vals) if vals else None

    # ── Forward estimates from Earnings Trends ────────────────────────
    trends = data.get("Earnings", {}).get("Trend", {})
    plus1y = next((v for v in trends.values() if v.get("period") == "+1y"), {})
    rev_gr_fwd = fv(plus1y.get("revenueEstimateGrowth"))
    if rev_gr_fwd: rev_gr_fwd *= 100
    ni_gr_fwd  = fv(plus1y.get("earningsEstimateGrowth"))
    if ni_gr_fwd: ni_gr_fwd *= 100
    eps_gr_fwd = ni_gr_fwd  # same source

    # ── Current values ────────────────────────────────────────────────
    rev_gr_ttm  = ttm_gr(q_is, "totalRevenue")
    rev_gr_yoy  = yoy_gr(q_is, "totalRevenue")
    rev_gr_yr   = yr_gr(a_is,  "totalRevenue")

    ni_gr_ttm   = ttm_gr(q_is, "netIncome")
    ni_gr_yoy   = yoy_gr(q_is, "netIncome")
    ni_gr_yr    = yr_gr(a_is,  "netIncome")

    ni_common   = a_is[years_is[0]].get("netIncomeApplicableToCommonShares") if years_is else None
    ni_common0  = fv(ni_common) or fv(a_is[years_is[0]].get("netIncome")) if years_is else None
    ni_common1  = fv(a_is[years_is[1]].get("netIncomeApplicableToCommonShares")) if len(years_is)>1 else None
    ni_common1  = ni_common1 or (fv(a_is[years_is[1]].get("netIncome")) if len(years_is)>1 else None)
    eps_gr_yr   = (ni_common0 / ni_common1 - 1) * 100 if ni_common0 and ni_common1 and ni_common1 != 0 else None
    eps_gr_ttm  = ttm_gr(q_is, "netIncomeApplicableToCommonShares") or ttm_gr(q_is, "netIncome")
    eps_gr_yoy  = yoy_gr(q_is, "netIncomeApplicableToCommonShares") or yoy_gr(q_is, "netIncome")

    ebit_gr_ttm = ttm_gr(q_is, "ebit")
    ebit_gr_yoy = yoy_gr(q_is, "ebit")
    ebit_gr_yr  = yr_gr(a_is,  "ebit")

    ebitda_gr_ttm = ttm_gr(q_is, "ebitda")
    ebitda_gr_yoy = yoy_gr(q_is, "ebitda")
    ebitda_gr_yr  = yr_gr(a_is,  "ebitda")

    fcf_gr_ttm_v  = fcf_gr_ttm()
    fcf_gr_yoy_v  = fcf_yoy()
    fcf_gr_yr     = yr_gr(a_cf, "freeCashFlow")

    # Rule of 40: Revenue Growth + FCF Margin
    rev_ttm_v = sum(fv(q_is[q].get("totalRevenue")) or 0 for q in sorted(q_is.keys(), reverse=True)[:4])
    fcf_ttm_v = fcf_ttm_sum()
    fcfm_ttm  = fcf_ttm_v / rev_ttm_v * 100 if rev_ttm_v and fcf_ttm_v is not None else None
    ro40_ttm  = (rev_gr_ttm or 0) + (fcfm_ttm or 0) if rev_gr_ttm is not None and fcfm_ttm is not None else None

    rev_yr_v  = fv(a_is[years_is[0]].get("totalRevenue")) if years_is else None
    fcf_yr_v  = fcf_yr(years_is[0]) if years_is else None
    fcfm_yr   = fcf_yr_v / rev_yr_v * 100 if rev_yr_v and fcf_yr_v is not None else None
    ro40_yr   = (rev_gr_yr or 0) + (fcfm_yr or 0) if rev_gr_yr is not None and fcfm_yr is not None else None

    # ── Historical averages ───────────────────────────────────────────
    rev_3y  = hist_yoy_avg(a_is, "totalRevenue", 3)
    rev_5y  = hist_yoy_avg(a_is, "totalRevenue", 5)
    rev_10y = hist_yoy_avg(a_is, "totalRevenue", 10)
    ni_3y   = hist_yoy_avg(a_is, "netIncome",    3)
    ni_5y   = hist_yoy_avg(a_is, "netIncome",    5)
    ni_10y  = hist_yoy_avg(a_is, "netIncome",    10)
    eps_3y  = hist_yoy_avg(a_is, "netIncomeApplicableToCommonShares", 3) or hist_yoy_avg(a_is, "netIncome", 3)
    eps_5y  = hist_yoy_avg(a_is, "netIncomeApplicableToCommonShares", 5) or hist_yoy_avg(a_is, "netIncome", 5)
    eps_10y = hist_yoy_avg(a_is, "netIncomeApplicableToCommonShares", 10) or hist_yoy_avg(a_is, "netIncome", 10)
    ebit_3y = hist_yoy_avg(a_is, "ebit",   3)
    ebit_5y = hist_yoy_avg(a_is, "ebit",   5)
    ebit_10y= hist_yoy_avg(a_is, "ebit",   10)
    ebitda_3y = hist_yoy_avg(a_is, "ebitda", 3)
    ebitda_5y = hist_yoy_avg(a_is, "ebitda", 5)
    ebitda_10y= hist_yoy_avg(a_is, "ebitda", 10)
    fcf_3y  = fcf_hist_yoy(3)
    fcf_5y  = fcf_hist_yoy(5)
    fcf_10y = fcf_hist_yoy(10)

    # Rule of 40 hist avg: rev_gr + fcf_margin per year
    def ro40_hist(n):
        ys = sorted(a_is.keys(), reverse=True)
        vals = []
        for i in range(min(n, len(ys) - 1)):
            r0 = fv(a_is[ys[i]].get("totalRevenue"))
            r1 = fv(a_is[ys[i+1]].get("totalRevenue"))
            rg = (r0/r1 - 1)*100 if r0 and r1 and r1 != 0 else None
            fc = fcf_yr(ys[i])
            fm = fc/r0*100 if fc is not None and r0 and r0 != 0 else None
            if rg is not None and fm is not None: vals.append(rg + fm)
        return sum(vals)/len(vals) if vals else None

    ro40_3y  = ro40_hist(3);  ro40_5y  = ro40_hist(5);  ro40_10y = ro40_hist(10)

    # ── Grade thresholds (higher = better) ───────────────────────────
    REV_T   = [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-5,"cp"),(-10,"c")]
    NI_T    = [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    EPS_T   = [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    EBIT_T  = [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    EBITDA_T= [(40,"ap"),(25,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    FCF_T   = [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    RO40_T  = [(60,"ap"),(50,"a"),(40,"am"),(30,"bp"),(20,"b"),(10,"bm"),(0,"cp"),(-10,"c")]

    def fmt(v): return f"{v:.2f} %" if v is not None else "—"

    def row(label, cur, avg3, avg5, avg10, T):
        css, lbl = get_grade(cur, T) if cur is not None else ("grade-na", "—")
        return {
            "label": label, "fmt": fmt(cur),
            "css": css, "lbl": lbl,
            "avg3":  fmt(avg3),
            "avg5":  fmt(avg5),
            "avg10": fmt(avg10),
            "group": label.split(" ")[0],
        }

    rows = [
        row("Revenue Growth (Fwd)",       rev_gr_fwd,    None,      None,      None,      REV_T),
        row("Revenue Growth (TTM)",        rev_gr_ttm,    rev_3y,    rev_5y,    rev_10y,   REV_T),
        row("Revenue Growth (YoY)",        rev_gr_yoy,    rev_3y,    rev_5y,    rev_10y,   REV_T),
        row("Revenue Growth (Year)",       rev_gr_yr,     rev_3y,    rev_5y,    rev_10y,   REV_T),
        row("Net Income Growth (Fwd)",     ni_gr_fwd,     None,      None,      None,      NI_T),
        row("Net Income Growth (TTM)",     ni_gr_ttm,     ni_3y,     ni_5y,     ni_10y,    NI_T),
        row("Net Income Growth (YoY)",     ni_gr_yoy,     ni_3y,     ni_5y,     ni_10y,    NI_T),
        row("Net Income Growth (Year)",    ni_gr_yr,      ni_3y,     ni_5y,     ni_10y,    NI_T),
        row("EPS Growth (Fwd)",            eps_gr_fwd,    None,      None,      None,      EPS_T),
        row("EPS Growth (TTM)",            eps_gr_ttm,    eps_3y,    eps_5y,    eps_10y,   EPS_T),
        row("EPS Growth (YoY)",            eps_gr_yoy,    eps_3y,    eps_5y,    eps_10y,   EPS_T),
        row("EPS Growth (Year)",           eps_gr_yr,     eps_3y,    eps_5y,    eps_10y,   EPS_T),
        row("EBIT Growth (TTM)",           ebit_gr_ttm,   ebit_3y,   ebit_5y,   ebit_10y,  EBIT_T),
        row("EBIT Growth (YoY)",           ebit_gr_yoy,   ebit_3y,   ebit_5y,   ebit_10y,  EBIT_T),
        row("EBIT Growth (Year)",          ebit_gr_yr,    ebit_3y,   ebit_5y,   ebit_10y,  EBIT_T),
        row("EBITDA Growth (TTM)",         ebitda_gr_ttm, ebitda_3y, ebitda_5y, ebitda_10y,EBITDA_T),
        row("EBITDA Growth (YoY)",         ebitda_gr_yoy, ebitda_3y, ebitda_5y, ebitda_10y,EBITDA_T),
        row("EBITDA Growth (Year)",        ebitda_gr_yr,  ebitda_3y, ebitda_5y, ebitda_10y,EBITDA_T),
        row("FCF Growth (TTM)",            fcf_gr_ttm_v,  fcf_3y,    fcf_5y,    fcf_10y,   FCF_T),
        row("FCF Growth (YoY)",            fcf_gr_yoy_v,  fcf_3y,    fcf_5y,    fcf_10y,   FCF_T),
        row("FCF Growth (Year)",           fcf_gr_yr,     fcf_3y,    fcf_5y,    fcf_10y,   FCF_T),
        row("Rule of 40 (TTM)",            ro40_ttm,      ro40_3y,   ro40_5y,   ro40_10y,  RO40_T),
        row("Rule of 40 (Year)",           ro40_yr,       ro40_3y,   ro40_5y,   ro40_10y,  RO40_T),
    ]

    # ── Overall Score ─────────────────────────────────────────────────
    grade_score = {"ap":100,"a":92,"am":84,"bp":76,"b":68,"bm":60,"cp":52,"c":44,"cm":36,"d":28,"na":0}
    scores = [grade_score.get(r["css"].replace("grade-",""), 0) for r in rows if r["css"] != "grade-na"]
    overall_score = sum(scores) / len(scores) if scores else 0
    overall_css, overall_lbl = get_grade(overall_score, [
        (96,"ap"),(92,"a"),(84,"am"),(76,"bp"),(68,"b"),(60,"bm"),(52,"cp"),(44,"c"),(36,"cm"),(0,"d")
    ])

    # ── Chart data: annual YoY growth rates as ratio ──────────────────
    chart_rows = []
    for i, y in enumerate(sorted(a_is.keys())):
        idx = sorted(a_is.keys(), reverse=True).index(y)
        ys  = sorted(a_is.keys(), reverse=True)
        if idx + 1 >= len(ys): continue
        y_prev = ys[idx + 1]
        def gr(stmt, key):
            v0 = fv(stmt.get(y, {}).get(key))
            v1 = fv(stmt.get(y_prev, {}).get(key))
            return (v0/v1 - 1) if v0 and v1 and v1 != 0 else None
        rev_g = gr(a_is, "totalRevenue")
        ni_g  = gr(a_is, "netIncome")
        ocf_g = gr(a_cf, "totalCashFromOperatingActivities")
        fc0   = fcf_yr(y); fc1 = fcf_yr(y_prev)
        fcf_g = (fc0/fc1 - 1) if fc0 and fc1 and fc1 != 0 else None
        if rev_g is not None:
            chart_rows.append({
                "Year": y[:4],
                "Rev Growth":  round(rev_g, 4),
                "Net Income":  round(ni_g,  4) if ni_g  is not None else None,
                "OCF":         round(ocf_g, 4) if ocf_g is not None else None,
                "FCF":         round(fcf_g, 4) if fcf_g is not None else None,
            })

    return {
        "rows":          rows,
        "overall_score": overall_score,
        "overall_css":   overall_css,
        "overall_lbl":   overall_lbl,
        "chart_data":    chart_rows,
    }


# ── Profitability Score ───────────────────────────────────────────────────────
def compute_profitability_score(data: dict, hl: dict, price_data: dict = None) -> dict:
    price_data = price_data or {}

    def fv(v):
        try: return float(v) if v not in (None, "", "NA", "None") else None
        except: return None

    a_is = data["Financials"]["Income_Statement"].get("yearly", {})
    a_cf = data["Financials"]["Cash_Flow"].get("yearly", {})
    a_bs = data["Financials"]["Balance_Sheet"].get("yearly", {})
    q_is = data["Financials"]["Income_Statement"].get("quarterly", {})
    q_cf = data["Financials"]["Cash_Flow"].get("quarterly", {})
    q_bs = data["Financials"]["Balance_Sheet"].get("quarterly", {})

    years_is = sorted(a_is.keys(), reverse=True)
    years_bs = sorted(a_bs.keys(), reverse=True)
    q_sorted = sorted(q_is.keys(), reverse=True)
    qcf_sorted = sorted(q_cf.keys(), reverse=True)
    qbs_sorted = sorted(q_bs.keys(), reverse=True)

    def yr_is(key, idx=0):
        if idx >= len(years_is): return None
        return fv(a_is[years_is[idx]].get(key))
    def yr_bs(key, idx=0):
        if idx >= len(years_bs): return None
        return fv(a_bs[years_bs[idx]].get(key))

    # ── TTM sums ─────────────────────────────────────────────────────
    def ttm_sum(statement, key):
        vals = []
        for q in sorted(statement.keys(), reverse=True)[:4]:
            v = fv(statement[q].get(key))
            if v is not None: vals.append(v)
        return sum(vals) if len(vals) == 4 else None

    ni_ttm     = ttm_sum(q_is, "netIncome")
    rev_ttm    = ttm_sum(q_is, "totalRevenue")
    gp_ttm     = ttm_sum(q_is, "grossProfit")
    oi_ttm     = ttm_sum(q_is, "operatingIncome")
    ebit_ttm   = ttm_sum(q_is, "ebit")
    ebitda_ttm = ttm_sum(q_is, "ebitda")
    cfo_ttm    = ttm_sum(q_cf, "totalCashFromOperatingActivities")
    capex_ttm  = ttm_sum(q_cf, "capitalExpenditures")
    fcf_ttm_raw= ttm_sum(q_cf, "freeCashFlow")
    fcf_ttm    = fcf_ttm_raw or (cfo_ttm - abs(capex_ttm) if cfo_ttm and capex_ttm else None)

    assets_ttm  = fv(q_bs[qbs_sorted[0]].get("totalAssets"))      if qbs_sorted else None
    equity_ttm  = fv(q_bs[qbs_sorted[0]].get("totalStockholderEquity")) if qbs_sorted else None
    cur_lia_ttm = fv(q_bs[qbs_sorted[0]].get("totalCurrentLiabilities")) if qbs_sorted else None
    ltd_ttm     = fv(q_bs[qbs_sorted[0]].get("longTermDebt"))     if qbs_sorted else None
    std_ttm     = fv(q_bs[qbs_sorted[0]].get("shortLongTermDebt")) if qbs_sorted else None
    debt_ttm    = (ltd_ttm or 0) + (std_ttm or 0)

    # ── Annual values ─────────────────────────────────────────────────
    ni_yr     = yr_is("netIncome")
    rev_yr    = yr_is("totalRevenue")
    gp_yr     = yr_is("grossProfit")
    oi_yr     = yr_is("operatingIncome")
    ebit_yr   = yr_is("ebit")
    ebitda_yr = yr_is("ebitda")
    fcf_yr_raw= fv(a_cf[years_is[0]].get("freeCashFlow")) if years_is and years_is[0] in a_cf else None
    cfo_yr    = fv(a_cf[years_is[0]].get("totalCashFromOperatingActivities")) if years_is and years_is[0] in a_cf else None
    capex_yr  = fv(a_cf[years_is[0]].get("capitalExpenditures")) if years_is and years_is[0] in a_cf else None
    fcf_yr    = fcf_yr_raw or (cfo_yr - abs(capex_yr) if cfo_yr and capex_yr else None)
    assets_yr = yr_bs("totalAssets")
    equity_yr = yr_bs("totalStockholderEquity")
    cur_lia_yr= yr_bs("totalCurrentLiabilities")
    ltd_yr    = yr_bs("longTermDebt")
    std_yr    = yr_bs("shortLongTermDebt")
    debt_yr   = (ltd_yr or 0) + (std_yr or 0)

    # avg equity / assets for ROE/ROA
    eq_prev     = yr_bs("totalStockholderEquity", 1)
    assets_prev = yr_bs("totalAssets", 1)
    eq_avg      = (equity_yr + eq_prev) / 2   if equity_yr and eq_prev else equity_yr
    assets_avg  = (assets_yr + assets_prev) / 2 if assets_yr and assets_prev else assets_yr

    # ── Current ratios ────────────────────────────────────────────────
    def safe_div(a, b): return a / b if a is not None and b and b != 0 else None
    def pct(v): return v * 100 if v is not None else None

    roa_ttm   = safe_div(ni_ttm,   assets_ttm)
    roa_yr    = safe_div(ni_yr,    assets_avg)
    roe_ttm   = safe_div(ni_ttm,   equity_ttm)
    roe_yr    = safe_div(ni_yr,    eq_avg)
    # Return on Capital = NI / (Equity + Debt)
    roc_ttm   = safe_div(ni_ttm,   (equity_ttm or 0) + debt_ttm)
    roc_yr    = safe_div(ni_yr,    (equity_yr  or 0) + debt_yr)
    # ROCE = EBIT / Capital Employed (Assets - Current Liabilities)
    cap_emp_ttm = (assets_ttm - cur_lia_ttm) if assets_ttm and cur_lia_ttm else None
    cap_emp_yr  = (assets_yr  - cur_lia_yr)  if assets_yr  and cur_lia_yr  else None
    roce_ttm  = safe_div(ebit_ttm, cap_emp_ttm)
    roce_yr   = safe_div(ebit_yr,  cap_emp_yr)
    # ROIC = EBIT*(1-tax_rate) / Invested Capital — simplified: NI / (Equity + Debt)
    roic_ttm  = safe_div(ni_ttm, (equity_ttm or 0) + debt_ttm)
    roic_yr   = safe_div(ni_yr,  (equity_yr  or 0) + debt_yr)

    gm_ttm    = safe_div(gp_ttm,     rev_ttm)
    gm_yr     = safe_div(gp_yr,      rev_yr)
    om_ttm    = safe_div(oi_ttm,     rev_ttm)
    om_yr     = safe_div(oi_yr,      rev_yr)
    nm_ttm    = safe_div(ni_ttm,     rev_ttm)
    nm_yr     = safe_div(ni_yr,      rev_yr)
    ebitm_ttm = safe_div(ebit_ttm,   rev_ttm)
    ebitm_yr  = safe_div(ebit_yr,    rev_yr)
    ebitdam_ttm = safe_div(ebitda_ttm, rev_ttm)
    ebitdam_yr  = safe_div(ebitda_yr,  rev_yr)
    fcfm_ttm  = safe_div(fcf_ttm,    rev_ttm)
    fcfm_yr   = safe_div(fcf_yr,     rev_yr)
    at_ttm    = safe_div(rev_ttm,    assets_ttm)
    at_yr     = safe_div(rev_yr,     assets_avg)

    # ── Historical averages ───────────────────────────────────────────
    def margin_hist(is_key_num, is_key_den, n, cf=False):
        ys = sorted(a_is.keys(), reverse=True)
        vals = []
        for y in ys[:n]:
            num = fv((a_cf if cf else a_is)[y].get(is_key_num)) if y in (a_cf if cf else a_is) else None
            den = fv(a_is[y].get(is_key_den))
            if num is not None and den and den != 0:
                vals.append(num / den)
        return sum(vals)/len(vals) if vals else None

    def return_hist(ni_key, asset_key, n, use_avg=False):
        ys = sorted(a_is.keys(), reverse=True)
        bsy= sorted(a_bs.keys(), reverse=True)
        vals = []
        for i, y in enumerate(ys[:n]):
            ni  = fv(a_is[y].get(ni_key))
            bs  = fv(a_bs[y].get(asset_key)) if y in a_bs else None
            if use_avg and i+1 < len(bsy):
                bs_p = fv(a_bs[bsy[i+1]].get(asset_key))
                bs = (bs + bs_p) / 2 if bs and bs_p else bs
            if ni is not None and bs and bs != 0:
                vals.append(ni / bs)
        return sum(vals)/len(vals) if vals else None

    def roce_hist(n):
        ys = sorted(a_is.keys(), reverse=True)
        vals = []
        for y in ys[:n]:
            e = fv(a_is[y].get("ebit"))
            bs = a_bs.get(y, {})
            ta = fv(bs.get("totalAssets"))
            cl = fv(bs.get("totalCurrentLiabilities"))
            if e is not None and ta and cl:
                vals.append(e / (ta - cl))
        return sum(vals)/len(vals) if vals else None

    def at_hist(n):
        ys = sorted(a_is.keys(), reverse=True)
        bsy= sorted(a_bs.keys(), reverse=True)
        vals = []
        for i, y in enumerate(ys[:n]):
            r = fv(a_is[y].get("totalRevenue"))
            a = fv(a_bs[y].get("totalAssets")) if y in a_bs else None
            a_p = fv(a_bs[bsy[i+1]].get("totalAssets")) if i+1 < len(bsy) else None
            a_avg = (a + a_p)/2 if a and a_p else a
            if r and a_avg and a_avg != 0: vals.append(r / a_avg)
        return sum(vals)/len(vals) if vals else None

    def fcfm_hist(n):
        ys = sorted(a_is.keys(), reverse=True)
        vals = []
        for y in ys[:n]:
            rev = fv(a_is[y].get("totalRevenue"))
            fcf = fv(a_cf[y].get("freeCashFlow")) if y in a_cf else None
            if not fcf and y in a_cf:
                c   = fv(a_cf[y].get("totalCashFromOperatingActivities"))
                cx  = fv(a_cf[y].get("capitalExpenditures"))
                fcf = c - abs(cx) if c and cx else None
            if fcf is not None and rev and rev != 0: vals.append(fcf / rev)
        return sum(vals)/len(vals) if vals else None

    def roc_hist(n):
        ys  = sorted(a_is.keys(), reverse=True)
        bsy = sorted(a_bs.keys(), reverse=True)
        vals = []
        for i, y in enumerate(ys[:n]):
            ni  = fv(a_is[y].get("netIncome"))
            bs  = a_bs.get(y, {})
            eq  = fv(bs.get("totalStockholderEquity"))
            ltd = fv(bs.get("longTermDebt")) or 0
            std = fv(bs.get("shortLongTermDebt")) or 0
            ic  = (eq or 0) + ltd + std
            if ni is not None and ic > 0:
                vals.append(ni / ic)
        return sum(vals)/len(vals) if vals else None

    roa_3y  = return_hist("netIncome","totalAssets",3,use_avg=True)
    roa_5y  = return_hist("netIncome","totalAssets",5,use_avg=True)
    roa_10y = return_hist("netIncome","totalAssets",10,use_avg=True)
    roe_3y  = return_hist("netIncome","totalStockholderEquity",3,use_avg=True)
    roe_5y  = return_hist("netIncome","totalStockholderEquity",5,use_avg=True)
    roe_10y = return_hist("netIncome","totalStockholderEquity",10,use_avg=True)
    roc_3y  = roc_hist(3);  roc_5y  = roc_hist(5);  roc_10y = roc_hist(10)
    roce_3y = roce_hist(3); roce_5y = roce_hist(5);  roce_10y = roce_hist(10)
    roic_3y = roc_hist(3);  roic_5y = roc_hist(5);  roic_10y = roc_hist(10)

    gm_3y   = margin_hist("grossProfit",  "totalRevenue",3)
    gm_5y   = margin_hist("grossProfit",  "totalRevenue",5)
    gm_10y  = margin_hist("grossProfit",  "totalRevenue",10)
    om_3y   = margin_hist("operatingIncome","totalRevenue",3)
    om_5y   = margin_hist("operatingIncome","totalRevenue",5)
    om_10y  = margin_hist("operatingIncome","totalRevenue",10)
    nm_3y   = margin_hist("netIncome",    "totalRevenue",3)
    nm_5y   = margin_hist("netIncome",    "totalRevenue",5)
    nm_10y  = margin_hist("netIncome",    "totalRevenue",10)
    ebitm_3y = margin_hist("ebit",        "totalRevenue",3)
    ebitm_5y = margin_hist("ebit",        "totalRevenue",5)
    ebitm_10y= margin_hist("ebit",        "totalRevenue",10)
    ebitdam_3y  = margin_hist("ebitda",   "totalRevenue",3)
    ebitdam_5y  = margin_hist("ebitda",   "totalRevenue",5)
    ebitdam_10y = margin_hist("ebitda",   "totalRevenue",10)
    fcfm_3y = fcfm_hist(3);  fcfm_5y = fcfm_hist(5);  fcfm_10y = fcfm_hist(10)
    at_3y   = at_hist(3);    at_5y   = at_hist(5);    at_10y   = at_hist(10)

    # ── Grade thresholds ─────────────────────────────────────────────
    ROA_T   = [(15,"ap"),(10,"a"),(7,"am"),(5,"bp"),(3,"b"),(1,"bm"),(0,"cp")]
    ROE_T   = [(25,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm")]
    ROC_T   = [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(4,"b"),(0,"bm")]
    ROCE_T  = [(25,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm")]
    ROIC_T  = [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(4,"b"),(0,"bm")]
    GM_T    = [(70,"ap"),(50,"a"),(40,"am"),(30,"bp"),(20,"b"),(10,"bm"),(0,"cp")]
    OM_T    = [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm")]
    NM_T    = [(25,"ap"),(15,"a"),(10,"am"),(7,"bp"),(3,"b"),(0,"bm")]
    EBITM_T = [(35,"ap"),(25,"a"),(20,"am"),(15,"bp"),(10,"b"),(5,"bm"),(0,"cp")]
    EBITDAM_T=[(40,"ap"),(30,"a"),(25,"am"),(20,"bp"),(15,"b"),(10,"bm"),(0,"cp")]
    FCFM_T  = [(25,"ap"),(15,"a"),(10,"am"),(7,"bp"),(3,"b"),(0,"bm")]
    AT_T    = [(2,"ap"),(1.5,"a"),(1,"am"),(0.7,"bp"),(0.4,"b"),(0.2,"bm"),(0,"cp")]

    def fmt(v, pct=False, decimals=2):
        if v is None: return "—"
        val = v * 100 if pct else v
        if pct: return f"{val:.{decimals}f} %"
        return f"{val:.{decimals}f}"

    def row(label, cur, avg3, avg5, avg10, T, pct=True):
        cur_pct = cur * 100 if cur is not None and pct else cur
        a3  = avg3  * 100 if avg3  is not None and pct else avg3
        a5  = avg5  * 100 if avg5  is not None and pct else avg5
        a10 = avg10 * 100 if avg10 is not None and pct else avg10
        css, lbl = get_grade(cur_pct if cur_pct is not None else cur, T) if cur is not None else ("grade-na","—")
        f = lambda v: (f"{v:.2f} %" if pct else f"{v:.2f}") if v is not None else "—"
        return {
            "label": label, "cur": cur_pct, "fmt": f(cur_pct if pct else cur),
            "css": css, "lbl": lbl,
            "avg3":  f(a3  if pct else avg3),
            "avg5":  f(a5  if pct else avg5),
            "avg10": f(a10 if pct else avg10),
            "group": label.split(" ")[0],
        }

    rows = [
        row("Return on Assets (TTM)",           roa_ttm,     roa_3y,     roa_5y,     roa_10y,     ROA_T),
        row("Return on Assets (Year)",           roa_yr,      roa_3y,     roa_5y,     roa_10y,     ROA_T),
        row("Return on Equity (TTM)",            roe_ttm,     roe_3y,     roe_5y,     roe_10y,     ROE_T),
        row("Return on Equity (Year)",           roe_yr,      roe_3y,     roe_5y,     roe_10y,     ROE_T),
        row("Return on Capital (TTM)",           roc_ttm,     roc_3y,     roc_5y,     roc_10y,     ROC_T),
        row("Return on Capital (Year)",          roc_yr,      roc_3y,     roc_5y,     roc_10y,     ROC_T),
        row("Return on Cap. Empl. (TTM)",        roce_ttm,    roce_3y,    roce_5y,    roce_10y,    ROCE_T),
        row("Return on Cap. Empl. (Year)",       roce_yr,     roce_3y,    roce_5y,    roce_10y,    ROCE_T),
        row("Return on Inv. Capital (TTM)",      roic_ttm,    roic_3y,    roic_5y,    roic_10y,    ROIC_T),
        row("Return on Inv. Capital (Year)",     roic_yr,     roic_3y,    roic_5y,    roic_10y,    ROIC_T),
        row("Gross Margin (TTM)",                gm_ttm,      gm_3y,      gm_5y,      gm_10y,      GM_T),
        row("Gross Margin (Year)",               gm_yr,       gm_3y,      gm_5y,      gm_10y,      GM_T),
        row("Operating Margin (TTM)",            om_ttm,      om_3y,      om_5y,      om_10y,      OM_T),
        row("Operating Margin (Year)",           om_yr,       om_3y,      om_5y,      om_10y,      OM_T),
        row("Net Margin (TTM)",                  nm_ttm,      nm_3y,      nm_5y,      nm_10y,      NM_T),
        row("Net Margin (Year)",                 nm_yr,       nm_3y,      nm_5y,      nm_10y,      NM_T),
        row("EBIT Margin (TTM)",                 ebitm_ttm,   ebitm_3y,   ebitm_5y,   ebitm_10y,   EBITM_T),
        row("EBIT Margin (Year)",                ebitm_yr,    ebitm_3y,   ebitm_5y,   ebitm_10y,   EBITM_T),
        row("EBITDA Margin (TTM)",               ebitdam_ttm, ebitdam_3y, ebitdam_5y, ebitdam_10y, EBITDAM_T),
        row("EBITDA Margin (Year)",              ebitdam_yr,  ebitdam_3y, ebitdam_5y, ebitdam_10y, EBITDAM_T),
        row("FCF Margin (TTM)",                  fcfm_ttm,    fcfm_3y,    fcfm_5y,    fcfm_10y,    FCFM_T),
        row("FCF Margin (Year)",                 fcfm_yr,     fcfm_3y,    fcfm_5y,    fcfm_10y,    FCFM_T),
        row("Asset Turnover (TTM)",              at_ttm,      at_3y,      at_5y,      at_10y,      AT_T, pct=False),
        row("Asset Turnover (Year)",             at_yr,       at_3y,      at_5y,      at_10y,      AT_T, pct=False),
    ]

    # ── Overall Score ─────────────────────────────────────────────────
    grade_score = {"ap":100,"a":92,"am":84,"bp":76,"b":68,"bm":60,"cp":52,"c":44,"cm":36,"d":28,"na":0}
    scores = [grade_score.get(r["css"].replace("grade-",""), 0) for r in rows if r["css"] != "grade-na"]
    overall_score = sum(scores) / len(scores) if scores else 0
    overall_css, overall_lbl = get_grade(overall_score, [
        (96,"ap"),(92,"a"),(84,"am"),(76,"bp"),(68,"b"),(60,"bm"),(52,"cp"),(44,"c"),(36,"cm"),(0,"d")
    ])

    # ── Chart data (annual margins) ───────────────────────────────────
    chart_rows = []
    for y in sorted(a_is.keys()):
        r  = fv(a_is[y].get("totalRevenue"))
        gp = fv(a_is[y].get("grossProfit"))
        ni = fv(a_is[y].get("netIncome"))
        cf = a_cf.get(y, {})
        fc = fv(cf.get("freeCashFlow"))
        if not fc:
            c  = fv(cf.get("totalCashFromOperatingActivities"))
            cx = fv(cf.get("capitalExpenditures"))
            fc = c - abs(cx) if c and cx else None
        if r and r > 0:
            chart_rows.append({
                "Year":         y[:4],
                "Gross Margin": round(gp/r*100, 2) if gp else None,
                "Net Margin":   round(ni/r*100, 2) if ni else None,
                "FCF Margin":   round(fc/r*100, 2) if fc else None,
            })

    return {
        "rows":          rows,
        "overall_score": overall_score,
        "overall_css":   overall_css,
        "overall_lbl":   overall_lbl,
        "chart_data":    chart_rows,
    }


# ── API ───────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fundamentals(ticker: str, api_token: str) -> dict:
    url = f"https://eodhd.com/api/fundamentals/{ticker}?api_token={api_token}&fmt=json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_prices(ticker: str, api_token: str) -> dict:
    """Fetch daily EOD prices and return a dict of {YYYY: year_end_close_price}."""
    url = f"https://eodhd.com/api/eod/{ticker}?api_token={api_token}&fmt=json&period=d"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    raw = r.json()
    # Build year → last available close price for that year
    year_prices = {}
    for entry in raw:
        year = entry["date"][:4]
        year_prices[year] = float(entry["adjusted_close"] or entry["close"])
    return year_prices  # keeps last entry per year (since sorted ascending)


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

        # Derived margins — same logic as TTM
        rev    = df.get("totalRevenue")
        gp     = df.get("grossProfit")
        oi     = df.get("operatingIncome")
        ni     = df.get("netIncome")
        ebitda = df.get("ebitda")
        cfo    = df.get("totalCashFromOperatingActivities")
        capex  = df.get("capitalExpenditures")
        fcf_raw = df.get("freeCashFlow")

        if rev is not None:
            if gp     is not None: df["grossMargin"]     = gp     / rev
            if oi     is not None: df["operatingMargin"] = oi     / rev
            if ni     is not None: df["netMargin"]       = ni     / rev
            if ebitda is not None: df["ebitdaMargin"]    = ebitda / rev
            # FCF: use direct field, fallback to CFO - abs(CapEx), fallback to CFO
            fcf_calc = fcf_raw
            if fcf_calc is None and cfo is not None and capex is not None:
                fcf_calc = cfo - capex.abs()
            elif fcf_calc is None and cfo is not None:
                fcf_calc = cfo
            if fcf_calc is not None:
                df["freeCashFlowCalc"] = fcf_calc
                df["fcfMargin"] = fcf_calc / rev

        return df
    except Exception:
        return pd.DataFrame()

# ── TTM Calculator ────────────────────────────────────────────────────────────
def calculate_ttm(data: dict, statement: str) -> pd.Series:
    """Current TTM (latest 4 quarters) as a Series — used for KPI cards."""
    df = calculate_ttm_history(data, statement)
    if df.empty:
        return pd.Series(dtype=float)
    latest = df.iloc[0].copy()
    latest["_quarters_used"] = 4
    latest["_latest_quarter"] = df.index[0]
    return latest


def calculate_ttm_history(data: dict, statement: str) -> pd.DataFrame:
    """
    Historical TTM: for every quarter Q, compute TTM(Q) = sum of Q + Q-1 + Q-2 + Q-3.
    Returns a DataFrame indexed by quarter-end date, columns = all financial fields + derived margins.
    Only quarters where all 4 trailing quarters are available are included.
    """
    SUM_FIELDS = {
        "totalRevenue", "costOfRevenue", "grossProfit",
        "researchDevelopment", "sellingGeneralAdministrative", "sellingAndMarketingExpenses",
        "totalOperatingExpenses", "operatingIncome", "ebit", "ebitda",
        "interestExpense", "interestIncome", "totalOtherIncomeExpenseNet",
        "incomeBeforeTax", "incomeTaxExpense", "netIncome",
        "netIncomeApplicableToCommonShares", "netIncomeFromContinuingOps",
        "depreciation", "depreciationAndAmortization",
        "totalCashFromOperatingActivities", "capitalExpenditures",
        "freeCashFlow", "dividendsPaid",
        "totalCashflowsFromInvestingActivities", "totalCashFromFinancingActivities",
        "stockBasedCompensation", "changeInWorkingCapital",
    }
    AVG_FIELDS = {
        # Shares — average over the 4-quarter window
        "commonStockSharesOutstanding",
    }
    LATEST_FIELDS = {
        "totalAssets", "totalCurrentAssets", "cash", "cashAndEquivalents",
        "cashAndShortTermInvestments", "shortTermInvestments",
        "netReceivables", "inventory", "otherCurrentAssets",
        "totalCurrentLiabilities", "shortLongTermDebt", "shortLongTermDebtTotal",
        "shortTermDebt", "longTermDebt", "longTermDebtTotal",
        "totalLiab", "totalStockholderEquity", "retainedEarnings",
        "commonStock", "goodWill", "intangibleAssets",
        "propertyPlantEquipment", "propertyPlantAndEquipmentNet",
        "otherAssets", "netDebt", "netWorkingCapital",
        "capitalLeaseObligations", "longTermInvestments",
    }
    try:
        quarterly = data["Financials"][statement].get("quarterly", {})
        if not quarterly or len(quarterly) < 4:
            return pd.DataFrame()

        # Load shares from Balance Sheet for epsCalc (only needed for Income Statement TTM)
        bs_quarterly = data["Financials"]["Balance_Sheet"].get("quarterly", {}) if statement == "Income_Statement" else {}

        # Sort all quarters descending
        sorted_q = sorted(quarterly.keys(), reverse=True)

        # Collect all numeric field names
        all_fields = set()
        for q in sorted_q:
            all_fields.update(quarterly[q].keys())
        all_fields -= {"date", "filing_date", "currency_symbol", "type", "period"}

        rows = []
        # For each quarter (starting from index 0), use that quarter + next 3 older ones
        for i in range(len(sorted_q) - 3):
            window = sorted_q[i:i+4]   # [newest, Q-1, Q-2, Q-3]
            latest = window[0]

            ttm_row = {"Date": latest}
            for field in all_fields:
                if field in SUM_FIELDS:
                    vals = []
                    for q in window:
                        try: vals.append(float(quarterly[q].get(field)))
                        except (TypeError, ValueError): pass
                    ttm_row[field] = sum(vals) if vals else None
                elif field in AVG_FIELDS:
                    vals = []
                    for q in window:
                        try: vals.append(float(quarterly[q].get(field)))
                        except (TypeError, ValueError): pass
                    ttm_row[field] = sum(vals) / len(vals) if vals else None
                elif field in LATEST_FIELDS:
                    try: ttm_row[field] = float(quarterly[latest].get(field))
                    except (TypeError, ValueError): ttm_row[field] = None
                else:
                    vals = []
                    for q in window:
                        try: vals.append(float(quarterly[q].get(field)))
                        except (TypeError, ValueError): pass
                    ttm_row[field] = sum(vals) if len(vals) == 4 else None

            # Derived margins
            rev    = ttm_row.get("totalRevenue")
            ni     = ttm_row.get("netIncome")
            gp     = ttm_row.get("grossProfit")
            oi     = ttm_row.get("operatingIncome")
            ebitda = ttm_row.get("ebitda")
            cfo    = ttm_row.get("totalCashFromOperatingActivities")
            capex  = ttm_row.get("capitalExpenditures")
            assets = ttm_row.get("totalAssets")
            equity = ttm_row.get("totalStockholderEquity")
            debt   = ttm_row.get("longTermDebt")

            ttm_row["grossMargin"]      = gp  / rev    if rev and gp     else None
            ttm_row["operatingMargin"]  = oi  / rev    if rev and oi     else None
            ttm_row["netMargin"]        = ni  / rev    if rev and ni     else None
            ttm_row["ebitdaMargin"]     = ebitda / rev if rev and ebitda else None
            ttm_row["roa"]              = ni / assets  if assets and ni  else None
            ttm_row["roe"]              = ni / equity  if equity and ni  else None
            fcf = ttm_row.get("freeCashFlow")
            if not fcf:
                if cfo is not None and capex is not None:
                    fcf = cfo - abs(capex)
                elif cfo is not None:
                    fcf = cfo
            ttm_row["freeCashFlowCalc"] = fcf
            ttm_row["fcfMargin"]        = fcf / rev    if rev and fcf    else None
            ttm_row["debtToEquity"]     = debt / equity if equity and debt else None

            # EPS calc: netIncomeApplicableToCommonShares / avg shares from BS
            ni_common = (ttm_row.get("netIncomeApplicableToCommonShares")
                         or ttm_row.get("netIncome"))
            # Average shares over the 4-quarter window from Balance Sheet
            share_vals = []
            for q in window:
                try:
                    s = bs_quarterly.get(q, {}).get("commonStockSharesOutstanding")
                    if s: share_vals.append(float(s))
                except: pass
            shares = sum(share_vals) / len(share_vals) if share_vals else None
            ttm_row["epsCalc"] = ni_common / shares if (ni_common and shares and shares != 0) else None

            rows.append(ttm_row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).set_index("Date")
        df = df.apply(pd.to_numeric, errors="coerce")
        return df

    except Exception:
        return pd.DataFrame()

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

def add_growth_rows(raw_df: pd.DataFrame, formatted_df: pd.DataFrame, period: str = "TTM") -> pd.DataFrame:
    """
    Interleaves two growth rows after each base row:
    - QoQ: current vs col+1 (always available except last column)
    - YoY: current vs col+4 for TTM/Quarterly, col+1 for Annual
           Shows — only when not enough history (last 4 cols for QoQ, last col for Annual)
    """
    result = {}
    cols = list(raw_df.columns)
    n = len(cols)

    def calc_growth(curr, prev):
        if curr is not None and prev is not None and prev != 0:
            pct = (curr / prev - 1) * 100
            return f"{'+'if pct>=0 else ''}{pct:.1f}%"
        return "—"

    for field in raw_df.index:
        result[field] = formatted_df.loc[field].tolist() if field in formatted_df.index else ["—"] * n

        vals = []
        for col in cols:
            try:
                vals.append(float(raw_df.loc[field, col]))
            except:
                vals.append(None)

        if period == "Annual":
            # Annual: only YoY → col vs col+1 (= 1 year back), always available except last
            yoy = []
            for i in range(n):
                yoy.append("—" if i == n-1 else calc_growth(vals[i], vals[i+1]))
            result[f"↳ {field} YoY"] = yoy

        else:
            # TTM / Quarterly:
            # QoQ → col vs col+1, always except last
            # YoY → col vs col+4 if available, fallback to col+1 (— only at very last col)
            qoq, yoy = [], []
            for i in range(n):
                qoq.append("—" if i >= n-1 else calc_growth(vals[i], vals[i+1]))
                if i+4 < n:
                    yoy.append(calc_growth(vals[i], vals[i+4]))   # same quarter last year
                elif i+1 < n:
                    yoy.append(calc_growth(vals[i], vals[i+1]))   # fallback: nearest available
                else:
                    yoy.append("—")                                # very last col, nothing to compare
            result[f"↳ {field} QoQ"] = qoq
            result[f"↳ {field} YoY"] = yoy

    return pd.DataFrame(result, index=cols).T

def compute_key_facts(hl, val, tech, kz):
    """
    Returns list of (label, value_str, sentiment) tuples.
    sentiment: 'pos' | 'neg' | 'neu'
    value_str: optional number shown next to badge, or None
    """
    facts = []

    def fv(v):
        try: return float(v)
        except: return None

    def get_kz_val(key):
        if key in kz: return kz[key][0]
        return None

    mcap        = fv(hl.get("MarketCapitalization"))
    ev          = fv(hl.get("EnterpriseValue"))
    revenue     = fv(hl.get("RevenueTTM"))
    gross_mar   = get_kz_val("gross_mar")
    op_mar      = get_kz_val("op_mar")
    net_mar     = get_kz_val("net_mar")
    roe         = get_kz_val("roe")
    roic        = get_kz_val("roic")
    roce        = get_kz_val("roce")
    de          = get_kz_val("de_ratio")
    da          = get_kz_val("da_ratio")
    fcf_yield   = get_kz_val("fcf_yield")
    fcf_mar     = get_kz_val("fcf_mar")
    cur_ratio   = get_kz_val("cur_ratio")
    quick_r     = get_kz_val("quick_r")
    rev_gr_yoy  = get_kz_val("rev_gr_yoy")
    rev_gr_ttm  = get_kz_val("rev_gr_ttm")
    earn_gr_yoy = get_kz_val("earn_gr_yoy")
    fcf_gr      = get_kz_val("fcf_gr")
    ebitda_mar  = get_kz_val("ebitda_mar")
    pe          = fv(hl.get("PERatio"))
    beta        = fv(tech.get("Beta"))
    div_yield   = fv(hl.get("DividendYield"))
    gp          = fv(hl.get("GrossProfitTTM"))
    fcf_abs     = get_kz_val("fcf_mar")

    currency = ""  # pulled from general if needed

    # ── Profitability ───────────────────────────────────────────────
    if gross_mar is not None:
        if gross_mar > 60:   facts.append(("Exceptional Gross Margin", f"{gross_mar:.1f}%", "pos"))
        elif gross_mar > 40: facts.append(("High Pricing Power", f"{gross_mar:.1f}%", "pos"))
        elif gross_mar > 20: facts.append(("Moderate Gross Margin", f"{gross_mar:.1f}%", "neu"))
        else:                facts.append(("Low Gross Margin", f"{gross_mar:.1f}%", "neg"))

    if net_mar is not None:
        if net_mar > 20:     facts.append(("Exceptional Profitability", f"{net_mar:.1f}%", "pos"))
        elif net_mar > 10:   facts.append(("High Profitability", f"{net_mar:.1f}%", "pos"))
        elif net_mar > 5:    facts.append(("Moderate Net Margin", f"{net_mar:.1f}%", "neu"))
        elif net_mar > 0:    facts.append(("Low Net Margin", f"{net_mar:.1f}%", "neu"))
        else:                facts.append(("Negative Net Margin", f"{net_mar:.1f}%", "neg"))

    if ebitda_mar is not None:
        if ebitda_mar > 30:  facts.append(("High Efficient Business", f"{ebitda_mar:.1f}%", "pos"))
        elif ebitda_mar > 15:facts.append(("Decent EBITDA Margin", f"{ebitda_mar:.1f}%", "pos"))

    # ── Returns ─────────────────────────────────────────────────────
    if roe is not None:
        if roe > 25:         facts.append(("Exceptional ROE", f"{roe:.1f}%", "pos"))
        elif roe > 15:       facts.append(("Strong ROE", f"{roe:.1f}%", "pos"))
        elif roe > 5:        facts.append(("Positive ROE", f"{roe:.1f}%", "pos"))
        else:                facts.append(("Weak ROE", f"{roe:.1f}%", "neg"))

    if roic is not None:
        if roic > 15:        facts.append(("Exceptional ROIC", f"{roic:.1f}%", "pos"))
        elif roic > 8:       facts.append(("Positive ROIC", f"{roic:.1f}%", "pos"))

    # ── Growth ──────────────────────────────────────────────────────
    if rev_gr_yoy is not None:
        if rev_gr_yoy > 25:  facts.append(("Exceptional Revenue Growth", f"{rev_gr_yoy:.1f}%", "pos"))
        elif rev_gr_yoy > 10:facts.append(("Strong Revenue Growth", f"{rev_gr_yoy:.1f}%", "pos"))
        elif rev_gr_yoy > 3: facts.append(("Positive Revenue Growth", f"{rev_gr_yoy:.1f}%", "pos"))
        elif rev_gr_yoy > -3:facts.append(("Flat Revenue Growth", f"{rev_gr_yoy:.1f}%", "neu"))
        else:                facts.append(("Declining Revenue", f"{rev_gr_yoy:.1f}%", "neg"))

    if earn_gr_yoy is not None:
        if earn_gr_yoy > 50: facts.append(("Exceptional Earnings Growth", f"{earn_gr_yoy:.1f}%", "pos"))
        elif earn_gr_yoy > 15:facts.append(("Strong Earnings Growth", f"{earn_gr_yoy:.1f}%", "pos"))
        elif earn_gr_yoy > 0:facts.append(("Positive Earnings Growth", f"{earn_gr_yoy:.1f}%", "pos"))
        else:                facts.append(("Declining Earnings", f"{earn_gr_yoy:.1f}%", "neg"))

    if fcf_gr is not None:
        if fcf_gr > 50:      facts.append(("Exceptional FCF Growth", f"{fcf_gr:.1f}%", "pos"))
        elif fcf_gr > 15:    facts.append(("Strong FCF Growth", f"{fcf_gr:.1f}%", "pos"))
        elif fcf_gr < 0:     facts.append(("Declining FCF", f"{fcf_gr:.1f}%", "neg"))

    # ── Cash Flow ───────────────────────────────────────────────────
    if fcf_mar is not None:
        if fcf_mar > 15:     facts.append(("Exceptional Free Cash Flow", f"{fcf_mar:.1f}%", "pos"))
        elif fcf_mar > 5:    facts.append(("Positive Free Cash Flow", f"{fcf_mar:.1f}%", "pos"))
        elif fcf_mar < 0:    facts.append(("Negative Free Cash Flow", f"{fcf_mar:.1f}%", "neg"))

    if fcf_yield is not None:
        if fcf_yield > 6:    facts.append(("High FCF Yield", f"{fcf_yield:.1f}%", "pos"))
        elif fcf_yield > 3:  facts.append(("Decent FCF Yield", f"{fcf_yield:.1f}%", "pos"))

    # ── Debt & Solvency ─────────────────────────────────────────────
    if de is not None:
        if de < 0.1:         facts.append(("Negligible Debt", None, "pos"))
        elif de < 0.5:       facts.append(("Low Level of Debt", f"{de:.2f}x D/E", "pos"))
        elif de < 1.0:       facts.append(("Moderate Debt", f"{de:.2f}x D/E", "neu"))
        elif de < 2.0:       facts.append(("Elevated Debt", f"{de:.2f}x D/E", "neg"))
        else:                facts.append(("High Debt Load", f"{de:.2f}x D/E", "neg"))

    if cur_ratio is not None:
        if cur_ratio > 2:    facts.append(("Strong Short-Term Solvency", f"{cur_ratio:.2f}x", "pos"))
        elif cur_ratio > 1:  facts.append(("Adequate Short-Term Solvency", f"{cur_ratio:.2f}x", "pos"))
        else:                facts.append(("Weak Short-Term Solvency", f"{cur_ratio:.2f}x", "neg"))

    # ── Valuation ───────────────────────────────────────────────────
    if pe is not None:
        if pe < 0:           facts.append(("Negative Earnings", None, "neg"))
        elif pe < 15:        facts.append(("Attractively Valued", f"P/E {pe:.1f}", "pos"))
        elif pe < 25:        facts.append(("Fairly Valued", f"P/E {pe:.1f}", "neu"))
        elif pe < 35:        facts.append(("Elevated Valuation", f"P/E {pe:.1f}", "neu"))
        else:                facts.append(("High Valuation", f"P/E {pe:.1f}", "neg"))

    # ── Dividend ────────────────────────────────────────────────────
    if div_yield is not None and div_yield > 0:
        if div_yield > 0.04: facts.append(("High Dividend Yield", f"{div_yield*100:.1f}%", "pos"))
        elif div_yield > 0.01:facts.append(("Dividend Paying", f"{div_yield*100:.1f}%", "pos"))
    else:
        facts.append(("No Dividend", None, "neu"))

    # ── Volatility ──────────────────────────────────────────────────
    if beta is not None:
        if beta < 0.8:       facts.append(("Low Volatility", f"β {beta:.2f}", "pos"))
        elif beta < 1.2:     facts.append(("Market-Like Volatility", f"β {beta:.2f}", "neu"))
        else:                facts.append(("High Volatility", f"β {beta:.2f}", "neg"))

    return facts


def render_key_facts(name, facts):
    sentiment_styles = {
        "pos": ("background:#1a3a2a; border:1px solid #2d6a4f; color:#48bb78;", "✅"),
        "neg": ("background:#3a1a1a; border:1px solid #6a2d2d; color:#fc8181;", "❌"),
        "neu": ("background:#2a2d3a; border:1px solid #4a4d6a; color:#a0aec0;", "⚪"),
    }
    badges = ""
    for label, value, sentiment in facts:
        style, icon = sentiment_styles.get(sentiment, sentiment_styles["neu"])
        val_html = f' <span style="font-weight:700;">{value}</span>' if value else ""
        badges += f'''<span style="{style} display:inline-flex; align-items:center; gap:5px;
            border-radius:6px; padding:5px 10px; margin:3px; font-size:12.5px; font-weight:500;">
            {icon} {label}{val_html}</span>'''

    return f'''
    <div style="background:#1e2535; border:1px solid #2d3748; border-radius:10px; padding:16px 20px; margin-bottom:16px;">
        <div style="color:#e2e8f0; font-size:17px; font-weight:800; margin-bottom:12px;">
            📋 {name}'s Key Facts
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:2px;">
            {badges}
        </div>
    </div>'''

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
    st.session_state.pop("price_data", None)

if "fund_data" not in st.session_state:
    with st.spinner(f"Lade Daten für **{ticker_input}** …"):
        try:
            result = fetch_fundamentals(ticker_input, api_token)
            st.session_state["fund_data"]   = result
            st.session_state["fund_ticker"] = ticker_input
        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")
            st.stop()

if "price_data" not in st.session_state:
    with st.spinner("Lade Preis-History …"):
        try:
            prices = fetch_prices(ticker_input, api_token)
            st.session_state["price_data"] = prices
        except Exception as e:
            st.warning(f"Preis-History nicht verfügbar: {e}")
            st.session_state["price_data"] = {}

data        = st.session_state["fund_data"]
price_data  = st.session_state.get("price_data", {})

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
tab1, tab2, tab2b, tab3, tab4, tab5 = st.tabs(["📈 Highlights", "💰 Financials", "🏆 Score", "📊 Earnings", "🔬 Valuation", "🌐 Info"])

# ═══════════════════════════════════════════════════════════════════
# TAB 1 · Highlights
# ═══════════════════════════════════════════════════════════════════
with tab1:
    # ── Key Facts ─────────────────────────────────────────────────────
    kz_for_facts = compute_kennzahlen(data, hl, val, tech)
    facts = compute_key_facts(hl, val, tech, kz_for_facts)
    company_name = g.get("Name", "Company")
    st.markdown(render_key_facts(company_name, facts), unsafe_allow_html=True)

    marktdaten = [
        ("Market Cap",       fmt_num(hl.get("MarketCapitalization"), prefix="$")),
        ("EV",               fmt_num(hl.get("EnterpriseValue"),       prefix="$")),
        ("52W High",         fmt_num(hl.get("52WeekHigh"),            prefix="$")),
        ("52W Low",          fmt_num(hl.get("52WeekLow"),             prefix="$")),
        ("Revenue TTM",      fmt_num(hl.get("RevenueTTM"),            prefix="$")),
        ("Gross Profit TTM", fmt_num(hl.get("GrossProfitTTM"),        prefix="$")),
        ("EPS",              fmt_num(hl.get("DilutedEpsTTM"),         prefix="$")),
        ("Dividend/Share",   fmt_num(hl.get("DividendShare"),         prefix="$")),
        ("Dividend Yield",   fmt_pct(hl.get("DividendYield"))),
        ("Beta",             fmt_num(tech.get("Beta"),                decimals=2)),
    ]

    st.markdown('<div class="section-header">Marktdaten</div>', unsafe_allow_html=True)
    for row_start in range(0, len(marktdaten), 5):
        row_items = marktdaten[row_start:row_start+5]
        row_cols = st.columns(5)
        for i, (label, value) in enumerate(row_items):
            with row_cols[i]:
                metric_card(label, value)

    st.markdown('<div class="section-header">Kennzahlen</div>', unsafe_allow_html=True)
    kz = kz_for_facts

    VALUE_ROWS = [
        ("P/Earnings (Fwd)",  "fwd_pe"),
        ("P/Earnings",        "pe"),
        ("P/FCF",             "p_fcf"),
        ("P/Sales",           "ps"),
        ("EV/Revenue",        "ev_rev"),
        ("EV/EBIT",           "ev_ebit"),
        ("EV/EBITDA",         "ev_ebitda"),
        ("Earnings Yield",    "earn_yield"),
        ("FCF Yield",         "fcf_yield"),
    ]
    PROFIT_ROWS = [
        ("Return on Equity",         "roe"),
        ("Return on Cap. Empl.",     "roce"),
        ("Return on Inv. Capital",   "roic"),
        ("Gross Margin",             "gross_mar"),
        ("Operating Margin",         "op_mar"),
        ("Net Margin",               "net_mar"),
        ("EBIT Margin",              "ebit_mar"),
        ("EBITDA Margin",            "ebitda_mar"),
        ("FCF Margin",               "fcf_mar"),
    ]
    GROWTH_ROWS = [
        ("Revenue Growth TTM",  "rev_gr_ttm"),
        ("Revenue Growth YoY",  "rev_gr_yoy"),
        ("Earnings Growth TTM", "earn_gr_ttm"),
        ("Earnings Growth YoY", "earn_gr_yoy"),
        ("EPS Growth TTM",      "eps_gr_ttm"),
        ("EPS Growth YoY",      "eps_gr_yoy"),
        ("EBIT Growth",         "ebit_gr_yoy"),
        ("EBITDA Growth",       "ebitda_gr_yoy"),
        ("FCF Growth",          "fcf_gr_yoy"),
    ]
    HEALTH_ROWS = [
        ("Cash Ratio",      "cash_r"),
        ("Current Ratio",   "cur_ratio"),
        ("Quick Ratio",     "quick_r"),
        ("Equity/Assets",   "ea_ratio"),
        ("Debt/Equity",     "de_ratio"),
        ("Debt/Assets",     "da_ratio"),
        ("FCF/Debt",        "fcf_debt"),
    ]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(render_kz_col("Value",       VALUE_ROWS,  kz), unsafe_allow_html=True)
    with c2:
        st.markdown(render_kz_col("Profitability", PROFIT_ROWS, kz), unsafe_allow_html=True)
    with c3:
        st.markdown(render_kz_col("Growth",      GROWTH_ROWS, kz), unsafe_allow_html=True)
    with c4:
        st.markdown(render_kz_col("Health",      HEALTH_ROWS, kz), unsafe_allow_html=True)

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

    # ── Charts Dashboard ───────────────────────────────────────────────
    st.markdown('<div class="section-header">Charts</div>', unsafe_allow_html=True)

    chart_period = st.radio("Zeitraum", ["Annual", "Quarterly", "TTM"], horizontal=True, key="chart_period_tab1")
    currency = g.get("CurrencyCode", "")
    st.caption(f"Währung: {currency} / Werte in Mio.")

    N = 20  # number of data points to show

    if chart_period == "TTM":
        df_is_chart = calculate_ttm_history(data, "Income_Statement").iloc[:N]
        df_cf_chart = calculate_ttm_history(data, "Cash_Flow").iloc[:N]
        df_bs_chart = calculate_ttm_history(data, "Balance_Sheet").iloc[:N]
    else:
        df_is_chart = parse_financials(data, "Income_Statement", chart_period).iloc[:N]
        df_cf_chart = parse_financials(data, "Cash_Flow",        chart_period).iloc[:N]
        df_bs_chart = parse_financials(data, "Balance_Sheet",    chart_period).iloc[:N]

    CHART_BG   = "#1e2535"
    CHART_GRID = "#2d3748"
    CHART_FONT = "#e2e8f0"
    COLORS = ["#4da6ff", "#48bb78", "#fc8181", "#f6ad55", "#b794f4", "#76e4f7"]

    def base_layout(title):
        return dict(
            title=dict(text=title, font=dict(color=CHART_FONT, size=13)),
            paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
            font=dict(color=CHART_FONT, size=11),
            height=280, margin=dict(l=10, r=10, t=40, b=30),
            xaxis=dict(gridcolor=CHART_GRID, showgrid=False),
            yaxis=dict(gridcolor=CHART_GRID),
            legend=dict(bgcolor=CHART_BG, borderwidth=0, orientation="h",
                        yanchor="bottom", y=1.02, xanchor="right", x=1),
            bargap=0.15,
        )

    def make_bar(df, col, color, name=None, div=1e6):
        if df.empty or col not in df.columns:
            return None
        s = df[col].dropna().iloc[:N]
        return go.Bar(
            x=s.index[::-1], y=(s / div)[::-1],
            name=name or col, marker_color=color,
            marker_line_width=0,
        )

    def make_chart(traces, title):
        fig = go.Figure()
        for t in traces:
            if t is not None:
                fig.add_trace(t)
        fig.update_layout(**base_layout(title))
        return fig

    row1_c1, row1_c2, row1_c3 = st.columns(3)
    row2_c1, row2_c2, row2_c3 = st.columns(3)

    with row1_c1:
        fig = make_chart(
            [make_bar(df_is_chart, "totalRevenue", COLORS[0], "Revenue")],
            f"Revenue ({currency} mln)"
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with row1_c2:
        fig = make_chart(
            [make_bar(df_is_chart, "netIncome", COLORS[1], "Net Income")],
            f"Net Income ({currency} mln)"
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with row1_c3:
        cfo_col = "totalCashFromOperatingActivities"
        fcf_col = "freeCashFlow"
        fig = make_chart([
            make_bar(df_cf_chart, cfo_col, COLORS[2], "Operating Cash Flow"),
            make_bar(df_cf_chart, fcf_col, COLORS[0], "Free Cash Flow"),
        ], f"Cash Flow ({currency} mln)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with row2_c1:
        # Shares outstanding — from general or highlights
        shares_val = hl.get("SharesOutstanding") or hl.get("SharesFloat")
        if not df_bs_chart.empty and "commonStock" in df_bs_chart.columns:
            fig = make_chart(
                [make_bar(df_bs_chart, "commonStock", COLORS[4], "Shares Outstanding", div=1e6)],
                "Shares Outstanding (mln)"
            )
        else:
            fig = go.Figure()
            fig.update_layout(**base_layout("Shares Outstanding (mln)"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with row2_c2:
        # Total cash = cash + shortTermInvestments, Total debt = shortLongTermDebt + longTermDebt
        if not df_bs_chart.empty:
            cash_s = df_bs_chart.get("cash", pd.Series(dtype=float))
            sti_s  = df_bs_chart.get("shortTermInvestments", pd.Series(dtype=float))
            ltd_s  = df_bs_chart.get("longTermDebt", pd.Series(dtype=float))
            std_s  = df_bs_chart.get("shortLongTermDebt", pd.Series(dtype=float))

            total_cash = cash_s.add(sti_s, fill_value=0)
            total_debt = ltd_s.add(std_s, fill_value=0)

            fig = go.Figure()
            tc = total_cash.dropna().iloc[:N]
            td = total_debt.reindex(tc.index)
            fig.add_trace(go.Bar(x=tc.index[::-1], y=(tc / 1e6)[::-1], name="Total Cash", marker_color=COLORS[1], marker_line_width=0))
            fig.add_trace(go.Bar(x=td.index[::-1], y=(td / 1e6)[::-1], name="Total Debt", marker_color="#fc8181", marker_line_width=0))
            fig.update_layout(**base_layout(f"Cash & Debt ({currency} mln)"))
            fig.update_layout(barmode="group")
        else:
            fig = go.Figure()
            fig.update_layout(**base_layout(f"Cash & Debt ({currency} mln)"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with row2_c3:
        fig = make_chart([
            make_bar(df_is_chart, "researchDevelopment",        COLORS[0], "R&D"),
            make_bar(df_is_chart, "sellingGeneralAdministrative", COLORS[5], "SG&A"),
        ], f"Operating Expenses ({currency} mln)")
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


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
        ttm_history = calculate_ttm_history(data, stmt_choice)

        if not ttm_series.empty:
            q_used = int(ttm_series.get("_quarters_used", 0))
            q_date = ttm_series.get("_latest_quarter", "—")
            st.markdown(
                f'<div class="section-header">TTM — Trailing Twelve Months '
                f'<span style="font-weight:400; color:#8892a4;">'
                f'(letztes: {q_date} · rolling 4 Quartale)</span></div>',
                unsafe_allow_html=True
            )

            # KPI cards — current TTM, 5 per row
            fields_to_show = TTM_FIELDS.get(stmt_choice, [])
            for row_start in range(0, len(fields_to_show), 5):
                row_fields = fields_to_show[row_start:row_start+5]
                ttm_cols = st.columns(5)
                for i, (lbl, field, fmt) in enumerate(row_fields):
                    raw_val = ttm_series.get(field)
                    if fmt == "$":
                        display = fmt_num(raw_val, prefix="$")
                    elif fmt == "%":
                        display = fmt_pct(raw_val)
                    else:
                        display = fmt_num(raw_val, suffix="x", decimals=2) if raw_val is not None else "—"
                    with ttm_cols[i]:
                        metric_card(lbl, display)

            st.markdown("---")

            # Historical TTM chart
            if not ttm_history.empty:
                chart_cols_map = {
                    "Income_Statement": ["totalRevenue", "grossProfit", "ebitda", "netIncome"],
                    "Balance_Sheet":    ["totalAssets", "totalLiab", "totalStockholderEquity", "cash"],
                    "Cash_Flow":        ["totalCashFromOperatingActivities", "capitalExpenditures", "freeCashFlowCalc", "dividendsPaid"],
                }
                chart_cols = [c for c in chart_cols_map.get(stmt_choice, []) if c in ttm_history.columns]
                if chart_cols:
                    st.markdown('<div class="section-header">Historical TTM — Chart</div>', unsafe_allow_html=True)
                    st.plotly_chart(
                        plot_financials(ttm_history, chart_cols, f"{stmt_choice.replace('_',' ')} (TTM)"),
                        use_container_width=True
                    )

                # Historical TTM raw table
                st.markdown('<div class="section-header">Historical TTM — Rohdaten</div>', unsafe_allow_html=True)
                show_growth_ttm = st.toggle("Growth anzeigen", key="growth_ttm")
                raw_df = ttm_history.T.copy()
                display_df = raw_df.applymap(lambda x: fmt_num(x) if pd.notna(x) else "—")
                if show_growth_ttm:
                    display_df = add_growth_rows(raw_df, display_df, period="TTM")
                st.dataframe(display_df, use_container_width=True)

        else:
            st.info("Keine Quartalsdaten für TTM-Berechnung verfügbar (mind. 4 Quartale benötigt).")

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
            show_growth = st.toggle("Growth anzeigen", key="growth_hist")
            raw_df = df_fin.T.copy()
            display_df = raw_df.applymap(lambda x: fmt_num(x) if pd.notna(x) else "—")
            if show_growth:
                display_df = add_growth_rows(raw_df, display_df, period=period_type)
            st.dataframe(display_df, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 2b · Score
# ═══════════════════════════════════════════════════════════════════
with tab2b:
    score_tabs = st.tabs(["💎 Value", "📈 Profitability", "🚀 Growth", "🏥 Health", "⭐ Quality", "🔍 All"])

    with score_tabs[0]:  # Value
        vs = compute_value_score(data, hl, val, price_data)
        rows_all = vs["rows"]

        # ── Header ────────────────────────────────────────────────────
        col_hdr, col_filter = st.columns([3, 1])
        with col_hdr:
            st.markdown(
                f'<div style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:8px;">'
                f'Value <span style="color:#94a3b8;">{vs["overall_score"]:.1f}</span>'
                f' &nbsp;{grade_badge(vs["overall_css"], vs["overall_lbl"])}</div>',
                unsafe_allow_html=True
            )
        with col_filter:
            groups = ["All Values"] + sorted(set(r["label"].split(" ")[0] for r in rows_all))
            filter_sel = st.selectbox("", groups, key="value_score_filter", label_visibility="collapsed")

        rows_show = rows_all if filter_sel == "All Values" else [r for r in rows_all if r["label"].startswith(filter_sel)]

        # ── Table + Chart ─────────────────────────────────────────────
        col_table, col_chart = st.columns([1, 1])

        with col_table:
            # Table header
            hdr_html = '''
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
              <thead>
                <tr style="color:#64748b;border-bottom:1px solid #2d3748;">
                  <th style="text-align:left;padding:6px 4px;font-weight:500;">Ratio</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">Value</th>
                  <th style="text-align:center;padding:6px 4px;font-weight:500;">Grade</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">3Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">5Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">10Y Avg.</th>
                </tr>
              </thead><tbody>'''

            for r in rows_show:
                hdr_html += f'''
                <tr style="border-bottom:1px solid #1e2535;">
                  <td style="padding:6px 4px;color:#cbd5e1;">{r["label"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#e2e8f0;font-weight:600;">{r["fmt"]}</td>
                  <td style="padding:6px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg3"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg5"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg10"]}</td>
                </tr>'''

            hdr_html += "</tbody></table>"
            st.markdown(hdr_html, unsafe_allow_html=True)

        with col_chart:
            chart_df = pd.DataFrame(vs["chart_data"])
            if not chart_df.empty:
                fig_vs = go.Figure()
                colors_fill = {
                    "Revenue":    ("#3b82f6", "rgba(59,130,246,0.12)"),
                    "Net Income": ("#22c55e", "rgba(34,197,94,0.12)"),
                    "FCF":        ("#ec4899", "rgba(236,72,153,0.12)"),
                }
                for col_name, (line_col, fill_col) in colors_fill.items():
                    if col_name in chart_df.columns:
                        fig_vs.add_trace(go.Scatter(
                            x=chart_df["Year"], y=chart_df[col_name],
                            name=col_name, mode="lines",
                            line=dict(color=line_col, width=2),
                            fill="tozeroy", fillcolor=fill_col,
                        ))
                fig_vs.update_layout(
                    title=dict(text="Revenue | Net Income | Free Cash Flow", font=dict(color="#e2e8f0", size=13)),
                    paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                    font=dict(color="#94a3b8", size=11),
                    legend=dict(orientation="h", y=-0.15, bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=40, b=30),
                    xaxis=dict(gridcolor="#1e2535", showgrid=False),
                    yaxis=dict(gridcolor="#1e2535", tickformat=","),
                    height=420,
                )
                st.plotly_chart(fig_vs, use_container_width=True)

    with score_tabs[1]:  # Profitability
        ps = compute_profitability_score(data, hl, price_data)
        rows_all = ps["rows"]

        col_hdr, col_filter = st.columns([3, 1])
        with col_hdr:
            st.markdown(
                f'<div style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:8px;">'
                f'Profit <span style="color:#94a3b8;">{ps["overall_score"]:.2f}</span>'
                f' &nbsp;{grade_badge(ps["overall_css"], ps["overall_lbl"])}</div>',
                unsafe_allow_html=True
            )
        with col_filter:
            groups = ["All Values"] + sorted(set(r["label"].split(" ")[0] for r in rows_all))
            filter_sel = st.selectbox("", groups, key="profit_score_filter", label_visibility="collapsed")

        rows_show = rows_all if filter_sel == "All Values" else [r for r in rows_all if r["label"].startswith(filter_sel)]

        col_table, col_chart = st.columns([1, 1])

        with col_table:
            tbl = '''
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
              <thead>
                <tr style="color:#64748b;border-bottom:1px solid #2d3748;">
                  <th style="text-align:left;padding:6px 4px;font-weight:500;">Ratio</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">Value</th>
                  <th style="text-align:center;padding:6px 4px;font-weight:500;">Grade</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">3Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">5Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">10Y Avg.</th>
                </tr>
              </thead><tbody>'''
            for r in rows_show:
                tbl += f'''
                <tr style="border-bottom:1px solid #1e2535;">
                  <td style="padding:6px 4px;color:#cbd5e1;">{r["label"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#e2e8f0;font-weight:600;">{r["fmt"]}</td>
                  <td style="padding:6px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg3"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg5"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg10"]}</td>
                </tr>'''
            tbl += "</tbody></table>"
            st.markdown(tbl, unsafe_allow_html=True)

        with col_chart:
            chart_df = pd.DataFrame(ps["chart_data"])
            if not chart_df.empty:
                fig_p = go.Figure()
                margin_colors = {
                    "Gross Margin": ("#3b82f6", "rgba(59,130,246,0.12)"),
                    "Net Margin":   ("#22c55e", "rgba(34,197,94,0.12)"),
                    "FCF Margin":   ("#ec4899", "rgba(236,72,153,0.12)"),
                }
                for col_name, (line_col, fill_col) in margin_colors.items():
                    if col_name in chart_df.columns:
                        fig_p.add_trace(go.Scatter(
                            x=chart_df["Year"], y=chart_df[col_name],
                            name=col_name, mode="lines",
                            line=dict(color=line_col, width=2),
                            fill="tozeroy", fillcolor=fill_col,
                        ))
                fig_p.update_layout(
                    title=dict(text="Margins", font=dict(color="#e2e8f0", size=13)),
                    paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                    font=dict(color="#94a3b8", size=11),
                    legend=dict(orientation="h", y=-0.15, bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=40, b=30),
                    xaxis=dict(gridcolor="#1e2535", showgrid=False),
                    yaxis=dict(gridcolor="#1e2535", ticksuffix="%"),
                    height=420,
                )
                st.plotly_chart(fig_p, use_container_width=True)

    with score_tabs[2]:  # Growth
        gs = compute_growth_score(data, hl)
        rows_all = gs["rows"]

        col_hdr, col_filter = st.columns([3, 1])
        with col_hdr:
            st.markdown(
                f'<div style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:8px;">'
                f'Growth <span style="color:#94a3b8;">{gs["overall_score"]:.2f}</span>'
                f' &nbsp;{grade_badge(gs["overall_css"], gs["overall_lbl"])}</div>',
                unsafe_allow_html=True
            )
        with col_filter:
            groups = ["All Values"] + sorted(set(r["label"].split(" ")[0] for r in rows_all))
            filter_sel = st.selectbox("", groups, key="growth_score_filter", label_visibility="collapsed")

        rows_show = rows_all if filter_sel == "All Values" else [r for r in rows_all if r["label"].startswith(filter_sel)]

        col_table, col_chart = st.columns([1, 1])

        with col_table:
            tbl = '''
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
              <thead>
                <tr style="color:#64748b;border-bottom:1px solid #2d3748;">
                  <th style="text-align:left;padding:6px 4px;font-weight:500;">Ratio</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">Value</th>
                  <th style="text-align:center;padding:6px 4px;font-weight:500;">Grade</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">3Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">5Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">10Y Avg.</th>
                </tr>
              </thead><tbody>'''
            for r in rows_show:
                tbl += f'''
                <tr style="border-bottom:1px solid #1e2535;">
                  <td style="padding:6px 4px;color:#cbd5e1;">{r["label"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#e2e8f0;font-weight:600;">{r["fmt"]}</td>
                  <td style="padding:6px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg3"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg5"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg10"]}</td>
                </tr>'''
            tbl += "</tbody></table>"
            st.markdown(tbl, unsafe_allow_html=True)

        with col_chart:
            chart_df = pd.DataFrame(gs["chart_data"])
            if not chart_df.empty:
                fig_g = go.Figure()
                growth_colors = {
                    "Rev Growth": ("#3b82f6", "rgba(59,130,246,0.08)"),
                    "Net Income": ("#22c55e", "rgba(34,197,94,0.08)"),
                    "OCF":        ("#f59e0b", "rgba(245,158,11,0.08)"),
                    "FCF":        ("#ec4899", "rgba(236,72,153,0.08)"),
                }
                for col_name, (line_col, fill_col) in growth_colors.items():
                    if col_name in chart_df.columns:
                        fig_g.add_trace(go.Scatter(
                            x=chart_df["Year"], y=chart_df[col_name],
                            name=col_name, mode="lines",
                            line=dict(color=line_col, width=2),
                        ))
                fig_g.add_hline(y=0, line_dash="dot", line_color="#475569", line_width=1)
                fig_g.update_layout(
                    title=dict(text="Growth of: Revenue | Net Income | OCF | FCF", font=dict(color="#e2e8f0", size=13)),
                    paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                    font=dict(color="#94a3b8", size=11),
                    legend=dict(orientation="h", y=-0.15, bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=40, b=30),
                    xaxis=dict(gridcolor="#1e2535", showgrid=False),
                    yaxis=dict(gridcolor="#1e2535", tickformat=".0%"),
                    height=420,
                )
                st.plotly_chart(fig_g, use_container_width=True)

    with score_tabs[3]:  # Health
        hs = compute_health_score(data, hl, price_data)
        rows_all = hs["rows"]

        col_hdr, col_filter = st.columns([3, 1])
        with col_hdr:
            st.markdown(
                f'<div style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:8px;">'
                f'Health <span style="color:#94a3b8;">{hs["overall_score"]:.2f}</span>'
                f' &nbsp;{grade_badge(hs["overall_css"], hs["overall_lbl"])}</div>',
                unsafe_allow_html=True
            )
        with col_filter:
            groups = ["All Values"] + sorted(set(r["label"].split(" ")[0].split("/")[0] for r in rows_all))
            filter_sel = st.selectbox("", groups, key="health_score_filter", label_visibility="collapsed")

        rows_show = rows_all if filter_sel == "All Values" else [r for r in rows_all if r["label"].split(" ")[0].split("/")[0] == filter_sel]

        col_table, col_chart = st.columns([1, 1])

        with col_table:
            tbl = '''
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
              <thead>
                <tr style="color:#64748b;border-bottom:1px solid #2d3748;">
                  <th style="text-align:left;padding:6px 4px;font-weight:500;">Ratio</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">Value</th>
                  <th style="text-align:center;padding:6px 4px;font-weight:500;">Grade</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">3Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">5Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">10Y Avg.</th>
                </tr>
              </thead><tbody>'''
            for r in rows_show:
                tbl += f'''
                <tr style="border-bottom:1px solid #1e2535;">
                  <td style="padding:6px 4px;color:#cbd5e1;">{r["label"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#e2e8f0;font-weight:600;">{r["fmt"]}</td>
                  <td style="padding:6px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg3"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg5"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg10"]}</td>
                </tr>'''
            tbl += "</tbody></table>"
            st.markdown(tbl, unsafe_allow_html=True)

        with col_chart:
            chart_df = pd.DataFrame(hs["chart_data"])
            if not chart_df.empty:
                fig_h = go.Figure()
                bs_colors = {
                    "Total Stockholder Equity":  ("#3b82f6", "rgba(59,130,246,0.35)"),
                    "Total Current Liabilities": ("#22c55e", "rgba(34,197,94,0.35)"),
                    "Non-current Liabilities":   ("#ec4899", "rgba(236,72,153,0.35)"),
                }
                for col_name, (line_col, fill_col) in bs_colors.items():
                    if col_name in chart_df.columns:
                        fig_h.add_trace(go.Scatter(
                            x=chart_df["Year"], y=chart_df[col_name],
                            name=col_name, mode="lines",
                            line=dict(color=line_col, width=2),
                            fill="tozeroy", fillcolor=fill_col,
                            stackgroup="one",
                        ))
                fig_h.update_layout(
                    title=dict(text="Financial Breakdown", font=dict(color="#e2e8f0", size=13)),
                    paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                    font=dict(color="#94a3b8", size=11),
                    legend=dict(orientation="h", y=-0.18, bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=40, b=40),
                    xaxis=dict(gridcolor="#1e2535", showgrid=False),
                    yaxis=dict(gridcolor="#1e2535", ticksuffix="M"),
                    height=420,
                )
                st.plotly_chart(fig_h, use_container_width=True)

    with score_tabs[4]:  # Quality
        qs = compute_quality_score(data, hl, price_data)
        rows_all = qs["rows"]

        col_hdr, col_filter = st.columns([3, 1])
        with col_hdr:
            st.markdown(
                f'<div style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:8px;">'
                f'Quality <span style="color:#94a3b8;">{qs["overall_score"]:.2f}</span>'
                f' &nbsp;{grade_badge(qs["overall_css"], qs["overall_lbl"])}</div>',
                unsafe_allow_html=True
            )
        with col_filter:
            groups = ["All Values"] + sorted(set(r["label"].split(" ")[0] for r in rows_all))
            filter_sel = st.selectbox("", groups, key="quality_score_filter", label_visibility="collapsed")

        rows_show = rows_all if filter_sel == "All Values" else [r for r in rows_all if r["label"].startswith(filter_sel)]

        col_table, col_charts = st.columns([1, 1])

        with col_table:
            tbl = '''
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
              <thead>
                <tr style="color:#64748b;border-bottom:1px solid #2d3748;">
                  <th style="text-align:left;padding:6px 4px;font-weight:500;">Ratio</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">Value</th>
                  <th style="text-align:center;padding:6px 4px;font-weight:500;">Grade</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">3Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">5Y Avg.</th>
                  <th style="text-align:right;padding:6px 4px;font-weight:500;">10Y Avg.</th>
                </tr>
              </thead><tbody>'''
            for r in rows_show:
                tbl += f'''
                <tr style="border-bottom:1px solid #1e2535;">
                  <td style="padding:6px 4px;color:#cbd5e1;">{r["label"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#e2e8f0;font-weight:600;">{r["fmt"]}</td>
                  <td style="padding:6px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg3"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r["avg5"]}</td>
                  <td style="padding:6px 4px;text-align:right;color:#94a3b8;">{r.get("avg10","—")}</td>
                </tr>'''
            tbl += "</tbody></table>"
            st.markdown(tbl, unsafe_allow_html=True)

        with col_charts:
            # Chart 1: ROIC | Gross Margin | FCF Margin
            df1 = pd.DataFrame(qs["chart1"])
            if not df1.empty:
                fig_q1 = go.Figure()
                q1_colors = {
                    "ROIC":         ("#3b82f6", "rgba(59,130,246,0.25)"),
                    "Gross Margin": ("#22c55e", "rgba(34,197,94,0.25)"),
                    "FCF Margin":   ("#ec4899", "rgba(236,72,153,0.25)"),
                }
                for col_name, (lc, fc) in q1_colors.items():
                    if col_name in df1.columns:
                        fig_q1.add_trace(go.Scatter(
                            x=df1["Year"], y=df1[col_name],
                            name=col_name, mode="lines",
                            line=dict(color=lc, width=2),
                            fill="tozeroy", fillcolor=fc,
                        ))
                fig_q1.update_layout(
                    title=dict(text="ROIC | Gross Margin | FCF Margin", font=dict(color="#e2e8f0", size=13)),
                    paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                    font=dict(color="#94a3b8", size=11),
                    legend=dict(orientation="h", y=-0.18, bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=40, b=40),
                    xaxis=dict(gridcolor="#1e2535", showgrid=False),
                    yaxis=dict(gridcolor="#1e2535", ticksuffix="%"),
                    height=320,
                )
                st.plotly_chart(fig_q1, use_container_width=True)

            # Chart 2: Debt/Equity & Cash Ratio
            df2 = pd.DataFrame(qs["chart2"])
            if not df2.empty:
                fig_q2 = go.Figure()
                q2_colors = {
                    "Debt Equity": ("#3b82f6", "rgba(59,130,246,0.15)"),
                    "Cash Ratio":  ("#22c55e", "rgba(34,197,94,0.15)"),
                }
                for col_name, (lc, fc) in q2_colors.items():
                    if col_name in df2.columns:
                        fig_q2.add_trace(go.Scatter(
                            x=df2["Year"], y=df2[col_name],
                            name=col_name, mode="lines",
                            line=dict(color=lc, width=2),
                        ))
                fig_q2.update_layout(
                    title=dict(text="Debt/Equity & Cash Ratio", font=dict(color="#e2e8f0", size=13)),
                    paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                    font=dict(color="#94a3b8", size=11),
                    legend=dict(orientation="h", y=-0.18, bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=40, b=40),
                    xaxis=dict(gridcolor="#1e2535", showgrid=False),
                    yaxis=dict(gridcolor="#1e2535"),
                    height=320,
                )
                st.plotly_chart(fig_q2, use_container_width=True)

    with score_tabs[5]:  # All
        # ── Collect all rows ──────────────────────────────────────────
        vs = compute_value_score(data, hl, val, price_data)
        ps = compute_profitability_score(data, hl, price_data)
        gs = compute_growth_score(data, hl)
        hs = compute_health_score(data, hl, price_data)

        all_rows = []
        for tag, sub_rows in [("💎 Value", vs["rows"]), ("📈 Profit", ps["rows"]),
                               ("🚀 Growth", gs["rows"]), ("🏥 Health",  hs["rows"])]:
            for r in sub_rows:
                all_rows.append({**r, "tab": tag})

        # ── Score header ──────────────────────────────────────────────
        avg_all = sum([vs["overall_score"], ps["overall_score"],
                       gs["overall_score"], hs["overall_score"]]) / 4
        overall_all_css, overall_all_lbl = get_grade(avg_all, [
            (96,"ap"),(92,"a"),(84,"am"),(76,"bp"),(68,"b"),(60,"bm"),
            (52,"cp"),(44,"c"),(36,"cm"),(0,"d")
        ])

        hcol1, hcol2, hcol3, hcol4, hcol5 = st.columns([3, 1, 1, 1, 1])
        with hcol1:
            st.markdown(
                f'<div style="font-size:20px;font-weight:700;color:#e2e8f0;">'
                f'All Metrics &nbsp;{grade_badge(overall_all_css, overall_all_lbl)}'
                f' <span style="font-size:14px;color:#64748b;font-weight:400;">'
                f'Avg {avg_all:.1f}</span></div>', unsafe_allow_html=True)
        for col, key, sc in zip([hcol2, hcol3, hcol4, hcol5],
                                 ["💎 Value","📈 Profit","🚀 Growth","🏥 Health"],
                                 [vs, ps, gs, hs]):
            with col:
                st.markdown(
                    f'<div style="font-size:12px;color:#64748b;">{key}</div>'
                    f'<div style="font-size:15px;font-weight:600;color:#e2e8f0;">'
                    f'{sc["overall_score"]:.1f} {grade_badge(sc["overall_css"], sc["overall_lbl"])}</div>',
                    unsafe_allow_html=True)

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # ── Filters ───────────────────────────────────────────────────
        fcol1, fcol2, fcol3 = st.columns([2, 2, 2])
        with fcol1:
            tab_filter = st.selectbox("Kategorie", ["All","💎 Value","📈 Profit","🚀 Growth","🏥 Health"],
                                      key="all_tab_filter", label_visibility="collapsed")
        with fcol2:
            grade_filter = st.selectbox("Grade", ["All Grades","A+","A","A-","B+","B","B-","C+","C","C-","D"],
                                        key="all_grade_filter", label_visibility="collapsed")
        with fcol3:
            search_filter = st.text_input("", placeholder="🔍  Suche: Margin, Debt, FCF …",
                                          key="all_search_filter", label_visibility="collapsed")

        rows_filtered = all_rows
        if tab_filter != "All":
            rows_filtered = [r for r in rows_filtered if r["tab"] == tab_filter]
        if grade_filter != "All Grades":
            css_map = {"A+":"grade-ap","A":"grade-a","A-":"grade-am","B+":"grade-bp",
                       "B":"grade-b","B-":"grade-bm","C+":"grade-cp","C":"grade-c",
                       "C-":"grade-cm","D":"grade-d"}
            rows_filtered = [r for r in rows_filtered if r["css"] == css_map.get(grade_filter,"")]
        if search_filter:
            rows_filtered = [r for r in rows_filtered if search_filter.lower() in r["label"].lower()]

        # ── Build DataFrame for st.dataframe with row selection ───────
        df_all = pd.DataFrame([{
            "Metric":  r["label"],
            "Cat.":    r["tab"],
            "Value":   r["fmt"],
            "Grade":   r["lbl"],
            "3Y Avg":  r["avg3"],
            "5Y Avg":  r["avg5"],
            "10Y Avg": r.get("avg10", "—"),
        } for r in rows_filtered])

        col_tbl, col_drill = st.columns([3, 2])

        with col_tbl:
            label_list = [r["label"] for r in rows_filtered]

            # Selectbox at the top for drill-down selection
            if label_list:
                if "all_selected_metric" not in st.session_state or \
                   st.session_state.get("all_selected_metric") not in label_list:
                    st.session_state["all_selected_metric"] = label_list[0]
                default_idx = label_list.index(st.session_state["all_selected_metric"])
                selected_metric = st.selectbox(
                    "🔍 Metric auswählen für Drill-Down:",
                    label_list, index=default_idx,
                    key="all_metric_selectbox"
                )
                st.session_state["all_selected_metric"] = selected_metric

            if not df_all.empty:
                sel_event = st.dataframe(
                    df_all,
                    use_container_width=True,
                    hide_index=True,
                    height=600,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="all_df_selection",
                    column_config={
                        "Metric":  st.column_config.TextColumn("Metric",  width="large"),
                        "Cat.":    st.column_config.TextColumn("Cat.",    width="small"),
                        "Value":   st.column_config.TextColumn("Value",   width="small"),
                        "Grade":   st.column_config.TextColumn("Grade",   width="small"),
                        "3Y Avg":  st.column_config.TextColumn("3Y Avg",  width="small"),
                        "5Y Avg":  st.column_config.TextColumn("5Y Avg",  width="small"),
                        "10Y Avg": st.column_config.TextColumn("10Y Avg", width="small"),
                    },
                )
                # Resolve selected row
                sel_rows = sel_event.selection.rows if sel_event and sel_event.selection else []
                if sel_rows:
                    st.session_state["all_selected_metric"] = rows_filtered[sel_rows[0]]["label"]
                elif "all_selected_metric" not in st.session_state and rows_filtered:
                    st.session_state["all_selected_metric"] = rows_filtered[0]["label"]

        with col_drill:
            sel = st.session_state.get("all_selected_metric")
            # Keep sel valid when filters change
            valid_labels = [r["label"] for r in rows_filtered]
            if sel not in valid_labels and valid_labels:
                sel = valid_labels[0]
                st.session_state["all_selected_metric"] = sel

            if sel:
                row_data = next((r for r in all_rows if r["label"] == sel), None)
                dd = compute_drilldown(sel, data, hl, val, price_data)

                # ── Drill-down card ───────────────────────────────────
                card = (
                    f'<div style="background:#131b2e;border:1px solid #1e3a5f;'
                    f'border-radius:10px;padding:20px;">'
                    f'<div style="font-size:16px;font-weight:700;color:#e2e8f0;'
                    f'margin-bottom:2px;">{sel}</div>'
                    f'<div style="font-size:12px;color:#64748b;margin-bottom:14px;">'
                    f'{row_data["tab"] if row_data else ""}</div>'
                )
                # Value + grade
                if row_data:
                    card += (
                        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">'
                        f'<span style="font-size:26px;font-weight:700;color:#60a5fa;">'
                        f'{row_data["fmt"]}</span>'
                        f'<span style="font-size:20px;">{grade_badge(row_data["css"], row_data["lbl"])}</span>'
                        f'</div>'
                    )
                # Formula
                formula_html = dd["formula"].replace("\n", "<br>")
                card += (
                    f'<div style="background:#0a1628;border-left:3px solid #3b82f6;'
                    f'padding:10px 14px;border-radius:4px;margin-bottom:12px;">'
                    f'<div style="font-size:10px;color:#64748b;margin-bottom:4px;'
                    f'text-transform:uppercase;letter-spacing:.05em;">Formel</div>'
                    f'<div style="font-size:13px;color:#93c5fd;font-family:monospace;'
                    f'white-space:pre-wrap;">{formula_html}</div>'
                    f'</div>'
                )
                # Data Fields
                fields = dd.get("fields", [])
                if fields:
                    card += (
                        '<div style="background:#0a1628;border-left:3px solid #6366f1;'
                        'padding:10px 14px;border-radius:4px;margin-bottom:16px;">'
                        '<div style="font-size:10px;color:#64748b;margin-bottom:6px;'
                        'text-transform:uppercase;letter-spacing:.05em;">Data Fields</div>'
                    )
                    for f_name in fields:
                        parts = f_name.split(".", 1)
                        stmt  = parts[0] if len(parts) == 2 else ""
                        field = parts[1] if len(parts) == 2 else f_name
                        card += (
                            f'<div style="display:flex;align-items:baseline;gap:6px;'
                            f'margin-bottom:3px;font-family:monospace;font-size:12px;">'
                            f'<span style="color:#6366f1;white-space:nowrap;">{stmt}.</span>'
                            f'<span style="color:#a5b4fc;">{field}</span>'
                            f'</div>'
                        )
                    card += '</div>'
                # Components
                if dd["components"]:
                    card += (
                        '<div style="margin-bottom:16px;">'
                        '<div style="font-size:10px;color:#64748b;margin-bottom:6px;'
                        'text-transform:uppercase;letter-spacing:.05em;">Rohdaten</div>'
                        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
                    )
                    for name, value in dd["components"]:
                        if not name: continue
                        card += (
                            f'<tr style="border-bottom:1px solid #1e2535;">'
                            f'<td style="padding:5px 2px;color:#94a3b8;">{name}</td>'
                            f'<td style="padding:5px 2px;text-align:right;color:#e2e8f0;'
                            f'font-weight:600;">{value}</td></tr>'
                        )
                    card += '</table></div>'
                # Historical averages
                if row_data:
                    card += (
                        f'<div style="background:#0f1a2e;border-radius:6px;padding:10px 14px;">'
                        f'<div style="font-size:10px;color:#64748b;margin-bottom:8px;'
                        f'text-transform:uppercase;letter-spacing:.05em;">Historische Durchschnitte</div>'
                        f'<div style="display:flex;gap:20px;">'
                        f'<div><div style="font-size:10px;color:#64748b;">3Y Avg</div>'
                        f'<div style="font-size:15px;font-weight:600;color:#e2e8f0;">'
                        f'{row_data["avg3"]}</div></div>'
                        f'<div><div style="font-size:10px;color:#64748b;">5Y Avg</div>'
                        f'<div style="font-size:15px;font-weight:600;color:#e2e8f0;">'
                        f'{row_data["avg5"]}</div></div>'
                        f'<div><div style="font-size:10px;color:#64748b;">10Y Avg</div>'
                        f'<div style="font-size:15px;font-weight:600;color:#e2e8f0;">'
                        f'{row_data.get("avg10","—")}</div></div>'
                        f'</div></div>'
                    )
                card += '</div>'
                st.markdown(card, unsafe_allow_html=True)
            else:
                st.info("← Zeile in der Tabelle anklicken für Drill-Down")


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
