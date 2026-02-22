# Chemo Rota to EPMA Converter

## 1. Project Overview

Automates conversion of paper chemotherapy rotas (PDF) into structured formats for the
PICS EPMA (Electronic Prescribing and Medicines Administration) system.

- **Hospital**: Queen Elizabeth Hospital, Cancer Centre, Edgbaston, Birmingham B15 2TH
- **EPMA system**: PICS (MUMPS/M-based backend)
- **Users**: Pharmacists, oncology clinical staff

**Workflow**: `PDF (paper rota) → config.yaml (human review) → DOCX (template) + TXT (EPMA upload)`

---

## 2. Phases

### Phase 1 — Core Python Pipeline (current)
- PDF → structured config YAML (with human review/edit step)
- Config YAML → DOCX template (4-table format)
- Config YAML → TXT EPMA upload file (PICS import format)
- CLI tool: `python3 convert.py <pdf_path>`

### Phase 2 — Web Application
- Deploy via Google Antigravity as a web tool for non-technical users
- Drag-and-drop PDF upload, preview/edit extracted data, download DOCX + TXT

---

## 2.1. Setup Instructions

### Prerequisites
- Python 3.10+
- Tesseract OCR (for scanned PDFs)

### System packages (Ubuntu/Debian)
```bash
sudo apt install tesseract-ocr poppler-utils python3-venv
```

### Python environment
```bash
cd "/home/office/Documents/PICS/Chemo rotas"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Verify setup
```bash
.venv/bin/python3 convert.py
```
This should print the usage instructions.

---

## 2.2. Usage Guide

### Step 1: Extract config from PDF
Place the chemo rota PDF in the `input/` folder, then run:
```bash
.venv/bin/python3 convert.py extract "input/MyRota.pdf"
```
This creates `output/MyRota_config.yaml` with data extracted from the PDF.

### Step 2: Review and edit the config YAML
Open the generated YAML and:
1. **Fix any `CHANGE_ME` fields** — these require human input:
   - `drug_prefix`: Short uppercase code (e.g., `DARO`)
   - `ticket_number`: PICS change ticket number (e.g., `10350`)
   - `specialty_class`: Rota classification (e.g., `UROLOGY`)
2. **Verify extracted data** — check doses, blood test thresholds, indication text
3. **Clean up OCR artifacts** — especially in `rota_info_paragraphs` (OCR from scanned PDFs can be noisy)

### Step 3: Generate outputs
```bash
.venv/bin/python3 convert.py generate "output/MyRota_config.yaml"
```
This creates:
- `output/#<ticket><PREFIX>.txt` — the PICS EPMA import file
- `output/<DocCode> <DrugName>.docx` — the 4-table template

### One-shot mode (extract + generate)
For PDFs with clean digital text (not scanned), you can skip the review step:
```bash
.venv/bin/python3 convert.py auto "input/MyRota.pdf"
```
**Note**: You will still need to edit the YAML for `CHANGE_ME` fields before the output is usable. The `auto` command generates outputs immediately but warns if required fields are missing.

### Example (Darolutamide)
```bash
# Extract
.venv/bin/python3 convert.py extract "Rota example/Drota930 Darolutamide.pdf"

# Edit output/Drota930 Darolutamide_config.yaml:
#   drug_prefix: DARO
#   ticket_number: 10350
#   specialty_class: UROLOGY

# Generate
.venv/bin/python3 convert.py generate "output/Drota930 Darolutamide_config.yaml"

# Outputs: output/#10350DARO.txt and output/Drota930 Darolutamide.docx
```

---

## 3. Directory Structure

```
Chemo rotas/
  CLAUDE.md              ← this specification
  convert.py             ← Phase 1 CLI entry point
  converter/             ← Python package
    __init__.py
    models.py            ← data classes
    extract_pdf.py       ← PDF → config YAML
    generate_docx.py     ← config → DOCX
    generate_txt.py      ← config → TXT
  Rota example/          ← reference/example files
    Drota930 Darolutamide.pdf
    Drota930 Darolutamide.docx
    #10350Daro- my test version.txt
  input/                 ← user drops new PDFs here
  output/                ← generated DOCX + TXT files
  .venv/                 ← Python virtual environment
  requirements.txt       ← pip dependencies
```

---

## 4. FORMAL SPECIFICATION: TXT File Syntax (PICS Import Format)

### 4.1. File Encoding
- **Line endings**: Windows CRLF (`\r\n`) — this is MANDATORY for PICS import
- **Character encoding**: ASCII (7-bit safe, no Unicode)
- **No BOM** (byte order mark)

### 4.2. Line Types

Every line in the TXT file is one of these types:

| Type | Prefix | Purpose | Example |
|---|---|---|---|
| **Section header** | None (col 0) | Opens a new section block | `Drug Messages` |
| **Navigation key** | Spaces only | Identifies existing record to modify | `  Code: DAROneuts` |
| **Structural marker** | Spaces only | Sub-section label within a block | `    Main Form` |
| **Data line** | `+` then spaces | Data to be written/created | `+   Message target: sysACTION` |
| **Delete marker** | Spaces then `CUT` | Deletes the navigated-to record | `    CUT` |
| **Block terminator** | `END` at col 0 | Closes the current section block | `END` |
| **Comment** | `;` at col 0 | Ignored by parser (`;` single, `;;` double) | `;d L^P025ZA(...)` |
| **Blank line** | Empty | Visual separator, ignored | |

