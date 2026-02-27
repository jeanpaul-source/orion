"""Unit tests for PlannerAgent and CriticAgent (hal/agents.py).

These tests mock VLLMClient so no real LLM calls are made. They verify
that the sub-agents:

- Use the correct system prompts
- Pass the operator query (and plan) into the user message
- Return the underlying LLM response text unchanged
"""

from __future__ import annotations

from unittest.mock import MagicMock

from hal._unlocked.agents import (
    CRITIC_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    CriticAgent,
    PlannerAgent,
)


def test_planner_uses_system_prompt_and_returns_text() -> None:
    """PlannerAgent should call LLM.chat with its system prompt and
    include the user input in the user message.
    """

    mock_llm = MagicMock()
    mock_response = (
        "PLAN:\n1. Do the thing.\n\nASSUMPTIONS:\n- none.\n\nRISKS:\n- minimal."
    )
    mock_llm.chat.return_value = mock_response

    agent = PlannerAgent(mock_llm)
    result = agent.run(user_input="set up backups for the lab server")

    # Returned text should match the LLM output (minus any internal stripping).
    assert result == mock_response

    # LLM.chat should have been called exactly once with the planner system prompt.
    mock_llm.chat.assert_called_once()
    (messages,) = mock_llm.chat.call_args[0]
    system = mock_llm.chat.call_args[1].get("system")

    assert system == PLANNER_SYSTEM_PROMPT

    user_msgs = [m for m in messages if m.get("role") == "user"]
    assert len(user_msgs) == 1
    assert "set up backups for the lab server" in user_msgs[0].get("content", "")


def test_critic_receives_plan_and_query_in_prompt() -> None:
    """CriticAgent should see both the original query and the plan in
    the user message it sends to the LLM.
    """

    mock_llm = MagicMock()
    mock_response = "ISSUES:\n- none.\n\nMISSING_CHECKS:\n- verify once more.\n\nRECOMMENDATIONS:\n- proceed with caution."
    mock_llm.chat.return_value = mock_response

    agent = CriticAgent(mock_llm)
    query = "deploy a new version of the monitoring stack"
    plan = "PLAN:\n1. Build images.\n2. Deploy to staging.\n3. Roll out to production."

    result = agent.run(user_input=query, plan=plan)

    assert result == mock_response

    mock_llm.chat.assert_called_once()
    (messages,) = mock_llm.chat.call_args[0]
    system = mock_llm.chat.call_args[1].get("system")

    assert system == CRITIC_SYSTEM_PROMPT

    user_msgs = [m for m in messages if m.get("role") == "user"]
    assert len(user_msgs) == 1
    content = user_msgs[0].get("content", "")

    # The critic prompt should include both the original query and the plan text.
    assert "deploy a new version of the monitoring stack" in content
    assert "PLAN:" in content
    assert "1. Build images." in content
