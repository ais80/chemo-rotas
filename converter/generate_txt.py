"""Generate PICS EPMA TXT upload file from config.

Follows the formal specification in CLAUDE.md Sections 4-5.
All output uses Windows CRLF line endings.
"""

from .models import RotaConfig, BloodTest, DrugTemplate


def _line(level: int, text: str, plus: bool = False) -> str:
    """Format a single TXT line at the given indentation level.

    Args:
        level: Hierarchy level (0 = no indent, 1 = 2 spaces, etc.)
        text: The line content
        plus: Whether to prefix with '+' (data line vs navigation/structural)

    Returns:
        Formatted line WITHOUT line ending (caller adds CRLF)
    """
    if level == 0:
        if plus:
            raise ValueError("Level 0 lines cannot have + prefix")
        return text
    indent = 2 * level
    if plus:
        # '+' replaces first space: total width = 2*level chars
        return "+" + " " * (indent - 1) + text
    else:
        return " " * indent + text


def generate_txt(config: RotaConfig) -> str:
    """Generate the complete TXT file content.

    Returns string with CRLF line endings.
    """
    lines: list[str] = []

    def add(level: int, text: str, plus: bool = False):
        lines.append(_line(level, text, plus))

    def blank():
        lines.append("")

    # === 5.1 Header Comments ===
    add(0, f';d L^P025ZA("\\\\uhb\\wcl\\PICS\\Live Development\\#{config.ticket_number} {config.doc_code_upper} {config.drug_full_name}\\#{config.ticket_number}{config.drug_prefix}.txt")')
    blank()
    add(0, ";d BuildSet^P040EA,OverInd^P040EC,BuildR^P040EF")
    blank()
    blank()

    # === 5.2 Drug Messages — CUT Block ===
    add(0, "Drug Messages")
    for bt in config.blood_tests:
        code = config.message_code(bt)
        add(1, f"Code: {code}")
        add(2, "CUT")
    add(0, "END")
    blank()

    # === 5.3 Drug Messages — CREATE Block ===
    add(0, "Drug Messages")
    for bt in config.blood_tests:
        code = config.message_code(bt)
        add(1, f"Code: {code}")  # Navigation key — NO +
        add(2, "Message target: sysACTION", plus=True)
        add(2, f"Text line 1: {bt.message_text_line1}", plus=True)
        add(2, "Text line 2: {{{RESULT}}} at {{{RESTIME}}}.", plus=True)
        add(2, f"Text line 3: {bt.message_text_line3}", plus=True)
    add(0, "END")
    blank()

    # === 5.4 Drug Templates — CUT Block ===
    add(0, ";;UHB only ;;;")
    add(0, "Drug Template")
    for t in config.templates:
        tc = config.template_code(t)
        add(1, f"Template Code: {tc}")
        add(2, "CUT")
    add(0, "END")
    blank()

    # === 5.5 Drug Templates — CREATE Block ===
    add(0, "Drug Template")
    for t in config.templates:
        tc = config.template_code(t)
        desc = config.template_description(t)
        pmode = config.prescription_mode(t)
        add(1, f"Template Code: {tc}", plus=True)
        add(2, f"Description: {desc}", plus=True)
        add(2, f"Prescription mode: {pmode}", plus=True)
        add(2, f"Drug: {config.drug_prefix}", plus=True)
        add(2, f"Form: {t.form}", plus=True)
        add(2, "Main Form")  # Structural marker — NO +
        add(3, f"Route: {t.route}", plus=True)
        add(3, f"Dose: {t.dose}", plus=True)
        add(3, f"Units: {t.units}", plus=True)
        add(2, f"Frequency: {t.frequency}", plus=True)
    add(0, "END")
    blank()

    # === 5.6 Rota Stage — CUT Block ===
    add(0, "Rota Stage")
    add(1, f"Stage Code: {config.stage_code(1)}", plus=True)
    add(2, "CUT")
    add(0, "END")

    # === 5.7 Rota Stage — CREATE Block ===
    seq_list = config.seq_assignments()
    add(0, "Rota Stage")
    add(1, f"Stage Code: {config.stage_code(1)}")  # Navigation — NO +
    add(2, "Non-Sequenced Templates")  # Structural — NO +
    # List in DESCENDING Seq order
    for seq_num, t in sorted(seq_list, key=lambda x: x[0], reverse=True):
        tc = config.template_code(t)
        add(3, f"Seq: {seq_num}", plus=True)
        add(4, f"Template: {tc}", plus=True)
        if seq_num != 0:
            # Alternates get Excluded and Alternate to
            add(4, "Excluded by default: Y", plus=True)
            add(4, "Alternate to: 0", plus=True)
    add(2, f"In or Outpatient? (I/O): {config.inpatient_or_outpatient}", plus=True)
    add(0, "END")
    blank()

    # === 5.8 Rota — CUT Block ===
    add(0, "Rota")
    add(1, f"Rota Code: {config.drug_prefix}")
    add(2, "CUT")
    add(0, "END")

    # === 5.9 Rota — CREATE Block ===
    add(0, "Rota")
    add(1, f"Rota Code: {config.drug_prefix}", plus=True)
    add(2, f"Description: {config.drug_full_name}", plus=True)
    add(2, "Approval")  # Structural
    add(3, "Available: N", plus=True)
    add(3, "Default stage start time: 09:00", plus=True)
    add(3, f"Default cycles: {config.default_cycles}", plus=True)
    add(3, f"Cycle delay: {config.cycle_delay}", plus=True)
    add(3, f"Rota code: {config.document_code}", plus=True)
    add(2, "Stages")  # Structural
    add(3, "Seq: 0", plus=True)
    add(4, f"Description: {config.drug_full_name} stage 1", plus=True)
    add(4, f"Rota stage: {config.stage_code(1)}", plus=True)
    add(2, f"Info URL: http://pics-client-web/static/PICS/Specialties/Oncology/{config.doc_code_upper}.htm", plus=True)
    add(2, "Directorate overrides")  # Structural
    add(3, f"Directorate: {config.directorate}", plus=True)
    add(4, "Available: Y", plus=True)
    add(2, "Privilege required")  # Structural
    add(3, "Privilege to final authorise: CHDPRES!CHNURSE!PHARMFA", plus=True)
    add(2, "Authorise multiple stages?: Y", plus=True)
    add(2, "Configuration notes")  # Structural
    add(3, f"Notes: Ticket number #{config.ticket_number}", plus=True)
    add(0, "END")
    blank()

    # === 5.10 Rota — Activation Result Warnings ===
    # === 5.11 Rota — Result Warnings ===
    # These are in a THIRD Rota block
    add(0, "Rota")
    add(1, f"Rota Code: {config.drug_prefix}")
    add(2, "Stages")
    add(3, "Seq: 0")

    # --- Activation Result warnings (level 4) ---
    add(4, "Activation Result warnings")
    add(5, "Investigations")
    max_age = config.max_result_age
    for bt in config.blood_tests:
        add(6, f"Investigation Code: {bt.test_code}", plus=True)
        add(6, f"Test: {bt.test_code}", plus=True)
        add(7, f"Maximum result age: {max_age}", plus=True)
        add(7, "No result warnings")  # Structural
        add(8, "Message code: ROTANORES", plus=True)
        add(9, "Severity: sysPassword", plus=True)
    add(5, "Conditions")
    # Conditions listed in DESCENDING order
    n_tests = len(config.blood_tests)
    for i in range(n_tests - 1, -1, -1):
        bt = config.blood_tests[i]
        add(6, f"Condition No: {i}", plus=True)
        add(7, "Levels")  # Structural
        add(8, f"Investigation Code: {bt.test_code}", plus=True)
        add(8, f"Test: {bt.test_code}", plus=True)
        add(9, f"Value: {bt.threshold_value}", plus=True)
        add(9, f"Function: {bt.threshold_function}", plus=True)
        add(7, "Messages")  # Structural
        add(8, f"Message code: {config.message_code(bt)}", plus=True)
        add(9, "Severity: sysPassword", plus=True)

    # --- Result warnings (level 2, parallel to Stages) ---
    add(2, "Result warnings")
    add(3, "Investigations")
    add(4, "REORDER")
    for bt in config.blood_tests:
        add(4, f"Investigation Code: {bt.test_code}", plus=True)
        add(4, f"Test: {bt.test_code}", plus=True)
        add(5, f"Maximum result age: {max_age}", plus=True)
        add(5, "No result warnings")  # Structural
        add(6, "Message code: ROTANORES", plus=True)
        add(7, "Severity: sysPassword", plus=True)
    add(5, "Conditions")
    for i in range(n_tests - 1, -1, -1):
        bt = config.blood_tests[i]
        add(6, f"Condition No: {i}", plus=True)
        add(7, "Levels")  # Structural
        add(8, f"Investigation Code: {bt.test_code}", plus=True)
        add(8, f"Test: {bt.test_code}", plus=True)
        add(9, f"Value: {bt.threshold_value}", plus=True)
        add(9, f"Function: {bt.threshold_function}", plus=True)
        add(7, "Messages")  # Structural
        add(8, f"Message code: {config.message_code(bt)}", plus=True)
        add(9, "Severity: sysPassword", plus=True)
    add(0, "END")
    blank()

    # === 5.12 Rota Class ===
    add(0, "Rota Class")
    add(1, f"Class Code: {config.specialty_class}")
    add(2, "Items")
    add(3, f"Code: {config.drug_prefix}", plus=True)
    add(4, f"Description: {config.drug_full_name}", plus=True)
    add(4, "Rota/Rota group/Rota class: R", plus=True)
    add(4, f"Rota: {config.drug_prefix}", plus=True)
    add(0, "END")
    blank()

    # Join with CRLF line endings
    return "\r\n".join(lines)