### 4.3. Indentation Rules

Indentation uses **spaces only** (never tabs). Each hierarchy level = **2 spaces**.

| Level | Without `+` | With `+` prefix | Notes |
|---|---|---|---|
| 0 | `(no indent)` | N/A | Section headers, END |
| 1 | `··` (2 spaces) | `+·` (+ then 1 space) | Top-level fields |
| 2 | `····` (4 spaces) | `+···` (+ then 3 spaces) | Nested fields |
| 3 | `······` (6 spaces) | `+·····` (+ then 5 spaces) | Deeper nesting |
| N | `2N spaces` | `+` then `(2N-1) spaces` | General rule |

**Rule**: The `+` character replaces the first space of the indentation. The total
character width (indent + prefix) is always `2N` characters for level N.

### 4.4. Section Block Pattern

Every data entity follows the **CUT-then-CREATE** pattern:

```
SectionType                    ← section header (level 0)
  Key: VALUE1                  ← navigation key (level 1, NO +)
    CUT                        ← delete existing (level 2, NO +)
  Key: VALUE2                  ← next record
    CUT
END                            ← close CUT block

SectionType                    ← same section header again
  Key: VALUE1                  ← navigate (NO + on navigation keys)
+   Field1: data               ← create data (+ prefix)
+   Field2: data
  Key: VALUE2                  ← next record (NO +)
+   Field1: data
END                            ← close CREATE block
```

**Critical rule**: Navigation key lines NEVER have a `+` prefix. Only data-value lines
get `+`. The navigation key tells the system WHICH record to operate on; the `+` lines
tell it WHAT to write.

### 4.5. Structural Markers

Some lines are structural sub-section markers (no `+`, just indentation):

```
    Main Form                  ← level 2, structural (within Drug Template)
    Approval                   ← level 2, structural (within Rota)
    Stages                     ← level 2, structural
    Non-Sequenced Templates    ← level 2, structural (within Rota Stage)
    Directorate overrides      ← level 2, structural
    Privilege required         ← level 2, structural
    Configuration notes        ← level 2, structural
      Activation Result warnings  ← level 4, structural (within Rota > Stages > Seq)
        Investigations         ← level 5, structural
        Conditions             ← level 5, structural
          Levels               ← level 7, structural
          Messages             ← level 7, structural
          No result warnings   ← varies, structural
    Result warnings            ← level 2, structural (within Rota, parallel to Stages)
      Investigations           ← level 3, structural
        REORDER                ← level 4, keyword
```

---

## 5. FORMAL SPECIFICATION: TXT Sections (in order)

### 5.1. Header Comments (optional, lines 1-9)

```
;d L^P025ZA("\\uhb\wcl\PICS\Live Development\#{TICKET} {DOC_CODE} {DRUG_FULL}\#{TICKET}{PREFIX}.txt")

;d BuildSet^P040EA,OverInd^P040EC,BuildR^P040EF
```

These are MUMPS routine calls for loading the file. Fields:
- `{TICKET}`: Ticket number (e.g., `#10350`)
- `{DOC_CODE}`: Document code from PDF (e.g., `DROTA930`)
- `{DRUG_FULL}`: Full drug name (e.g., `Darolutamide`)
- `{PREFIX}`: Drug prefix code (e.g., `DARO`)

### 5.2. Drug Messages — CUT Block

Deletes any existing messages before recreation.
One entry per blood test that has a threshold condition.

```
Drug Messages
  Code: {PREFIX}{test_lower}
    CUT
  Code: {PREFIX}{test_lower}
    CUT
  ...
END
```

**Ordering**: List messages in the order defined by the `blood_tests` list in config
(see Section 7 for canonical ordering).

### 5.3. Drug Messages — CREATE Block

Creates alert messages triggered by blood test results.

```
Drug Messages
  Code: {PREFIX}{test_lower}
+   Message target: sysACTION
+   Text line 1: {threshold_text}
+   Text line 2: {{{RESULT}}} at {{{RESTIME}}}.
+   Text line 3: {action_text}
  Code: {PREFIX}{test_lower}
+   Message target: sysACTION
+   Text line 1: {threshold_text}
+   Text line 2: {{{RESULT}}} at {{{RESTIME}}}.
+   Text line 3: {action_text}
  ...
END
```

**Field rules**:
- `Code:` line has NO `+` prefix (it is a navigation key)
- `Message target: sysACTION` — ALWAYS present for every message
- `Text line 2:` is ALWAYS `{{{RESULT}}} at {{{RESTIME}}}.` (literal triple braces, these are PICS template variables)
- `{threshold_text}`: Human-readable threshold (e.g., `Neuts < 1.0 x 10 9/L`)
- `{action_text}`: Clinical action (e.g., `Contact prescriber.`)

### 5.4. Drug Templates — CUT Block

```
;;UHB only ;;;
Drug Template
  Template Code: {template_code_1}
    CUT
  Template Code: {template_code_2}
    CUT
  ...
END
```

### 5.5. Drug Templates — CREATE Block

One template per row in DOCX Table 2 (i.e., per dose/mode combination).

