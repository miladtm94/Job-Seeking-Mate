import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentTask:
    name: str
    payload: dict[str, Any]


@dataclass(slots=True)
class AgentPlan:
    steps: list[str]
    required_data: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentResult:
    agent_name: str
    success: bool
    confidence: float
    output: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    iterations: int = 1


class BaseAgent(ABC):
    """Base agent implementing the Plan -> Act -> Evaluate -> Refine loop."""

    name: str = "base_agent"
    max_iterations: int = 3
    confidence_threshold: float = 0.7

    def run(self, task: AgentTask) -> AgentResult:
        logger.info("[%s] Starting task: %s", self.name, task.name)

        # 1. PLAN
        plan = self.plan(task)
        logger.info("[%s] Plan: %d steps", self.name, len(plan.steps))

        result = None
        for iteration in range(1, self.max_iterations + 1):
            # 2. ACT
            result = self.act(task, plan)
            result.iterations = iteration

            # 3. EVALUATE
            if self.evaluate(result):
                logger.info(
                    "[%s] Completed in %d iteration(s), confidence=%.2f",
                    self.name,
                    iteration,
                    result.confidence,
                )
                return result

            # 4. REFINE
            if iteration < self.max_iterations:
                logger.info(
                    "[%s] Refining (iteration %d, confidence=%.2f)",
                    self.name,
                    iteration,
                    result.confidence,
                )
                task = self.refine(task, result)

        logger.warning(
            "[%s] Max iterations reached, returning best result (confidence=%.2f)",
            self.name,
            result.confidence if result else 0,
        )
        return result or AgentResult(self.name, False, 0, {}, ["Max iterations exceeded"])

    @abstractmethod
    def plan(self, task: AgentTask) -> AgentPlan:
        ...

    @abstractmethod
    def act(self, task: AgentTask, plan: AgentPlan) -> AgentResult:
        ...

    def evaluate(self, result: AgentResult) -> bool:
        return result.success and result.confidence >= self.confidence_threshold

    def refine(self, task: AgentTask, result: AgentResult) -> AgentTask:
        task.payload["_previous_errors"] = result.errors
        task.payload["_previous_confidence"] = result.confidence
        return task
