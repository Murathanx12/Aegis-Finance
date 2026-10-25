"""Private stdlib gate. Never use as an independent provider CLI."""

import sys
from pathlib import Path


def main():
    if sys.stdin.buffer.read(1) != b"A":
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.services.funnel_acquisition import worker_main

    try:
        return worker_main(sys.stdin.buffer)
    except Exception:
        # No raw SDK exception, credentials or traceback on stdout/stderr.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
