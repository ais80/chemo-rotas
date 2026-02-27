"""
PICS SACT Pharmacy Dashboard — Streamlit App

Data sources (in priority order):
  1. Google Sheet published as CSV (live, editable by team)
  2. Uploaded Excel file (fallback / preview)

Google Sheet setup:
  1. Create a Google Sheet with columns: Period, Metric, Oncology, Haematology, Total
  2. Go to File > Share > Publish to web
  3. Choose "Comma-separated values (.csv)" and click Publish
  4. Copy the URL and add it to .streamlit/secrets.toml:
       GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/XXXX/pub?output=csv"

9 standard metrics per period (in this exact order):
  Templates written, Sent to programming, Under review, Template updates,
  Updates sent to programming, Tested by pharmacist, Tested by nursing,
  Tested by doctors, Gone live
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
from io import BytesIO

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="PICS SACT Pharmacy Dashboard",
    page_icon="🏥",
    layout="wide",
)

# ---------------------------------------------------------------------------
# NHS-themed CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Header bar */
    .nhs-header {
        background: linear-gradient(135deg, #003087, #005eb8);
        color: white;
        padding: 24px 32px;
        border-radius: 8px;
        margin-bottom: 24px;
    }
    .nhs-header h1 { margin: 0; font-size: 1.6rem; }
    .nhs-header p { margin: 4px 0 0; opacity: 0.85; font-size: 0.95rem; }

    /* KPI cards */
    .kpi-card {
        background: white;
        border-radius: 10px;
        padding: 18px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        border-left: 4px solid #005eb8;
        height: 100%;
    }
    .kpi-card.green  { border-left-color: #009639; }
    .kpi-card.orange { border-left-color: #ed8b00; }
    .kpi-card.pink   { border-left-color: #ae2573; }
    .kpi-card.aqua   { border-left-color: #00a9ce; }

    .kpi-label {
        font-size: 0.75rem;
        color: #4c6272;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 2rem;
        font-weight: 700;
        color: #003087;
        line-height: 1.1;
    }
    .kpi-detail {
        font-size: 0.8rem;
        color: #4c6272;
        margin-top: 4px;
    }
    .kpi-detail .onc  { color: #0072ce; font-weight: 600; }
    .kpi-detail .haem { color: #ae2573; font-weight: 600; }

    /* Pipeline */
    .pipeline-stage {
        text-align: center;
        padding: 12px 8px;
    }
    .pipeline-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #003087;
    }
    .pipeline-label {
        font-size: 0.75rem;
        color: #4c6272;
        margin-top: 2px;
    }
    .pipeline-arrow {
        font-size: 1.4rem;
        color: #41b6e6;
        text-align: center;
        padding-top: 10px;
    }

    /* Footer */
    .footer {
        text-align: center;
        color: #4c6272;
        font-size: 0.8rem;
        padding: 16px;
        border-top: 1px solid #d8dde0;
        margin-top: 24px;
    }

    /* Hide default Streamlit padding at top */
    .block-container { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------
ONC_COLOUR = "#0072ce"
HAEM_COLOUR = "#ae2573"
NHS_BLUE = "#005eb8"
NHS_DARK_BLUE = "#003087"
NHS_ORANGE = "#ed8b00"
NHS_LIGHT_BLUE = "#41b6e6"
NHS_GREEN = "#009639"
NHS_DARK_GREEN = "#006747"
NHS_AQUA = "#00a9ce"

METRIC_ORDER = [
    "Templates written",
    "Sent to programming",
    "Under review",
    "Template updates",
    "Updates sent to programming",
    "Tested by pharmacist",
    "Tested by nursing",
    "Tested by doctors",
    "Gone live",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_from_google_sheet(url: str) -> pd.DataFrame | None:
    """Attempt to load data from a Google Sheet published-as-CSV URL."""
    try:
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        required = {"Period", "Metric", "Oncology", "Haematology", "Total"}
        if not required.issubset(set(df.columns)):
            return None
        return df
    except Exception:
        return None


def load_from_excel(file) -> pd.DataFrame | None:
    """Load data from an uploaded Excel file."""
    try:
        df = pd.read_excel(file, engine="openpyxl")
        df.columns = df.columns.str.strip()
        required = {"Period", "Metric", "Oncology", "Haematology", "Total"}
        if not required.issubset(set(df.columns)):
            st.error("Excel file must have columns: Period, Metric, Oncology, Haematology, Total")
            return None
        return df
    except Exception as e:
        st.error(f"Could not read Excel file: {e}")
        return None


def parse_data(df: pd.DataFrame) -> dict:
    """Convert flat DataFrame into {period: {metric: {onc, haem, total}}} dict."""
    data = {}
    for period in df["Period"].unique():
        pdf = df[df["Period"] == period]
        metrics = {}
        for _, row in pdf.iterrows():
            metrics[row["Metric"]] = {
                "onc": int(row["Oncology"]),
                "haem": int(row["Haematology"]),
                "total": int(row["Total"]),
            }
        data[period] = metrics
    return data


# ---------------------------------------------------------------------------
# Sidebar — data source
# ---------------------------------------------------------------------------
st.sidebar.title("Data Source")

# Try Google Sheet first
google_url = None
try:
    google_url = st.secrets["GOOGLE_SHEET_CSV_URL"]
except Exception:
    pass

df = None
source_label = None

if google_url:
    df = load_from_google_sheet(google_url)
    if df is not None:
        source_label = "Google Sheet (live)"
        st.sidebar.success("Connected to Google Sheet")

# File uploader (always available as override)
uploaded = st.sidebar.file_uploader("Upload Excel file", type=["xlsx", "xls"])
if uploaded is not None:
    df = load_from_excel(uploaded)
    if df is not None:
        source_label = f"Uploaded: {uploaded.name}"

# Fallback: try local file
if df is None:
    local_path = Path(__file__).parent / "SACT_Dashboard_Data.xlsx"
    if local_path.exists():
        df = load_from_excel(str(local_path))
        if df is not None:
            source_label = "Local file: SACT_Dashboard_Data.xlsx"
            st.sidebar.info("Using local Excel file")

# Download template button
template_path = Path(__file__).parent / "SACT_Dashboard_Data.xlsx"
if template_path.exists():
    st.sidebar.download_button(
        "Download Excel template",
        data=template_path.read_bytes(),
        file_name="SACT_Dashboard_Data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

if df is None:
    st.markdown("""
    <div class="nhs-header">
        <h1>PICS SACT Pharmacy Dashboard</h1>
        <p>University Hospitals Birmingham NHS Foundation Trust</p>
    </div>
    """, unsafe_allow_html=True)
    st.warning("No data loaded. Please either:")
    st.markdown("""
    1. **Configure Google Sheet** — add `GOOGLE_SHEET_CSV_URL` to `.streamlit/secrets.toml`
    2. **Upload an Excel file** — use the sidebar uploader
    3. **Place the template** — put `SACT_Dashboard_Data.xlsx` in the app directory
    """)
    st.stop()

# ---------------------------------------------------------------------------
# Parse data
# ---------------------------------------------------------------------------
data = parse_data(df)
periods = list(data.keys())

st.sidebar.markdown(f"**Source:** {source_label}")
st.sidebar.markdown(f"**Periods:** {len(periods)}")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
<div class="nhs-header">
    <h1>PICS SACT Pharmacy Dashboard</h1>
    <p>University Hospitals Birmingham NHS Foundation Trust</p>
</div>
""", unsafe_allow_html=True)

