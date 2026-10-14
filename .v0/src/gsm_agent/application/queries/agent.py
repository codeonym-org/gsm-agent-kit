from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass

from mediary.cqrs import Query, StreamQuery, query, query_handler, stream_query, stream_query_handler

from gsm_agent.application.ports.ai_agent import AIAgent
from gsm_agent.domain.agent import AgentInput, AgentStreamEvent, ReplyDecision


@query
@dataclass(frozen=True)
class InvokeAgent(Query[ReplyDecision]):
    request: AgentInput


@query_handler
class InvokeAgentHandler:
    def __init__(self, agent: AIAgent):
        self.agent = agent

    async def handle(self, query: InvokeAgent) -> ReplyDecision:
        return await self.agent.invoke(query.request)


@stream_query
@dataclass(frozen=True)
class StreamAgent(StreamQuery[AgentStreamEvent]):
    request: AgentInput


@stream_query_handler
class StreamAgentHandler:
    def __init__(self, agent: AIAgent):
        self.agent = agent

    async def handle(self, query: StreamAgent) -> AsyncIterator[AgentStreamEvent]:
        async with aclosing(self.agent.stream(query.request)) as events:
            async for event in events:
                yield event
