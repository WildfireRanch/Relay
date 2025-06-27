import pytest
from unittest.mock import AsyncMock, patch
from agents import planner_agent
from llama_index.core.settings import Settings
Settings.llm = None

@pytest.mark.asyncio
async def test_critic_fallback_on_invalid_gpt_label(monkeypatch):
    user_id = "test-user"
    query = "please banana my system"

    # Mock ContextEngine
    monkeypatch.setattr(
        planner_agent,
        "ContextEngine",
        lambda user_id: type("MockEngine", (), {
            "build_context": lambda self, q, **kwargs: {"prompt": "", "files_used": []}
        })("")
    )

    # Mock GPT classification to return invalid label
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value.choices = [
        type("Choice", (), {"message": type("Message", (), {"content": "banana"})})()
    ]
    monkeypatch.setattr(planner_agent, "AsyncOpenAI", lambda api_key: mock_client)

    # Mock echo agent response
    monkeypatch.setattr(planner_agent.echo_agent, "handle", AsyncMock(return_value={"response": "[echoed]"}))

    # Mock critic agent
    monkeypatch.setattr(planner_agent, "critic_agent", __import__("agents.critic_agent"))
    monkeypatch.setattr(planner_agent.critic_agent, "handle_routing_error", AsyncMock(return_value={
        "response": "[critic detected banana]",
        "action": None
    }))

    result = await planner_agent.handle_query(user_id, query)

    assert "banana" not in result["response"]  # it was rewritten
    assert "[critic detected banana]" in result["response"]
    assert "[echoed]" in result["response"]
