"""Main entry point for the chemotherapy protocol conversion pipeline.

Usage:
    # Forward: HTML → PICS + Rota
    python pipeline/convert.py                          # Default: 3 PoC files
    python pipeline/convert.py DROTA932.htm             # Single file
    python pipeline/convert.py --all                    # All .htm files

    # Reverse: Rota .docx/.doc → PICS + HTML
    python pipeline/convert.py --reverse                # All .docx/.doc in Rotas/
    python pipeline/convert.py --reverse "H-ROTA 175.docx"  # Single file
    python pipeline/convert.py --reverse --html         # Also generate HTML
"""

import argparse
import os
import sys

# Ensure pipeline modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from html_parser import HTMLProtocolParser
from pics_generator import PICSGenerator
from rota_generator import RotaGenerator

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_DIR = os.path.join(BASE_DIR, "Downloaded_pages html rota info")
ROTA_DIR = os.path.join(BASE_DIR, "Rotas")
TEMPLATE_PATH = os.path.join(BASE_DIR, "FLAG PICS template.docx")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

POC_FILES = [
    'DROTA932.htm',
    'OROTA105av2.htm',
    'IPROTA502TAK.htm',
]


def convert_protocol(htm_filename: str):
    """Convert a single .htm file to both PICS and Rota formats."""
    html_path = os.path.join(HTML_DIR, htm_filename)
    if not os.path.exists(html_path):
        print(f"  ERROR: File not found: {html_path}")
        return None

    basename = os.path.splitext(htm_filename)[0]

    # Phase 1: Parse
    print(f"  Parsing HTML...")
    parser = HTMLProtocolParser(html_path)
    protocol = parser.parse()

    print(f"  Header: {protocol.header.regimen_name} ({protocol.header.rota_code})")
    print(f"  Chemo rows: {len(protocol.treatment.chemo_rows)}, "
          f"Non-seq rows: {len(protocol.treatment.non_sequenced_rows)}, "
          f"Proceed rules: {len(protocol.proceed_rules)} drugs")

    # Phase 2: Generate PICS document
    pics_output = os.path.join(OUTPUT_DIR, f"{basename}_PICS.docx")
    print(f"  Generating PICS -> {os.path.basename(pics_output)}")
    try:
        pics_gen = PICSGenerator(TEMPLATE_PATH)
        pics_gen.generate(protocol, pics_output)
        print(f"  PICS generated OK")
    except Exception as e:
        print(f"  PICS generation FAILED: {e}")

    # Phase 3: Generate Rota document
    rota_output = os.path.join(OUTPUT_DIR, f"{basename}_ROTA.docx")
    print(f"  Generating Rota -> {os.path.basename(rota_output)}")
    try:
        rota_gen = RotaGenerator()
        rota_gen.generate(protocol, rota_output)
        print(f"  Rota generated OK")
    except Exception as e:
        print(f"  Rota generation FAILED: {e}")

    # Phase 4: Report review flags
    if protocol.review_flags:
        print(f"  Review flags ({len(protocol.review_flags)}):")
        for flag in protocol.review_flags:
            print(f"    [{flag.severity}] {flag.section}.{flag.field}: {flag.message}")
    else:
        print(f"  No review flags")

    return protocol


