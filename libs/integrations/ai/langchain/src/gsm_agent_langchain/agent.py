"""OpenRouter implementation; framework types stop at this package boundary."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from typing import Any, Literal, cast

from gsm_agent_core.ai import AgentUnavailableError
from gsm_agent_core.domain.agent import AgentInput, ReplyDecision
from langchain.agents import create_agent
from langchain.agents.middleware.types import InputAgentState
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openrouter import ChatOpenRouter
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ReplySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["reply", "ignore"]
    text: str = Field(max_length=10000, description="Plain concise SMS text; empty for ignore")
    ignore_reason: Literal["spam", "automated_notification"] | None = None


class LangChainAgent:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        instructions: str,
        max_output_tokens: int = 384,
        max_total_chars: int = 240,
        max_parts: int = 3,
        timeout_seconds: float = 60,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        prompt = instructions + (
            "\nYou are an SMS assistant. NEVER use Markdown, HTML, styling, or emoji. Use plain text. "
            f"Answer the main point first, within {max_total_chars} characters and {max_parts} SMS parts. "
            "Do not number parts; the application handles splitting. "
            "You have no live search, news, browsing, or device-control tools. Never invent current facts "
            "or claim to have sent, delivered, purchased, activated, or checked anything. "
            "Always reply to human questions, including requests for latest news: explain the limitation "
            "when you lack access. Ignore only spam or automated notifications, with an ignore reason. "
            "Previous assistant messages are text accepted for submission, not proof of delivery."
        )
        chat = ChatOpenRouter(
            model=model,
            api_key=SecretStr(api_key),
            max_tokens=max_output_tokens,
            timeout=max(1, int(timeout_seconds * 1000)),
            max_retries=0,
        )
        self._graph = create_agent(
            model=chat,
            tools=[],
            system_prompt=prompt,
            response_format=ToolStrategy(ReplySchema, handle_errors=False),
        )

    @staticmethod
    def _input(request: AgentInput) -> InputAgentState:
        return {
            "messages": [
                HumanMessage(msg.content) if msg.role == "user" else AIMessage(msg.content)
                for msg in request.messages
            ]
        }

    @staticmethod
    def _config(request: AgentInput) -> RunnableConfig:
        # Application-owned history is the source of truth; no framework checkpointer.
        return {"recursion_limit": 4, "configurable": {"thread_id": request.thread_id}}

    @staticmethod
    def _decision(value: object) -> ReplyDecision:
        schema = ReplySchema.model_validate(value)
        return ReplyDecision(schema.action, schema.text, schema.ignore_reason)

    async def invoke(self, request: AgentInput) -> ReplyDecision:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                state = await self._graph.ainvoke(self._input(request), config=self._config(request))
                return self._decision(state["structured_response"])
        except Exception:
            raise AgentUnavailableError("AI agent could not produce a decision") from None

    async def stream(self, request: AgentInput) -> AsyncIterator[ReplyDecision]:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                decision = None
                source = cast(
                    AsyncGenerator[dict[str, Any], None],
                    self._graph.astream(
                        self._input(request), config=self._config(request), stream_mode="values"
                    ),
                )
                async with aclosing(source) as values:
                    async for state in values:
                        if "structured_response" in state:
                            decision = self._decision(state["structured_response"])
                if decision is None:
                    raise ValueError("Missing structured decision")
                yield decision
        except Exception:
            raise AgentUnavailableError("AI agent could not produce a decision") from None
