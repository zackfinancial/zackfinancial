
import os
import io
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Zack Financial — GL Dashboard + Rolling TB", layout="wide")

st.markdown('<h1 style="text-align:center; font-size:48px; margin:0.2em 0;">Zack Financial</h1>', unsafe_allow_html=True)

# Locked headers expected in the GL tab
EXPECTED = [
    "seq","Fund","FSLI.1","FSLI.3","GL Account","GL Account Name",
    "reference","description","date","Net amount"
]

def _norm(s): return str(s).strip().lower()

def parse_date(series):
    # Robust: normal parse + Excel serials + Unix s/ms (picks plausible years)
    s0 = pd.to_datetime(series, errors="coerce", infer_datetime_format=True)
    def score(d):
        if d is None: return -1
        d = d.dropna()
        if d.empty: return -1
        y = d.dt.year
        return int(y.between(1990,2100).sum())
    best, best_sc = s0, score(s0)

    # try numeric conversions
    nums = pd.to_numeric(pd.Series(series).astype(str).str.replace(",","",regex=False).str.strip(), errors="coerce")
    if nums.notna().sum()>0:
        for unit, origin in [("d","1899-12-30"),("s",None),("ms",None)]:
            try:
                cand = pd.to_datetime(nums, unit=unit, origin=origin, errors="coerce") if origin else pd.to_datetime(nums, unit=unit, errors="coerce")
                sc = score(cand)
                if sc>best_sc: best, best_sc = cand, sc
            except: pass
    return best.dt.normalize()

def parse_amount(series):
    s = pd.Series(series).astype(str).str.replace(",","",regex=False).str.strip()
    s = s.str.replace(r"\((.*)\)", r"-\1", regex=True)  # (1,234.56) -> -1,234.56
    return pd.to_numeric(s, errors="coerce")

def load_gl_sheet(uploaded):
    xls = pd.ExcelFile(uploaded, engine="openpyxl")
    # Prefer a sheet literally named "GL" if present
    sheet_name = "GL" if "GL" in [str(s) for s in xls.sheet_names] else xls.sheet_names[0]
    df = xls.parse(sheet_name)
    return df, sheet_name

def prepare(df):
    d = df.copy()
    # Normalize headers by exact expected names where possible
    cols = { _norm(c): c for c in d.columns }
    # Coerce/rename to canonical names when present
    rename = {}
    for want in EXPECTED:
        for c in d.columns:
            if _norm(c)==_norm(want):
                rename[c] = want
                break
    if rename:
        d = d.rename(columns=rename)

    # Parse date and amount
    if "date" in d.columns:
        d["Date"] = parse_date(d["date"])
    else:
        st.error("Missing required 'date' column."); st.stop()

    amt_col = "Net amount" if "Net amount" in d.columns else None
    if amt_col is None:
        st.error("Missing required 'Net amount' column."); st.stop()
    d["Amount"] = parse_amount(d[amt_col])

    # Drop rows without essentials
    d = d.dropna(subset=["Date","Amount"])

    # Month key
    d["Month"] = d["Date"].dt.to_period("M").dt.to_timestamp()

    return d

def apply_filters(df):
    d = df.copy()
    # Date slider
    mn, mx = d["Date"].min(), d["Date"].max()
    start, end = st.sidebar.slider(
        "Date range",
        min_value=mn.to_pydatetime(),
        max_value=mx.to_pydatetime(),
        value=(mn.to_pydatetime(), mx.to_pydatetime())
    )
    d = d[(d["Date"]>=pd.to_datetime(start)) & (d["Date"]<=pd.to_datetime(end))]

    # Role filters (every column if present)
    for col in ["Fund","FSLI.1","FSLI.3","GL Account","GL Account Name","reference","description","seq"]:
        if col in d.columns:
            opts = sorted(d[col].dropna().astype(str).unique().tolist())
            pick = st.sidebar.multiselect(f"Filter {col}", options=opts)
            if pick:
                d = d[d[col].astype(str).isin(pick)]
    return d

# ---------- Formatting helpers ----------
def fmt_currency(x):
    try:
        return f"${x:,.2f}"
    except Exception:
        return x

def fmt_date(series):
    s = pd.to_datetime(series, errors="coerce")
    return s.dt.strftime("%m/%d/%Y")

def display_df_with_formats(df, currency_cols=None, date_cols=None):
    d = df.copy()
    if date_cols:
        for c in date_cols:
            if c in d.columns:
                d[c] = fmt_date(d[c])
    if currency_cols:
        for c in currency_cols:
            if c in d.columns:
                d[c] = d[c].apply(fmt_currency)
    st.dataframe(d, hide_index=True, use_container_width=True)

