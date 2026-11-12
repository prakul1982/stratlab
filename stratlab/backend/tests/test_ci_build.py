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


def _run_blocks(text: str) -> list[str]:
    """Every shell `run:` step's script (one-line or block)."""
    lines, out = text.splitlines(), []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", line)
        if not m:
            continue
        indent, first = len(m.group(1)), m.group(2)
        body = [first]
        if first.strip() in ("|", ">", "|-", ">-"):
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                body.append(nxt)
        out.append("\n".join(body))
    return out


# text anyone can write: issue and pull request titles and bodies, comments, reviews, branch names, commit messages
FREE_TEXT = re.compile(
    r"\$\{\{[^}]*github\.(?:event\.(?:issue|comment|review|pull_request|head_commit|commits|discussion)"
    r"[^}]*\.(?:title|body|message|name|label|ref)|head_ref)[^}]*\}\}"
)


def test_no_shell_step_reads_text_from_an_issue_or_comment():
    runs = 0
    for path in WORKFLOWS:
        for block in _run_blocks(path.read_text()):
            runs += 1
            assert not FREE_TEXT.search(block), f"{path.name}: pass it through env instead:\n{block}"
    assert runs >= 5
    # the check itself catches the shape it is for
    assert FREE_TEXT.search("echo ${{ github.event.issue.title }}")
    assert FREE_TEXT.search("echo ${{ github.event.comment.body }}")
    assert FREE_TEXT.search("git checkout ${{ github.head_ref }}")
    assert not FREE_TEXT.search("npm run e2e -- --shard=${{ matrix.shard }}/6")


def test_the_builder_starts_only_for_the_owner_on_a_trusted_thread():
    text = (ROOT / ".github" / "workflows" / "claude.yml").read_text()
    m = re.search(r"\n    if: >-\n((?:      .*\n)+)", text)
    assert m, "the builder job has an if"
    cond = " ".join(m.group(1).split())
    assert cond.startswith("github.actor == github.repository_owner && (")
    # each event: whoever wrote the text is the owner, and the thread was opened by the owner or a collaborator
    assert "github.event_name == 'issues' && github.event.issue.user.login == github.repository_owner &&" in cond
    for event, thread in (("issue_comment", "issue"), ("pull_request_review_comment", "pull_request")):
        assert (f"github.event_name == '{event}' && github.event.comment.user.login == github.repository_owner && "
                f"contains(fromJSON('[\"OWNER\",\"MEMBER\",\"COLLABORATOR\"]'), github.event.{thread}.author_association)"
                ) in cond, event
    assert "github.event_name != " not in cond, "every event is named, so a new one starts nothing by default"
    # the events the workflow listens to are exactly the ones the condition names
    on = _top_level(text, "on")
    assert sorted(re.findall(r"^  ([a-z_]+):", "\n".join(on), re.M)) == ["issue_comment", "issues", "pull_request_review_comment"]
    # Claude reads the owner's comments and apps' only
    assert 'include_comments_by_actor: "${{ github.repository_owner }},*[bot]"' in text
    # and the action keeps its own default checks: no non-write users, no bots allowed in
    assert "allowed_non_write_users" not in text and "allowed_bots" not in text


def test_the_backend_image_runs_as_an_unprivileged_user():
    lines = [ln.strip() for ln in (ROOT / "stratlab" / "backend" / "Dockerfile").read_text().splitlines()]
    steps = [ln for ln in lines if ln and not ln.startswith("#")]
    users = [i for i, ln in enumerate(steps) if ln.startswith("USER ")]
    assert users, "the image names the user it runs as"
    last = steps[users[-1]].split()[1]
    assert last.split(":")[0] not in ("root", "0"), last
    # it switches after everything that installs or copies, so the code and the packages stay root's
    installs = [i for i, ln in enumerate(steps) if ln.startswith(("RUN pip", "COPY ", "ADD "))]
    assert installs and max(installs) < users[-1]
    assert not [ln for ln in steps[users[-1] + 1:] if ln.startswith(("RUN ", "USER "))]
    # the user it switches to is made in the image, with its own home, and not as a system account sharing an id
    made = [ln for ln in steps if ln.startswith("RUN useradd ")]
    assert made and "--create-home" in made[0] and "--uid 10001" in made[0]
    assert last == "10001:10001"
    # the start command is unchanged: the same uvicorn line as railway.json, on $PORT
    cmd = next(ln for ln in steps if ln.startswith("CMD "))
    assert "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1" in cmd
