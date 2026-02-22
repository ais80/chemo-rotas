"""Extract structured data from a chemo rota PDF into a config YAML."""

import re
import yaml
import pdfplumber
from pathlib import Path


# ---------------------------------------------------------------------------
# Known IV chemotherapy drug names (all-caps, as they appear on printed rotas)
# ---------------------------------------------------------------------------
_IV_DRUG_NAMES = [
    'FLUDARABINE', 'CYTARABINE', 'GEMCITABINE', 'OXALIPLATIN',
    'BENDAMUSTINE', 'RITUXIMAB', 'CYCLOPHOSPHAMIDE', 'IFOSFAMIDE',
    'DOXORUBICIN', 'EPIRUBICIN', 'BLEOMYCIN', 'VINCRISTINE', 'VINBLASTINE',
    'ETOPOSIDE', 'CARBOPLATIN', 'CISPLATIN', 'PACLITAXEL', 'DOCETAXEL',
    'IDARUBICIN', 'DAUNORUBICIN', 'MITOXANTRONE', 'CARFILZOMIB',
    'BORTEZOMIB', 'METHOTREXATE', 'MESNA', 'OFATUMUMAB', 'OBINUTUZUMAB',
    'ARSENIC TRIOXIDE', 'ARSENIC', 'INOTUZUMAB', 'AMSACRINE',
    'CLOFARABINE', 'NELARABINE', 'ATG', 'ANTITHYMOCYTE',
    'METHYLPREDNISOLONE', 'HYDROCORTISONE', 'DARATUMUMAB', 'ISATUXIMAB',
    'VENETOCLAX', 'IBRUTINIB',
    # NOTE: ACALABRUTINIB, IBRUTINIB are oral capsules — handled by oral dose parser
]

# Sorted longest-first so multi-word names (e.g. ARSENIC TRIOXIDE) match before ARSENIC
_IV_DRUG_NAMES_SORTED = sorted(_IV_DRUG_NAMES, key=len, reverse=True)


# ---------------------------------------------------------------------------
# Text extraction (digital then OCR fallback)
# ---------------------------------------------------------------------------

