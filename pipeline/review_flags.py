"""Review flag collector for tracking parsing ambiguities."""

from models import ReviewFlag


class ReviewFlagCollector:
    def __init__(self):
        self.flags: list[ReviewFlag] = []

    def warn(self, section: str, field: str, message: str):
        self.flags.append(ReviewFlag(section, field, message, "warning"))

    def error(self, section: str, field: str, message: str):
        self.flags.append(ReviewFlag(section, field, message, "error"))

    def info(self, section: str, field: str, message: str):
        self.flags.append(ReviewFlag(section, field, message, "info"))

    def get_all(self) -> list[ReviewFlag]:
        return list(self.flags)
