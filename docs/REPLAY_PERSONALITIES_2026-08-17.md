# Replay per personality: the risk reduction is real and the timing is not established

**2026-08-17.** The last routed research item. Four declared personalities, nine
books, one path — and one comparison that decides the whole thing.

**Result: vol targeting cuts drawdown hard under every personality, and none of
that is distinguishable from simply holding less.**

---

## The comparison that matters is not vol-target vs buy-and-hold

A vol-targeted book holds less equity on average. So "it beat buy-and-hold" is
two claims wearing one number — it held less, **and** it held less at the right
times. Only the second is a skill claim.

So every vol-target policy runs beside a **constant-exposure policy whose fixed
weight equals that policy's own realised average weight**. Same average equity,
no timing at all. The difference between them is the timing, isolated. This is
the mission's winner-versus-matched-loser design applied to a policy instead of
an episode.

## The books

SPY total return, daily, 2006-01-03 … 2019-12-31, 3,523 days. Cash earns 0% in
the primary run, which understates every policy that holds cash — the bias runs
*against* the policies being tested.

```
  policy                                  avg w    return    maxDD     vol
  buy_and_hold                             1.00    243.2%    55.2%   18.8%
  voltarget_10_cap1.0                      0.73    184.8%    22.9%   10.8%
    matched constant                       0.73    159.4%    43.4%   13.8%
  voltarget_15_cap1.0                      0.89    250.5%    31.5%   13.8%
    matched constant                       0.89    207.5%    50.6%   16.7%
  voltarget_20_cap1.0                      0.95    272.3%    39.6%   15.4%
    matched constant                       0.95    226.2%    53.1%   17.8%
  voltarget_15_cap1.5                      1.10    351.6%    33.1%   16.3%
    matched constant                       1.10    278.2%    59.2%   20.7%
```

Each vol-target book beats its own matched constant on **both** return and
drawdown. `voltarget_15_cap1.0` returns 250.5% against 207.5% at identical
average exposure, with a 31.5% drawdown against 50.6%. That is the timing,
isolated, and it looks good.

## Then each difference is put against its own MDE

```
  policy                   objective            delta       SE      MDE
  voltarget_10_cap1.0      preservation        +37.62    58.70   164.46
  voltarget_15_cap1.0      preservation        +54.45    72.14   202.10
  voltarget_20_cap1.0      preservation        +54.15    65.09   182.37
  voltarget_15_cap1.5      preservation        +89.06   165.68   464.18
    ... and the same pattern under balanced / aggressive / extreme_growth

  timing effects detectable: 0 of 16
```

Every MDE is three to five times its effect. **Not one of the sixteen timing
comparisons is detectable**, under any declared personality.

Under §19 this is *not established*, not refuted — the point estimates are all
positive and the window simply cannot resolve them. What it does mean is that
the drawdown reduction we can actually rely on is the one coming from **average
exposure**, which needs no skill and no forecast. N13 recorded *sizing, not
timing* from the losing side; this is the same conclusion from the winning side.

## Sixteen agreeing cells are worth about one

All sixteen point estimates are positive. That reads like a sign test and it is
not one: four objectives differing only in a drawdown λ, applied to four
policies, on a single price path.

Measured rather than asserted, using Order 8's own primitive:

```
  mean pairwise correlation across the 16 cells   rho_bar = 0.920
  k_eff = 16 / (1 + 15 x 0.920)                          = 1.08
```

**The consistency is one observation wearing sixteen hats.**

### The first version of that measurement was broken

It reported ρ̄ = 0.002 and k_eff = 15.54 — sixteen cells declared nearly
independent. The cause: each cell drew its **own** bootstrap resample indices,
and independent resample streams are uncorrelated by construction. The number
was measuring the random number generator, not the redundancy of the cells.

Correct arithmetic against the wrong world, inside the code written to catch
that. Fixed by drawing one bank of block resamples and sharing it across every
cell; ρ̄ then reads 0.920, which is what four λ-variants of two statistics on one
path should look like.

## What the personalities actually rank

Every ranking names its objective, as rule 3 requires. Under all four,
`voltarget_15_cap1.5` ranks first — but note it holds **avg w = 1.10**, i.e. it
is levered, which is not a book Murat can run today. Among the unlevered
policies the ordering shifts with λ exactly as the declared preferences say it
should: preservation puts `voltarget_20_cap1.0` above its matched constant by
more than extreme growth does, because preservation charges drawdown 0.60 and
extreme growth charges it 0.05.

Nothing here tuned a λ. The personalities are declared preferences; the replay
scores against them and does not fit them.

## Status and honest limits

* EXPLORE only, on the already-claimed 2006–2019 slice. Nothing reserved,
  nothing confirmed.
* **One path, one asset.** Every number here is SPY. §58's exit — more
  weakly-correlated sleeves — is the way to make this resolvable, and it is
  exactly the same prescription the M4 ruling arrived at from the other side.
* **One crisis.** The drawdown differences are dominated by 2008, and there is
  exactly one drawdown reaching −20% in this window.
* Cash at 0% is conservative for these policies; a 2-year-yield sensitivity is
  reported in the run and moves nothing qualitatively.
* No bond or multi-asset leg: our adjusted-price ETF panel has no fixed income,
  and using unadjusted TLT closes would understate bond total return by roughly
  3%/yr. Refused rather than proxied.
