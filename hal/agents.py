"""Sub-agent abstractions for HAL: Planner and Critic.

These are "thinker" agents that never call tools directly. They use
VLLMClient under the hood with specialized system prompts to:

- PlannerAgent: turn an operator query into a short, concrete plan
  (steps, assumptions, risks).
- CriticAgent: review a plan for safety, completeness, and sanity,
  and suggest improvements or escalation.

They are intentionally minimal in v1 — pure LLM wrappers with clear
roles and structured-but-freeform text outputs.
"""
from __future__ import annotations

from typing import Protocol

from hal.llm import VLLMClient
from hal.logging_utils import get_logger
from hal.tracing import get_tracer

log = get_logger(__name__)


class SubAgent(Protocol):
    """Minimal protocol for HAL sub-agents.

    Sub-agents have a name, a role description, and a run() method that
    returns a string given the operator's query and optional context.
    """

    name: str
    role_description: str

    def run(self, user_input: str, **kwargs) -> str:  # pragma: no cover - Protocol
        ...


PLANNER_SYSTEM_PROMPT = """You are HAL's Planner sub-agent.

You do not execute tools or run commands. Your job is to take the
operator's request and produce a short, concrete plan that HAL can
follow. Think like a senior SRE planning work for a reliable, safety-
critical homelab.

Keep the plan focused on the operator's actual goal. Prefer 3–7 steps
unless the task is truly large. Surface what you do *not* know.

Output format (plain text):

PLAN:
1. ...
2. ...
3. ...

ASSUMPTIONS:
- ...

RISKS:
- ...

If there is not enough information to plan safely, say so explicitly
in the RISKS section and note what is missing.
"""


CRITIC_SYSTEM_PROMPT = """You are HAL's Critic sub-agent.

You do not execute tools or run commands. Your job is to review the
Planner's plan for safety, completeness, and sanity. You think like a
cautious production reviewer: you look for missing checks, risky
shortcuts, and escalation points.

You are given:
- The operator's original query
- The Planner's proposed plan

Output format (plain text):

ISSUES:
- ...  (specific problems or concerns)

MISSING_CHECKS:
- ...  (tests, verifications, or safeguards that should be added)

RECOMMENDATIONS:
- ...  (concrete improvements, including when to escalate to the
         operator for confirmation)

If the plan is sound, say so explicitly in ISSUES and still list any
residual risks or uncertainties.
"""


class PlannerAgent:
    """Planner sub-agent: turn a query into a structured plan.

    This agent is tool-less. It only uses the chat model with a
    specialized system prompt.
    """

    name = "Planner"
    role_description = (
        "Turn an operator query into a short, concrete plan with steps, "
        "assumptions, and risks. Never executes tools; plans only."
    )

    def __init__(self, llm: VLLMClient) -> None:
        self._llm = llm

    def run(
        self,
        user_input: str,
        history: list[dict] | None = None,
        session_id: str | None = None,
    ) -> str:
        """Return a structured plan for the given user_input.

        history and session_id are accepted for future use (e.g. adding
        light conversational context or tracing), but are optional and
        may be None.
        """

        messages: list[dict] = []
        if history:
            # Keep any provided context in order, but do not mutate it.
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        with get_tracer().start_as_current_span("hal.subagent.planner") as span:
            span.set_attribute("subagent.name", self.name)
            span.set_attribute("subagent.role", self.role_description)
            span.set_attribute("subagent.input_len", len(user_input))
            if session_id is not None:
                span.set_attribute("hal.session_id", session_id)

            log.info("planner run", extra={"subagent": self.name})
            plan = self._llm.chat(messages, system=PLANNER_SYSTEM_PROMPT)
            plan = plan.strip()
            span.set_attribute("subagent.output_len", len(plan))

        return plan


class CriticAgent:
    """Critic sub-agent: review a plan for safety and completeness.

    This agent is also tool-less. It evaluates the Planner's output and
    suggests improvements or escalation points.
    """

    name = "Critic"
    role_description = (
        "Review the Planner's plan for safety, completeness, and sanity. "
        "Never executes tools; critiques only."
    )

    def __init__(self, llm: VLLMClient) -> None:
        self._llm = llm

    def run(
        self,
        user_input: str,
        plan: str,
        history: list[dict] | None = None,
        session_id: str | None = None,
    ) -> str:
        """Return a structured critique for the given plan.

        The user_input is the operator's original query; plan is the
        Planner's output.
        """

        # Build a single user message that includes both query and plan.
        critique_prompt = (
            "Operator query:\n" + user_input.strip() + "\n\n" +
            "Planner's plan:\n" + plan.strip()
        )

        messages: list[dict] = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": critique_prompt})

        with get_tracer().start_as_current_span("hal.subagent.critic") as span:
            span.set_attribute("subagent.name", self.name)
            span.set_attribute("subagent.role", self.role_description)
            span.set_attribute("subagent.input_len", len(critique_prompt))
            if session_id is not None:
                span.set_attribute("hal.session_id", session_id)

            log.info("critic run", extra={"subagent": self.name})
            critique = self._llm.chat(messages, system=CRITIC_SYSTEM_PROMPT)
            critique = critique.strip()
            span.set_attribute("subagent.output_len", len(critique))

        return critique
