# gsm-agent-simulated

An explicit development adapter with model identity `GSM Agent Kit / Simulated cellular device`.
It performs no hardware access, sends no messages and calls no external services.

It implements `device.status.read`. Availability is configurable;
unavailable status does not remove the capability.

Opt in with `SimulatedDevice(..., balance_enabled=True)` to additionally expose
`carrier.balance.read`. Its exclusive reservation rejects concurrent owners,
allows one consultation, and closes idempotently. Only the `simulated` carrier
policy is accepted; its response is clearly synthetic and supplies no numeric
credit or SMS allowance. The default device remains status-only.
In the server, set `GSM_DEVICE__SIMULATED_BALANCE_ENABLED=true` and
`GSM_BALANCE__CARRIER=simulated` for this hardware-free demonstration.

The server's `simulated` extra installs this adapter. See the server README
for a complete API demo. The adapter implements only core ports and has no
FastAPI, Dishka, Mediary or AI dependency.

`tests/test_contract.py` runs the [shared device contract suite](../../../standard-tests/README.md)
against ready, unavailable and optional-balance profiles. The suite inspects
balance support without reserving a session; adapter-specific tests exercise its
synthetic consultation and ownership behavior separately.