```
Drug Template
+ Template Code: {template_code}
+   Description: {drug_full} {dose}{units} {freq} {mode_label}
+   Prescription mode: {prescription_mode}
+   Drug: {PREFIX}
+   Form: {form}
    Main Form
+     Route: {route}
+     Dose: {dose_numeric}
+     Units: {units}
+   Frequency: {freq}
+ Template Code: {next_template_code}
+   Description: {drug_full} {dose}{units} {freq} {mode_label}
  ...
END
```

**Field derivation rules**:

| Field | Rule | Example |
|---|---|---|
| `template_code` | `{PREFIX}_{DrugTitleCase}{DoseNumeric}{Freq}_{ModeLabel}` | `DARO_Daro600BD_TTO` |
| `DrugTitleCase` | First letter uppercase, rest lowercase, of the short drug name | `Daro` |
| `DoseNumeric` | Numeric dose value only (no units) | `600` |
| `ModeLabel` | From DOCX Table 2 Mode column: `TTO` or `REG` | `TTO` |
| `Description` | `{DrugFullName} {dose}{units} {freq} {ModeLabel}` | `Darolutamide 600mg BD TTO` |
| `prescription_mode` | `TTO` → `REG_T`, `REG` → `REG` | `REG_T` |
| `Drug` | Always the PREFIX code | `DARO` |
| `Form` | From DOCX Table 2 or PDF (e.g., `TAB`, `CAP`, `INJ`) | `TAB` |
| `Route` | From DOCX Table 2 or PDF (e.g., `ORAL`, `IV`, `SC`) | `ORAL` |
| `dose_numeric` | Integer, no units | `600` |
| `units` | Lowercase unit string | `mg` |
| `freq` | Frequency code | `BD` |

**Template ordering**: Templates are listed in the order they appear in DOCX Table 2
(primary first, then alternates, then inpatient).

**IMPORTANT**: `+ Template Code:` lines DO have a `+` prefix (this is the CREATE pattern
for templates — the Template Code IS the data being created, unlike Drug Messages where
Code is a navigation key for an existing record).

### 5.6. Rota Stage — CUT Block

```
Rota Stage
+ Stage Code: {PREFIX}_Stage{n}
    CUT
END
```

Note: `+ Stage Code:` has `+` prefix here (creating the stage, then immediately deleting
to clear it for recreation).

### 5.7. Rota Stage — CREATE Block

```
Rota Stage
  Stage Code: {PREFIX}_Stage{n}
    Non-Sequenced Templates
+     Seq: {highest_seq}
+       Template: {template_code}
+       Excluded by default: Y
+       Alternate to: 0
+     Seq: {next_seq}
+       Template: {template_code}
+       Excluded by default: Y
+       Alternate to: 0
+     Seq: 0
+       Template: {primary_template_code}
+   In or Outpatient? (I/O): {I_or_O}
END
```

**Sequencing rules**:

| DOCX Table 2 Group | Seq number | Excluded by default | Alternate to | Notes |
|---|---|---|---|---|
| `{n}A` (has letter suffix) | `0` | *(field omitted)* | *(field omitted)* | Primary/default template |
| `{n}` (no letter suffix) | `1, 2, 3...` | `Y` | `0` | Alternates |

- **Seq 0** is ALWAYS the primary/default template (the one with the letter suffix in Group)
- Seq 0 does NOT include `Excluded by default` or `Alternate to` fields
- Alternate templates are assigned Seq numbers 1, 2, 3... in the order they appear in DOCX Table 2
- **Listing order**: Sequences are listed in DESCENDING order (highest Seq first, Seq 0 last)
- `In or Outpatient?`: `O` for outpatient (oral/TTO rotas), `I` for inpatient (IV rotas)

### 5.8. Rota — CUT Block

```
Rota
  Rota Code: {PREFIX}
    CUT
END
```

### 5.9. Rota — CREATE Block

```
Rota
+ Rota Code: {PREFIX}
+   Description: {drug_full_name}
    Approval
+     Available: N
+     Default stage start time: 09:00
+     Default cycles: {default_cycles}
+     Cycle delay: {cycle_delay}
+     Rota code: {document_code}
    Stages
+     Seq: 0
+       Description: {drug_full_name} stage 1
+       Rota stage: {PREFIX}_Stage1
+   Info URL: http://pics-client-web/static/PICS/Specialties/Oncology/{DOC_CODE_UPPER}.htm
    Directorate overrides
+     Directorate: {directorate}
+       Available: Y
    Privilege required
+     Privilege to final authorise: CHDPRES!CHNURSE!PHARMFA
+   Authorise multiple stages?: Y
    Configuration notes
+     Notes: Ticket number #{ticket_number}
END
```

**Field derivation rules**:

| Field | Rule | Example |
|---|---|---|
| `Rota Code` | Same as PREFIX | `DARO` |
| `Description` | Full drug name, title case | `Darolutamide` |
| `Available` | Always `N` globally | `N` |
| `Default stage start time` | Always `09:00` | `09:00` |
| `default_cycles` | **HUMAN INPUT** — number of treatment cycles | `12` |
| `cycle_delay` | From PDF: cycle length in weeks, format `{n}w` | `4w` |
| `document_code` | From PDF header, mixed case as printed | `Drota930` |
| `DOC_CODE_UPPER` | Document code, UPPERCASE | `DROTA930` |
| `Stage description` | `{drug_full_name} stage {n}` | `Darolutamide stage 1` |
| `directorate` | **HUMAN INPUT** — 3-letter directorate code | `ONC` |
| `Privilege to final authorise` | Always `CHDPRES!CHNURSE!PHARMFA` | *(fixed)* |
| `ticket_number` | **HUMAN INPUT** — PICS ticket number (digits only) | `10350` |

