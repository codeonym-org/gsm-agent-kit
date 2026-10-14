import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from gsm_agent.domain.agent import AgentInput, ChatMessage, ReplyDecision
from gsm_agent.domain.errors import AgentUnavailableError
from gsm_agent.domain.sms_text import ReplyLimits
from gsm_agent.infra.ai import langchain_agent
from gsm_agent.infra.text.plain_text import PlainTextNormalizer


class StructuredModel(BaseChatModel):
    """A tool-calling model that runs through the real create_agent graph."""

    reply_text: str = "Hello"
    action: str = "reply"
    ignore_reason: str | None = None

    @property
    def _llm_type(self):
        return "test-structured-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "SmsReplySchema",
                    "args": {
                        "action": self.action,
                        "text": self.reply_text,
                        "ignore_reason": self.ignore_reason,
                    },
                    "id": "reply-1",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


async def test_real_create_agent_structured_invoke_and_stream(monkeypatch):
    captured = []

    def model_factory(**kwargs):
        captured.append(kwargs)
        return StructuredModel()

    monkeypatch.setattr(langchain_agent, "ChatOpenRouter", model_factory)
    agent = langchain_agent.LangChainAgent(
        model="openai/gpt-4.1-mini",
        instructions="Be concise",
        timeout=12.5,
        api_key="test-key",
        normalizer=PlainTextNormalizer(),
        limits=ReplyLimits(),
        max_output_tokens=192,
    )
    request = AgentInput((ChatMessage("user", "hello"),))
    assert await agent.invoke(request) == ReplyDecision("reply", "Hello")
    events = [event async for event in agent.stream(request)]
    assert events[-1].kind == "result"
    assert events[-1].result == ReplyDecision("reply", "Hello")
    assert sum(event.kind == "result" for event in events) == 1
    assert captured == [
        {
            "model": "openai/gpt-4.1-mini",
            "timeout": 12500,
            "max_retries": 1,
            "api_key": "test-key",
            "max_tokens": 192,
        }
    ]


async def test_adapter_sanitizes_provider_error(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("secret provider details")

    monkeypatch.setattr(langchain_agent, "ChatOpenRouter", unavailable)
    agent = langchain_agent.LangChainAgent(
        model="test", instructions="Be concise", normalizer=PlainTextNormalizer(), limits=ReplyLimits()
    )
    with pytest.raises(AgentUnavailableError, match="could not produce"):
        await agent.invoke(AgentInput((ChatMessage("user", "hello"),)))


async def test_unexplained_ignore_of_news_question_returns_reply(monkeypatch):
    # Replay the decision recorded for the user's unanswered question.
    monkeypatch.setattr(
        langchain_agent, "ChatOpenRouter", lambda **kw: StructuredModel(action="ignore", reply_text="")
    )
    agent = langchain_agent.LangChainAgent(
        model="test", instructions="Be concise", normalizer=PlainTextNormalizer(), limits=ReplyLimits()
    )
    decision = await agent.invoke(AgentInput((ChatMessage("user", "What are the latest news?"),)))
    assert decision.action == "reply"
    assert decision.text.strip()


@pytest.mark.parametrize("reason", [None, "unavailable_information", "unsupported_request"])
async def test_non_spam_ignore_returns_reply_in_invoke_and_stream(monkeypatch, reason):
    monkeypatch.setattr(
        langchain_agent,
        "ChatOpenRouter",
        lambda **kw: StructuredModel(action="ignore", reply_text="", ignore_reason=reason),
    )
    agent = langchain_agent.LangChainAgent(
        model="test",
        instructions="Custom instructions",
        normalizer=PlainTextNormalizer(),
        limits=ReplyLimits(),
    )
    request = AgentInput((ChatMessage("user", "What are the latest news?"),))
    decision = await agent.invoke(request)
    events = [event async for event in agent.stream(request)]
    assert decision.action == "reply"
    assert events[-1].result == decision
    if reason == "unavailable_information":
        assert "live news" in decision.text


async def test_explicit_spam_remains_ignored(monkeypatch):
    monkeypatch.setattr(
        langchain_agent,
        "ChatOpenRouter",
        lambda **kw: StructuredModel(action="ignore", reply_text="", ignore_reason="spam"),
    )
    agent = langchain_agent.LangChainAgent(
        model="test", instructions="Be concise", normalizer=PlainTextNormalizer(), limits=ReplyLimits()
    )
    result = await agent.invoke(AgentInput((ChatMessage("user", "Advertisement"),)))
    assert result == ReplyDecision("ignore", "", ignore_reason="spam")


async def test_model_markdown_overshoot_is_normalized_and_capped_invoke_and_stream(monkeypatch):
    monkeypatch.setattr(
        langchain_agent, "ChatOpenRouter", lambda **kw: StructuredModel(reply_text="**مرحبا** 😀 " * 100)
    )
    limits = ReplyLimits(max_reply_chars=200, max_sms_parts=2)
    agent = langchain_agent.LangChainAgent(
        model="test", instructions="Custom user instructions", normalizer=PlainTextNormalizer(), limits=limits
    )
    request = AgentInput((ChatMessage("user", "hello"),), thread_id="+212600000000")
    decision = await agent.invoke(request)
    events = [event async for event in agent.stream(request)]
    assert events[-1].result == decision
    assert "**" not in decision.text and "😀" not in decision.text
    assert len(decision.text) <= limits.max_reply_chars
    assert decision.text.endswith("...")
