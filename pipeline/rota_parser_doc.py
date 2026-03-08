"""Reverse parser: Rota .doc (legacy format) -> ParsedProtocol.

Uses win32com.client to convert .doc to .docx via Word COM automation,
then delegates to RotaDocxParser. Falls back to antiword for Word 95 files.
"""

import os
import re
import tempfile
import subprocess
from models import ParsedProtocol, ProtocolHeader, SectionContent
from review_flags import ReviewFlagCollector


class RotaDocParser:
    """Parser for legacy .doc Rota files.

    Strategy:
    1. Convert .doc to .docx via Word COM automation
    2. Delegate to RotaDocxParser
    3. If Word blocks the file (Word 95), fall back to antiword
    """

    def __init__(self, doc_path: str):
        self.doc_path = os.path.abspath(doc_path)
        self.flags = ReviewFlagCollector()
        self.filename = os.path.basename(doc_path)

    def parse(self) -> ParsedProtocol:
        """Main entry: convert .doc to .docx, then delegate."""
        try:
            docx_path = self._convert_via_word()
            from rota_parser import RotaDocxParser
            parser = RotaDocxParser(docx_path)
            result = parser.parse()
            # Clean up temp file and directory
            try:
                os.unlink(docx_path)
                os.rmdir(os.path.dirname(docx_path))
            except OSError:
                pass
            return result
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in [
                'blocked', 'protected', 'trust center', 'file block',
                'cannot open', 'format',
            ]):
                self.flags.warn(
                    "file", "format",
                    f"Word could not open file (likely Word 95 format), "
                    f"trying antiword: {e}"
                )
                return self._parse_via_antiword()
            raise

    def _convert_via_word(self) -> str:
        """Use Word COM to save .doc as .docx in a temp directory."""
        import win32com.client

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0  # Suppress dialogs

        try:
            doc = word.Documents.Open(self.doc_path, ReadOnly=True)
            # Save as .docx (format 16 = wdFormatXMLDocument)
            temp_dir = tempfile.mkdtemp(prefix='rota_convert_')
            basename = os.path.splitext(self.filename)[0]
            docx_path = os.path.join(temp_dir, f"{basename}.docx")
            doc.SaveAs2(docx_path, FileFormat=16)
            doc.Close(False)
            return docx_path
        finally:
            word.Quit()

    def _parse_via_antiword(self) -> ParsedProtocol:
        """Fallback for Word 95 files: use antiword for text extraction."""
        try:
            result = subprocess.run(
                ['antiword', '-w', '0', self.doc_path],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                self.flags.error(
                    "file", "antiword",
                    f"antiword failed: {result.stderr[:200]}"
                )
                return self._empty_protocol()

            return self._parse_plain_text(result.stdout)
        except FileNotFoundError:
            self.flags.error(
                "file", "antiword",
                "antiword not found. Cannot parse Word 95 files without it."
            )
            return self._empty_protocol()

    def _parse_plain_text(self, text: str) -> ParsedProtocol:
        """Parse antiword plain text output into a best-effort ParsedProtocol.

        This is inherently lossy — table structure is approximated from
        pipe-delimited output.
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        self.flags.warn(
            "file", "format",
            "Word 95 file parsed via antiword — table structure may be "
            "incomplete. Manual review recommended."
        )

        return ParsedProtocol(
            header=ProtocolHeader(
                regimen_name=self._extract_name_from_filename(),
                rota_code=self._extract_code_from_filename(),
                last_updated="",
            ),
            warnings_text=lines[:20],  # Best effort: first 20 lines
            review_flags=self.flags.get_all(),
        )

    def _extract_code_from_filename(self) -> str:
        name = os.path.splitext(self.filename)[0]
        match = re.search(r'H-?ROTA?\s*(\d+\w*)', name, re.IGNORECASE)
        if match:
            return f"HROTA{match.group(1)}"
        return name.replace(' ', '_')

    def _extract_name_from_filename(self) -> str:
        name = os.path.splitext(self.filename)[0]
        cleaned = re.sub(r'H-?ROTA?\s*\d+\w*', '', name,
                         flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*-?\s*(final|v\d+|draft)\s*$', '',
                         cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(' -')
        return cleaned if len(cleaned) > 2 else ""

    def _empty_protocol(self) -> ParsedProtocol:
        return ParsedProtocol(review_flags=self.flags.get_all())
