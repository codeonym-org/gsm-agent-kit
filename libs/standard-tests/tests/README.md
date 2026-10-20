`test_device_suite.py` injects broken cellular-device implementations into the
exported contract tests. It covers missing/undeclared/wrong ports, noncanonical
keys, descriptor mismatches, identity/support mutation, foreign inbox sources,
vendor payloads, evidence provenance/coverage and skip behavior. Trap methods
fail if the suite attempts SMS submission or carrier reservation.

The shared suite is also collected normally against simulated and fixture-backed
ZTE devices in each adapter's `tests/test_contract.py`. All data is synthetic;
no environment file, hardware, carrier session or paid AI service is used.
