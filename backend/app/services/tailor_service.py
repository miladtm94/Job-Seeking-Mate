import io
import json
import logging
import re
import zipfile
from xml.etree import ElementTree

import pdfplumber

from app.core.ai_client import ai_complete
from app.schemas.tailor import EvaluateResponse

logger = logging.getLogger(__name__)


def parse_pdf(content: bytes) -> str:
    """Extract plain text from a PDF file."""
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def parse_docx(content: bytes) -> str:
    """Extract plain text from a .docx file without external dependencies."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paragraphs: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            with z.open("word/document.xml") as f:
                tree = ElementTree.parse(f)
        for para in tree.iter(f"{{{ns}}}p"):
            runs = [t.text for t in para.iter(f"{{{ns}}}t") if t.text]
            if runs:
                paragraphs.append("".join(runs))
    except Exception as exc:
        raise ValueError(f"Could not parse .docx file: {exc}") from exc
    return "\n".join(paragraphs)


class TailorService:
    """Generate a tailored resume and cover letter from raw CV text + job description.

    Implements a 5-step Senior Recruiter workflow:
      1. Deep Analysis      — extract JD priorities, ATS keywords, seniority signals
      2. Gap & Fit          — map candidate background to JD; reframe partial matches
      3. Resume Generation  — ATS-optimized, impact-driven, mirrors JD language
      4. Cover Letter       — 250-350 words, evidence-based, role-specific hook
      5. Optimization       — keyword density, consistency, remove fluff
    """

    _SYSTEM = (
        "You are a Senior Principal Recruiter and Hiring Manager with 15+ years of experience "
        "across industry and academia. You specialize in ATS optimization, competency-based "
        "hiring, and crafting high-conversion resumes and cover letters.\n\n"
        "OBJECTIVE: Generate a highly tailored, ATS-optimized resume and cover letter that aligns "
        "precisely with the provided job description, using the candidate's existing resume/CV "
        "and background.\n\n"

        "STEP 1 — DEEP ANALYSIS\n"
        "Extract and prioritize: core responsibilities, required vs preferred skills, ATS keywords, "
        "seniority signals (ownership, leadership, scope). Identify implicit expectations such as "
        "stakeholder management, business impact, and domain expertise.\n\n"

        "STEP 2 — CANDIDATE GAP & FIT ASSESSMENT\n"
        "Map candidate experience to JD requirements:\n"
        "- Strong matches → emphasize and quantify with metrics\n"
        "- Partial matches → reframe using transferable skills without fabrication\n"
        "- Gaps → de-emphasize or strategically bridge\n"
        "RULE: Do NOT invent experience, credentials, or metrics. Only optimize framing.\n\n"

        "STEP 3 — RESUME GENERATION (ATS-OPTIMIZED)\n"
        "Structure in this order:\n"
        "  1. Header: Name, Location, Phone, Email, LinkedIn/Portfolio\n"
        "  2. Professional Summary: 3-5 lines, keyword-rich, tailored to this exact role\n"
        "  3. Skills: grouped by category, aligned with JD keywords\n"
        "  4. Professional Experience: reverse chronological; bullets use Action → Method → Result; "
        "quantified outcomes; mirror JD language naturally; prioritize relevance over completeness\n"
        "  5. Projects (if relevant, especially for technical roles)\n"
        "  6. Education\n"
        "  7. Additional (Certifications, Publications, etc. if applicable)\n"
        "Target length: 1-2 pages. Output in plain text with section headers in ALL CAPS.\n\n"

        "STEP 4 — COVER LETTER GENERATION\n"
        "Structure:\n"
        "  Opening: role-specific hook proving you read the JD; NOT 'I am excited to apply'\n"
        "  Body: 2-3 paragraphs mapping experience to role priorities; cite 1-2 standout "
        "achievements with context; show understanding of company/mission if inferable\n"
        "  Closing: clear value proposition, one confident call-to-action sentence\n"
        "Length: 250-350 words exactly. Tone: professional, direct, credible.\n"
        "Forbidden words: 'passionate', 'excited', 'thrilled', 'team player', 'hardworking'.\n"
        "Output in plain text, no headers.\n\n"

        "STEP 5 — OPTIMIZATION\n"
        "Ensure ATS keyword density without stuffing. Ensure resume and cover letter are consistent. "
        "Remove all fluff, redundancy, and vague claims.\n\n"

        "STRICT RULES:\n"
        "- NEVER fabricate experience, metrics, or roles\n"
        "- NEVER use generic templates without tailoring\n"
        "- Prioritize quality over length\n"
        "- Write as if reviewed by a senior hiring panel\n\n"

        "OUTPUT FORMAT — use these exact section markers:\n\n"
        "### 1. Tailored Resume\n"
        "[Full resume in plain text]\n\n"
        "---\n\n"
        "### 2. Tailored Cover Letter\n"
        "[Full cover letter in plain text]\n\n"
        "---\n\n"
        "### 3. Strategic Notes\n"
        "[Key changes vs original, positioning strategy, any remaining gaps or risks]"
    )

    def generate(
        self,
        cv_text: str,
        job_description: str,
        key_achievements: str = "",
        target_industry: str = "",
        career_narrative: str = "",
        portfolio_links: str = "",
        constraints: str = "",
    ) -> tuple[str, str, str]:
        """Return (resume, cover_letter, strategic_notes). Raises ValueError on empty inputs."""
        if not cv_text.strip():
            raise ValueError("CV text is required")
        if not job_description.strip():
            raise ValueError("Job description is required")

        context_parts: list[str] = []
        if key_achievements:
            context_parts.append(f"Key achievements to highlight: {key_achievements}")
        if target_industry:
            context_parts.append(f"Target industry / company type: {target_industry}")
        if career_narrative:
            context_parts.append(f"Career narrative / positioning goal: {career_narrative}")
        if portfolio_links:
            context_parts.append(f"GitHub / portfolio links: {portfolio_links}")
        if constraints:
            context_parts.append(f"Constraints (visa, location, gaps, etc.): {constraints}")

        prompt = (
            f"CANDIDATE MASTER CV / RESUME:\n{cv_text[:5000]}\n\n"
            f"JOB DESCRIPTION:\n{job_description[:3500]}\n\n"
        )
        if context_parts:
            prompt += "ADDITIONAL CONTEXT:\n" + "\n".join(context_parts) + "\n\n"
        prompt += "Generate the tailored resume, cover letter, and strategic notes now."

        result = ai_complete(self._SYSTEM, prompt, max_tokens=3500)
        if not result:
            logger.error("TailorService: AI returned no output")
            return (
                "AI generation failed. Check your AI provider configuration in Settings.",
                "",
                "",
            )

        return self._parse(result)

    _EVAL_SYSTEM = (
        "You are a Certified Professional Resume Writer (CPRW) and ATS specialist "
        "with 15 years of recruitment experience across multiple industries.\n\n"
        "Evaluate the candidate's CV against the job description on these dimensions:\n"
        "1. ats_score (0-100): How well the resume passes ATS filters — keyword density, "
        "relevant skills, formatting signals.\n"
        "2. interview_probability (0-100): Probability a human recruiter shortlists this "
        "candidate after reviewing both documents.\n"
        "3. strengths: 3-5 specific strengths the candidate brings to this exact role.\n"
        "4. gaps: 3-5 specific gaps or weaknesses in the match.\n"
        "5. keyword_matches: For the 10-15 most important keywords from the JD, indicate "
        "'present' (clearly in CV), 'partial' (implied/related), or 'missing'.\n"
        "6. summary: 2-3 sentence overall assessment.\n"
        "7. recommendation: exactly one of — 'Strong Match', 'Good Match', "
        "'Moderate Match', or 'Weak Match'.\n\n"
        "Return ONLY valid JSON — no markdown, no preamble:\n"
        '{"ats_score": <int>, "interview_probability": <int>, '
        '"strengths": [...], "gaps": [...], '
        '"keyword_matches": {"keyword": "present|partial|missing", ...}, '
        '"summary": "...", "recommendation": "..."}'
    )

    _CL_SYSTEM = (
        "You are a professional career consultant and expert cover letter writer.\n\n"
        "Write a compelling, tailored cover letter BODY for this job application.\n\n"
        "REQUIREMENTS:\n"
        "- Output ONLY the body paragraphs — NO salutation, NO closing sign-off, "
        "NO date, NO address, NO candidate name at the end.\n"
        "- 3 tight paragraphs, 220-280 words total.\n"
        "- Tone: professional, direct, confident — never generic.\n"
        "- Opening: a strong hook connecting the candidate's key background to the "
        "role's primary need — NOT 'I am writing to apply'.\n"
        "- Body: evidence-based — reference 1-2 specific achievements with context; "
        "highlight transferable skills and genuine interest in this specific role.\n"
        "- Closing: clear value proposition and a forward-looking statement.\n"
        "- Forbidden words: passionate, excited, thrilled, team player, hardworking, "
        "synergy, leverage.\n"
        "- Plain text only — no markdown, no bullet points, no headers."
    )

    @staticmethod
    def _extract_json(raw: str) -> dict:
        """Extract the first balanced JSON object from AI output.

        More robust than regex: strips markdown fences, then walks character-
        by-character to find the matching closing brace, handling nested
        objects and strings with escaped characters.
        """
        # Strip markdown fences (```json ... ``` or ``` ... ```)
        text = re.sub(r"```(?:json)?\s*", "", raw)
        text = re.sub(r"\s*```", "", text).strip()

        # Try direct parse first (AI returned clean JSON)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Scan for the first { and find its matching }
        start = text.find("{")
        if start == -1:
            logger.error("evaluate: no JSON object in AI response:\n%s", raw[:500])
            raise ValueError(
                "AI did not return a JSON object. "
                "Check that your AI provider is configured correctly in Settings."
            )

        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError as exc:
                        logger.error(
                            "evaluate: JSON parse error on extracted block: %s\n%s",
                            exc, text[start : i + 1][:300],
                        )
                        raise ValueError(
                            "AI response contained malformed JSON. Try again."
                        ) from exc

        logger.error(
            "evaluate: unmatched braces in AI response (likely truncated):\n%s", raw[:500]
        )
        raise ValueError(
            "AI response was cut off before the JSON was complete. "
            "This usually means the response was too long — try a shorter CV or JD."
        )

    def evaluate(self, cv_text: str, job_description: str) -> EvaluateResponse:
        """Return an ATS + fit evaluation for the CV against the job description."""
        if not cv_text.strip():
            raise ValueError("CV text is required")
        if not job_description.strip():
            raise ValueError("Job description is required")

        prompt = (
            f"CANDIDATE CV:\n{cv_text[:5000]}\n\n"
            f"JOB DESCRIPTION:\n{job_description[:3500]}\n\n"
            "Evaluate now and return JSON only."
        )
        # 2000 tokens: keyword_matches alone can be ~600 tokens with 15 entries
        raw = ai_complete(self._EVAL_SYSTEM, prompt, max_tokens=2000)
        if not raw:
            raise ValueError("AI returned no output — check your provider configuration in Settings.")

        data = self._extract_json(raw)

        return EvaluateResponse(
            ats_score=int(data.get("ats_score", 0)),
            interview_probability=int(data.get("interview_probability", 0)),
            strengths=data.get("strengths", []),
            gaps=data.get("gaps", []),
            keyword_matches=data.get("keyword_matches", {}),
            summary=data.get("summary", ""),
            recommendation=data.get("recommendation", ""),
        )

    def generate_cover_letter(self, cv_text: str, job_description: str) -> str:
        """Return a plain-text cover letter body (no header/footer)."""
        if not cv_text.strip():
            raise ValueError("CV text is required")
        if not job_description.strip():
            raise ValueError("Job description is required")

        prompt = (
            f"CANDIDATE CV:\n{cv_text[:5000]}\n\n"
            f"JOB DESCRIPTION:\n{job_description[:3500]}\n\n"
            "Write the cover letter body now."
        )
        result = ai_complete(self._CL_SYSTEM, prompt, max_tokens=600)
        if not result:
            raise ValueError("AI returned no output — check your provider configuration in Settings.")
        return result.strip()

    @staticmethod
    def _parse(text: str) -> tuple[str, str, str]:
        """Split AI output into (resume, cover_letter, strategic_notes)."""
        resume_m = re.search(
            r"###\s*1\.\s*Tailored Resume\s*\n(.*?)(?=###\s*2\.|$)",
            text, re.DOTALL | re.IGNORECASE,
        )
        cover_m = re.search(
            r"###\s*2\.\s*Tailored Cover Letter\s*\n(.*?)(?=###\s*3\.|$)",
            text, re.DOTALL | re.IGNORECASE,
        )
        notes_m = re.search(
            r"###\s*3\.\s*Strategic Notes\s*\n(.*?)$",
            text, re.DOTALL | re.IGNORECASE,
        )

        resume = resume_m.group(1).strip().strip("-").strip() if resume_m else ""
        cover_letter = cover_m.group(1).strip().strip("-").strip() if cover_m else ""
        strategic_notes = notes_m.group(1).strip() if notes_m else ""

        # Fallback: return full text as resume if parsing failed entirely
        if not resume and not cover_letter:
            logger.warning("TailorService: could not parse sections, returning raw output")
            resume = text

        return resume, cover_letter, strategic_notes
