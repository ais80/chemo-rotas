"""Data models for chemo rota conversion."""

from dataclasses import dataclass, field


@dataclass
class BloodTest:
    test_code: str           # e.g. "PLATS", "NEUTS", "GFR", "BILI", "ALT"
    threshold_value: int     # e.g. 100
    threshold_function: str  # "LT" or "GT"
    message_text_line1: str  # e.g. "Plts < 100 x 10^9/L"
    message_text_line3: str  # e.g. "Contact prescriber."


@dataclass
class DrugTemplate:
    drug_name_upper: str      # e.g. "DAROLUTAMIDE"
    dose: int                 # e.g. 600
    units: str                # e.g. "mg"
    mode: str                 # "TTO" or "REG"
    frequency: str            # e.g. "BD"
    route: str                # e.g. "ORAL" or "IV"
    form: str                 # e.g. "TAB" or "INJ"
    timing_constraints: str   # e.g. "Take with food" or "30 min infusion"
    first_dose_day: int       # e.g. 1
    final_dose_day: str       # "U" (until stopped) or integer as string
    group: str                # e.g. "1A" (primary) or "1" (alternate)
    # IV-specific fields (empty string for oral templates)
    fluid_type: str = ""      # e.g. "N/Saline", "Dextrose 5%"
    volume_ml: str = ""       # e.g. "1000" (ml)
    infusion_duration: str = ""  # e.g. "4 hours", "30 mins"

    @property
    def is_primary(self) -> bool:
        """Primary template has a letter suffix in group (e.g. '1A')."""
        return self.group[-1].isalpha()


@dataclass
class RotaConfig:
    # Extracted from PDF
    document_code: str         # e.g. "Drota930"
    drug_full_name: str        # e.g. "Darolutamide"
    indication: str            # e.g. "non-metastatic castration resistant prostate cancer (nmCRPC)"
    reference: str             # e.g. "SmPC for Darolutamide"

    # Human input required
    drug_prefix: str           # e.g. "DARO"
    ticket_number: str         # e.g. "10350"
    default_cycles: int        # e.g. 12
    cycle_delay: str           # e.g. "4w"
    directorate: str           # e.g. "ONC"
    specialty_class: str       # e.g. "UROLOGY"
    inpatient_or_outpatient: str  # "O" or "I"

    # Drug templates
    templates: list[DrugTemplate] = field(default_factory=list)

    # Blood tests (order defines canonical ordering)
    blood_test_validity_days: int = 7
    blood_tests: list[BloodTest] = field(default_factory=list)

    # Free text
    rota_info_paragraphs: list[str] = field(default_factory=list)
    warnings_paragraphs: list[str] = field(default_factory=list)

    @property
    def drug_title_case(self) -> str:
        """E.g. PREFIX='DARO' -> 'Daro'"""
        return self.drug_prefix[0].upper() + self.drug_prefix[1:].lower()

    @property
    def doc_code_upper(self) -> str:
        return self.document_code.upper()

    @property
    def max_result_age(self) -> str:
        """Convert days to weeks string. E.g. 7 -> '1w'"""
        return f"{self.blood_test_validity_days // 7}w"

    def template_code(self, t: DrugTemplate) -> str:
        """Generate template code. E.g. DARO_Daro600BD_TTO"""
        return f"{self.drug_prefix}_{self.drug_title_case}{t.dose}{t.frequency}_{t.mode}"

    def template_description(self, t: DrugTemplate) -> str:
        """Generate template description. E.g. Darolutamide 600mg BD TTO"""
        return f"{self.drug_full_name} {t.dose}{t.units} {t.frequency} {t.mode}"

    def message_code(self, bt: BloodTest) -> str:
        """Generate message code. E.g. DAROneuts"""
        return f"{self.drug_prefix}{bt.test_code.lower()}"

    def stage_code(self, n: int = 1) -> str:
        """Generate stage code. E.g. DARO_Stage1"""
        return f"{self.drug_prefix}_Stage{n}"

    def prescription_mode(self, t: DrugTemplate) -> str:
        """Map DOCX mode to PICS prescription mode."""
        return "REG_T" if t.mode == "TTO" else "REG"

    @classmethod
    def from_dict(cls, d: dict) -> "RotaConfig":
        """Build a RotaConfig from a config dictionary (loaded from YAML)."""
        templates = [
            DrugTemplate(
                drug_name_upper=t["drug_name_upper"],
                dose=int(t["dose"]),
                units=t["units"],
                mode=t["mode"],
                frequency=t["frequency"],
                route=t["route"],
                form=t["form"],
                timing_constraints=t.get("timing_constraints", ""),
                first_dose_day=int(t.get("first_dose_day", 1)),
                final_dose_day=str(t.get("final_dose_day", "U")),
                group=t["group"],
                fluid_type=t.get("fluid_type", ""),
                volume_ml=str(t.get("volume_ml", "")),
                infusion_duration=t.get("infusion_duration", ""),
            )
            for t in d.get("templates", [])
        ]
        blood_tests = [
            BloodTest(
                test_code=bt["test_code"],
                threshold_value=int(bt["threshold_value"]),
                threshold_function=bt["threshold_function"],
                message_text_line1=bt["message_text_line1"],
                message_text_line3=bt["message_text_line3"],
            )
            for bt in d.get("blood_tests", [])
        ]
        return cls(
            document_code=d["document_code"],
            drug_full_name=d["drug_full_name"],
            indication=d.get("indication", ""),
            reference=d.get("reference", ""),
            drug_prefix=d["drug_prefix"],
            ticket_number=str(d["ticket_number"]),
            default_cycles=int(d["default_cycles"]),
            cycle_delay=d["cycle_delay"],
            directorate=d["directorate"],
            specialty_class=d["specialty_class"],
            inpatient_or_outpatient=d.get("inpatient_or_outpatient", "O"),
            templates=templates,
            blood_test_validity_days=int(d.get("blood_test_validity_days", 7)),
            blood_tests=blood_tests,
            rota_info_paragraphs=d.get("rota_info_paragraphs", []),
            warnings_paragraphs=d.get("warnings_paragraphs", []),
        )

    def seq_assignments(self) -> list[tuple[int, DrugTemplate]]:
        """Assign sequence numbers. Primary (group ends with letter) = 0, others = 1,2,..."""
        primary = None
        alternates = []
        for t in self.templates:
            if t.is_primary:
                primary = t
            else:
                alternates.append(t)
        result = []
        if primary:
            result.append((0, primary))
        for i, alt in enumerate(alternates, start=1):
            result.append((i, alt))
        return result
