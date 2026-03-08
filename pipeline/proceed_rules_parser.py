"""Parser for the Proceed Rules section of PICS HTML protocols.

Handles three patterns:
1. Single drug with all 4 subsections (DROTA932)
2. Multiple drugs each with full subsections (OROTA105av2)
3. Shared neutrophils/platelets then per-drug renal/hepatic (IPROTA502TAK)
"""

import re
from bs4 import Tag
from models import ProceedRuleDrug
from utils import clean_text, is_bold_element, get_bold_text


SUBSECTION_NAMES = ['neutrophils', 'platelets', 'renal', 'hepatic']


def parse_proceed_rules(p_elements: list[Tag], flags) -> list[ProceedRuleDrug]:
    """Parse proceed rules from <p> elements from the Tests section.

    Returns list of ProceedRuleDrug, one per drug found.
    """
    # Find the start of PROCEED RULES
    start_idx = None
    for i, p in enumerate(p_elements):
        text = clean_text(p)
        if 'PROCEED RULES' in text.upper():
            start_idx = i + 1
            break

    if start_idx is None:
        flags.warn("tests", "proceed_rules", "No PROCEED RULES section found")
        return []

    # Parse into blocks: shared block + per-drug blocks
    shared = {'neutrophils': [], 'platelets': [], 'renal': [], 'hepatic': []}
    drugs: list[dict] = []  # Each is {'name': str, 'neutrophils': [], ...}
    current_target = shared  # Where text currently goes (shared or a drug dict)
    current_subsection = None
    extra_text = []  # Text outside known subsections

    for p in p_elements[start_idx:]:
        text = clean_text(p)
        if not text or text == '\xa0':
            continue

        bold_text = get_bold_text(p)
        text_upper = text.upper().strip()
        bold_upper = bold_text.upper().strip()

        # Check for DRUG: NAME header
        drug_match = (
            re.match(r'DRUG\s*[:\s]\s*(.+)', bold_upper) or
            re.match(r'DRUG\s*[:\s]\s*(.+)', text_upper)
        )
        if drug_match:
            drug_name = drug_match.group(1).strip()
            drug_dict = {
                'name': drug_name,
                'neutrophils': [], 'platelets': [], 'renal': [], 'hepatic': []
            }
            drugs.append(drug_dict)
            current_target = drug_dict
            current_subsection = None
            continue

        # Check for subsection headers
        matched_sub = None
        for sub in SUBSECTION_NAMES:
            if bold_upper.startswith(sub.upper()) or (
                is_bold_element(p) and text_upper.startswith(sub.upper())
            ):
                matched_sub = sub
                break

        if matched_sub:
            current_subsection = matched_sub
            # Extract any value text on the same line after the bold header
            remaining = text
            if bold_text:
                remaining = remaining.replace(bold_text, '', 1).strip()
            else:
                remaining = re.sub(r'^' + re.escape(matched_sub), '', remaining, flags=re.IGNORECASE).strip()
            if remaining:
                current_target[current_subsection].append(remaining)
            continue

        # Accumulate text into current subsection
        if current_subsection:
            current_target[current_subsection].append(text)
        else:
            # Text outside any subsection — extra clinical info
            extra_text.append(text)

    # Build ProceedRuleDrug objects
    results = []
    for drug_dict in drugs:
        prd = ProceedRuleDrug(
            drug_name=drug_dict['name'],
            neutrophils='\n'.join(drug_dict['neutrophils']),
            platelets='\n'.join(drug_dict['platelets']),
            renal='\n'.join(drug_dict['renal']),
            hepatic='\n'.join(drug_dict['hepatic']),
        )
        # Apply shared values where the drug doesn't have its own
        if not prd.neutrophils and shared['neutrophils']:
            prd.neutrophils = '\n'.join(shared['neutrophils'])
        if not prd.platelets and shared['platelets']:
            prd.platelets = '\n'.join(shared['platelets'])
        if not prd.renal and shared['renal']:
            prd.renal = '\n'.join(shared['renal'])
        if not prd.hepatic and shared['hepatic']:
            prd.hepatic = '\n'.join(shared['hepatic'])
        results.append(prd)

    # If no DRUG: headers were found but there are shared subsections,
    # create a single generic entry
    if not drugs and any(shared[k] for k in SUBSECTION_NAMES):
        results.append(ProceedRuleDrug(
            drug_name="(General)",
            neutrophils='\n'.join(shared['neutrophils']),
            platelets='\n'.join(shared['platelets']),
            renal='\n'.join(shared['renal']),
            hepatic='\n'.join(shared['hepatic']),
        ))

    if extra_text:
        flags.info("tests", "proceed_rules_extra",
                    f"Extra text after proceed rules ({len(extra_text)} paragraphs) - "
                    "check if it should go to Warnings")

    return results
