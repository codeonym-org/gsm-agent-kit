"""Exercise real create_agent graphs with an in-process chat model, without API calls."""

import asyncio

import pytest
from gsm_agent_core.ai import AgentUnavailableError
from gsm_agent_core.domain.agent import AgentInput, ChatMessage, ReplyDecision
from gsm_agent_langchain import LangChainAgent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class FixtureModel(BaseChatModel):
    payload: dict
    delay: bool = False
    _inputs: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "fixture"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._inputs.append(messages)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[{"name": "ReplySchema", "args": self.payload, "id": "fixture-call"}],
                    )
                )
            ]
        )

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.delay:
            await asyncio.Event().wait()
        return self._generate(messages, **kwargs)


def adapter(monkeypatch, payload, **kwargs):
    model = FixtureModel(payload=payload)
    options = {}

    def chat(**config):
        options.update(config)
        return model

    monkeypatch.setattr("gsm_agent_langchain.agent.ChatOpenRouter", chat)
    agent = LangChainAgent(
        model="fixture/model", api_key="fictional-key", instructions="Be helpful.", **kwargs
    )
    return agent, model, options


REQUEST = AgentInput("opaque-thread", (ChatMessage("user", "What is the latest news?"),))


async def test_invoke_and_stream_use_structured_create_agent_and_plain_text_prompt(monkeypatch):
    expected = ReplyDecision("reply", "I cannot access live news.")
    agent, model, options = adapter(monkeypatch, {"action": "reply", "text": expected.text})
    assert await agent.invoke(REQUEST) == expected
    assert [decision async for decision in agent.stream(REQUEST)] == [expected]
    assert options["max_retries"] == 0 and options["max_tokens"] == 384 and options["timeout"] == 60000
    assert options["api_key"].get_secret_value() == "fictional-key"
    prompt = model._inputs[0][0].content
    assert "NEVER use Markdown" in prompt and "no live search" in prompt and "240 characters" in prompt
    assert "Always reply to human questions" in prompt


async def test_ignore_is_explicit_and_invalid_decisions_are_sanitized(monkeypatch):
    agent, _, _ = adapter(monkeypatch, {"action": "ignore", "text": "", "ignore_reason": "spam"})
    assert await agent.invoke(REQUEST) == ReplyDecision("ignore", ignore_reason="spam")
    agent, _, _ = adapter(monkeypatch, {"action": "reply", "text": "", "private": "secret provider data"})
    with pytest.raises(AgentUnavailableError) as failure:
        await agent.invoke(REQUEST)
    assert str(failure.value) == "AI agent could not produce a decision"
    assert failure.value.__cause__ is None and failure.value.__suppress_context__


async def test_deadline_and_cancellation_propagation(monkeypatch):
    agent, model, _ = adapter(monkeypatch, {"action": "reply", "text": "Hello"}, timeout_seconds=0.02)
    model.delay = True
    with pytest.raises(AgentUnavailableError):
        await agent.invoke(REQUEST)
    task = asyncio.create_task(agent.invoke(REQUEST))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
