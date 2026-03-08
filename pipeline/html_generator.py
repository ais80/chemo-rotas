"""HTML generator: ParsedProtocol -> PICS-style HTML file.

Produces HTML matching the structure of existing .htm protocol files
with msosectiontitle/msosectionheader CSS classes and anchor-linked sections.
"""

import html as html_mod
from models import (
    ParsedProtocol, ChemoRow, NonSequencedRow, ProceedRuleDrug,
    SectionContent, RowType,
)
from utils import is_fluid_row

SECTIONS = [
    ('eligibility', 'Eligibility'),
    ('exclusions', 'Exclusions'),
    ('tests', 'Tests'),
    ('premedications', 'Premedications'),
    ('treatment', 'Treatment'),
    ('modifications', 'Dose Modifications'),
    ('precautions', 'Precautions'),
    ('continue', 'Continue treatment if'),
    ('support', 'Support Medications'),
]

NAV_ITEMS = [
    ('eligibility', 'Eligibility'),
    ('exclusions', 'Exclusions'),
    ('tests', 'Tests'),
    ('premedications', 'Premedications'),
    ('treatment', 'Treatment'),
    ('modifications', 'Dose Modifications'),
    ('precautions', 'Precautions'),
    ('continue', 'Continue treatment if'),
    ('support', 'Support Medications'),
]


