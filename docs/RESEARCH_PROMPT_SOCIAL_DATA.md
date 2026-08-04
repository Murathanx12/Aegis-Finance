# Short research prompt — social-strategy data sources (feed to Gemini/GPT/etc.)

Paste the block below as one prompt. It targets the practical data questions
that decide whether T1/T2/T6 and the political-access design can start on
schedule. (The literature audit is already done — this is sources only.)

---

> I'm building point-in-time datasets for a retail-scale quant project. For
> each item, give: the exact free/cheap source (URL), bulk-download format,
> update frequency, the field that gives a true PUBLICATION timestamp (not
> reference date), known gaps/pitfalls, and any published paper that used
> that exact source. **Only sources you can verify exist — say "cannot
> verify" rather than guessing.**
>
> 1. **US lobbying**: Senate LDA quarterly filings — bulk XML/API? Is the
>    filing date a reliable PIT timestamp? Any ticker/CIK mapping resource?
> 2. **PAC / campaign contributions**: FEC bulk data — which files map
>    corporate PACs to public companies, and how do researchers usually do
>    the company-name→ticker link?
> 3. **Federal contract awards**: USAspending bulk — award announcement date
>    vs action date; which is PIT-safe? Sub-awards coverage?
> 4. **Revolving-door hires** (ex-officials joining boards/management): any
>    structured source at all (OpenSecrets? LinkedIn-derived academic sets?),
>    or is this only extractable from 8-K/proxy text?
> 5. **SEC Form 4 clusters**: best bulk path for full-history Form 4 with
>    ACCEPTANCE timestamps (EDGAR full-text index vs FTS API vs prepared
>    sets like WRDS/SEC Analytics), and the standard recipe for classifying
>    routine vs opportunistic trades (Cohen-Malloy-Pomorski) — exact rule.
> 6. **13F holdings**: for Thomson/WRDS s34 — the documented filing-lag
>    distribution (45-day deadline vs actual), and the standard PIT
>    convention papers use (available at filing date? quarter-end + 45?).
> 7. **Board/director news events** (departures, appointments) faster than
>    BoardEx's update cycle: is 8-K item 5.02 bulk-parseable with reliable
>    timestamps, and is there an open parsed dataset?
>
> Format: a table per item, then a 5-line summary of which items are
> genuinely PIT-buildable for free vs which need paid data.

---

*When the answers come back: they slot into the T1 (Form 4 × network), T2
(departures), T6 (centrality), and political-access designs — data acquisition
is the only open blocker for those trial specs.*
