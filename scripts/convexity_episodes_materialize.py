"""Materialize CONVEXITY-EPISODES-1 (Order 20 §2.2).

    python -m scripts.convexity_episodes_materialize            # audit only
    python -m scripts.convexity_episodes_materialize --write    # + artifacts

Construction only: episodes, per-episode arm outcomes, matched controls.
NO aggregate verdicts — the trim-vs-hold question belongs to
CONVEXITY-PRESERVATION-1's registration.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import convexity_episodes as CE       # noqa: E402
from backend.services import net_panel as NP                # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="convexity_episodes_materialize")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    px = NP.load_price_panel()
    print("=" * 74)
    print(f"{CE.LIBRARY} — episode construction (no aggregates)")
    print("=" * 74)
    res = CE.materialize(px)
    m = res["meta"]
    print(f"episodes          {m['n_episodes']}")
    print(f"by threshold      {m['episodes_by_threshold']}")
    print(f"skipped           {m['skipped']}")
    print(f"controls missing  {m['controls_missing']}")
    df = res["rows"]
    if len(df):
        matched = df["control"].notna().mean()
        print(f"matched fraction  {matched:.1%}")
    print(f"\nuniverse note: {m['universe_note']}")

    if a.write:
        paths = CE.write(res)
        for k, p in paths.items():
            print(f"wrote {k}: {p}")
    else:
        print("\n--write not given: nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
