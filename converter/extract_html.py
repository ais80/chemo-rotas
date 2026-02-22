"""Extract structured data from a PICS HTML rota info page (HROTA*.htm).

These HTML files are the PICS clinical information pages, generated from Microsoft Word
and stored at http://pics-client-web/static/PICS/Specialties/Oncology/<DOCCODE>.htm.

They contain exactly the data needed for the PICS EPMA configuration:
  - CHEMOTHERAPY table  → IV/SC infusion schedule (maps to DOCX Table 0)
  - FLUIDS table         → non-sequenced fluids (maps to DOCX Table 1)
  - NON-SEQUENCED table  → drug templates with TTO/REG modes (maps to DOCX Table 2)
  - Tests section        → blood test validity + proceed rules (maps to DOCX Table 3)
"""

import re
import yaml
from pathlib import Path
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cell_text(td, include_strikethrough=False) -> str:
    """Get clean text from a table cell, optionally ignoring strikethrough."""
    if not include_strikethrough:
        # Remove <s>...</s> content (alternate/inactive entries)
        for s in td.find_all('s'):
            s.decompose()
    text = td.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove non-breaking spaces and other noise
    text = text.replace('\xa0', '').strip()
    return text if text not in ('', '-', '\u2013', '\u2014') else ''


def _row_is_strikethrough(tr) -> bool:
    """Return True if the majority of this row's cells are struck through."""
    tds = tr.find_all('td')
    if not tds:
        return False
    struck = sum(1 for td in tds if td.find('s'))
    return struck >= len(tds) // 2


