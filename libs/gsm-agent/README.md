# gsm-agent

Reusable application workflows and CQRS handlers.

The initial use cases are `ListAdapters`, `ListDevices`, `GetDevice` and
`GetDeviceStatus`. All are Mediary queries dispatched through `QuerySender`;
none are commands. Reads use an application-owned device-directory port and
the core cellular-device capability ports.

Description and status queries have a bounded budget, with separate unknown
device, unsupported capability and deadline errors. Concrete directories,
device lifecycle and transport error mapping live in the server or adapters.
SMS workflows, persistence and AI orchestration follow in separate tickets.

Python import: `gsm_agent`.
