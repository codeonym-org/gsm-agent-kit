# gsm-agent-simulated

An explicit development adapter with model identity `GSM Agent Kit / Simulated cellular device`.
It performs no hardware access, sends no messages and calls no external services.

It currently implements `device.status.read`. Availability is configurable;
unavailable status does not remove the capability. Future SMS simulation will
arrive with the corresponding capability contracts.

The server's `simulated` extra installs this adapter. See the server README
for a complete API demo. The adapter implements only core ports and has no
FastAPI, Dishka, Mediary or AI dependency.