def extract_text(pdf_path: str) -> str:
    """Extract all text from a PDF file.

    Tries pdfplumber first (for digital PDFs). Falls back to OCR via
    pytesseract + pdf2image for scanned PDFs.
    """
    with pdfplumber.open(pdf_path) as pdf:
        texts = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
    if texts:
        return "\n".join(texts)

    # Fallback: OCR for scanned PDFs
    print("  No digital text found — attempting OCR...")
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(pdf_path, dpi=300)
        texts = []
        for i, img in enumerate(images):
            # Auto-detect rotation: try 0, 90, 270 and pick best keyword score
            best_text = ""
            best_score = -1
            keywords = ['dose', 'mg', 'prescriber', 'blood', 'oral', 'patient',
                        'cancer', 'tablets', 'cycle', 'rota', 'frequency',
                        'saline', 'infusion', 'document', 'fluid']
            for angle in [0, 90, 270]:
                rotated = img.rotate(angle, expand=True) if angle else img
                candidate = pytesseract.image_to_string(rotated, config='--psm 6')
                score = sum(1 for kw in keywords if kw.lower() in candidate.lower())
                if score > best_score:
                    best_score = score
                    best_text = candidate
            if best_text:
                texts.append(best_text)
            print(f"  OCR page {i+1}: {len(best_text)} chars extracted (keyword score: {best_score}/{len(keywords)})")
        return "\n".join(texts)
    except ImportError:
        print("  ERROR: pytesseract/pdf2image not installed. Run:")
        print("    sudo apt install tesseract-ocr")
        print("    .venv/bin/pip install pytesseract pdf2image")
        return ""
    except Exception as e:
        print(f"  ERROR: OCR failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Rota type detection
# ---------------------------------------------------------------------------

def detect_rota_type(text: str) -> str:
    """Detect whether the rota is primarily IV, ORAL, or MIXED.

    Returns: 'IV', 'ORAL', or 'MIXED'
    """
    tl = text.lower()

    # Check if an IV drug name appears in a table-like context (not just interaction text)
    _iv_drug_in_table = any(
        re.search(r'(?:\|[^\n]*' + re.escape(d.lower()) + r'|' + re.escape(d.lower()) + r'[^\n]*\|)',
                  tl)
        for d in _IV_DRUG_NAMES
    )
    iv_signals = [
        bool(re.search(r'n/saline|0\.9%\s*nacl|dextrose|glucose\s*5%', tl)),
        bool(re.search(r'\b\d+\s*ml\b', tl)),
        bool(re.search(r'\d+\s*(?:hour|hr|min)s?\s+infusion', tl)),
        bool(re.search(r'flow\s*rate|iv\s*fluid|drug.*electrolyte|electrolyte.*drug', tl)),
        _iv_drug_in_table,  # IV drug name near pipe chars (table context), not just any mention
        bool(re.search(r'subcutaneous|s/c\b|\bsc\s+inj', tl)),  # SC injectable route
    ]
    oral_signals = [
        bool(re.search(r'starting\s+dose|please\s+supply', tl)),
        bool(re.search(r'\btablets?\b|\bcapsules?\b', tl)),
        bool(re.search(r'take\s+with\s+food|orally\s+days', tl)),
    ]

    iv_score = sum(iv_signals)
    oral_score = sum(oral_signals)

    if iv_score >= 2 and oral_score == 0:
        return 'IV'
    elif iv_score >= 2 and oral_score >= 1:
        return 'MIXED'
    elif oral_score >= 1:
        return 'ORAL'
    else:
        return 'ORAL'  # default — let oral parser try


# ---------------------------------------------------------------------------
# Document code parsing (fixed to handle H-ROTA / HROTA formats)
# ---------------------------------------------------------------------------

def parse_document_code(text: str) -> str:
    """Extract document code from PDF text.

    Handles formats: H-ROTA49, HROTA448, Drota930, etc.
    """
    # Prefer explicit "Document Code: XXXX" label
    # Match HROTA with optional space before digits (e.g. "HROTA 10b") or compact form
    m = re.search(
        r'Document\s*Code\s*[:\-]\s*(H-?ROTA\s*\d+[a-z]?|[A-Za-z][A-Za-z0-9\-]+)',
        text, re.IGNORECASE
    )
    if m:
        # Normalise: remove spaces (e.g. "HROTA 10b" → "HROTA10b")
        return m.group(1).strip().replace(' ', '').rstrip('_')

    # Fallback: scan for rota code patterns
    m = re.search(
        r'\b(H-?ROTA\s*\d+[a-z]?|[A-Z]rota\s*\d+[a-z]?|[Dd]rota\s*\d+[a-z]?)\b',
        text, re.IGNORECASE
    )
    if m:
        return m.group(1).replace(' ', '')

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Oral rota parsers (existing logic, unchanged)
# ---------------------------------------------------------------------------

def parse_drug_name_and_indication(text: str) -> tuple[str, str]:
    """Extract drug name and indication from oral rota title.
    Pattern: '{Drug} for {indication}'
    """
    # Generic words that should never be treated as drug names
    _NOT_DRUG_NAMES = {
        'maintenance', 'treatment', 'therapy', 'regimen', 'protocol',
        'induction', 'consolidation', 'information', 'further', 'patient',
        'please', 'refer', 'supply', 'cycle', 'stage', 'course', 'this',
    }

    m = re.search(
        r'([A-Z][a-z]{3,}(?:amide|inib|umab|izumab|cillin|mycin|ide|ine|ole|ib|ab)?)\s+for\s*\n?\s*(.+?)(?:\n\n|\()',
        text, re.DOTALL
    )
    if m:
        drug = m.group(1).strip()
        if len(drug) >= 5 and drug.lower() not in _NOT_DRUG_NAMES:
            indication = re.sub(r'\s+', ' ', m.group(2)).strip()
            return drug, indication
    m = re.search(r'([A-Z][a-z]{4,})\s+for\s+(.+?)$', text, re.MULTILINE)
    if m:
        drug = m.group(1).strip()
        if drug.lower() not in _NOT_DRUG_NAMES:
            return drug, m.group(2).strip()
    return "UNKNOWN", "UNKNOWN"


def parse_dose_info(text: str) -> list[dict]:
    """Extract dose, frequency, and mode for oral rotas."""
    templates = []

    m = re.search(r'[Ss]tarting\s+dose\s+(?:usually\s+)?(\d+)\s*mg\s+(BD|OD|TDS)', text)
    if m:
        primary_dose = int(m.group(1).rstrip('.'))
        freq = m.group(2)
    else:
        primary_dose = 0
        freq = "BD"

    m_red = re.search(r'[Dd]ose\s+reduced?\s+to\s+(\d+)\s*mg\s*(BD|OD|TDS)?', text)
    reduced_dose = int(m_red.group(1).rstrip('.')) if m_red else None

    form = "TAB"
    route = "ORAL"
    if re.search(r'tablets?', text, re.IGNORECASE):
        form, route = "TAB", "ORAL"
    elif re.search(r'capsules?', text, re.IGNORECASE):
        form, route = "CAP", "ORAL"

    timing = ""
    if re.search(r'[Tt]aken?\s+(?:continuously\s+)?with\s+food', text):
        timing = "Take with food"

    if primary_dose:
        templates.append({
            "dose": primary_dose, "units": "mg", "mode": "TTO",
            "frequency": freq, "route": route, "form": form,
            "timing_constraints": timing, "first_dose_day": 1,
            "final_dose_day": "U", "group": "1A",
        })
        if reduced_dose:
            red_timing = f"Dose reduction  {timing}" if timing else "Dose reduction"
            templates.append({
                "dose": reduced_dose, "units": "mg", "mode": "TTO",
                "frequency": freq, "route": route, "form": form,
                "timing_constraints": red_timing, "first_dose_day": 1,
                "final_dose_day": "U", "group": "1",
            })
        ip_timing = f"Inpatient prescribing {timing}" if timing else "Inpatient prescribing"
        templates.append({
            "dose": primary_dose, "units": "mg", "mode": "REG",
            "frequency": freq, "route": route, "form": form,
            "timing_constraints": ip_timing, "first_dose_day": 1,
            "final_dose_day": "U", "group": "1",
        })

    return templates


# ---------------------------------------------------------------------------
# IV table parser (new)
# ---------------------------------------------------------------------------

def parse_iv_drug_table(text: str) -> list[dict]:
    """Extract IV drug data from a chemo rota drug table.

    Searches the OCR text for known IV drug names, then attempts to extract
    dose, fluid type, volume, and infusion duration from surrounding context.

    OCR from scanned IV tables is often garbled; this extracts what it can.
    Fields that cannot be reliably extracted are left blank for manual review.
    """
    found = {}   # drug_upper -> template dict (deduplicate by drug name)
    lines = text.split('\n')

    for i, line in enumerate(lines):
        line_upper = line.upper()

        matched_drug = None
        for drug in _IV_DRUG_NAMES_SORTED:
            # Require that the drug name is not preceded by a letter or hyphen
            # (prevents matching e.g. "pre-rituximab" as RITUXIMAB)
            if re.search(r'(?<![A-Za-z\-])' + re.escape(drug), line_upper):
                matched_drug = drug
                break

        if not matched_drug or matched_drug in found:
            continue

        # Skip narrative lines — drug mentioned in informational text, not a prescription row.
        # e.g. "Two cycles alternating R-CODOX-M and R-IVAC followed by further doses of Rituximab"
        _NARRATIVE = re.compile(
            r'\b(?:alternating|followed\s+by|further\s+doses?\s+of|prior\s+to|'
            r'instead\s+of|pre[- ](?:medication|treatment)|two\s+cycles|'
            r'subsequent\s+doses?|is\s+given\s+(?:on|as|with)|'
            r'are\s+given\s+(?:on|as|with))\b',
            re.IGNORECASE
        )
        if _NARRATIVE.search(line):
            continue

        # Context for fluid/volume/duration: 1 line before + current + 2 after
        ctx_lines = lines[max(0, i - 1): min(len(lines), i + 3)]
        context = ' '.join(ctx_lines)

        # Dose context: current line ONLY — prevents all cross-drug dose contamination.
        # In sequential drug tables, each drug's dose is on its own row.
        # Including i+1 still allows the NEXT drug's dose to bleed in when the
        # current drug's dose is garbled (e.g. OCR "5"→"S"). A missing template
        # is safer than a template with a grossly wrong dose.
        dose_context = lines[i]

        # Current line only — for route and duration.
        # Route is always on the drug's own row; duration normally too.
        # Including line i+1 causes adjacent drug rows to contaminate these fields.
        curr_line = lines[i]

        # Narrow context: current + 1 ahead — for day range only.
        day_ctx = ' '.join(lines[i: min(len(lines), i + 2)])

        # --- Dose extraction ---
        # Handles: 30mg, 30mg/m², 2g/m², 25mg, 1000mcg
        # OCR artifacts for m²: m?, m", im, m2, /m sq
        dose_val = 0
        units = 'mg'
        bsa_based = False

        dose_m = re.search(
            r'(\d+(?:\.\d+)?)\s*(mg|g|mcg|microgram)s?'
            r'(?:\s*/\s*m\s*[²2?"\']|\s*/m(?:sq|2)|\s*/m\b)?',
            dose_context, re.IGNORECASE
        )
        if dose_m:
            raw = float(dose_m.group(1).rstrip('.'))
            units = dose_m.group(2).lower().replace('microgram', 'mcg')
            if units == 'g':
                dose_val = int(raw * 1000)
                units = 'mg'
            else:
                dose_val = int(raw)
            # Check if BSA-based (m² suffix anywhere near the dose)
            surrounding = dose_context[max(0, dose_m.start() - 5): dose_m.end() + 15]
            bsa_based = bool(re.search(r'/m\s*[²2?"\']|/m(?:sq|2)|/m\b', surrounding, re.IGNORECASE))

        if not dose_val:
            # Dose couldn't be extracted (OCR garble). Still add the drug so the
            # human reviewer can see it and fill in the correct value.
            dose_val = 0
            units = 'mg'
            bsa_based = False

        # --- Route: IV or SC ---
        # Use current line only. Bare \bSC\b is excluded because OCR of signature
        # columns at the row end often produces isolated "SC" / "S" artifacts.
        route = 'IV'
        if re.search(r'\bsubcutaneous\b|\bs/c\b|\bsc\s+inj\b|\bsc\s+injection\b',
                     curr_line, re.IGNORECASE):
            route = 'SC'

        # --- IV fluid type (not applicable for SC) ---
        fluid = ''
        if route == 'IV':
            fluid_m = re.search(
                r'(N/[Ss]aline|0\.9%\s*(?:NaCl|Sodium\s*Chloride)|'
                r'[Dd]extrose\s*5%|D5W|Glucose\s*5%|Hartmann\'?s?)',
                context
            )
            if fluid_m:
                fluid = fluid_m.group(1)
            elif re.search(r'\bSALINE\b', context, re.IGNORECASE):
                fluid = 'N/Saline'

        # --- Volume (ml) ---
        volume = ''
        vol_m = re.search(r'\b(\d{2,4})\s*ml\b', context, re.IGNORECASE)
        if vol_m and route == 'IV':
            volume = vol_m.group(1)

        # --- Infusion duration ---
        # Current line only: line i+1 is the NEXT drug's row in sequential tables
        # and would contribute its own duration, contaminating the current drug.
        duration = ''
        dur_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)', curr_line, re.IGNORECASE)
        if dur_m:
            duration = dur_m.group(0).strip()
        else:
            dur_m = re.search(r'(\d+)\s*(?:minutes?|mins?)', curr_line, re.IGNORECASE)
            if dur_m:
                duration = dur_m.group(0).strip()

        # --- Day range ---
        first_day = 1
        day_m = re.search(r'[Dd]ays?\s*(\d+)(?:\s*[-–]\s*(\d+))?', day_ctx)
        if day_m:
            first_day = int(day_m.group(1))
            last_day = day_m.group(2) if day_m.group(2) else str(first_day)
        else:
            last_day = str(first_day)  # Single-day IV: final = first day

        # --- Timing constraints (special directions) ---
        timing_parts = []
        if dose_val == 0:
            timing_parts.append("DOSE UNKNOWN — OCR could not read dose, check original rota")
        if duration:
            timing_parts.append(f"{duration} infusion")
        timing_m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\s+after\s+(?:start\s+of\s+)?(\w+)',
            context, re.IGNORECASE
        )
        if timing_m:
            timing_parts.append(timing_m.group(0).strip())
        if bsa_based:
            timing_parts.append("dose per m² — confirm BSA calculation")

        group_n = len(found) + 1
        drug_title = matched_drug.title()

        found[matched_drug] = {
            'drug_name_upper': matched_drug,
            'dose': dose_val,
            'units': units,
            'mode': 'REG',
            'frequency': 'OD',
            'route': route,
            'form': 'INJ',
            'timing_constraints': ', '.join(timing_parts),
            'first_dose_day': first_day,
            'final_dose_day': last_day,
            'group': f'{group_n}A',
            'fluid_type': fluid,
            'volume_ml': volume,
            'infusion_duration': duration,
        }

    return list(found.values())


