from dataclasses import dataclass, field


@dataclass(slots=True)
class MatchResult:
    score: int
    recommendation: str
    matching_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
