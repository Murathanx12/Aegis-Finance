# AEGIS GitHub usage ? 27 October 2026

**No paid charge appears in your export. No subscription purchase is recommended.**

| Export, October 1?25 | Verified total |
|---|---:|
| Linux runner minutes | 3,930 |
| Gross usage | $23.580 |
| Included discount | $23.580 |
| Net amount | $0 |
| AEGIS minutes | 3,927 |
| CV-Templates minutes | 3 |
| October 7?15 minutes | 3,295 (83.8%) |

The live GitHub API reports Aegis-Finance PRIVATE. Historical visibility is not established; older public-repository notes must not be used as current billing evidence. October 7?15 had 128 CI runs: 75 PR runs and 53 pushes, versus only five Vercel deployments. A sampled successful CI run used 28m02s backend plus 3m19s frontend. This supports repeated test/build runs as the main driver; the sample is not a complete allocation of billed minutes.

Your screenshots show a Free plan, gross usage fully included, and zero-dollar budgets marked blocked. Recent jobs fail before any steps with a payment-failure OR spending-limit annotation. Neither the CSV nor that generic annotation identifies the exact account restriction. No storage SKU appears in this export. The CSV covers only the exported interval; it is not proof that every possible account charge is zero.

The local CI candidate cancels superseded runs of the same PR and skips expensive backend/frontend work only for proven generated-receipt-only main pushes. PR checks and code/security/dependency checks remain; unknown diffs run full CI. Production monitoring cadence is preserved. The patch is local, not pushed or effective on GitHub yet; savings are unmeasured.

Keep the $0 cap. GitHub's private-repository minutes reset at the next billing cycle, not weekly. Waiting can clear an allowance exhaustion but will not necessarily fix a payment/account restriction. Another contributor account does not move the owner's Actions charges. Already-used minutes cannot be reversed by deleting runs. This investigation has not changed budgets, visibility, accounts or billing.

Next UI check: Settings ? Billing and licensing ? Usage ? Actions: inspect included minutes remaining and the billing-cycle reset date. If the next cycle starts and zero-step failures persist, contact GitHub Support with run 40430195110, its annotation, and the $0-net export. The existing support draft is unsent. Do not make the repository public merely to bypass billing: that is a separate exposure decision.

Sources: [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [budget controls](https://docs.github.com/en/billing/how-tos/set-up-budgets). Private evidence: GITHUB_USAGE_TOTALS.json and github-cost-r1/REPORT.md in the current continuation folder.
