"""Convert plain-text resume into a clean, ATS-safe PDF using fpdf2."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fpdf import FPDF

logger = logging.getLogger(__name__)

_RESUME_DIR = Path(__file__).resolve().parents[4] / "data" / "resumes"


class ResumePDFGenerator:
    """Converts a plain-text resume string into a PDF file ready for upload."""

    # Visual settings
    PAGE_MARGIN   = 18   # mm
    BODY_FONT_SZ  = 10   # pt
    HEAD_FONT_SZ  = 13   # pt
    SEC_FONT_SZ   = 10   # pt
    LINE_H        = 5.5  # mm
    SEC_GAP       = 3    # mm
    ACCENT        = (44, 62, 80)   # dark navy for headings
    BODY_COLOR    = (30, 30, 30)

    def generate(self, resume_text: str, candidate_name: str) -> Path:
        """Return path to generated PDF, creating it under data/resumes/."""
        _RESUME_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w\-]", "_", candidate_name.strip())
        out_path = _RESUME_DIR / f"{safe_name}_resume.pdf"

        pdf = _ResumePDF(
            margin=self.PAGE_MARGIN,
            body_sz=self.BODY_FONT_SZ,
            head_sz=self.HEAD_FONT_SZ,
            sec_sz=self.SEC_FONT_SZ,
            line_h=self.LINE_H,
            sec_gap=self.SEC_GAP,
            accent=self.ACCENT,
            body_color=self.BODY_COLOR,
        )
        pdf.add_page()
        pdf.render(resume_text)
        pdf.output(str(out_path))
        logger.info("Generated resume PDF: %s", out_path)
        return out_path


class _ResumePDF(FPDF):
    """Internal FPDF subclass with resume-specific rendering logic."""

    # Section header keywords that trigger a divider + bold heading
    SECTION_HEADERS = {
        "professional summary", "summary", "objective",
        "experience", "work experience", "employment",
        "education", "qualifications",
        "skills", "core skills", "technical skills", "key skills",
        "certifications", "awards", "publications",
        "projects", "volunteer", "languages",
    }

    # Use built-in core PDF font (no external TTF required, fully ATS-safe)
    _FONT = "Helvetica"

    def __init__(self, margin, body_sz, head_sz, sec_sz, line_h, sec_gap, accent, body_color):
        super().__init__()
        self.set_margins(margin, margin, margin)
        self.set_auto_page_break(auto=True, margin=margin)
        self._body_sz   = body_sz
        self._head_sz   = head_sz
        self._sec_sz    = sec_sz
        self._line_h    = line_h
        self._sec_gap   = sec_gap
        self._accent    = accent
        self._body_color = body_color
        self._first_line = True

    # Map common Unicode chars that core PDF fonts can't handle
    _UNICODE_MAP = str.maketrans({
        "\u2013": "-", "\u2014": "--", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2022": "-", "\u00b7": ".",
        "\u00e9": "e", "\u00e8": "e", "\u00ea": "e", "\u00fc": "u",
        "\u00f6": "o", "\u00e4": "a", "\u00df": "ss",
    })

    def render(self, text: str) -> None:
        safe = text.translate(self._UNICODE_MAP)
        # Replace any remaining non-latin1 chars with '?'
        safe = safe.encode("latin-1", errors="replace").decode("latin-1")
        lines = safe.splitlines()
        for raw in lines:
            line = raw.rstrip()
            self._render_line(line)

    def _render_line(self, line: str) -> None:
        stripped = line.strip()

        # Blank line → small vertical gap
        if not stripped:
            self.ln(self._sec_gap)
            return

        # Detect all-caps section header (e.g. "EXPERIENCE", "CORE SKILLS")
        is_allcaps_header = (
            stripped.isupper()
            and 2 < len(stripped) < 60
            and not stripped.startswith("•")
        )
        # Detect mixed-case known section header
        is_known_header = stripped.lower().rstrip(":") in self.SECTION_HEADERS

        if self._first_line:
            # Very first line → treat as the candidate name (large heading)
            self._draw_name(stripped)
            self._first_line = False
            return

        if is_allcaps_header or is_known_header:
            self._draw_section_header(stripped)
            return

        # Contact line (email / phone / location — usually near the top)
        if self._looks_like_contact(stripped):
            self._draw_contact(stripped)
            return

        # Bullet point
        if stripped.startswith(("•", "-", "–", "*")):
            self._draw_bullet(stripped.lstrip("•-–* "))
            return

        # Default body text
        self._draw_body(stripped)

    def _draw_name(self, name: str) -> None:
        self.set_text_color(*self._accent)
        self.set_font(self._FONT, "B", self._head_sz + 3)
        self.cell(0, 9, name, new_x="LMARGIN", new_y="NEXT", align="C")
        # Underline
        self.set_draw_color(*self._accent)
        self.set_line_width(0.4)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(2)
        self._reset_body()

    def _draw_section_header(self, text: str) -> None:
        self.ln(self._sec_gap)
        self.set_text_color(*self._accent)
        self.set_font(self._FONT, "B", self._sec_sz + 1)
        self.cell(0, 6, text.upper(), new_x="LMARGIN", new_y="NEXT")
        # Thin rule under header
        self.set_draw_color(*self._accent)
        self.set_line_width(0.2)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(1.5)
        self._reset_body()

    def _draw_contact(self, text: str) -> None:
        self.set_text_color(80, 80, 80)
        self.set_font(self._FONT, "", self._body_sz - 1)
        self.cell(0, self._line_h, text, new_x="LMARGIN", new_y="NEXT", align="C")
        self._reset_body()

    def _draw_bullet(self, text: str) -> None:
        self._reset_body()
        self.set_x(self.l_margin + 4)
        self.multi_cell(0, self._line_h, f"- {text}")

    def _draw_body(self, text: str) -> None:
        self._reset_body()
        self.multi_cell(0, self._line_h, text)

    def _reset_body(self) -> None:
        self.set_text_color(*self._body_color)
        self.set_font(self._FONT, "", self._body_sz)

    @staticmethod
    def _looks_like_contact(line: str) -> bool:
        lower = line.lower()
        return any(kw in lower for kw in ("@", "phone:", "mobile:", "linkedin", "github", "|"))
