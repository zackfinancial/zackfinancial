# app.py
import os
from io import BytesIO
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Zack Financial — GL Dashboard + Rolling TB", layout="wide")
st.markdown('<h1 style="text-align:center; font-size:48px; margin:0.2em 0;">Zack Financial</h1>', unsafe_allow_html=True)

# ===== Sample GL download section (centered under header) =====
def make_sample_gl_bytes() -> BytesIO:
    """Create a simple, valid GL workbook if no local sample file is present."""
    df = pd.DataFrame([
        # seq, Fund, FSLI.1, FSLI.3, GL Account, GL Account Name, reference, description, date, Net amount
        ["JE00001-1","Fund I","Assets","Cash","1000","Cash","Bank","Initial capital", "2025-01-03", "250,000.00"],
        ["JE00001-2","Fund I","Equity","Partners' Capital","3000","Partners' Capital","LPs","Initial capital", "2025-01-03", "-250,000.00"],
        ["JE00002-1","Fund I","Expenses","Management Fees","6100","Management Fees","MGMT CO","January fee", "2025-01-31", "-5,000.00"],
        ["JE00002-2","Fund I","Assets","Cash","1000","Cash","Bank","January fee", "2025-01-31", "5,000.00"],
        ["JE00003-1","Fund I","Assets","Investment","1200","Investment - XYZ","XYZ","Initial purchase", "2025-02-05", "-100,000.00"],
        ["JE00003-2","Fund I","Assets","Cash","1000","Cash","Bank","Initial purchase", "2025-02-05", "100,000.00"],
    ], columns=["seq","Fund","FSLI.1","FSLI.3","GL Account","GL Account Name","reference","description","date","Net amount"])
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="GL")
    bio.seek(0)
    return bio

