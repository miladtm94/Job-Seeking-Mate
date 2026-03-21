from dataclasses import dataclass, field


@dataclass(slots=True)
class Job:
    id: str
    title: str
    company: str
    source: str
    location: str
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