def parse_rota_name_from_iv(text: str, doc_code: str) -> str:
    """Try to infer the rota name for an IV rota.

    Looks for common rota abbreviations, or derives from the document code.
    """
    # Common rota name abbreviations — only specific ones unlikely to appear as common words
    # Longer/more-specific names must come BEFORE shorter prefixes they contain
    # (e.g. 'R-CODOX-M' before 'R-CODOX', 'BEACOPP' before 'BEACOP')
    ROTA_ABBREVIATIONS = [
        'FLAG', 'BEACOPP', 'BEACOP',
        'R-CHOP', 'RCHOP', 'R-CHOEP', 'CHOEP',
        'R-CODOX-M', 'R-CODOX', 'CODOX-M', 'CODOX',
        'R-IVAC', 'IVAC',
        'ABVD', 'GemOx', 'GEMOX', 'D-VTD', 'VTD', 'CarLenDex', 'CARLENDEX',
        'DHAP', 'FLAMSA', 'BuCy', 'BEAM', 'ESHAP',
    ]
    def _find_abbr_in(search_text: str):
        """Return (abbr, suffix) for the highest-count valid, non-nested match.

        Shorter abbreviations (e.g. IVAC, CODOX) are only counted when they are
        NOT a sub-span of a longer compound abbreviation match (e.g. R-IVAC).
        """
        # Step 1: collect all valid match spans for every abbreviation.
        all_matches: dict[str, list[tuple[int, int, str]]] = {}  # abbr → [(start, end, suffix)]
        for abbr in ROTA_ABBREVIATIONS:
            spans = []
            for m in re.finditer(r'\b' + re.escape(abbr) + r'(?:\s+(\d+))?\b',
                                 search_text, re.IGNORECASE):
                trailing = search_text[m.end(): min(len(search_text), m.end() + 40)].lower()
                if re.search(r'\bvs\b|\bversus\b|\bv\b|\btrial\b|\bstudy\b|\bve\b', trailing):
                    continue
                spans.append((m.start(), m.end(), m.group(1) or ''))
            if spans:
                all_matches[abbr] = spans

        # Step 2: build set of spans covered by LONGER abbreviations.
        # A match of shorter abbr is "nested" if any longer abbr span contains it.
        long_spans: list[tuple[int, int]] = []
        for abbr, spans in all_matches.items():
            for start, end, _ in spans:
                long_spans.append((start, end))

        def _is_nested(start: int, end: int) -> bool:
            """True if this span is fully contained within a longer match."""
            for ls, le in long_spans:
                if ls <= start and le >= end and (le - ls) > (end - start):
                    return True
            return False

        # Step 3: count non-nested matches per abbreviation.
        best_abbr: str | None = None
        best_count = 0
        best_suffix: str = ''
        for abbr in ROTA_ABBREVIATIONS:
            if abbr not in all_matches:
                continue
            count = 0
            last_suffix = ''
            for start, end, suffix in all_matches[abbr]:
                if not _is_nested(start, end):
                    count += 1
                    if suffix:
                        last_suffix = suffix
            if count > best_count:
                best_count = count
                best_abbr = abbr
                best_suffix = last_suffix
        return (best_abbr, best_suffix) if best_abbr else (None, '')

    # Pass 1: title area (first 800 chars) — the rota name is usually prominent here.
    title_area = text[:800]
    abbr, suffix = _find_abbr_in(title_area)
    if abbr:
        return f"{abbr} {suffix}".strip() if suffix else abbr

    # Pass 2: full text — fallback using frequency count
    abbr, suffix = _find_abbr_in(text)
    if abbr:
        return f"{abbr} {suffix}".strip() if suffix else abbr

    # Try "Patient label:" line
    m = re.search(r'[Pp]atient\s+label\s*[:\-]\s*([A-Z][A-Za-z0-9\- ]+)', text)
    if m:
        name = m.group(1).strip()
        if len(name) <= 30:
            return name

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Shared parsers (blood tests, monitoring, cycle info, rota info)
# ---------------------------------------------------------------------------

