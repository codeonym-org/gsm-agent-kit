# SMS assistant

Compose the ZTE MF833T HTTP adapter, SQLite inbox/submission/conversation stores,
and the LangChain/OpenRouter agent in the server.

From the repository root, copy [.env.example](.env.example) to `.env`, set your
OpenRouter key, and enable `GSM_ASSISTANT__ENABLED`. Then run:

```bash
uv run --package gsm-agent-server --extra zte-mf833t --extra inbox --extra sms --extra ai gsm-agent-server
```

The example starts with dry-run enabled and submission disabled. It generates
model replies but spends no SMS credit. Inspect
`GET /api/devices/zte-device/assistant` and `/api/devices/zte-device/assistant/jobs`.
The first inbox scan baselines existing messages; only new complete messages
after that scan trigger replies. Set an explicit country region to accept
national sender numbers.

For live SMS replies, enable submissions and turn off assistant dry-run, then
restart. See the [server README](../../apps/server/README.md#sms-assistant) for
configuration, state/recovery semantics and conversation retention.

Tests use fixture devices and models; no live SMS or paid model calls are part
of the default checks. Keep local databases and keys out of commits and reports.
