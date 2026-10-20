CLI configuration, HTTP behavior and installed entry-point tests live here.
`test_backend_integration.py` runs the installed client against the real API,
DI, CQRS and SQLite stores with a simulated device on an ephemeral loopback port.
All configuration and message data are synthetic; the server is stopped at teardown.