### 5.10. Rota — Activation Result Warnings

This is a THIRD Rota block (separate from CUT and CREATE), nested under Stages > Seq.

```
Rota
  Rota Code: {PREFIX}
    Stages
      Seq: 0
        Activation Result warnings
          Investigations
+           Investigation Code: {TEST_CODE}
+           Test: {TEST_CODE}
+             Maximum result age: {max_age}
              No result warnings
+               Message code: ROTANORES
+                 Severity: sysPassword
+           Investigation Code: {TEST_CODE}
+           Test: {TEST_CODE}
            ...
          Conditions
+           Condition No: {highest_n}
              Levels
+               Investigation Code: {TEST_CODE}
+               Test: {TEST_CODE}
+                 Value: {threshold_value}
+                 Function: {GT_or_LT}
              Messages
+               Message code: {PREFIX}{test_lower}
+                 Severity: sysPassword
+           Condition No: {next_n}
            ...
```

**Investigation ordering**: Investigations are listed in the **canonical blood test order**
(see Section 7).

**Condition numbering**: Conditions are numbered 0 to N-1, assigned in the same order as
the canonical blood test list. Condition 0 = first test in the list, Condition 1 = second, etc.

**Condition listing order**: Conditions are listed in DESCENDING order (highest number first,
0 last).

**`Function` field**:
- `LT` = the alert fires when the result is LESS THAN the threshold (e.g., Neuts < 1.0)
- `GT` = the alert fires when the result is GREATER THAN the threshold (e.g., Bilirubin > 31)

### 5.11. Rota — Result Warnings

Follows immediately after the Activation Result warnings block (within the same `Rota` /
`END` pair). This section is at **level 2** (parallel to Stages, NOT nested inside
Stages > Seq).

```
    Result warnings
      Investigations
        REORDER
+       Investigation Code: {TEST_CODE}
+       Test: {TEST_CODE}
+         Maximum result age: {max_age}
          No result warnings
+           Message code: ROTANORES
+             Severity: sysPassword
        ...
          Conditions
+           Condition No: {highest_n}
              Levels
+               Investigation Code: {TEST_CODE}
+               Test: {TEST_CODE}
+                 Value: {threshold_value}
+                 Function: {GT_or_LT}
              Messages
+               Message code: {PREFIX}{test_lower}
+                 Severity: sysPassword
            ...
END
```

**Key differences from Activation Result warnings**:
- Nesting starts at level 2 (`    Result warnings`) not level 4
- Investigation/Condition indentation is correspondingly 2 levels shallower
- Includes `REORDER` keyword at level 4 (after `Investigations` at level 3)
- Investigations and Conditions use the same data and ordering as Activation block
- The `END` that closes this also closes the entire Rota block

### 5.12. Rota Class

```
Rota Class
  Class Code: {specialty_class}
    Items
+     Code: {PREFIX}
+       Description: {drug_full_name}
+       Rota/Rota group/Rota class: R
+       Rota: {PREFIX}
END
```

- `specialty_class`: **HUMAN INPUT** — e.g., `UROLOGY`, `ONCOLOGY`, `HAEMATOLOGY`
- `Rota/Rota group/Rota class`: Always `R` (this is a single Rota, not a group or class)

---

## 6. FORMAL SPECIFICATION: DOCX Template Structure

### 6.1. Document Layout

The DOCX contains **4 tables** followed by **free text sections**. Sections are labelled
with paragraph headings.

### 6.2. Table 0 — Chemotherapy Fluids (12 columns, variable rows)

For IV chemo drugs administered in the day unit. **Empty for oral-only rotas.**

| Col | Header Row 0 | Header Row 1 | Data type |
|---|---|---|---|
| 0 | DUE | Stage day | Integer (day within treatment stage) |
| 1 | DUE | Time | HH:MM or blank |
| 2 | DRUG/DILUENT | DRUG/DILUENT | Drug name string |
| 3 | DOSE CALCULATION/VOLUME | DOSE CALCULATION/VOLUME | Dose + units |
| 4 | RATE | RATE | Infusion rate |
| 5 | ROUTE | ROUTE | e.g., IV |
| 6 | Special directions/PiP | Special directions/PiP | Free text |
| 7 | Critical timings | Target interval | Duration string |
| 8 | Critical timings | Margin | Duration string |
| 9 | Critical timings | Follows seq. label | Ref to another seq |
| 10 | Line | Line | Line number |
| 11 | Seq. label | Seq. label | Sequence identifier |

### 6.3. Table 1 — Non-Sequenced Items (12 columns, variable rows)

Same structure as Table 0 but column 3 header is `UNIT/VOLUME` instead of
`DOSE CALCULATION/VOLUME`, and column 6 is `Special directions` (no PiP mention).
**Empty for simple oral rotas.**

### 6.4. Table 2 — Drug Templates (13 columns)

The primary table for oral/non-sequenced drug prescriptions.

