from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Literal

from langchain.agents import create_agent
from langchain_openrouter import ChatOpenRouter
from pydantic import BaseModel, Field

from gsm_agent.application.ports.text_normalizer import TextNormalizer
from gsm_agent.domain.agent import AgentInput, AgentStreamEvent, ReplyDecision, require_answer
from gsm_agent.domain.errors import AgentUnavailableError
from gsm_agent.domain.sms_text import ReplyLimits, plan_sms


class SmsReplySchema(BaseModel):
    """Structured output used only at the framework boundary."""

    action: Literal["reply", "ignore"] = Field(description="Reply to the sender, or ignore unsolicited spam")
    text: str = Field(
        description="Concise plain SMS text; empty for ignore. No Markdown styling or emoji.",
    )
    ignore_reason: (
        Literal["spam", "automated_notification", "unavailable_information", "unsupported_request"] | None
    ) = Field(
        default=None,
        description="Required explanation for ignore. Use spam/automated_notification only for unsolicited "
        "or machine-generated notifications, never for a human question. Use null for reply.",
    )


class LangChainAgent:
    def __init__(
        self,
        *,
        model: str,
        instructions: str,
        timeout: float = 60,
        api_key: str | None = None,
        base_url: str | None = None,
        normalizer: TextNormalizer,
        limits: ReplyLimits,
        max_output_tokens: int = 384,
    ):
        self.model = model
        self.instructions = instructions
        self.timeout = timeout
        self.api_key = api_key
        self.base_url = base_url
        self.normalizer = normalizer
        self.limits = limits
        self.max_output_tokens = max_output_tokens
        self._graph = None

    def _agent(self):
        # Lazy construction lets the modem/API start without AI credentials.
        if self._graph is None:
            # ChatOpenRouter uses milliseconds; runtime settings use seconds.
            kwargs: dict = {
                "timeout": max(1, int(self.timeout * 1000)),
                "max_retries": 1,
                "max_tokens": self.max_output_tokens,
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
            chat = ChatOpenRouter(model=self.model, **kwargs)
            unicode_budget = min(
                self.limits.max_reply_chars,
                70 if self.limits.max_sms_parts == 1 else 64 * self.limits.max_sms_parts,
            )
            instructions = self.instructions + (
                "\nSMS output requirements: NEVER use Markdown styling; output regular text only. "
                f"Keep reply text under {self.limits.max_reply_chars} characters. "
                f"For Arabic or other Unicode text, aim under {unicode_budget} "
                f"characters. The total budget is {self.limits.max_sms_parts} SMS messages. "
                "Answer the main point first. Do not add message numbering; the application does that."
                " Always reply to genuine questions, including requests for latest news or information "
                "you cannot access. Explain the limitation; do not fabricate current facts. "
                "Use ignore only for actual spam or automated notifications and specify ignore_reason. "
                "Lack of knowledge, unsupported requests, and lack of live search "
                "are never reasons for silence."
            )
            self._graph = create_agent(
                model=chat, tools=[], system_prompt=instructions, response_format=SmsReplySchema
            )
        return self._graph

    @staticmethod
    def _input(request: AgentInput) -> dict:
        return {"messages": [{"role": m.role, "content": m.content} for m in request.messages]}

    def _decision(self, value: object) -> ReplyDecision:
        schema = value if isinstance(value, SmsReplySchema) else SmsReplySchema.model_validate(value)
        decision = require_answer(
            ReplyDecision(
                schema.action, schema.text, schema.ignore_reason if schema.action == "ignore" else None
            )
        )
        if decision.action == "ignore":
            return decision
        plan = plan_sms(self.normalizer.normalize(decision.text), self.limits)
        return ReplyDecision("reply", plan.text)

    @staticmethod
    def _config(request: AgentInput) -> dict:
        config: dict = {"recursion_limit": 10}
        if request.thread_id is not None:
            config["configurable"] = {"thread_id": request.thread_id}
        return config

    async def invoke(self, request: AgentInput) -> ReplyDecision:
        try:
            state = await self._agent().ainvoke(self._input(request), config=self._config(request))
            return self._decision(state["structured_response"])
        except Exception as exc:
            raise AgentUnavailableError("AI agent could not produce a reply") from exc

    async def stream(self, request: AgentInput) -> AsyncIterator[AgentStreamEvent]:
        try:
            decision = None
            # Values carry the validated schema; messages carry optional text previews.
            # Structured providers may emit tool arguments instead of text; the final
            # result is always emitted even if there are no text fragments.
            source = self._agent().astream(
                self._input(request), config=self._config(request), stream_mode=["messages", "values"]
            )
            async with aclosing(source) as events:
                async for mode, payload in events:
                    if mode == "messages":
                        chunk, _metadata = payload
                        content = chunk.content
                        if isinstance(content, str) and content:
                            yield AgentStreamEvent("text", text=content)
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text")
                                    if isinstance(text, str) and text:
                                        yield AgentStreamEvent("text", text=text)
                    elif mode == "values" and payload.get("structured_response") is not None:
                        decision = self._decision(payload["structured_response"])
            if decision is None:
                raise ValueError("Stream ended without structured output")
            yield AgentStreamEvent("result", result=decision)
        except Exception as exc:
            raise AgentUnavailableError("AI agent stream failed") from exc