def parse_blood_tests(text: str) -> list[dict]:
    """Extract blood test thresholds from the BLOOD TESTS / Haematology section."""
    tests = []

    m = re.search(r'[Pp][li](?:a)?ts?\s*<\s*([\d.]+)', text)
    if m:
        tests.append({
            "test_code": "PLATS",
            "threshold_value": int(float(m.group(1).rstrip('.'))),
            "threshold_function": "LT",
            "message_text_line1": f"Plts < {m.group(1)} x 10^9/L",
            "message_text_line3": "Contact prescriber.",
        })

    m = re.search(r'[Nn]euts?\s*<\s*([\d.]+)', text)
    if m:
        tests.append({
            "test_code": "NEUTS",
            "threshold_value": int(float(m.group(1).rstrip('.'))),
            "threshold_function": "LT",
            "message_text_line1": f"Neuts < {m.group(1)} x 10 9/L",
            "message_text_line3": "Contact prescriber. Reduced neutrophils common with longer treatment",
        })

    m = re.search(r'(?:GFR|[Rr]enal\s*(?:function)?)\s*[:<]?\s*<?\.?\s*(\d+)\s*m[lL]/min', text)
    if m:
        tests.append({
            "test_code": "GFR",
            "threshold_value": int(m.group(1)),
            "threshold_function": "LT",
            "message_text_line1": f"GFR < {m.group(1)}mL/min",
            "message_text_line3": "Contact prescriber.",
        })

    m = re.search(r'[Bb]ilirubin\s*[>]\s*(\d+)', text)
    if m:
        tests.append({
            "test_code": "BILI",
            "threshold_value": int(m.group(1)),
            "threshold_function": "GT",
            "message_text_line1": f"Bilirubin > {m.group(1)} umol/L",
            "message_text_line3": "Contact prescriber.",
        })

    m = re.search(r'ALT\s*[>]\s*(\d+)', text)
    if m:
        tests.append({
            "test_code": "ALT",
            "threshold_value": int(m.group(1)),
            "threshold_function": "GT",
            "message_text_line1": f"ALT  > {m.group(1)} U/L",
            "message_text_line3": "Contact prescriber.",
        })

    return tests


