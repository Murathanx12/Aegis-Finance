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
    receipt = lambda p: p.startswith("backend/data/public_receipts/")

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


if __name__ == "__main__":
    receipts, frontend = classify_event(
        os.getenv("EVENT", ""), os.getenv("BEFORE", ""),
        os.getenv("BASE", ""), os.getenv("PR_HEAD", ""),
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"receipts_only={str(receipts).lower()}\n")
        output.write(f"frontend_unaffected={str(frontend).lower()}\n")
    print(f"Proven receipt-only push: {receipts}; frontend unaffected: {frontend}")