def reverse_convert(rota_filename: str, generate_html: bool = False):
    """Convert a Rota .docx/.doc file to PICS format (and optionally HTML)."""
    rota_path = os.path.join(ROTA_DIR, rota_filename)
    if not os.path.exists(rota_path):
        print(f"  ERROR: File not found: {rota_path}")
        return None

    basename = os.path.splitext(rota_filename)[0]
    # Clean basename for output filenames (replace spaces)
    safe_basename = basename.replace(' ', '_')
    ext = os.path.splitext(rota_filename)[1].lower()

    # Phase 1: Parse Rota document
    print(f"  Parsing Rota ({ext})...")
    try:
        if ext == '.docx':
            from rota_parser import RotaDocxParser
            parser = RotaDocxParser(rota_path)
        elif ext == '.doc':
            from rota_parser_doc import RotaDocParser
            parser = RotaDocParser(rota_path)
        else:
            print(f"  ERROR: Unsupported format: {ext}")
            return None

        protocol = parser.parse()
    except Exception as e:
        print(f"  Parse FAILED: {e}")
        return None

    print(f"  Header: {protocol.header.regimen_name} ({protocol.header.rota_code})")
    print(f"  Chemo rows: {len(protocol.treatment.chemo_rows)}, "
          f"Non-seq rows: {len(protocol.treatment.non_sequenced_rows)}, "
          f"Proceed rules: {len(protocol.proceed_rules)} drugs")

    # Phase 2: Generate PICS document
    pics_output = os.path.join(OUTPUT_DIR, f"{safe_basename}_from_rota_PICS.docx")
    print(f"  Generating PICS -> {os.path.basename(pics_output)}")
    try:
        pics_gen = PICSGenerator(TEMPLATE_PATH)
        pics_gen.generate(protocol, pics_output)
        print(f"  PICS generated OK")
    except Exception as e:
        print(f"  PICS generation FAILED: {e}")

    # Phase 3: Generate HTML (if requested)
    if generate_html:
        htm_output = os.path.join(OUTPUT_DIR, f"{safe_basename}_from_rota.htm")
        print(f"  Generating HTML -> {os.path.basename(htm_output)}")
        try:
            from html_generator import HTMLGenerator
            html_gen = HTMLGenerator()
            html_gen.generate(protocol, htm_output)
            print(f"  HTML generated OK")
        except Exception as e:
            print(f"  HTML generation FAILED: {e}")

    # Phase 4: Report review flags
    if protocol.review_flags:
        print(f"  Review flags ({len(protocol.review_flags)}):")
        for flag in protocol.review_flags:
            print(f"    [{flag.severity}] {flag.section}.{flag.field}: {flag.message}")
    else:
        print(f"  No review flags")

    return protocol


def main():
    parser = argparse.ArgumentParser(
        description="Convert PICS chemotherapy protocols between formats"
    )
    parser.add_argument('files', nargs='*',
                        help='Files to convert (HTM for forward, DOCX/DOC for reverse)')
    parser.add_argument('--all', action='store_true',
                        help='Process all files in the source directory')
    parser.add_argument('--reverse', action='store_true',
                        help='Reverse mode: Rota .docx/.doc -> PICS .docx')
    parser.add_argument('--html', action='store_true',
                        help='Also generate HTML output (reverse mode only)')
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.reverse:
        # Reverse mode: Rota → PICS (+ optional HTML)
        if args.all:
            files = [f for f in os.listdir(ROTA_DIR)
                     if f.lower().endswith(('.docx', '.doc'))]
        elif args.files:
            files = args.files
        else:
            # Default: all .docx and .doc files
            files = [f for f in os.listdir(ROTA_DIR)
                     if f.lower().endswith(('.docx', '.doc'))]

        print(f"Reverse converting {len(files)} Rota file(s)...")
        print(f"Source:   {ROTA_DIR}")
        print(f"Template: {TEMPLATE_PATH}")
        print(f"Output:   {OUTPUT_DIR}")

        for f in sorted(files):
            print(f"\n{'='*60}")
            print(f"  {f}")
            print(f"{'='*60}")
            reverse_convert(f, generate_html=args.html)
    else:
        # Forward mode: HTML → PICS + Rota
        if args.all:
            files = [f for f in os.listdir(HTML_DIR) if f.endswith('.htm')]
        elif args.files:
            files = args.files
        else:
            files = POC_FILES

        print(f"Converting {len(files)} file(s)...")
        print(f"Template: {TEMPLATE_PATH}")
        print(f"Output:   {OUTPUT_DIR}")

        for f in files:
            print(f"\n{'='*60}")
            print(f"  {f}")
            print(f"{'='*60}")
            convert_protocol(f)

    print(f"\nDone. Output files in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
