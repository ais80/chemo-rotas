# Chemo Rota Converter — Change Log

## Session 2 (February 2026) — Sequential PDF Testing & IV Parser Fixes

### Overview
Conducted sequential PDF-to-YAML extraction testing across 4 test folders
(`Rota examples/Testing files sequential/`), comparing each PDF output against its
corresponding HTML reference file. 14 code fixes were applied to `converter/extract_pdf.py`.

---

### Fixes Applied to `converter/extract_pdf.py`

#### Fix 1 — Dose context window (cross-drug contamination)
**Problem:** Dose extraction used a 3-line context window (`lines[i-1:i+3]`), causing the
previous or next drug's dose to bleed into the current drug when OCR table rows are close.
**Fix:** Restricted `dose_context` to the current line only (`dose_context = lines[i]`).
**Effect:** Eliminated false doses on DOXORUBICIN, VINCRISTINE, ETOPOSIDE in CHOEP/R-CHOEP.

#### Fix 2 — Route detection false SC positives
**Problem:** `\bsc\b` in a 3-line context matched OCR artefacts from signature columns at
the end of drug table rows, incorrectly assigning `route: SC` to IV drugs.
**Fix:** (a) Restricted route detection to `curr_line = lines[i]` only.
(b) Replaced bare `\bsc\b` with explicit patterns: `subcutaneous`, `s/c`, `sc inj`,
`sc injection`.