def _parse_dose(raw: str) -> tuple[int, str]:
    """Parse a dose string like '375mg/m²/500ml', '100mg', '1g' into (value_mg, units).

    Returns (dose_value, units_string).  Converts g → mg.
    Volume part (/500ml) is ignored here — extracted separately.
    """
    if not raw:
        return 0, 'mg'
    # Take only the first dose component (before /)
    part = raw.split('/')[0].strip()
    m = re.match(r'([\d.]+)\s*(mg|g|mcg|microgram|unit)', part, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        unit = m.group(2).lower().replace('microgram', 'mcg')
        if unit == 'g':
            return int(val * 1000), 'mg'
        return int(val), unit
    return 0, 'mg'


def _parse_volume(raw: str) -> str:
    """Extract volume in ml from a string like '375mg/m²/500ml'."""
    m = re.search(r'(\d+)\s*ml', raw, re.IGNORECASE)
    return m.group(1) if m else ''


def _is_bsa(raw: str) -> bool:
    """Return True if the dose is per m² (BSA-based)."""
    return bool(re.search(r'/m\s*[²2]|per\s*m\s*sq', raw, re.IGNORECASE))


def _parse_day(raw: str) -> int:
    """Parse a stage day string to int (default 1)."""
    m = re.search(r'\d+', raw)
    return int(m.group()) if m else 1


def _parse_final_day(raw: str) -> str:
    """Parse final dose day — returns int or 'U' (until stopped)."""
    if not raw or raw.upper() in ('U', 'UNTIL', ''):
        return 'U'
    m = re.search(r'\d+', raw)
    return m.group() if m else 'U'


# ---------------------------------------------------------------------------
# Section finders
# ---------------------------------------------------------------------------

def _find_section(soup: BeautifulSoup, anchor_name: str):
    """Find the element with <a name=anchor_name> and return its ancestor row/cell."""
    a = soup.find('a', attrs={'name': anchor_name})
    return a


def _find_bold_text(soup, text: str, after_element=None):
    """Find a <b> or <p><b> element containing the given text."""
    for b in soup.find_all(['b', 'strong']):
        if text.lower() in b.get_text().lower():
            return b
    return None


def _tables_after(element, n=1) -> list:
    """Find the next n tables in the document after the given element."""
    results = []
    for sib in element.find_all_next():
        if sib.name == 'table':
            results.append(sib)
            if len(results) >= n:
                break
    return results


# ---------------------------------------------------------------------------
# Rota name and document code
# ---------------------------------------------------------------------------

def parse_html_header(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract rota name and document code from the HTML title area.

    Returns (rota_name, document_code).
    """
    rota_name = 'UNKNOWN'
    doc_code = 'UNKNOWN'

    titles = soup.find_all(class_='msosectiontitle')
    for t in titles:
        text = t.get_text(strip=True)
        # Document code is usually in a <span> with small font or on second title line
        if re.match(r'H-?ROTA\d+|HROTA\d+|[A-Z]ROTA\d+', text, re.IGNORECASE):
            doc_code = text.strip()
        elif text and rota_name == 'UNKNOWN':
            rota_name = text.strip()

    return rota_name, doc_code


# ---------------------------------------------------------------------------
# Blood tests (Tests section)
# ---------------------------------------------------------------------------

def parse_html_blood_tests(soup: BeautifulSoup) -> tuple[list[dict], int]:
    """Extract blood test proceed rules and validity days from the Tests section.

    Returns (blood_tests_list, validity_days).
    """
    tests_anchor = _find_section(soup, 'tests')
    if not tests_anchor:
        return [], 7

    # Get all text within the tests section (up to the next anchor)
    section_text = ''
    for el in tests_anchor.find_all_next():
        if el.name == 'a' and el.get('name') and el.get('name') != 'tests':
            break
        section_text += el.get_text(separator='\n') + '\n'

    tests = []
    validity_days = 7

    # Blood test validity days
    m = re.search(r'[Vv]alidity of (?:platelets and neutrophils|FBC).*?=?\s*(\d+)\s*days?', section_text)
    if m:
        validity_days = int(m.group(1))

    # Parse thresholds line-by-line (handles multi-paragraph HTML structure)
    lines = [l.strip() for l in section_text.splitlines() if l.strip()]

    def _find_threshold_and_action(lines, keyword_re, threshold_re):
        """Find (value_str, action_str) by scanning for keyword then threshold."""
        for i, line in enumerate(lines):
            if re.search(keyword_re, line, re.IGNORECASE):
                # Look ahead for threshold
                for j in range(i + 1, min(i + 5, len(lines))):
                    tm = re.search(threshold_re, lines[j])
                    if tm:
                        # Action is next non-threshold, non-empty line
                        action = 'Contact prescriber.'
                        for k in range(j + 1, min(j + 4, len(lines))):
                            al = lines[k]
                            if al and not re.search(r'^[x×]\s*10|^/L|^\d+\s*$', al):
                                action = al.rstrip('.')  + '.'
                                break
                        return tm.group(1), action
        return None, None

    # Neutrophils
    val_s, action = _find_threshold_and_action(
        lines,
        r'^neutrophils?$',
        r'[≤<]\s*([\d.]+)',
    )
    if val_s:
        val = float(val_s)
        tests.append({
            'test_code': 'NEUTS',
            'threshold_value': val,
            'threshold_function': 'LT',
            'message_text_line1': f'Neuts < {val} x 10 9/L',
            'message_text_line3': action or 'Contact prescriber.',
        })

    # Platelets
    val_s, action = _find_threshold_and_action(
        lines,
        r'^platelets?$',
        r'[≤<]\s*([\d.]+)',
    )
    if val_s:
        val = int(float(val_s))
        tests.append({
            'test_code': 'PLATS',
            'threshold_value': val,
            'threshold_function': 'LT',
            'message_text_line1': f'Plts < {val} x 10^9/L',
            'message_text_line3': action or 'Contact prescriber.',
        })

    # GFR / Renal threshold
    m = re.search(r'GFR\s*[<≤]\s*(\d+)', section_text)
    if m:
        val = int(m.group(1))
        tests.append({
            'test_code': 'GFR',
            'threshold_value': val,
            'threshold_function': 'LT',
            'message_text_line1': f'GFR < {val}mL/min',
            'message_text_line3': 'Contact prescriber.',
        })

    # Bilirubin threshold (take first / lowest threshold that triggers action)
    m = re.search(r'[Bb]ilirubin\s*[>≥]\s*(\d+)', section_text)
    if m:
        val = int(m.group(1))
        tests.append({
            'test_code': 'BILI',
            'threshold_value': val,
            'threshold_function': 'GT',
            'message_text_line1': f'Bilirubin > {val} umol/L',
            'message_text_line3': 'Contact prescriber.',
        })

    # ALT threshold
    m = re.search(r'ALT\s*[>≥]\s*(\d+)', section_text)
    if m:
        val = int(m.group(1))
        tests.append({
            'test_code': 'ALT',
            'threshold_value': val,
            'threshold_function': 'GT',
            'message_text_line1': f'ALT > {val} U/L',
            'message_text_line3': 'Contact prescriber.',
        })

    # Sort by canonical order: NEUTS, PLATS, GFR, BILI, ALT
    order = {'NEUTS': 0, 'PLATS': 1, 'GFR': 2, 'BILI': 3, 'ALT': 4}
    tests.sort(key=lambda t: order.get(t['test_code'], 99))

    return tests, validity_days


# ---------------------------------------------------------------------------
# Treatment table: CHEMOTHERAPY section (Table 0 — IV/SC drugs)
# ---------------------------------------------------------------------------

def parse_html_chemo_table(soup: BeautifulSoup) -> list[dict]:
    """Parse the CHEMOTHERAPY treatment table.

    Columns: Stage day | Time | Drug/Diluent | Round dose | Dose/Vol |
             Rate | Route | Special directions | Target interval | Margin |
             Follows seq. label | Line | Seq. label

    Returns a list of template dicts for injectable (IV/SC) drugs.
    Primary templates have group ending in a letter (e.g. '1A').
    """
    # Find the bold CHEMOTHERAPY heading within the treatment section
    treatment_anchor = _find_section(soup, 'treatment')
    if not treatment_anchor:
        return []

    chemo_heading = None
    for el in treatment_anchor.find_all_next(['b', 'strong', 'p']):
        txt = el.get_text(strip=True)
        if txt.upper() == 'CHEMOTHERAPY':
            chemo_heading = el
            break
        # Stop at next anchor (section boundary)
        if el.name == 'a' and el.get('name') and el.get('name') != 'treatment':
            break

    if not chemo_heading:
        return []

    # Get the first large table after this heading
    tables = _tables_after(chemo_heading, n=3)
    chemo_table = None
    for t in tables:
        # The chemotherapy table has at least 10 columns and multiple rows
        rows = t.find_all('tr')
        if len(rows) > 2:
            first_data_cells = rows[2].find_all('td') if len(rows) > 2 else []
            if len(first_data_cells) >= 8:
                chemo_table = t
                break

    if not chemo_table:
        return []

    templates = []
    rows = chemo_table.find_all('tr')
    # Skip header rows (first 2 rows are headers)
    for tr in rows[2:]:
        if _row_is_strikethrough(tr):
            continue  # skip alternates/dose reductions

        tds = tr.find_all('td')
        if len(tds) < 7:
            continue

        # Column mapping (0-indexed):
        # 0=Stage day, 1=Time, 2=Drug/Diluent, 3=Round dose, 4=Dose/Vol,
        # 5=Rate, 6=Route, 7=Special dirs, 8=Target interval, 9=Margin,
        # 10=Follows seq, 11=Line, 12=Seq label
        day_raw = _cell_text(tds[0])
        time_raw = _cell_text(tds[1])
        drug_raw = _cell_text(tds[2])
        dose_raw = _cell_text(tds[4]) if len(tds) > 4 else ''
        rate_raw = _cell_text(tds[5]) if len(tds) > 5 else ''
        route_raw = _cell_text(tds[6]) if len(tds) > 6 else ''
        special_raw = _cell_text(tds[7]) if len(tds) > 7 else ''
        seq_label = _cell_text(tds[-1]) if tds else ''  # last column = seq label

        if not drug_raw or not seq_label:
            continue

        # Parse drug name (before '/' which separates drug from diluent)
        drug_name = drug_raw.split('/')[0].strip().upper()
        # Remove brand names in parentheses e.g. "Rituximab (RIXATHON)" → "RITUXIMAB"
        drug_name = re.sub(r'\s*\(.*?\)', '', drug_name).strip()

        dose_val, units = _parse_dose(dose_raw)
        volume = _parse_volume(dose_raw)
        bsa = _is_bsa(dose_raw)

        # Route normalisation
        route_upper = route_raw.upper()
        if route_upper in ('PO', 'ORAL'):
            route = 'ORAL'
        elif route_upper in ('SC', 'S/C', 'SUBCUT'):
            route = 'SC'
        elif route_upper in ('IVB', 'IV BOLUS', 'IVBOLUS'):
            route = 'IV'
        else:
            route = route_upper or 'IV'

        # Infusion duration from rate column or special directions
        duration = ''
        dur_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|minutes?|mins?)', rate_raw, re.IGNORECASE)
        if dur_m:
            duration = dur_m.group(0).strip()

        timing_parts = []
        if duration:
            timing_parts.append(f'{duration} infusion')
        if special_raw:
            timing_parts.append(special_raw)
        if bsa:
            timing_parts.append('dose per m² — confirm BSA calculation')

        first_day = _parse_day(day_raw)

        templates.append({
            'drug_name_upper': drug_name,
            'dose': dose_val,
            'units': units,
            'mode': 'REG',
            'frequency': 'OD',
            'route': route,
            'form': 'INJ',
            'timing_constraints': ', '.join(timing_parts),
            'first_dose_day': first_day,
            'final_dose_day': str(first_day),
            'group': seq_label,
            'fluid_type': '',
            'volume_ml': volume,
            'infusion_duration': duration,
        })

    return templates


# ---------------------------------------------------------------------------
# Non-sequenced table (Table 2 — oral/other drug templates)
# ---------------------------------------------------------------------------

def parse_html_nonseq_table(soup: BeautifulSoup) -> list[dict]:
    """Parse the NON-SEQUENCED drug templates table.

    Columns: Drug | Dose | Mode | Freq | Timing constraints | Route | Form |
             OOF | First day | First time | Final day | Final time | Group

    Returns a list of template dicts for oral/non-sequenced drugs.
    Only includes primary (non-strikethrough) rows.
    """
    # Find the NON-SEQUENCED heading (may be "NON SEQUENCED" or "NON-SEQUENCED")
    nonseq_heading = None
    for el in soup.find_all(['b', 'strong', 'p']):
        if re.search(r'non.?sequenced', el.get_text(strip=True), re.IGNORECASE):
            nonseq_heading = el
            break

    if not nonseq_heading:
        return []

    tables = _tables_after(nonseq_heading, n=2)
    nonseq_table = None
    for t in tables:
        rows = t.find_all('tr')
        if len(rows) > 2:
            cells = rows[2].find_all('td') if len(rows) > 2 else []
            if len(cells) >= 10:
                nonseq_table = t
                break

    if not nonseq_table:
        return []

    templates = []
    rows = nonseq_table.find_all('tr')
    # Skip 2 header rows
    for tr in rows[2:]:
        if _row_is_strikethrough(tr):
            continue

        tds = tr.find_all('td')
        if len(tds) < 10:
            continue

        # Column mapping:
        # 0=Drug, 1=Dose, 2=Mode, 3=Freq, 4=Constraints, 5=Route, 6=Form,
        # 7=OOF, 8=First day, 9=First time, 10=Final day, 11=Final time, 12=Group
        drug_raw = _cell_text(tds[0]).upper()
        dose_raw = _cell_text(tds[1])
        mode_raw = _cell_text(tds[2]).upper()
        freq_raw = _cell_text(tds[3]).upper()
        constraints_raw = _cell_text(tds[4])
        route_raw = _cell_text(tds[5]).upper()
        form_raw = _cell_text(tds[6])
        first_day_raw = _cell_text(tds[8]) if len(tds) > 8 else '1'
        final_day_raw = _cell_text(tds[10]) if len(tds) > 10 else 'U'
        group_raw = _cell_text(tds[12]) if len(tds) > 12 else ''

        if not drug_raw or not mode_raw:
            continue

        dose_val, units = _parse_dose(dose_raw)

        # Route normalisation
        route_map = {'PO': 'ORAL', 'ORAL': 'ORAL', 'SC': 'SC', 'S/C': 'SC',
                     'IV': 'IV', 'IVB': 'IV', 'IM': 'IM'}
        route = route_map.get(route_raw, route_raw)

        # Mode normalisation
        mode = 'TTO' if mode_raw in ('TTO', 'T', 'OUT') else 'REG'

        # Form: capitalise title case
        form = form_raw.title() if form_raw else ('Tab' if route == 'ORAL' else 'Inj')

        templates.append({
            'drug_name_upper': drug_raw,
            'dose': dose_val,
            'units': units,
            'mode': mode,
            'frequency': freq_raw or 'OD',
            'route': route,
            'form': form,
            'timing_constraints': constraints_raw,
            'first_dose_day': _parse_day(first_day_raw),
            'final_dose_day': _parse_final_day(final_day_raw),
            'group': group_raw,
        })

    return templates


# ---------------------------------------------------------------------------
# Rota info paragraphs (precautions, support info)
# ---------------------------------------------------------------------------

def parse_html_rota_info(soup: BeautifulSoup) -> list[str]:
    """Extract rota information paragraphs from precautions/support sections."""
    paragraphs = []
    for anchor_name in ('precautions', 'continue', 'support'):
        anchor = _find_section(soup, anchor_name)
        if not anchor:
            continue
        for el in anchor.find_all_next('p'):
            # Stop at next section anchor
            if el.find('a', attrs={'name': True}):
                break
            text = el.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text).strip()
            # Skip nav bar (multiple | separators), "Top" links, and boilerplate
            if (text and text.lower() not in ('nothing entered', 'top', '')
                    and text.count('|') < 3):
                paragraphs.append(text)
    return paragraphs


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------

def extract_html_to_yaml(html_path: str, output_yaml_path: str) -> dict:
    """Extract data from a PICS HTML info page and write config YAML."""
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    print(f'  Parsing HTML: {Path(html_path).name}')

    rota_name, doc_code = parse_html_header(soup)
    print(f'  Rota: {rota_name}  |  Doc code: {doc_code}')

    blood_tests, validity_days = parse_html_blood_tests(soup)
    print(f'  Blood tests found: {len(blood_tests)}')

    iv_templates = parse_html_chemo_table(soup)
    print(f'  Chemotherapy drugs found: {len(iv_templates)}')

    oral_templates = parse_html_nonseq_table(soup)
    print(f'  Non-sequenced templates found: {len(oral_templates)}')

    rota_info = parse_html_rota_info(soup)

    all_templates = iv_templates + oral_templates

    # Detect inpatient/outpatient
    inpatient_or_outpatient = 'I' if iv_templates else 'O'

    # Auto-detect directorate from document code
    if re.match(r'H-?ROTA', doc_code, re.IGNORECASE):
        directorate = 'HAE'
    else:
        directorate = 'ONC'

    config = {
        'document_code': doc_code,
        'drug_full_name': rota_name,
        'indication': 'CHANGE_ME',
        'reference': f'SmPC for {rota_name}',
        'drug_prefix': 'CHANGE_ME',
        'ticket_number': 'CHANGE_ME',
        'default_cycles': 6,
        'cycle_delay': '3w',
        'directorate': directorate,
        'specialty_class': 'CHANGE_ME',
        'inpatient_or_outpatient': inpatient_or_outpatient,
        'templates': all_templates,
        'blood_test_validity_days': validity_days,
        'blood_tests': blood_tests,
        'rota_info_paragraphs': rota_info,
        'warnings_paragraphs': [
            f'Validity of FBC {validity_days} days',
            f'Validity of LFTs {validity_days} days',
        ],
    }

    with open(output_yaml_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True, width=120)

    return config
