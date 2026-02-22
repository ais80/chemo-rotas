# Chemo Rota to EPMA Converter

Converts paper chemotherapy rota PDFs into structured files for the PICS EPMA system:
- **TXT** — coded import file for direct upload to PICS
- **DOCX** — 4-table template for human review

## Setup

### 1. Install system packages
```bash
sudo apt install tesseract-ocr poppler-utils python3-venv
```

### 2. Create Python environment
```bash
cd "/home/office/Documents/PICS/Chemo rotas"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

### Step 1: Place your PDF
Copy the chemo rota PDF into the `input/` folder.

### Step 2: Extract config from PDF
```bash
.venv/bin/python3 convert.py extract "input/YourRota.pdf"
```
This creates a config YAML file in `output/` with data extracted from the PDF.

### Step 3: Review and edit the config YAML
Open the generated YAML in a text editor and:

1. **Fill in `CHANGE_ME` fields** (these cannot be extracted from the PDF):
   - `drug_prefix` — short uppercase code, e.g. `DARO`
   - `ticket_number` — PICS change ticket number, e.g. `10350`
   - `specialty_class` — rota classification, e.g. `UROLOGY`

2. **Verify extracted data** — check doses, blood test thresholds, indication text

3. **Clean up OCR artifacts** — especially in `rota_info_paragraphs` (scanned PDFs can produce noisy text)

### Step 4: Generate outputs
```bash
.venv/bin/python3 convert.py generate "output/YourRota_config.yaml"
```
This creates two files in `output/`:
- `#<ticket><PREFIX>.txt` — the PICS EPMA import file
- `<DocCode> <DrugName>.docx` — the 4-table template

### Step 5: Review before uploading
Always check the generated TXT and DOCX against the original PDF before uploading to PICS.

## Example (Darolutamide)

```bash
# Extract
.venv/bin/python3 convert.py extract "Rota example/Drota930 Darolutamide.pdf"

# Edit output/Drota930 Darolutamide_config.yaml:
#   drug_prefix: DARO
#   ticket_number: 10350
#   specialty_class: UROLOGY

# Generate
.venv/bin/python3 convert.py generate "output/Drota930 Darolutamide_config.yaml"

# Outputs:
#   output/#10350DARO.txt
#   output/Drota930 Darolutamide.docx
```

## Project Structure

```
Chemo rotas/
  convert.py             CLI entry point
  converter/             Python package
    extract_pdf.py         PDF -> config YAML
    generate_txt.py        config -> TXT
    generate_docx.py       config -> DOCX
    models.py              data classes
  input/                 Drop new PDFs here
  output/                Generated files appear here
  Rota example/          Reference files
  requirements.txt       Python dependencies
  CLAUDE.md              Full technical specification
```

## Notes

- Scanned PDFs are handled via OCR (tesseract) with automatic rotation detection
- The config YAML is an intermediate step so you can review and correct extracted data before generating outputs
- Fields the converter cannot read (BSA-based doses, poor scan quality) are flagged with
  `dose: 0` and `DOSE UNKNOWN — OCR could not read dose, check original rota` in
  `timing_constraints`, so a human reviewer can find and correct them
- See `CLAUDE.md` for the full technical specification of the TXT file format
- See `CHANGES.md` for the development changelog and testing history
- See `output/PDF_Extraction_Testing_Report.html` for the latest PDF extraction test report
  (open in any browser or LibreOffice)
