Behavior tests cover API authentication, capability dispatch, CQRS semantics,
durable inbox/submission workflows and persistent AI replies. HTTP device
fixtures and an injected AI port avoid hardware and paid provider calls.
Assistant tests include background polling, dry-run, ignore, provider errors,
bounded output, scoped history, cancellation and restart reconciliation.
Balance tests use the real query/DI/HTTP path with a synthetic capability and
owned-session fixtures: raw/parsed observations, unsupported ZTE with zero I/O,
foreign-session busy, acquisition/response/cleanup deadlines and cancellation.
