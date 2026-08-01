# Why the wall is temporal: shuffled CV manufactures AUC 0.78 from pure noise

**2026-08-02.** Murat proposed replacing the explore/confirm temporal wall
with shuffled train/test splits ("mix the years up randomly, test a few
times"). This note is the answer, with a runnable receipt.

## The experiment

Returns are **iid Gaussian noise** — there is nothing to predict, AUC 0.50 is
the true skill by construction. Features are ordinary rolling statistics
(mean and std at 5/10/20/40-day lookbacks — the same kind of features every
real strategy uses). Label = sign of the next 20-day return (overlapping
forward window, as every real label is). Model: 1-nearest-neighbour (a stand-
in for what any flexible model — LightGBM, deep trees — does internally:
match a test point to its most similar training point). Five seeds.

| validation | mean AUC | per-seed |
|---|---|---|
| shuffled 5-fold CV | **0.783** | 0.788, 0.783, 0.795, 0.765, 0.786 |
| walk-forward + purge gap = label horizon | **0.493** | 0.495, 0.500, 0.476, 0.495, 0.496 |

Script: one page, sklearn + pandas, deterministic seeds (session scratchpad;
reproduce with the parameters above).

## The mechanism, in one paragraph

Rolling features make **adjacent days near-twins** (a 40-day mean barely
moves in a day), and overlapping labels make adjacent days' labels agree
~90% (they share 19/20 of their forward window). Shuffling puts day *t* in
the training set and day *t+1* in the test set; the model finds the twin and
reads off its label. That is not forecasting — it is **looking up the answer
in a mirror**. The temporal split with a purge gap removes every twin pair,
and the "skill" evaporates to exactly zero.

Honest disclosure: it took three attempts to build a leak this clean —
severity depends on feature smoothness and model memorisation capacity,
neither of which is auditable in general. That is the point: **the split
method must be safe under the worst case, because you cannot know where on
the leak spectrum your model sits.**

## Three further reasons, beyond leakage

1. **Interpolation is not the job.** Shuffled CV asks "can the model fill in
   held-out days *between* days it has seen?" Investing asks "can it predict
   a future it has never seen?" Only a temporal split asks the real question.
   COVID appearing *unwarned* in the held-out window is not a flaw — it is
   the entire test. TRIAL-COND-VT (NEG_RESULTS §21) passed its explore years
   and died on 2020's speed in confirm; under shuffled folds it would have
   "passed" — and then taken SPY's full drawdown with real money.
2. **Most of our trials fit no model at all.** The wall's main job is
   controlling RESEARCHER overfitting across 178 registered candidates.
   INSTR-OVERFIT-CEILING measured the zero-skill search ceiling at t≈3.6-4.0
   with the wall intact; letting every hypothesis peek at all years raises
   that ceiling and silently voids the DSR/deflation accounting the entire
   graveyard rests on. Changing the split now would invalidate 178
   candidates' worth of recorded statistics.
3. **The asymmetry.** Every failure mode of shuffling inflates results; none
   deflates them. A method whose errors all point toward "buy" is not a
   validation method.

## The valid core of the instinct — and where it already lives

"One 2019-2024 window is a single draw of history" is true. The honest
remedies are already standard here: purged k-fold **with embargo** inside
explore for fitted models (crash model), CPCV/PBO/DSR overfitting guards
wired to the gate, pre-declared **era splits** in every trial (the 13DG
era split is exactly "testing on different cases," done without leakage),
bootstrap CIs on lane tearsheets — and above all the **forward paper lanes**,
which are the only test set that is unconditionally un-peekable. More
robustness comes from more forward time, never from reshuffling the past.

References: Lopez de Prado, *Advances in Financial ML* ch. 7 (purged k-fold,
embargo); Bailey-Borwein-Lopez de Prado-Zhu (PBO, DSR). House rule
(CLAUDE.md): "Use walk-forward temporal splits (never random k-fold)."

**Ruling: the wall stands unchanged.**
