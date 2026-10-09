# Repository reconciliation — 2026-10-09

This is a forensic recovery record, not a roadmap. Current operating facts and
remaining gates are in [VERIFICATION_2026-10-09.md](VERIFICATION_2026-10-09.md).

## The two pushes

Counts below come from complete local `git diff --numstat`, not GitHub's first
300 files. Push boundaries were cross-checked against GitHub PushEvents and the
remote-tracking reflog. Added/deleted counts describe text lines, not unique
information or deployable code. Blob sizes count the complete touched files.

| Push | Exact boundary | Lines added / deleted | Files | Meaning |
|---|---|---:|---:|---|
| October 7, 11:02:40 UTC, main | `2454b9410a855cb8458cfafa593ee44f01cb8542` → `6bc11c4060d26abb324c6e7a91c8cd40fa096bdf` (PR #12 merge) | 190,070 / 1,852 | 156 | 171,520 added runtime lines; 5,815 application/config, 8,611 tests, 4,124 documentation |
| October 9, 04:05:38 UTC, WIP | `3a3ad09b895648d4fa8d1a1ff820ccc0b262503d` → `74f82326cbf5d33d584386c11764d35a9817f4c9` | 3,271,529 / 40,288 | 429 | 401 runtime files account for 3,269,657 added lines (99.94%); 27 docs/config files and one 82-line hook test; no application behavior implementation |

The first range's touched new blobs total 74,365,158 bytes: runtime 69,907,549,
application/config 2,021,929, tests 801,330, docs 1,634,350. Its largest addition
is a 155,171-line source-scorecard snapshot. Useful code includes results voice,
the PC benchmark core/revision-flow sleeve, C26/C27 reconciliation and wash-trade
handling, and public evidence/health work. These changes were already on main.

The second range has 308 added and 121 modified files. New touched blobs total
196,191,714 bytes versus 103,617,920 old bytes, a 92,573,794-byte difference.
Fifteen source-scorecard snapshots alone add 2,463,729 lines (57,365,988 bytes).
Other large additions are review receipts (238,790 lines), strategy-library
results (175,483), paper-account receipts (110,614), and straddle data (59,015).
These include dated evidence, repeated complete snapshots and append-only
records; volume is not evidence of improved trading performance.

Commit `74f82326` was authored by Murathan on October 9 at 12:05:23 +08:00;
its single parent is `6bc11c4`. The push's previous WIP tip differs from the
commit parent because main had incorporated that older WIP work. Canonical
JSON comparison of 71 modified JSON files found **zero** semantic-equal
rewrites: this is not simply indentation churn. Repeated scorecard subtrees
explain much of the size, although the complete snapshots are not identical.
Older commits `92f147f6` (+10,235,829 lines) and `46d6efa4` (+6,571,036) are
separate historical bulk-data commits, already in main.

Reproduce the principal totals:

```powershell
git diff --numstat 2454b9410a855cb8458cfafa593ee44f01cb8542 6bc11c4060d26abb324c6e7a91c8cd40fa096bdf
git diff --numstat 3a3ad09b895648d4fa8d1a1ff820ccc0b262503d 74f82326cbf5d33d584386c11764d35a9817f4c9
git show --no-patch --format=fuller 74f82326
```

Detailed machine inventories remain local in the sibling
`aegis-recovery-evidence/git/` directory; sanitized reproducible totals are
retained in this document. Raw account/browser records are not republished.

## Did the news digest get pushed and integrated?

**The implementation was already pushed.** `scripts/world_digest.py` and
`backend/services/world_digest.py` entered history in
`21aa8ffd86ac3777128be9898238643d8adb1327` on September 29, an ancestor of main.
The October 9 push adds 66 Dow Jones runtime files (+42,615/-4,725 lines;
8,433,319 touched bytes), but only three rows to
`news_digest/shadow/decisions.jsonl`. It does not introduce the digest engine.
The full article corpus and raw digests are deliberately ignored.

On October 9, the scheduled digest consumed a 24-hour window with 1,495
items: 161 articles, 30 stock pages, 10 transcripts, 60 social items and 1,234
headlines. It removed 96 duplicate URLs, 177 duplicate headlines and 96 archive
items, while retaining 262 undated items. Provenance/freshness is therefore
not uniformly known. It used 1,456 cached extractions and 39 new extractions.
The existing scheduled run made 57 DeepSeek calls costing $0.04031; local
extraction was OFF. This is distinct from the new local-only operations digest.

It wrote 41 forecast rows (23 size, 18 direction), refused 38 already written
that day, and reported 13 missing ticker proxies and five missing bar inputs.
The producer/consumer chain is documented in the
[operating digest](AEGIS_OPERATING_DIGEST.md). The shadow has 38 rows, but
direction and size trust are both zero; `NEWS_TILT_IN_PLAN=False`. The measured
small graded samples have negative mean improvement. **It contributes research,
forecasts, grades and reading questions; it is not an enabled profitable news
trading strategy.** No trading flag was changed in this recovery.

## Local data and publication boundary

The initial index-only operation removed 587 OpenClaw/Dow Jones operational files and
source-scorecard snapshots from the integration Git index, preserving all
248,407,265 bytes on disk. Paths and hashes at the operation are recorded in
[local_runtime_manifest.json](research_notes/2026-10-09/local_runtime_manifest.json).
`.gitignore` prevents their re-addition. This is index-only housekeeping, not
history rewriting, financial-ledger modification or runtime-directory cleanup.
Existing Git commits retain the old evidence. Active WIP unique work is kept.

Final dependency review restored **two unchanged static launcher templates**:
`dowjones/supervisor_run.cmd` (used by task_keeper) and `dowjones/queue_run.cmd`
(read by the rolling-queue builder). They are executable configuration, not logs.
The final integration therefore removes **585** runtime paths from the index.
Exactly these two templates are exempted from the folder's ignore rule; generated
`reader_pool_run.cmd`, `queue_run_rolling.cmd`, queues, logs and snapshots remain
local. A regression checks template presence in Git on a clean checkout.

Applied the same policy in the active runtime checkout as `8f0054d4` and pushed
WIP: 638 paths / 308,047,647 bytes were retained locally. This larger count
includes snapshots added by `74f82326`. Unrelated active changes were not staged.

Only the established deny-by-default public-receipt publisher is used to
refresh public evidence. Its eight output kinds occupy 4,767,640 bytes, below
the existing 5 MB limit. Raw logs, browser state, account records, full news
text and local model outputs are not part of that publication.

A bounded initial content scan inspected heads/tails (up to 2 MB) of eligible changed
blobs up to 15 MB. Apparent secret-pattern matches were article URL slugs,
not matched configured keys. This is **not a full secret or licensing audit**.
The data contains browser/account metadata and news provenance; no new blanket
public redistribution is justified. Licensed article text was not found in
the sampled Dow Jones JSON, but absence in a sample proves no general absence.

A subsequent complete-blob signature scan covered all 429 added/modified blobs
in the October 9 range (196,191,714 bytes), and all 152 extant added/modified
blobs in the October 7 range (74,365,158 bytes; the remaining four paths were
deletions). No private-key, GitHub-token, AWS-access-ID, project-key or JWT
signature matched. Dow Jones JSON parsed without errors and had no nonempty
common full-article/body fields. These finite signatures do not prove absence
of every credential format or establish redistribution rights.

## Branch disposition and actions

Remote tips were fetched and compared immediately before each deletion.
Conditional deletion used exact expected tips; main was never force-pushed.
No active worktree or open PR was removed. Local worktree branches remain.

| Branch | Disposition | Evidence / action |
|---|---|---|
| main | KEEP | Started `6bc11c4`; PR #14 merged to `866c84c8`, PR #15 to `d4789050`; deployment verification is separate |
| wip/2026-10-07-day | KEEP | `74f82326`, active runtime checkout and unique unmerged records; recover selected docs/config instead of merging bulk runtime |
| wip/2026-10-06-v1-beta | DELETE, executed | `07f2489d`, zero commits ahead of main, no open PR/worktree/automation reference |
| wip/2026-09-29-day | DELETE, executed | `8ac64468`, same reachability and dependency checks |
| claude/beautiful-meitner-hq5614 | DELETE, executed | `00bcb808`, PR #11 merged; same checks |
| lab/weekend-2026-09-06 | DELETE, executed | `c45a825e`, same checks |
| feat/2026-10-07-assets-refresh | KEEP; PR #13 requires repair | `fb60f2d5`, active worktree; green CI does not cover reproduced publication defects below |
| astra/2026-10-08-bloomberg-readiness | MERGE then DELETE, executed | PR #14, `1e51c7bf`, reviewed dated documentation; merge `866c84c8` at 05:42:53 UTC; unchanged tip deleted after green main CI |
| docs/canonical-integration-20260828 | ARCHIVE in place | `d4bde9fb`, one unique commit; historical knowledge not discarded |
| lab/autonomous-rd | KEEP | `4c23ade4`, incorporated but `lab/rd_loop.py:750` still names it as default branch |
| lab-v5-abandoned | KEEP historical evidence | `78cd3e54`, unique commit, owner's explicit preservation instruction |
| recovery/2026-10-09-reconciliation | KEEP active integration worktree | PR #15; selected source/docs and index-only log isolation; do not delete its active worktree or retained ignored copies |

After PR #14's main CI passed, its unchanged remote branch was conditionally
deleted too: **five** obsolete remote branches removed in total. Recovery
integration is [PR #15](https://github.com/Murathanx12/Aegis-Finance/pull/15).
It merged at 09:55:39 UTC as `d4789050c49ea39210e0e6d433a019034fcbedce` after
final source `e2a4d5d7` passed backend and frontend CI (`37911817477`, 14,029
tests passed). The integration branch/worktree stays retained, including its
ignored local copies; this is not an instruction to clean or remove it.
The repaired scheduled publisher subsequently pushed `ba135a54`, followed by
updated health publication `9ea43a12`. Main was merged **into** runtime WIP
(`661db356`, template-index follow-up `ed9a24c4`), preserving its unique history
and unstaged writers. It was not merged wholesale into main. Conflicts were
limited to reviewed recovery files and sanitized public outputs, and owner
documents/image hashes were unchanged.

The archived canonical branch's unique document is
[the August 28 historical roadmap](https://github.com/Murathanx12/Aegis-Finance/blob/d4bde9fba8023c51a8edf7f9d068cebb68ddcd33/docs/ACTIVE_ROADMAP.md).
It is retained evidence, not a second active roadmap. The lab default branch
dependency and abandoned branch's unique rewrite prevent automatic deletion.

PR #13 was reproduced in a disposable repository: its broad `docs/assets`
allowlist committed an unrelated local file as well as the intended asset.
Its pin updater also writes the pin before checking whether the previous pin
changed, and can leave partial outputs when README-marker validation fails.
These are concrete reasons to retain the PR unmerged, despite passing CI.

## Handoff contradiction resolved

The earlier October 9 handoff describes a failed publication attempt caused
by that session's Git lock restrictions. The owner subsequently committed
the document as part of `74f82326`. Its historical statement was accurate for
the earlier attempt, but is not a present permission or publication blocker.
Current authenticated Git operations, PR merge and conditional branch deletion
worked. The new recovery uses its own integration branch and explicit staging.
