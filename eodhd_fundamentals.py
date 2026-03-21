import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from auth import require_login

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EOD Fundamentals Viewer",
    page_icon="📊",
    layout="wide",
)

require_login()  # ← GitHub OAuth gate — muss vor allem anderen stehen

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
    import math
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
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


def expand_rows_with_avgs(rows):
    """
    Insert 3Y/5Y/10Y avg sub-rows once per metric, after the LAST period-variant row.
    Metric group = label stripped of period suffixes like (TTM), (Year), (Quarterly),
    (Cur), (Fwd), (Ann), (QoQ), (YoY), (3Y CAGR) etc.
    """
    import re as _re

    def metric_key(label):
        """Strip period/variant suffix and ↳ prefix to get canonical metric name."""
        label = label.strip().lstrip("↳").strip()
        return _re.sub(
            r"\s*\((Fwd|Cur|TTM|Year|Ann|QoQ|YoY|Quarterly|\d+Y CAGR)\)\s*$",
            "", label
        ).strip()

    # Find last index per metric key (only rows that have avgs)
    # Skip: already-expanded avg rows, CAGR rows (Growth uses explicit CAGR rows instead)
    CAGR_KEYWORDS = ("CAGR", "Fwd", "TTM", "Ann", "QoQ", "YoY")
    def is_growth_variant(label):
        """Returns True if label is a period-variant that already has explicit CAGR rows below it."""
        return "Growth" in label and any(k in label for k in CAGR_KEYWORDS)

    # Use (tab, metric_key) as group key so rows from different tabs don't interfere
    group_last = {}
    for i, r in enumerate(rows):
        avg_vals = [r.get("avg3","—"), r.get("avg5","—"), r.get("avg10","—")]
        has_avgs = any(v not in ("—", None, "") for v in avg_vals)
        if has_avgs and not r.get("is_avg_row", False) and not is_growth_variant(r["label"]):
            mk = (r.get("tab", ""), metric_key(r["label"]))
            group_last[mk] = i

    expanded = []
    for i, r in enumerate(rows):
        expanded.append(r)
        mk = (r.get("tab", ""), metric_key(r["label"]))
        if group_last.get(mk) == i:
            # Append avg sub-rows once after the last period-variant of this metric
            T       = r.get("T", [])
            higher  = r.get("higher", True)
            pct     = r.get("pct", False)
            base_label = metric_key(r["label"])  # e.g. "P/Earnings", "Gross Margin"
            for suffix, raw_key, fmt_key, hy_key in [
                ("3Y Avg",  "avg3_raw",  "avg3",  "hy3"),
                ("5Y Avg",  "avg5_raw",  "avg5",  "hy5"),
                ("10Y Avg", "avg10_raw", "avg10", "hy10"),
            ]:
                raw_val = r.get(raw_key)
                fmt_val = r.get(fmt_key, "—")
                if raw_val is None or fmt_val in ("—", None, ""):
                    continue
                # Compute grade for this avg value
                if T:
                    if higher:
                        css, lbl = get_grade(raw_val, T)
                    else:
                        neg = [(-t, g) for t, g in T]
                        css, lbl = get_grade(-raw_val, neg)
                else:
                    css, lbl = "grade-na", "—"
                expanded.append({
                    "label":      f"  ↳ {base_label} ({suffix})",
                    "fmt":        fmt_val,
                    "css":        css,
                    "lbl":        lbl,
                    "avg3":       "—",
                    "avg5":       "—",
                    "avg10":      "—",
                    "group":      r.get("group", ""),
                    "tab":        r.get("tab", ""),
                    "is_avg_row": True,
                    "hy_vals":    r.get(hy_key, []),   # [(year, fmt_val), ...]
                    "hy_n":       suffix,               # "3Y Avg" / "5Y Avg" / "10Y Avg"
                })
    return expanded

