"""Verify installed workspace packages and their declared local dependencies."""

import importlib
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    files = sorted([*ROOT.glob("libs/**/pyproject.toml"), *ROOT.glob("apps/*/pyproject.toml")])
    projects = {tomllib.loads(path.read_text())["project"]["name"]: path for path in files}
    assert len(projects) == len(files), "Duplicate distribution names"
    for name, path in projects.items():
        metadata = tomllib.loads(path.read_text())
        for module in (path.parent / "src").iterdir():
            if not module.is_dir():
                continue
            loaded = importlib.import_module(module.name)
            assert loaded.__file__ is not None
            assert Path(loaded.__file__).resolve().is_relative_to(module.resolve()), name
            assert (module / "py.typed").is_file(), name
        for dependency, source in metadata.get("tool", {}).get("uv", {}).get("sources", {}).items():
            if source.get("workspace"):
                assert dependency in projects, f"Missing workspace dependency {dependency}"
        assert metadata["project"]["license"] == "LicenseRef-Proprietary", name
    print(f"Verified {len(projects)} workspace packages")


if __name__ == "__main__":
    main()
