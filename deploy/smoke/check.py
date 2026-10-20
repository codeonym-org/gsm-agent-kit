"""Assertions run inside the isolated smoke network, using synthetic data only."""

import json
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "http://smoke-backend:8000"
FIXTURES = "http://smoke-fixtures:9000"
DEVICE = "/api/devices/smoke-device"


def request(path, data=None, *, fixtures=False, authenticated=True):
    headers = {"Content-Type": "application/json"}
    if authenticated and not fixtures:
        headers["Authorization"] = "Bearer smoke-only-token"
    req = Request(
        (FIXTURES if fixtures else API) + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers,
    )
    with urlopen(req, timeout=5) as response:
        return json.load(response)


def wait_for_jobs(expected):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        jobs = request(DEVICE + "/assistant/jobs")
        states = sorted(job["state"] for job in jobs)
        if states == sorted(expected):
            return jobs
        if any(state in {"failed", "interrupted"} for state in states):
            raise AssertionError(f"Reply did not complete: {states}")
        time.sleep(0.2)
    raise AssertionError("Timed out waiting for synthetic reply jobs")


def check_submissions(jobs):
    for job in jobs:
        if job["state"] != "completed":
            continue
        result = request(DEVICE + "/submissions/" + job["request_id"])
        assert result["complete"] and result["accepted_parts"] == 1
    effects = request("/effects", fixtures=True)
    assert all(body == "Hello! This is a synthetic SMS reply." for body in effects["outgoing"])
    return effects


def main(phase):
    assert request("/health")["adapter_profile"] == "zte-mf833t"
    assert request(DEVICE + "/status")["availability"] == "ready"
    status = request(DEVICE + "/assistant")
    assert status["auto_reply"] and status["dry_run"] == (phase == "dry-run")
    try:
        request("/api/adapters", authenticated=False)
        raise AssertionError("Protected API accepted an unauthenticated request")
    except HTTPError as exc:
        assert exc.code == 401

    if phase == "exercise":
        # Establish the empty inbox baseline through the real command endpoint.
        request(DEVICE + "/inbox/ingest", {})
        request("/incoming", {"body": "Hello from the synthetic SIM."}, fixtures=True)
        jobs = wait_for_jobs(["completed"])
        effects = check_submissions(jobs)
        assert len(effects["outgoing"]) == len(effects["histories"]) == 1
        assert len(request(DEVICE + "/messages")) == 1
    elif phase == "persist":
        # Backend AND fixture containers have been recreated with existing volumes.
        jobs = wait_for_jobs(["completed"])
        assert len(request(DEVICE + "/messages")) == 1
        effects = check_submissions(jobs)
        assert len(effects["outgoing"]) == len(effects["histories"]) == 1
        request("/incoming", {"body": "Do you remember our conversation?"}, fixtures=True)
        jobs = wait_for_jobs(["completed", "completed"])
        effects = check_submissions(jobs)
        assert len(effects["outgoing"]) == len(effects["histories"]) == 2
        assert any(message["role"] == "assistant" for message in effects["histories"][1])
    elif phase == "dry-run":
        request("/incoming", {"body": "This one must stay in dry-run."}, fixtures=True)
        jobs = wait_for_jobs(["completed", "completed", "dry_run"])
        effects = check_submissions(jobs)
        assert len(effects["outgoing"]) == 2 and len(effects["histories"]) == 3
        assert len(request(DEVICE + "/messages")) == 3
        # Several complete polls/drains must not re-enqueue or resubmit stored SMS.
        time.sleep(2)
        assert request("/effects", fixtures=True) == effects
    else:
        raise ValueError("Unknown smoke phase")
    print(f"PASS: {phase}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