| Col | Header Row 0 | Header Row 1 | Data type |
|---|---|---|---|
| 0 | Drug | Drug | UPPERCASE drug name |
| 1 | Dose/Calculation | Dose/Calculation | e.g., `600mg` |
| 2 | Mode | Mode | `TTO` or `REG` |
| 3 | Freq | Freq | Frequency code (e.g., `BD`, `OD`, `TDS`) |
| 4 | Any timing constraints | Any timing constraints | Free text (e.g., `Take with food`) |
| 5 | Route | Route | e.g., `ORAL` |
| 6 | Form | Form | e.g., `TAB`, `CAP` |
| 7 | Start with OOF? | Start with OOF? | `-` or `Y` |
| 8 | First dose | Stage day | Integer |
| 9 | First dose | Time | HH:MM or blank |
| 10 | Final dose | Stage day | `U` (until stopped) or integer |
| 11 | Final dose | Time | HH:MM or blank |
| 12 | Group | Group | Group code (see Section 5.7) |

**Row ordering convention**:
1. Primary dose (TTO mode) — Group has letter suffix (e.g., `1A`)
2. Dose reduction (TTO mode) — Group without letter (e.g., `1`)
3. Inpatient version (REG mode) — Group without letter (e.g., `1`)

### 6.5. Table 3 — Proceed Rules / Blood Test Warnings (5 columns)

| Col | Header | Data type |
|---|---|---|
| 0 | Drug | Drug name (title case) |
| 1 | Neutrophils | Threshold + action text |
| 2 | Platelets | Threshold + action text |
| 3 | Renal (estimated by Cockroft Gault) | Threshold + action text |
| 4 | Hepatic | Threshold + action text (may contain MULTIPLE tests, e.g., Bilirubin AND ALT) |

**Parsing the Hepatic column**: This column may contain thresholds for multiple tests
(e.g., `Bilirubin >31 or ALT >165 ...`). These must be split into separate entries
for the TXT file.

### 6.6. Free Text Sections

After the tables, paragraphs appear with these headings:

| Heading | Content | Maps to TXT |
|---|---|---|
| `Warnings` | Validity periods for blood tests | `Maximum result age` fields |
| `Rota Information` | Cycle details, counselling notes, drug interactions | Info URL content |

**Parsing "Validity of FBC X days"**: Extract integer X, convert to weeks: `{X/7}w`.
If X = 7, result = `1w`. This value applies to ALL investigation codes.

---

## 7. Canonical Blood Test Ordering

All blood test references in the TXT file follow this canonical order. This determines:
- Order of Drug Message CUT entries
- Order of Drug Message CREATE entries
- Order of Investigation entries in Activation/Result warnings
- Condition numbering (0 = first in list, 1 = second, etc.)

### Standard order (derived from example):

| Position | Test Code | PICS Investigation Code | Drug Message suffix | Typical threshold direction |
|---|---|---|---|---|
| 0 | PLATS | PLATS | `plats` | LT (less than) |
| 1 | NEUTS | NEUTS | `neuts` | LT |
| 2 | GFR | GFR | `gfr` | LT |
| 3 | BILI | BILI | `bili` | GT (greater than) |
| 4 | ALT | ALT | `alt` | GT |

**Ordering rule**: Haematology tests first (PLATS, NEUTS), then renal (GFR), then
hepatic (BILI, ALT). Within each group, order matches the Investigation listing in the
reference TXT file.

**NOTE**: The Drug Messages section in the example file lists messages in a slightly
different order (NEUTS, PLATS, GFR, BILI, ALT). For consistency, the converter should
use the canonical order above for ALL sections. This is a minor normalisation from the
hand-coded example.

**Condition numbering**: Condition No `0` = PLATS (position 0), Condition No `1` = NEUTS
(position 1), etc. Conditions are LISTED in descending order (highest number first).

### Adding/removing tests

Not all rotas will use all 5 tests. The config YAML defines which tests apply. Only
configured tests appear in the output. Condition numbers are assigned sequentially
starting from 0 based on the tests present, following the canonical order above (skip
any tests not in use, do not leave gaps).

---

## 8. Fields Requiring Human Input

These fields CANNOT be reliably extracted from the PDF and must be provided by the user
in the config YAML:

| Field | Description | Example | Where used |
|---|---|---|---|
| `drug_prefix` | Short uppercase code for the drug (typically 3-5 chars) | `DARO` | All sections |
| `ticket_number` | PICS change ticket number (digits only) | `10350` | Header comments, Rota config |
| `default_cycles` | Number of treatment cycles | `12` | Rota config |
| `directorate` | 3-letter directorate code | `ONC` | Rota directorate overrides |
| `specialty_class` | Rota classification for PICS | `UROLOGY` | Rota Class section |
| `cycle_delay` | Cycle length (e.g., `4w` for 4 weeks) | `4w` | Rota config |

The converter will attempt to extract these from the PDF where possible and prompt
the user to confirm or provide them.

---

## 9. Naming Convention Algorithms

All naming is deterministic given the input fields. Every algorithm below must produce
identical output for identical input.

### 9.1. Drug Prefix (`PREFIX`)
- **Input**: User-provided (cannot be algorithmically derived)
- **Format**: 3-5 uppercase letters
- **Example**: `DAROLUTAMIDE` → user provides `DARO`

