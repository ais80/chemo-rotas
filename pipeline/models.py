"""Data models for the chemotherapy protocol conversion pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RowType(Enum):
    NORMAL = "normal"
    DOSE_REDUCTION = "dose_reduction"  # Strikethrough rows


@dataclass
class ProtocolHeader:
    regimen_name: str       # e.g. "Apalutamide", "Mitoxantrone & prednisolone"
    rota_code: str          # e.g. "DROTA932", "OROTA105a"
    last_updated: str       # e.g. "7th January 2023"


@dataclass
class ChemoRow:
    """A row from the CHEMOTHERAPY (sequenced) treatment table."""
    stage_day: str = ""
    time: str = ""
    drug_diluent: str = ""
    round_dose_to: str = ""
    dose_calc_volume: str = ""
    rate: str = ""
    route: str = ""
    special_directions: str = ""
    target_interval: str = ""
    margin: str = ""
    follows_seq_label: str = ""
    line: str = ""
    seq_label: str = ""
    row_type: RowType = RowType.NORMAL


@dataclass
class NonSequencedRow:
    """A row from the NON-SEQUENCED treatment table."""
    drug: str = ""
    dose_calculation: str = ""
    mode: str = ""
    freq: str = ""
    timing_constraints: str = ""
    route: str = ""
    form: str = ""
    start_with_oof: str = ""
    first_dose_day: str = ""
    first_dose_time: str = ""
    final_dose_day: str = ""
    final_dose_time: str = ""
    group: str = ""
    row_type: RowType = RowType.NORMAL


@dataclass
class ProceedRuleDrug:
    """Proceed rules for a single drug."""
    drug_name: str = ""
    neutrophils: str = ""
    platelets: str = ""
    renal: str = ""
    hepatic: str = ""


@dataclass
class SectionContent:
    """Free text content from a named section."""
    section_name: str = ""
    text_paragraphs: list[str] = field(default_factory=list)
    is_empty: bool = False


@dataclass
class TreatmentData:
    """All treatment information extracted from the Treatment section."""
    chemo_rows: list[ChemoRow] = field(default_factory=list)
    non_sequenced_rows: list[NonSequencedRow] = field(default_factory=list)
    has_chemo_table: bool = False
    has_nonsequenced_table: bool = False


@dataclass
class ReviewFlag:
    """A flag indicating something needs manual review."""
    section: str
    field: str
    message: str
    severity: str = "warning"  # "warning", "error", or "info"


@dataclass
class ParsedProtocol:
    """The complete parsed protocol - universal intermediate format."""
    header: ProtocolHeader = field(default_factory=lambda: ProtocolHeader("", "", ""))
    eligibility: SectionContent = field(default_factory=SectionContent)
    exclusions: SectionContent = field(default_factory=SectionContent)
    tests: SectionContent = field(default_factory=SectionContent)
    premedications: SectionContent = field(default_factory=SectionContent)
    treatment: TreatmentData = field(default_factory=TreatmentData)
    proceed_rules: list[ProceedRuleDrug] = field(default_factory=list)
    dose_modifications: SectionContent = field(default_factory=SectionContent)
    precautions: SectionContent = field(default_factory=SectionContent)
    continue_treatment: SectionContent = field(default_factory=SectionContent)
    support_medications: SectionContent = field(default_factory=SectionContent)
    review_flags: list[ReviewFlag] = field(default_factory=list)
    warnings_text: list[str] = field(default_factory=list)
    info_text: list[str] = field(default_factory=list)
