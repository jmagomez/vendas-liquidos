"""Smoke test: garante que todo o codigo Python compila sem erro de sintaxe."""
import pathlib
import py_compile

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCLUDE = {".git", "data", "docs", "output", ".venv", "venv", "env", "node_modules"}


def test_todo_python_compila():
    files = [p for p in ROOT.rglob("*.py") if not EXCLUDE & set(p.parts)]
    assert files, "nenhum arquivo .py encontrado"
    for f in files:
        py_compile.compile(str(f), doraise=True)