def parse_monitoring_frequency(text: str) -> int:
    m = re.search(r'[Vv]alidity.*?(\d+)\s*days', text)
    return int(m.group(1)) if m else 7


def parse_cycle_info(text: str, drug_name: str = "") -> str:
    # First: infer from drug name suffix (e.g. "R-CHOP 21" → 21 days → 3w)
    if drug_name:
        m = re.search(r'\s+(\d+)$', drug_name.strip())
        if m:
            days = int(m.group(1))
            if 7 <= days <= 56:  # reasonable cycle range
                return f"{days // 7}w"
    # Second: search for explicit "N day cycle" or "every N days" in text
    m = re.search(r'(\d+)\s*day\s*cycle|every\s+(\d+)\s*days?', text, re.IGNORECASE)
    if m:
        days = int(m.group(1) or m.group(2))
        return f"{days // 7}w"
    return "4w"


def parse_rota_info(text: str) -> list[str]:
    paragraphs = []
    sections = re.split(r'(?:Further Information|BLOOD TESTS|Please supply)', text, flags=re.IGNORECASE)
    if len(sections) > 1:
        for section in sections[1:]:
            for line in section.strip().split('\n'):
                line = line.strip()
                if line and len(line) > 20:
                    paragraphs.append(line)
    return paragraphs


