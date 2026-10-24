# GP1 global-price diagnostic selection

Source-only performance fix; no runtime installation or deployment. The pure
diagnostic now groups normalized after/before frames once using
`groupby("symbol", sort=False).indices` and selects each ticker with `iloc`.
All other production source text is unchanged after newline normalization.
Targets, progress, output fields and input immutability retain their contracts.

**45 tests passed in 2.20s**: all existing 33 plus 12 durable full-receipt or
structural cases. Coverage includes missing symbols, duplicate/invalid dates
and marks, partial targets, prior/unchanged progress, nonunique frame indices,
empty frames and the default symbol/date/close-only schema. One expected pandas
date-parser warning comes from the deliberately invalid-date fixture.

Bounded synthetic benchmark: two calls per variant, 64 rows per symbol,
object-string symbols, identical previous/current frames, no required session.
The timed region includes the entire helper; fixture construction is excluded.

| Symbols | Old median seconds | Group-index median seconds | Speedup |
|---|---:|---:|---:|
| 424 | 0.6791 | 0.1488 | 4.56x |
| 848 | 2.3957 | 0.2982 | 8.03x |
| 1,696 | 9.0659 | 0.5998 | 15.12x |

Every complete output matched the preserved old candidate, including ten
additional edge comparisons. Tests assert structure/equivalence, with no timing
threshold. Timings describe this shared host, not a runtime SLA or measured
native history. Peak memory was not measured.

Private receipts are under
`C:/Users/mrthn/aegis-recovery-evidence/beta-v2-owner-20261025/global_prices/`:
`gp1-before_global_prices.py`, `gp1-benchmark.py`, `gp1-benchmark.json`,
`gp1-test-results.json`, complete equivalent outputs and `gp1-freeze.json`.
The benchmark AST-extracts only the two pure diagnostic functions; it never
imports project configuration or invokes ensure/fetch/cache/scheduler paths.
Existing offline ensure tests use injected downloaders and isolated temporary
fixture files only. R6's original freeze/source inventory was rehashed unchanged.

| Frozen artifact | SHA-256 |
|---|---|
| Production source | `df65bbf718c97b04aeb8bfc6e5705dfe45fe5665ff58ff26ba91ebbc4b187e66` |
| Candidate tests | `6a5cdfa776fd48c9dcb9b63de5c577afada4d1b68a0ec712b65e4308e90a75f3` |
| Preserved old candidate | `aae39594b0129e4efb645baa83fdf85378ec2b08dfed2c28bb77cf65dc0690fa` |
| Benchmark receipt | `be40bd3f9bc0e7c8542771ee2b6cf06d2c65b835a44afa56fcfe89ea389576a8` |
| GP1 freeze | `4db6024efc691f2df7c927b8b7656c0afe3e36d6973ab8f7383ae59c875a4a6b` |
