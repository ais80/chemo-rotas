#!/usr/bin/env python3
"""Chemo Rota to EPMA Converter — Phase 1 CLI.

Usage:
    # Step 1: Extract PDF or HTML to config YAML (review and edit the YAML)
    python3 convert.py extract <pdf_path>
    python3 convert.py extract <htm_path>   # PICS info page HTML — more accurate

    # Step 2: Generate DOCX + TXT from reviewed config YAML
    python3 convert.py generate <yaml_path>

    # One-shot: Extract + generate (skip review step)
    python3 convert.py auto <pdf_path>
"""

import sys
import os
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from converter.models import RotaConfig
from converter.extract_pdf import extract_to_yaml, load_config
from converter.extract_html import extract_html_to_yaml
from converter.generate_txt import generate_txt
from converter.generate_docx import generate_docx


def validate_config(d: dict) -> list[str]:
    """Check for CHANGE_ME values and other issues. Returns list of errors."""
    errors = []
    for field in ["drug_prefix", "ticket_number", "specialty_class"]:
        val = d.get(field, "")
        if val == "CHANGE_ME" or not val:
            errors.append(f"'{field}' is not set — you must provide this value in the YAML")
    if not d.get("templates"):
        errors.append("No drug templates found — check PDF extraction or add manually")
    if not d.get("blood_tests"):
        errors.append("No blood tests found — check PDF extraction or add manually")
    return errors


def cmd_extract(input_path: str):
    """Extract PDF or HTML to config YAML."""
    src = Path(input_path)
    if not src.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    yaml_name = src.stem + "_config.yaml"
    yaml_path = output_dir / yaml_name

    print(f"Extracting: {src.name}")
    print(f"Output:     {yaml_path}")
    print()

    if src.suffix.lower() in ('.htm', '.html'):
        print("  Source type: HTML (PICS info page) — structured extraction")
        extract_html_to_yaml(str(src), str(yaml_path))
    else:
        extract_to_yaml(str(src), str(yaml_path))

    print(f"Config YAML written to: {yaml_path}")
    print()
    print("=== NEXT STEPS ===")
    print(f"1. Open and review: {yaml_path}")
    print("2. Fill in all CHANGE_ME fields (drug_prefix, ticket_number, specialty_class)")
    print("3. Verify extracted data (doses, blood tests, thresholds)")
    print(f"4. Run: python3 convert.py generate {yaml_path}")


def cmd_generate(yaml_path: str):
    """Generate DOCX + TXT from config YAML."""
    yp = Path(yaml_path)
    if not yp.exists():
        print(f"Error: YAML not found: {yaml_path}")
        sys.exit(1)

    config_dict = load_config(str(yp))

    # Validate
    errors = validate_config(config_dict)
    if errors:
        print("=== VALIDATION ERRORS ===")
        for e in errors:
            print(f"  ERROR: {e}")
        print()
        print(f"Please fix these in: {yaml_path}")
        sys.exit(1)

    config = RotaConfig.from_dict(config_dict)

    output_dir = yp.parent
    base_name = config.document_code

    # Generate TXT
    txt_path = output_dir / f"#{config.ticket_number}{config.drug_prefix}.txt"
    txt_content = generate_txt(config)
    with open(txt_path, 'w', newline='') as f:
        f.write(txt_content)
    print(f"TXT generated: {txt_path}")

    # Generate DOCX
    docx_path = output_dir / f"{base_name} {config.drug_full_name}.docx"
    generate_docx(config, str(docx_path))
    print(f"DOCX generated: {docx_path}")

    print()
    print("=== DONE ===")
    print("Please review both files before uploading to PICS.")


def cmd_auto(pdf_path: str):
    """Extract + generate in one step (for testing with pre-filled configs)."""
    pdf = Path(pdf_path)
    if not pdf.exists():
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    yaml_name = pdf.stem + "_config.yaml"
    yaml_path = output_dir / yaml_name

    print(f"Extracting: {pdf.name}")
    extract_to_yaml(str(pdf), str(yaml_path))
    print(f"Config YAML: {yaml_path}")

    # Check for CHANGE_ME
    config_dict = load_config(str(yaml_path))
    errors = validate_config(config_dict)
    if errors:
        print()
        print("=== AUTO MODE: Config has unfilled fields ===")
        for e in errors:
            print(f"  WARNING: {e}")
        print()
        print(f"Edit the YAML at: {yaml_path}")
        print(f"Then run: python3 convert.py generate {yaml_path}")
        return

    cmd_generate(str(yaml_path))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    path = sys.argv[2]

    if command == "extract":
        cmd_extract(path)
    elif command == "generate":
        cmd_generate(path)
    elif command == "auto":
        cmd_auto(path)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