### 9.2. Message Code
- **Algorithm**: `{PREFIX}` + `{test_code_lowercase}`
- **test_code_lowercase**: The PICS test code in all lowercase
- **Examples**: `DARO` + `neuts` → `DAROneuts`, `DARO` + `plats` → `DAROplats`

### 9.3. Template Code
- **Algorithm**: `{PREFIX}_{DrugShortTitleCase}{DoseInteger}{FreqCode}_{ModeLabel}`
- **DrugShortTitleCase**: Short drug name with first letter uppercase, rest lowercase.
  Derived from the drug_prefix: first letter uppercase + remaining letters lowercase.
  E.g., PREFIX=`DARO` → `Daro`
- **DoseInteger**: Numeric dose with no units, no decimals. E.g., `600`
- **FreqCode**: Frequency code exactly as in DOCX. E.g., `BD`, `OD`
- **ModeLabel**: `TTO` if DOCX mode is TTO, `REG` if DOCX mode is REG
- **Example**: `DARO_Daro600BD_TTO`

### 9.4. Template Description
- **Algorithm**: `{DrugFullName} {dose}{units} {freq} {ModeLabel}`
- **DrugFullName**: Full drug name, title case. E.g., `Darolutamide`
- **Example**: `Darolutamide 600mg BD TTO`

### 9.5. Stage Code
- **Algorithm**: `{PREFIX}_Stage{n}`
- **n**: Stage number, starting from 1
- **Example**: `DARO_Stage1`

### 9.6. Rota Code
- **Algorithm**: Same as `{PREFIX}`
- **Example**: `DARO`

### 9.7. Info URL
- **Algorithm**: `http://pics-client-web/static/PICS/Specialties/Oncology/{DOC_CODE_UPPER}.htm`
- **DOC_CODE_UPPER**: Document code from PDF, converted to UPPERCASE
- **Example**: Document code `Drota930` → `DROTA930` → URL `.../DROTA930.htm`

---

## 10. Config YAML Schema

The intermediate human-reviewable format. Generated from PDF extraction, edited by user,
then consumed by DOCX and TXT generators.

```yaml
# === EXTRACTED FROM PDF (review and correct) ===
document_code: "Drota930"          # From PDF header
drug_full_name: "Darolutamide"     # Full drug name
indication: "non-metastatic castration resistant prostate cancer (nmCRPC)"
reference: "SmPC for Darolutamide"

# === HUMAN INPUT REQUIRED ===
drug_prefix: "DARO"                # Short code — YOU MUST PROVIDE THIS
ticket_number: "10350"             # PICS ticket — YOU MUST PROVIDE THIS
default_cycles: 12                 # Number of cycles — YOU MUST PROVIDE THIS
cycle_delay: "4w"                  # Cycle length — verify against PDF
directorate: "ONC"                 # Directorate code — YOU MUST PROVIDE THIS
specialty_class: "UROLOGY"         # Rota class — YOU MUST PROVIDE THIS
inpatient_or_outpatient: "O"       # O=outpatient, I=inpatient

# === DRUG TEMPLATES (from PDF prescription section) ===
templates:
  - drug_name_upper: "DAROLUTAMIDE"
    dose: 600
    units: "mg"
    mode: "TTO"                    # TTO=outpatient, REG=inpatient
    frequency: "BD"
    route: "ORAL"
    form: "TAB"
    timing_constraints: "Take with food"
    first_dose_day: 1
    final_dose_day: "U"            # U=until stopped
    group: "1A"                    # Letter suffix = primary
  - drug_name_upper: "DAROLUTAMIDE"
    dose: 300
    units: "mg"
    mode: "TTO"
    frequency: "BD"
    route: "ORAL"
    form: "TAB"
    timing_constraints: "Dose reduction  Take with food"
    first_dose_day: 1
    final_dose_day: "U"
    group: "1"                     # No letter = alternate
  - drug_name_upper: "DAROLUTAMIDE"
    dose: 600
    units: "mg"
    mode: "REG"
    frequency: "BD"
    route: "ORAL"
    form: "TAB"
    timing_constraints: "Inpatient prescribing Take with food"
    first_dose_day: 1
    final_dose_day: "U"
    group: "1"

# === BLOOD TESTS (from PDF Blood Tests section) ===
# Order here defines canonical ordering for all TXT sections
blood_test_validity_days: 7        # From "Validity of FBC X days"

blood_tests:
  - test_code: "PLATS"
    threshold_value: 100
    threshold_function: "LT"       # LT=less than, GT=greater than
    message_text_line1: "Plts < 100 x 10^9/L"
    message_text_line3: "Contact prescriber."
  - test_code: "NEUTS"
    threshold_value: 1
    threshold_function: "LT"
    message_text_line1: "Neuts < 1.0 x 10 9/L"
    message_text_line3: "Contact prescriber. Reduced neutrophils common with longer treatment"
  - test_code: "GFR"
    threshold_value: 30
    threshold_function: "LT"
    message_text_line1: "GFR < 30mL/min"
    message_text_line3: "Contact prescriber, consider 300mg BD starting dose."
  - test_code: "BILI"
    threshold_value: 31
    threshold_function: "GT"
    message_text_line1: "Bilirubin > 31 umol/L"
    message_text_line3: "Contact prescriber. Consider 300mg BD starting dose in hepatic impairment. Darolutamide is also known to affect liver function."
  - test_code: "ALT"
    threshold_value: 165
    threshold_function: "GT"
    message_text_line1: "ALT  > 165 U/L"
    message_text_line3: "Contact prescriber. Consider 300mg BD starting dose in hepatic impairment. Darolutamide is also known to affect liver function."

# === ROTA INFORMATION (from PDF Further Information section) ===
rota_info_paragraphs:
  - "Given continuously. Supplied as a 28 day cycle for prostate cancer as per national funding considerations."
  - "Patient should be referred to pharmacist for counselling prior to first cycle."
  - "Darolutamide is metabolised by CYP3A4 and therefore the concomitant use of strong CYP3A4/ P-gp inducers (phenytoin, rifampicin, St John's Wort, carbamazepine, phenobarbital) should be avoided. Caution with CYP3A4 inhibitors (ritonavir, ketoconazole, itraconazole, erythromycin, clarithromycin, grapefruit juice)."
  - "Darolutamide is a BCRP, OATP1B1/1B3 inhibitor. Avoid use of rosuvastatin with Darolutamide. Other substrates such as methotrexate, sulfasalazine, fluvastatin, atorvastatin, pitavastatin should be monitored closely for increased toxicity."
  - "Darolutamide is a mild CYP3A4 inducer. Increased monitoring is needed for CYP3A4 substrates with narrow therapeutic window e.g. warfarin."
  - "Darolutamide tablets may prolong the QT interval and should therefore be avoided in patients taking other drugs known to have the same effect."

# === WARNINGS (from PDF Blood Tests frequency section) ===
warnings_paragraphs:
  - "Validity of FBC 7   days"
  - "Validity of U&E, LFTs, 7 days"
  - "Blood results needed at baseline, then monitor monthly. Frequency may be reduced to 3 monthly in stable patients"
```

