"""Run the host helper against a fake nmcli executable; never touch host networking."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "deploy/host/network-manager.sh"
UUID = "00000000-0000-0000-0000-000000000001"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="Host helper requires bash")
FAKE_NMCLI = r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
path = Path(os.environ["NM_TEST_STATE"])
state = json.loads(path.read_text())
args = sys.argv[3:]
if args[:2] == ["-g", "connection.type"]:
    print(state["type"])
elif args[:2] == ["-g", "GENERAL.DEVICES"]:
    print(state["device"])
elif args[0] == "-f":
    print("Synthetic profile settings")
elif args[:2] == ["connection", "modify"]:
    assert args[2:4] == ["uuid", "00000000-0000-0000-0000-000000000001"]
    state["settings"].update(zip(args[4::2], args[5::2]))
    state["writes"] += 1
    path.write_text(json.dumps(state))
elif args[:2] == ["device", "reapply"]:
    assert args[2] == state["device"]
    state["reapplies"] += 1
    path.write_text(json.dumps(state))
    sys.exit(state.get("reapply_exit", 0))
else:
    raise AssertionError(args)
"""


@pytest.fixture
def network(tmp_path):
    binary = tmp_path / "nmcli"
    # Use the same interpreter as the test, including on Windows with Git Bash.
    import sys

    if os.name == "nt":
        pytest.skip("NetworkManager host helper is Linux-specific")
    binary.write_text(FAKE_NMCLI.replace("/usr/bin/env python3", sys.executable))
    binary.chmod(0o700)
    state_path = tmp_path / "state.json"
    initial = {
        "type": "802-3-ethernet",
        "device": "usb-test",
        "writes": 0,
        "reapplies": 0,
        "settings": {"ipv4.dns": "192.0.2.1", "ipv4.addresses": "192.0.2.2/24"},
    }

    def run(mode, *, dry_run=False, **overrides):
        state_path.write_text(json.dumps({**initial, **overrides}))
        result = subprocess.run(
            ["bash", str(SCRIPT), mode, UUID, *(["--dry-run"] if dry_run else [])],
            env={
                **os.environ,
                "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
                "NM_TEST_STATE": str(state_path),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        return result, json.loads(state_path.read_text())

    return run


def test_fallback_retains_default_routes_and_reset_returns_automatic_settings(network):
    result, state = network("fallback-modem")
    assert result.returncode == 0, result.stderr
    assert state["writes"] == state["reapplies"] == 1
    for family in ("ipv4", "ipv6"):
        assert state["settings"][family + ".never-default"] == "no"
        assert state["settings"][family + ".route-metric"] == "1000"
        assert state["settings"][family + ".dns-priority"] == "1000"
    assert state["settings"]["ipv4.dns"] == "192.0.2.1"
    assert state["settings"]["ipv4.addresses"] == "192.0.2.2/24"
    result, state = network("reset", settings=state["settings"])
    assert result.returncode == 0, result.stderr
    assert state["settings"]["ipv4.route-metric"] == state["settings"]["ipv6.route-metric"] == "-1"
    assert state["settings"]["ipv4.dns-priority"] == state["settings"]["ipv6.dns-priority"] == "0"


def test_dry_run_and_wrong_profile_never_modify_network_settings(network):
    result, state = network("fallback-modem", dry_run=True)
    assert result.returncode == 0 and "Would run:" in result.stdout
    assert state["writes"] == state["reapplies"] == 0
    result, state = network("fallback-modem", type="802-11-wireless")
    assert result.returncode == 2 and "refusing" in result.stderr
    assert state["writes"] == state["reapplies"] == 0


def test_inactive_profiles_stay_inactive_and_reapply_failure_is_visible(network):
    result, state = network("fallback-modem", device="--")
    assert result.returncode == 0 and state["writes"] == 1 and state["reapplies"] == 0
    result, state = network("fallback-modem", reapply_exit=1)
    assert result.returncode == 1 and "live reapply failed" in result.stderr
    assert state["writes"] == state["reapplies"] == 1
