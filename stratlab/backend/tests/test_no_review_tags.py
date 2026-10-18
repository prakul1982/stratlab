"""No review tag ("R45A-016") in text the app sends: they belong in comments and docstrings only (R56-002, R49-012)."""
import ast
import re
from pathlib import Path

TAG = re.compile(r"\bR\d+[A-Z]?-\d{3}\b")
APP = Path(__file__).resolve().parent.parent / "app"


def _docstrings(tree) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def test_no_review_tag_in_a_string_the_app_uses():
    found = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and TAG.search(node.value):
                found.append(f"{path.relative_to(APP)}:{node.lineno}: {node.value[:80]!r}")
    assert not found, "review tags in app strings:\n" + "\n".join(found)