---

## 11. Known Issues in the Example Test File

The file `#10350Daro- my test version.txt` is a hand-coded test version with several
inconsistencies. The converter should produce the CORRECTED canonical output, NOT
replicate these errors.

| Line(s) | Issue | Correction |
|---|---|---|
| 37 (`Code: DAROgfr`) | Missing `Message target: sysACTION` | ADD `+   Message target: sysACTION` for all messages |
| 40 (`+ Code: DARObili`) | Has `+` prefix on Code navigation line | REMOVE `+` — Code lines are navigation keys, never `+` |
| 46 (`+ Code: DAROalt`) | Same as above | REMOVE `+` |
| 73 (`DARO_Daro300BD_TTO`) | Missing `Description:` line | ADD `+   Description: Darolutamide 300mg BD TTO` |
| 241 (`;;;  Test: NEUTS`) | Commented-out incorrect test (should be GFR) | REMOVE comment line entirely |
| 248 (`;;  Test: GFR`) | Commented-out incorrect test (should be BILI) | REMOVE comment line entirely |
| Various | Trailing tab characters (`\t`) at end of some lines | REMOVE all trailing whitespace |
| Drug Messages order | NEUTS listed before PLATS | Use canonical order: PLATS, NEUTS, GFR, BILI, ALT |

---

## 12. Transformation Rules: PDF → Config YAML

### 12.1. Document Code
- **Location in PDF**: Top-left, labelled "Document Code:"
- **Extract**: The code string (e.g., `Drota930`)
- **YAML field**: `document_code`

### 12.2. Drug Name and Indication
- **Location in PDF**: Large bold text area, format: `{Drug} for {indication}`
- **Extract**: Split on ` for ` — left part = drug name, right part = indication
- **YAML fields**: `drug_full_name`, `indication`

### 12.3. Dose and Frequency
- **Location in PDF**: "DOSE" field and bullet points under "Please supply"
- **Extract**: Primary dose from "Starting dose usually {dose} {freq}" pattern
- Dose reductions from "Dose reduced to {dose} {freq}" pattern
- **YAML fields**: `templates[].dose`, `templates[].frequency`

### 12.4. Blood Test Thresholds
- **Location in PDF**: "BLOOD TESTS" section at bottom right
- **Patterns to match**:
  - `Neuts < {value} x 10 9/L` → test_code: NEUTS, function: LT
  - `plts < {value}` → test_code: PLATS, function: LT
  - `GFR < {value}mL/min` → test_code: GFR, function: LT
  - `Bilirubin > {value}` → test_code: BILI, function: GT
  - `ALT > {value}` → test_code: ALT, function: GT
- **YAML fields**: `blood_tests[]`

### 12.5. Blood Test Monitoring Frequency
- **Location in PDF**: "BLOOD TESTS" section, "Baseline results needed..." text
- **Pattern**: Look for "Validity" or day count
- **YAML field**: `blood_test_validity_days`

### 12.6. Route and Form
- **Location in PDF**: Inferred from drug type
  - "tablets" → form: TAB, route: ORAL
  - "capsules" → form: CAP, route: ORAL
  - "injection" → form: INJ, route: IV/SC/IM
- **YAML fields**: `templates[].form`, `templates[].route`

---

## 13. Transformation Rules: Config YAML → TXT

These are the deterministic rules the TXT generator must follow. Given identical YAML
input, the output must be byte-identical (modulo CRLF line endings).