#### Fix 3 — Infusion duration bleeding
**Problem:** Administration advice on adjacent lines (e.g. "Initial rate of 50mg/hr for the
first 30 minutes…") was picked up as infusion duration for the wrong drug.
**Fix:** Restricted duration extraction to `curr_line = lines[i]` only.

#### Fix 4 — `final_dose_day` default for single-day IV drugs
**Problem:** `final_dose_day` defaulted to `"U"` (until stopped) for IV drugs when no day
range was detected — incorrect for single-day infusions.
**Fix:** When no day range detected, set `last_day = str(first_day)`.

#### Fix 5 — Document code with space ("HROTA 10b")
**Problem:** Regex `H-?ROTA\d+` did not match document codes with a space (e.g. "H-ROTA 10b").
**Fix:** Updated regex to `H-?ROTA\s*\d+[a-z]?` and normalise by removing spaces.

#### Fix 6 — Rota name captures cycle-length suffix
**Problem:** Rota names like "R-CHOP 21" were being extracted as just "R-CHOP".
**Fix:** Updated `parse_rota_name_from_iv` regex to `\b{abbr}(?:\s+(\d+))?\b` and returns
`f"{abbr} {suffix}"` when a number suffix is found.

#### Fix 7 — Cycle delay inference from name suffix
**Problem:** `cycle_delay` defaulted to `4w` even when the drug name contained the cycle
length (e.g. "R-CHOP 21" → 21 days → 3 weeks).
**Fix:** `parse_cycle_info` now accepts `drug_name` parameter; extracts trailing integer,
divides by 7, returns as `Nw` string. Also added `every\s+(\d+)\s*days?` pattern.

#### Fix 8 — ROTA_ABBREVIATIONS ordering (longer names before prefixes)
**Problem:** Shorter abbreviations matched before their longer compound forms
(e.g. `R-CODOX` matched before `R-CODOX-M`; `BEACOP` before `BEACOPP`).
**Fix:** Placed longer/more-specific forms first in `ROTA_ABBREVIATIONS`:
`R-CODOX-M` before `R-CODOX`; `BEACOPP` before `BEACOP`.

#### Fix 9 — DOSE UNKNOWN placeholder for unreadable doses
**Problem:** When OCR could not read a drug's dose, the drug was silently dropped from
the YAML output, giving no indication to the human reviewer.
**Fix:** Changed `if not dose_val: continue` to set `dose_val = 0` and append
`"DOSE UNKNOWN — OCR could not read dose, check original rota"` to `timing_constraints`.

#### Fix 10 — Additional Therapy section parser
**Problem:** Older IV rotas have a "Additional Therapy" footer section listing oral support
medications. These were not being extracted.
**Fix:** Added `parse_additional_therapy()` function. Parses lines in that section using
an explicit frequency whitelist (`od`, `bd`, `tds`, `qds`, etc.) to avoid consuming
"days" as part of the frequency field.

#### Fix 11 — Rota name frequency counting (cross-contamination between regimens)
**Problem:** The function returned the first matching abbreviation found anywhere in the
document text. Since R-IVAC rotas describe their alternating counterpart (R-CODOX-M)
in the preamble text, R-CODOX-M was returned as the name of an R-IVAC rota.
**Fix:** Changed from "first match" to "highest frequency count" approach.
Collects all valid (non-reference-context) matches for every abbreviation, counts them,
and returns the one with the most occurrences. Title area (first 800 chars) is searched
first as a priority pass.

#### Fix 12 — Nested abbreviation match elimination
**Problem:** `\bIVAC\b` matches the IVAC substring within every occurrence of `R-IVAC`
(because `-` is a non-word character, creating a word boundary before `I`). This inflated
IVAC's count above R-IVAC's, causing IVAC to be returned instead of R-IVAC.
**Fix:** After collecting all match spans, a shorter match is excluded if it is fully
contained within a longer match's span. This ensures `IVAC` occurrences inside `R-IVAC`
are not counted for the IVAC candidate.

#### Fix 13 — Narrative line skip in drug table parser
**Problem:** Informational sentences mentioning a drug (e.g. "…followed by two further
doses of Rituximab (on days 21 and 42…)") were matched as drug table rows. The "21" in
the sentence was then extracted as the dose day, giving RITUXIMAB `first_dose_day: 21`
instead of 1.
**Fix:** Added a `_NARRATIVE` regex that skips any line containing keywords indicating
narrative/informational context: `alternating`, `followed by`, `further doses of`,
`prior to`, `instead of`, `pre-medication`, `two cycles`, `subsequent doses`,
`is given on/as/with`, `are given on/as/with`.

#### Fix 14 — Rota type detection false IV signals
**Problem:** The rota type detector used `any(IV_drug in full_text)` as one of its IV
signals. This caused oral-only rotas (e.g. Darolutamide) to be misclassified as `MIXED`
when a known IV drug name (METHOTREXATE) appeared in the drug interaction warnings text.
When classified as MIXED, the IV name parser was called and returned garbage like "Hb Na"
(from the blood test header).
**Fix:** Changed signal from "IV drug name anywhere in text" to "IV drug name appearing
adjacent to a `|` table separator character" — requiring table context rather than any
text mention.

---

### Rota ABBREVIATIONS Added
- `CHOEP`, `R-CHOEP` — CHEOP regimen variants
- `R-CODOX-M` — moved before `R-CODOX` to ensure correct matching

---

### Known OCR Limitations (not code bugs)

The following issues are inherent to poor-quality scanned PDFs and cannot be resolved
by code changes:

| Drug | Issue | Cause |
|---|---|---|
| BSA-based doses (mg/m²) | `dose: 0` with DOSE UNKNOWN flag | OCR misreads fractions/superscripts |
| VINCRISTINE in BEACOP PDF | Drug absent from YAML | Drug name not in OCR output at all |
| PROCARBAZINE in BEACOP PDF | Drug absent from YAML | Drug name not in OCR output at all |
| ALLOPURINOL, FILGRASTIM in R-IVAC PDF | Absent from YAML | Not in OCR output |
| Blood test thresholds in some PDFs | `blood_tests: []` | Poor scan quality |
| Rota info paragraphs in some PDFs | `rota_info_paragraphs: []` | Poor scan quality |

---

### Test Results Summary

| Folder | PDF | HTML Reference | Key Result |
|---|---|---|---|
| 2 R-CHEOP | CHOEP-21.pdf | HROTA210v02.htm | drug name, doses, cycle delay fixed |
| 3 R-CODOX-M | rcodox m \_65001.pdf | HROTA191v1.htm | R-CODOX-M name fixed, DOSE UNKNOWN working |
| 4 R-IVAC | H-ROTA 192.pdf | HROTA192v01.htm | R-IVAC name fixed, RITUXIMAB 375mg day 1 |
| 5 BEACOP DAC | Escalated BEACOP DAC v3.1.pdf | HROTA88v01.htm | OCR limitations documented |

**Regression test:** All 17 previously-working PDFs confirmed unbroken after all changes.

---

## Session 1 (earlier) — Initial Pipeline & Core Fixes

### Overview
Initial pipeline built. Core fixes applied following R-CHOP 21 and other early test cases.

### Changes
- ICE false positive filter (prevented "ICE" matching in non-ICE contexts)
- Maintenance false positive filter
- ACALABRUTINIB removed from IV drug list (oral drug)
- HTML parser (`extract_html.py`) built for PICS info pages
- R-CHOP 21 full pipeline working end-to-end
