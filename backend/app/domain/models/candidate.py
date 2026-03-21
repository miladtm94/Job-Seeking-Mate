from dataclasses import dataclass, field


@dataclass(slots=True)
class CandidateProfile:
    id: str
    name: str
    email: str
    skills: list[str] = field(default_factory=list)
    preferred_roles: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