def dashboard_view(df):
    st.subheader("Dashboard")
    # KPIs
    c1,c2,c3,c4 = st.columns(4)
    inflow = df.loc[df["Amount"]>0,"Amount"].sum()
    outflow = df.loc[df["Amount"]<0,"Amount"].sum()
    net = inflow + outflow
    c1.metric("Inflow", f"${inflow:,.0f}")
    c2.metric("Outflow", f"${outflow:,.0f}")
    c3.metric("Net", f"${net:,.0f}")
    c4.metric("# Rows", f"{len(df):,}")

    # Monthly activity
    m = df.groupby("Month", as_index=False)["Amount"].sum().sort_values("Month")
    fig = px.bar(m, x="Month", y="Amount", title="Monthly Net Activity")
    fig.update_yaxes(tickprefix="$", separatethousands=True)
    st.plotly_chart(fig, use_container_width=True)

    # Explorer
    st.markdown("**Transactions**")
    show_cols = [c for c in ["Date","Amount","Fund","FSLI.1","FSLI.3","GL Account","GL Account Name","reference","description","seq"] if c in df.columns]
    display_df_with_formats(df[show_cols], currency_cols=["Amount"], date_cols=["Date"])

def trial_balance_view(df):
    st.subheader("Rolling Monthly Trial Balance (Cumulative)")

    # Index: GL Account + optional descriptors
    idx = [c for c in ["GL Account", "GL Account Name", "FSLI.1", "FSLI.3", "Fund"] if c in df.columns]
    if ("GL Account" not in idx) and ("GL Account Name" not in idx):
        st.error("GL Account columns not found. Need 'GL Account' and 'GL Account Name'.")
        return

    # Group by Month + Account for monthly movements
    monthly_tb = df.groupby(idx + ["Month"], as_index=False)["Amount"].sum()

    # Pivot so months become columns (monthly movements)
    pivot_mov = monthly_tb.pivot_table(
        index=idx,
        columns="Month",
        values="Amount",
        aggfunc="sum",
        fill_value=0
    )

    # Sort month columns chronologically
    month_cols = sorted([c for c in pivot_mov.columns], key=lambda x: pd.Timestamp(x))

    # Compute cumulative (rolling) balances across months
    pivot_cum = pivot_mov[month_cols].cumsum(axis=1)

    # Add Grand Total on the far right (same as last cumulative column)
    if month_cols:
        pivot_cum["Grand Total"] = pivot_cum[month_cols[-1]]
    else:
        pivot_cum["Grand Total"] = 0

    # For display: convert month column names to mm/dd/yyyy (use first day of month)
    display_cols = [(c.strftime("%m/%d/%Y") if hasattr(c, "strftime") else str(c)) for c in pivot_cum.columns]
    pivot_cum_display = pivot_cum.copy()
    pivot_cum_display.columns = display_cols

    # Combine back with the index (account descriptors)
    out_display = pivot_cum_display.reset_index()
    out_export  = pivot_cum.reset_index()  # keep numeric for Excel

    # Display with currency formatting for all numeric month/total columns
    currency_cols = [col for col in out_display.columns if col not in idx]
    display_df_with_formats(out_display, currency_cols=currency_cols, date_cols=None)

    # Export (numeric)
    from io import BytesIO
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        out_export.to_excel(w, index=False, sheet_name="Rolling_Trial_Balance_Cumulative")
    bio.seek(0)
    st.download_button(
        "Download Rolling Trial Balance (Cumulative, Excel)",
        data=bio,
        file_name="Rolling_Trial_Balance_Cumulative.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def main():
    st.sidebar.title("Load GL")
    st.sidebar.caption("Tip: set a custom logo URL by adding `logo_url` to `.streamlit/secrets.toml`.")
    up = st.sidebar.file_uploader("Upload Excel (.xlsx) containing a 'GL' sheet", type=["xlsx"])
    if up is None:
        st.info("Upload your GL workbook (we'll use the 'GL' tab if present, or the first sheet).")
        return

    try:
        raw, sheet = load_gl_sheet(up)
    except Exception as e:
        st.error(f"Failed to read Excel: {e}")
        return

    df = prepare(raw)
    st.caption(f"Sheet used: **{sheet}** | Rows loaded: **{len(df):,}**")

    # Filters
    st.sidebar.header("Filters (roles)")
    fdf = apply_filters(df)
    st.caption(f"Rows after filters: **{len(fdf):,}**")

    # Two separate views
    view = st.radio("View", ["Dashboard", "Rolling Trial Balance (Cumulative)"], horizontal=True)
    if view == "Dashboard":
        dashboard_view(fdf)
    else:
        trial_balance_view(fdf)

if __name__ == "__main__":
    main()
