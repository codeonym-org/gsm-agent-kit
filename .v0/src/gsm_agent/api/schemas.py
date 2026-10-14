from typing import Literal

from pydantic import BaseModel, Field

from gsm_agent.domain.agent import AgentInput, ChatMessage


class SendSmsBody(BaseModel):
    recipient: str
    text: str = Field(min_length=1, max_length=10000)


class ChatMessageBody(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str = Field(min_length=1, max_length=4000)


class AgentBody(BaseModel):
    messages: list[ChatMessageBody] = Field(min_length=1, max_length=20)

    def to_input(self) -> AgentInput:
        return AgentInput(tuple(ChatMessage(m.role, m.content) for m in self.messages))
