from app.agents.orchestrator import AgentOrchestrator

orchestrator = AgentOrchestrator()


def run_recommendation_cycle(payload: dict[str, object]) -> dict[str, object]:
    """Entry point for background orchestration jobs."""
    return orchestrator.run_full_cycle(payload)


def run_search_and_match(payload: dict[str, object]) -> dict[str, object]:
    """Search jobs and match against candidate profile."""
    return orchestrator.search_and_match(payload)
