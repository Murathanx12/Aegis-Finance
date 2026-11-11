"""CH-05 "U" (OD-c / OD-d, 2026-11-11): growing data under backend/data/optimus
leaves git, and nothing new enters it by default.

Why: production code runs from a release clone whose backend/data/optimus is a
junction to the live data dir. A growing file main still tracks shows as
modified through the junction, and a checkout in that clone would write main's
stale copy INTO live data. These tests read git's own answer (`check-ignore
--no-index`, `ls-files`), so they hold on a fresh CI checkout too."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OPT = "backend/data/optimus"


def _ignored(rel: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "--no-index", "-q", rel], cwd=REPO)
    assert r.returncode in (0, 1), r
    return r.returncode == 0


def _tracked(rel: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO,
                       capture_output=True)
    return r.returncode == 0


#: A sample of the 81 files untracked in this PR (each differed from the live copy on
#: 2026-11-11: an append ledger, a rewritten state file, a dated receipt a later run rewrote).
UNTRACKED = (
    "predictions.jsonl", "decisions/ledger.jsonl", "hyp_lab/ledger.jsonl", "hyp_lab/spend.jsonl",
    "sim/session.json", "sim/sessions.jsonl", "sim/owner.jsonl", "pc_book/nav.jsonl",
    "pc_book/policy_state.json", "paper_accounts/pc_snapshot/nav.jsonl",
    "paper_accounts/fleet_manager/decisions.jsonl", "paper_accounts/fleet_manager/state/hack1.json",
    "official/requests.jsonl", "official/state.json", "official/robots/www.sec.gov.json",
    "brain/learned_rules.jsonl", "nn_lab/trust.jsonl", "llm_portfolio/books.jsonl",
    "world_state/beliefs.json", "deepseek_balance.jsonl", "strategy_library/LEADERBOARD.md",
)


@pytest.mark.parametrize("rel", UNTRACKED)
def test_a_growing_file_is_neither_tracked_nor_addable_by_default(rel):
    assert not _tracked(f"{OPT}/{rel}"), f"{rel} is tracked: it grows on the live box"
    assert _ignored(f"{OPT}/{rel}"), f"{rel} would show as untracked through the junction"


@pytest.mark.parametrize("rel", [
    "some_new_lane/receipt_2026-11-12.json", "night_factory_2099-01-01/X1_run.json",
    "forecasts/forecasts_2026-11.jsonl", "ledger_manifests/forecast_ledger/x.json.tmp",
    "dowjones/reader_pool_run.cmd", "dowjones/reader_launch.json",
])
def test_default_deny_new_data_needs_a_reviewed_add_f(rel):
    assert _ignored(f"{OPT}/{rel}")


@pytest.mark.parametrize("rel", [
    "opportunities/README.md", "digest_inbox/README.md", "digest_inbox/WEEKEND_READING_LIST.md",
    "ledger_manifests/forecast_ledger/manifest_2026-11.json", "ledger_archive/llm_calls_2026-10.parquet",
    "nn_lab/revisions_archive/r_2026-10.parquet", "typed_events/MANIFEST.json",
    "strategy_library/holdings_2099-01-01T000000Z.manifest.json",
    "paper_accounts/fleet_manager/contracts/hack9_v1.json",
    # `task_keeper assets` commits this receipt with a plain `git add` (publish_receipts.commit_paths)
    "paper_accounts/public_assets_refresh_2099-01-01T000000Z.json",
    "finra_short_volume/manifest.json", "finra_short_volume/pull_receipt_2026-11-11.json",
    "empty_stdin.txt",
    # still executed by the old runtime checkout until every task has switched (CH-05)
    "dowjones/supervisor_run.cmd", "dowjones/queue_run.cmd",
])
def test_the_keep_list_stays_addable(rel):
    assert not _ignored(f"{OPT}/{rel}")


@pytest.mark.parametrize("rel", [
    # pinned by the prepared PC policy epoch (source_sha256): untracking it would refuse the epoch
    "paper_accounts/fleet_manager/contracts/hack2_v2.json",
    # sealed archives the ledger_archive / nn_lab seals require to be tracked
    "ledger_archive/llm_calls_2026-09.parquet", "ledger_manifests/llm_calls_2026-09.json",
    "empty_stdin.txt", "dowjones/supervisor_run.cmd", "dowjones/queue_run.cmd",
])
def test_what_must_stay_tracked_is_tracked(rel):
    assert _tracked(f"{OPT}/{rel}")