# ---------------------------------------------------------------------------
# Additional Therapy section parser (oral support meds on IV rotas)
# ---------------------------------------------------------------------------

def parse_additional_therapy(text: str, group_start: int = 1) -> list[dict]:
    """Extract oral support medications from the 'Additional Therapy' section.

    These appear at the bottom of older-style IV rotas, e.g.:
        Prednisolone po 100mg daily days 2-5
        Metoclopramide po 10mg tds days 1-7

    Returns a list of TTO template dicts, group-numbered from group_start.
    """
    m = re.search(r'Additional\s+[Tt]herap(?:y|ies)', text)
    if not m:
        return []

    section_text = text[m.end():]
    # Stop at next major section header
    stop = re.search(
        r'\n(?:Blood\s*[Tt]ests|BLOOD\s*TESTS|Further\s*[Ii]nformation|'
        r'Administration|Monitoring|Special\s*[Pp]recautions|Warnings?)',
        section_text
    )
    if stop:
        section_text = section_text[:stop.start()]

    freq_map = {
        'daily': 'OD', 'od': 'OD', 'once daily': 'OD',
        'bd': 'BD', 'twice daily': 'BD',
        'tds': 'TDS', 'three times': 'TDS',
        'qds': 'QDS', 'four times': 'QDS',
    }

    templates = []
    group_n = group_start

    for line in section_text.split('\n'):
        line = line.strip().lstrip('/').strip()
        if not line or len(line) < 8:
            continue

        # Pattern: drug_name [po|oral] dose units freq [days n[-m]]
        # Frequency is limited to known codes to avoid consuming "days" as a word
        pat = re.match(
            r'([A-Za-z][\w\-]+)\s+'            # drug name
            r'(?:po\s+)*'                       # optional "po" (may appear twice in OCR)
            r'(\d+(?:\.\d+)?)\s*(mg|g|mcg)\s+' # dose + units
            r'(daily|od|bd|tds|qds|'            # frequency — explicit codes only
            r'once\s+daily|twice\s+daily|three\s+times\s+daily|four\s+times\s+daily)\s*'
            r'(?:for\s+[\d/]+\w*\s*(?:then\s+\w+)?\s*)?'  # optional "for 3/7 then prn"
            r',?\s*'
            r'(?:days?\s*(\d+)(?:\s*[-–]\s*(\d+))?)?',   # optional day range
            line, re.IGNORECASE
        )
        if not pat:
            continue

        drug = pat.group(1).upper()
        dose_raw = float(pat.group(2))
        units = pat.group(3).lower()
        freq_raw = pat.group(4).lower().strip().rstrip(',')
        first_day_str = pat.group(5)
        last_day_str = pat.group(6)

        if units == 'g':
            dose = int(dose_raw * 1000)
            units = 'mg'
        else:
            dose = int(dose_raw)

        freq = 'OD'
        for k, v in freq_map.items():
            if k in freq_raw:
                freq = v
                break

        first_day = int(first_day_str) if first_day_str else 1
        last_day = last_day_str if last_day_str else str(first_day)

        templates.append({
            'drug_name_upper': drug,
            'dose': dose,
            'units': units,
            'mode': 'TTO',
            'frequency': freq,
            'route': 'ORAL',
            'form': 'Tab',
            'timing_constraints': '',
            'first_dose_day': first_day,
            'final_dose_day': last_day,
            'group': f'{group_n}A',
        })
        group_n += 1

    return templates


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------

