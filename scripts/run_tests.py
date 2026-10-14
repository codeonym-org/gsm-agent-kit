"""Run behavior tests; an empty skeleton suite is explicitly reported."""

import subprocess
import sys

result = subprocess.run([sys.executable, "-m", "pytest"], check=False)
if result.returncode == 5:
    print("No behavior tests exist yet; workspace and distribution checks run separately.")
    raise SystemExit(0)
raise SystemExit(result.returncode)
