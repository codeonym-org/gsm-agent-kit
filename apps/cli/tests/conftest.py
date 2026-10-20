import os

import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(tmp_path, monkeypatch):
    # Never load repository secrets or inherit its runtime device configuration.
    monkeypatch.chdir(tmp_path)
    for key in tuple(os.environ):
        if key.startswith("GSM_"):
            monkeypatch.delenv(key)