# Period selector
selected_period = st.radio("Select period", periods, horizontal=True)
d = data[selected_period]


def get_metric(name: str) -> dict:
    """Safely get a metric dict, defaulting to zeros."""
    return d.get(name, {"onc": 0, "haem": 0, "total": 0})


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
written = get_metric("Templates written")
sent = get_metric("Sent to programming")
live = get_metric("Gone live")
pharm = get_metric("Tested by pharmacist")
updates = get_metric("Template updates")

kpi_cols = st.columns(5)

kpi_data = [
    ("TEMPLATES WRITTEN", written["total"], written, ""),
    ("SENT TO PROGRAMMING", sent["total"], sent, "orange"),
    ("ROTAS GONE LIVE", live["total"], live, "green"),
    ("PHARMACIST TESTS", pharm["total"], pharm, "aqua"),
    ("TEMPLATE UPDATES", updates["total"], updates, "pink"),
]

for col, (label, value, vals, cls) in zip(kpi_cols, kpi_data):
    with col:
        st.markdown(f"""
        <div class="kpi-card {cls}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-detail">
                Onc <span class="onc">{vals['onc']}</span> /
                Haem <span class="haem">{vals['haem']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Pipeline funnel
# ---------------------------------------------------------------------------
st.subheader("Rota Template Pipeline")

tested_nursing = get_metric("Tested by nursing")
tested_doctors = get_metric("Tested by doctors")

pipeline_stages = [
    (written["total"], "Written"),
    (sent["total"], "Sent to\nProgramming"),
    (pharm["total"], "Pharmacist\nTested"),
    (tested_doctors["total"], "Doctor\nTested"),
    (tested_nursing["total"], "Nursing\nTested"),
    (live["total"], "Gone Live"),
]

pipe_cols = st.columns(len(pipeline_stages) * 2 - 1)
for i, (val, label) in enumerate(pipeline_stages):
    col_idx = i * 2
    with pipe_cols[col_idx]:
        st.markdown(f"""
        <div class="pipeline-stage">
            <div class="pipeline-value">{val}</div>
            <div class="pipeline-label">{label.replace(chr(10), '<br>')}</div>
        </div>
        """, unsafe_allow_html=True)
    if i < len(pipeline_stages) - 1:
        with pipe_cols[col_idx + 1]:
            st.markdown('<div class="pipeline-arrow">&#9654;</div>', unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
chart_col1, chart_col2 = st.columns(2)

# Templates by Specialty (grouped bar)
reviewed = get_metric("Under review")
with chart_col1:
    st.subheader("Templates by Specialty")
    cats = ["Written", "Sent to Prog.", "Under Review", "Updates", "Gone Live"]
    onc_vals = [written["onc"], sent["onc"], reviewed["onc"], updates["onc"], live["onc"]]
    haem_vals = [written["haem"], sent["haem"], reviewed["haem"], updates["haem"], live["haem"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Oncology", x=cats, y=onc_vals, marker_color=ONC_COLOUR))
    fig.add_trace(go.Bar(name="Haematology", x=cats, y=haem_vals, marker_color=HAEM_COLOUR))
    fig.update_layout(
        barmode="group", legend=dict(orientation="h", y=-0.2),
        margin=dict(l=20, r=20, t=10, b=40), height=350,
        yaxis=dict(title="Count"),
    )
    st.plotly_chart(fig, use_container_width=True)

# Testing Coverage (grouped bar)
with chart_col2:
    st.subheader("Testing Coverage")
    test_cats = ["Pharmacist", "Doctors", "Nursing"]
    test_onc = [pharm["onc"], tested_doctors["onc"], tested_nursing["onc"]]
    test_haem = [pharm["haem"], tested_doctors["haem"], tested_nursing["haem"]]

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(name="Oncology", x=test_cats, y=test_onc, marker_color=ONC_COLOUR))
    fig2.add_trace(go.Bar(name="Haematology", x=test_cats, y=test_haem, marker_color=HAEM_COLOUR))
    fig2.update_layout(
        barmode="group", legend=dict(orientation="h", y=-0.2),
        margin=dict(l=20, r=20, t=10, b=40), height=350,
        yaxis=dict(title="Rotas tested"),
    )
    st.plotly_chart(fig2, use_container_width=True)

chart_col3, chart_col4 = st.columns(2)

# Workload Breakdown (donut)
with chart_col3:
    st.subheader("Workload Breakdown")
    donut_labels = ["Written (new)", "Updates", "Sent to Programming", "Under Review", "Gone Live"]
    donut_vals = [written["total"], updates["total"], sent["total"], reviewed["total"], live["total"]]
    donut_colors = [NHS_BLUE, HAEM_COLOUR, NHS_ORANGE, NHS_LIGHT_BLUE, NHS_GREEN]

    fig3 = go.Figure(go.Pie(
        labels=donut_labels, values=donut_vals,
        hole=0.55, marker=dict(colors=donut_colors),
        textinfo="label+value",
    ))
    fig3.update_layout(
        margin=dict(l=20, r=20, t=10, b=10), height=350,
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig3, use_container_width=True)

# Period Comparison (grouped bar) — only if 2+ periods
with chart_col4:
    st.subheader("Period Comparison")
    if len(periods) >= 2:
        comp_cats = ["Written", "Sent to Prog.", "Updates", "Pharm Tests", "Gone Live"]
        comp_colours = [
            "rgba(0,48,135,0.75)", "rgba(255,184,28,0.85)",
            "rgba(0,150,57,0.75)", "rgba(174,37,115,0.75)",
        ]
        fig4 = go.Figure()
        for i, period_name in enumerate(periods):
            pd_data = data[period_name]
            gm = lambda n: pd_data.get(n, {"total": 0})["total"]
            fig4.add_trace(go.Bar(
                name=period_name,
                x=comp_cats,
                y=[
                    gm("Templates written"), gm("Sent to programming"),
                    gm("Template updates"), gm("Tested by pharmacist"),
                    gm("Gone live"),
                ],
                marker_color=comp_colours[i % len(comp_colours)],
            ))
        fig4.update_layout(
            barmode="group", legend=dict(orientation="h", y=-0.2),
            margin=dict(l=20, r=20, t=10, b=40), height=350,
        )
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("Need 2+ periods for comparison chart.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Detailed data table
# ---------------------------------------------------------------------------
st.subheader("Detailed Data")

table_rows = []
for metric_name in METRIC_ORDER:
    vals = get_metric(metric_name)
    table_rows.append({
        "Metric": metric_name,
        "Oncology": vals["onc"],
        "Haematology": vals["haem"],
        "Total": vals["total"],
    })

table_df = pd.DataFrame(table_rows)
st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Metric": st.column_config.TextColumn(width="large"),
        "Total": st.column_config.NumberColumn(help="Combined total"),
    },
)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("""
<div class="footer">
    PICS SACT Pharmacy Team &mdash; Data compiled by Hasan Varachhia, Specialist Pharmacist
</div>
""", unsafe_allow_html=True)