def render_sample_download_block():
    st.markdown(
        """
        <div style="text-align:center; margin: 8px 0 18px;">
          <p style="font-size:18px; margin:0 0 8px;">
            <strong>Try it now:</strong> Download the sample GL workbook, replace with your data, then re-upload to generate
            Rolling Trial Balances and financial statements.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sample_path = "GL_sample_data.xlsx"  # place a real sample here if you want
    label = "Download sample GL file (Excel)"
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            st.download_button(label, data=f, file_name="GL_sample_data.xlsx", mime=mime, use_container_width=True)
    else:
        sample_bytes = make_sample_gl_bytes()
        st.download_button(label, data=sample_bytes, file_name="GL_sample_data.xlsx", mime=mime, use_container_width=True)

render_sample_download_block()
# ===============================================================

# Expected GL headers (case/space-insensitive match handled later)
EXPECTED = [
    "seq","Fund","FSLI.1","FSLI.3","GL Account","GL Account Name",
    "reference","description","date","Net amount"
]

def _norm(s): 
    return str(s).strip().lower()

def parse_date(series):
    s0 = pd.to_datetime(series, errors="coerce", infer_datetime_format=True)
    def score(d):
        if d is None: return -1
        d = d.dropna()
        if d.empty: return -1
        y = d.dt.year
        return int(y.between(1990,2100).sum())
    best, best_sc = s0, score(s0)

    # try numeric conversions (Excel serials, unix seconds/ms)
    nums = pd.to_numeric(pd.Series(series).astype(str).str.replace(",","",regex=False).str.strip(), errors="coerce")
    if nums.notna().sum() > 0:
        for unit, origin in [("d","1899-12-30"),("s",None),("ms",None)]:
            try:
                cand = pd.to_datetime(nums, unit=unit, origin=origin, errors="coerce") if origin else pd.to_datetime(nums, unit=unit, errors="coerce")
                sc = score(cand)
                if sc > best_sc:
                    best, best_sc = cand, sc
            except:
                pass
    return best.dt.normalize()

def parse_amount(series):
    s = pd.Series(series).astype(str).str.replace(",","",regex=False).str.strip()
    s = s.replace(r"\((.*)\)", r"-\1", regex=True)  # (1,234.56) -> -1,234.56
    return pd.to_numeric(s, errors="coerce")

def load_gl_sheet(uploaded_file):
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sheet_name = "GL" if "GL" in [str(s) for s in xls.sheet_names] else xls.sheet_names[0]
    df = xls.parse(sheet_name)
    return df, sheet_name

def prepare(df):
    d = df.copy()

    # rename columns to canonical forms when names match ignoring case/space
    rename = {}
    for want in EXPECTED:
        for c in d.columns:
            if _norm(c) == _norm(want):
                rename[c] = want
                break
    if rename:
        d = d.rename(columns=rename)

    # essentials
    if "date" not in d.columns:
        st.error("Missing required 'date' column."); st.stop()
    if "Net amount" not in d.columns:
        st.error("Missing required 'Net amount' column."); st.stop()

    d["Date"] = parse_date(d["date"])
    d["Amount"] = parse_amount(d["Net amount"])
    d = d.dropna(subset=["Date","Amount"])

    # Month column for groupings
    d["Month"] = d["Date"].dt.to_period("M").dt.to_timestamp()
    return d

def apply_filters(df):
    d = df.copy()

    # date range
    mn, mx = d["Date"].min(), d["Date"].max()
    start, end = st.sidebar.slider(
        "Date range",
        min_value=mn.to_pydatetime(),
        max_value=mx.to_pydatetime(),
        value=(mn.to_pydatetime(), mx.to_pydatetime())
    )
    d = d[(d["Date"] >= pd.to_datetime(start)) & (d["Date"] <= pd.to_datetime(end))]

    # role filters
    for col in ["Fund","FSLI.1","FSLI.3","GL Account","GL Account Name","reference","description","seq"]:
        if col in d.columns:
            opts = sorted(d[col].dropna().astype(str).unique())
            pick = st.sidebar.multiselect(f"Filter {col}", options=opts)
            if pick:
                d = d[d[col].astype(str).isin(pick)]
    return d

def fmt_currency(x):
    try: return f"${x:,.2f}"
    except Exception: return x

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
    c1,c2,c3,c4 = st.columns(4)
    inflow = df.loc[df["Amount"] > 0, "Amount"].sum()
    outflow = df.loc[df["Amount"] < 0, "Amount"].sum()
    c1.metric("Inflow", f"${inflow:,.0f}")
    c2.metric("Outflow", f"${outflow:,.0f}")
    c3.metric("Net", f"${(inflow+outflow):,.0f}")
    c4.metric("# Rows", f"{len(df):,}")

    # monthly net bar
    m = df.groupby("Month", as_index=False)["Amount"].sum().sort_values("Month")
    fig = px.bar(m, x="Month", y="Amount", title="Monthly Net Activity")
    fig.update_yaxes(tickprefix="$", separatethousands=True)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Transactions**")
    cols = [c for c in ["Date","Amount","Fund","FSLI.1","FSLI.3","GL Account","GL Account Name","reference","description","seq"] if c in df.columns]
    display_df_with_formats(df[cols], currency_cols=["Amount"], date_cols=["Date"])

def transactions_download_button(df):
    cols_pref = ["Date","Amount","Fund","FSLI.1","FSLI.3","GL Account","GL Account Name","reference","description","seq"]
    cols = [c for c in cols_pref if c in df.columns]
    out = df.copy()
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    if "Amount" in out.columns:
        out["Amount"] = pd.to_numeric(out["Amount"], errors="coerce")
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        out[cols].to_excel(w, index=False, sheet_name="Transactions_Filtered")
    bio.seek(0)
    st.download_button(
        "Download filtered transactions (Excel)",
        data=bio,
        file_name="Transactions_Filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

def trial_balance_view(df):
    st.subheader("Rolling Monthly Trial Balance (Cumulative)")
    idx = [c for c in ["GL Account","GL Account Name","FSLI.1","FSLI.3","Fund"] if c in df.columns]
    if ("GL Account" not in idx) and ("GL Account Name" not in idx):
        st.error("Need 'GL Account' and 'GL Account Name' columns.")
        return

    monthly_tb = df.groupby(idx + ["Month"], as_index=False)["Amount"].sum()
    pivot_mov = monthly_tb.pivot_table(index=idx, columns="Month", values="Amount", aggfunc="sum", fill_value=0)
    month_cols = sorted(list(pivot_mov.columns), key=lambda x: pd.Timestamp(x))
    pivot_cum = pivot_mov[month_cols].cumsum(axis=1)
    pivot_cum["Grand Total"] = pivot_cum[month_cols[-1]] if month_cols else 0

    # pretty display (month labels)
    display_cols = [(c.strftime("%m/%d/%Y") if hasattr(c, "strftime") else str(c)) for c in pivot_cum.columns]
    out_display = pivot_cum.copy()
    out_display.columns = display_cols
    out_display = out_display.reset_index()

    # numeric export
    out_export = pivot_cum.reset_index()

    currency_cols = [c for c in out_display.columns if c not in idx]
    display_df_with_formats(out_display, currency_cols=currency_cols, date_cols=None)

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
    # Sidebar (no tips)
    st.sidebar.title("Load GL")
    uploaded = st.sidebar.file_uploader("Upload Excel (.xlsx) containing a 'GL' sheet", type=["xlsx"])

    if uploaded is None:
        st.info("Upload your GL workbook (we'll use the 'GL' tab if present, or the first sheet).")
        return

    try:
        raw, sheet = load_gl_sheet(uploaded)
    except Exception as e:
        st.error(f"Failed to read Excel: {e}")
        return

    df = prepare(raw)
    st.caption(f"Sheet used: **{sheet}** | Rows loaded: **{len(df):,}**")

    st.sidebar.header("Filters")
    fdf = apply_filters(df)
    st.caption(f"Rows after filters: **{len(fdf):,}**")

    # transactions download button (new)
    transactions_download_button(fdf)

    # views
    view = st.radio("View", ["Dashboard", "Rolling Trial Balance (Cumulative)"], horizontal=True)
    if view == "Dashboard":
        dashboard_view(fdf)
    else:
        trial_balance_view(fdf)

if __name__ == "__main__":
    main()
