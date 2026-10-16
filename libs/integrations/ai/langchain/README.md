# gsm-agent-langchain

Implements the core `AIAgent` port using LangChain `create_agent` and the dedicated
`langchain-openrouter` integration. `invoke` returns a validated `ReplyDecision`;
`stream` yields the final structured decision, never raw tool arguments or
unvalidated text. Conversation persistence belongs to the application and its
SQLite adapter; the graph has no separate memory/checkpointer.

Configure model, key, instructions, token budget and timeout at construction.
The prompt requires plain, concise SMS, explains the absence of live news/search
tools, and reserves ignore for spam/automated notifications. The application
enforces transmitted length/encoding and removes Markdown even if the model
ignores the prompt. Choose an OpenRouter model supporting tool calling.

Uses `ToolStrategy` with structured-output retries disabled and provider
`max_retries=0`. Provider timeout units are milliseconds; the adapter also bounds
the whole invocation/stream and sanitizes exceptions. Cancellation propagates.
Default operation has no external tracing configured; explicitly enabled
LangChain/LangSmith tracing may export prompts and responses.

Tests run real agent graphs against an in-process fixture chat model, without
OpenRouter calls or credentials. References:
[ChatOpenRouter](https://reference.langchain.com/python/langchain-openrouter/langchain_openrouter),
[structured output](https://docs.langchain.com/oss/python/langchain/structured-output).

Python import: `gsm_agent_langchain`.
