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
    ebit     = latest(ttm_is, "operatingIncome")
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
    eps_gr_ttm    = ttm_growth(ttm_is, "netIncomeApplicableToCommonShares")
    ebit_gr_ttm   = ttm_growth(ttm_is, "operatingIncome")
    ebitda_gr_ttm = ttm_growth(ttm_is, "ebitda")
    fcf_gr_ttm    = ttm_growth(ttm_cf, "freeCashFlowCalc")

    # QoQ growth — from raw quarterly data
    rev_gr_qoq    = qoq_growth(q_is, "totalRevenue")
    earn_gr_qoq   = qoq_growth(q_is, "netIncome")
    eps_gr_qoq    = qoq_growth(q_is, "netIncomeApplicableToCommonShares")
    ebit_gr_qoq   = qoq_growth(q_is, "operatingIncome")
    ebitda_gr_qoq = qoq_growth(q_is, "ebitda")
    fcf_gr_qoq    = qoq_growth(q_cf, "freeCashFlow")

    # YoY growth — from raw quarterly data (Q[0] vs Q[4])
    rev_gr_yoy    = yoy_growth(q_is, "totalRevenue")
    earn_gr_yoy   = yoy_growth(q_is, "netIncome")
    eps_gr_yoy    = yoy_growth(q_is, "netIncomeApplicableToCommonShares")
    ebit_gr_yoy   = yoy_growth(q_is, "operatingIncome")
    ebitda_gr_yoy = yoy_growth(q_is, "ebitda")
    fcf_gr_yoy    = yoy_growth(q_cf, "freeCashFlow")

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
        if not quarterly or len(quarterly) < 4:
            return pd.DataFrame()

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
            if fcf is None:
                # fallback: CFO - abs(CapEx), handles both sign conventions
                if cfo is not None and capex is not None:
                    fcf = cfo - abs(capex)
                else:
                    fcf = None
            ttm_row["freeCashFlowCalc"] = fcf
            ttm_row["fcfMargin"]        = fcf / rev    if rev and fcf    else None
            ttm_row["debtToEquity"]     = debt / equity if equity and debt else None

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
