"""Utility functions for HTML text extraction and classification."""

import re
from bs4 import Tag, NavigableString, Comment


FLUID_KEYWORDS = [
    'sodium chloride', 'normal saline', 'n/saline', 'saline',
    'dextrose', 'glucose', 'water for injection',
    'hartmann', 'ringer',
]

# These are standalone fluids only when they appear as the sole drug
FLUID_ADDITIVES = [
    'potassium chloride', 'sodium bicarbonate', 'magnesium',
    'mannitol', 'calcium gluconate',
]


def clean_text(element) -> str:
    """Extract clean text from a BeautifulSoup element, preserving superscripts inline."""
    if element is None:
        return ""
    if isinstance(element, NavigableString):
        return str(element).strip()

    parts = []
    for child in element.children:
        if isinstance(child, Comment):
            continue  # Skip HTML comments
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            if child.name == 'sup':
                parts.append(child.get_text())
            elif child.name == 'br':
                parts.append('\n')
            else:
                parts.append(clean_text(child))
    text = ''.join(parts)
    # Collapse runs of whitespace (but preserve explicit newlines)
    text = re.sub(r'[^\S\n]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()


def clean_cell_text(td_element) -> str:
    """Extract text from a table cell, joining paragraphs with newlines."""
    if td_element is None:
        return ""
    paragraphs = td_element.find_all('p')
    if not paragraphs:
        return clean_text(td_element)
    texts = []
    for p in paragraphs:
        t = clean_text(p)
        if t and t != '\xa0':
            texts.append(t)
    return '\n'.join(texts)


def is_strikethrough(td_element) -> bool:
    """Check if a table cell's content has strikethrough formatting."""
    if td_element is None:
        return False
    # Check for <s> or <strike> tags
    if td_element.find(['s', 'strike']):
        return True
    # Check for CSS text-decoration:line-through on spans
    for span in td_element.find_all('span'):
        style = span.get('style', '')
        if 'line-through' in style:
            return True
    return False


def is_bold_element(p_element) -> bool:
    """Check if a paragraph element starts with or contains bold text."""
    if p_element is None:
        return False
    b_tag = p_element.find('b')
    if b_tag:
        return True
    # Check for font-weight:bold in style
    for span in p_element.find_all('span'):
        style = span.get('style', '')
        if 'font-weight:bold' in style:
            return True
    return False


def get_bold_text(p_element) -> str:
    """Extract just the bold portion of a paragraph."""
    if p_element is None:
        return ""
    b_tag = p_element.find('b')
    if b_tag:
        return clean_text(b_tag)
    for span in p_element.find_all('span'):
        style = span.get('style', '')
        if 'font-weight:bold' in style:
            return clean_text(span)
    return ""


def is_fluid_row(drug_name: str) -> bool:
    """Determine if a drug name represents a standalone fluid (not a drug+diluent combo)."""
    name_lower = drug_name.lower().strip()
    # If it contains a slash (like "Etoposide/Sodium Chloride"), it's a drug+diluent, not pure fluid
    if '/' in drug_name and not name_lower.startswith(('sodium', 'potassium', 'n/')):
        return False
    for kw in FLUID_KEYWORDS:
        if kw in name_lower:
            return True
    for kw in FLUID_ADDITIVES:
        if kw in name_lower:
            return True
    return False


def is_empty_section(paragraphs: list[str]) -> bool:
    """Check if a section's content is effectively empty."""
    if not paragraphs:
        return True
    cleaned = [p.strip() for p in paragraphs if p.strip() and p.strip() != '\xa0']
    if not cleaned:
        return True
    if len(cleaned) == 1 and cleaned[0].lower() in ('nothing entered', 'none', 'n/a'):
        return True
    return False


def split_dose_calc_volume(dose_str: str) -> tuple[str, str, str]:
    """Split a dose/calculation/volume string into (calculation, dose, volume).

    Examples:
        "100mg/m2/1000ml" -> ("100mg/m2", "", "1000ml")
        "12 mg/m2 / 50ml" -> ("12 mg/m2", "", "50ml")
        "8mg" -> ("", "8mg", "")
        "1 capsule" -> ("", "1 capsule", "")
        "300mcg (if weight <80kg)" -> ("", "300mcg (if weight <80kg)", "")
    """
    if not dose_str:
        return ("", "", "")

    # Try to find a volume at the end (e.g., "/1000ml", "/ 50ml")
    vol_match = re.search(r'/\s*(\d+\s*ml)\s*$', dose_str, re.IGNORECASE)
    if vol_match:
        volume = vol_match.group(1).strip()
        calc = dose_str[:vol_match.start()].strip()
        return (calc, "", volume)

    # Check if it's a per-body-surface-area calculation
    if '/m2' in dose_str.lower() or '/m²' in dose_str:
        return (dose_str, "", "")

    # Otherwise it's a flat dose
    return ("", dose_str, "")


def split_drug_diluent(drug_diluent: str) -> tuple[str, str]:
    """Split a DRUG/DILUENT string into (drug_name, diluent).

    Examples:
        "ETOPOSIDE / Sodium chloride 0.9%" -> ("ETOPOSIDE", "Sodium chloride 0.9%")
        "Metoclopramide" -> ("Metoclopramide", "")
        "Sodium chloride 0.9%" -> ("", "Sodium chloride 0.9%")
    """
    if not drug_diluent:
        return ("", "")

    # Check if it's a pure fluid
    if is_fluid_row(drug_diluent):
        return ("", drug_diluent)

    # Try splitting on " / " or "/"
    parts = re.split(r'\s*/\s*', drug_diluent, maxsplit=1)
    if len(parts) == 2:
        drug = parts[0].strip()
        diluent = parts[1].strip()
        # Verify the second part looks like a fluid
        if is_fluid_row(diluent):
            return (drug, diluent)
        # Otherwise keep combined
        return (drug_diluent, "")

    return (drug_diluent, "")