def score_rows_to_excel(rows: list, sheet_name: str = "Score") -> bytes:
    """Convert score tab rows to CSV bytes for download."""
    import io
    import pandas as pd
    def clean(v):
        """Normalise display values for CSV — replace special chars with ASCII-safe equivalents."""
        if v is None: return "-"
        s = str(v)
        if s in ("N/A", "None", "", "nan", "inf", "-inf", "—", "–"): return "-"
        # Replace em/en dash with hyphen for Excel compatibility
        s = s.replace("—", "-").replace("–", "-")
        return s
    df = pd.DataFrame([{
        "Metric":   r["label"],
        "Value":    clean(r.get("fmt")),
        "Grade":    clean(r.get("lbl")),
        "3Y Avg":   clean(r.get("avg3")),
        "5Y Avg":   clean(r.get("avg5")),
        "10Y Avg":  clean(r.get("avg10")),
    } for r in rows])
    # UTF-8 BOM so Excel opens the file with correct encoding
    return b"\xef\xbb\xbf" + df.to_csv(index=False).encode("utf-8")


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
    # P/S (Fwd): estimated from Revenue_TTM * (1 + revenueEstimateGrowth)
    _tr_kz   = data.get("Earnings", {}).get("Trend", {})
    _p1y_kz  = next((v for v in _tr_kz.values() if v.get("period") == "+1y"), {})
    _rgr_kz  = fv(_p1y_kz.get("revenueEstimateGrowth"))
    _mcap_kz = fv(hl.get("MarketCapitalization"))
    _rev_ttm_kz = fv(hl.get("RevenueTTM"))
    ps_fwd   = (_mcap_kz / (_rev_ttm_kz * (1 + _rgr_kz))) \
               if _mcap_kz and _rev_ttm_kz and _rgr_kz is not None and _rev_ttm_kz * (1 + _rgr_kz) > 0 \
               else None
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
    cash     = (latest(ttm_bs, "cash") or latest(ttm_bs, "cashAndEquivalents") or 0) + (latest(ttm_bs, "shortTermInvestments") or 0)
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
        import math
        try:
            s = df[col].dropna()
            if len(s) >= 5 and s.iloc[4] != 0:
                r = (s.iloc[0] / s.iloc[4] - 1) * 100
                return None if (math.isnan(r) or math.isinf(r)) else r
            elif len(s) >= 2 and s.iloc[1] != 0:
                r = (s.iloc[0] / s.iloc[1] - 1) * 100
                return None if (math.isnan(r) or math.isinf(r)) else r
        except: pass
        return None

    def qoq_growth(df, col):
        """QoQ: Q[0] vs Q[1] — raw quarterly data"""
        import math
        try:
            s = df[col].dropna()
            if len(s) >= 2 and s.iloc[1] != 0:
                r = (s.iloc[0] / s.iloc[1] - 1) * 100
                return None if (math.isnan(r) or math.isinf(r)) else r
        except: pass
        return None

    def yoy_growth(df, col):
        """YoY: Q[0] vs Q[4] if available, fallback to Q[1]"""
        import math
        try:
            s = df[col].dropna()
            if len(s) >= 5 and s.iloc[4] != 0:
                r = (s.iloc[0] / s.iloc[4] - 1) * 100
                return None if (math.isnan(r) or math.isinf(r)) else r
            elif len(s) >= 2 and s.iloc[1] != 0:
                r = (s.iloc[0] / s.iloc[1] - 1) * 100
                return None if (math.isnan(r) or math.isinf(r)) else r
        except: pass
        return None

    # TTM growth — from TTM history
    rev_gr_ttm    = ttm_growth(ttm_is, "totalRevenue")
    earn_gr_ttm   = ttm_growth(ttm_is, "netIncome")
    # EPS TTM growth: self-calculated NI/shares (consistent with Score Tab)
    _q_is_eg = data["Financials"]["Income_Statement"].get("quarterly", {})
    _q_bs_eg = data["Financials"]["Balance_Sheet"].get("quarterly", {})
    _qs_eg   = sorted(_q_is_eg.keys(), reverse=True)
    _qbs_eg  = sorted(_q_bs_eg.keys(), reverse=True)
    def _ni_ttm_eg(start):
        if len(_qs_eg) < start + 4: return None
        vals = [fv(_q_is_eg[_qs_eg[i]].get("netIncomeApplicableToCommonShares")) or
                fv(_q_is_eg[_qs_eg[i]].get("netIncome")) for i in range(start, start+4)]
        return sum(vals) if all(v is not None for v in vals) else None
    _ni_now_eg  = _ni_ttm_eg(0)
    _ni_ago_eg  = _ni_ttm_eg(4)
    _sh_now_eg  = fv(_q_bs_eg[_qbs_eg[0]].get("commonStockSharesOutstanding")) if _qbs_eg else None
    _sh_ago_eg  = fv(_q_bs_eg[_qbs_eg[4]].get("commonStockSharesOutstanding")) if len(_qbs_eg) > 4 else _sh_now_eg
    _eps_now_eg = (_ni_now_eg / _sh_now_eg) if _ni_now_eg and _sh_now_eg and _sh_now_eg > 0 else None
    _eps_ago_eg = (_ni_ago_eg / _sh_ago_eg) if _ni_ago_eg and _sh_ago_eg and _sh_ago_eg > 0 else None
    eps_gr_ttm  = ((_eps_now_eg / _eps_ago_eg - 1) * 100) if _eps_now_eg and _eps_ago_eg and _eps_ago_eg > 0 else None
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
    ebit_gr_yoy   = yoy_growth(q_is, "ebit")
    ebitda_gr_yoy = yoy_growth(q_is, "ebitda")
    fcf_gr_yoy    = (yoy_growth(q_cf, "freeCashFlow")
                     or yoy_growth(q_cf, "freeCashFlowCalc"))

    # Annual growth — Y0 vs Y1 (last fiscal year vs prior fiscal year)
    def ann_growth(stmt, key):
        """Annual YoY: latest fiscal year vs prior fiscal year."""
        import math
        ys = sorted(stmt.keys(), reverse=True)
        if len(ys) < 2: return None
        v0 = fv(stmt[ys[0]].get(key))
        v1 = fv(stmt[ys[1]].get(key))
        if v0 is None or not v1 or v1 <= 0: return None
        r = (v0 / v1 - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r

    _a_is_hl = data["Financials"]["Income_Statement"].get("yearly", {})
    _a_cf_hl = data["Financials"]["Cash_Flow"].get("yearly", {})
    rev_gr_ann    = ann_growth(_a_is_hl, "totalRevenue")
    earn_gr_ann   = ann_growth(_a_is_hl, "netIncome")
    ebit_gr_ann   = ann_growth(_a_is_hl, "ebit")
    ebitda_gr_ann = ann_growth(_a_is_hl, "ebitda")
    # EPS annual: NI/shares Y0 vs Y1
    _a_bs_hl = data["Financials"]["Balance_Sheet"].get("yearly", {})
    _ys_hl   = sorted(_a_is_hl.keys(), reverse=True)
    def _eps_ann_hl(idx):
        if idx >= len(_ys_hl): return None
        y   = _ys_hl[idx]
        ni  = fv(_a_is_hl[y].get("netIncomeApplicableToCommonShares")) or fv(_a_is_hl[y].get("netIncome"))
        shs = fv(_a_bs_hl.get(y, {}).get("commonStockSharesOutstanding"))
        return (ni / shs) if ni and shs and shs > 0 else None
    _ea0 = _eps_ann_hl(0); _ea1 = _eps_ann_hl(1)
    eps_gr_ann = ((_ea0 / _ea1 - 1) * 100) if _ea0 and _ea1 and _ea1 > 0 else None
    # FCF annual: freeCashFlow Y0 vs Y1, fallback CFO-CapEx
    def _fcf_ann_hl(y):
        d = _a_cf_hl.get(y, {})
        f = fv(d.get("freeCashFlow"))
        if f is None:
            cfo   = fv(d.get("totalCashFromOperatingActivities"))
            capex = fv(d.get("capitalExpenditures"))
            f = cfo - abs(capex) if cfo and capex else None
        return f
    _ys_cf_hl = sorted(_a_cf_hl.keys(), reverse=True)
    _fcf0 = _fcf_ann_hl(_ys_cf_hl[0]) if len(_ys_cf_hl) > 0 else None
    _fcf1 = _fcf_ann_hl(_ys_cf_hl[1]) if len(_ys_cf_hl) > 1 else None
    fcf_gr_ann = ((_fcf0 / _fcf1 - 1) * 100) if _fcf0 and _fcf1 and _fcf1 > 0 else None

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
        "ps_fwd":    (ps_fwd,    fmt_n(ps_fwd,2),    [(0,"ap"),(1,"a"),(2,"am"),(3,"bp"),(5,"b"),(7,"bm"),(10,"cp")],               False),
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
        # Annual growth (Y0 vs Y1 — full fiscal year)
        "rev_gr_ann":    (rev_gr_ann,    fmt_p(rev_gr_ann),    [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-5,"cp")],  True),
        "earn_gr_ann":   (earn_gr_ann,   fmt_p(earn_gr_ann),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "eps_gr_ann":    (eps_gr_ann,    fmt_p(eps_gr_ann),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebit_gr_ann":   (ebit_gr_ann,   fmt_p(ebit_gr_ann),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ebitda_gr_ann": (ebitda_gr_ann, fmt_p(ebitda_gr_ann), [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "fcf_gr_ann":    (fcf_gr_ann,    fmt_p(fcf_gr_ann),    [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
        "ni_gr_ann":     (earn_gr_ann,   fmt_p(earn_gr_ann),   [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(0,"b"),(-10,"bm")],         True),
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
    cash_yr  = (yr(a_bs, "cash") or yr(a_bs, "cashAndEquivalents") or 0) + (yr(a_bs, "shortTermInvestments") or 0)
    total_debt = (lt_debt or 0) + (st_debt or 0)

    # EV: from Valuation, fallback calculated
    ev = ev_raw or (mcap + total_debt - (cash_yr or 0) if mcap else None)

    # TTM from Highlights
    rev_ttm = fv(hl.get("RevenueTTM"))
    # EPS TTM = NI_TTM / shares (latest quarter) — self-calculated
    _q_is_vs = data["Financials"]["Income_Statement"].get("quarterly", {})
    _q_bs_vs = data["Financials"]["Balance_Sheet"].get("quarterly", {})
    _qs_vs   = sorted(_q_is_vs.keys(), reverse=True)
    _qbs_vs  = sorted(_q_bs_vs.keys(), reverse=True)
    _ni_ttm_vals = []
    for _q in _qs_vs[:4]:
        _v = fv(_q_is_vs[_q].get("netIncomeApplicableToCommonShares")) or fv(_q_is_vs[_q].get("netIncome"))
        if _v is not None: _ni_ttm_vals.append(_v)
    _ni_ttm_sum = sum(_ni_ttm_vals) if len(_ni_ttm_vals) == 4 else None
    _shs_latest = fv(_q_bs_vs[_qbs_vs[0]].get("commonStockSharesOutstanding")) if _qbs_vs else None
    eps_ttm = (_ni_ttm_sum / _shs_latest) if _ni_ttm_sum and _shs_latest and _shs_latest > 0 else None

    # ── Current Ratios ───────────────────────────────────────────────
    pe_fwd   = fv(val.get("ForwardPE"))
    # P/E (Cur): MCap/NI_common_TTM → MCap/NI_TTM → TrailingPE → PERatio
    _q_is_pe  = data["Financials"]["Income_Statement"].get("quarterly", {})
    _qs_pe    = sorted(_q_is_pe.keys(), reverse=True)
    _nicom_pe = [fv(_q_is_pe[q].get("netIncomeApplicableToCommonShares")) for q in _qs_pe[:4]]
    _ni_pe    = [fv(_q_is_pe[q].get("netIncome")) for q in _qs_pe[:4]]
    _ni_common_ttm = sum(_nicom_pe) if len(_nicom_pe)==4 and all(v is not None for v in _nicom_pe) else None
    _ni_ttm_pe     = sum(_ni_pe)    if len(_ni_pe)==4    and all(v is not None for v in _ni_pe)    else None
    _pe_common = (mcap / _ni_common_ttm) if mcap and _ni_common_ttm and _ni_common_ttm > 0 else None
    _pe_ni     = (mcap / _ni_ttm_pe)     if mcap and _ni_ttm_pe     and _ni_ttm_pe     > 0 else None
    pe_cur   = _pe_common or _pe_ni or fv(val.get("TrailingPE")) or fv(hl.get("PERatio"))
    # P/E (Year): MCap/NI_common_Year → MCap/NI_Year (no API fallback)
    _ni_common_yr = fv(a_is[years_is[0]].get("netIncomeApplicableToCommonShares")) if years_is else None
    pe_yr    = (mcap / _ni_common_yr) if mcap and _ni_common_yr and _ni_common_yr > 0 else \
               (mcap / ni_yr)         if mcap and ni_yr          and ni_yr          > 0 else None
    # P/S (Fwd): estimated as MCap / (Revenue_TTM * (1 + revenueEstimateGrowth))
    _trends_ps  = data.get("Earnings", {}).get("Trend", {})
    _p1y_ps     = next((v for v in _trends_ps.values() if v.get("period") == "+1y"), {})
    _rev_gr_est = fv(_p1y_ps.get("revenueEstimateGrowth"))  # raw decimal e.g. 0.08
    _rev_ttm_ps_fwd = sum(
        fv(data["Financials"]["Income_Statement"].get("quarterly", {}).get(q, {}).get("totalRevenue")) or 0
        for q in sorted(data["Financials"]["Income_Statement"].get("quarterly", {}).keys(), reverse=True)[:4]
    ) or None
    if _rev_gr_est is not None and _rev_ttm_ps_fwd:
        _fwd_rev = _rev_ttm_ps_fwd * (1 + _rev_gr_est)
        ps_fwd   = (mcap / _fwd_rev) if mcap and _fwd_rev and _fwd_rev > 0 else None
    else:
        ps_fwd   = None

    # P/Sales (Cur): PriceSalesTTM → self-calculated mcap/rev_ttm
    _q_is_ps   = data["Financials"]["Income_Statement"].get("quarterly", {})
    _qs_ps     = sorted(_q_is_ps.keys(), reverse=True)
    _rev_ttm_ps_vals = [
        fv(_q_is_ps[q].get("totalRevenue")) for q in _qs_ps[:4]
    ]
    _rev_ttm_ps = sum(_rev_ttm_ps_vals) if len(_rev_ttm_ps_vals) == 4 and all(v is not None for v in _rev_ttm_ps_vals) else None
    _ps_calc   = (mcap / _rev_ttm_ps) if mcap and _rev_ttm_ps and _rev_ttm_ps > 0 else None
    ps_cur     = fv(val.get("PriceSalesTTM")) or _ps_calc
    ps_yr      = (mcap / rev_yr)    if mcap and rev_yr and rev_yr > 0 else None
    _q_bs_pb  = data["Financials"]["Balance_Sheet"].get("quarterly", {})
    _qbs_pb   = sorted(_q_bs_pb.keys(), reverse=True)
    _equity_q_pb = fv(_q_bs_pb[_qbs_pb[0]].get("totalStockholderEquity")) if _qbs_pb else None
    _pb_self  = (mcap / _equity_q_pb) if mcap and _equity_q_pb and _equity_q_pb > 0 else None
    pb_cur    = fv(val.get("PriceBookMRQ")) or _pb_self
    pb_yr     = (mcap / equity_yr) if mcap and equity_yr and equity_yr > 0 else None

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
    # Growth rate: YoY EPS growth — self-calculated as NI/shares
    _a_bs_peg = data["Financials"]["Balance_Sheet"].get("yearly", {})
    _a_is_peg = data["Financials"]["Income_Statement"].get("yearly", {})
    _ys_peg   = sorted(_a_is_peg.keys(), reverse=True)
    def _get_eps_peg(idx):
        if idx >= len(_ys_peg): return None
        y   = _ys_peg[idx]
        ni  = fv(_a_is_peg[y].get("netIncomeApplicableToCommonShares")) or fv(_a_is_peg[y].get("netIncome"))
        shs = fv(_a_bs_peg.get(y, {}).get("commonStockSharesOutstanding"))
        return (ni / shs) if ni and shs and shs > 0 else None
    _eps0_peg = _get_eps_peg(0)
    _eps1_peg = _get_eps_peg(1)
    ni_cur  = yr(a_is, "netIncome", 0)   # kept for drilldown display only
    ni_prev = yr(a_is, "netIncome", 1)   # kept for drilldown display only
    eps_gr_yr = ((_eps0_peg / _eps1_peg - 1) * 100) if _eps0_peg and _eps1_peg and _eps1_peg > 0 else None
    # PEG (Fwd): earningsEstimateGrowth(+1y) -> eps_gr_ttm_peg -> eps_gr_yr
    _tr_sc   = data.get("Earnings", {}).get("Trend", {})
    _p1y_sc  = next((v for v in _tr_sc.values() if v.get("period") == "+1y"), {})
    _eg_raw  = fv(_p1y_sc.get("earningsEstimateGrowth"))
    _eg_pct  = _eg_raw * 100 if _eg_raw is not None else None
    # TTM EPS growth for fallback
    _qis_sc  = data["Financials"]["Income_Statement"].get("quarterly", {})
    _qbs_sc  = data["Financials"]["Balance_Sheet"].get("quarterly", {})
    _qs_sc   = sorted(_qis_sc.keys(), reverse=True)
    _qbss    = sorted(_qbs_sc.keys(), reverse=True)
    def _ni_ttm_sc(st):
        vs = [fv(_qis_sc[q].get("netIncomeApplicableToCommonShares")) or fv(_qis_sc[q].get("netIncome")) for q in _qs_sc[st:st+4]]
        return sum(vs) if len(vs)==4 and all(v is not None for v in vs) else None
    _ni0_sc  = _ni_ttm_sc(0); _ni4_sc = _ni_ttm_sc(4)
    _sh0_sc  = fv(_qbs_sc[_qbss[0]].get("commonStockSharesOutstanding")) if _qbss else None
    _sh4_sc  = fv(_qbs_sc[_qbss[4]].get("commonStockSharesOutstanding")) if len(_qbss)>4 else None
    _ep0_sc  = (_ni0_sc/_sh0_sc) if _ni0_sc and _sh0_sc and _sh0_sc>0 else None
    _ep4_sc  = (_ni4_sc/_sh4_sc) if _ni4_sc and _sh4_sc and _sh4_sc>0 else None
    _eg_ttm  = ((_ep0_sc/_ep4_sc-1)*100) if _ep0_sc and _ep4_sc and _ep4_sc>0 else None
    _peg_fwd_gr = (_eg_pct  if (_eg_pct  and _eg_pct  > 0) else
                  (_eg_ttm  if (_eg_ttm  and _eg_ttm  > 0) else
                  (eps_gr_yr if (eps_gr_yr and eps_gr_yr > 0) else None)))
    peg_fwd  = (pe_fwd / _peg_fwd_gr) if pe_fwd and _peg_fwd_gr else None
    peg_cur  = (pe_cur / eps_gr_yr)  if pe_cur  and eps_gr_yr and eps_gr_yr > 0 else None
    peg_yr   = (pe_yr  / eps_gr_yr)  if pe_yr   and eps_gr_yr and eps_gr_yr > 0 else None

    # ── Historical averages using real year-end prices ────────────────
    # price_data: {YYYY: adjusted_close} — last trading day of each year
    def hist_multiple(statement, key, n, use_ev=False, invert_fcf=False):
        """Return (avg, [(year, val_or_skip_reason)]) using real year-end prices.
        Skipped years are included as (year, None, reason_str) tuples for display."""
        years = sorted(statement.keys(), reverse=True)
        vals   = []   # (year, float) — used for avg
        all_yr = []   # (year, float|None, reason|None) — full display list
        for y in years[:n]:
            yr_str = y[:4]
            price  = price_data.get(yr_str)
            fund   = fv(statement[y].get(key))
            if price is None:
                all_yr.append((yr_str, None, "kein Preis verfügbar"))
                continue
            if not fund:
                all_yr.append((yr_str, None, "Fundamental-Wert fehlt"))
                continue
            if fund <= 0:
                all_yr.append((yr_str, None, f"neg. Basis ({key})"))
                continue
            if use_ev:
                bs_y   = data["Financials"]["Balance_Sheet"]["yearly"].get(y, {})
                ltd    = fv(bs_y.get("longTermDebt")) or 0
                std    = fv(bs_y.get("shortLongTermDebt")) or 0
                csh    = (fv(bs_y.get("cash")) or fv(bs_y.get("cashAndEquivalents")) or 0) + (fv(bs_y.get("shortTermInvestments")) or 0)
                shs    = fv(bs_y.get("commonStockSharesOutstanding"))
                if not shs:
                    all_yr.append((yr_str, None, "Shares fehlen"))
                    continue
                ev_y  = price * shs + ltd + std - csh
                mult  = ev_y / fund
                vals.append((yr_str, mult))
                all_yr.append((yr_str, mult, None))
            else:
                shs = fv(data["Financials"]["Balance_Sheet"]["yearly"].get(y, {}).get("commonStockSharesOutstanding"))
                if not shs:
                    all_yr.append((yr_str, None, "Shares fehlen"))
                    continue
                mcap_y = price * shs
                mult   = mcap_y / fund
                vals.append((yr_str, mult))
                all_yr.append((yr_str, mult, None))
        avg = sum(v for _, v in vals) / len(vals) if vals else None
        return avg, all_yr

    def fcf_hist_real(n):
        years = sorted(a_cf.keys(), reverse=True)
        vals   = []
        all_yr = []
        for y in years[:n]:
            yr_str = y[:4]
            price  = price_data.get(yr_str)
            if price is None:
                all_yr.append((yr_str, None, "kein Preis verfügbar"))
                continue
            f = fv(a_cf[y].get("freeCashFlow"))
            if not f:
                cfo   = fv(a_cf[y].get("totalCashFromOperatingActivities"))
                capex = fv(a_cf[y].get("capitalExpenditures"))
                f = cfo - abs(capex) if cfo and capex else None
            if not f:
                all_yr.append((yr_str, None, "FCF-Wert fehlt"))
                continue
            if f <= 0:
                all_yr.append((yr_str, None, "neg. FCF"))
                continue
            shs = fv(data["Financials"]["Balance_Sheet"]["yearly"].get(y, {}).get("commonStockSharesOutstanding"))
            if not shs:
                all_yr.append((yr_str, None, "Shares fehlen"))
                continue
            mult = price * shs / f
            vals.append((yr_str, mult))
            all_yr.append((yr_str, mult, None))
        avg = sum(v for _, v in vals) / len(vals) if vals else None
        return avg, all_yr

    def yield_hist_real(statement, key, n):
        years = sorted(statement.keys(), reverse=True)
        vals   = []
        all_yr = []
        for y in years[:n]:
            yr_str = y[:4]
            price  = price_data.get(yr_str)
            if price is None:
                all_yr.append((yr_str, None, "kein Preis verfügbar"))
                continue
            fund = fv(statement[y].get(key))
            if not fund:
                all_yr.append((yr_str, None, "Fundamental-Wert fehlt"))
                continue
            shs = fv(data["Financials"]["Balance_Sheet"]["yearly"].get(y, {}).get("commonStockSharesOutstanding"))
            if not shs:
                all_yr.append((yr_str, None, "Shares fehlen"))
                continue
            mcap_y = price * shs
            if mcap_y > 0:
                yld = fund / mcap_y * 100
                vals.append((yr_str, yld))
                all_yr.append((yr_str, yld, None))
            else:
                all_yr.append((yr_str, None, "MCap ≤ 0"))
        avg = sum(v for _, v in vals) / len(vals) if vals else None
        return avg, all_yr

    pe_3y,   _hy_pe_3   = hist_multiple(a_is, "netIncome",             3)
    pe_5y,   _hy_pe_5   = hist_multiple(a_is, "netIncome",             5)
    pe_10y,  _hy_pe_10  = hist_multiple(a_is, "netIncome",            10)
    ps_3y,   _hy_ps_3   = hist_multiple(a_is, "totalRevenue",          3)
    ps_5y,   _hy_ps_5   = hist_multiple(a_is, "totalRevenue",          5)
    ps_10y,  _hy_ps_10  = hist_multiple(a_is, "totalRevenue",         10)
    pb_3y,   _hy_pb_3   = hist_multiple(a_bs, "totalStockholderEquity",3)
    pb_5y,   _hy_pb_5   = hist_multiple(a_bs, "totalStockholderEquity",5)
    pb_10y,  _hy_pb_10  = hist_multiple(a_bs, "totalStockholderEquity",10)
    pfcf_3y, _hy_pfcf_3 = fcf_hist_real(3)
    pfcf_5y, _hy_pfcf_5 = fcf_hist_real(5)
    pfcf_10y,_hy_pfcf_10= fcf_hist_real(10)
    ev_rev_3y,  _hy_evr_3   = hist_multiple(a_is, "totalRevenue", 3,  use_ev=True)
    ev_rev_5y,  _hy_evr_5   = hist_multiple(a_is, "totalRevenue", 5,  use_ev=True)
    ev_rev_10y, _hy_evr_10  = hist_multiple(a_is, "totalRevenue", 10, use_ev=True)
    ev_ebit_3y, _hy_eveb_3  = hist_multiple(a_is, "ebit",         3,  use_ev=True)
    ev_ebit_5y, _hy_eveb_5  = hist_multiple(a_is, "ebit",         5,  use_ev=True)
    ev_ebit_10y,_hy_eveb_10 = hist_multiple(a_is, "ebit",         10, use_ev=True)
    ev_ebitda_3y, _hy_evda_3  = hist_multiple(a_is, "ebitda",      3,  use_ev=True)
    ev_ebitda_5y, _hy_evda_5  = hist_multiple(a_is, "ebitda",      5,  use_ev=True)
    ev_ebitda_10y,_hy_evda_10 = hist_multiple(a_is, "ebitda",      10, use_ev=True)
    earn_yield_3y, _hy_ey_3  = yield_hist_real(a_is, "netIncome",    3)
    earn_yield_5y, _hy_ey_5  = yield_hist_real(a_is, "netIncome",    5)
    earn_yield_10y,_hy_ey_10 = yield_hist_real(a_is, "netIncome",   10)
    fcf_yield_3y,  _hy_fy_3  = yield_hist_real(a_cf, "freeCashFlow", 3)
    fcf_yield_5y,  _hy_fy_5  = yield_hist_real(a_cf, "freeCashFlow", 5)
    fcf_yield_10y, _hy_fy_10 = yield_hist_real(a_cf, "freeCashFlow",10)

    # PEG historical averages: avg(P/E_year / EPS_growth_year) per rolling window
    def peg_hist_avg(n):
        years = sorted(a_is.keys(), reverse=True)
        vals   = []
        all_yr = []
        for i in range(min(n, len(years) - 1)):
            y_cur  = years[i]
            y_prev = years[i + 1]
            yr_str = y_cur[:4]
            ni_c = fv(a_is[y_cur].get("netIncome"))
            ni_p = fv(a_is[y_prev].get("netIncome"))
            if not ni_c or not ni_p or ni_p <= 0:
                all_yr.append((yr_str, None, "NI fehlt oder neg. Basis"))
                continue
            gr = (ni_c / ni_p - 1) * 100
            if gr <= 0:
                all_yr.append((yr_str, None, f"neg. NI-Wachstum ({gr:.1f}%)"))
                continue
            price = price_data.get(yr_str)
            if not price:
                all_yr.append((yr_str, None, "kein Preis verfügbar"))
                continue
            shs = fv(a_bs.get(y_cur, {}).get("commonStockSharesOutstanding"))
            if not shs:
                all_yr.append((yr_str, None, "Shares fehlen"))
                continue
            pe_y = price * shs / ni_c if ni_c > 0 else None
            if pe_y:
                peg = pe_y / gr
                vals.append((yr_str, peg))
                all_yr.append((yr_str, peg, None))
            else:
                all_yr.append((yr_str, None, "P/E nicht berechenbar"))
        avg = sum(v for _, v in vals) / len(vals) if vals else None
        return avg, all_yr

    peg_3y,  _hy_peg_3  = peg_hist_avg(3)
    peg_5y,  _hy_peg_5  = peg_hist_avg(5)
    peg_10y, _hy_peg_10 = peg_hist_avg(10)

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
    def row(label, cur, avg3, avg5, avg10, T, higher=False, pct=False,
            hy3=None, hy5=None, hy10=None):
        css, lbl = ratio_grade(cur, T, higher_is_better=higher)
        def fmtv(v): return f"{v:.2f} %" if pct else f"{v:.2f}" if v is not None else None
        def conv(hy):
            # accepts [(y, val, reason)] or [(y, val)] — normalise to 3-tuple
            if not hy: return []
            result = []
            for item in hy:
                if len(item) == 3:
                    yr, v, reason = item
                else:
                    yr, v = item; reason = None
                result.append((yr, fmtv(v), reason))
            return result
        return {
            "label":  label,
            "cur":    cur,
            "fmt":    fmt(cur, pct),
            "css":    css,
            "lbl":    lbl,
            "avg3":   fmt(avg3,  pct),
            "avg5":   fmt(avg5,  pct),
            "avg10":  fmt(avg10, pct),
            "avg3_raw": avg3, "avg5_raw": avg5, "avg10_raw": avg10,
            "T": T, "higher": higher, "pct": pct,
            "group":  label.split(" ")[0],
            "hy3":  conv(hy3),
            "hy5":  conv(hy5),
            "hy10": conv(hy10),
        }

    PEG_T   = [(0,"ap"),(0.5,"a"),(1,"am"),(1.5,"bp"),(2,"b"),(3,"bm"),(4,"cp"),(5,"c")]

    rows = [
        row("P/Earnings (Fwd)",      pe_fwd,         None,          None,          None,           PE_T),
        row("P/Earnings (Cur)",      pe_cur,         pe_3y,         pe_5y,         pe_10y,         PE_T,  hy3=_hy_pe_3,   hy5=_hy_pe_5,   hy10=_hy_pe_10),
        row("P/Earnings (Year)",     pe_yr,          pe_3y,         pe_5y,         pe_10y,         PE_T,  hy3=_hy_pe_3,   hy5=_hy_pe_5,   hy10=_hy_pe_10),
        row("P/Sales (Fwd)",         ps_fwd,         None,          None,          None,           PS_T),
        row("P/Sales (Cur)",         ps_cur,         ps_3y,         ps_5y,         ps_10y,         PS_T,  hy3=_hy_ps_3,   hy5=_hy_ps_5,   hy10=_hy_ps_10),
        row("P/Sales (Year)",        ps_yr,          ps_3y,         ps_5y,         ps_10y,         PS_T,  hy3=_hy_ps_3,   hy5=_hy_ps_5,   hy10=_hy_ps_10),
        row("P/Book (Cur)",          pb_cur,         pb_3y,         pb_5y,         pb_10y,         PB_T,  hy3=_hy_pb_3,   hy5=_hy_pb_5,   hy10=_hy_pb_10),
        row("P/Book (Year)",         pb_yr,          pb_3y,         pb_5y,         pb_10y,         PB_T,  hy3=_hy_pb_3,   hy5=_hy_pb_5,   hy10=_hy_pb_10),
        row("P/FCF (Cur)",           pfcf_cur,       pfcf_3y,       pfcf_5y,       pfcf_10y,       PFCF_T, hy3=_hy_pfcf_3, hy5=_hy_pfcf_5, hy10=_hy_pfcf_10),
        row("P/FCF (Year)",          pfcf_yr,        pfcf_3y,       pfcf_5y,       pfcf_10y,       PFCF_T, hy3=_hy_pfcf_3, hy5=_hy_pfcf_5, hy10=_hy_pfcf_10),
        row("PEG Ratio (Fwd)",       peg_fwd,        peg_3y,        peg_5y,        peg_10y,        PEG_T),
        row("PEG Ratio (Cur)",       peg_cur,        peg_3y,        peg_5y,        peg_10y,        PEG_T, hy3=_hy_peg_3, hy5=_hy_peg_5, hy10=_hy_peg_10),
        row("PEG Ratio (Year)",      peg_yr,         peg_3y,        peg_5y,        peg_10y,        PEG_T, hy3=_hy_peg_3, hy5=_hy_peg_5, hy10=_hy_peg_10),
        row("EV/Revenue (Cur)",      ev_rev_cur,     ev_rev_3y,     ev_rev_5y,     ev_rev_10y,     EVR_T,   hy3=_hy_evr_3,  hy5=_hy_evr_5,  hy10=_hy_evr_10),
        row("EV/Revenue (Year)",     ev_rev_yr,      ev_rev_3y,     ev_rev_5y,     ev_rev_10y,     EVR_T,   hy3=_hy_evr_3,  hy5=_hy_evr_5,  hy10=_hy_evr_10),
        row("EV/EBIT (Cur)",         ev_ebit_cur,    ev_ebit_3y,    ev_ebit_5y,    ev_ebit_10y,    EVEBIT_T, hy3=_hy_eveb_3, hy5=_hy_eveb_5, hy10=_hy_eveb_10),
        row("EV/EBIT (Year)",        ev_ebit_yr,     ev_ebit_3y,    ev_ebit_5y,    ev_ebit_10y,    EVEBIT_T, hy3=_hy_eveb_3, hy5=_hy_eveb_5, hy10=_hy_eveb_10),
        row("EV/EBITDA (Cur)",       ev_ebitda_cur,  ev_ebitda_3y,  ev_ebitda_5y,  ev_ebitda_10y,  EVEBDA_T, hy3=_hy_evda_3, hy5=_hy_evda_5, hy10=_hy_evda_10),
        row("EV/EBITDA (Year)",      ev_ebitda_yr,   ev_ebitda_3y,  ev_ebitda_5y,  ev_ebitda_10y,  EVEBDA_T, hy3=_hy_evda_3, hy5=_hy_evda_5, hy10=_hy_evda_10),
        row("Earnings Yield (Cur)",  earn_yield_cur, earn_yield_3y, earn_yield_5y, earn_yield_10y, EY_T,   higher=True, pct=True, hy3=_hy_ey_3, hy5=_hy_ey_5, hy10=_hy_ey_10),
        row("Earnings Yield (Year)", earn_yield_yr,  earn_yield_3y, earn_yield_5y, earn_yield_10y, EY_T,   higher=True, pct=True, hy3=_hy_ey_3, hy5=_hy_ey_5, hy10=_hy_ey_10),
        row("FCF Yield (TTM)",       fcf_yield_ttm,  fcf_yield_3y,  fcf_yield_5y,  fcf_yield_10y,  FCFY_T, higher=True, pct=True, hy3=_hy_fy_3, hy5=_hy_fy_5, hy10=_hy_fy_10),
        row("FCF Yield (Year)",      fcf_yield_yr,   fcf_yield_3y,  fcf_yield_5y,  fcf_yield_10y,  FCFY_T, higher=True, pct=True, hy3=_hy_fy_3, hy5=_hy_fy_5, hy10=_hy_fy_10),
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
    Returns { formula, fields, components: [(name, value)], result, unit }
    Every raw value, intermediate step and final result is shown explicitly.
    """
    def fv(v):
        try: return float(v) if v not in (None, "", "NA", "None") else None
        except: return None
    def pct(v):  return f"{v*100:.4f} %" if v is not None else "—"
    def num(v, d=4): return f"{v:.{d}f}" if v is not None else "—"
    def raw(v):
        """Show exact API value — integer if whole number, otherwise full float."""
        if v is None: return "—"
        if v == int(v): return f"{int(v):,}"
        return f"{v:,.2f}"
    def bn(v):   return raw(v)   # all component values now show raw API numbers
    def safe(a, b): return a/b if (a is not None and b is not None and b != 0) else None
    def div_str(a, b, unit=""):
        r = safe(a, b)
        a_s = bn(a); b_s = bn(b)
        r_s = (f"{r:.4f} {unit}" if unit else f"{r:.4f}") if r is not None else "—"
        return a_s, b_s, r_s

    a_is = data["Financials"]["Income_Statement"].get("yearly", {})
    a_cf = data["Financials"]["Cash_Flow"].get("yearly", {})
    a_bs = data["Financials"]["Balance_Sheet"].get("yearly", {})
    q_is = data["Financials"]["Income_Statement"].get("quarterly", {})
    q_cf = data["Financials"]["Cash_Flow"].get("quarterly", {})
    q_bs = data["Financials"]["Balance_Sheet"].get("quarterly", {})

    years    = sorted(a_is.keys(), reverse=True)
    years_bs = sorted(a_bs.keys(), reverse=True)
    years_cf = sorted(a_cf.keys(), reverse=True)
    qis_s    = sorted(q_is.keys(), reverse=True)
    qcf_s    = sorted(q_cf.keys(), reverse=True)
    qbs_s    = sorted(q_bs.keys(), reverse=True)

    def ttm_quarters(stmt, key):
        qs   = sorted(stmt.keys(), reverse=True)
        vals = [(q, fv(stmt[q].get(key))) for q in qs[:4]]
        total = sum(v for _, v in vals if v is not None)
        return total if sum(1 for _, v in vals if v is not None) == 4 else None, vals

    def ttm_rows(stmt, key, api_field, label="TTM"):
        """Returns component rows showing each quarter + sum for TTM values."""
        qs = sorted(stmt.keys(), reverse=True)[:4]
        rows = [(f"  {api_field}  [{q}]", raw(fv(stmt[q].get(key)))) for q in qs]
        total = sum(fv(stmt[q].get(key)) or 0 for q in qs)
        rows.append((f"  → {label} Sum  (Q1+Q2+Q3+Q4)", raw(total)))
        return rows

    def cash_comps(bs_dict, dt):
        """Returns component rows for cash showing cashAndEquivalents + shortTermInvestments breakdown."""
        cae = fv(bs_dict.get("cash")) or fv(bs_dict.get("cashAndEquivalents"))
        sti = fv(bs_dict.get("shortTermInvestments"))
        total = (cae or 0) + (sti or 0)
        rows = [
            (f"  cash (primary)  [{dt}]",        raw(fv(bs_dict.get("cash")))),
            (f"  cashAndEquivalents (fallback)  [{dt}]", raw(fv(bs_dict.get("cashAndEquivalents"))) if not fv(bs_dict.get("cash")) else "— (not used)"),
            (f"  shortTermInvestments  [{dt}]",  raw(sti) if sti else "0  (not reported)"),
            (f"  → Cash Total (used)",           raw(total)),
        ]
        return rows, total

    def ttm(stmt, key):
        v, _ = ttm_quarters(stmt, key)
        return v

    def get_fcf_detail(is_ttm, yr=None):
        """Returns (fcf, cfo, capex, fcf_raw_available, quarters_used)"""
        if is_ttm:
            qs = sorted(q_cf.keys(), reverse=True)[:4]
            fcf_qs, cfo_qs, cx_qs = [], [], []
            for q in qs:
                f  = fv(q_cf[q].get("freeCashFlow"))
                c  = fv(q_cf[q].get("totalCashFromOperatingActivities"))
                cx = fv(q_cf[q].get("capitalExpenditures"))
                fcf_qs.append((q, f)); cfo_qs.append((q, c)); cx_qs.append((q, cx))
            # try direct FCF sum
            fcf_vals = [v for _, v in fcf_qs if v is not None]
            if len(fcf_vals) == 4:
                fcf_direct_sum = sum(fcf_vals)
                # Plausibility check: compare sign/magnitude with CFO-|CapEx| fallback
                cfo_vals = [v for _, v in cfo_qs if v is not None]
                cx_vals  = [v for _, v in cx_qs  if v is not None]
                if len(cfo_vals) == 4 and len(cx_vals) == 4:
                    fallback_sum = sum(c - abs(cx) for c, cx in zip(
                        [v for _, v in cfo_qs], [v for _, v in cx_qs]))
                    # If signs differ, EODHD freeCashFlow likely has sign issue → use fallback
                    if (fcf_direct_sum > 0) != (fallback_sum > 0) and abs(fallback_sum) > 1e6:
                        return fallback_sum, sum(v for _,v in cfo_qs if v is not None), \
                               sum(v for _,v in cx_qs if v is not None), False, qs
                return fcf_direct_sum, sum(v for _,v in cfo_qs if v is not None), \
                       sum(v for _,v in cx_qs if v is not None), True, qs
            # fallback: CFO - |CapEx|
            fallback = []
            for i, q in enumerate(qs):
                c  = cfo_qs[i][1]; cx = cx_qs[i][1]
                if c is not None and cx is not None: fallback.append(c - abs(cx))
            if len(fallback) == 4:
                return sum(fallback), sum(v for _,v in cfo_qs if v is not None), \
                       sum(v for _,v in cx_qs if v is not None), False, qs
            return None, None, None, False, qs
        else:
            y   = yr or (years_cf[0] if years_cf else None)
            if not y: return None, None, None, False, []
            cf  = a_cf.get(y, {})
            fcf = fv(cf.get("freeCashFlow"))
            cfo = fv(cf.get("totalCashFromOperatingActivities"))
            cx  = fv(cf.get("capitalExpenditures"))
            if fcf is not None:
                # Plausibility check: if CFO and CapEx available, verify sign consistency
                if cfo is not None and cx is not None:
                    fallback = cfo - abs(cx)
                    if (fcf > 0) != (fallback > 0) and abs(fallback) > 1e6:
                        return fallback, cfo, cx, False, [y]
                return fcf, cfo, cx, True, [y]
            if cfo is not None and cx is not None:
                return cfo - abs(cx), cfo, cx, False, [y]
            return None, cfo, cx, False, [y]

    mcap   = fv(hl.get("MarketCapitalization"))
    shares = fv(hl.get("SharesOutstanding")) or (fv(q_bs[qbs_s[0]].get("commonStockSharesOutstanding")) if qbs_s else None)
    ev     = fv(val.get("EnterpriseValue"))
    bsQ    = q_bs.get(qbs_s[0], {}) if qbs_s else {}
    bsQ_dt = qbs_s[0] if qbs_s else "—"
    bsA    = a_bs.get(years_bs[0], {}) if years_bs else {}
    bsA_dt = years_bs[0] if years_bs else "—"
    isA    = a_is.get(years[0], {}) if years else {}
    isA_dt = years[0] if years else "—"
    cfA    = a_cf.get(years_cf[0], {}) if years_cf else {}
    cfA_dt = years_cf[0] if years_cf else "—"

    # ── TTM values with quarter breakdown ─────────────────────────────
    rev_ttm    = ttm(q_is, "totalRevenue")
    ni_ttm     = ttm(q_is, "netIncome")
    ebit_ttm   = ttm(q_is, "ebit")
    ebitda_ttm = ttm(q_is, "ebitda")
    gp_ttm     = ttm(q_is, "grossProfit")
    oi_ttm     = ttm(q_is, "operatingIncome")
    cfo_ttm    = ttm(q_cf, "totalCashFromOperatingActivities")
    int_ttm    = ttm(q_is, "interestExpense")
    fcf_ttm, fcf_ttm_cfo, fcf_ttm_cx, fcf_ttm_direct, fcf_ttm_qs = get_fcf_detail(True)

    # ── Annual values ─────────────────────────────────────────────────
    rev_a    = fv(isA.get("totalRevenue"))
    ni_a     = fv(isA.get("netIncome"))
    ebit_a   = fv(isA.get("ebit"))
    ebitda_a = fv(isA.get("ebitda"))
    gp_a     = fv(isA.get("grossProfit"))
    oi_a     = fv(isA.get("operatingIncome"))
    int_a    = fv(isA.get("interestExpense"))
    fcf_a, fcf_a_cfo, fcf_a_cx, fcf_a_direct, _ = get_fcf_detail(False)

    # ── BS quarterly ──────────────────────────────────────────────────
    cash_q = (fv(bsQ.get("cash")) or fv(bsQ.get("cashAndEquivalents")) or 0) + (fv(bsQ.get("shortTermInvestments")) or 0)
    ltd_q  = fv(bsQ.get("longTermDebt")) or 0
    std_q  = fv(bsQ.get("shortLongTermDebt")) or 0
    debt_q = ltd_q + std_q
    eq_q   = fv(bsQ.get("totalStockholderEquity"))
    ta_q   = fv(bsQ.get("totalAssets"))
    ca_q   = fv(bsQ.get("totalCurrentAssets"))
    cl_q   = fv(bsQ.get("totalCurrentLiabilities"))
    tl_q   = fv(bsQ.get("totalLiab"))
    inv_q  = fv(bsQ.get("inventory")) or 0
    re_q   = fv(bsQ.get("retainedEarnings"))
    sh_q   = fv(bsQ.get("commonStockSharesOutstanding"))

    # ── BS annual ─────────────────────────────────────────────────────
    cash_a = (fv(bsA.get("cash")) or fv(bsA.get("cashAndEquivalents")) or 0) + (fv(bsA.get("shortTermInvestments")) or 0)
    ltd_a  = fv(bsA.get("longTermDebt")) or 0
    std_a  = fv(bsA.get("shortLongTermDebt")) or 0
    debt_a = ltd_a + std_a
    eq_a   = fv(bsA.get("totalStockholderEquity"))
    ta_a   = fv(bsA.get("totalAssets"))
    ca_a   = fv(bsA.get("totalCurrentAssets"))
    cl_a   = fv(bsA.get("totalCurrentLiabilities"))
    tl_a   = fv(bsA.get("totalLiab"))
    inv_a  = fv(bsA.get("inventory")) or 0
    sh_a   = fv(bsA.get("commonStockSharesOutstanding"))

    # ── Prior-year BS (for averages) ──────────────────────────────────
    bsA1   = a_bs.get(years_bs[1], {}) if len(years_bs) > 1 else {}
    bsA1_dt= years_bs[1] if len(years_bs) > 1 else "—"
    eq_a1  = fv(bsA1.get("totalStockholderEquity"))
    ta_a1  = fv(bsA1.get("totalAssets"))
    eq_avg = (eq_a + eq_a1) / 2 if eq_a and eq_a1 else eq_a
    ta_avg = (ta_a + ta_a1) / 2 if ta_a and ta_a1 else ta_a

    nd_q  = debt_q - (cash_q or 0)
    nd_a  = debt_a - (cash_a or 0)
    ic_ttm = (eq_q or 0) + debt_q
    ic_a   = (eq_a or 0) + debt_a
    ce_ttm = (ta_q - cl_q) if ta_q and cl_q else None
    ce_a   = (ta_a - cl_a) if ta_a and cl_a else None

    UNKNOWN = {"formula": "—", "fields": [], "components": [], "result": "—", "unit": ""}
    L = label

    # ═══════════════════════════════════════════════════════════════════
    # VALUE
    # ═══════════════════════════════════════════════════════════════════
    if "P/Earnings" in L or "P/E" in L:
        if "Fwd" in L:
            fwd_pe_raw = fv(val.get("ForwardPE"))
            return {
                "formula": "Valuation.ForwardPE — direct EODHD API field (analyst consensus)",
                "fields":  ["Valuation.ForwardPE"],
                "unit": "x",
                "components": [
                    ("API field",                   "Valuation.ForwardPE"),
                    ("Raw value",                   num(fwd_pe_raw, 4)),
                    ("── Result ──",                ""),
                    ("P/E (Fwd)",                   num(fwd_pe_raw, 4) + " x"),
                ],
                "result": num(fwd_pe_raw, 2)}

        is_ttm = "TTM" in L or "Cur" in L
        ni  = ni_ttm if is_ttm else ni_a
        dt  = f"TTM ({qis_s[0][:7]}\u2026{qis_s[3][:7]})" if is_ttm else isA_dt
        pe  = safe(mcap, ni)

        if "Cur" in L:
            # P/E (Cur): MCap/NI_common_TTM → MCap/NI_TTM → TrailingPE → PERatio
            _q_is_dd    = data["Financials"]["Income_Statement"].get("quarterly", {})
            _qs_dd      = sorted(_q_is_dd.keys(), reverse=True)
            _nicom_dd   = [fv(_q_is_dd[q].get("netIncomeApplicableToCommonShares")) for q in _qs_dd[:4]]
            _ni_dd      = [fv(_q_is_dd[q].get("netIncome")) for q in _qs_dd[:4]]
            ni_common_ttm_dd = sum(_nicom_dd) if len(_nicom_dd)==4 and all(v is not None for v in _nicom_dd) else None
            ni_ttm_dd        = sum(_ni_dd)    if len(_ni_dd)==4    and all(v is not None for v in _ni_dd)    else None
            trailing    = fv(val.get("TrailingPE"))
            pe_ratio    = fv(hl.get("PERatio"))
            pe_common   = (mcap / ni_common_ttm_dd) if mcap and ni_common_ttm_dd and ni_common_ttm_dd > 0 else None
            pe_ni_ttm   = (mcap / ni_ttm_dd)        if mcap and ni_ttm_dd        and ni_ttm_dd        > 0 else None
            pe_cur_used = pe_common or pe_ni_ttm or trailing or pe_ratio
            if pe_common:
                source_label = "MCap / NI_common_TTM  (primary)"
                source_val   = pe_common
            elif pe_ni_ttm:
                source_label = "MCap / NI_TTM  (fallback 1 — NI_common not available)"
                source_val   = pe_ni_ttm
            elif trailing:
                source_label = "Valuation.TrailingPE  (fallback 2 — TTM NI not available)"
                source_val   = trailing
            elif pe_ratio:
                source_label = "Highlights.PERatio  (fallback 3)"
                source_val   = pe_ratio
            else:
                source_label = "— (no data available)"
                source_val   = None
            return {
                "formula": (
                    "MCap / netIncomeApplicableToCommonShares_TTM  [primary]\n"
                    "MCap / netIncome_TTM                          [fallback 1]\n"
                    "Valuation.TrailingPE                          [fallback 2]\n"
                    "Highlights.PERatio                            [fallback 3]"
                ),
                "fields":  ["Highlights.MarketCapitalization",
                            "Income_Statement.netIncomeApplicableToCommonShares (quarterly TTM — primary)",
                            "Income_Statement.netIncome (quarterly TTM — fallback 1)",
                            "Valuation.TrailingPE (fallback 2)",
                            "Highlights.PERatio (fallback 3)",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
                "unit": "x",
                "components": [
                    ("── Self-Calculated ──",              ""),
                    ("Market Cap  [Highlights.MarketCapitalization]", raw(mcap)),
                    ("NI_common_TTM  [netIncomeApplicableToCommonShares]", raw(ni_common_ttm_dd) if ni_common_ttm_dd else "— (not available)"),
                    ("MCap / NI_common_TTM",           num(pe_common, 4) + " x" if pe_common else "—"),
                    ("NI_TTM  [netIncome]",            raw(ni_ttm_dd) if ni_ttm_dd else "— (not available)"),
                    ("MCap / NI_TTM",                  num(pe_ni_ttm, 4) + " x" if pe_ni_ttm else "—"),
                    ("── API Values ──",                  ""),
                    ("Valuation.TrailingPE",           num(trailing, 4) if trailing else "— (not available)"),
                    ("Highlights.PERatio",             num(pe_ratio, 4) if pe_ratio else "— (not available)"),
                    ("── Source used ──",                 ""),
                    (source_label,                     num(source_val, 4) + " x" if source_val else "—"),
                    ("── Result ──",                      ""),
                    ("P/E (Cur)",                      num(pe_cur_used, 4) + " x" if pe_cur_used else "—"),
                ],
                "result": num(pe_cur_used, 2) if pe_cur_used else "—"}


        ni_comps = ttm_rows(q_is, "netIncome", "Income_Statement.netIncome") if is_ttm else \
                   [(f"Income_Statement.netIncome  [{isA_dt}]", raw(ni))]
        return {
            "formula": "Market Cap ÷ Net Income",
            "fields":  ["Highlights.MarketCapitalization",
                        "Income_Statement.netIncome (quarterly TTM sum)" if is_ttm else "Income_Statement.netIncome (annual)",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
            "unit": "x",
            "components": [
                ("Market Cap  [Highlights.MarketCapitalization]", raw(mcap)),
                (f"── Net Income {'TTM quarters' if is_ttm else dt} ──", ""),
                *ni_comps,
                ("── Calculation ──",                             ""),
                (f"Market Cap ÷ Net Income",                      f"{raw(mcap)} ÷ {raw(ni)}"),
                ("── Result ──",                                  ""),
                ("P/E",                                           num(pe, 4) + " x"),
            ],
            "result": num(pe, 2)}

    if "P/Sales" in L:
        is_ttm = "TTM" in L or "Cur" in L
        rev = rev_ttm if is_ttm else rev_a
        dt  = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        ps_self = safe(mcap, rev)
        rev_comps = ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue") if is_ttm else \
                    [(f"Income_Statement.totalRevenue  [{isA_dt}]", raw(rev))]
        if "Fwd" in L:
            _tr_ps   = data.get("Earnings", {}).get("Trend", {})
            _p1y_ps  = next((v for v in _tr_ps.values() if v.get("period") == "+1y"), {})
            _rgr     = fv(_p1y_ps.get("revenueEstimateGrowth"))
            _rev_ttm_fwd = rev_ttm  # already computed
            _fwd_rev = (_rev_ttm_fwd * (1 + _rgr)) if _rgr is not None and _rev_ttm_fwd else None
            _ps_fwd  = (mcap / _fwd_rev) if mcap and _fwd_rev and _fwd_rev > 0 else None
            return {
                "formula": (
                    "MCap / Forward Revenue (estimated)\n"
                    "Forward Revenue = Revenue_TTM × (1 + revenueEstimateGrowth)\n"
                    "⚠ Estimate only — EODHD has no direct Forward Revenue field"
                ),
                "fields":  ["Highlights.MarketCapitalization",
                            "Income_Statement.totalRevenue (quarterly TTM)",
                            "Earnings.Trend[+1y].revenueEstimateGrowth",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
                "unit": "x",
                "components": [
                    ("Market Cap  [Highlights.MarketCapitalization]", raw(mcap)),
                    ("── Forward Revenue Estimate ──", ""),
                    ("Revenue_TTM  [Income_Statement]",              raw(_rev_ttm_fwd)),
                    ("revenueEstimateGrowth (+1y)  [raw decimal]",   f"{_rgr:.6f}" if _rgr is not None else "— (not available)"),
                    ("  → as percentage",                          f"{_rgr*100:.2f} %" if _rgr is not None else "—"),
                    ("Forward Revenue = TTM × (1 + growth)",       raw(_fwd_rev) if _fwd_rev else "—"),
                    ("── Calculation ──",               ""),
                    ("MCap / Forward Revenue",                      f"{raw(mcap)} / {raw(_fwd_rev)}" if _fwd_rev else "—"),
                    ("── Result ──",                    ""),
                    ("P/S (Fwd)  ⚠ estimate",                     num(_ps_fwd, 4) + " x" if _ps_fwd else "—"),
                ],
                "result": num(_ps_fwd, 2) if _ps_fwd else "—"}

        if "Cur" in L:
            ps_api  = fv(val.get("PriceSalesTTM"))
            ps_used = ps_self or ps_api
            if ps_self:
                src_lbl = "MCap / Revenue_TTM  (primary — self-calculated)"
                src_val = ps_self
            elif ps_api:
                src_lbl = "Valuation.PriceSalesTTM  (fallback — Revenue TTM not available)"
                src_val = ps_api
            else:
                src_lbl = "\u2014 (no data available)"
                src_val = None
            return {
                "formula": (
                    "Primary: MCap / Revenue_TTM (self-calculated)\n"
                    "Fallback: Valuation.PriceSalesTTM"
                ),
                "fields":  ["Highlights.MarketCapitalization",
                            "Income_Statement.totalRevenue (quarterly TTM \u2014 primary)",
                            "Valuation.PriceSalesTTM (fallback)",
                            "\u2139 Market Cap / Price sourced from Finqube DB"],
                "unit": "x",
                "components": [
                    ("\u2500\u2500 Self-Calculated \u2500\u2500",              ""),
                    ("Market Cap  [Highlights.MarketCapitalization]", raw(mcap)),
                    *rev_comps,
                    ("MCap / Revenue_TTM",                         num(ps_self, 4) + " x" if ps_self else "\u2014 (not available)"),
                    ("\u2500\u2500 API Value \u2500\u2500",                    ""),
                    ("Valuation.PriceSalesTTM",                    num(ps_api, 4) if ps_api else "\u2014 (not available)"),
                    ("\u2500\u2500 Source used \u2500\u2500",                  ""),
                    (src_lbl,                                      num(src_val, 4) + " x" if src_val else "\u2014"),
                    ("\u2500\u2500 Result \u2500\u2500",                       ""),
                    ("P/S (Cur)",                                  num(ps_used, 4) + " x" if ps_used else "\u2014"),
                ],
                "result": num(ps_used, 2) if ps_used else "\u2014"}
        ps = ps_self
        return {
            "formula": "Market Cap / Revenue",
            "fields":  ["Highlights.MarketCapitalization",
                        "Income_Statement.totalRevenue",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
            "unit": "x",
            "components": [
                ("Market Cap  [Highlights.MarketCapitalization]", raw(mcap)),
                (f"-- Revenue {dt} --", ""),
                *rev_comps,
                ("-- Calculation --",              ""),
                ("Market Cap / Revenue",           f"{raw(mcap)} / {raw(rev)}"),
                ("-- Result --",                   ""),
                ("P/S",                            num(ps, 4) + " x"),
            ],
            "result": num(ps, 2)}

    if "P/Book" in L:
        is_q = "Cur" in L or "Quarterly" in L
        eq   = eq_q if is_q else eq_a
        dt   = bsQ_dt if is_q else bsA_dt
        pb_self = safe(mcap, eq)

        if "Cur" in L:
            price_book_mrq = fv(val.get("PriceBookMRQ"))
            pb_used = price_book_mrq or pb_self
            if price_book_mrq:
                src_lbl = "Valuation.PriceBookMRQ  (primary)"
                src_val = price_book_mrq
            else:
                src_lbl = "self-calculated: MarketCap / Equity_Q  (fallback - PriceBookMRQ missing)"
                src_val = pb_self
            return {
                "formula": "Primary: Valuation.PriceBookMRQ\nFallback: MarketCap / totalStockholderEquity (latest quarter)",
                "fields":  ["Valuation.PriceBookMRQ",
                            "Highlights.MarketCapitalization",
                            "Balance_Sheet.totalStockholderEquity",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
                "unit": "x",
                "components": [
                    ("Valuation.PriceBookMRQ",                         num(price_book_mrq, 4) if price_book_mrq else "- (not available)"),
                    ("-- Source used --",                               ""),
                    (src_lbl,                                           num(src_val, 4) + " x"),
                    ("-- Self-calc cross-check --",                     ""),
                    ("Market Cap  [Highlights.MarketCapitalization]",   raw(mcap)),
                    (f"Equity  [Balance_Sheet {bsQ_dt}]",              raw(eq_q)),
                    ("MarketCap / Equity_Q",                            num(pb_self, 4) + " x"),
                    ("-- Result --",                                    ""),
                    ("P/B (Cur)",                                       num(pb_used, 4) + " x"),
                ],
                "result": num(pb_used, 2)}

        pb = pb_self
        return {
            "formula": "Market Cap / Stockholder Equity  (annual)",
            "fields":  ["Highlights.MarketCapitalization",
                        "Balance_Sheet.totalStockholderEquity",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
            "unit": "x",
            "components": [
                ("Market Cap  [Highlights.MarketCapitalization]",      bn(mcap)),
                (f"Stockholder Equity  [Balance_Sheet {dt}]",          bn(eq)),
                ("-- Calculation --",                                   ""),
                ("Market Cap / Equity",                                 f"{bn(mcap)} / {bn(eq)}"),
                ("-- Result --",                                        ""),
                ("P/B",                                                 num(pb, 4) + " x"),
            ],
            "result": num(pb, 2)}

    if "P/FCF" in L:
        is_ttm = "TTM" in L or "Cur" in L
        fcf    = fcf_ttm    if is_ttm else fcf_a
        cfo    = fcf_ttm_cfo if is_ttm else fcf_a_cfo
        cx     = fcf_ttm_cx  if is_ttm else fcf_a_cx
        direct = fcf_ttm_direct if is_ttm else fcf_a_direct
        dt     = f"TTM ({qcf_s[0][:7]}…{qcf_s[3][:7]})" if is_ttm else cfA_dt
        pf     = safe(mcap, fcf)
        comps  = [("Market Cap  [Highlights.MarketCapitalization]", raw(mcap))]
        if is_ttm:
            qs_used = sorted(q_cf.keys(), reverse=True)[:4]
            if direct:
                comps.append((f"── FCF quarters (freeCashFlow) ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.freeCashFlow  [{q}]", raw(fv(q_cf[q].get("freeCashFlow")))))
                comps.append((f"  → FCF TTM Sum", raw(fcf)))
            else:
                comps.append((f"── CFO quarters (freeCashFlow was null → fallback) ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.totalCashFromOperatingActivities  [{q}]", raw(fv(q_cf[q].get("totalCashFromOperatingActivities")))))
                comps.append((f"  → CFO TTM Sum", raw(cfo)))
                comps.append((f"── CapEx quarters ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.capitalExpenditures  [{q}]", raw(fv(q_cf[q].get("capitalExpenditures")))))
                comps.append((f"  → CapEx TTM Sum", raw(cx)))
                comps.append((f"  FCF = CFO − |CapEx| = {raw(cfo)} − |{raw(cx)}|", raw(fcf)))
        else:
            if direct:
                comps += [(f"Cash_Flow.freeCashFlow  [{cfA_dt}]", raw(fcf))]
            else:
                comps += [
                    (f"Cash_Flow.totalCashFromOperatingActivities  [{cfA_dt}]", raw(cfo)),
                    (f"Cash_Flow.capitalExpenditures  [{cfA_dt}]",              raw(cx)),
                    (f"FCF = CFO − |CapEx| (fallback)",                         raw(fcf)),
                ]
        comps += [
            ("── Calculation ──",                                    ""),
            ("Market Cap ÷ FCF",                                     f"{raw(mcap)} ÷ {raw(fcf)}"),
            ("── Result ──",                                         ""),
            ("P/FCF",                                                num(pf, 4) + " x"),
        ]
        return {
            "formula": "Market Cap ÷ Free Cash Flow\n(FCF = Cash_Flow.freeCashFlow; fallback: CFO − |CapEx|)",
            "fields":  ["Highlights.MarketCapitalization",
                        "Cash_Flow.freeCashFlow",
                        "Cash_Flow.totalCashFromOperatingActivities (fallback numerator)",
                        "Cash_Flow.capitalExpenditures (fallback subtractor)",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
            "unit": "x",
            "components": comps,
            "result": num(pf, 2)}

    if "EV/Revenue" in L:
        is_ttm = "Cur" in L or "TTM" in L
        rev    = rev_ttm if is_ttm else rev_a
        dt     = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        # EV breakdown
        ev_raw = fv(val.get("EnterpriseValue"))
        r      = safe(ev, rev)
        rev_comps = ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue") if is_ttm else                     [(f"Income_Statement.totalRevenue  [{isA_dt}]", raw(rev))]
        return {
            "formula": "Enterprise Value ÷ Revenue\n(EV = Valuation.EnterpriseValue; if null → MCap + Debt − Cash)",
            "fields":  ["Valuation.EnterpriseValue", "Income_Statement.totalRevenue",
                            "ℹ Enterprise Value uses MCap from Finqube DB"],
            "unit": "x",
            "components": [
                ("EV  [Valuation.EnterpriseValue]",                 raw(ev_raw)),
                (f"── Revenue {'TTM quarters' if is_ttm else dt} ──", ""),
                *rev_comps,
                ("── Calculation ──",                                ""),
                ("EV ÷ Revenue",                                    f"{raw(ev)} ÷ {raw(rev)}"),
                ("── Result ──",                                     ""),
                ("EV/Revenue",                                      num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "EV/EBIT" in L and "EBITDA" not in L:
        is_ttm = "Cur" in L or "TTM" in L
        ebit   = ebit_ttm if is_ttm else ebit_a
        dt     = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        r      = safe(ev, ebit)
        ebit_comps = ttm_rows(q_is, "ebit", "Income_Statement.ebit") if is_ttm else                      [(f"Income_Statement.ebit  [{isA_dt}]", raw(ebit))]
        return {
            "formula": "Enterprise Value ÷ EBIT",
            "fields":  ["Valuation.EnterpriseValue", "Income_Statement.ebit",
                            "ℹ Enterprise Value uses MCap from Finqube DB"],
            "unit": "x",
            "components": [
                ("EV  [Valuation.EnterpriseValue]",                  raw(ev)),
                (f"── EBIT {'TTM quarters' if is_ttm else dt} ──",  ""),
                *ebit_comps,
                ("── Calculation ──",                                 ""),
                ("EV ÷ EBIT",                                       f"{raw(ev)} ÷ {raw(ebit)}"),
                ("── Result ──",                                      ""),
                ("EV/EBIT",                                         num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "EV/EBITDA" in L:
        is_ttm = "Cur" in L or "TTM" in L
        ebitda = ebitda_ttm if is_ttm else ebitda_a
        dt     = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        r      = safe(ev, ebitda)
        ebitda_comps = ttm_rows(q_is, "ebitda", "Income_Statement.ebitda") if is_ttm else                        [(f"Income_Statement.ebitda  [{isA_dt}]", raw(ebitda))]
        return {
            "formula": "Enterprise Value ÷ EBITDA",
            "fields":  ["Valuation.EnterpriseValue", "Income_Statement.ebitda",
                            "ℹ Enterprise Value uses MCap from Finqube DB"],
            "unit": "x",
            "components": [
                ("EV  [Valuation.EnterpriseValue]",                    raw(ev)),
                (f"── EBITDA {'TTM quarters' if is_ttm else dt} ──",  ""),
                *ebitda_comps,
                ("── Calculation ──",                                   ""),
                ("EV ÷ EBITDA",                                       f"{raw(ev)} ÷ {raw(ebitda)}"),
                ("── Result ──",                                        ""),
                ("EV/EBITDA",                                         num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Earnings Yield" in L:
        is_ttm = "Cur" in L or "TTM" in L
        ni  = ni_ttm if is_ttm else ni_a
        dt  = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        r   = safe(ni, mcap)
        ni_comps = ttm_rows(q_is, "netIncome", "Income_Statement.netIncome") if is_ttm else                    [(f"Income_Statement.netIncome  [{isA_dt}]", raw(ni))]
        return {
            "formula": "Net Income ÷ Market Cap × 100  (inverse of P/E)",
            "fields":  ["Income_Statement.netIncome", "Highlights.MarketCapitalization",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
            "unit": "%",
            "components": [
                (f"── Net Income {'TTM quarters' if is_ttm else dt} ──", ""),
                *ni_comps,
                ("Market Cap  [Highlights.MarketCapitalization]",        raw(mcap)),
                ("── Calculation ──",                                     ""),
                ("Net Income ÷ Market Cap × 100",                       f"{raw(ni)} ÷ {raw(mcap)}"),
                ("── Result ──",                                          ""),
                ("Earnings Yield",                                        pct(r)),
            ],
            "result": pct(r)}

    if "FCF Yield" in L:
        is_ttm = "TTM" in L or "Cur" in L
        fcf    = fcf_ttm if is_ttm else fcf_a
        direct = fcf_ttm_direct if is_ttm else fcf_a_direct
        cfo    = fcf_ttm_cfo if is_ttm else fcf_a_cfo
        cx     = fcf_ttm_cx  if is_ttm else fcf_a_cx
        dt     = f"TTM ({qcf_s[0][:7]}…{qcf_s[3][:7]})" if is_ttm else cfA_dt
        r      = safe(fcf, mcap)
        comps  = []
        if is_ttm:
            qs_used = sorted(q_cf.keys(), reverse=True)[:4]
            if direct:
                comps.append((f"── FCF quarters (freeCashFlow) ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.freeCashFlow  [{q}]", raw(fv(q_cf[q].get("freeCashFlow")))))
                comps.append(("  → FCF TTM Sum", raw(fcf)))
            else:
                comps.append(("── CFO quarters (freeCashFlow null → fallback) ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.totalCashFromOperatingActivities  [{q}]", raw(fv(q_cf[q].get("totalCashFromOperatingActivities")))))
                comps.append(("  → CFO TTM Sum", raw(cfo)))
                comps.append(("── CapEx quarters ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.capitalExpenditures  [{q}]", raw(fv(q_cf[q].get("capitalExpenditures")))))
                comps.append(("  → CapEx TTM Sum", raw(cx)))
                comps.append((f"  FCF = CFO − |CapEx| = {raw(cfo)} − |{raw(cx)}|", raw(fcf)))
        else:
            if direct:
                comps.append((f"Cash_Flow.freeCashFlow  [{cfA_dt}]", raw(fcf)))
            else:
                comps += [
                    (f"Cash_Flow.totalCashFromOperatingActivities  [{cfA_dt}]", raw(cfo)),
                    (f"Cash_Flow.capitalExpenditures  [{cfA_dt}]",              raw(cx)),
                    (f"FCF = CFO − |CapEx| (fallback)",                         raw(fcf)),
                ]
        comps += [
            ("Market Cap  [Highlights.MarketCapitalization]",               raw(mcap)),
            ("── Calculation ──",                                            ""),
            ("FCF ÷ Market Cap × 100",                                      f"{raw(fcf)} ÷ {raw(mcap)}"),
            ("── Result ──",                                                 ""),
            ("FCF Yield",                                                    pct(r)),
        ]
        return {
            "formula": "Free Cash Flow ÷ Market Cap × 100",
            "fields":  ["Cash_Flow.freeCashFlow (fallback: CFO − |CapEx|)",
                        "Highlights.MarketCapitalization",
                            "ℹ Market Cap / Price sourced from Finqube DB"],
            "unit": "%", "components": comps, "result": pct(r)}

    if "PEG" in L:
        y0 = years[0] if years else "-"
        y1 = years[1] if len(years) > 1 else "-"

        if "Fwd" in L:
            pe_used    = fv(val.get("ForwardPE"))
            trends_dd  = data.get("Earnings", {}).get("Trend", {})
            p1y_dd     = next((v for v in trends_dd.values() if v.get("period") == "+1y"), {})
            gr_raw     = fv(p1y_dd.get("earningsEstimateGrowth"))
            gr_fwd_pct = gr_raw * 100 if gr_raw is not None else None
            # Fallback 1: TTM EPS growth (NI/shares based)
            _q_is_fb   = data["Financials"]["Income_Statement"].get("quarterly", {})
            _q_bs_fb   = data["Financials"]["Balance_Sheet"].get("quarterly", {})
            _qs_fb     = sorted(_q_is_fb.keys(), reverse=True)
            _qbs_fb    = sorted(_q_bs_fb.keys(), reverse=True)
            def _ni_eps_ttm(start):
                vals = []
                for q in _qs_fb[start:start+4]:
                    v = fv(_q_is_fb[q].get("netIncomeApplicableToCommonShares")) or fv(_q_is_fb[q].get("netIncome"))
                    if v is not None: vals.append(v)
                return sum(vals) if len(vals) == 4 else None
            _ni_now    = _ni_eps_ttm(0)
            _ni_1yago  = _ni_eps_ttm(4)
            _shs_q0    = fv(_q_bs_fb[_qbs_fb[0]].get("commonStockSharesOutstanding")) if _qbs_fb else None
            _shs_q4    = fv(_q_bs_fb[_qbs_fb[4]].get("commonStockSharesOutstanding")) if len(_qbs_fb) > 4 else None
            _eps_now   = (_ni_now   / _shs_q0) if _ni_now   and _shs_q0 and _shs_q0 > 0 else None
            _eps_1yago = (_ni_1yago / _shs_q4) if _ni_1yago and _shs_q4 and _shs_q4 > 0 else None
            gr_ttm_fb  = ((_eps_now / _eps_1yago - 1) * 100) if _eps_now and _eps_1yago and _eps_1yago > 0 else None
            # Fallback 2: YoY EPS growth (annual NI/shares)
            _a_bs_fb2  = data["Financials"]["Balance_Sheet"].get("yearly", {})
            _a_is_fb2  = data["Financials"]["Income_Statement"].get("yearly", {})
            _ys_fb2    = sorted(_a_is_fb2.keys(), reverse=True)
            def _eps_ann(idx):
                if idx >= len(_ys_fb2): return None
                y   = _ys_fb2[idx]
                ni  = fv(_a_is_fb2[y].get("netIncomeApplicableToCommonShares")) or fv(_a_is_fb2[y].get("netIncome"))
                shs = fv(_a_bs_fb2.get(y, {}).get("commonStockSharesOutstanding"))
                return (ni / shs) if ni and shs and shs > 0 else None
            _ea0 = _eps_ann(0); _ea1 = _eps_ann(1)
            gr_yoy_fb  = ((_ea0 / _ea1 - 1) * 100) if _ea0 and _ea1 and _ea1 > 0 else None
            # Select source
            if gr_fwd_pct and gr_fwd_pct > 0:
                gr_used = gr_fwd_pct
                src     = "Earnings.Trend[+1y].earningsEstimateGrowth  (primary, forward-looking)"
                src_key = "primary"
            elif gr_ttm_fb and gr_ttm_fb > 0:
                gr_used = gr_ttm_fb
                src     = "EPS Growth TTM  (fallback 1 - estimate missing/negative)"
                src_key = "ttm"
            elif gr_yoy_fb and gr_yoy_fb > 0:
                gr_used = gr_yoy_fb
                src     = "EPS Growth YoY  (fallback 2 - TTM also unavailable)"
                src_key = "yoy"
            else:
                gr_used = None
                src     = "- (no growth data available)"
                src_key = "none"
            peg = (pe_used / gr_used) if pe_used and gr_used and gr_used > 0 else None
            return {
                "formula": (
                    "ForwardPE / EPS Growth (%)\n"
                    "Numerator:   Valuation.ForwardPE\n"
                    "Denominator [priority chain]:\n"
                    "  1. Earnings.Trend[+1y].earningsEstimateGrowth  (forward-looking, analyst consensus)\n"
                    "  2. EPS Growth TTM  (NI_TTM/shares, fallback 1)\n"
                    "  3. EPS Growth YoY  (NI_annual/shares, fallback 2)\n"
                    "N/A when growth <= 0"
                ),
                "fields":  ["Valuation.ForwardPE",
                            "Earnings.Trend[+1y].earningsEstimateGrowth",
                            "EPS Growth TTM / YoY  (fallback only)"],
                "unit": "x",
                "components": [
                    ("── P/E Numerator ──",                                              ""),
                    ("Valuation.ForwardPE",                                                num(pe_used, 4) if pe_used else "— (not available)"),
                    ("── EPS Growth Denominator ──",                                      ""),
                    ("1. earningsEstimateGrowth (+1y)  [raw decimal]",                    f"{gr_raw:.6f}" if gr_raw is not None else "—"),
                    ("   -> as percentage",                                                f"{gr_fwd_pct:.4f} %" if gr_fwd_pct is not None else "—"),
                    ("2. EPS Growth TTM  [fallback 1]",                                   f"{gr_ttm_fb:.4f} %" if gr_ttm_fb is not None else "—"),
                    ("3. EPS Growth YoY  [fallback 2]",                                   f"{gr_yoy_fb:.4f} %" if gr_yoy_fb is not None else "—"),
                    ("── Source used ──",                                                 ""),
                    (src,                                                                  f"{gr_used:.4f} %" if gr_used else "—"),
                    ("── Calculation ──",                                                  ""),
                    ("ForwardPE / EPS Growth %",                                          f"{num(pe_used,4)} / {gr_used:.4f}" if gr_used else "N/A"),
                    ("── Result ──",                                                       ""),
                    ("PEG Ratio (Fwd)",                                                    num(peg, 4) + " x" if peg else "—"),
                ],
                "result": num(peg, 2) if peg else "—"}

        # PEG (Cur) / PEG (Year): historical EPS growth = NI/shares YoY
        a_bs_dd = data["Financials"]["Balance_Sheet"].get("yearly", {})
        def _eps_peg_dd(idx):
            if idx >= len(years): return None
            y   = years[idx]
            ni  = fv(a_is.get(y, {}).get("netIncomeApplicableToCommonShares")) or fv(a_is.get(y, {}).get("netIncome"))
            shs = fv(a_bs_dd.get(y, {}).get("commonStockSharesOutstanding"))
            return (ni / shs) if ni and shs and shs > 0 else None
        eps0_dd    = _eps_peg_dd(0)
        eps1_dd    = _eps_peg_dd(1)
        ni0_dd     = fv(a_is.get(y0, {}).get("netIncomeApplicableToCommonShares")) or fv(a_is.get(y0, {}).get("netIncome"))
        ni1_dd     = fv(a_is.get(y1, {}).get("netIncomeApplicableToCommonShares")) or fv(a_is.get(y1, {}).get("netIncome"))
        shs0_dd    = fv(a_bs_dd.get(y0, {}).get("commonStockSharesOutstanding"))
        shs1_dd    = fv(a_bs_dd.get(y1, {}).get("commonStockSharesOutstanding"))
        eps_gr_pct = ((eps0_dd / eps1_dd - 1) * 100) if eps0_dd and eps1_dd and eps1_dd > 0 else None
        ni_cur_yr  = fv(a_is.get(y0, {}).get("netIncome")) if years else None

        if "Cur" in L:
            pe_used  = fv(val.get("TrailingPE")) or fv(hl.get("PERatio"))
            pe_label = "Valuation.TrailingPE  (fallback: Highlights.PERatio)"
        else:
            pe_used  = safe(mcap, ni_cur_yr)
            pe_label = f"P/E (Year) = MarketCap / NI ({y0})"

        peg = safe(pe_used, eps_gr_pct) if eps_gr_pct and eps_gr_pct > 0 else None
        gr_str  = f"{eps_gr_pct:.4f} %" if eps_gr_pct else "\u2014"
        eps0_str = f"{eps0_dd:.4f}" if eps0_dd else "?"
        eps1_str = f"{eps1_dd:.4f}" if eps1_dd else "?"
        return {
            "formula": (
                "P/E / EPS Growth Rate (%)\n"
                "Denominator: historical YoY EPS growth  (NI / commonStockSharesOutstanding)\n"
                "N/A when growth <= 0"
            ),
            "fields":  ["Valuation.TrailingPE / Highlights.PERatio / self-calc",
                        "Income_Statement.netIncomeApplicableToCommonShares (fallback: netIncome)",
                        "Balance_Sheet.commonStockSharesOutstanding"],
            "unit": "x",
            "components": [
                ("\u2500\u2500 P/E Numerator \u2500\u2500",                                          ""),
                (pe_label,                                                            num(pe_used, 4) if pe_used else "\u2014"),
                ("\u2500\u2500 EPS Growth Denominator \u2500\u2500",                                 ""),
                (f"-- EPS {y0} --",                                                  ""),
                (f"  NI  [Income_Statement {y0}]",                                  raw(ni0_dd)),
                (f"  Shares  [Balance_Sheet {y0}]",                                 raw(shs0_dd)),
                (f"  -> EPS {y0}",                                                   f"{eps0_dd:.6f}" if eps0_dd else "\u2014"),
                (f"-- EPS {y1} --",                                                  ""),
                (f"  NI  [Income_Statement {y1}]",                                  raw(ni1_dd)),
                (f"  Shares  [Balance_Sheet {y1}]",                                 raw(shs1_dd)),
                (f"  -> EPS {y1}",                                                   f"{eps1_dd:.6f}" if eps1_dd else "\u2014"),
                ("\u2500\u2500 Calculation \u2500\u2500",                                             ""),
                (f"EPS growth = ({eps0_str} / {eps1_str}) - 1 x 100",               gr_str),
                ("P/E / EPS Growth %",                                               f"{num(pe_used,4)} / {eps_gr_pct:.4f}" if eps_gr_pct else "N/A"),
                ("\u2500\u2500 Result \u2500\u2500",                                                  ""),
                ("PEG Ratio",                                                         num(peg, 4) + " x" if peg else "\u2014"),
            ],
            "result": num(peg, 2) if peg else "\u2014"}

    # ═══════════════════════════════════════════════════════════════════
    # PROFITABILITY
    # ═══════════════════════════════════════════════════════════════════
    if "Return on Assets" in L:
        is_ttm = "TTM" in L
        ni     = ni_ttm if is_ttm else ni_a
        ta     = ta_q   if is_ttm else ta_avg   # avg Y0/Y-1 for annual, latest Q for TTM
        dt_ni  = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        r      = safe(ni, ta)
        ni_comps = ttm_rows(q_is, "netIncome", "Income_Statement.netIncome") if is_ttm else \
                   [(f"Income_Statement.netIncome  [{isA_dt}]", raw(ni))]
        comps  = [
            (f"── Net Income {'TTM quarters' if is_ttm else dt_ni} ──", ""),
            *ni_comps,
        ]
        if is_ttm:
            comps.append((f"Total Assets  [Balance_Sheet.totalAssets {bsQ_dt}]  (latest Q, no avg)", raw(ta_q)))
        else:
            comps += [
                (f"Total Assets Y0  [Balance_Sheet.totalAssets {bsA_dt}]",       raw(ta_a)),
                (f"Total Assets Y-1  [Balance_Sheet.totalAssets {bsA1_dt}]",     raw(ta_a1) if ta_a1 else "— (not available)"),
                (f"Avg Assets = ({raw(ta_a)} + {raw(ta_a1 or 0)}) ÷ 2  (used)", raw(ta_avg)),
            ]
        comps += [
            ("── Calculation ──",           ""),
            (f"NI ÷ Avg Assets × 100",      f"{raw(ni)} ÷ {raw(ta)}"),
            ("── Result ──",                ""),
            ("ROA",                          pct(r)),
        ]
        return {"formula": "Net Income ÷ Total Assets × 100\n(Annual: avg of Y0 and Y-1 assets; TTM: latest quarter assets)",
                "fields": ["Income_Statement.netIncome", "Balance_Sheet.totalAssets"],
                "unit": "%", "components": comps, "result": pct(r)}

    if "Return on Equity" in L and "Cap" not in L and "Inv" not in L:
        is_ttm = "TTM" in L
        ni     = ni_ttm if is_ttm else ni_a
        eq     = eq_q   if is_ttm else eq_avg
        dt_ni  = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        r      = safe(ni, eq)
        ni_comps = ttm_rows(q_is, "netIncome", "Income_Statement.netIncome") if is_ttm else \
                   [(f"Income_Statement.netIncome  [{isA_dt}]", raw(ni))]
        comps  = [
            (f"── Net Income {'TTM quarters' if is_ttm else dt_ni} ──", ""),
            *ni_comps,
        ]
        if is_ttm:
            comps.append((f"Equity  [Balance_Sheet.totalStockholderEquity {bsQ_dt}]  (latest Q)", raw(eq_q)))
        else:
            comps += [
                (f"Equity Y0  [Balance_Sheet.totalStockholderEquity {bsA_dt}]",       raw(eq_a)),
                (f"Equity Y-1  [Balance_Sheet.totalStockholderEquity {bsA1_dt}]",     raw(eq_a1) if eq_a1 else "— (not available)"),
                (f"Avg Equity = ({raw(eq_a)} + {raw(eq_a1 or 0)}) ÷ 2  (used)",      raw(eq_avg)),
            ]
        comps += [
            ("── Calculation ──",       ""),
            ("NI ÷ Avg Equity × 100",   f"{raw(ni)} ÷ {raw(eq)}"),
            ("── Result ──",            ""),
            ("ROE",                      pct(r)),
        ]
        return {"formula": "Net Income ÷ Stockholder Equity × 100\n(Annual: avg of Y0 and Y-1 equity; TTM: latest quarter equity)",
                "fields": ["Income_Statement.netIncome", "Balance_Sheet.totalStockholderEquity"],
                "unit": "%", "components": comps, "result": pct(r)}

    if "Return on Cap. Empl" in L or "Return on Capital Empl" in L:
        is_ttm = "TTM" in L
        ebit   = ebit_ttm if is_ttm else ebit_a
        ta     = ta_q if is_ttm else ta_a
        cl     = cl_q if is_ttm else cl_a
        ce     = (ta - cl) if ta and cl else None
        dt_e   = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        dt_bs  = bsQ_dt if is_ttm else bsA_dt
        r      = safe(ebit, ce)
        return {
            "formula": "EBIT ÷ Capital Employed × 100\nCapital Employed = Total Assets − Current Liabilities",
            "fields":  ["Income_Statement.ebit", "Balance_Sheet.totalAssets", "Balance_Sheet.totalCurrentLiabilities"],
            "unit": "%",
            "components": [
                (f"── EBIT {'TTM quarters' if is_ttm else dt_e} ──",                  ""),
                *(ttm_rows(q_is, "ebit", "Income_Statement.ebit") if is_ttm else
                  [(f"Income_Statement.ebit  [{isA_dt}]", raw(ebit))]),
                (f"Total Assets  [Balance_Sheet.totalAssets {dt_bs}]",               raw(ta)),
                (f"Current Liabilities  [Balance_Sheet.totalCurrentLiabilities {dt_bs}]", raw(cl)),
                (f"Capital Employed = {raw(ta)} − {raw(cl)}",                        raw(ce)),
                ("── Calculation ──",                                                  ""),
                (f"EBIT ÷ Capital Employed × 100",                                    f"{raw(ebit)} ÷ {raw(ce)}"),
                ("── Result ──",                                                       ""),
                ("ROCE",                                                               pct(r)),
            ],
            "result": pct(r)}

    if "Return on Inv" in L or "ROIC" in L:
        is_ttm = "TTM" in L
        ni     = ni_ttm if is_ttm else ni_a
        eq     = eq_q if is_ttm else eq_a
        ltd    = ltd_q if is_ttm else ltd_a
        std    = std_q if is_ttm else std_a
        debt   = ltd + std
        ic     = ic_ttm if is_ttm else ic_a
        dt_ni  = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        dt_bs  = bsQ_dt if is_ttm else bsA_dt
        r      = safe(ni, ic)
        return {
            "formula": "Net Income ÷ Invested Capital × 100\nInvested Capital = Equity + Long-Term Debt + Short-Term Debt",
            "fields":  ["Income_Statement.netIncome", "Balance_Sheet.totalStockholderEquity",
                        "Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt"],
            "unit": "%",
            "components": [
                (f"── Net Income {'TTM quarters' if is_ttm else dt_ni} ──",             ""),
                *(ttm_rows(q_is, "netIncome", "Income_Statement.netIncome") if is_ttm else
                  [(f"Income_Statement.netIncome  [{isA_dt}]", raw(ni))]),
                (f"Equity  [Balance_Sheet.totalStockholderEquity {dt_bs}]",            raw(eq)),
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt_bs}]",              raw(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt_bs}]",        raw(std)),
                (f"Total Debt = {raw(ltd)} + {raw(std)}",                             raw(debt)),
                (f"Invested Capital = {raw(eq)} + {raw(debt)}",                       raw(ic)),
                ("── Calculation ──",                                                   ""),
                (f"NI ÷ Invested Capital × 100",                                       f"{raw(ni)} ÷ {raw(ic)}"),
                ("── Result ──",                                                        ""),
                ("ROIC",                                                                pct(r)),
            ],
            "result": pct(r)}

    if "Return on Capital" in L and "Empl" not in L:
        is_ttm = "TTM" in L
        ni     = ni_ttm if is_ttm else ni_a
        eq     = eq_q if is_ttm else eq_a
        ltd    = ltd_q if is_ttm else ltd_a
        std    = std_q if is_ttm else std_a
        debt   = ltd + std
        ic     = ic_ttm if is_ttm else ic_a
        dt_ni  = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        dt_bs  = bsQ_dt if is_ttm else bsA_dt
        r      = safe(ni, ic)
        return {
            "formula": "Net Income ÷ (Equity + Debt) × 100",
            "fields":  ["Income_Statement.netIncome", "Balance_Sheet.totalStockholderEquity",
                        "Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt"],
            "unit": "%",
            "components": [
                (f"── Net Income {'TTM quarters' if is_ttm else dt_ni} ──", ""),
                *(ttm_rows(q_is, "netIncome", "Income_Statement.netIncome") if is_ttm else
                  [(f"Income_Statement.netIncome  [{isA_dt}]", raw(ni))]),
                (f"Equity  [Balance_Sheet.totalStockholderEquity {dt_bs}]",  raw(eq)),
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt_bs}]",    raw(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt_bs}]", raw(std)),
                (f"Total Debt = {raw(ltd)} + {raw(std)}",                    raw(debt)),
                (f"Invested Capital = {raw(eq)} + {raw(debt)}",              raw(ic)),
                ("── Calculation ──",                                         ""),
                (f"NI ÷ (Eq + Debt) × 100",                                 f"{raw(ni)} ÷ {raw(ic)}"),
                ("── Result ──",                                              ""),
                ("ROC",                                                        pct(r)),
            ],
            "result": pct(r)}

    if "Gross Margin" in L:
        is_ttm = "TTM" in L
        gp  = gp_ttm if is_ttm else gp_a
        rev = rev_ttm if is_ttm else rev_a
        dt  = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        r   = safe(gp, rev)
        return {
            "formula": "Gross Profit ÷ Revenue × 100",
            "fields":  ["Income_Statement.grossProfit", "Income_Statement.totalRevenue"],
            "unit": "%",
            "components": [
                (f"── Gross Profit {'TTM quarters' if is_ttm else dt} ──", ""),
                *(ttm_rows(q_is, "grossProfit", "Income_Statement.grossProfit") if is_ttm else
                  [(f"Income_Statement.grossProfit  [{isA_dt}]", raw(gp))]),
                (f"── Revenue {'TTM quarters' if is_ttm else dt} ──",   ""),
                *(ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue") if is_ttm else
                  [(f"Income_Statement.totalRevenue  [{isA_dt}]", raw(rev))]),
                ("── Calculation ──",                                     ""),
                ("Gross Profit ÷ Revenue × 100",                        f"{raw(gp)} ÷ {raw(rev)}"),
                ("── Result ──",                                          ""),
                ("Gross Margin",                                          pct(r)),
            ],
            "result": pct(r)}

    if "Operating Margin" in L:
        is_ttm = "TTM" in L
        oi  = oi_ttm if is_ttm else oi_a
        rev = rev_ttm if is_ttm else rev_a
        dt  = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        r   = safe(oi, rev)
        return {
            "formula": "Operating Income ÷ Revenue × 100",
            "fields":  ["Income_Statement.operatingIncome", "Income_Statement.totalRevenue"],
            "unit": "%",
            "components": [
                (f"── Operating Income {'TTM quarters' if is_ttm else dt} ──", ""),
                *(ttm_rows(q_is, "operatingIncome", "Income_Statement.operatingIncome") if is_ttm else
                  [(f"Income_Statement.operatingIncome  [{isA_dt}]", raw(oi))]),
                (f"── Revenue {'TTM quarters' if is_ttm else dt} ──",          ""),
                *(ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue") if is_ttm else
                  [(f"Income_Statement.totalRevenue  [{isA_dt}]", raw(rev))]),
                ("── Calculation ──",                                            ""),
                ("Operating Income ÷ Revenue × 100",                           f"{raw(oi)} ÷ {raw(rev)}"),
                ("── Result ──",                                                 ""),
                ("Operating Margin",                                             pct(r)),
            ],
            "result": pct(r)}

    if "EBIT Margin" in L:
        is_ttm = "TTM" in L
        ebit = ebit_ttm if is_ttm else ebit_a
        rev  = rev_ttm  if is_ttm else rev_a
        dt   = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        r    = safe(ebit, rev)
        return {
            "formula": "EBIT ÷ Revenue × 100",
            "fields":  ["Income_Statement.ebit", "Income_Statement.totalRevenue"],
            "unit": "%",
            "components": [
                (f"── EBIT {'TTM quarters' if is_ttm else dt} ──", ""),
                *(ttm_rows(q_is, "ebit", "Income_Statement.ebit") if is_ttm else
                  [(f"Income_Statement.ebit  [{isA_dt}]", raw(ebit))]),
                (f"── Revenue {'TTM quarters' if is_ttm else dt} ──", ""),
                *(ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue") if is_ttm else
                  [(f"Income_Statement.totalRevenue  [{isA_dt}]", raw(rev))]),
                ("── Calculation ──",                                ""),
                ("EBIT ÷ Revenue × 100",                           f"{raw(ebit)} ÷ {raw(rev)}"),
                ("── Result ──",                                    ""),
                ("EBIT Margin",                                      pct(r)),
            ],
            "result": pct(r)}

    if "EBITDA Margin" in L:
        is_q   = "Quarterly" in L
        is_ttm = "TTM" in L
        q0     = qis_s[0] if qis_s else "—"
        ebitda = fv(q_is[q0].get("ebitda"))       if is_q else (ebitda_ttm if is_ttm else ebitda_a)
        rev    = fv(q_is[q0].get("totalRevenue")) if is_q else (rev_ttm    if is_ttm else rev_a)
        dt     = f"Q0 ({q0})" if is_q else (f"TTM ({qis_s[0][:7]}\u2026{qis_s[3][:7]})" if is_ttm else isA_dt)
        r      = safe(ebitda, rev)
        return {
            "formula": "EBITDA \u00f7 Revenue \u00d7 100",
            "fields":  ["Income_Statement.ebitda", "Income_Statement.totalRevenue"],
            "unit": "%",
            "components": [
                (f"\u2500\u2500 EBITDA {dt} \u2500\u2500", ""),
                *(ttm_rows(q_is, "ebitda", "Income_Statement.ebitda") if is_ttm else
                  [(f"Income_Statement.ebitda  [{dt}]", raw(ebitda))]),
                (f"\u2500\u2500 Revenue {dt} \u2500\u2500", ""),
                *(ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue") if is_ttm else
                  [(f"Income_Statement.totalRevenue  [{dt}]", raw(rev))]),
                ("\u2500\u2500 Calculation \u2500\u2500",        ""),
                ("EBITDA \u00f7 Revenue \u00d7 100",  f"{raw(ebitda)} \u00f7 {raw(rev)}"),
                ("\u2500\u2500 Result \u2500\u2500",             ""),
                ("EBITDA Margin",            pct(r)),
            ],
            "result": pct(r)}

    if "Net Margin" in L:
        is_q   = "Quarterly" in L
        is_ttm = "TTM" in L
        q0     = qis_s[0] if qis_s else "—"
        ni  = fv(q_is[q0].get("netIncome"))     if is_q else (ni_ttm  if is_ttm else ni_a)
        rev = fv(q_is[q0].get("totalRevenue"))  if is_q else (rev_ttm if is_ttm else rev_a)
        dt  = f"Q0 ({q0})" if is_q else (f"TTM ({qis_s[0][:7]}\u2026{qis_s[3][:7]})" if is_ttm else isA_dt)
        r   = safe(ni, rev)
        return {
            "formula": "Net Income \u00f7 Revenue \u00d7 100",
            "fields":  ["Income_Statement.netIncome", "Income_Statement.totalRevenue"],
            "unit": "%",
            "components": [
                (f"\u2500\u2500 Net Income {dt} \u2500\u2500", ""),
                *(ttm_rows(q_is, "netIncome", "Income_Statement.netIncome") if is_ttm else
                  [(f"Income_Statement.netIncome  [{dt}]", raw(ni))]),
                (f"\u2500\u2500 Revenue {dt} \u2500\u2500", ""),
                *(ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue") if is_ttm else
                  [(f"Income_Statement.totalRevenue  [{dt}]", raw(rev))]),
                ("\u2500\u2500 Calculation \u2500\u2500",           ""),
                ("Net Income \u00f7 Revenue \u00d7 100", f"{raw(ni)} \u00f7 {raw(rev)}"),
                ("\u2500\u2500 Result \u2500\u2500",                ""),
                ("Net Margin",                  pct(r)),
            ],
            "result": pct(r)}

    if "FCF Margin" in L:
        is_q   = "Quarterly" in L
        is_ttm = "TTM" in L and not is_q
        if is_q:
            q0cf = qcf_s[0] if qcf_s else None
            _fcf_q = fv(q_cf[q0cf].get("freeCashFlow")) if q0cf else None
            if _fcf_q is None and q0cf:
                _cfo   = fv(q_cf[q0cf].get("totalCashFromOperatingActivities"))
                _capex = fv(q_cf[q0cf].get("capitalExpenditures"))
                _fcf_q = _cfo - abs(_capex) if _cfo and _capex else None
            _rev_q = fv(q_is[qis_s[0]].get("totalRevenue")) if qis_s else None
            _r_q   = safe(_fcf_q, _rev_q)
            return {
                "formula": "FCF \u00f7 Revenue \u00d7 100  (single quarter Q0)\n(FCF = freeCashFlow; fallback: CFO \u2212 |CapEx|)",
                "fields":  ["Cash_Flow.freeCashFlow", "Income_Statement.totalRevenue"],
                "unit": "%",
                "components": [
                    (f"Cash_Flow.freeCashFlow  [{q0cf}]", raw(_fcf_q)),
                    (f"Income_Statement.totalRevenue  [{qis_s[0] if qis_s else '\u2014'}]", raw(_rev_q)),
                    ("\u2500\u2500 Calculation \u2500\u2500",       ""),
                    ("FCF \u00f7 Revenue \u00d7 100",    f"{raw(_fcf_q)} \u00f7 {raw(_rev_q)}"),
                    ("\u2500\u2500 Result \u2500\u2500",            ""),
                    ("FCF Margin (Quarterly)", pct(_r_q)),
                ],
                "result": pct(_r_q)}
        fcf    = fcf_ttm if is_ttm else fcf_a
        is_ttm = "TTM" in L
        fcf    = fcf_ttm if is_ttm else fcf_a
        cfo    = fcf_ttm_cfo if is_ttm else fcf_a_cfo
        cx     = fcf_ttm_cx  if is_ttm else fcf_a_cx
        direct = fcf_ttm_direct if is_ttm else fcf_a_direct
        rev    = rev_ttm if is_ttm else rev_a
        dt     = f"TTM ({qcf_s[0][:7]}…{qcf_s[3][:7]})" if is_ttm else cfA_dt
        r      = safe(fcf, rev)
        comps  = []
        if is_ttm:
            qs_used = sorted(q_cf.keys(), reverse=True)[:4]
            if direct:
                comps.append((f"── FCF quarters (freeCashFlow) ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.freeCashFlow  [{q}]", raw(fv(q_cf[q].get("freeCashFlow")))))
                comps.append(("  → FCF TTM Sum", raw(fcf)))
            else:
                comps.append((f"── CFO quarters (freeCashFlow null → fallback) ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.totalCashFromOperatingActivities  [{q}]", raw(fv(q_cf[q].get("totalCashFromOperatingActivities")))))
                comps.append(("  → CFO TTM Sum", raw(cfo)))
                comps.append((f"── CapEx quarters ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.capitalExpenditures  [{q}]", raw(fv(q_cf[q].get("capitalExpenditures")))))
                comps.append(("  → CapEx TTM Sum", raw(cx)))
                comps.append((f"  FCF = CFO − |CapEx| = {raw(cfo)} − |{raw(cx)}|", raw(fcf)))
            rev_comps = ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue")
            comps += [(f"── Revenue TTM quarters ──", ""), *rev_comps]
        else:
            if direct:
                comps.append((f"Cash_Flow.freeCashFlow  [{cfA_dt}]", raw(fcf)))
            else:
                comps += [
                    (f"Cash_Flow.totalCashFromOperatingActivities  [{cfA_dt}]", raw(cfo)),
                    (f"Cash_Flow.capitalExpenditures  [{cfA_dt}]",              raw(cx)),
                    (f"FCF = CFO − |CapEx| (fallback)",                         raw(fcf)),
                ]
            comps.append((f"Income_Statement.totalRevenue  [{isA_dt}]", raw(rev)))
        comps += [
            ("── Calculation ──",                                            ""),
            ("FCF ÷ Revenue × 100",                                        f"{raw(fcf)} ÷ {raw(rev)}"),
            ("── Result ──",                                                 ""),
            ("FCF Margin",                                                   pct(r)),
        ]
        return {
            "formula": "Free Cash Flow ÷ Revenue × 100\n(FCF = freeCashFlow; fallback: CFO − |CapEx|)",
            "fields":  ["Cash_Flow.freeCashFlow (fallback: totalCashFromOperatingActivities − |capitalExpenditures|)",
                        "Income_Statement.totalRevenue"],
            "unit": "%", "components": comps, "result": pct(r)}

    if "Asset Turnover" in L:
        is_ttm = "TTM" in L
        rev    = rev_ttm if is_ttm else rev_a
        ta     = ta_q   if is_ttm else ta_avg
        dt_rev = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm else isA_dt
        dt_bs  = bsQ_dt if is_ttm else bsA_dt
        r      = safe(rev, ta)
        rev_comps = ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue") if is_ttm else                     [(f"Income_Statement.totalRevenue  [{isA_dt}]", raw(rev))]
        comps  = [
            (f"── Revenue {'TTM quarters' if is_ttm else dt_rev} ──",  ""),
            *rev_comps,
            (f"Total Assets  [Balance_Sheet.totalAssets {dt_bs}]",     raw(ta)),
        ]
        if not is_ttm and ta_a and ta_a1:
            comps += [
                (f"Total Assets Y-1  [{bsA1_dt}]",                     raw(ta_a1)),
                (f"Avg Assets = ({raw(ta_a)} + {raw(ta_a1)}) ÷ 2",   raw(ta_avg)),
            ]
        comps += [
            ("── Calculation ──",    ""),
            ("Revenue ÷ Avg Assets", f"{raw(rev)} ÷ {raw(ta)}"),
            ("── Result ──",         ""),
            ("Asset Turnover",        num(r, 4) + " x"),
        ]
        return {"formula": "Revenue ÷ Total Assets (avg Y0/Y-1 for annual)",
                "fields": ["Income_Statement.totalRevenue", "Balance_Sheet.totalAssets"],
                "unit": "x", "components": comps, "result": num(r, 2)}

    # ═══════════════════════════════════════════════════════════════════
    # GROWTH
    # ═══════════════════════════════════════════════════════════════════
    def growth_dd(field_label, q_stmt, a_stmt, field_key, q_cf_stmt=None, cf_key=None):
        use_cf  = q_cf_stmt is not None
        stmt_q  = q_cf_stmt if use_cf else q_stmt
        stmt_a  = a_cf if use_cf else a_stmt
        api_key = cf_key if use_cf else field_key
        stmt_lbl= "Cash_Flow" if use_cf else "Income_Statement"
        is_fcf  = use_cf and cf_key == "freeCashFlow"

        def get_fcf_q(q_key):
            """For FCF: try freeCashFlow, fallback CFO − |CapEx|. Returns (value, source_label)."""
            f = fv(stmt_q[q_key].get("freeCashFlow"))
            if f is not None:
                return f, "freeCashFlow"
            cfo   = fv(stmt_q[q_key].get("totalCashFromOperatingActivities"))
            capex = fv(stmt_q[q_key].get("capitalExpenditures"))
            if cfo is not None and capex is not None:
                return cfo - abs(capex), "CFO−|CapEx|"
            return None, "—"

        def get_fcf_a(y_key):
            """For FCF annual: try freeCashFlow, fallback CFO − |CapEx|."""
            d = stmt_a.get(y_key, {})
            f = fv(d.get("freeCashFlow"))
            if f is not None:
                return f, "freeCashFlow"
            cfo   = fv(d.get("totalCashFromOperatingActivities"))
            capex = fv(d.get("capitalExpenditures"))
            if cfo is not None and capex is not None:
                return cfo - abs(capex), "CFO−|CapEx|"
            return None, "—"

        if "Ann" in L:
            ys = sorted(stmt_a.keys(), reverse=True)
            if len(ys) < 2:
                return {"formula": "V[y0] ÷ V[y1] − 1 × 100  (latest vs prior fiscal year)",
                        "fields": [f"{stmt_lbl}.{api_key} — annual"],
                        "unit": "%", "components": [("N/A", "Requires at least 2 years of data")], "result": "—"}
            y0 = ys[0]; y1 = ys[1]
            if is_fcf:
                v0, s0 = get_fcf_a(y0); v1, s1 = get_fcf_a(y1)
            else:
                v0 = fv(stmt_a[y0].get(api_key)); s0 = api_key
                v1 = fv(stmt_a[y1].get(api_key)); s1 = api_key
            if v0 is None or v1 is None:
                gr = None; gr_note = "N/A — data missing"
            elif v1 <= 0:
                gr = None; gr_note = "N/A — prior year value ≤ 0"
            else:
                gr = (v0 / v1 - 1) * 100; gr_note = None
            fcf_note = "\n⚠ FCF = freeCashFlow; fallback CFO−|CapEx| if null" if is_fcf else ""
            return {
                "formula": f"(V[{y0}] ÷ V[{y1}]) − 1 × 100\n= Annual growth (latest fiscal year vs prior){fcf_note}\n⚠ N/A when prior year ≤ 0",
                "fields":  [f"{stmt_lbl}.{api_key} — annual"],
                "unit": "%",
                "components": [
                    (f"{stmt_lbl}.{api_key}  [{y0}]  (V recent)" + (f"  source: {s0}" if is_fcf else ""), raw(v0)),
                    (f"{stmt_lbl}.{api_key}  [{y1}]  (V prior year)" + (f"  source: {s1}" if is_fcf else ""), raw(v1)),
                    ("── Calculation ──",                                  ""),
                    (f"({raw(v0)} ÷ {raw(v1)}) − 1",                      f"{(gr/100):.6f}" if gr is not None else (gr_note or "—")),
                    ("× 100",                                               ""),
                    ("── Result ──",                                        ""),
                    (f"{field_label} Growth (Ann)",                        f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
                ],
                "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}

        if "QoQ" in L:
            qs = sorted(stmt_q.keys(), reverse=True)
            if len(qs) < 2:
                return {"formula": "V[Q0] ÷ V[Q1] − 1 × 100  (latest vs prior quarter)",
                        "fields": [f"{stmt_lbl}.{api_key} — quarterly"],
                        "unit": "%", "components": [("N/A", "Requires at least 2 quarters of data")], "result": "—"}
            q0 = qs[0]; q1 = qs[1]
            if is_fcf:
                v0, s0 = get_fcf_q(q0); v1, s1 = get_fcf_q(q1)
            else:
                v0 = fv(stmt_q[q0].get(api_key)); s0 = api_key
                v1 = fv(stmt_q[q1].get(api_key)); s1 = api_key
            if v0 is None or v1 is None:
                gr = None; gr_note = "N/A — data missing"
            elif v1 <= 0:
                gr = None; gr_note = "N/A — prior quarter value ≤ 0"
            else:
                gr = (v0 / v1 - 1) * 100; gr_note = None
            fcf_note = "\n⚠ FCF = freeCashFlow; fallback CFO−|CapEx| if null" if is_fcf else ""
            return {
                "formula": f"(V[{q0}] ÷ V[{q1}]) − 1 × 100\n= Quarter-over-Quarter growth{fcf_note}\n⚠ N/A when prior quarter ≤ 0",
                "fields":  [f"{stmt_lbl}.{api_key} — quarterly"],
                "unit": "%",
                "components": [
                    (f"{stmt_lbl}.{api_key}  [{q0}]  (Q0)" + (f"  source: {s0}" if is_fcf else ""), raw(v0)),
                    (f"{stmt_lbl}.{api_key}  [{q1}]  (Q1)" + (f"  source: {s1}" if is_fcf else ""), raw(v1)),
                    ("── Calculation ──",                                  ""),
                    (f"({raw(v0)} ÷ {raw(v1)}) − 1",                      f"{(gr/100):.6f}" if gr is not None else (gr_note or "—")),
                    ("× 100",                                               ""),
                    ("── Result ──",                                        ""),
                    (f"{field_label} Growth (QoQ)",                        f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
                ],
                "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}

        if "YoY" in L:
            qs = sorted(stmt_q.keys(), reverse=True)
            if len(qs) < 5:
                return {"formula": "V[Q0] ÷ V[Q4] − 1 × 100  (same quarter prior year)",
                        "fields": [f"{stmt_lbl}.{api_key} — quarterly"],
                        "unit": "%", "components": [("N/A", "Requires at least 5 quarters of data")], "result": "—"}
            q0 = qs[0]; q4 = qs[4]
            if is_fcf:
                v0, s0 = get_fcf_q(q0); v4, s4 = get_fcf_q(q4)
            else:
                v0 = fv(stmt_q[q0].get(api_key)); s0 = api_key
                v4 = fv(stmt_q[q4].get(api_key)); s4 = api_key
            if v0 is None or v4 is None:
                gr = None; gr_note = "N/A — data missing"
            elif v4 <= 0:
                gr = None; gr_note = "N/A — prior year quarter value ≤ 0"
            else:
                gr = (v0 / v4 - 1) * 100; gr_note = None
            fcf_note = "\n⚠ FCF = freeCashFlow; fallback CFO−|CapEx| if null" if is_fcf else ""
            return {
                "formula": f"(V[{q0}] ÷ V[{q4}]) − 1 × 100\n= Year-over-Year (same quarter prior year){fcf_note}\n⚠ N/A when prior year quarter ≤ 0",
                "fields":  [f"{stmt_lbl}.{api_key} — quarterly"],
                "unit": "%",
                "components": [
                    (f"{stmt_lbl}.{api_key}  [{q0}]  (Q0 — current)" + (f"  source: {s0}" if is_fcf else ""), raw(v0)),
                    (f"{stmt_lbl}.{api_key}  [{q4}]  (Q4 — same quarter prior year)" + (f"  source: {s4}" if is_fcf else ""), raw(v4)),
                    ("── Calculation ──",                                  ""),
                    (f"({raw(v0)} ÷ {raw(v4)}) − 1",                      f"{(gr/100):.6f}" if gr is not None else (gr_note or "—")),
                    ("× 100",                                               ""),
                    ("── Result ──",                                        ""),
                    (f"{field_label} Growth (YoY)",                        f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
                ],
                "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}

        if "TTM" in L:
            qs = sorted(stmt_q.keys(), reverse=True)
            def get_ttm_with_qs(start):
                rows = []
                for i in range(start, start+4):
                    q = qs[i]
                    if is_fcf:
                        v, src = get_fcf_q(q)
                        rows.append((q, v, src))
                    else:
                        v = fv(stmt_q[q].get(api_key))
                        rows.append((q, v, api_key))
                total = sum(v for _, v, _ in rows if v is not None)
                return (total if sum(1 for _, v, _ in rows if v is not None) == 4 else None), rows
            t0, t0_qs = get_ttm_with_qs(0)
            t4, t4_qs = get_ttm_with_qs(4)
            # Guard: base must be positive for meaningful growth rate
            gr = (t0 / t4 - 1) * 100 if t0 is not None and t4 and t4 > 0 else None
            gr_note = "N/A — base period FCF negative" if (t4 is not None and t4 <= 0) else None
            comps = [
                (f"TTM now  ({qs[0][:7]}–{qs[3][:7]})", ""),
            ]
            for q, v, src in t0_qs:
                lbl = f"  {stmt_lbl}.freeCashFlow [{q}]" if src == "freeCashFlow" else \
                      f"  CFO−|CapEx| fallback  [{q}]" if src == "CFO−|CapEx|" else \
                      f"  {stmt_lbl}.{api_key}  [{q}]"
                comps.append((lbl, raw(v)))
            comps.append((f"  → TTM Sum (now)", raw(t0)))
            comps.append((f"TTM 1Y ago  ({qs[4][:7]}–{qs[7][:7]})" if len(qs)>7 else "TTM 1Y ago", ""))
            for q, v, src in t4_qs:
                lbl = f"  {stmt_lbl}.freeCashFlow [{q}]" if src == "freeCashFlow" else \
                      f"  CFO−|CapEx| fallback  [{q}]" if src == "CFO−|CapEx|" else \
                      f"  {stmt_lbl}.{api_key}  [{q}]"
                comps.append((lbl, raw(v)))
            comps.append((f"  → TTM Sum (1Y ago)", raw(t4)))
            comps += [
                ("── Calculation ──",                              ""),
                (f"(TTM now ÷ TTM 1Y ago) − 1",                  f"({raw(t0)} ÷ {raw(t4)}) − 1"),
                ("× 100",                                          ""),
                ("── Result ──",                                   ""),
                (f"{field_label} Growth (TTM)",                   f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
            ]
            fcf_note = "\n⚠ FCF = freeCashFlow; fallback CFO−|CapEx| if null\n⚠ N/A when base period ≤ 0" if is_fcf else ""
            return {"formula": f"(TTM[now] ÷ TTM[1Y ago] − 1) × 100  |  4-quarter rolling sums{fcf_note}",
                    "fields": [f"{stmt_lbl}.{api_key} — quarterly, windows [Q0:Q3] and [Q4:Q7]"],
                    "unit": "%", "components": comps, "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}

        elif "CAGR" in L:
            # Extract n from label: "3Y CAGR" → 3, "5Y CAGR" → 5, "10Y CAGR" → 10
            import re as _re
            m = _re.search(r"(\d+)Y CAGR", L)
            n = int(m.group(1)) if m else None
            if n is None: return UNKNOWN
            ys = sorted(stmt_a.keys(), reverse=True)
            if len(ys) < n + 1:
                return {"formula": f"(V[year 0] ÷ V[year -{n}])^(1/{n}) − 1",
                        "fields": [f"{stmt_lbl}.{api_key} — annual"],
                        "unit": "%", "components": [("N/A", f"Requires {n+1} years of data — only {len(ys)} available")],
                        "result": "—"}
            if is_fcf:
                v0, s0 = get_fcf_a(ys[0])
                vn, sn = get_fcf_a(ys[n])
            else:
                v0 = fv(stmt_a[ys[0]].get(api_key)); s0 = api_key
                vn = fv(stmt_a[ys[n]].get(api_key)); sn = api_key
            y0 = ys[0]; yn = ys[n]
            gr_note = None
            if v0 is None or vn is None:
                gr = None; gr_note = "N/A — data missing"
            elif vn <= 0:
                gr = None; gr_note = "N/A — base year value ≤ 0"
            else:
                gr = ((v0 / vn) ** (1 / n) - 1) * 100
            fcf_note = "\n⚠ FCF = freeCashFlow; fallback CFO−|CapEx| if null" if is_fcf else ""
            # Build per-year value table (all n+1 years used in CAGR span)
            yr_comps = []
            for i, y in enumerate(ys[:n + 1]):
                if is_fcf:
                    yv, _ = get_fcf_a(y)
                else:
                    yv = fv(stmt_a[y].get(api_key))
                label_suffix = "  ← recent" if i == 0 else (f"  ← base ({n}Y ago)" if i == n else "")
                yr_comps.append((f"  {y[:4]}{label_suffix}", raw(yv)))
            return {
                "formula": f"(V[{y0}] ÷ V[{yn}])^(1/{n}) − 1  × 100\n= Compound Annual Growth Rate over {n} years{fcf_note}\n⚠ N/A when base year ≤ 0",
                "fields":  [f"{stmt_lbl}.{api_key} — annual"],
                "unit": "%",
                "components": (
                    yr_comps +
                    [
                        ("── Berechnung ──",                                             ""),
                        (f"({raw(v0)} ÷ {raw(vn)})^(1/{n}) − 1",  f"{(gr / 100):.6f}" if gr is not None else (gr_note or "—")),
                        ("× 100",                                                        ""),
                        ("── Result ──",                                                 ""),
                        (f"→ {field_label} Growth ({n}Y CAGR)",  f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
                    ]
                ),
                "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}

        elif "Fwd" in L:
            trends   = data.get("Earnings", {}).get("Trend", {})
            p1y      = next((v for v in trends.values() if v.get("period") == "+1y"), {})
            p1y_date = next((k for k, v in trends.items() if v.get("period") == "+1y"), "—")
            is_rev   = "Revenue" in L
            gr_key   = "revenueEstimateGrowth" if is_rev else "earningsEstimateGrowth"
            avg_key  = "revenueEstimateAvg"    if is_rev else "earningsEstimateAvg"
            lo_key   = "revenueEstimateLow"    if is_rev else "earningsEstimateLow"
            hi_key   = "revenueEstimateHigh"   if is_rev else "earningsEstimateHigh"
            na_key   = "revenueEstimateNumberOfAnalysts" if is_rev else "earningsEstimateNumberOfAnalysts"
            g        = fv(p1y.get(gr_key))
            est_avg  = fv(p1y.get(avg_key))
            est_lo   = fv(p1y.get(lo_key))
            est_hi   = fv(p1y.get(hi_key))
            n_an     = p1y.get(na_key, "—")
            def fmt_est(v): return f"{v/1e9:.4f} B" if v and abs(v) > 1e6 else (f"{v:.6f}" if v else "—")
            hl_rev_gr  = fv(hl.get("RevenueGrowthQuarterlyYOY"))
            hl_earn_gr = fv(hl.get("QuarterlyEarningsGrowthYOY"))
            comps = [
                ("Earnings.Trend key (date)",                        p1y_date),
                (f"Earnings.Trend[+1y].{gr_key}  (raw decimal)",    num(g, 6) if g else "—"),
                (f"Earnings.Trend[+1y].{avg_key}",                  fmt_est(est_avg)),
                (f"Earnings.Trend[+1y].{lo_key}",                   fmt_est(est_lo)),
                (f"Earnings.Trend[+1y].{hi_key}",                   fmt_est(est_hi)),
                (f"Earnings.Trend[+1y].{na_key}",                   str(n_an)),
            ]
            if is_rev and hl_rev_gr is not None:
                comps.append(("Highlights.RevenueGrowthQuarterlyYOY  (cross-check)", pct(hl_rev_gr)))
            elif not is_rev and hl_earn_gr is not None:
                comps.append(("Highlights.QuarterlyEarningsGrowthYOY  (cross-check)", pct(hl_earn_gr)))
            comps += [
                ("── Result ──",                   ""),
                (f"{field_label} Growth (Fwd)",   pct(g)),
            ]
            return {"formula": "Analyst consensus — Earnings.Trend period +1y\nField: " + gr_key,
                    "fields": [f"Earnings.Trend[+1y].{gr_key}", f"Earnings.Trend[+1y].{avg_key}",
                               f"Earnings.Trend[+1y].{na_key}"],
                    "unit": "%", "components": comps, "result": pct(g)}
        return UNKNOWN

    if "Revenue Growth" in L:    return growth_dd("Revenue",  q_is, a_is, "totalRevenue")
    if "Net Income Growth" in L: return growth_dd("Net Income", q_is, a_is, "netIncome")
    if "EPS Growth" in L and "Fwd" not in L:
        # EPS = NI / commonStockSharesOutstanding
        # TTM: NI_TTM / shares_Q0  vs  NI_TTM_1Yago / shares_Q4
        # CAGR: (EPS_y0 / EPS_yn)^(1/n) − 1  on annual basis

        def dd_eps_cagr(n):
            ys  = sorted(a_is.keys(), reverse=True)
            ybs = sorted(a_bs.keys(), reverse=True)
            if len(ys) < n + 1:
                return {"formula": f"(EPS[y0] ÷ EPS[y-{n}])^(1/{n}) − 1 × 100\nEPS = NI ÷ commonStockSharesOutstanding",
                        "fields": ["Income_Statement.netIncomeApplicableToCommonShares",
                                   "Balance_Sheet.commonStockSharesOutstanding"],
                        "unit": "%",
                        "components": [("N/A", f"Requires {n+1} years of data — only {len(ys)} available")],
                        "result": "—"}
            def get_eps_dd(y):
                ni  = fv(a_is[y].get("netIncomeApplicableToCommonShares")) or fv(a_is[y].get("netIncome"))
                shs = fv(a_bs.get(y, {}).get("commonStockSharesOutstanding"))
                return ni, shs, (ni / shs) if ni is not None and shs and shs > 0 else None
            y0 = ys[0]; yn = ys[n]
            ni0, shs0, eps0 = get_eps_dd(y0)
            nin, shsn, epsn = get_eps_dd(yn)
            if eps0 is None or epsn is None or epsn <= 0:
                note = "N/A — base EPS ≤ 0 or data missing"
                return {"formula": f"(EPS[{y0}] ÷ EPS[{yn}])^(1/{n}) − 1 × 100",
                        "fields": ["Income_Statement.netIncomeApplicableToCommonShares",
                                   "Balance_Sheet.commonStockSharesOutstanding"],
                        "unit": "%", "components": [("N/A", note)], "result": "—"}
            gr = ((eps0 / epsn) ** (1 / n) - 1) * 100
            return {
                "formula": f"(EPS[{y0}] ÷ EPS[{yn}])^(1/{n}) − 1 × 100\nEPS = NI ÷ commonStockSharesOutstanding",
                "fields":  ["Income_Statement.netIncomeApplicableToCommonShares (fallback: netIncome)",
                            "Balance_Sheet.commonStockSharesOutstanding"],
                "unit": "%",
                "components": [
                    (f"── EPS {y0} (recent) ──",                                       ""),
                    (f"  NI  [Income_Statement {y0}]",                                 raw(ni0)),
                    (f"  Shares  [Balance_Sheet {y0}]",                               raw(shs0)),
                    (f"  → EPS {y0}  =  {raw(ni0)} ÷ {raw(shs0)}",                   f"{eps0:.6f}"),
                    (f"── EPS {yn} (base, {n}Y ago) ──",                               ""),
                    (f"  NI  [Income_Statement {yn}]",                                 raw(nin)),
                    (f"  Shares  [Balance_Sheet {yn}]",                               raw(shsn)),
                    (f"  → EPS {yn}  =  {raw(nin)} ÷ {raw(shsn)}",                   f"{epsn:.6f}"),
                    ("── Calculation ──",                                               ""),
                    (f"({eps0:.6f} ÷ {epsn:.6f})^(1/{n}) − 1",                       f"{(gr/100):.6f}"),
                    ("× 100",                                                           ""),
                    ("── Result ──",                                                    ""),
                    (f"EPS Growth ({n}Y CAGR)",                                        f"{gr:.4f} %"),
                ],
                "result": f"{gr:.4f} %"}

        def dd_eps_ttm():
            qs  = sorted(q_is.keys(), reverse=True)
            qbs = sorted(q_bs.keys(), reverse=True)
            def ttm_ni_rows(start):
                rows = []
                for i in range(start, start+4):
                    q = qs[i]
                    v = fv(q_is[q].get("netIncomeApplicableToCommonShares")) or fv(q_is[q].get("netIncome"))
                    rows.append((q, v))
                total = sum(v for _, v in rows if v is not None)
                return rows, (total if sum(1 for _, v in rows if v is not None)==4 else None)
            t0_rows, ni0 = ttm_ni_rows(0)
            t4_rows, ni4 = ttm_ni_rows(4)
            shs0 = fv(q_bs[qbs[0]].get("commonStockSharesOutstanding")) if qbs else None
            shs4 = fv(q_bs[qbs[4]].get("commonStockSharesOutstanding")) if len(qbs)>4 else shs0
            eps0 = (ni0 / shs0) if ni0 and shs0 and shs0 > 0 else None
            eps4 = (ni4 / shs4) if ni4 and shs4 and shs4 > 0 else None
            if eps4 is not None and eps4 <= 0:
                gr_note = "N/A — base EPS ≤ 0"
            elif eps0 is None or eps4 is None:
                gr_note = "N/A — data missing"
            else:
                gr_note = None
            gr = (eps0 / eps4 - 1) * 100 if eps0 and eps4 and eps4 > 0 else None
            comps = [(f"── NI TTM now  ({qs[0][:7]}–{qs[3][:7]}) ──", "")]
            for q, v in t0_rows:
                comps.append((f"  NI  [{q}]", raw(v)))
            comps.append((f"  → NI TTM (now)", raw(ni0)))
            comps.append((f"  Shares  [{qbs[0] if qbs else '—'}]", raw(shs0)))
            comps.append((f"  → EPS TTM (now)  =  {raw(ni0)} ÷ {raw(shs0)}", f"{eps0:.6f}" if eps0 else "—"))
            comps.append((f"── NI TTM 1Y ago  ({qs[4][:7]}–{qs[7][:7] if len(qs)>7 else '—'}) ──", ""))
            for q, v in t4_rows:
                comps.append((f"  NI  [{q}]", raw(v)))
            comps.append((f"  → NI TTM (1Y ago)", raw(ni4)))
            comps.append((f"  Shares  [{qbs[4] if len(qbs)>4 else '—'}]", raw(shs4)))
            comps.append((f"  → EPS TTM (1Y ago)  =  {raw(ni4)} ÷ {raw(shs4)}", f"{eps4:.6f}" if eps4 else "—"))
            comps += [
                ("── Calculation ──",                              ""),
                (f"(EPS now ÷ EPS 1Y ago) − 1 × 100",            f"({eps0:.6f} ÷ {eps4:.6f})" if eps0 and eps4 else "—"),
                ("── Result ──",                                   ""),
                ("EPS Growth (TTM)",                               f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
            ]
            return {"formula": "EPS Growth TTM = (EPS_TTM_now ÷ EPS_TTM_1Yago − 1) × 100\nEPS = NI_TTM ÷ shares (latest quarter)",
                    "fields": ["Income_Statement.netIncomeApplicableToCommonShares (fallback: netIncome) — quarterly",
                               "Balance_Sheet.commonStockSharesOutstanding — quarterly"],
                    "unit": "%", "components": comps,
                    "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}

        if "CAGR" in L:
            import re as _re
            m = _re.search(r"(\d+)Y CAGR", L)
            n = int(m.group(1)) if m else None
            if n: return dd_eps_cagr(n)
        elif "Ann" in L:
            # EPS Ann: (EPS_y0 / EPS_y1) - 1
            ys = sorted(a_is.keys(), reverse=True)
            if len(ys) < 2:
                return {"formula": "EPS Ann = (EPS[y0] / EPS[y1]) - 1 x 100", "fields": [], "unit": "%",
                        "components": [("N/A", "Requires at least 2 years of data")], "result": "—"}
            y0 = ys[0]; y1 = ys[1]
            ni0 = fv(a_is[y0].get("netIncomeApplicableToCommonShares")) or fv(a_is[y0].get("netIncome"))
            ni1 = fv(a_is[y1].get("netIncomeApplicableToCommonShares")) or fv(a_is[y1].get("netIncome"))
            shs0 = fv(a_bs.get(y0, {}).get("commonStockSharesOutstanding"))
            shs1 = fv(a_bs.get(y1, {}).get("commonStockSharesOutstanding"))
            eps0 = (ni0 / shs0) if ni0 and shs0 and shs0 > 0 else None
            eps1 = (ni1 / shs1) if ni1 and shs1 and shs1 > 0 else None
            if eps1 is not None and eps1 <= 0:
                gr = None; gr_note = "N/A — prior year EPS <= 0"
            elif eps0 is None or eps1 is None:
                gr = None; gr_note = "N/A — data missing"
            else:
                gr = (eps0 / eps1 - 1) * 100; gr_note = None
            return {
                "formula": f"(EPS[{y0}] / EPS[{y1}]) - 1 x 100\nEPS = NI / commonStockSharesOutstanding\n= Annual growth (latest fiscal year vs prior)",
                "fields": ["Income_Statement.netIncomeApplicableToCommonShares (fallback: netIncome)",
                           "Balance_Sheet.commonStockSharesOutstanding"],
                "unit": "%",
                "components": [
                    (f"-- EPS {y0} (recent) --",                              ""),
                    (f"  NI  [Income_Statement {y0}]",                        raw(ni0)),
                    (f"  Shares  [Balance_Sheet {y0}]",                      raw(shs0)),
                    (f"  -> EPS {y0}  =  {raw(ni0)} / {raw(shs0)}",          f"{eps0:.6f}" if eps0 else "—"),
                    (f"-- EPS {y1} (prior year) --",                          ""),
                    (f"  NI  [Income_Statement {y1}]",                        raw(ni1)),
                    (f"  Shares  [Balance_Sheet {y1}]",                      raw(shs1)),
                    (f"  -> EPS {y1}  =  {raw(ni1)} / {raw(shs1)}",          f"{eps1:.6f}" if eps1 else "—"),
                    ("-- Calculation --",                                       ""),
                    (f"({eps0:.6f} / {eps1:.6f}) - 1" if eps0 and eps1 else "N/A", f"{(gr/100):.6f}" if gr is not None else (gr_note or "—")),
                    ("x 100",                                                   ""),
                    ("-- Result --",                                            ""),
                    ("EPS Growth (Ann)",                                        f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
                ],
                "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}
        elif "QoQ" in L:
            # EPS QoQ: (EPS_Q0 / EPS_Q1) - 1
            qs_is = sorted(q_is.keys(), reverse=True)
            qs_bs = sorted(q_bs.keys(), reverse=True)
            if len(qs_is) < 2 or len(qs_bs) < 2:
                return {"formula": "EPS QoQ = (EPS[Q0] / EPS[Q1]) - 1 x 100", "fields": [], "unit": "%",
                        "components": [("N/A", "Requires at least 2 quarters")], "result": "—"}
            q0i = qs_is[0]; q1i = qs_is[1]
            q0b = qs_bs[0]; q1b = qs_bs[1]
            ni0 = fv(q_is[q0i].get("netIncomeApplicableToCommonShares")) or fv(q_is[q0i].get("netIncome"))
            ni1 = fv(q_is[q1i].get("netIncomeApplicableToCommonShares")) or fv(q_is[q1i].get("netIncome"))
            shs0 = fv(q_bs[q0b].get("commonStockSharesOutstanding"))
            shs1 = fv(q_bs[q1b].get("commonStockSharesOutstanding"))
            eps0 = (ni0 / shs0) if ni0 and shs0 and shs0 > 0 else None
            eps1 = (ni1 / shs1) if ni1 and shs1 and shs1 > 0 else None
            if eps1 is not None and eps1 <= 0:
                gr = None; gr_note = "N/A — prior quarter EPS <= 0"
            elif eps0 is None or eps1 is None:
                gr = None; gr_note = "N/A — data missing"
            else:
                gr = (eps0 / eps1 - 1) * 100; gr_note = None
            return {
                "formula": f"(EPS[{q0i}] / EPS[{q1i}]) - 1 x 100\nEPS = NI / commonStockSharesOutstanding\n= Quarter-over-Quarter growth",
                "fields": ["Income_Statement.netIncomeApplicableToCommonShares (fallback: netIncome)",
                           "Balance_Sheet.commonStockSharesOutstanding"],
                "unit": "%",
                "components": [
                    (f"-- EPS {q0i} (Q0) --",                                 ""),
                    (f"  NI  [Income_Statement {q0i}]",                       raw(ni0)),
                    (f"  Shares  [Balance_Sheet {q0b}]",                     raw(shs0)),
                    (f"  -> EPS {q0i}  =  {raw(ni0)} / {raw(shs0)}",         f"{eps0:.6f}" if eps0 else "—"),
                    (f"-- EPS {q1i} (Q1) --",                                 ""),
                    (f"  NI  [Income_Statement {q1i}]",                       raw(ni1)),
                    (f"  Shares  [Balance_Sheet {q1b}]",                     raw(shs1)),
                    (f"  -> EPS {q1i}  =  {raw(ni1)} / {raw(shs1)}",         f"{eps1:.6f}" if eps1 else "—"),
                    ("-- Calculation --",                                       ""),
                    (f"({eps0:.6f} / {eps1:.6f}) - 1" if eps0 and eps1 else "N/A", f"{(gr/100):.6f}" if gr is not None else (gr_note or "—")),
                    ("x 100",                                                   ""),
                    ("-- Result --",                                            ""),
                    ("EPS Growth (QoQ)",                                        f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
                ],
                "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}
        elif "YoY" in L:
            # EPS YoY: Q0 vs Q4 (same quarter prior year)
            qs_is = sorted(q_is.keys(), reverse=True)
            qs_bs = sorted(q_bs.keys(), reverse=True)
            if len(qs_is) < 5 or len(qs_bs) < 5:
                return {"formula": "EPS YoY = (EPS[Q0] / EPS[Q4]) - 1 x 100", "fields": [], "unit": "%",
                        "components": [("N/A", "Requires at least 5 quarters")], "result": "—"}
            q0i = qs_is[0]; q4i = qs_is[4]
            q0b = qs_bs[0]; q4b = qs_bs[4]
            ni0 = fv(q_is[q0i].get("netIncomeApplicableToCommonShares")) or fv(q_is[q0i].get("netIncome"))
            ni4 = fv(q_is[q4i].get("netIncomeApplicableToCommonShares")) or fv(q_is[q4i].get("netIncome"))
            shs0 = fv(q_bs[q0b].get("commonStockSharesOutstanding"))
            shs4 = fv(q_bs[q4b].get("commonStockSharesOutstanding"))
            eps0 = (ni0 / shs0) if ni0 and shs0 and shs0 > 0 else None
            eps4 = (ni4 / shs4) if ni4 and shs4 and shs4 > 0 else None
            if eps4 is not None and eps4 <= 0:
                gr = None; gr_note = "N/A — prior year quarter EPS <= 0"
            elif eps0 is None or eps4 is None:
                gr = None; gr_note = "N/A — data missing"
            else:
                gr = (eps0 / eps4 - 1) * 100; gr_note = None
            return {
                "formula": f"(EPS[{q0i}] / EPS[{q4i}]) - 1 x 100\nEPS = NI / commonStockSharesOutstanding\n= Same quarter prior year",
                "fields": ["Income_Statement.netIncomeApplicableToCommonShares (fallback: netIncome)",
                           "Balance_Sheet.commonStockSharesOutstanding"],
                "unit": "%",
                "components": [
                    (f"-- EPS {q0i} (Q0 — current) --",                        ""),
                    (f"  NI  [Income_Statement {q0i}]",                        raw(ni0)),
                    (f"  Shares  [Balance_Sheet {q0b}]",                       raw(shs0)),
                    (f"  -> EPS {q0i}",                                        f"{eps0:.6f}" if eps0 else "—"),
                    (f"-- EPS {q4i} (Q4 — same quarter prior year) --",        ""),
                    (f"  NI  [Income_Statement {q4i}]",                        raw(ni4)),
                    (f"  Shares  [Balance_Sheet {q4b}]",                       raw(shs4)),
                    (f"  -> EPS {q4i}",                                        f"{eps4:.6f}" if eps4 else "—"),
                    ("-- Calculation --",                                        ""),
                    (f"({eps0:.6f} / {eps4:.6f}) - 1" if eps0 and eps4 else "N/A", f"{(gr/100):.6f}" if gr is not None else (gr_note or "—")),
                    ("x 100",                                                    ""),
                    ("-- Result --",                                             ""),
                    ("EPS Growth (YoY)",                                         f"{gr:.4f} %" if gr is not None else (gr_note or "—")),
                ],
                "result": f"{gr:.4f} %" if gr is not None else (gr_note or "—")}
        elif "TTM" in L:
            return dd_eps_ttm()
        return UNKNOWN
    if "EPS Growth (Fwd)" in L:  return growth_dd("EPS", None, None, None)
    if "EBIT Growth" in L:       return growth_dd("EBIT", q_is, a_is, "ebit")
    if "EBITDA Growth" in L:     return growth_dd("EBITDA", q_is, a_is, "ebitda")
    if "FCF Growth" in L:        return growth_dd("FCF", q_cf, a_cf, "freeCashFlow", q_cf, "freeCashFlow")

    if "Rule of 40" in L:
        is_ttm  = "TTM" in L
        rev0    = rev_ttm; rev1_a = fv(a_is.get(years[1], {}).get("totalRevenue")) if len(years)>1 else None
        rev_gr  = (rev_ttm / rev1_a - 1) if rev_ttm and rev1_a and rev1_a > 0 else None
        fcf     = fcf_ttm if is_ttm else fcf_a
        rev     = rev_ttm if is_ttm else rev_a
        fcfm    = safe(fcf, rev)
        r40     = ((rev_gr or 0)*100 + (fcfm or 0)*100) if rev_gr is not None and fcfm is not None else None
        y0 = years[0] if years else "—"; y1 = years[1] if len(years)>1 else "—"
        return {
            "formula": "Revenue Growth (%) + FCF Margin (%)",
            "fields":  ["Income_Statement.totalRevenue (TTM + annual Y-1 for growth)",
                        "Cash_Flow.freeCashFlow (TTM)"],
            "unit": "%",
            "components": [
                ("── Revenue TTM quarters ──",                                ""),
                *ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue"),
                (f"Revenue Y-1  [Income_Statement.totalRevenue {y1}]",       raw(rev1_a)),
                (f"Revenue Growth = ({raw(rev_ttm)} ÷ {raw(rev1_a)}) − 1",  pct(rev_gr)),
                ("── FCF TTM quarters ──",                                    ""),
                *(ttm_rows(q_cf, "freeCashFlow", "Cash_Flow.freeCashFlow") if is_ttm else
                  [(f"Cash_Flow.freeCashFlow  [{cfA_dt}]", raw(fcf))]),
                (f"Revenue {'TTM' if is_ttm else 'Annual'}",                  raw(rev)),
                (f"FCF Margin = {raw(fcf)} ÷ {raw(rev)}",                    pct(fcfm)),
                ("── Calculation ──",                                           ""),
                (f"Rev Growth % + FCF Margin %",
                 f"{pct(rev_gr)} + {pct(fcfm)}"),
                ("── Result ──",                                                ""),
                ("Rule of 40",                                                  f"{r40:.4f} %" if r40 else "—"),
            ],
            "result": f"{r40:.2f} %" if r40 else "—"}

    # ═══════════════════════════════════════════════════════════════════
    # HEALTH
    # ═══════════════════════════════════════════════════════════════════
    def _iq(q=True): return True if ("Quarterly" in L or "TTM" in L) else False

    def health_debt_comps(is_q):
        ltd  = ltd_q if is_q else ltd_a
        std  = std_q if is_q else std_a
        debt = ltd + std
        dt   = bsQ_dt if is_q else bsA_dt
        return ltd, std, debt, dt

    is_q = "Quarterly" in L or "TTM" in L

    if "Cash/Debt" in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        cash = cash_q if is_q else cash_a
        r    = safe(cash, debt)
        return {
            "formula": "Cash & Equivalents ÷ Total Debt",
            "fields":  ["Balance_Sheet.cash + shortTermInvestments (cashAndEquivalents fallback)", "Balance_Sheet.longTermDebt",
                        "Balance_Sheet.shortLongTermDebt"],
            "unit": "x",
            "components": [
                ("── Cash breakdown ──",                                   ""),
                *(cash_comps(bsQ if is_q else bsA, dt)[0]),
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt}]",    bn(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt}]", bn(std)),
                (f"Total Debt = {bn(ltd)} + {bn(std)}",                  bn(debt)),
                ("── Calculation ──",                                      ""),
                (f"Cash ÷ Total Debt",                                    f"{bn(cash)} ÷ {bn(debt)}"),
                ("── Result ──",                                           ""),
                ("Cash/Debt",                                              num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Debt/Capital" in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        eq   = eq_q if is_q else eq_a
        cap  = debt + (eq or 0)
        r    = safe(debt, cap)
        return {
            "formula": "Total Debt ÷ (Total Debt + Equity)",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt",
                        "Balance_Sheet.totalStockholderEquity"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [{dt}]",       bn(ltd)),
                (f"Short-Term Debt  [{dt}]",      bn(std)),
                (f"Total Debt = {bn(ltd)} + {bn(std)}", bn(debt)),
                (f"Equity  [{dt}]",               bn(eq)),
                (f"Capital = Debt + Equity",      bn(cap)),
                ("── Calculation ──",              ""),
                (f"Debt ÷ Capital",               f"{bn(debt)} ÷ {bn(cap)}"),
                ("── Result ──",                   ""),
                ("Debt/Capital",                   num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "FCF/Debt" in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        fcf    = fcf_ttm if is_q else fcf_a
        direct = fcf_ttm_direct if is_q else fcf_a_direct
        cfo    = fcf_ttm_cfo if is_q else fcf_a_cfo
        cx     = fcf_ttm_cx  if is_q else fcf_a_cx
        r      = safe(fcf, debt)
        comps  = []
        if is_q:
            qs_used = sorted(q_cf.keys(), reverse=True)[:4]
            if direct:
                comps.append(("── FCF quarters (freeCashFlow) ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.freeCashFlow  [{q}]", raw(fv(q_cf[q].get("freeCashFlow")))))
                comps.append(("  → FCF TTM Sum", raw(fcf)))
            else:
                comps.append(("── CFO quarters (freeCashFlow null → fallback) ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.totalCashFromOperatingActivities  [{q}]", raw(fv(q_cf[q].get("totalCashFromOperatingActivities")))))
                comps.append(("  → CFO TTM Sum", raw(cfo)))
                comps.append(("── CapEx quarters ──", ""))
                for q in qs_used:
                    comps.append((f"  Cash_Flow.capitalExpenditures  [{q}]", raw(fv(q_cf[q].get("capitalExpenditures")))))
                comps.append(("  → CapEx TTM Sum", raw(cx)))
                comps.append((f"  FCF = CFO − |CapEx| = {raw(cfo)} − |{raw(cx)}|", raw(fcf)))
        else:
            if direct:
                comps.append((f"Cash_Flow.freeCashFlow  [{cfA_dt}]", raw(fcf)))
            else:
                comps += [
                    (f"Cash_Flow.totalCashFromOperatingActivities  [{cfA_dt}]", raw(cfo)),
                    (f"Cash_Flow.capitalExpenditures  [{cfA_dt}]",              raw(cx)),
                    (f"FCF = CFO − |CapEx| (fallback)",                         raw(fcf)),
                ]
        comps += [
            (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt}]",          raw(ltd)),
            (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt}]",    raw(std)),
            (f"Total Debt = {raw(ltd)} + {raw(std)}",                       raw(debt)),
            ("── Calculation ──",                                             ""),
            (f"FCF ÷ Total Debt  =  {raw(fcf)} ÷ {raw(debt)}",              ""),
            ("── Result ──",                                                  ""),
            ("FCF/Debt",                                                      num(r, 4) + " x"),
        ]
        return {"formula": "Free Cash Flow ÷ Total Debt",
                "fields": ["Cash_Flow.freeCashFlow", "Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt"],
                "unit": "x", "components": comps, "result": num(r, 2)}

    if "Interest Coverage" in L:
        is_ttm2 = "TTM" in L
        ebit = ebit_ttm if is_ttm2 else ebit_a
        intr = int_ttm  if is_ttm2 else int_a
        dt   = f"TTM ({qis_s[0][:7]}…{qis_s[3][:7]})" if is_ttm2 else isA_dt
        r    = safe(ebit, abs(intr) if intr else None)
        return {
            "formula": "EBIT ÷ |Interest Expense|\n(interestExpense is often negative in EODHD → use abs())",
            "fields":  ["Income_Statement.ebit", "Income_Statement.interestExpense"],
            "unit": "x",
            "components": [
                (f"── EBIT {'TTM quarters' if is_ttm2 else dt} ──",    ""),
                *(ttm_rows(q_is, "ebit", "Income_Statement.ebit") if is_ttm2 else
                  [(f"Income_Statement.ebit  [{isA_dt}]", raw(ebit))]),
                (f"── Interest Expense {'TTM quarters' if is_ttm2 else dt} ──", ""),
                *(ttm_rows(q_is, "interestExpense", "Income_Statement.interestExpense") if is_ttm2 else
                  [(f"Income_Statement.interestExpense  [{isA_dt}]", raw(intr))]),
                (f"Interest Expense  [|abs| used]",                    raw(abs(intr) if intr else None)),
                ("── Calculation ──",                                   ""),
                (f"EBIT ÷ |Interest|",                                f"{raw(ebit)} ÷ {raw(abs(intr) if intr else None)}"),
                ("── Result ──",                                        ""),
                ("Interest Coverage",                                   num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Cash Ratio" in L:
        cash = cash_q if is_q else cash_a
        cl   = cl_q   if is_q else cl_a
        dt   = bsQ_dt if is_q else bsA_dt
        r    = safe(cash, cl)
        return {
            "formula": "Cash & Equivalents ÷ Current Liabilities",
            "fields":  ["Balance_Sheet.cash + shortTermInvestments (cashAndEquivalents fallback)", "Balance_Sheet.totalCurrentLiabilities"],
            "unit": "x",
            "components": [
                ("── Cash breakdown ──",                                        ""),
                *(cash_comps(bsQ if is_q else bsA, dt)[0]),
                (f"Current Liabilities  [Balance_Sheet.totalCurrentLiabilities {dt}]", bn(cl)),
                ("── Calculation ──",                                            ""),
                (f"Cash ÷ Current Liabilities",                                f"{bn(cash)} ÷ {bn(cl)}"),
                ("── Result ──",                                                 ""),
                ("Cash Ratio",                                                   num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Debt/Equity" in L and "Net" not in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        eq = eq_q if is_q else eq_a
        r  = safe(debt, eq)
        return {
            "formula": "Total Debt ÷ Stockholder Equity",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt",
                        "Balance_Sheet.totalStockholderEquity"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [{dt}]",           bn(ltd)),
                (f"Short-Term Debt  [{dt}]",          bn(std)),
                (f"Total Debt = {bn(ltd)} + {bn(std)}", bn(debt)),
                (f"Equity  [{dt}]",                   bn(eq)),
                ("── Calculation ──",                  ""),
                (f"Total Debt ÷ Equity",             f"{bn(debt)} ÷ {bn(eq)}"),
                ("── Result ──",                       ""),
                ("D/E",                                num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "NetDebt/Equity" in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        cash = cash_q if is_q else cash_a
        nd   = debt - (cash or 0)
        eq   = eq_q if is_q else eq_a
        r    = safe(nd, eq)
        return {
            "formula": "Net Debt ÷ Equity\nNet Debt = Total Debt − Cash",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt",
                        "Balance_Sheet.cash + shortTermInvestments (cashAndEquivalents fallback)", "Balance_Sheet.totalStockholderEquity"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt}]",        raw(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt}]",  raw(std)),
                (f"Total Debt = {raw(ltd)} + {raw(std)}",                     raw(debt)),
                ("── Cash breakdown ──",                                        ""),
                *(cash_comps(bsQ if is_q else bsA, dt)[0]),
                (f"Net Debt = {raw(debt)} − {raw(cash)}",                    raw(nd)),
                (f"Equity  [Balance_Sheet.totalStockholderEquity {dt}]",      raw(eq)),
                ("── Calculation ──",                                           ""),
                (f"Net Debt ÷ Equity  =  {raw(nd)} ÷ {raw(eq)}",             ""),
                ("── Result ──",                       ""),
                ("NetDebt/Equity",                     num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Equity/Assets" in L:
        eq  = eq_q if is_q else eq_a
        ta  = ta_q if is_q else ta_a
        dt  = bsQ_dt if is_q else bsA_dt
        r   = safe(eq, ta)
        return {
            "formula": "Stockholder Equity ÷ Total Assets",
            "fields":  ["Balance_Sheet.totalStockholderEquity", "Balance_Sheet.totalAssets"],
            "unit": "x",
            "components": [
                (f"Equity  [Balance_Sheet.totalStockholderEquity {dt}]", bn(eq)),
                (f"Total Assets  [Balance_Sheet.totalAssets {dt}]",      bn(ta)),
                ("── Calculation ──",                                      ""),
                (f"Equity ÷ Total Assets",                               f"{bn(eq)} ÷ {bn(ta)}"),
                ("── Result ──",                                           ""),
                ("Equity/Assets",                                          num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Debt/Asset" in L and "Net" not in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        ta = ta_q if is_q else ta_a
        r  = safe(debt, ta)
        return {
            "formula": "Total Debt ÷ Total Assets",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Balance_Sheet.totalAssets"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [{dt}]",           bn(ltd)),
                (f"Short-Term Debt  [{dt}]",          bn(std)),
                (f"Total Debt = {bn(ltd)} + {bn(std)}", bn(debt)),
                (f"Total Assets  [{dt}]",             bn(ta)),
                ("── Calculation ──",                  ""),
                (f"Debt ÷ Assets",                   f"{bn(debt)} ÷ {bn(ta)}"),
                ("── Result ──",                       ""),
                ("Debt/Assets",                        num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "NetDebt/Asset" in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        cash = cash_q if is_q else cash_a
        nd   = debt - (cash or 0)
        ta   = ta_q if is_q else ta_a
        r    = safe(nd, ta)
        return {
            "formula": "Net Debt ÷ Total Assets\nNet Debt = Total Debt − Cash",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt",
                        "Balance_Sheet.cash + shortTermInvestments (cashAndEquivalents fallback)", "Balance_Sheet.totalAssets"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt}]",        raw(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt}]",  raw(std)),
                (f"Total Debt = {raw(ltd)} + {raw(std)}",                     raw(debt)),
                ("── Cash breakdown ──",                                        ""),
                *(cash_comps(bsQ if is_q else bsA, dt)[0]),
                (f"Net Debt = {raw(debt)} − {raw(cash)}",                    raw(nd)),
                (f"Total Assets  [Balance_Sheet.totalAssets {dt}]",           raw(ta)),
                ("── Calculation ──",                                           ""),
                (f"Net Debt ÷ Assets  =  {raw(nd)} ÷ {raw(ta)}",             ""),
                ("── Result ──",                       ""),
                ("NetDebt/Assets",                     num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Debt/EBIT" in L and "EBITDA" not in L and "Net" not in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        is_ttm2 = "TTM" in L
        ebit    = ebit_ttm if is_ttm2 else ebit_a
        r       = safe(debt, ebit)
        ebit_comps = ttm_rows(q_is, "ebit", "Income_Statement.ebit") if is_ttm2 else                      [(f"Income_Statement.ebit  [{isA_dt}]", raw(ebit))]
        return {
            "formula": "Total Debt ÷ EBIT",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Income_Statement.ebit"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt}]",        raw(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt}]",  raw(std)),
                (f"Total Debt = {raw(ltd)} + {raw(std)}",                     raw(debt)),
                (f"── EBIT {'TTM quarters' if is_ttm2 else isA_dt} ──",      ""),
                *ebit_comps,
                ("── Calculation ──",                                          ""),
                (f"Debt ÷ EBIT  =  {raw(debt)} ÷ {raw(ebit)}",               ""),
                ("── Result ──",                                               ""),
                ("Debt/EBIT",                                                  num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "NetDebt/EBIT" in L and "EBITDA" not in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        cash    = cash_q if is_q else cash_a
        nd      = debt - (cash or 0)
        is_ttm2 = "TTM" in L
        ebit    = ebit_ttm if is_ttm2 else ebit_a
        r       = safe(nd, ebit)
        ebit_comps = ttm_rows(q_is, "ebit", "Income_Statement.ebit") if is_ttm2 else                      [(f"Income_Statement.ebit  [{isA_dt}]", raw(ebit))]
        return {
            "formula": "Net Debt ÷ EBIT\nNet Debt = Total Debt − Cash",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt",
                        "Balance_Sheet.cash + shortTermInvestments (cashAndEquivalents fallback)", "Income_Statement.ebit"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt}]",        raw(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt}]",  raw(std)),
                (f"Total Debt = {raw(ltd)} + {raw(std)}",                     raw(debt)),
                ("── Cash breakdown ──",                                          ""),
                *(cash_comps(bsQ if is_ttm2 else bsA, dt)[0]),
                (f"Net Debt = {raw(debt)} − {raw(cash)}",                    raw(nd)),
                (f"── EBIT {'TTM quarters' if is_ttm2 else isA_dt} ──",      ""),
                *ebit_comps,
                ("── Calculation ──",                                          ""),
                (f"Net Debt ÷ EBIT  =  {raw(nd)} ÷ {raw(ebit)}",             ""),
                ("── Result ──",                                               ""),
                ("NetDebt/EBIT",                                               num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Debt/EBITDA" in L and "Net" not in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        is_ttm2 = "TTM" in L
        ebitda  = ebitda_ttm if is_ttm2 else ebitda_a
        r       = safe(debt, ebitda)
        ebitda_comps = ttm_rows(q_is, "ebitda", "Income_Statement.ebitda") if is_ttm2 else                        [(f"Income_Statement.ebitda  [{isA_dt}]", raw(ebitda))]
        return {
            "formula": "Total Debt ÷ EBITDA",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt", "Income_Statement.ebitda"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt}]",        raw(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt}]",  raw(std)),
                (f"Total Debt = {raw(ltd)} + {raw(std)}",                     raw(debt)),
                (f"── EBITDA {'TTM quarters' if is_ttm2 else isA_dt} ──",    ""),
                *ebitda_comps,
                ("── Calculation ──",                                          ""),
                (f"Debt ÷ EBITDA  =  {raw(debt)} ÷ {raw(ebitda)}",           ""),
                ("── Result ──",                                               ""),
                ("Debt/EBITDA",                                                num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "NetDebt/EBITDA" in L:
        ltd, std, debt, dt = health_debt_comps(is_q)
        cash    = cash_q if is_q else cash_a
        nd      = debt - (cash or 0)
        is_ttm2 = "TTM" in L
        ebitda  = ebitda_ttm if is_ttm2 else ebitda_a
        r       = safe(nd, ebitda)
        ebitda_comps = ttm_rows(q_is, "ebitda", "Income_Statement.ebitda") if is_ttm2 else                        [(f"Income_Statement.ebitda  [{isA_dt}]", raw(ebitda))]
        return {
            "formula": "Net Debt ÷ EBITDA\nNet Debt = Total Debt − Cash",
            "fields":  ["Balance_Sheet.longTermDebt", "Balance_Sheet.shortLongTermDebt",
                        "Balance_Sheet.cash + shortTermInvestments (cashAndEquivalents fallback)", "Income_Statement.ebitda"],
            "unit": "x",
            "components": [
                (f"Long-Term Debt  [Balance_Sheet.longTermDebt {dt}]",        raw(ltd)),
                (f"Short-Term Debt  [Balance_Sheet.shortLongTermDebt {dt}]",  raw(std)),
                (f"Total Debt = {raw(ltd)} + {raw(std)}",                     raw(debt)),
                ("── Cash breakdown ──",                                          ""),
                *(cash_comps(bsQ if is_ttm2 else bsA, dt)[0]),
                (f"Net Debt = {raw(debt)} − {raw(cash)}",                    raw(nd)),
                (f"── EBITDA {'TTM quarters' if is_ttm2 else isA_dt} ──",    ""),
                *ebitda_comps,
                ("── Calculation ──",                                          ""),
                (f"Net Debt ÷ EBITDA  =  {raw(nd)} ÷ {raw(ebitda)}",         ""),
                ("── Result ──",                                               ""),
                ("NetDebt/EBITDA",                                             num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Current Ratio" in L:
        ca  = ca_q if is_q else ca_a
        cl  = cl_q if is_q else cl_a
        dt  = bsQ_dt if is_q else bsA_dt
        r   = safe(ca, cl)
        return {
            "formula": "Current Assets ÷ Current Liabilities",
            "fields":  ["Balance_Sheet.totalCurrentAssets", "Balance_Sheet.totalCurrentLiabilities"],
            "unit": "x",
            "components": [
                (f"Current Assets  [Balance_Sheet.totalCurrentAssets {dt}]",          bn(ca)),
                (f"Current Liabilities  [Balance_Sheet.totalCurrentLiabilities {dt}]", bn(cl)),
                ("── Calculation ──",                                                   ""),
                (f"CA ÷ CL",                                                          f"{bn(ca)} ÷ {bn(cl)}"),
                ("── Result ──",                                                        ""),
                ("Current Ratio",                                                       num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Quick Ratio" in L:
        ca  = ca_q if is_q else ca_a
        cl  = cl_q if is_q else cl_a
        inv = inv_q if is_q else inv_a
        dt  = bsQ_dt if is_q else bsA_dt
        r   = safe((ca - inv) if ca else None, cl)
        return {
            "formula": "(Current Assets − Inventory) ÷ Current Liabilities",
            "fields":  ["Balance_Sheet.totalCurrentAssets", "Balance_Sheet.inventory",
                        "Balance_Sheet.totalCurrentLiabilities"],
            "unit": "x",
            "components": [
                (f"Current Assets  [{dt}]",                                             bn(ca)),
                (f"Inventory  [Balance_Sheet.inventory {dt}]",                         bn(inv)),
                (f"CA − Inventory = {bn(ca)} − {bn(inv)}",                            bn(ca - inv if ca else None)),
                (f"Current Liabilities  [{dt}]",                                       bn(cl)),
                ("── Calculation ──",                                                   ""),
                (f"(CA − Inv) ÷ CL",                                                  f"{bn(ca-inv if ca else None)} ÷ {bn(cl)}"),
                ("── Result ──",                                                        ""),
                ("Quick Ratio",                                                         num(r, 4) + " x"),
            ],
            "result": num(r, 2)}

    if "Altman Z" in L:
        is_annual = "Year" in L

        if is_annual:
            # Annual: BS from latest annual, income from annual
            _ta  = ta_a;    _ca  = ca_a;    _cl  = cl_a
            _re  = fv(bsA.get("retainedEarnings"))
            _tl  = tl_a;    _dt  = bsA_dt
            _ebit = ebit_a; _rev = rev_a
            _ebit_lbl = f"Income_Statement.ebit  [{isA_dt}]"
            _rev_lbl  = f"Income_Statement.totalRevenue  [{isA_dt}]"
            _ebit_qs  = [(f"Income_Statement.ebit  [{isA_dt}]", raw(_ebit))]
            _rev_qs   = [(f"Income_Statement.totalRevenue  [{isA_dt}]", raw(_rev))]
            mode_note = "Annual: Balance Sheet from latest annual report; EBIT/Revenue from annual"
        else:
            # Cur: BS from latest quarter, EBIT/Revenue as TTM sum
            _ta  = ta_q;    _ca  = ca_q;    _cl  = cl_q
            _re  = fv(bsQ.get("retainedEarnings"))
            _tl  = tl_q;    _dt  = bsQ_dt
            _ebit = ebit_ttm; _rev = rev_ttm
            _ebit_qs = ttm_rows(q_is, "ebit", "Income_Statement.ebit")
            _rev_qs  = ttm_rows(q_is, "totalRevenue", "Income_Statement.totalRevenue")
            mode_note = "Cur: Balance Sheet from latest quarter; EBIT/Revenue as TTM (4-quarter sum)"

        wc = (_ca - _cl) if _ca is not None and _cl is not None else None
        x1 = safe(wc,   _ta); x2 = safe(_re,  _ta)
        x3 = safe(_ebit,_ta); x4 = safe(mcap,  _tl); x5 = safe(_rev, _ta)
        z  = (1.2*(x1 or 0) + 1.4*(x2 or 0) + 3.3*(x3 or 0) +
              0.6*(x4 or 0) + 1.0*(x5 or 0)) if all([x1, x2, x3, x4, x5]) else None
        zone = ("≥ 2.99 → Safe Zone" if z and z >= 2.99 else
                ("1.81–2.99 → Grey Zone" if z and z >= 1.81 else "< 1.81 → Distress Zone")) if z else "—"

        return {
            "formula": f"1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5\n>2.99 Safe | 1.81–2.99 Grey | <1.81 Distress\n{mode_note}",
            "fields": ["Balance_Sheet.totalCurrentAssets", "Balance_Sheet.totalCurrentLiabilities",
                       "Balance_Sheet.retainedEarnings", "Balance_Sheet.totalAssets",
                       "Balance_Sheet.totalLiab", "Income_Statement.ebit",
                       "Income_Statement.totalRevenue", "Highlights.MarketCapitalization"],
            "unit": "",
            "components": [
                ("── Balance Sheet inputs ──",                                                f"[{_dt}]"),
                (f"Balance_Sheet.totalCurrentAssets  [{_dt}]",                              raw(_ca)),
                (f"Balance_Sheet.totalCurrentLiabilities  [{_dt}]",                        raw(_cl)),
                (f"Working Capital = CA − CL  =  {raw(_ca)} − {raw(_cl)}",                raw(wc)),
                (f"Balance_Sheet.retainedEarnings  [{_dt}]",                               raw(_re)),
                (f"Balance_Sheet.totalAssets  [{_dt}]",                                    raw(_ta)),
                (f"Balance_Sheet.totalLiab  [{_dt}]",                                      raw(_tl)),
                (f"Highlights.MarketCapitalization",                                        raw(mcap)),
                (f"── EBIT {'TTM quarters' if not is_annual else isA_dt} ──",              ""),
                *_ebit_qs,
                (f"── Revenue {'TTM quarters' if not is_annual else isA_dt} ──",           ""),
                *_rev_qs,
                ("── Factor Calculation ──",                                                ""),
                (f"X1 = WC ÷ TA  =  {raw(wc)} ÷ {raw(_ta)}",                             num(x1, 6) if x1 else "—"),
                (f"X2 = RE ÷ TA  =  {raw(_re)} ÷ {raw(_ta)}",                            num(x2, 6) if x2 else "—"),
                (f"X3 = EBIT ÷ TA  =  {raw(_ebit)} ÷ {raw(_ta)}",                        num(x3, 6) if x3 else "—"),
                (f"X4 = MCap ÷ TL  =  {raw(mcap)} ÷ {raw(_tl)}",                         num(x4, 6) if x4 else "—"),
                (f"X5 = Rev ÷ TA  =  {raw(_rev)} ÷ {raw(_ta)}",                           num(x5, 6) if x5 else "—"),
                ("── Z-Score = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5 ──",         ""),
                (f"= 1.2·{num(x1,4)} + 1.4·{num(x2,4)} + 3.3·{num(x3,4)} + 0.6·{num(x4,4)} + 1.0·{num(x5,4)}", ""),
                ("── Result ──",                                                             ""),
                ("Altman Z-Score",                                                           num(z, 4) if z else "—"),
                ("Zone",                                                                     zone),
            ],
            "result": num(z, 2) if z else "—"}

    if "Piotroski" in L:
        return {
            "formula": "9 binary criteria (0 or 1 each) — sum = F-Score\n8–9 Strong | 5–7 Neutral | 0–4 Weak",
            "fields":  ["Income_Statement.netIncome", "Cash_Flow.totalCashFromOperatingActivities",
                        "Balance_Sheet.totalAssets", "Balance_Sheet.longTermDebt",
                        "Balance_Sheet.totalCurrentAssets", "Balance_Sheet.totalCurrentLiabilities",
                        "Balance_Sheet.commonStockSharesOutstanding",
                        "Income_Statement.grossProfit", "Income_Statement.totalRevenue"],
            "unit": "/9",
            "components": [
                ("── Profitability ──",          ""),
                ("F1: ROA > 0",                  "Net Income ÷ Total Assets > 0"),
                ("F2: CFO > 0",                  "Cash_Flow.totalCashFromOperatingActivities > 0"),
                ("F3: ΔROA > 0",                 "ROA[Y0] > ROA[Y-1]"),
                ("F4: Accrual (CFO > NI)",       "CFO ÷ TA > NI ÷ TA"),
                ("── Leverage / Liquidity ──",   ""),
                ("F5: Δ Long-Term Debt < 0",     "LTD/TA[Y0] < LTD/TA[Y-1]"),
                ("F6: Δ Current Ratio > 0",      "CurrentRatio[Y0] > CurrentRatio[Y-1]"),
                ("F7: No new shares issued",     "Shares[Y0] ≤ Shares[Y-1]"),
                ("── Efficiency ──",             ""),
                ("F8: Δ Gross Margin > 0",       "GrossMargin[Y0] > GrossMargin[Y-1]"),
                ("F9: Δ Asset Turnover > 0",     "AssetTurnover[Y0] > AssetTurnover[Y-1]"),
                ("── Result ──",                 ""),
                ("Score",                        "See Health tab for computed value"),
            ],
            "result": "See Health tab"}

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

    # Growth rows (Fwd / TTM / Ann / QoQ / YoY / CAGR for Rev, NI, EPS, FCF)
    q_growth = pick(gs["rows"],
        "Revenue Growth (Fwd)",      "Revenue Growth (TTM)",      "Revenue Growth (Ann)",
        "Revenue Growth (QoQ)",      "Revenue Growth (YoY)",
        "Revenue Growth (3Y CAGR)",  "Revenue Growth (5Y CAGR)",  "Revenue Growth (10Y CAGR)",
        "Net Income Growth (Fwd)",   "Net Income Growth (TTM)",   "Net Income Growth (Ann)",
        "Net Income Growth (QoQ)",   "Net Income Growth (YoY)",
        "Net Income Growth (3Y CAGR)","Net Income Growth (5Y CAGR)","Net Income Growth (10Y CAGR)",
        "EPS Growth (Fwd)",          "EPS Growth (TTM)",          "EPS Growth (Ann)",
        "EPS Growth (QoQ)",          "EPS Growth (YoY)",
        "EPS Growth (3Y CAGR)",      "EPS Growth (5Y CAGR)",      "EPS Growth (10Y CAGR)",
        "FCF Growth (TTM)",          "FCF Growth (Ann)",          "FCF Growth (QoQ)",
        "FCF Growth (YoY)",
        "FCF Growth (3Y CAGR)",      "FCF Growth (5Y CAGR)",      "FCF Growth (10Y CAGR)",
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
        "Gross Margin (Quarterly)",        "Gross Margin (TTM)",        "Gross Margin (Year)",
        "Net Margin (Quarterly)",          "Net Margin (TTM)",          "Net Margin (Year)",
        "EBIT Margin (Quarterly)",         "EBIT Margin (TTM)",         "EBIT Margin (Year)",
        "EBITDA Margin (Quarterly)",       "EBITDA Margin (TTM)",       "EBITDA Margin (Year)",
        "FCF Margin (Quarterly)",          "FCF Margin (TTM)",          "FCF Margin (Year)",
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
        cash = (fv(bs_d.get("cash")) or fv(bs_d.get("cashAndEquivalents")) or 0) + (fv(bs_d.get("shortTermInvestments")) or 0)
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
    cash_q  = (fv(bsQ.get("cash")) or fv(bsQ.get("cashAndEquivalents")) or 0) + (fv(bsQ.get("shortTermInvestments")) or 0)
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
    cash_a  = (fv(bsA.get("cash")) or fv(bsA.get("cashAndEquivalents")) or 0) + (fv(bsA.get("shortTermInvestments")) or 0)
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

    def hist_hy(fn, n):
        """Return [(year_str, value_or_None, reason_or_None)] for n years."""
        result = []
        for i in range(min(n, len(years_bs))):
            yr = years_bs[i][:4]
            v  = fn(i)
            if v is None:
                result.append((yr, None, "Wert nicht berechenbar"))
            else:
                result.append((yr, v, None))
        return result

    def h(fn, n):  return hist_avg(fn, n)
    def hy(fn, n): return hist_hy(fn, n)

    def yr_cd(i):
        bs = a_bs.get(years_bs[i], {}); cf = a_cf.get(years_bs[i], {})
        c = (fv(bs.get("cash")) or fv(bs.get("cashAndEquivalents")) or 0) + (fv(bs.get("shortTermInvestments")) or 0)
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
        c   = (fv(bs.get("cash")) or fv(bs.get("cashAndEquivalents")) or 0) + (fv(bs.get("shortTermInvestments")) or 0)
        cl  = fv(bs.get("totalCurrentLiabilities"))
        return safe(c, cl)
    def yr_de(i):
        bs  = a_bs.get(years_bs[i], {})
        d   = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        e   = fv(bs.get("totalStockholderEquity"))
        return safe(d, e)
    def yr_nde(i):
        bs  = a_bs.get(years_bs[i], {})
        c   = (fv(bs.get("cash")) or fv(bs.get("cashAndEquivalents")) or 0) + (fv(bs.get("shortTermInvestments")) or 0)
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
        c   = (fv(bs.get("cash")) or fv(bs.get("cashAndEquivalents")) or 0) + (fv(bs.get("shortTermInvestments")) or 0)
        d   = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d-(c or 0), fv(bs.get("totalAssets")))
    def yr_debit(i):
        bs = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {})
        d  = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d, fv(is_d.get("ebit")))
    def yr_ndebit(i):
        bs = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {})
        c  = (fv(bs.get("cash")) or fv(bs.get("cashAndEquivalents")) or 0) + (fv(bs.get("shortTermInvestments")) or 0)
        d  = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d-(c or 0), fv(is_d.get("ebit")))
    def yr_debitda(i):
        bs = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {})
        d  = (fv(bs.get("longTermDebt")) or 0)+(fv(bs.get("shortLongTermDebt")) or 0)
        return safe(d, fv(is_d.get("ebitda")))
    def yr_ndebitda(i):
        bs = a_bs.get(years_bs[i], {}); is_d= a_is.get(years_bs[i], {})
        c  = (fv(bs.get("cash")) or fv(bs.get("cashAndEquivalents")) or 0) + (fv(bs.get("shortTermInvestments")) or 0)
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

    def row(label, cur, avg3, avg5, avg10, T, invert=False, decimals=2,
            hy3=None, hy5=None, hy10=None):
        css, lbl = get_grade(cur, T) if cur is not None else ("grade-na", "—")
        f = lambda v: fmt_r(v, decimals) if v is not None else "—"
        def conv(hy):
            if not hy: return []
            result = []
            for item in hy:
                yr, v, reason = item if len(item) == 3 else (*item, None)
                result.append((yr, f(v) if v is not None else None, reason))
            return result
        return {
            "label": label, "fmt": f(cur),
            "css": css, "lbl": lbl,
            "avg3": f(avg3), "avg5": f(avg5), "avg10": f(avg10),
            "avg3_raw": avg3, "avg5_raw": avg5, "avg10_raw": avg10,
            "T": T, "higher": True, "pct": False, "decimals": decimals,
            "group": label.split("/")[0].split(" ")[0],
            "hy3":  conv(hy3),
            "hy5":  conv(hy5),
            "hy10": conv(hy10),
        }

    rows = [
        row("Cash/Debt (Quarterly)",      cd_q,        h(yr_cd,3),    h(yr_cd,5),    h(yr_cd,10),    CD_T, hy3=hy(yr_cd,3), hy5=hy(yr_cd,5), hy10=hy(yr_cd,10)),
        row("Cash/Debt (Year)",           cd_a,        h(yr_cd,3),    h(yr_cd,5),    h(yr_cd,10),    CD_T, hy3=hy(yr_cd,3), hy5=hy(yr_cd,5), hy10=hy(yr_cd,10)),
        row("Debt/Capital (Quarterly)",   dc_q,        h(yr_dc,3),    h(yr_dc,5),    h(yr_dc,10),    DCi_T, hy3=hy(yr_dc,3), hy5=hy(yr_dc,5), hy10=hy(yr_dc,10)),
        row("Debt/Capital (Year)",        dc_a,        h(yr_dc,3),    h(yr_dc,5),    h(yr_dc,10),    DCi_T, hy3=hy(yr_dc,3), hy5=hy(yr_dc,5), hy10=hy(yr_dc,10)),
        row("FCF/Debt (Quarterly)",       fd_q,        h(yr_fd,3),    h(yr_fd,5),    h(yr_fd,10),    FD_T, hy3=hy(yr_fd,3), hy5=hy(yr_fd,5), hy10=hy(yr_fd,10)),
        row("FCF/Debt (Year)",            fd_a,        h(yr_fd,3),    h(yr_fd,5),    h(yr_fd,10),    FD_T, hy3=hy(yr_fd,3), hy5=hy(yr_fd,5), hy10=hy(yr_fd,10)),
        row("Interest Coverage (TTM)",    ic_ttm,      h(yr_ic,3),    h(yr_ic,5),    h(yr_ic,10),    IC_T, hy3=hy(yr_ic,3), hy5=hy(yr_ic,5), hy10=hy(yr_ic,10)),
        row("Interest Coverage (Year)",   ic_a,        h(yr_ic,3),    h(yr_ic,5),    h(yr_ic,10),    IC_T, hy3=hy(yr_ic,3), hy5=hy(yr_ic,5), hy10=hy(yr_ic,10)),
        row("Cash Ratio (Quarterly)",     cr_q,        h(yr_cr,3),    h(yr_cr,5),    h(yr_cr,10),    CR_T, hy3=hy(yr_cr,3), hy5=hy(yr_cr,5), hy10=hy(yr_cr,10)),
        row("Cash Ratio (Year)",          cr_a,        h(yr_cr,3),    h(yr_cr,5),    h(yr_cr,10),    CR_T, hy3=hy(yr_cr,3), hy5=hy(yr_cr,5), hy10=hy(yr_cr,10)),
        row("Debt/Equity (Quarterly)",    de_q,        h(yr_de,3),    h(yr_de,5),    h(yr_de,10),    DEi_T, hy3=hy(yr_de,3), hy5=hy(yr_de,5), hy10=hy(yr_de,10)),
        row("Debt/Equity (Year)",         de_a,        h(yr_de,3),    h(yr_de,5),    h(yr_de,10),    DEi_T, hy3=hy(yr_de,3), hy5=hy(yr_de,5), hy10=hy(yr_de,10)),
        row("NetDebt/Equity (Quarterly)", nde_q,       h(yr_nde,3),    h(yr_nde,5),    h(yr_nde,10),   NDEi_T, hy3=hy(yr_nde,3), hy5=hy(yr_nde,5), hy10=hy(yr_nde,10)),
        row("NetDebt/Equity (Year)",      nde_a,       h(yr_nde,3),    h(yr_nde,5),    h(yr_nde,10),   NDEi_T, hy3=hy(yr_nde,3), hy5=hy(yr_nde,5), hy10=hy(yr_nde,10)),
        row("Equity/Assets (Quarterly)",  ea_q,        h(yr_ea,3),    h(yr_ea,5),    h(yr_ea,10),    EA_T, hy3=hy(yr_ea,3), hy5=hy(yr_ea,5), hy10=hy(yr_ea,10)),
        row("Equity/Assets (Year)",       ea_a,        h(yr_ea,3),    h(yr_ea,5),    h(yr_ea,10),    EA_T, hy3=hy(yr_ea,3), hy5=hy(yr_ea,5), hy10=hy(yr_ea,10)),
        row("Debt/Asset (Quarterly)",     da_q,        h(yr_da,3),    h(yr_da,5),    h(yr_da,10),    DAi_T, hy3=hy(yr_da,3), hy5=hy(yr_da,5), hy10=hy(yr_da,10)),
        row("Debt/Asset (Year)",          da_a,        h(yr_da,3),    h(yr_da,5),    h(yr_da,10),    DAi_T, hy3=hy(yr_da,3), hy5=hy(yr_da,5), hy10=hy(yr_da,10)),
        row("NetDebt/Asset (Quarterly)",  nda_q,       h(yr_nda,3),    h(yr_nda,5),    h(yr_nda,10),   NDEi_T, hy3=hy(yr_nda,3), hy5=hy(yr_nda,5), hy10=hy(yr_nda,10)),
        row("NetDebt/Asset (Year)",       nda_a,       h(yr_nda,3),    h(yr_nda,5),    h(yr_nda,10),   NDEi_T, hy3=hy(yr_nda,3), hy5=hy(yr_nda,5), hy10=hy(yr_nda,10)),
        row("Debt/EBIT (TTM)",            debit_ttm,   h(yr_debit,3),    h(yr_debit,5),    h(yr_debit,10), DEBITi_T, hy3=hy(yr_debit,3), hy5=hy(yr_debit,5), hy10=hy(yr_debit,10)),
        row("Debt/EBIT (Year)",           debit_a,     h(yr_debit,3),    h(yr_debit,5),    h(yr_debit,10), DEBITi_T, hy3=hy(yr_debit,3), hy5=hy(yr_debit,5), hy10=hy(yr_debit,10)),
        row("NetDebt/EBIT (TTM)",         ndebit_ttm,  h(yr_ndebit,3),h(yr_ndebit,5),h(yr_ndebit,10),NDEi_T, hy3=hy(yr_ndebit,3), hy5=hy(yr_ndebit,5), hy10=hy(yr_ndebit,10)),
        row("NetDebt/EBIT (Year)",        ndebit_a,    h(yr_ndebit,3),h(yr_ndebit,5),h(yr_ndebit,10),NDEi_T, hy3=hy(yr_ndebit,3), hy5=hy(yr_ndebit,5), hy10=hy(yr_ndebit,10)),
        row("Debt/EBITDA (TTM)",          debitda_ttm, h(yr_debitda,3),h(yr_debitda,5),h(yr_debitda,10),DEBITi_T, hy3=hy(yr_debitda,3), hy5=hy(yr_debitda,5), hy10=hy(yr_debitda,10)),
        row("Debt/EBITDA (Year)",         debitda_a,   h(yr_debitda,3),h(yr_debitda,5),h(yr_debitda,10),DEBITi_T, hy3=hy(yr_debitda,3), hy5=hy(yr_debitda,5), hy10=hy(yr_debitda,10)),
        row("NetDebt/EBITDA (TTM)",       ndebitda_ttm,h(yr_ndebitda,3),h(yr_ndebitda,5),h(yr_ndebitda,10),NDEi_T, hy3=hy(yr_ndebitda,3), hy5=hy(yr_ndebitda,5), hy10=hy(yr_ndebitda,10)),
        row("NetDebt/EBITDA (Year)",      ndebitda_a,  h(yr_ndebitda,3),h(yr_ndebitda,5),h(yr_ndebitda,10),NDEi_T, hy3=hy(yr_ndebitda,3), hy5=hy(yr_ndebitda,5), hy10=hy(yr_ndebitda,10)),
        row("Current Ratio (Quarterly)",  cur_q,       h(yr_cur,3),    h(yr_cur,5),    h(yr_cur,10),   CURR_T, hy3=hy(yr_cur,3), hy5=hy(yr_cur,5), hy10=hy(yr_cur,10)),
        row("Current Ratio (Year)",       cur_a,       h(yr_cur,3),    h(yr_cur,5),    h(yr_cur,10),   CURR_T, hy3=hy(yr_cur,3), hy5=hy(yr_cur,5), hy10=hy(yr_cur,10)),
        row("Quick Ratio (Quarterly)",    qr_q,        h(yr_qr,3),    h(yr_qr,5),    h(yr_qr,10),    CURR_T, hy3=hy(yr_qr,3), hy5=hy(yr_qr,5), hy10=hy(yr_qr,10)),
        row("Quick Ratio (Year)",         qr_a,        h(yr_qr,3),    h(yr_qr,5),    h(yr_qr,10),    CURR_T, hy3=hy(yr_qr,3), hy5=hy(yr_qr,5), hy10=hy(yr_qr,10)),
        row("Altman Z-Score (Cur)",       az_cur,      h(yr_az,3),    h(yr_az,5),    h(yr_az,10),    AZ_T, hy3=hy(yr_az,3), hy5=hy(yr_az,5), hy10=hy(yr_az,10)),
        row("Altman Z-Score (Year)",      az_a,        h(yr_az,3),    h(yr_az,5),    h(yr_az,10),    AZ_T, hy3=hy(yr_az,3), hy5=hy(yr_az,5), hy10=hy(yr_az,10)),
    ]

    def yr_pf(i):
        if i + 1 >= len(years_bs): return None
        y    = years_bs[i]
        is_d = a_is.get(y, {}); cf_d = a_cf.get(y, {}); bs_d = a_bs.get(y, {})
        bs_p = a_bs.get(years_bs[i + 1], {})
        return piotroski(is_d, cf_d, bs_d, bs_p)

    rows += [
        row("Piotroski F-Score (Cur)",  pf_cur, h(yr_pf,3),    h(yr_pf,5),    h(yr_pf,10), PF_T, decimals=0, hy3=hy(yr_pf,3), hy5=hy(yr_pf,5), hy10=hy(yr_pf,10)),
        row("Piotroski F-Score (Year)", pf_a,   h(yr_pf,3),    h(yr_pf,5),    h(yr_pf,10), PF_T, decimals=0, hy3=hy(yr_pf,3), hy5=hy(yr_pf,5), hy10=hy(yr_pf,10)),
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
    a_bs = data["Financials"]["Balance_Sheet"].get("yearly", {})
    q_is = data["Financials"]["Income_Statement"].get("quarterly", {})
    q_cf = data["Financials"]["Cash_Flow"].get("quarterly", {})
    q_bs = data["Financials"]["Balance_Sheet"].get("quarterly", {})

    years_is = sorted(a_is.keys(), reverse=True)
    years_cf = sorted(a_cf.keys(), reverse=True)

    # ── TTM growth: rolling 4-quarter sum now vs 1Y ago ──────────────
    def ttm_gr(stmt, key):
        qs = sorted(stmt.keys(), reverse=True)
        rows = []
        for i in range(len(qs) - 3):
            w = qs[i:i+4]
            vals = [fv(stmt[q].get(key)) for q in w]
            if all(v is not None for v in vals):
                rows.append(sum(vals))
        if len(rows) >= 5 and rows[4] and rows[4] > 0:
            return (rows[0] / rows[4] - 1) * 100
        return None

    # ── Annual YoY: year[0] vs year[1] (kept for Rule of 40 only) ────
    def yr_gr(stmt, key):
        import math
        ys = sorted(stmt.keys(), reverse=True)
        if len(ys) < 2: return None
        v0 = fv(stmt[ys[0]].get(key))
        v1 = fv(stmt[ys[1]].get(key))
        if v0 is None or not v1 or v1 <= 0: return None
        r = (v0 / v1 - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r

    # ── CAGR: (V0 / Vn)^(1/n) − 1 ───────────────────────────────────
    def cagr(stmt, key, n):
        import math
        ys = sorted(stmt.keys(), reverse=True)
        if len(ys) < n + 1: return None
        v0 = fv(stmt[ys[0]].get(key))
        vn = fv(stmt[ys[n]].get(key))
        if v0 is None or not vn or vn <= 0: return None
        ratio = v0 / vn
        if ratio < 0: return None  # negative base -> complex result
        r = (ratio ** (1 / n) - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r

    def get_eps_annual(y):
        """EPS = NI / shares for a given annual period."""
        ni  = fv(a_is[y].get("netIncomeApplicableToCommonShares")) or fv(a_is[y].get("netIncome"))
        shs = fv(a_bs.get(y, {}).get("commonStockSharesOutstanding"))
        if ni is None or not shs or shs <= 0: return None
        return ni / shs

    def eps_cagr(n):
        import math
        ys = sorted(a_is.keys(), reverse=True)
        if len(ys) < n + 1: return None
        eps0 = get_eps_annual(ys[0])
        epsn = get_eps_annual(ys[n])
        if eps0 is None or not epsn or epsn <= 0: return None
        r = ((eps0 / epsn) ** (1 / n) - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r

    def eps_ttm_gr():
        """EPS TTM growth: (NI_TTM/shares_Q0) vs (NI_TTM_1Yago/shares_Q4)."""
        qs = sorted(q_is.keys(), reverse=True)
        qbs = sorted(q_bs.keys(), reverse=True)
        if len(qs) < 8 or len(qbs) < 5: return None
        def ttm_ni(start):
            vals = [fv(q_is[qs[i]].get("netIncomeApplicableToCommonShares"))
                    or fv(q_is[qs[i]].get("netIncome")) for i in range(start, start+4)]
            return sum(vals) if all(v is not None for v in vals) else None
        ni0  = ttm_ni(0); ni4  = ttm_ni(4)
        shs0 = fv(q_bs[qbs[0]].get("commonStockSharesOutstanding"))
        shs4 = fv(q_bs[qbs[4]].get("commonStockSharesOutstanding")) if len(qbs) > 4 else shs0
        if not ni0 or not ni4 or not shs0 or shs0 <= 0 or not shs4 or shs4 <= 0: return None
        eps0 = ni0 / shs0; eps4 = ni4 / shs4
        if eps4 <= 0: return None
        return (eps0 / eps4 - 1) * 100

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
        import math
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
        if len(rows) >= 5 and rows[4] and rows[4] > 0:
            r = (rows[0] / rows[4] - 1) * 100
            return None if (math.isnan(r) or math.isinf(r)) else r
        return None

    def fcf_cagr(n):
        import math
        ys = sorted(a_cf.keys(), reverse=True)
        if len(ys) < n + 1: return None
        v0 = fcf_yr(ys[0]); vn = fcf_yr(ys[n])
        if v0 is None or not vn or vn <= 0: return None
        ratio = v0 / vn
        if ratio < 0: return None  # negative base -> complex result
        r = (ratio ** (1 / n) - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r

    # ── Forward estimates from Earnings Trends ────────────────────────
    trends = data.get("Earnings", {}).get("Trend", {})
    plus1y = next((v for v in trends.values() if v.get("period") == "+1y"), {})
    rev_gr_fwd = fv(plus1y.get("revenueEstimateGrowth"))
    if rev_gr_fwd: rev_gr_fwd *= 100
    ni_gr_fwd  = fv(plus1y.get("earningsEstimateGrowth"))
    if ni_gr_fwd: ni_gr_fwd *= 100
    eps_gr_fwd = ni_gr_fwd  # same source

    # ── TTM values ────────────────────────────────────────────────────
    rev_gr_ttm    = ttm_gr(q_is, "totalRevenue")
    ni_gr_ttm     = ttm_gr(q_is, "netIncome")
    eps_gr_ttm    = eps_ttm_gr()
    ebit_gr_ttm   = ttm_gr(q_is, "ebit")
    ebitda_gr_ttm = ttm_gr(q_is, "ebitda")
    fcf_gr_ttm_v  = fcf_gr_ttm()

    # ── Ann values (Y0 vs Y1 — full fiscal year) ────────────────────
    rev_gr_ann    = yr_gr(a_is, "totalRevenue")
    ni_gr_ann     = yr_gr(a_is, "netIncome")
    ebit_gr_ann   = yr_gr(a_is, "ebit")
    ebitda_gr_ann = yr_gr(a_is, "ebitda")
    fcf_gr_ann    = fcf_cagr(1)   # n=1 CAGR == simple annual YoY

    def eps_ann():
        ys = sorted(a_is.keys(), reverse=True)
        if len(ys) < 2: return None
        eps0 = get_eps_annual(ys[0])
        eps1 = get_eps_annual(ys[1])
        if eps0 is None or not eps1 or eps1 <= 0: return None
        return (eps0 / eps1 - 1) * 100
    eps_gr_ann = eps_ann()

    # ── QoQ values (Q0 vs Q1 — latest vs prior quarter) ──────────────
    def qoq_gr(stmt, key):
        import math
        qs = sorted(stmt.keys(), reverse=True)
        if len(qs) < 2: return None
        v0 = fv(stmt[qs[0]].get(key))
        v1 = fv(stmt[qs[1]].get(key))
        if v0 is None or not v1 or v1 <= 0: return None
        r = (v0 / v1 - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r

    rev_gr_qoq    = qoq_gr(q_is, "totalRevenue")
    ni_gr_qoq     = qoq_gr(q_is, "netIncome")
    ebit_gr_qoq   = qoq_gr(q_is, "ebit")
    ebitda_gr_qoq = qoq_gr(q_is, "ebitda")

    def fcf_qoq():
        qs = sorted(q_cf.keys(), reverse=True)
        if len(qs) < 2: return None
        def get_fcf_q(q):
            f = fv(q_cf[q].get("freeCashFlow"))
            if f is None:
                cfo   = fv(q_cf[q].get("totalCashFromOperatingActivities"))
                capex = fv(q_cf[q].get("capitalExpenditures"))
                f = cfo - abs(capex) if cfo and capex else None
            return f
        v0 = get_fcf_q(qs[0]); v1 = get_fcf_q(qs[1])
        if v0 is None or not v1 or v1 <= 0: return None
        import math; r = (v0 / v1 - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r
    fcf_gr_qoq = fcf_qoq()

    def eps_qoq():
        qs_is = sorted(q_is.keys(), reverse=True)
        qs_bs = sorted(q_bs.keys(), reverse=True)
        if len(qs_is) < 2 or len(qs_bs) < 2: return None
        def get_eps_q(qi, bi):
            ni  = fv(q_is[qs_is[qi]].get("netIncomeApplicableToCommonShares")) or fv(q_is[qs_is[qi]].get("netIncome"))
            shs = fv(q_bs[qs_bs[bi]].get("commonStockSharesOutstanding"))
            return (ni / shs) if ni and shs and shs > 0 else None
        eps0 = get_eps_q(0, 0); eps1 = get_eps_q(1, 1)
        if eps0 is None or not eps1 or eps1 <= 0: return None
        import math; r = (eps0 / eps1 - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r
    eps_gr_qoq = eps_qoq()

    # ── YoY quarterly values (Q0 vs Q4 — same quarter prior year) ──────
    def yoq_gr(stmt, key):
        import math
        qs = sorted(stmt.keys(), reverse=True)
        if len(qs) < 5: return None
        v0 = fv(stmt[qs[0]].get(key))
        v4 = fv(stmt[qs[4]].get(key))
        if v0 is None or v4 is None or v4 <= 0: return None
        r = (v0 / v4 - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r

    rev_gr_yoq    = yoq_gr(q_is, "totalRevenue")
    ni_gr_yoq     = yoq_gr(q_is, "netIncome")
    ebit_gr_yoq   = yoq_gr(q_is, "ebit")
    ebitda_gr_yoq = yoq_gr(q_is, "ebitda")

    def fcf_yoq():
        qs = sorted(q_cf.keys(), reverse=True)
        if len(qs) < 5: return None
        def get_fcf_q(q):
            f = fv(q_cf[q].get("freeCashFlow"))
            if f is None:
                cfo   = fv(q_cf[q].get("totalCashFromOperatingActivities"))
                capex = fv(q_cf[q].get("capitalExpenditures"))
                f = cfo - abs(capex) if cfo and capex else None
            return f
        v0 = get_fcf_q(qs[0]); v4 = get_fcf_q(qs[4])
        if v0 is None or not v4 or v4 <= 0: return None
        import math; r = (v0 / v4 - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r
    fcf_gr_yoq = fcf_yoq()

    def eps_yoq():
        qs_is = sorted(q_is.keys(), reverse=True)
        qs_bs = sorted(q_bs.keys(), reverse=True)
        if len(qs_is) < 5 or len(qs_bs) < 5: return None
        def get_eps_q(qi, bi):
            ni  = fv(q_is[qs_is[qi]].get("netIncomeApplicableToCommonShares")) or fv(q_is[qs_is[qi]].get("netIncome"))
            shs = fv(q_bs[qs_bs[bi]].get("commonStockSharesOutstanding"))
            return (ni / shs) if ni and shs and shs > 0 else None
        eps0 = get_eps_q(0, 0); eps4 = get_eps_q(4, 4)
        if eps0 is None or not eps4 or eps4 <= 0: return None
        import math; r = (eps0 / eps4 - 1) * 100
        return None if (math.isnan(r) or math.isinf(r)) else r
    eps_gr_yoq = eps_yoq()

    # ── CAGR values ───────────────────────────────────────────────────
    rev_3y  = cagr(a_is, "totalRevenue", 3);   rev_5y  = cagr(a_is, "totalRevenue", 5);   rev_10y  = cagr(a_is, "totalRevenue", 10)
    ni_3y   = cagr(a_is, "netIncome",    3);   ni_5y   = cagr(a_is, "netIncome",    5);   ni_10y   = cagr(a_is, "netIncome",    10)
    eps_3y  = eps_cagr(3);                     eps_5y  = eps_cagr(5);                     eps_10y  = eps_cagr(10)
    ebit_3y = cagr(a_is, "ebit",   3);        ebit_5y = cagr(a_is, "ebit",   5);        ebit_10y = cagr(a_is, "ebit",   10)
    ebitda_3y= cagr(a_is, "ebitda", 3);       ebitda_5y= cagr(a_is, "ebitda", 5);       ebitda_10y= cagr(a_is, "ebitda", 10)
    fcf_3y  = fcf_cagr(3);                    fcf_5y  = fcf_cagr(5);                    fcf_10y  = fcf_cagr(10)

    # ── Rule of 40 (keeps YoY rev growth as per convention) ──────────
    rev_gr_yr = yr_gr(a_is, "totalRevenue")
    rev_ttm_v = sum(fv(q_is[q].get("totalRevenue")) or 0 for q in sorted(q_is.keys(), reverse=True)[:4])
    fcf_ttm_v = fcf_ttm_sum()
    fcfm_ttm  = fcf_ttm_v / rev_ttm_v * 100 if rev_ttm_v and fcf_ttm_v is not None else None
    ro40_ttm  = (rev_gr_ttm or 0) + (fcfm_ttm or 0) if rev_gr_ttm is not None and fcfm_ttm is not None else None

    rev_yr_v  = fv(a_is[years_is[0]].get("totalRevenue")) if years_is else None
    fcf_yr_v  = fcf_yr(years_is[0]) if years_is else None
    fcfm_yr   = fcf_yr_v / rev_yr_v * 100 if rev_yr_v and fcf_yr_v is not None else None
    ro40_yr   = (rev_gr_yr or 0) + (fcfm_yr or 0) if rev_gr_yr is not None and fcfm_yr is not None else None

    def ro40_hist(n):
        ys = sorted(a_is.keys(), reverse=True)
        vals, all_yr = [], []
        for i in range(min(n, len(ys) - 1)):
            yr = ys[i][:4]
            r0 = fv(a_is[ys[i]].get("totalRevenue"))
            r1 = fv(a_is[ys[i+1]].get("totalRevenue"))
            if not r0 or not r1 or r1 <= 0:
                all_yr.append((yr, None, "Revenue fehlt/0")); continue
            rg = (r0/r1 - 1)*100
            fc = fcf_yr(ys[i])
            if fc is None:
                all_yr.append((yr, None, "FCF fehlt")); continue
            fm = fc/r0*100 if r0 > 0 else None
            if fm is None:
                all_yr.append((yr, None, "FCF Margin nicht berechenbar")); continue
            v = rg + fm
            vals.append(v); all_yr.append((yr, v, None))
        avg = sum(vals)/len(vals) if vals else None
        return avg, all_yr

    ro40_3y,  _hy_ro40_3  = ro40_hist(3)
    ro40_5y,  _hy_ro40_5  = ro40_hist(5)
    ro40_10y, _hy_ro40_10 = ro40_hist(10)

    # ── Grade thresholds ─────────────────────────────────────────────
    # Single-period (Fwd, TTM): higher expected volatility
    REV_T    = [(30,"ap"),(20,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-5,"cp"),(-10,"c")]
    NI_T     = [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    EPS_T    = [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    EBIT_T   = [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    EBITDA_T = [(40,"ap"),(25,"a"),(15,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    FCF_T    = [(50,"ap"),(30,"a"),(20,"am"),(10,"bp"),(5,"b"),(0,"bm"),(-10,"cp"),(-20,"c")]
    RO40_T   = [(60,"ap"),(50,"a"),(40,"am"),(30,"bp"),(20,"b"),(10,"bm"),(0,"cp"),(-10,"c")]
    # CAGR: smoother, lower thresholds
    REV_CAGR_T    = [(15,"ap"),(10,"a"),(7,"am"),(5,"bp"),(3,"b"),(0,"bm"),(-3,"cp"),(-7,"c")]
    NI_CAGR_T     = [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(3,"b"),(0,"bm"),(-5,"cp"),(-10,"c")]
    EPS_CAGR_T    = [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(3,"b"),(0,"bm"),(-5,"cp"),(-10,"c")]
    EBIT_CAGR_T   = [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(3,"b"),(0,"bm"),(-5,"cp"),(-10,"c")]
    EBITDA_CAGR_T = [(15,"ap"),(12,"a"),(8,"am"),(5,"bp"),(3,"b"),(0,"bm"),(-5,"cp"),(-10,"c")]
    FCF_CAGR_T    = [(20,"ap"),(15,"a"),(10,"am"),(7,"bp"),(3,"b"),(0,"bm"),(-5,"cp"),(-10,"c")]

    def fmt(v): return f"{v:.2f} %" if v is not None else "—"

    def row(label, cur, avg3, avg5, avg10, T):
        css, lbl = get_grade(cur, T) if cur is not None else ("grade-na", "—")
        return {
            "label": label, "fmt": fmt(cur),
            "css": css, "lbl": lbl,
            "avg3":  fmt(avg3),
            "avg5":  fmt(avg5),
            "avg10": fmt(avg10),
            "avg3_raw": avg3, "avg5_raw": avg5, "avg10_raw": avg10,
            "T": T, "higher": True, "pct": False,
            "group": label.split(" ")[0],
        }

    rows = [
        # Revenue
        row("Revenue Growth (Fwd)",         rev_gr_fwd,    rev_3y,    rev_5y,    rev_10y,    REV_T),
        row("Revenue Growth (TTM)",          rev_gr_ttm,    rev_3y,    rev_5y,    rev_10y,    REV_T),
        row("Revenue Growth (Ann)",          rev_gr_ann,    rev_3y,    rev_5y,    rev_10y,    REV_T),
        row("Revenue Growth (QoQ)",          rev_gr_qoq,    rev_3y,    rev_5y,    rev_10y,    REV_T),
        row("Revenue Growth (YoY)",          rev_gr_yoq,    rev_3y,    rev_5y,    rev_10y,    REV_T),
        row("  ↳ Revenue Growth (3Y CAGR)",      rev_3y,        None,      None,      None,       REV_CAGR_T),
        row("  ↳ Revenue Growth (5Y CAGR)",      rev_5y,        None,      None,      None,       REV_CAGR_T),
        row("  ↳ Revenue Growth (10Y CAGR)",     rev_10y,       None,      None,      None,       REV_CAGR_T),
        # Net Income
        row("Net Income Growth (Fwd)",       ni_gr_fwd,     ni_3y,     ni_5y,     ni_10y,     NI_T),
        row("Net Income Growth (TTM)",       ni_gr_ttm,     ni_3y,     ni_5y,     ni_10y,     NI_T),
        row("Net Income Growth (Ann)",       ni_gr_ann,     ni_3y,     ni_5y,     ni_10y,     NI_T),
        row("Net Income Growth (QoQ)",       ni_gr_qoq,     ni_3y,     ni_5y,     ni_10y,     NI_T),
        row("Net Income Growth (YoY)",       ni_gr_yoq,     ni_3y,     ni_5y,     ni_10y,     NI_T),
        row("  ↳ Net Income Growth (3Y CAGR)",   ni_3y,         None,      None,      None,       NI_CAGR_T),
        row("  ↳ Net Income Growth (5Y CAGR)",   ni_5y,         None,      None,      None,       NI_CAGR_T),
        row("  ↳ Net Income Growth (10Y CAGR)",  ni_10y,        None,      None,      None,       NI_CAGR_T),
        # EPS
        row("EPS Growth (Fwd)",              eps_gr_fwd,    eps_3y,    eps_5y,    eps_10y,    EPS_T),
        row("EPS Growth (TTM)",              eps_gr_ttm,    eps_3y,    eps_5y,    eps_10y,    EPS_T),
        row("EPS Growth (Ann)",              eps_gr_ann,    eps_3y,    eps_5y,    eps_10y,    EPS_T),
        row("EPS Growth (QoQ)",              eps_gr_qoq,    eps_3y,    eps_5y,    eps_10y,    EPS_T),
        row("EPS Growth (YoY)",              eps_gr_yoq,    eps_3y,    eps_5y,    eps_10y,    EPS_T),
        row("  ↳ EPS Growth (3Y CAGR)",          eps_3y,        None,      None,      None,       EPS_CAGR_T),
        row("  ↳ EPS Growth (5Y CAGR)",          eps_5y,        None,      None,      None,       EPS_CAGR_T),
        row("  ↳ EPS Growth (10Y CAGR)",         eps_10y,       None,      None,      None,       EPS_CAGR_T),
        # EBIT
        row("EBIT Growth (TTM)",             ebit_gr_ttm,   ebit_3y,   ebit_5y,   ebit_10y,   EBIT_T),
        row("EBIT Growth (Ann)",             ebit_gr_ann,   ebit_3y,   ebit_5y,   ebit_10y,   EBIT_T),
        row("EBIT Growth (QoQ)",             ebit_gr_qoq,   ebit_3y,   ebit_5y,   ebit_10y,   EBIT_T),
        row("EBIT Growth (YoY)",             ebit_gr_yoq,   ebit_3y,   ebit_5y,   ebit_10y,   EBIT_T),
        row("  ↳ EBIT Growth (3Y CAGR)",         ebit_3y,       None,      None,      None,       EBIT_CAGR_T),
        row("  ↳ EBIT Growth (5Y CAGR)",         ebit_5y,       None,      None,      None,       EBIT_CAGR_T),
        row("  ↳ EBIT Growth (10Y CAGR)",        ebit_10y,      None,      None,      None,       EBIT_CAGR_T),
        # EBITDA
        row("EBITDA Growth (TTM)",           ebitda_gr_ttm, ebitda_3y, ebitda_5y, ebitda_10y, EBITDA_T),
        row("EBITDA Growth (Ann)",           ebitda_gr_ann, ebitda_3y, ebitda_5y, ebitda_10y, EBITDA_T),
        row("EBITDA Growth (QoQ)",           ebitda_gr_qoq, ebitda_3y, ebitda_5y, ebitda_10y, EBITDA_T),
        row("EBITDA Growth (YoY)",           ebitda_gr_yoq, ebitda_3y, ebitda_5y, ebitda_10y, EBITDA_T),
        row("  ↳ EBITDA Growth (3Y CAGR)",       ebitda_3y,     None,      None,      None,       EBITDA_CAGR_T),
        row("  ↳ EBITDA Growth (5Y CAGR)",       ebitda_5y,     None,      None,      None,       EBITDA_CAGR_T),
        row("  ↳ EBITDA Growth (10Y CAGR)",      ebitda_10y,    None,      None,      None,       EBITDA_CAGR_T),
        # FCF
        row("FCF Growth (TTM)",              fcf_gr_ttm_v,  fcf_3y,    fcf_5y,    fcf_10y,    FCF_T),
        row("FCF Growth (Ann)",              fcf_gr_ann,    fcf_3y,    fcf_5y,    fcf_10y,    FCF_T),
        row("FCF Growth (QoQ)",              fcf_gr_qoq,    fcf_3y,    fcf_5y,    fcf_10y,    FCF_T),
        row("FCF Growth (YoY)",              fcf_gr_yoq,    fcf_3y,    fcf_5y,    fcf_10y,    FCF_T),
        row("  ↳ FCF Growth (3Y CAGR)",          fcf_3y,        None,      None,      None,       FCF_CAGR_T),
        row("  ↳ FCF Growth (5Y CAGR)",          fcf_5y,        None,      None,      None,       FCF_CAGR_T),
        row("  ↳ FCF Growth (10Y CAGR)",         fcf_10y,       None,      None,      None,       FCF_CAGR_T),
        # Rule of 40
        row("Rule of 40 (TTM)",              ro40_ttm,      ro40_3y,   ro40_5y,   ro40_10y,   RO40_T, hy3=_hy_ro40_3, hy5=_hy_ro40_5, hy10=_hy_ro40_10),
        row("Rule of 40 (Year)",             ro40_yr,       ro40_3y,   ro40_5y,   ro40_10y,   RO40_T, hy3=_hy_ro40_3, hy5=_hy_ro40_5, hy10=_hy_ro40_10),
    ]

    # ── Overall Score ─────────────────────────────────────────────────
    grade_score = {"ap":100,"a":92,"am":84,"bp":76,"b":68,"bm":60,"cp":52,"c":44,"cm":36,"d":28,"na":0}
    scores = [grade_score.get(r["css"].replace("grade-",""), 0) for r in rows if r["css"] != "grade-na"]
    overall_score = sum(scores) / len(scores) if scores else 0
    overall_css, overall_lbl = get_grade(overall_score, [
        (96,"ap"),(92,"a"),(84,"am"),(76,"bp"),(68,"b"),(60,"bm"),(52,"cp"),(44,"c"),(36,"cm"),(0,"d")
    ])

    # ── Chart data: annual YoY growth (for visual bar chart) ─────────
    chart_rows = []
    for i, y in enumerate(sorted(a_is.keys())):
        idx = sorted(a_is.keys(), reverse=True).index(y)
        ys  = sorted(a_is.keys(), reverse=True)
        if idx + 1 >= len(ys): continue
        y_prev = ys[idx + 1]
        def gr(stmt, key):
            v0 = fv(stmt.get(y, {}).get(key))
            v1 = fv(stmt.get(y_prev, {}).get(key))
            return (v0/v1 - 1) if v0 and v1 and v1 > 0 else None
        rev_g = gr(a_is, "totalRevenue")
        ni_g  = gr(a_is, "netIncome")
        ocf_g = gr(a_cf, "totalCashFromOperatingActivities")
        fc0   = fcf_yr(y); fc1 = fcf_yr(y_prev)
        fcf_g = (fc0/fc1 - 1) if fc0 is not None and fc1 and fc1 > 0 else None
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

    # ── Quarterly (Q0) margins ────────────────────────────────────────
    def _q0is(key): return fv(q_is[q_sorted[0]].get(key)) if q_sorted else None
    def _q0cf(key): return fv(q_cf[qcf_sorted[0]].get(key)) if qcf_sorted else None
    rev_q0    = _q0is("totalRevenue")
    gp_q0     = _q0is("grossProfit")
    oi_q0     = _q0is("operatingIncome")
    ni_q0     = _q0is("netIncome")
    ebit_q0   = _q0is("ebit")
    ebitda_q0 = _q0is("ebitda")
    _fcf_q0_raw = _q0cf("freeCashFlow")
    _cfo_q0     = _q0cf("totalCashFromOperatingActivities")
    _capex_q0   = _q0cf("capitalExpenditures")
    fcf_q0    = _fcf_q0_raw if _fcf_q0_raw is not None else (_cfo_q0 - abs(_capex_q0) if _cfo_q0 and _capex_q0 else None)
    gm_q      = safe_div(gp_q0,     rev_q0)
    om_q      = safe_div(oi_q0,     rev_q0)
    nm_q      = safe_div(ni_q0,     rev_q0)
    ebitm_q   = safe_div(ebit_q0,   rev_q0)
    ebitdam_q = safe_div(ebitda_q0, rev_q0)
    fcfm_q    = safe_div(fcf_q0,    rev_q0)

    # ── Historical averages ───────────────────────────────────────────
    def margin_hist(is_key_num, is_key_den, n, cf=False):
        ys = sorted(a_is.keys(), reverse=True)
        vals, all_yr = [], []
        for y in ys[:n]:
            yr = y[:4]
            num = fv((a_cf if cf else a_is)[y].get(is_key_num)) if y in (a_cf if cf else a_is) else None
            den = fv(a_is[y].get(is_key_den))
            if num is None:
                all_yr.append((yr, None, f"{is_key_num} fehlt")); continue
            if not den or den == 0:
                all_yr.append((yr, None, f"{is_key_den} fehlt/0")); continue
            v = num / den
            vals.append(v); all_yr.append((yr, v, None))
        avg = sum(vals)/len(vals) if vals else None
        return avg, all_yr

    def return_hist(ni_key, asset_key, n, use_avg=False):
        ys = sorted(a_is.keys(), reverse=True)
        vals, all_yr = [], []
        for i, y in enumerate(ys[:n]):
            yr  = y[:4]
            ni  = fv(a_is[y].get(ni_key))
            bs  = fv(a_bs[y].get(asset_key)) if y in a_bs else None
            if use_avg:
                bsy_all = sorted(a_bs.keys(), reverse=True)
                y_idx   = bsy_all.index(y) if y in bsy_all else None
                if y_idx is not None and y_idx + 1 < len(bsy_all):
                    bs_p = fv(a_bs[bsy_all[y_idx + 1]].get(asset_key))
                    bs = (bs + bs_p) / 2 if bs and bs_p else bs
            if ni is None:
                all_yr.append((yr, None, f"{ni_key} fehlt")); continue
            if not bs or bs == 0:
                all_yr.append((yr, None, f"{asset_key} fehlt/0")); continue
            v = ni / bs
            vals.append(v); all_yr.append((yr, v, None))
        avg = sum(vals)/len(vals) if vals else None
        return avg, all_yr

    def roce_hist(n):
        ys = sorted(a_is.keys(), reverse=True)
        vals, all_yr = [], []
        for y in ys[:n]:
            yr = y[:4]
            e  = fv(a_is[y].get("ebit"))
            bs = a_bs.get(y, {})
            ta = fv(bs.get("totalAssets"))
            cl = fv(bs.get("totalCurrentLiabilities"))
            if e is None:
                all_yr.append((yr, None, "EBIT fehlt")); continue
            if not ta or not cl:
                all_yr.append((yr, None, "Assets/CL fehlen")); continue
            v = e / (ta - cl)
            vals.append(v); all_yr.append((yr, v, None))
        avg = sum(vals)/len(vals) if vals else None
        return avg, all_yr

    def at_hist(n):
        ys = sorted(a_is.keys(), reverse=True)
        bsy_all = sorted(a_bs.keys(), reverse=True)
        vals, all_yr = [], []
        for y in ys[:n]:
            yr = y[:4]
            r = fv(a_is[y].get("totalRevenue"))
            a = fv(a_bs[y].get("totalAssets")) if y in a_bs else None
            y_idx = bsy_all.index(y) if y in bsy_all else None
            a_p   = fv(a_bs[bsy_all[y_idx + 1]].get("totalAssets")) if y_idx is not None and y_idx + 1 < len(bsy_all) else None
            a_avg = (a + a_p)/2 if a and a_p else a
            if not r:
                all_yr.append((yr, None, "Revenue fehlt")); continue
            if not a_avg or a_avg == 0:
                all_yr.append((yr, None, "Assets fehlen")); continue
            v = r / a_avg
            vals.append(v); all_yr.append((yr, v, None))
        avg = sum(vals)/len(vals) if vals else None
        return avg, all_yr

    def fcfm_hist(n):
        ys = sorted(a_is.keys(), reverse=True)
        vals, all_yr = [], []
        for y in ys[:n]:
            yr  = y[:4]
            rev = fv(a_is[y].get("totalRevenue"))
            fcf = fv(a_cf[y].get("freeCashFlow")) if y in a_cf else None
            if not fcf and y in a_cf:
                c  = fv(a_cf[y].get("totalCashFromOperatingActivities"))
                cx = fv(a_cf[y].get("capitalExpenditures"))
                fcf = c - abs(cx) if c and cx else None
            if not rev or rev == 0:
                all_yr.append((yr, None, "Revenue fehlt")); continue
            if fcf is None:
                all_yr.append((yr, None, "FCF fehlt")); continue
            v = fcf / rev
            vals.append(v); all_yr.append((yr, v, None))
        avg = sum(vals)/len(vals) if vals else None
        return avg, all_yr

    def roc_hist(n):
        ys  = sorted(a_is.keys(), reverse=True)
        vals, all_yr = [], []
        for i, y in enumerate(ys[:n]):
            yr  = y[:4]
            ni  = fv(a_is[y].get("netIncome"))
            bs  = a_bs.get(y, {})
            eq  = fv(bs.get("totalStockholderEquity"))
            ltd = fv(bs.get("longTermDebt")) or 0
            std = fv(bs.get("shortLongTermDebt")) or 0
            ic  = (eq or 0) + ltd + std
            if ni is None:
                all_yr.append((yr, None, "NI fehlt")); continue
            if ic <= 0:
                all_yr.append((yr, None, f"Inv.Capital ≤ 0 ({ic:,.0f})")); continue
            v = ni / ic
            vals.append(v); all_yr.append((yr, v, None))
        avg = sum(vals)/len(vals) if vals else None
        return avg, all_yr

    roa_3y,  _hy_roa_3  = return_hist("netIncome","totalAssets",3,use_avg=True)
    roa_5y,  _hy_roa_5  = return_hist("netIncome","totalAssets",5,use_avg=True)
    roa_10y, _hy_roa_10 = return_hist("netIncome","totalAssets",10,use_avg=True)
    roe_3y,  _hy_roe_3  = return_hist("netIncome","totalStockholderEquity",3,use_avg=True)
    roe_5y,  _hy_roe_5  = return_hist("netIncome","totalStockholderEquity",5,use_avg=True)
    roe_10y, _hy_roe_10 = return_hist("netIncome","totalStockholderEquity",10,use_avg=True)
    roc_3y,  _hy_roc_3  = roc_hist(3);  roc_5y,  _hy_roc_5  = roc_hist(5);  roc_10y, _hy_roc_10  = roc_hist(10)
    roce_3y, _hy_roce_3 = roce_hist(3); roce_5y, _hy_roce_5 = roce_hist(5); roce_10y,_hy_roce_10 = roce_hist(10)
    roic_3y, _hy_roic_3 = roc_hist(3);  roic_5y, _hy_roic_5 = roc_hist(5);  roic_10y,_hy_roic_10 = roc_hist(10)

    gm_3y,   _hy_gm_3   = margin_hist("grossProfit",    "totalRevenue",3)
    gm_5y,   _hy_gm_5   = margin_hist("grossProfit",    "totalRevenue",5)
    gm_10y,  _hy_gm_10  = margin_hist("grossProfit",    "totalRevenue",10)
    om_3y,   _hy_om_3   = margin_hist("operatingIncome","totalRevenue",3)
    om_5y,   _hy_om_5   = margin_hist("operatingIncome","totalRevenue",5)
    om_10y,  _hy_om_10  = margin_hist("operatingIncome","totalRevenue",10)
    nm_3y,   _hy_nm_3   = margin_hist("netIncome",      "totalRevenue",3)
    nm_5y,   _hy_nm_5   = margin_hist("netIncome",      "totalRevenue",5)
    nm_10y,  _hy_nm_10  = margin_hist("netIncome",      "totalRevenue",10)
    ebitm_3y,  _hy_ebitm_3  = margin_hist("ebit",   "totalRevenue",3)
    ebitm_5y,  _hy_ebitm_5  = margin_hist("ebit",   "totalRevenue",5)
    ebitm_10y, _hy_ebitm_10 = margin_hist("ebit",   "totalRevenue",10)
    ebitdam_3y,  _hy_ebitdam_3  = margin_hist("ebitda","totalRevenue",3)
    ebitdam_5y,  _hy_ebitdam_5  = margin_hist("ebitda","totalRevenue",5)
    ebitdam_10y, _hy_ebitdam_10 = margin_hist("ebitda","totalRevenue",10)
    fcfm_3y, _hy_fcfm_3 = fcfm_hist(3);  fcfm_5y, _hy_fcfm_5 = fcfm_hist(5);  fcfm_10y, _hy_fcfm_10 = fcfm_hist(10)
    at_3y,   _hy_at_3   = at_hist(3);    at_5y,   _hy_at_5   = at_hist(5);    at_10y,   _hy_at_10   = at_hist(10)

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

    def row(label, cur, avg3, avg5, avg10, T, pct=True, hy3=None, hy5=None, hy10=None):
        cur_pct = cur * 100 if cur is not None and pct else cur
        a3  = avg3  * 100 if avg3  is not None and pct else avg3
        a5  = avg5  * 100 if avg5  is not None and pct else avg5
        a10 = avg10 * 100 if avg10 is not None and pct else avg10
        css, lbl = get_grade(cur_pct if cur_pct is not None else cur, T) if cur is not None else ("grade-na","—")
        f = lambda v: (f"{v:.2f} %" if pct else f"{v:.2f}") if v is not None else "—"
        def conv(hy):
            if not hy: return []
            result = []
            for item in hy:
                yr, v, reason = item if len(item) == 3 else (*item, None)
                v_scaled = v * 100 if v is not None and pct else v
                fmt_v = f(v_scaled) if v_scaled is not None else None
                result.append((yr, fmt_v, reason))
            return result
        return {
            "label": label, "cur": cur_pct, "fmt": f(cur_pct if pct else cur),
            "css": css, "lbl": lbl,
            "avg3":  f(a3  if pct else avg3),
            "avg5":  f(a5  if pct else avg5),
            "avg10": f(a10 if pct else avg10),
            "avg3_raw": a3, "avg5_raw": a5, "avg10_raw": a10,
            "T": T, "higher": True, "pct": pct,
            "group": label.split(" ")[0],
            "hy3":  conv(hy3),
            "hy5":  conv(hy5),
            "hy10": conv(hy10),
        }

    rows = [
        row("Return on Assets (TTM)",           roa_ttm,     roa_3y,     roa_5y,     roa_10y,     ROA_T, hy3=_hy_roa_3, hy5=_hy_roa_5, hy10=_hy_roa_10),
        row("Return on Assets (Year)",           roa_yr,      roa_3y,     roa_5y,     roa_10y,     ROA_T, hy3=_hy_roa_3, hy5=_hy_roa_5, hy10=_hy_roa_10),
        row("Return on Equity (TTM)",            roe_ttm,     roe_3y,     roe_5y,     roe_10y,     ROE_T, hy3=_hy_roe_3, hy5=_hy_roe_5, hy10=_hy_roe_10),
        row("Return on Equity (Year)",           roe_yr,      roe_3y,     roe_5y,     roe_10y,     ROE_T, hy3=_hy_roe_3, hy5=_hy_roe_5, hy10=_hy_roe_10),
        row("Return on Capital (TTM)",           roc_ttm,     roc_3y,     roc_5y,     roc_10y,     ROC_T, hy3=_hy_roc_3, hy5=_hy_roc_5, hy10=_hy_roc_10),
        row("Return on Capital (Year)",          roc_yr,      roc_3y,     roc_5y,     roc_10y,     ROC_T, hy3=_hy_roc_3, hy5=_hy_roc_5, hy10=_hy_roc_10),
        row("Return on Cap. Empl. (TTM)",        roce_ttm,    roce_3y,    roce_5y,    roce_10y,    ROCE_T, hy3=_hy_roce_3, hy5=_hy_roce_5, hy10=_hy_roce_10),
        row("Return on Cap. Empl. (Year)",       roce_yr,     roce_3y,    roce_5y,    roce_10y,    ROCE_T, hy3=_hy_roce_3, hy5=_hy_roce_5, hy10=_hy_roce_10),
        row("Return on Inv. Capital (TTM)",      roic_ttm,    roic_3y,    roic_5y,    roic_10y,    ROIC_T, hy3=_hy_roic_3, hy5=_hy_roic_5, hy10=_hy_roic_10),
        row("Return on Inv. Capital (Year)",     roic_yr,     roic_3y,    roic_5y,    roic_10y,    ROIC_T, hy3=_hy_roic_3, hy5=_hy_roic_5, hy10=_hy_roic_10),
        row("Gross Margin (Quarterly)",          gm_q,        gm_3y,      gm_5y,      gm_10y,      GM_T, hy3=_hy_gm_3, hy5=_hy_gm_5, hy10=_hy_gm_10),
        row("Gross Margin (TTM)",                gm_ttm,      gm_3y,      gm_5y,      gm_10y,      GM_T, hy3=_hy_gm_3, hy5=_hy_gm_5, hy10=_hy_gm_10),
        row("Gross Margin (Year)",               gm_yr,       gm_3y,      gm_5y,      gm_10y,      GM_T, hy3=_hy_gm_3, hy5=_hy_gm_5, hy10=_hy_gm_10),
        row("Operating Margin (Quarterly)",      om_q,        om_3y,      om_5y,      om_10y,      OM_T, hy3=_hy_om_3, hy5=_hy_om_5, hy10=_hy_om_10),
        row("Operating Margin (TTM)",            om_ttm,      om_3y,      om_5y,      om_10y,      OM_T, hy3=_hy_om_3, hy5=_hy_om_5, hy10=_hy_om_10),
        row("Operating Margin (Year)",           om_yr,       om_3y,      om_5y,      om_10y,      OM_T, hy3=_hy_om_3, hy5=_hy_om_5, hy10=_hy_om_10),
        row("Net Margin (Quarterly)",            nm_q,        nm_3y,      nm_5y,      nm_10y,      NM_T, hy3=_hy_nm_3, hy5=_hy_nm_5, hy10=_hy_nm_10),
        row("Net Margin (TTM)",                  nm_ttm,      nm_3y,      nm_5y,      nm_10y,      NM_T, hy3=_hy_nm_3, hy5=_hy_nm_5, hy10=_hy_nm_10),
        row("Net Margin (Year)",                 nm_yr,       nm_3y,      nm_5y,      nm_10y,      NM_T, hy3=_hy_nm_3, hy5=_hy_nm_5, hy10=_hy_nm_10),
        row("EBIT Margin (Quarterly)",           ebitm_q,     ebitm_3y,   ebitm_5y,   ebitm_10y,   EBITM_T, hy3=_hy_ebitm_3, hy5=_hy_ebitm_5, hy10=_hy_ebitm_10),
        row("EBIT Margin (TTM)",                 ebitm_ttm,   ebitm_3y,   ebitm_5y,   ebitm_10y,   EBITM_T, hy3=_hy_ebitm_3, hy5=_hy_ebitm_5, hy10=_hy_ebitm_10),
        row("EBIT Margin (Year)",                ebitm_yr,    ebitm_3y,   ebitm_5y,   ebitm_10y,   EBITM_T, hy3=_hy_ebitm_3, hy5=_hy_ebitm_5, hy10=_hy_ebitm_10),
        row("EBITDA Margin (Quarterly)",         ebitdam_q,   ebitdam_3y, ebitdam_5y, ebitdam_10y, EBITDAM_T, hy3=_hy_ebitdam_3, hy5=_hy_ebitdam_5, hy10=_hy_ebitdam_10),
        row("EBITDA Margin (TTM)",               ebitdam_ttm, ebitdam_3y, ebitdam_5y, ebitdam_10y, EBITDAM_T, hy3=_hy_ebitdam_3, hy5=_hy_ebitdam_5, hy10=_hy_ebitdam_10),
        row("EBITDA Margin (Year)",              ebitdam_yr,  ebitdam_3y, ebitdam_5y, ebitdam_10y, EBITDAM_T, hy3=_hy_ebitdam_3, hy5=_hy_ebitdam_5, hy10=_hy_ebitdam_10),
        row("FCF Margin (Quarterly)",            fcfm_q,      fcfm_3y,    fcfm_5y,    fcfm_10y,    FCFM_T, hy3=_hy_fcfm_3, hy5=_hy_fcfm_5, hy10=_hy_fcfm_10),
        row("FCF Margin (TTM)",                  fcfm_ttm,    fcfm_3y,    fcfm_5y,    fcfm_10y,    FCFM_T, hy3=_hy_fcfm_3, hy5=_hy_fcfm_5, hy10=_hy_fcfm_10),
        row("FCF Margin (Year)",                 fcfm_yr,     fcfm_3y,    fcfm_5y,    fcfm_10y,    FCFM_T, hy3=_hy_fcfm_3, hy5=_hy_fcfm_5, hy10=_hy_fcfm_10),
        row("Asset Turnover (TTM)",              at_ttm,      at_3y,      at_5y,      at_10y,      AT_T, pct=False, hy3=_hy_at_3, hy5=_hy_at_5, hy10=_hy_at_10),
        row("Asset Turnover (Year)",             at_yr,       at_3y,      at_5y,      at_10y,      AT_T, pct=False, hy3=_hy_at_3, hy5=_hy_at_5, hy10=_hy_at_10),
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
    st.markdown("## 📊 EOD Fundamentals Viewer")
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
            EOD Fundamentals Viewer
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
        ("P/Sales (Fwd)",     "ps_fwd"),
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
        ("Revenue Growth Ann",   "rev_gr_ann"),
        ("Revenue Growth TTM",   "rev_gr_ttm"),
        ("Revenue Growth YoY",   "rev_gr_yoy"),
        ("Earnings Growth Ann",  "earn_gr_ann"),
        ("Earnings Growth TTM",  "earn_gr_ttm"),
        ("Earnings Growth YoY",  "earn_gr_yoy"),
        ("EPS Growth Ann",       "eps_gr_ann"),
        ("EPS Growth TTM",       "eps_gr_ttm"),
        ("EPS Growth YoY",       "eps_gr_yoy"),
        ("EBIT Growth Ann",      "ebit_gr_ann"),
        ("EBIT Growth TTM",      "ebit_gr_ttm"),
        ("EBIT Growth YoY",      "ebit_gr_yoy"),
        ("EBITDA Growth Ann",    "ebitda_gr_ann"),
        ("EBITDA Growth TTM",    "ebitda_gr_ttm"),
        ("EBITDA Growth YoY",    "ebitda_gr_yoy"),
        ("FCF Growth Ann",       "fcf_gr_ann"),
        ("FCF Growth TTM",       "fcf_gr_ttm"),
        ("FCF Growth YoY",       "fcf_gr_yoy"),
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
            cae_s  = df_bs_chart.get("cashAndEquivalents", pd.Series(dtype=float))
            # Use cash as primary; fall back to cashAndEquivalents where cash is null
            cash_s = cash_s.combine_first(cae_s)
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
        rows_show = expand_rows_with_avgs(rows_show)

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
                is_avg = r.get("is_avg_row", False)
                if is_avg:
                    hdr_html += f'''
                <tr style="border-bottom:1px solid #161d2e;background:#0d1320;">
                  <td style="padding:3px 4px 3px 18px;color:#64748b;font-size:11px;font-style:italic;">{r["label"]}</td>
                  <td style="padding:3px 4px;text-align:right;color:#94a3b8;font-size:11px;">{r["fmt"]}</td>
                  <td style="padding:3px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td colspan="3"></td>
                </tr>'''
                else:
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
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.download_button(
                label="⬇ Excel Download",
                data=score_rows_to_excel(rows_show, "Value_Score"),
                file_name=f"{(g.get('Code','') + '_' + g.get('Exchange','')).strip('_')}_Value_Score.csv",
                mime="text/csv",
                key="dl_value_score",
            )

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
        rows_show = expand_rows_with_avgs(rows_show)

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
                is_avg = r.get("is_avg_row", False)
                if is_avg:
                    tbl += f'''
                <tr style="border-bottom:1px solid #161d2e;background:#0d1320;">
                  <td style="padding:3px 4px 3px 18px;color:#64748b;font-size:11px;font-style:italic;">{r["label"]}</td>
                  <td style="padding:3px 4px;text-align:right;color:#94a3b8;font-size:11px;">{r["fmt"]}</td>
                  <td style="padding:3px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td colspan="3"></td>
                </tr>'''
                else:
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
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.download_button(
                label="⬇ CSV Download",
                data=score_rows_to_excel(rows_show, "Profitability_Score"),
                file_name=f"{(g.get('Code','') + '_' + g.get('Exchange','')).strip('_')}_Profitability_Score.csv",
                mime="text/csv",
                key="dl_profit_score",
            )
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
                is_cagr = "CAGR" in r["label"]
                if is_cagr:
                    tbl += f'''
                <tr style="border-bottom:1px solid #161d2e;background:#0d1320;">
                  <td style="padding:3px 4px 3px 18px;color:#64748b;font-size:11px;font-style:italic;">{r["label"]}</td>
                  <td style="padding:3px 4px;text-align:right;color:#94a3b8;font-size:11px;">{r["fmt"]}</td>
                  <td style="padding:3px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td colspan="3"></td>
                </tr>'''
                else:
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
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.download_button(
                label="⬇ CSV Download",
                data=score_rows_to_excel(rows_show, "Growth_Score"),
                file_name=f"{(g.get('Code','') + '_' + g.get('Exchange','')).strip('_')}_Growth_Score.csv",
                mime="text/csv",
                key="dl_growth_score",
            )

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
        rows_show = expand_rows_with_avgs(rows_show)

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
                is_avg = r.get("is_avg_row", False)
                if is_avg:
                    tbl += f'''
                <tr style="border-bottom:1px solid #161d2e;background:#0d1320;">
                  <td style="padding:3px 4px 3px 18px;color:#64748b;font-size:11px;font-style:italic;">{r["label"]}</td>
                  <td style="padding:3px 4px;text-align:right;color:#94a3b8;font-size:11px;">{r["fmt"]}</td>
                  <td style="padding:3px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td colspan="3"></td>
                </tr>'''
                else:
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
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.download_button(
                label="⬇ CSV Download",
                data=score_rows_to_excel(rows_show, "Health_Score"),
                file_name=f"{(g.get('Code','') + '_' + g.get('Exchange','')).strip('_')}_Health_Score.csv",
                mime="text/csv",
                key="dl_health_score",
            )

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
        rows_show = expand_rows_with_avgs(rows_show)

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
                is_avg  = r.get("is_avg_row", False)
                is_cagr = "CAGR" in r["label"]
                if is_avg or is_cagr:
                    tbl += f'''
                <tr style="border-bottom:1px solid #161d2e;background:#0d1320;">
                  <td style="padding:3px 4px 3px 18px;color:#64748b;font-size:11px;font-style:italic;">{r["label"]}</td>
                  <td style="padding:3px 4px;text-align:right;color:#94a3b8;font-size:11px;">{r["fmt"]}</td>
                  <td style="padding:3px 4px;text-align:center;">{grade_badge(r["css"], r["lbl"])}</td>
                  <td colspan="3"></td>
                </tr>'''
                else:
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
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.download_button(
                label="⬇ CSV Download",
                data=score_rows_to_excel(rows_all, "Quality_Score"),
                file_name=f"{(g.get('Code','') + '_' + g.get('Exchange','')).strip('_')}_Quality_Score.csv",
                mime="text/csv",
                key="dl_quality_score",
            )

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

        qs_all = compute_quality_score(data, hl, price_data)
        all_rows = []
        for tag, sub_rows in [("💎 Value", vs["rows"]), ("📈 Profit", ps["rows"]),
                               ("🚀 Growth", gs["rows"]), ("🏥 Health",  hs["rows"])]:
            for r in sub_rows:
                all_rows.append({**r, "tab": tag})

        # ── Score header ──────────────────────────────────────────────
        avg_all = sum([vs["overall_score"], ps["overall_score"],
                       gs["overall_score"], hs["overall_score"],
                       qs_all["overall_score"]]) / 5
        overall_all_css, overall_all_lbl = get_grade(avg_all, [
            (96,"ap"),(92,"a"),(84,"am"),(76,"bp"),(68,"b"),(60,"bm"),
            (52,"cp"),(44,"c"),(36,"cm"),(0,"d")
        ])

        hcol1, hcol2, hcol3, hcol4, hcol5, hcol6 = st.columns([3, 1, 1, 1, 1, 1])
        with hcol1:
            st.markdown(
                f'<div style="font-size:20px;font-weight:700;color:#e2e8f0;">'
                f'All Metrics &nbsp;{grade_badge(overall_all_css, overall_all_lbl)}'
                f' <span style="font-size:14px;color:#64748b;font-weight:400;">'
                f'Avg {avg_all:.1f}</span></div>', unsafe_allow_html=True)
        for col, key, sc in zip([hcol2, hcol3, hcol4, hcol5, hcol6],
                                 ["💎 Value","📈 Profit","🚀 Growth","🏥 Health","⭐ Quality"],
                                 [vs, ps, gs, hs, qs_all]):
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
            rows_filtered = [r for r in rows_filtered
                             if search_filter.lower() in r["label"].lstrip("↳ ").lower()]

        # ── Expand rows with avg/CAGR sub-rows ─────────────────────
        rows_expanded = expand_rows_with_avgs(rows_filtered)
        label_list = [r["label"] for r in rows_expanded]

        # Init / validate selection
        if "all_selected_metric" not in st.session_state or            st.session_state["all_selected_metric"] not in label_list:
            st.session_state["all_selected_metric"] = label_list[0] if label_list else ""

        col_tbl, col_drill = st.columns([3, 2])

        with col_tbl:
            # ── st.dataframe with row selection (checkbox) ────────────
            df_all = pd.DataFrame([{
                "Metric":  r["label"],
                "Cat.":    r.get("tab", ""),
                "Value":   r["fmt"],
                "Grade":   r["lbl"],
                "3Y":      r.get("avg3", "—"),
                "5Y":      r.get("avg5", "—"),
                "10Y":     r.get("avg10", "—"),
            } for r in rows_expanded])

            if rows_expanded:
                # Row-level styling: AVG/CAGR rows get a dimmed background
                _is_sub = [
                    r.get("is_avg_row", False) or "CAGR" in r["label"]
                    for r in rows_expanded
                ]
                def _style_rows(row):
                    idx = row.name
                    if idx < len(_is_sub) and _is_sub[idx]:
                        return ["background-color: #0d1320; color: #4b5563; font-style: italic; font-size: 11px"] * len(row)
                    return [""] * len(row)

                styled_df = df_all.style.apply(_style_rows, axis=1)

                sel_event = st.dataframe(
                    styled_df,
                    use_container_width=True,
                    hide_index=True,
                    height=600,
                    on_select="rerun",
                    selection_mode="single-row",
                )
                # Update session state from clicked row
                if sel_event.selection.rows:
                    picked_idx = sel_event.selection.rows[0]
                    if 0 <= picked_idx < len(rows_expanded):
                        st.session_state["all_selected_metric"] = rows_expanded[picked_idx]["label"]
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            st.download_button(
                label="⬇ Excel Download",
                data=score_rows_to_excel(rows_expanded, "All_Score"),
                file_name=f"{(g.get('Code','') + '_' + g.get('Exchange','')).strip('_')}_All_Score.csv",
                mime="text/csv",
                key="dl_all_score",
            )

        with col_drill:
            sel = st.session_state.get("all_selected_metric", "")
            valid_labels = [r["label"] for r in rows_expanded]
            if sel not in valid_labels and valid_labels:
                sel = valid_labels[0]
                st.session_state["all_selected_metric"] = sel

            if sel:
                # For avg/CAGR sub-rows, find parent row for drilldown
                row_data = next((r for r in rows_expanded if r["label"] == sel), None)
                # Resolve actual drilldown label:
                # avg rows like "P/Earnings (3Y Avg)" → drilldown on "P/Earnings (Cur)"
                # CAGR rows like "Revenue Growth (3Y CAGR)" → drilldown directly
                import re as _re
                _avg_match = _re.match(r"^\s*↳\s*(.+?)\s*\((\d+Y) Avg\)$", sel)
                _cagr_match = _re.match(r"^\s*↳\s*(.+?)\s*\((\d+Y CAGR)\)$", sel)
                if _avg_match:
                    # Avg row: show dedicated avg explanation + parent drilldown
                    _base  = _avg_match.group(1).strip()   # e.g. "P/Earnings"
                    _nyrs  = _avg_match.group(2).replace("Y","")  # e.g. "3"
                    _parent = next((r for r in rows_expanded
                                   if not r.get("is_avg_row") and "↳" not in r["label"]
                                   and _re.sub(r"\s*\(.*?\)$","",r["label"]).strip() == _base), None)
                    drill_label = _parent["label"] if _parent else sel
                    # Override dd with avg explanation
                    _is_growth = "Growth" in sel
                    _is_value  = any(x in sel for x in ["P/","EV/","PEG","Yield"])
                    if _is_value:
                        _method = (
                            f"Average of the last {_nyrs} annual multiples\n"
                            f"Each year: MCap (year-end price × shares) / Fundamental\n"
                            f"Year-end prices sourced from Finqube DB\n"
                            f"Then: sum(multiples) / {_nyrs}"
                        )
                    elif _is_growth:
                        _method = (
                            f"Average of {_nyrs} annual YoY growth rates\n"
                            f"Each year: (V[y] / V[y-1] - 1) × 100\n"
                            f"Then: sum(rates) / {_nyrs}"
                        )
                    else:
                        _method = (
                            f"Average of the last {_nyrs} annual values\n"
                            f"Then: sum(values) / {_nyrs}"
                        )
                    drill_label = _parent["label"] if _parent else sel
                    # Build yearly breakdown table from hy_vals stored on the row
                    # hy_vals: [(year, fmt_val|None, reason|None), ...]
                    _hy_vals  = row_data.get("hy_vals", []) if row_data else []
                    _hy_comps = []
                    if _hy_vals:
                        _valid_count = 0
                        for item in _hy_vals:
                            yr, fv_str, reason = item if len(item) == 3 else (*item, None)
                            if fv_str is not None:
                                _hy_comps.append((f"  {yr}", fv_str, None))
                                _valid_count += 1
                            else:
                                _hy_comps.append((f"  {yr}", f"— übersprungen", reason or ""))
                        _hy_comps.append((f"  → Avg ({_valid_count} gültige Jahre)", row_data["fmt"] if row_data else "—", None))
                    else:
                        _hy_comps = [
                            (f"{_nyrs}Y Avg Value", row_data["fmt"] if row_data else "—", None),
                            ("── Based on same calculation as ──", "", None),
                            (f"→ See drilldown of: {drill_label}", "↓ below", None),
                        ]
                    dd = {
                        "formula": _method,
                        "fields":  [f"Same fields as: {drill_label}",
                                    "ℹ Historical year-end prices from Finqube DB (for value multiples)"],
                        "unit":    "",
                        "components": _hy_comps,
                        "result": row_data["fmt"] if row_data else "—",
                        "_show_parent_dd": True,
                        "_parent_label":   drill_label,
                    }
                elif _cagr_match:
                    # Reconstruct full label with CAGR period for compute_drilldown
                    drill_label = f"{_cagr_match.group(1).strip()} ({_cagr_match.group(2)})"  # "Revenue Growth (3Y CAGR)"
                    dd = compute_drilldown(drill_label, data, hl, val, price_data)
                else:
                    drill_label = sel.lstrip("  ↳ ").strip()
                    dd = compute_drilldown(drill_label, data, hl, val, price_data)

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
                        if f_name.startswith("ℹ"):
                            # Special info note — rendered as amber notice
                            card += (
                                f'<div style="display:flex;align-items:center;gap:6px;'
                                f'margin-bottom:3px;margin-top:4px;font-size:11px;'
                                f'color:#f59e0b;font-style:italic;">'
                                f'{f_name}</div>'
                            )
                        else:
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
                    for comp in dd["components"]:
                        # support both 2-tuple (name, val) and 3-tuple (name, val, reason)
                        if len(comp) == 3:
                            name, value, skip_reason = comp
                        else:
                            name, value = comp; skip_reason = None
                        if not name: continue
                        is_skipped = skip_reason is not None
                        is_avg_row = name.strip().startswith("→")
                        if is_skipped:
                            card += (
                                f'<tr style="border-bottom:1px solid #1e2535;opacity:0.5;">'
                                f'<td style="padding:5px 2px;color:#64748b;font-style:italic;">{name}</td>'
                                f'<td style="padding:5px 2px;text-align:right;color:#f59e0b;'
                                f'font-size:11px;">{value} &nbsp;<span style="color:#64748b;">({skip_reason})</span></td></tr>'
                            )
                        elif is_avg_row:
                            card += (
                                f'<tr style="border-top:1px solid #3b82f6;background:#0a1628;">'
                                f'<td style="padding:6px 2px;color:#93c5fd;font-weight:600;">{name}</td>'
                                f'<td style="padding:6px 2px;text-align:right;color:#60a5fa;'
                                f'font-weight:700;">{value}</td></tr>'
                            )
                        else:
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

                # If avg row: also show parent metric drilldown below
                if dd.get("_show_parent_dd"):
                    _pdl = dd["_parent_label"]
                    _pdd = compute_drilldown(_pdl, data, hl, val, price_data)
                    st.markdown(
                        f'<div style="margin-top:10px;font-size:11px;color:#64748b;"'
                        f'> Berechnungsgrundlage: <b style="color:#93c5fd">{_pdl}</b></div>',
                        unsafe_allow_html=True
                    )
                    # Render parent dd as compact card
                    pcard = f'<div style="background:#0d1520;border:1px solid #1e3a5f;border-radius:8px;padding:14px;margin-top:4px;">'
                    _pfml = _pdd["formula"].replace("\n", "<br>")
                    pcard += (f'<div style="font-size:11px;color:#64748b;margin-bottom:6px;text-transform:uppercase;'
                              f'letter-spacing:.05em;">Formel</div>'
                              f'<div style="font-size:12px;color:#93c5fd;font-family:monospace;white-space:pre-wrap;margin-bottom:10px;">{_pfml}</div>')
                    if _pdd.get("components"):
                        pcard += '<table style="width:100%;border-collapse:collapse;font-size:11px;">'
                        for _pn, _pv in _pdd["components"]:
                            if not _pn: continue
                            pcard += (f'<tr style="border-bottom:1px solid #1e2535;">'
                                      f'<td style="padding:3px 2px;color:#94a3b8;">{_pn}</td>'
                                      f'<td style="padding:3px 2px;text-align:right;color:#e2e8f0;">{_pv}</td></tr>')
                        pcard += '</table>'
                    pcard += '</div>'
                    st.markdown(pcard, unsafe_allow_html=True)

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
