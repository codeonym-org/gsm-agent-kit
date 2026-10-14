import ast
from pathlib import Path


def test_domain_and_application_do_not_import_adapters_or_frameworks():
    root = Path(__file__).resolve().parents[1] / "src" / "gsm_agent"
    for layer in ("domain", "application"):
        for path in (root / layer).rglob("*.py"):
            tree = ast.parse(path.read_text())
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
                elif isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
            for name in imports:
                assert not name.startswith(
                    ("gsm_agent.infra", "gsm_agent.di", "gsm_agent.api", "gsm_agent.runtime")
                )
                assert name.split(".")[0] not in {
                    "langchain",
                    "langchain_core",
                    "langgraph",
                    "fastapi",
                    "dishka",
                    "httpx",
                    "aiosqlite",
                }
                if layer == "domain":
                    assert not name.startswith(("mediary", "gsm_agent.application"))
