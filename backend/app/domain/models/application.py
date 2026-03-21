from dataclasses import dataclass


@dataclass(slots=True)
class Application:
    id: str
    candidate_id: str
    job_id: str
    status: str
    mode: str
