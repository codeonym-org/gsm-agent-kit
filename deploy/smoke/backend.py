"""Smoke-only AI adapter; production transports and workflows remain unchanged."""

from collections.abc import AsyncIterator
from dataclasses import asdict

import httpx
from dishka import Provider, Scope, provide
from gsm_agent_core.ai import AIAgent
from gsm_agent_core.domain.agent import AgentInput, ReplyDecision
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import Settings


class FixtureAgent:
    async def invoke(self, request: AgentInput) -> ReplyDecision:
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            response = await client.post("http://smoke-fixtures:9000/agent", json=asdict(request))
            response.raise_for_status()
            return ReplyDecision(**response.json())

    async def stream(self, request: AgentInput) -> AsyncIterator[ReplyDecision]:
        yield await self.invoke(request)


class FixtureAIProvider(Provider):
    @provide(scope=Scope.APP, override=True)
    def ai_agent(self) -> AIAgent:
        return FixtureAgent()


def create_smoke_app():
    # No root .env, provider keys, paid AI, or real cellular device in this target.
    return create_app(Settings(_env_file=None), FixtureAIProvider())
