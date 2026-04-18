from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.security import require_auth
from app.schemas.tailor import (
    CoverLetterRequest,
    CoverLetterResponse,
    EvaluateRequest,
    EvaluateResponse,
    ParseFileResponse,
    TailorRequest,
    TailorResponse,
)
from app.services.tailor_service import TailorService, parse_docx, parse_pdf

router = APIRouter()
_service = TailorService()


@router.post(
    "/parse-file",
    response_model=ParseFileResponse,
    dependencies=[Depends(require_auth)],
)
async def parse_file(file: UploadFile = File(...)) -> ParseFileResponse:
    """Extract plain text from an uploaded PDF, .docx, or .txt file."""
    content = await file.read()
    filename = (file.filename or "").lower()

    try:
        if filename.endswith(".pdf"):
            text = parse_pdf(content)
        elif filename.endswith(".docx"):
            text = parse_docx(content)
        elif filename.endswith(".txt"):
            text = content.decode("utf-8", errors="replace")
        else:
            raise HTTPException(
                status_code=415,
                detail="Unsupported file type. Upload a .pdf, .docx, or .txt file.",
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from the file.")

    return ParseFileResponse(text=text)


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    dependencies=[Depends(require_auth)],
)
def evaluate(payload: EvaluateRequest) -> EvaluateResponse:
    """Run ATS + fit evaluation between a CV and a job description."""
    try:
        return _service.evaluate(
            cv_text=payload.cv_text,
            job_description=payload.job_description,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post(
    "/cover-letter",
    response_model=CoverLetterResponse,
    dependencies=[Depends(require_auth)],
)
def generate_cover_letter(payload: CoverLetterRequest) -> CoverLetterResponse:
    """Generate a tailored cover letter body (plain text, no header/footer)."""
    try:
        text = _service.generate_cover_letter(
            cv_text=payload.cv_text,
            job_description=payload.job_description,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return CoverLetterResponse(cover_letter=text)


@router.post(
    "/generate",
    response_model=TailorResponse,
    dependencies=[Depends(require_auth)],
)
def generate_tailored(payload: TailorRequest) -> TailorResponse:
    try:
        resume, cover_letter, strategic_notes = _service.generate(
            cv_text=payload.cv_text,
            job_description=payload.job_description,
            key_achievements=payload.key_achievements,
            target_industry=payload.target_industry,
            career_narrative=payload.career_narrative,
            portfolio_links=payload.portfolio_links,
            constraints=payload.constraints,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    return TailorResponse(
        resume=resume,
        cover_letter=cover_letter,
        strategic_notes=strategic_notes,
    )
