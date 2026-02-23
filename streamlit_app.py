"""Streamlit web app — Chemo Rota to EPMA Converter.

Two-step flow:
  1. Upload PDF → extract config → show editable form
  2. User fills required fields → generate ZIP (DOCX + TXT)

Deploy on Streamlit Community Cloud: set main file to streamlit_app.py.
"""

import io
import sys
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from converter.extract_pdf import extract_to_yaml
from converter.generate_txt import generate_txt
from converter.generate_docx import generate_docx
from converter.models import RotaConfig

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Chemo Rota → EPMA Converter",
    page_icon=":pill:",
    layout="wide",
)

REQUIRED_FIELDS = {
    "drug_prefix": "Drug prefix code (e.g. DARO)",
    "ticket_number": "PICS ticket number",
    "specialty_class": "Specialty / rota class (e.g. HAEMATOLOGY)",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_pdf(uploaded_file) -> dict:
    """Save uploaded PDF to temp dir, run extraction, return config dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / uploaded_file.name
        pdf_path.write_bytes(uploaded_file.getvalue())
        yaml_path = Path(tmpdir) / (pdf_path.stem + "_config.yaml")
        return extract_to_yaml(str(pdf_path), str(yaml_path))


def build_zip(config_dict: dict) -> bytes:
    """Generate DOCX + TXT and bundle into a ZIP, returned as bytes."""
    config = RotaConfig.from_dict(config_dict)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        txt_filename = f"#{config.ticket_number}{config.drug_prefix}.txt"
        txt_path = tmp / txt_filename
        with open(txt_path, "w", newline="") as f:
            f.write(generate_txt(config))

        docx_filename = f"{config.document_code} {config.drug_full_name}.docx"
        docx_path = tmp / docx_filename
        generate_docx(config, str(docx_path))

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(txt_path, txt_filename)
            zf.write(docx_path, docx_filename)
        buf.seek(0)
        return buf.read()


def get_warnings(cfg: dict) -> list[str]:
    """Return human-readable warnings for fields still needing completion."""
    warnings = []
    for field, label in REQUIRED_FIELDS.items():
        val = cfg.get(field, "CHANGE_ME")
        if val == "CHANGE_ME" or not val:
            warnings.append(f"**{label}** (`{field}`) — please fill this in.")
    return warnings


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("Chemo Rota to EPMA Converter")
st.caption("Queen Elizabeth Hospital Cancer Centre — PICS EPMA import tool")

# Step 1: Upload
st.header("Step 1: Upload PDF")
uploaded = st.file_uploader(
    "Drop a chemo rota PDF here",
    type=["pdf"],
    help="The paper chemotherapy rota PDF from the Cancer Centre.",
)

if uploaded and "config" not in st.session_state:
    with st.spinner("Extracting data from PDF..."):
        try:
            st.session_state.config = extract_pdf(uploaded)
            st.session_state.filename = uploaded.name
        except Exception as exc:
            st.error(f"Extraction failed: {exc}")
            st.stop()

if "config" not in st.session_state:
    st.info("Upload a PDF to get started.")
    st.stop()

# Step 2: Review & Edit
cfg = st.session_state.config

st.header("Step 2: Review & Edit")
st.caption(f"Extracted from: **{st.session_state.filename}**")

warnings = get_warnings(cfg)
if warnings:
    st.warning("The following fields could not be extracted and need your input:")
    for w in warnings:
        st.markdown(f"- {w}")

# --- Required fields ---
st.subheader("Required Fields")
col1, col2, col3 = st.columns(3)
with col1:
    cfg["drug_prefix"] = st.text_input(
        "Drug prefix",
        value=cfg.get("drug_prefix", "CHANGE_ME"),
        help="Short uppercase code, 3-5 characters (e.g. DARO, RCHO)",
    ).strip().upper()
with col2:
    cfg["ticket_number"] = st.text_input(
        "Ticket number",
        value=str(cfg.get("ticket_number", "CHANGE_ME")),
        help="PICS change ticket number (digits only)",
    ).strip()
with col3:
    cfg["specialty_class"] = st.text_input(
        "Specialty class",
        value=cfg.get("specialty_class", "CHANGE_ME"),
        help="Rota classification (e.g. UROLOGY, HAEMATOLOGY, ONCOLOGY)",
    ).strip().upper()

# --- Extracted fields ---
st.subheader("Extracted Details")
col_a, col_b = st.columns(2)
with col_a:
    cfg["document_code"] = st.text_input(
        "Document code", value=cfg.get("document_code", "")
    )
    cfg["drug_full_name"] = st.text_input(
        "Drug full name", value=cfg.get("drug_full_name", "")
    )
    cfg["indication"] = st.text_input(
        "Indication", value=cfg.get("indication", "")
    )
with col_b:
    cfg["cycle_delay"] = st.text_input(
        "Cycle delay", value=cfg.get("cycle_delay", "4w"),
        help="Cycle length, e.g. 4w for 4 weeks",
    )
    cfg["default_cycles"] = st.number_input(
        "Default cycles",
        value=int(cfg.get("default_cycles", 1)),
        min_value=1,
    )
    cfg["directorate"] = st.text_input(
        "Directorate", value=cfg.get("directorate", "ONC"),
        help="3-letter directorate code",
    ).strip().upper()
    cfg["inpatient_or_outpatient"] = st.selectbox(
        "Inpatient or Outpatient",
        options=["O", "I"],
        index=0 if cfg.get("inpatient_or_outpatient", "O") == "O" else 1,
        format_func=lambda x: "Outpatient (O)" if x == "O" else "Inpatient (I)",
    )

# --- Templates ---
st.subheader("Drug Templates")
templates = cfg.get("templates", [])
if templates:
    for i, t in enumerate(templates):
        with st.expander(
            f"Template {i+1}: {t.get('drug_name_upper', '?')} "
            f"{t.get('dose', '?')}{t.get('units', '')} "
            f"{t.get('frequency', '')} {t.get('mode', '')}",
            expanded=False,
        ):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                t["dose"] = st.number_input(
                    "Dose", value=int(t.get("dose", 0)), min_value=0, key=f"dose_{i}"
                )
            with c2:
                t["units"] = st.text_input("Units", value=t.get("units", "mg"), key=f"units_{i}")
            with c3:
                t["frequency"] = st.text_input("Frequency", value=t.get("frequency", ""), key=f"freq_{i}")
            with c4:
                t["mode"] = st.selectbox(
                    "Mode", options=["TTO", "REG"],
                    index=0 if t.get("mode", "TTO") == "TTO" else 1,
                    key=f"mode_{i}",
                )
            c5, c6, c7, c8 = st.columns(4)
            with c5:
                t["route"] = st.text_input("Route", value=t.get("route", "ORAL"), key=f"route_{i}")
            with c6:
                t["form"] = st.text_input("Form", value=t.get("form", "TAB"), key=f"form_{i}")
            with c7:
                t["group"] = st.text_input("Group", value=t.get("group", "1A"), key=f"group_{i}")
            with c8:
                t["timing_constraints"] = st.text_input(
                    "Timing", value=t.get("timing_constraints", ""), key=f"timing_{i}"
                )
else:
    st.info("No drug templates extracted. Check the PDF content.")

# --- Blood tests ---
st.subheader("Blood Tests")
blood_tests = cfg.get("blood_tests", [])
if blood_tests:
    for i, bt in enumerate(blood_tests):
        with st.expander(
            f"{bt.get('test_code', '?')}: {bt.get('message_text_line1', '')}",
            expanded=False,
        ):
            c1, c2, c3 = st.columns(3)
            with c1:
                bt["test_code"] = st.text_input(
                    "Test code", value=bt.get("test_code", ""), key=f"tc_{i}"
                )
            with c2:
                bt["threshold_value"] = st.number_input(
                    "Threshold", value=int(bt.get("threshold_value", 0)), key=f"tv_{i}"
                )
            with c3:
                bt["threshold_function"] = st.selectbox(
                    "Function", options=["LT", "GT"],
                    index=0 if bt.get("threshold_function", "LT") == "LT" else 1,
                    key=f"tf_{i}",
                )
            bt["message_text_line1"] = st.text_input(
                "Message line 1", value=bt.get("message_text_line1", ""), key=f"ml1_{i}"
            )
            bt["message_text_line3"] = st.text_input(
                "Message line 3", value=bt.get("message_text_line3", ""), key=f"ml3_{i}"
            )

cfg["blood_test_validity_days"] = st.number_input(
    "Blood test validity (days)",
    value=int(cfg.get("blood_test_validity_days", 7)),
    min_value=1,
)

# --- Rota info ---
st.subheader("Rota Information")
rota_info_text = st.text_area(
    "Rota info paragraphs (blank line between paragraphs)",
    value="\n\n".join(cfg.get("rota_info_paragraphs", [])),
    height=150,
)
cfg["rota_info_paragraphs"] = [
    p.strip() for p in rota_info_text.split("\n\n") if p.strip()
]

# Step 3: Generate
st.header("Step 3: Generate & Download")

# Validate before allowing generation
still_missing = [
    label for field, label in REQUIRED_FIELDS.items()
    if cfg.get(field, "CHANGE_ME") in ("CHANGE_ME", "")
]

if still_missing:
    st.warning(
        "Fill in the required fields before generating: "
        + ", ".join(still_missing)
    )

if st.button("Generate DOCX + TXT", type="primary", disabled=bool(still_missing)):
    with st.spinner("Generating files..."):
        try:
            zip_bytes = build_zip(cfg)
            stem = f"{cfg.get('document_code', 'rota')}_{cfg.get('drug_full_name', 'converted')}"
            st.download_button(
                label="Download ZIP",
                data=zip_bytes,
                file_name=f"{stem}.zip",
                mime="application/zip",
                type="primary",
            )
            st.success("Files generated successfully!")
        except Exception as exc:
            st.error(f"Generation failed: {exc}")

# --- Reset button ---
st.divider()
if st.button("Start over (new PDF)"):
    for key in ["config", "filename"]:
        st.session_state.pop(key, None)
    st.rerun()