def extract_to_yaml(pdf_path: str, output_yaml_path: str) -> dict:
    """Extract data from PDF and write config YAML for human review."""
    text = extract_text(pdf_path)

    rota_type = detect_rota_type(text)
    print(f"  Rota type detected: {rota_type}")

    doc_code = parse_document_code(text)
    blood_tests = parse_blood_tests(text)
    validity_days = parse_monitoring_frequency(text)
    rota_info = parse_rota_info(text)

    if rota_type == 'ORAL':
        drug_name, indication = parse_drug_name_and_indication(text)
        template_dicts = parse_dose_info(text)
        for t in template_dicts:
            t["drug_name_upper"] = drug_name.upper()
        inpatient_or_outpatient = "O"
    else:
        # IV or MIXED — parse the drug table
        template_dicts = parse_iv_drug_table(text)
        drug_name = parse_rota_name_from_iv(text, doc_code)
        indication = "CHANGE_ME"
        inpatient_or_outpatient = "I"

        # Parse oral support meds from "Additional Therapy" section
        additional = parse_additional_therapy(text, group_start=len(template_dicts) + 1)
        if additional:
            template_dicts.extend(additional)

        if rota_type == 'MIXED':
            # Also try to get oral templates (e.g. dexamethasone tablets)
            oral_templates = parse_dose_info(text)
            if oral_templates:
                # Renumber groups to avoid collision with IV groups
                n_iv = len(template_dicts)
                for j, ot in enumerate(oral_templates):
                    ot["drug_name_upper"] = ot.get("drug_name_upper", "UNKNOWN")
                    ot["group"] = str(n_iv + j + 1) + ("A" if ot["group"][-1].isalpha() else "")
                template_dicts.extend(oral_templates)

    # Cycle delay: infer from drug name suffix first, then text, then default 4w
    cycle_delay = parse_cycle_info(text, drug_name)

    # Auto-detect directorate: H-ROTA prefix → Haematology, D-ROTA → Oncology
    if re.match(r'H-?ROTA', doc_code, re.IGNORECASE):
        directorate = "HAE"
    else:
        directorate = "ONC"

    config = {
        "document_code": doc_code,
        "drug_full_name": drug_name,
        "indication": indication,
        "reference": f"SmPC for {drug_name}",
        "drug_prefix": "CHANGE_ME",
        "ticket_number": "CHANGE_ME",
        "default_cycles": 12,
        "cycle_delay": cycle_delay,
        "directorate": directorate,
        "specialty_class": "CHANGE_ME",
        "inpatient_or_outpatient": inpatient_or_outpatient,
        "templates": template_dicts,
        "blood_test_validity_days": validity_days,
        "blood_tests": blood_tests,
        "rota_info_paragraphs": rota_info,
        "warnings_paragraphs": [
            f"Validity of FBC {validity_days}   days",
            f"Validity of U&E, LFTs, {validity_days} days",
        ],
    }

    with open(output_yaml_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True, width=120)

    return config


def load_config(yaml_path: str) -> dict:
    """Load a reviewed config YAML file."""
    with open(yaml_path, 'r') as f:
        return yaml.safe_load(f)
