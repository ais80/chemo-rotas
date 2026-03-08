"""HTML parser for PICS chemotherapy protocol pages.

Parses Microsoft Word-exported .htm files into the ParsedProtocol intermediate format.
"""

import re
from pathlib import Path
from bs4 import BeautifulSoup, Tag
from models import (
    ParsedProtocol, ProtocolHeader, ChemoRow, NonSequencedRow,
    ProceedRuleDrug, SectionContent, TreatmentData, RowType,
)
from review_flags import ReviewFlagCollector
from proceed_rules_parser import parse_proceed_rules
from utils import clean_text, clean_cell_text, is_strikethrough, is_empty_section


SECTION_ANCHORS = [
    "eligibility", "exclusions", "tests", "premedications",
    "treatment", "modifications", "precautions", "continue", "support"
]

SECTION_DISPLAY_NAMES = {
    "eligibility": "Eligibility",
    "exclusions": "Exclusions",
    "tests": "Tests",
    "premedications": "Premedications",
    "treatment": "Treatment",
    "modifications": "Dose Modifications",
    "precautions": "Precautions",
    "continue": "Continue treatment if",
    "support": "Support Medications",
}


class HTMLProtocolParser:
    def __init__(self, html_path: str):
        self.html_path = html_path
        with open(html_path, 'r', encoding='utf-8') as f:
            self.soup = BeautifulSoup(f.read(), 'lxml')
        self.flags = ReviewFlagCollector()

    def parse(self) -> ParsedProtocol:
        header = self._parse_header()
        sections = self._extract_all_sections()

        # Parse treatment tables
        treatment = self._parse_treatment(sections.get("treatment"))

        # Parse proceed rules from tests section
        proceed_rules = self._parse_proceed_rules(sections.get("tests"))

        # Build warnings from tests section (validity info, pre-proceed-rules text)
        warnings = self._extract_warnings(sections.get("tests"))

        # Build info from precautions section
        info = self._extract_info_text(sections.get("precautions"))

        protocol = ParsedProtocol(
            header=header,
            eligibility=self._make_section_content("eligibility", sections),
            exclusions=self._make_section_content("exclusions", sections),
            tests=self._make_section_content("tests", sections),
            premedications=self._make_section_content("premedications", sections),
            treatment=treatment,
            proceed_rules=proceed_rules,
            dose_modifications=self._make_section_content("modifications", sections),
            precautions=self._make_section_content("precautions", sections),
            continue_treatment=self._make_section_content("continue", sections),
            support_medications=self._make_section_content("support", sections),
            review_flags=self.flags.get_all(),
            warnings_text=warnings,
            info_text=info,
        )
        return protocol

    # ── Header Extraction ──────────────────────────────────────────────

    def _parse_header(self) -> ProtocolHeader:
        """Extract regimen name, rota code, and last updated date from the header."""
        title_ps = self.soup.find_all('p', class_='msosectiontitle')
        if not title_ps:
            self.flags.error("header", "title", "No msosectiontitle elements found")
            return ProtocolHeader("", "", "")

        regimen_name = ""
        rota_code = ""
        last_updated = ""

        for p in title_ps:
            text = clean_text(p)
            if not text:
                continue

            # Check for "Last updated:" pattern
            if 'last updated' in text.lower():
                # Collapse all whitespace (including newlines) for the date
                flat_text = re.sub(r'\s+', ' ', text)
                match = re.search(r'Last updated:\s*(.+)', flat_text, re.IGNORECASE)
                if match:
                    last_updated = match.group(1).strip()
                continue

            # Check font size to distinguish name vs code
            span = p.find('span')
            if span:
                style = span.get('style', '')
                # Small font (8pt) = rota code
                if '8.0pt' in style and not ('font-weight:normal' in style):
                    rota_code = text.strip()
                    continue
                # Large font (18pt, 20pt) = regimen name
                size_match = re.search(r'font-size:\s*(\d+)', style)
                if size_match and int(size_match.group(1)) >= 14:
                    regimen_name = text.strip()
                    continue

            # Fallback: if text looks like a code (starts with letter, has numbers)
            if re.match(r'^[A-Z]+-?ROTA', text):
                rota_code = text.strip()
            elif not regimen_name:
                regimen_name = text.strip()

        # Clean up the regimen name
        regimen_name = re.sub(r'<!--.*?-->', '', regimen_name).strip()
        regimen_name = re.sub(r'\s+', ' ', regimen_name)  # Collapse whitespace

        return ProtocolHeader(regimen_name, rota_code, last_updated)

    # ── Section Extraction ─────────────────────────────────────────────

    def _extract_all_sections(self) -> dict[str, list[Tag]]:
        """Extract content <p> elements for each named section.

        Returns dict mapping anchor name -> list of <p> Tag elements in that section.
        """
        sections = {}
        for anchor_name in SECTION_ANCHORS:
            anchor = self.soup.find('a', attrs={'name': anchor_name})
            if not anchor:
                self.flags.info(anchor_name, "section", f"Section anchor '{anchor_name}' not found")
                continue

            # Navigate up to the containing <tr>
            header_tr = anchor.find_parent('tr')
            if not header_tr:
                continue

            # The content is in the next <tr> sibling(s) until the "Top" link row
            content_elements = []
            current_tr = header_tr.find_next_sibling('tr')

            while current_tr:
                # Check if this is a "Top" link row or next section header
                if self._is_top_link_row(current_tr) or self._is_section_header_row(current_tr):
                    break
                # Collect all <p> elements from this row
                for p in current_tr.find_all('p'):
                    content_elements.append(p)
                # Also collect any tables in this row (for treatment section)
                current_tr = current_tr.find_next_sibling('tr')

            sections[anchor_name] = content_elements

        return sections

    def _is_top_link_row(self, tr: Tag) -> bool:
        """Check if a <tr> is the 'Top' navigation link row."""
        link = tr.find('a', href='#home')
        return link is not None

    def _is_section_header_row(self, tr: Tag) -> bool:
        """Check if a <tr> contains a section header (msosectionheader)."""
        return tr.find('p', class_='msosectionheader') is not None

    def _make_section_content(self, anchor_name: str, sections: dict) -> SectionContent:
        """Convert extracted <p> elements to SectionContent."""
        p_elements = sections.get(anchor_name, [])
        paragraphs = []
        for p in p_elements:
            text = clean_text(p)
            if text and text != '\xa0':
                paragraphs.append(text)

        empty = is_empty_section(paragraphs)
        return SectionContent(
            section_name=SECTION_DISPLAY_NAMES.get(anchor_name, anchor_name),
            text_paragraphs=paragraphs,
            is_empty=empty,
        )

    # ── Treatment Table Parsing ────────────────────────────────────────

    def _parse_treatment(self, p_elements: list[Tag] | None) -> TreatmentData:
        """Parse treatment section which contains CHEMOTHERAPY and/or NON-SEQUENCED tables."""
        if not p_elements:
            return TreatmentData()

        # We need to find tables within the treatment section's parent container
        # Navigate from the treatment anchor to find the containing cell
        treatment_anchor = self.soup.find('a', attrs={'name': 'treatment'})
        if not treatment_anchor:
            self.flags.warn("treatment", "section", "Treatment section anchor not found")
            return TreatmentData()

        # Walk up to the treatment content area and find all tables within it
        header_tr = treatment_anchor.find_parent('tr')
        if not header_tr:
            return TreatmentData()

        # Collect all content TRs for the treatment section
        content_trs = []
        current_tr = header_tr.find_next_sibling('tr')
        while current_tr:
            if self._is_top_link_row(current_tr) or self._is_section_header_row(current_tr):
                break
            content_trs.append(current_tr)
            current_tr = current_tr.find_next_sibling('tr')

        # Find all tables within the treatment content
        tables = []
        for tr in content_trs:
            tables.extend(tr.find_all('table'))

        # Identify which tables are CHEMOTHERAPY vs NON-SEQUENCED
        # Look for header text "CHEMOTHERAPY" or column headers "DRUG/DILUENT"
        chemo_table = None
        nonseq_table = None

        # Also check text before/between tables for "CHEMOTHERAPY", "NON-SEQUENCED" labels
        all_text = ' '.join(clean_text(p) for p in p_elements)

        for table in tables:
            header_text = self._get_table_header_text(table)
            if not header_text:
                continue

            if 'Stage day' in header_text or 'DOSE CALCULATION' in header_text:
                # This could be either CHEMOTHERAPY or NON-SEQUENCED
                if 'DRUG/DILUENT' in header_text:
                    if chemo_table is None:
                        chemo_table = table
                    else:
                        # Second table with DRUG/DILUENT — this is the fluids/non-sequenced variant
                        pass
                elif 'Mode' in header_text or 'Freq' in header_text:
                    nonseq_table = table
                elif chemo_table is None:
                    chemo_table = table
                else:
                    nonseq_table = table

        # Parse the identified tables
        chemo_rows = []
        nonseq_rows = []
        has_chemo = False
        has_nonseq = False

        if chemo_table:
            chemo_rows = self._parse_chemo_table(chemo_table)
            has_chemo = len(chemo_rows) > 0

        if nonseq_table:
            nonseq_rows = self._parse_nonsequenced_table(nonseq_table)
            has_nonseq = len(nonseq_rows) > 0

        # If we found tables but couldn't classify them, try alternate approach
        if not has_chemo and not has_nonseq and tables:
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) < 3:
                    continue
                cols = rows[0].find_all('td')
                num_cols = len(cols)

                # Try to parse as NON-SEQUENCED if it has Mode/Freq columns
                header = ' '.join(clean_cell_text(c) for c in cols)
                if 'Mode' in header or 'Freq' in header:
                    nonseq_rows = self._parse_nonsequenced_table(table)
                    has_nonseq = len(nonseq_rows) > 0
                elif 'DRUG/DILUENT' in header or 'RATE' in header:
                    chemo_rows = self._parse_chemo_table(table)
                    has_chemo = len(chemo_rows) > 0

        return TreatmentData(
            chemo_rows=chemo_rows,
            non_sequenced_rows=nonseq_rows,
            has_chemo_table=has_chemo,
            has_nonsequenced_table=has_nonseq,
        )

    def _get_table_header_text(self, table: Tag) -> str:
        """Get concatenated text from the first 2 rows of a table (header rows)."""
        rows = table.find_all('tr', recursive=False)
        if not rows:
            return ""
        texts = []
        for row in rows[:2]:
            for cell in row.find_all('td'):
                t = clean_cell_text(cell)
                if t:
                    texts.append(t)
        return ' '.join(texts)

    def _parse_chemo_table(self, table: Tag) -> list[ChemoRow]:
        """Parse a CHEMOTHERAPY (sequenced) table into ChemoRow objects."""
        rows = table.find_all('tr', recursive=False)
        if len(rows) < 3:
            return []

        # Determine column count from header
        header_cells = rows[0].find_all('td')
        num_cols = sum(int(c.get('colspan', 1)) for c in header_cells)

        results = []
        for row in rows[2:]:  # Skip 2 header rows
            cells = row.find_all('td', recursive=False)
            if not cells:
                continue

            # Check for strikethrough on any cell
            row_type = RowType.NORMAL
            for cell in cells:
                if is_strikethrough(cell):
                    row_type = RowType.DOSE_REDUCTION
                    break

            # Extract cell values by position
            cell_texts = [clean_cell_text(c) for c in cells]

            # Pad to expected length
            while len(cell_texts) < 13:
                cell_texts.append("")

            # Skip completely empty rows
            if not any(t.strip() for t in cell_texts):
                continue

            chemo_row = ChemoRow(
                stage_day=cell_texts[0],
                time=cell_texts[1],
                drug_diluent=cell_texts[2],
                round_dose_to=cell_texts[3] if num_cols >= 13 else "",
                dose_calc_volume=cell_texts[4] if num_cols >= 13 else cell_texts[3],
                rate=cell_texts[5] if num_cols >= 13 else cell_texts[4],
                route=cell_texts[6] if num_cols >= 13 else cell_texts[5],
                special_directions=cell_texts[7] if num_cols >= 13 else cell_texts[6],
                target_interval=cell_texts[8] if num_cols >= 13 else cell_texts[7],
                margin=cell_texts[9] if num_cols >= 13 else cell_texts[8],
                follows_seq_label=cell_texts[10] if num_cols >= 13 else cell_texts[9],
                line=cell_texts[11] if num_cols >= 13 else cell_texts[10],
                seq_label=cell_texts[12] if num_cols >= 13 else cell_texts[11],
                row_type=row_type,
            )
            results.append(chemo_row)

        if not results:
            self.flags.info("treatment", "chemo_table", "CHEMOTHERAPY table found but no data rows")

        return results

    def _parse_nonsequenced_table(self, table: Tag) -> list[NonSequencedRow]:
        """Parse a NON-SEQUENCED table into NonSequencedRow objects."""
        rows = table.find_all('tr', recursive=False)
        if len(rows) < 3:
            return []

        # Determine if there's an extra "Round to nearest" column
        header_cells = rows[0].find_all('td')
        header_text = ' '.join(clean_cell_text(c) for c in header_cells)
        has_round_col = 'Round' in header_text

        results = []
        for row in rows[2:]:  # Skip 2 header rows
            cells = row.find_all('td', recursive=False)
            if not cells:
                continue

            row_type = RowType.NORMAL
            for cell in cells:
                if is_strikethrough(cell):
                    row_type = RowType.DOSE_REDUCTION
                    break

            cell_texts = [clean_cell_text(c) for c in cells]

            # Pad
            while len(cell_texts) < 14:
                cell_texts.append("")

            # Skip empty rows
            if not any(t.strip() for t in cell_texts):
                continue

            # Adjust column offsets if "Round to nearest" column is present
            offset = 1 if has_round_col else 0

            ns_row = NonSequencedRow(
                drug=cell_texts[0],
                dose_calculation=cell_texts[1],
                mode=cell_texts[2 + offset],
                freq=cell_texts[3 + offset],
                timing_constraints=cell_texts[4 + offset],
                route=cell_texts[5 + offset],
                form=cell_texts[6 + offset],
                start_with_oof=cell_texts[7 + offset],
                first_dose_day=cell_texts[8 + offset],
                first_dose_time=cell_texts[9 + offset],
                final_dose_day=cell_texts[10 + offset],
                final_dose_time=cell_texts[11 + offset],
                group=cell_texts[12 + offset] if (12 + offset) < len(cell_texts) else "",
                row_type=row_type,
            )
            results.append(ns_row)

        return results

    # ── Proceed Rules ──────────────────────────────────────────────────

    def _parse_proceed_rules(self, p_elements: list[Tag] | None) -> list[ProceedRuleDrug]:
        """Parse proceed rules from the tests section."""
        if not p_elements:
            return []
        return parse_proceed_rules(p_elements, self.flags)

    # ── Warnings & Info Extraction ─────────────────────────────────────

    def _extract_warnings(self, p_elements: list[Tag] | None) -> list[str]:
        """Extract warning text from the tests section (pre-proceed-rules content)."""
        if not p_elements:
            return []

        warnings = []
        for p in p_elements:
            text = clean_text(p)
            if not text or text == '\xa0':
                continue
            if 'PROCEED RULES' in text.upper():
                break  # Everything after PROCEED RULES is handled by proceed_rules_parser
            warnings.append(text)

        return warnings

    def _extract_info_text(self, p_elements: list[Tag] | None) -> list[str]:
        """Extract info text from the precautions section."""
        if not p_elements:
            return []
        texts = []
        for p in p_elements:
            text = clean_text(p)
            if text and text != '\xa0':
                texts.append(text)
        return texts
