"""Conservative CI diff classifier. Unknown means run the existing checks."""
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


def git(*args):
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE)


def classify(paths, event):
    if not paths:
        return False, False
    def receipt(p):
        return p.startswith("backend/data/public_receipts/")

    def independent(p):
        # Explicit non-build inputs only. Root/shared/config/new categories run CI.
        parts = PurePosixPath(p).parts
        if not parts or any(x in ("", ".", "..") for x in p.split("/")) or "\\" in p:
            return False
        return receipt(p) or (
            p.endswith(".py") and p.startswith(("backend/services/", "backend/tests/", "scripts/"))
        ) or (p.startswith("docs/") and p.endswith(".md"))

    return event == "push" and all(map(receipt, paths)), all(map(independent, paths))


def classify_event(event, before="", base="", head=""):
    try:
        refs = (before,) if event == "push" else (base, head)
        if event not in ("push", "pull_request") or any(
            not re.fullmatch(r"[0-9a-f]{40}", ref) or ref == "0" * 40 for ref in refs
        ):
            return False, False
        if event == "push":
            start = before
        else:
            # Checkout is GitHub's tested merge tree. Include base drift as well
            # as PR changes, rather than classifying only the PR head's files.
            for ref in (base, head):
                git("merge-base", "--is-ancestor", ref, "HEAD")
            start = git("merge-base", base, head).decode("ascii").strip()
        raw = git("diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", start, "HEAD", "--")
        if not raw.endswith(b"\0"):
            return False, False
        paths = [p.decode("utf-8", errors="strict") for p in raw[:-1].split(b"\0")]
        return classify(paths, event)
    except (subprocess.SubprocessError, OSError, UnicodeError):
        return False, False


def docs_only_event(event, before="", base="", head=""):
    """Prove regular docs Markdown additions/modifications over the ENTIRE diff.

    Keep this stricter than the existing frontend allowlist. --no-renames
    exposes every rename as a deletion plus addition, so neither endpoint
    can disappear behind a docs destination. Raw modes reject symlinks,
    submodules and type changes without trusting filename extensions.
    """
    try:
        refs = (before,) if event == "push" else (base, head)
        if event not in ("push", "pull_request") or any(
            not re.fullmatch(r"[0-9a-f]{40}", ref) or ref == "0" * 40 for ref in refs
        ):
            return False
        start = before
        if event == "pull_request":
            for ref in (base, head):
                git("merge-base", "--is-ancestor", ref, "HEAD")
            start = git("merge-base", base, head).decode("ascii").strip()
        raw = git("diff", "--no-ext-diff", "--no-renames", "--raw", "-z", start, "HEAD", "--")
        if not raw or not raw.endswith(b"\0"):
            return False
        fields = raw[:-1].split(b"\0")
        if len(fields) % 2:
            return False
        for metadata, path in zip(fields[::2], fields[1::2]):
            # Only ordinary files; even permission-only changes run checks.
            if not re.fullmatch(
                rb":(?:000000 100644 [0-9a-f]+ [0-9a-f]+ A|100644 100644 [0-9a-f]+ [0-9a-f]+ M)",
                metadata,
            ):
                return False
            name = path.decode("utf-8", errors="strict")
            parts = name.split("/")
            if (len(parts) < 2 or parts[0] != "docs" or not name.endswith(".md")
                    or any(part in ("", ".", "..") for part in parts)
                    or "\\" in name or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
                return False
        return True
    except (subprocess.SubprocessError, OSError, UnicodeError):
        return False


if __name__ == "__main__":
    receipts, frontend = classify_event(
        os.getenv("EVENT", ""), os.getenv("BEFORE", ""),
        os.getenv("BASE", ""), os.getenv("PR_HEAD", ""),
    )
    # A failure of either diff parser must retain backend checks.
    docs = frontend and docs_only_event(
        os.getenv("EVENT", ""), os.getenv("BEFORE", ""),
        os.getenv("BASE", ""), os.getenv("PR_HEAD", ""),
    )
    need_backend = not (receipts or docs)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"receipts_only={str(receipts).lower()}\n")
        output.write(f"frontend_unaffected={str(frontend).lower()}\n")
        output.write(f"docs_only={str(docs).lower()}\n")
        output.write(f"need_backend={str(need_backend).lower()}\n")
    print(f"Proven docs-only: {docs}; need backend: {need_backend}")
    print(f"Proven receipt-only push: {receipts}; frontend unaffected: {frontend}")
