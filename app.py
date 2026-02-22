"""Flask web app — Chemo Rota to EPMA Converter.

Two-step flow:
  1. /extract  POST  PDF → JSON config (shown as editable review form)
  2. /generate POST  JSON config → ZIP (DOCX + TXT download)

The legacy /convert endpoint (PDF → ZIP directly) is kept for backward compatibility.
"""

import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, render_template, request, send_file, jsonify

sys.path.insert(0, str(Path(__file__).parent))

from converter.extract_pdf import extract_to_yaml
from converter.generate_txt import generate_txt
from converter.generate_docx import generate_docx
from converter.models import RotaConfig

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024  # 30 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_config(d: dict) -> list[str]:
    """Return human-readable warnings for fields that need manual completion."""
    warnings = []
    checks = {
        "drug_prefix": "Drug prefix code (e.g. RCHO)",
        "ticket_number": "PICS ticket number",
        "specialty_class": "Specialty / rota class (e.g. HAEMATOLOGY)",
    }
    for field, label in checks.items():
        if d.get(field, "CHANGE_ME") == "CHANGE_ME" or not d.get(field):
            warnings.append(f"{label} (<code>{field}</code>) could not be extracted — please fill this in.")
    return warnings


def _build_zip(config_dict: dict) -> bytes:
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract_route():
    """Step 1 — Upload PDF, return extracted config as JSON for review."""
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    f = request.files["pdf"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are accepted."}), 400

    pdf_bytes = f.read()
    if not pdf_bytes:
        return jsonify({"error": "The uploaded file is empty."}), 400

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / f.filename
            pdf_path.write_bytes(pdf_bytes)
            yaml_path = Path(tmpdir) / (pdf_path.stem + "_config.yaml")
            config_dict = extract_to_yaml(str(pdf_path), str(yaml_path))
    except Exception as exc:
        return jsonify({"error": f"Extraction failed: {exc}"}), 500

    return jsonify({
        "config": config_dict,
        "warnings": _validate_config(config_dict),
    })


@app.route("/generate", methods=["POST"])
def generate_route():
    """Step 2 — Accept (edited) config JSON, return ZIP download."""
    config_dict = request.get_json(force=True)
    if not config_dict:
        return jsonify({"error": "No config data provided."}), 400

    try:
        zip_bytes = _build_zip(config_dict)
    except Exception as exc:
        return jsonify({"error": f"Generation failed: {exc}"}), 500

    stem = f"{config_dict.get('document_code','rota')}_{config_dict.get('drug_full_name','converted')}"
    return send_file(
        io.BytesIO(zip_bytes),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{stem}.zip",
    )


@app.route("/convert", methods=["POST"])
def convert_legacy():
    """Legacy one-shot endpoint — PDF → ZIP (no review step)."""
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    f = request.files["pdf"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are accepted."}), 400
    pdf_bytes = f.read()
    if not pdf_bytes:
        return jsonify({"error": "The uploaded file is empty."}), 400

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / f.filename
            pdf_path.write_bytes(pdf_bytes)
            yaml_path = Path(tmpdir) / (pdf_path.stem + "_config.yaml")
            config_dict = extract_to_yaml(str(pdf_path), str(yaml_path))
        zip_bytes = _build_zip(config_dict)
    except Exception as exc:
        return jsonify({"error": f"Conversion failed: {exc}"}), 500

    warnings = _validate_config(config_dict)
    stem = Path(f.filename).stem
    response = send_file(
        io.BytesIO(zip_bytes),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{stem}_converted.zip",
    )
    if warnings:
        import json, base64
        response.headers["X-Conversion-Warnings"] = base64.b64encode(
            json.dumps(warnings).encode()
        ).decode()
    return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