### 13.1. Maximum Result Age
- **Input**: `blood_test_validity_days` (integer, days)
- **Output**: `{days / 7}w` — integer division, always expressed in weeks
- **Example**: `7` → `1w`, `14` → `2w`

### 13.2. Drug Message Code
- **Input**: `drug_prefix`, `blood_tests[].test_code`
- **Output**: `{drug_prefix}{test_code.lower()}`
- **Example**: `DARO` + `PLATS` → `DAROplats`

### 13.3. Template Code
- **Input**: `drug_prefix`, `templates[].dose`, `templates[].frequency`, `templates[].mode`
- **DrugTitleCase**: `drug_prefix[0].upper() + drug_prefix[1:].lower()`
- **Output**: `{drug_prefix}_{DrugTitleCase}{dose}{frequency}_{mode}`
- **Example**: `DARO_Daro600BD_TTO`

### 13.4. Prescription Mode
- **Input**: `templates[].mode`
- **Mapping**: `TTO` → `REG_T`, `REG` → `REG`

### 13.5. Seq Assignment
- **Input**: `templates[].group`
- **Rule**: Template with group ending in letter (e.g., `1A`) gets Seq 0.
  Others get Seq 1, 2, 3... in the order they appear in the YAML.
- **Primary detection**: `group[-1].isalpha()` → this is the primary (Seq 0)

### 13.6. Condition Number Assignment
- **Input**: `blood_tests` list (ordered)
- **Rule**: Condition No = index position in the list (0-based)
- **Listing order**: Descending (highest condition number first)

---

## 14. Validation Checklist

After generating TXT output, verify:

- [ ] All lines end with CRLF (`\r\n`)
- [ ] No trailing tabs or spaces on any line
- [ ] Every section has matching `END`
- [ ] CUT blocks appear before CREATE blocks for same section type
- [ ] All `Code:` lines in Drug Messages have NO `+` prefix
- [ ] All `+ Template Code:` lines in Drug Template DO have `+` prefix
- [ ] Every Drug Message has `Message target: sysACTION`
- [ ] Every Drug Message has `Text line 2: {{{RESULT}}} at {{{RESTIME}}}.`
- [ ] Template Codes follow naming convention exactly
- [ ] Seq 0 template has NO `Excluded by default` or `Alternate to` fields
- [ ] All other Seq templates have `Excluded by default: Y` and `Alternate to: 0`
- [ ] Sequences listed in descending order in Rota Stage
- [ ] Conditions listed in descending order in both Activation and Result warnings
- [ ] Investigations listed in ascending canonical order
- [ ] `REORDER` keyword present in Result warnings > Investigations
- [ ] Result warnings at level 2 (parallel to Stages), NOT nested inside Stages > Seq
- [ ] Activation Result warnings at level 4 (inside Stages > Seq > )
- [ ] Info URL uses UPPERCASE document code
- [ ] No comment lines (`;;`) in generated output (those are hand-coding artifacts)
- [ ] Description line present for EVERY template (not just first and last)
- [ ] `Rota code:` in Approval section uses mixed-case document code (as in PDF)
- [ ] `Available: N` globally, `Available: Y` under directorate override

---

## 15. Domain Glossary

| Term | Definition |
|---|---|
| **EPMA** | Electronic Prescribing and Medicines Administration |
| **PICS** | Prescribing Information and Communication System (the specific EPMA) |
| **MUMPS/M** | Programming language used by PICS backend |
| **TTO** | To Take Out — outpatient prescription for patient to take home |
| **REG** | Regular — inpatient prescription administered in hospital |
| **REG_T** | Regular TTO — PICS prescription mode for outpatient (TTO mapped to REG_T) |
| **OOF** | Out of Formulary |
| **PiP** | Prepared in Pharmacy |
| **MRAPU** | Medicines Requiring Additional Precautions in Use |
| **FBC** | Full Blood Count (includes Hb, WCC, Neuts, Plt) |
| **U&E** | Urea and Electrolytes (includes Na, K, U, Cr, GFR) |
| **LFTs** | Liver Function Tests (includes Alb, Bili, AlkPhos, ALT) |
| **BSA** | Body Surface Area (used for dose calculation in some regimens) |
| **sysPassword** | PICS severity level — requires password override to proceed |
| **sysACTION** | PICS message target — flags result for clinical action |
| **ROTANORES** | Standard PICS message code for "no blood result available" |
| **CYP3A4** | Cytochrome P450 3A4 enzyme (drug metabolism) |
| **BD** | Twice daily (bis die) |
| **OD** | Once daily (omni die) |
| **TDS** | Three times daily (ter die sumendus) |
| **SmPC** | Summary of Product Characteristics |
| **CRLF** | Carriage Return + Line Feed (`\r\n`, Windows line ending) |
| **CUT** | PICS import keyword to delete an existing record |
| **GT** | Greater Than (condition function) |
| **LT** | Less Than (condition function) |

---

## 16. Reference Files

All in `Rota example/`:

| File | Role | Notes |
|---|---|---|
| `Drota930 Darolutamide.pdf` | Input example | Paper rota for Darolutamide |
| `Drota930 Darolutamide.docx` | Intermediate example | 4-table DOCX template |
| `#10350Daro- my test version.txt` | Output example | Hand-coded TXT (has known errors — see Section 11) |
