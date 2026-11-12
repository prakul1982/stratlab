"""The repository's own build files: the GitHub workflows and the backend image. Each workflow step that runs someone else's
action names the exact commit it runs (the release tag beside it as a comment), and each workflow says what its token may do."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$")


def _top_level(text: str, key: str) -> list[str] | None:
    """The lines of a top-level YAML key: its own line, then the indented lines under it (None when absent)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}:", line):
            block = [line]
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.startswith((" ", "#")):
                    break
                block.append(nxt)
            return block
    return None


def test_the_workflows_are_found():
    assert {p.name for p in WORKFLOWS} >= {"tests.yml", "claude.yml"}


def test_every_action_is_pinned_to_a_commit_with_its_release_beside_it():
    seen = 0
    for path in WORKFLOWS:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            m = USES.match(line)
            if not m:
                continue
            ref, rest = m.groups()
            if ref.startswith("./") or ref.startswith("docker://"):
                continue
            seen += 1
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{path.name}:{n} {ref}"
            assert re.fullmatch(r"\s+# v\d+\.\d+\.\d+", rest), f"{path.name}:{n} needs '# vX.Y.Z' after the commit"
    assert seen >= 10


def test_every_workflow_sets_its_token_permissions():
    for path in WORKFLOWS:
        block = _top_level(path.read_text(), "permissions")
        assert block, f"{path.name}: no top-level permissions"
        head = block[0].split("#")[0].strip()
        if head == "permissions: {}":
            continue
        assert head == "permissions:", f"{path.name}: {head}"
        grants = [ln.split("#")[0].strip() for ln in block[1:] if ln.split("#")[0].strip()]
        assert grants, f"{path.name}: empty permissions block"
        for g in grants:
            assert re.fullmatch(r"[a-z-]+: (read|none)", g), f"{path.name}: top-level grants only read ({g})"