class HTMLGenerator:
    def generate(self, protocol: ParsedProtocol, output_path: str):
        """Generate PICS-style HTML file from ParsedProtocol."""
        parts = [
            self._head(protocol.header.regimen_name),
            self._body_start(),
            self._nav_bar(),
            self._header_block(protocol),
        ]

        # Section content map
        section_map = {
            'eligibility': protocol.eligibility,
            'exclusions': protocol.exclusions,
            'premedications': protocol.premedications,
            'modifications': protocol.dose_modifications,
            'precautions': protocol.precautions,
            'continue': protocol.continue_treatment,
            'support': protocol.support_medications,
        }

        for anchor, display in SECTIONS:
            if anchor == 'treatment':
                parts.append(self._section_header(anchor, display))
                parts.append(self._treatment_content(protocol))
                parts.append(self._top_link())
            elif anchor == 'tests':
                parts.append(self._section_header(anchor, display))
                parts.append(self._tests_content(protocol))
                parts.append(self._top_link())
            else:
                section = section_map.get(anchor, SectionContent())
                parts.append(self._section_header(anchor, display))
                parts.append(self._section_content(section))
                parts.append(self._top_link())

        parts.append(self._nav_bar())
        parts.append(self._body_end())

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(parts))

    # ── Head & Body ───────────────────────────────────────────────────

    def _head(self, title: str) -> str:
        return f"""<html>
<head>
<meta http-equiv=Content-Type content="text/html; charset=utf-8">
<meta name=Generator content="PICS Pipeline (Reverse Parser)">
<title>PICS Rota Information</title>
<style>
<!--
p.MsoNormal, li.MsoNormal, div.MsoNormal
\t{{margin:0cm;margin-bottom:.0001pt;font-size:9.0pt;
\tfont-family:"Arial","sans-serif";color:black;}}
a:link, span.MsoHyperlink
\t{{font-family:"Arial","sans-serif";color:black;text-decoration:none none;}}
a:visited, span.MsoHyperlinkFollowed
\t{{font-family:"Arial","sans-serif";color:black;text-decoration:none none;}}
p.msosectiontitle, li.msosectiontitle, div.msosectiontitle
\t{{mso-style-name:msosectiontitle;margin:0cm;margin-bottom:.0001pt;
\tfont-size:18.0pt;font-family:"Arial","sans-serif";color:red;font-weight:bold;}}
p.msosectionheader, li.msosectionheader, div.msosectionheader
\t{{mso-style-name:msosectionheader;margin:0cm;margin-bottom:.0001pt;
\tfont-size:12.0pt;font-family:"Arial","sans-serif";color:black;font-weight:bold;}}
@page WordSection1
\t{{size:595.3pt 841.9pt;margin:72.0pt 90.0pt 72.0pt 90.0pt;}}
div.WordSection1
\t{{page:WordSection1;}}
-->
</style>
</head>"""

    def _body_start(self) -> str:
        return """<body bgcolor="#F1F1F1" lang=EN-GB link=black vlink=black>
<div class=WordSection1>
<div align=center>
<table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0 width=1863
 style='width:558.75pt'>
 <tr style='height:6.0pt'>
  <td colspan=2 style='padding:0cm;height:6.0pt'>
  <p class=MsoNormal><span style='font-size:6.0pt'>&nbsp;</span></p>
  </td>
 </tr>
 <tr>
  <td width=24 style='width:7.2pt;padding:0cm'>
  <p class=MsoNormal>&nbsp;</p>
  </td>
  <td style='padding:0cm'>
  <div align=center>
  <table class=MsoNormalTable border=1 cellspacing=0 cellpadding=0 width=1850
   style='width:555.0pt'>"""

    def _body_end(self) -> str:
        return """  </table>
  </div>
  </td>
 </tr>
</table>
</div>
</div>
</body>
</html>"""

    # ── Navigation Bar ────────────────────────────────────────────────

    def _nav_bar(self) -> str:
        links = []
        for anchor, display in NAV_ITEMS:
            links.append(
                f'<a href="#{anchor}" title="Click here to read {display}">'
                f'<span style=\'font-size:8.5pt\'>{display}</span></a>'
            )
        nav_text = ' | '.join(links)
        return f"""   <tr>
    <td style='padding:0cm'>
    <table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0
     width="100%" style='width:100.0%'>
     <tr>
      <td width=24 style='width:7.2pt;padding:0cm'>
      <p class=MsoNormal><a name=home>&nbsp;</a></p>
      </td>
      <td style='padding:0cm'>
      <p class=MsoNormal align=center style='text-align:center'>
      {nav_text}
      </p>
      </td>
     </tr>
    </table>
    </td>
   </tr>"""

    # ── Header Block ──────────────────────────────────────────────────

    def _header_block(self, protocol: ParsedProtocol) -> str:
        h = protocol.header
        esc_name = html_mod.escape(h.regimen_name)
        esc_code = html_mod.escape(h.rota_code)
        date_html = ''
        if h.last_updated:
            date_html = (
                f"<p class=msosectiontitle align=right style='text-align:right'>"
                f"<span style='font-size:8.0pt;font-weight:normal'>"
                f"Last updated: {html_mod.escape(h.last_updated)}</span></p>"
            )
        return f"""   <tr>
    <td valign=top style='padding:0cm'>
    <table class=MsoNormalTable border=0 cellspacing=5 cellpadding=0
     width="100%">
     <tr style='height:6.0pt'>
      <td style='padding:.75pt;height:6.0pt'>
      <p class=MsoNormal><span style='font-size:6.0pt'>&nbsp;</span></p>
      </td>
     </tr>
     <tr>
      <td valign=top style='padding:.75pt'>
      <table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0
       width="100%">
       <tr>
        <td valign=top style='padding:0cm'>
        <table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0
         style='border-collapse:collapse'>
         <tr>
          <td valign=top style='border:solid windowtext 1.0pt;
          padding:0cm 5.4pt'>
          <p class=msosectiontitle><span style='font-size:20.0pt'>{esc_name}</span></p>
          <p class=msosectiontitle><span style='font-size:8.0pt'>{esc_code}</span></p>
          </td>
          <td valign=top style='border:solid windowtext 1.0pt;border-left:none;
          padding:0cm 5.4pt'>
          {date_html}
          </td>
         </tr>
        </table>
        <div class=MsoNormal align=center style='text-align:center'>
        <hr size=2 width="100%" align=center>
        </div>
        <p class=MsoNormal><span style='color:red'>The following information
        has not been checked by pharmacy</span></p>
        </td>
       </tr>
      </table>
      </td>"""

    # ── Section Header ────────────────────────────────────────────────

    def _section_header(self, anchor: str, display: str) -> str:
        return f"""     <tr>
      <td valign=top style='background:#336699;padding:.75pt'>
      <p class=msosectionheader><a name="{anchor}"><span
      style='color:white'>{html_mod.escape(display)}</span></a></p>
      </td>
     </tr>"""

    # ── Section Content ───────────────────────────────────────────────

    def _section_content(self, section: SectionContent) -> str:
        if section.is_empty or not section.text_paragraphs:
            return """     <tr>
      <td valign=top style='padding:.75pt'>
      <p class=MsoNormal>Nothing entered</p>
      </td>
     </tr>"""

        paras = '\n      '.join(
            f"<p class=MsoNormal>{html_mod.escape(t)}</p>"
            for t in section.text_paragraphs
        )
        return f"""     <tr>
      <td valign=top style='padding:.75pt'>
      {paras}
      </td>
     </tr>"""

    def _top_link(self) -> str:
        return """     <tr>
      <td valign=top style='padding:.75pt'>
      <p class=MsoNormal align=right style='text-align:right'>
      <a href="#home"><span style='font-size:8.0pt'>Top</span></a></p>
      </td>
     </tr>"""

    # ── Tests Section ─────────────────────────────────────────────────

    def _tests_content(self, protocol: ParsedProtocol) -> str:
        parts = []

        # Warnings text
        if protocol.warnings_text:
            for text in protocol.warnings_text:
                parts.append(
                    f"<p class=MsoNormal>{html_mod.escape(text)}</p>"
                )

        # Proceed rules
        if protocol.proceed_rules:
            parts.append(
                "<p class=MsoNormal><b>PROCEED RULES</b></p>"
            )
            for rule in protocol.proceed_rules:
                parts.append(
                    f"<p class=MsoNormal><b>DRUG: "
                    f"{html_mod.escape(rule.drug_name)}</b></p>"
                )
                if rule.neutrophils:
                    parts.append(
                        f"<p class=MsoNormal><b>Neutrophils</b></p>"
                    )
                    parts.append(
                        f"<p class=MsoNormal>"
                        f"{html_mod.escape(rule.neutrophils)}</p>"
                    )
                if rule.platelets:
                    parts.append(
                        f"<p class=MsoNormal><b>Platelets</b></p>"
                    )
                    parts.append(
                        f"<p class=MsoNormal>"
                        f"{html_mod.escape(rule.platelets)}</p>"
                    )
                if rule.renal:
                    parts.append(
                        f"<p class=MsoNormal><b>Renal</b></p>"
                    )
                    parts.append(
                        f"<p class=MsoNormal>"
                        f"{html_mod.escape(rule.renal)}</p>"
                    )
                if rule.hepatic:
                    parts.append(
                        f"<p class=MsoNormal><b>Hepatic</b></p>"
                    )
                    parts.append(
                        f"<p class=MsoNormal>"
                        f"{html_mod.escape(rule.hepatic)}</p>"
                    )

        if not parts:
            return """     <tr>
      <td valign=top style='padding:.75pt'>
      <p class=MsoNormal>Nothing entered</p>
      </td>
     </tr>"""

        content = '\n      '.join(parts)
        return f"""     <tr>
      <td valign=top style='padding:.75pt'>
      {content}
      </td>
     </tr>"""

    # ── Treatment Section ─────────────────────────────────────────────

    def _treatment_content(self, protocol: ParsedProtocol) -> str:
        parts = []

        # Separate chemo rows into drugs vs fluids
        drug_rows = [r for r in protocol.treatment.chemo_rows
                     if not is_fluid_row(r.drug_diluent)]
        fluid_rows = [r for r in protocol.treatment.chemo_rows
                      if is_fluid_row(r.drug_diluent)]

        # CHEMOTHERAPY table
        if drug_rows or fluid_rows:
            parts.append(
                "<p class=MsoNormal><b>CHEMOTHERAPY</b></p>"
            )
            parts.append(self._chemo_table_html(drug_rows + fluid_rows))

        # NON-SEQUENCED table
        if protocol.treatment.non_sequenced_rows:
            parts.append(
                "<p class=MsoNormal><b>NON-SEQUENCED</b></p>"
            )
            parts.append(self._nonseq_table_html(
                protocol.treatment.non_sequenced_rows
            ))

        if not parts:
            return """     <tr>
      <td valign=top style='padding:.75pt'>
      <p class=MsoNormal>Nothing entered</p>
      </td>
     </tr>"""

        content = '\n      '.join(parts)
        return f"""     <tr>
      <td valign=top style='padding:.75pt'>
      {content}
      </td>
     </tr>"""

    def _chemo_table_html(self, rows: list[ChemoRow]) -> str:
        """Generate the CHEMOTHERAPY table with 13 columns."""
        headers_row1 = [
            'Stage/Day', 'Time', 'Drug/Diluent', 'Round dose to nearest',
            'Dose calculation/Volume', 'Rate', 'Route',
            'Special directions', 'Target interval', 'Margin',
            'Follows seq label', 'Line', 'Seq Label',
        ]

        lines = ['<table border=1 cellspacing=0 cellpadding=2 width="100%">']
        # Header row
        lines.append('<tr style="background:#E0E0E0">')
        for h in headers_row1:
            lines.append(
                f'<td><p class=MsoNormal><b>'
                f'<span style="font-size:7.0pt">'
                f'{html_mod.escape(h)}</span></b></p></td>'
            )
        lines.append('</tr>')

        # Data rows
        for row in rows:
            strike_open = '<s>' if row.row_type == RowType.DOSE_REDUCTION else ''
            strike_close = '</s>' if row.row_type == RowType.DOSE_REDUCTION else ''

            values = [
                row.stage_day, row.time, row.drug_diluent,
                row.round_dose_to, row.dose_calc_volume, row.rate,
                row.route, row.special_directions, row.target_interval,
                row.margin, row.follows_seq_label, row.line, row.seq_label,
            ]

            lines.append('<tr>')
            for val in values:
                esc = html_mod.escape(val) if val else '&nbsp;'
                lines.append(
                    f'<td><p class=MsoNormal><span style="font-size:8.0pt">'
                    f'{strike_open}{esc}{strike_close}</span></p></td>'
                )
            lines.append('</tr>')

        lines.append('</table>')
        return '\n'.join(lines)

    def _nonseq_table_html(self, rows: list[NonSequencedRow]) -> str:
        """Generate the NON-SEQUENCED table with 13 columns."""
        headers = [
            'Drug', 'Dose/Calculation', 'Mode', 'Freq',
            'Timing constraints', 'Route', 'Form',
            'Start with OOF', 'First dose day', 'First dose time',
            'Final dose day', 'Final dose time', 'Group',
        ]

        lines = ['<table border=1 cellspacing=0 cellpadding=2 width="100%">']
        # Header row
        lines.append('<tr style="background:#E0E0E0">')
        for h in headers:
            lines.append(
                f'<td><p class=MsoNormal><b>'
                f'<span style="font-size:7.0pt">'
                f'{html_mod.escape(h)}</span></b></p></td>'
            )
        lines.append('</tr>')

        # Data rows
        for row in rows:
            strike_open = '<s>' if row.row_type == RowType.DOSE_REDUCTION else ''
            strike_close = '</s>' if row.row_type == RowType.DOSE_REDUCTION else ''

            values = [
                row.drug, row.dose_calculation, row.mode, row.freq,
                row.timing_constraints, row.route, row.form,
                row.start_with_oof, row.first_dose_day, row.first_dose_time,
                row.final_dose_day, row.final_dose_time, row.group,
            ]

            lines.append('<tr>')
            for val in values:
                esc = html_mod.escape(val) if val else '&nbsp;'
                lines.append(
                    f'<td><p class=MsoNormal><span style="font-size:8.0pt">'
                    f'{strike_open}{esc}{strike_close}</span></p></td>'
                )
            lines.append('</tr>')

        lines.append('</table>')
        return '\n'.join(lines)
