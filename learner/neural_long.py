"""W3 -- THE NEURAL ARM ON THE LONG PANEL, ON THE GPU, JUDGED AGAINST LightGBM.

WHY THIS FILE EXISTS
====================
The night lab of 2026-09-05 (L1) put the learner's best cell at +14.4%/yr ahead
of the market on 2013-2024 and then killed it with its own arithmetic: DSR 0.197
against a 0.2305 noise bar, SPA p 0.29, PBO 0.29, and **t = 2 needing 16.1 years
of out-of-sample tape against the 7.0 the 12-year panel held**. `long_panel.py`
answers the shortage of TAPE (1999-2024, ~19 scored years). This file answers
the only remaining modelling question the weekend has budget for: with 26 years
and a GPU that runs a fit in seconds instead of minutes, **does a neural
encoder beat LightGBM on the same folds, after the multiplicity family?**

That question, and not "is the neural net good". A neural arm that is +3%/yr
against the market and -1%/yr against `lgbm` on identical folds has discovered
nothing; it has re-derived the incumbent more expensively. So every receipt this
module writes carries TWO inference blocks -- one against the market, one
against LightGBM on the paired monthly series -- and the verdict requires both.

WHAT IS REUSED FROM `learner/encoder.py`, AND WHAT IS NOT
========================================================
REUSED, deliberately and by import rather than by copy:

* **`encoder.ClipSD`** -- the +/-5 sd clip on STANDARDISED features. It is
  load-bearing, not cosmetic: without it the v2 regression heads returned an sd
  of 15.3 in excess-return units (a predicted +1,533%) because `ratio` is
  unbounded and the panel holds name-months with a ratio in the hundreds. The
  same failure is available here and the same guard closes it.
* **`encoder._inner_split`** -- the last-12-months TEMPORAL inner holdout used
  for early stopping. Never random.
* **the trunk shape** -- `Linear -> GELU -> Dropout -> Linear -> GELU` into a
  small `Linear(16) -> GELU -> Linear(1)` head, AdamW, early stopping on an
  inner temporal holdout, per-horizon target standardisation.
* **the pipeline order** -- median impute, then standardise, then clip.
  `fillna(0)` is banned by the house and by this file.

CHANGED, with the reason:

* **ONE horizon (1m), not four.** v2's whole architectural claim was that a
  12-month target shapes a trunk the 1-month head reads. That claim was tested
  and is not what is being tested here; carrying it would put four horizons of
  cells into a multiplicity family that already has to pay for eight seeds. The
  book is graded on `fwd_1m` either way.
* **The target is clipped at +/-5 sd of the TRAIN target, not winsorised at the
  1st/99th percentile.** Both bound the same failure. The sd clip is stated in
  the same unit as the feature clip, so one number in the receipt describes
  both, and it is symmetric by construction where a percentile pair is not.
  The EVALUATION target is never clipped anywhere -- the tail is the result.
* **Eight seeds, always, and the SPREAD is the headline.** v2 fitted one seed
  per cell. S36 measured what that is worth: a model fitted on a shuffled target
  holds one persistent tilt and its naive t spans -9..+12 across seeds. A single
  draw is not a result, so the receipt reports min / median / max terminal
  wealth across seeds AND treats every seed as its own cell in the family.
* **A masked-feature pre-training pass** (below). v2 had none.
* **GPU, and it says so.** The device actually used is in the receipt. If CUDA
  is missing the module does not silently produce a CPU number under a GPU
  heading: `resolve_device` records `cuda_available: false` and every receipt
  carries `device_warning`.

THE SELF-SUPERVISED PASS, AND EXACTLY WHY IT IS NOT LEAKAGE
===========================================================
Pre-training reconstructs 15% randomly masked FEATURE entries from the other
85%. No target column is loaded, no target column is in the tensor, and the
reconstruction loss cannot see one. That is the legitimate unsupervised use: it
learns the shape of the feature manifold, which is knowable from prices and
analyst files without knowing what happened next.

It is still possible to be sloppy about it, so two scopes are run and BOTH are
reported:

* **`causal`** -- for test year Y, pre-training sees only rows with
  `entry_date < Y-01-01`, and the impute/scale/clip pipeline is fitted on those
  same rows. Nothing about year Y, features included, touches the model. This
  arm is strictly point-in-time and is the one a claim may be made from.
* **`all`** -- pre-training (and the pipeline it standardises with) sees the
  feature table of all 1999-2024 rows, targets still absent. **This is a mild
  look-ahead and it is named as one.** Knowing the 1999-2024 feature
  distribution -- that log market cap drifted up, that vol spiked in 2008 and
  2020 -- is information a 2004 desk did not have, even though no outcome is in
  it. It is reported because "pre-train on everything" is what a practitioner
  would do and the size of the advantage it buys is worth a number; it is
  segregated because that advantage is not tradeable.

If the two scopes agree, the look-ahead bought nothing and the point is moot.
If `all` wins and `causal` does not, the finding is about the leak.

THE FAMILY, AND WHY IT IS COUNTED THE WAY IT IS
===============================================
Eight seeds x two cost rates is sixteen looks at one hypothesis, not one look.
`inference.full_report` is handed EVERY cell -- seeds included -- as the family,
so the Deflated Sharpe pays for the seed search as well as for the grid. The
seed-mean ensemble is reported as its own cell and is not exempt. Variants are
separate families with separate `family_id`s; cross-variant multiplicity is the
leaderboard's to carry, and the receipt says so rather than quietly netting it.

THE THIRD LEG, ADDED AFTER THE FIRST FULL PASS (2026-09-06)
===========================================================
The first 2004-2024 pass returned a champion cell with **terminal wealth 561x
against the market's 14.4x**, DSR 0.98, SPA p 0.016, PBO 0.09 and a positive
mean in all three eras. It cleared every statistical bar this repo owns, and it
was not a model result. `robustness()` was written to say what it was made of,
and said it in four numbers:

* the book's MEDIAN holding traded **$1.07m a day** and cost **$6.51 a share**;
  **50% of the book sat below the house's own $3m/day execution floor** and 40%
  below $5 a share;
* imposing that floor cut the champion from **561x to 93x** -- and *raised*
  LightGBM from **16.8x to 59.8x**. The 33x lead became 1.6x, and the seed-mean
  ensemble (42.8x) went from ahead of lgbm to **behind** it;
* **43% of the entire 251-month excess came from FIVE months**;
* 25 bps rather than 10 halved it again.

So the verdict has a third leg: a cell that clears every bar on a book the desk
could not have filled is `NOISE (clears every bar, dies at the $3m/day execution
floor)`. That block runs on every receipt now, because the pass that produced
561x would otherwise have published it in good faith -- `evaluate.book`'s
default output contains nothing that would have contradicted it.

WHAT FAILURE THIS PREVENTS
==========================
The specific one this repo has already paid for twice: a champion published on a
single seed, against the market, with no incumbent in the comparison and no
`years_needed_for_t2` beside its t -- and now a third, a champion published on a
book half of which is untradable. Every one of those is structurally impossible
to omit here: the seed loop is not optional, the LightGBM leg is computed in the
same pass on the same folds, `full_report` returns the power block, `robustness`
re-grades under the execution floor, and `job()` refuses to emit a verdict that
did not consult all of them.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from learner import dataset as DS
from learner import encoder as ENC            # ClipSD + the temporal inner split
from learner import evaluate, inference
from learner import long_panel as LP
from learner import models as M

try:  # pragma: no cover - environment dependent
    import torch
    import torch.nn as nn
    _TORCH = True
except Exception:  # pragma: no cover
    _TORCH = False


# ------------------------------------------------------------------ constants

#: Distinct from `encoder.SEED` and `models.SEED` on purpose: a shared seed
#: across modules makes two "independent" fits correlated in a way nobody sees.
SEED_BASE = 20260906
N_SEEDS = 8

#: The horizon the book is graded at, and the target the net is fitted on.
HORIZON = 1
COSTS: tuple[float, ...] = (10.0, 25.0)

#: Standardised features are clipped here, exactly as in the v2 encoder.
CLIP_SD = ENC.CLIP_SD
#: The STANDARDISED TRAINING target is clipped at the same width. The evaluation
#: target is never clipped -- the tail is the result, not an outlier.
TARGET_CLIP_SD = 5.0

#: Trunk widths. `base` is the v2 encoder's larger grid point; `wide` is the
#: variant-3 question ("does capacity help, or is the tape the binding
#: constraint?"), which on this repo's history has exactly one likely answer.
WIDTHS: dict[str, tuple[int, int]] = {"base": (128, 64), "wide": (512, 256)}
DROPOUT = 0.2
LR = 1e-3
WEIGHT_DECAY = 1e-4
MAX_EPOCHS = 30
PATIENCE = 4
BATCH = 16_384

#: Masked-feature reconstruction. 15% of entries per row, replaced by 0 -- which
#: is the MEAN after standardisation, i.e. "no information", not a magic value.
MASK_FRACTION = 0.15
PRETRAIN_EPOCHS = 8
PRETRAIN_LR = 1e-3

#: Pinball quantiles for variant 2. q50 is the median head (a different loss for
#: the same question); q90 asks the different question -- which names have an
#: unusually good RIGHT tail, which is what a concentrated book actually wants.
QUANTILES: tuple[float, ...] = (0.5, 0.9)

VARIANTS: tuple[str, ...] = ("supervised", "pretrained", "quantile", "wide")

#: The GPU is fast enough that a full 21-fold x 8-seed pass is minutes, so the
#: default is the whole window. A caller may shorten it; the receipt prints what
#: was actually run rather than what the default says.
FIRST_TEST_YEAR = LP.FIRST_TEST_YEAR      # 2004
LAST_TEST_YEAR = 2024


# ---------------------------------------------------------------- the device

def resolve_device(prefer_cuda: bool = True) -> tuple["torch.device", dict]:
    """Return the device AND a receipt of what it actually is.

    LOUD, NOT SILENT. A CPU run is allowed -- refusing to run at all would make
    the module untestable on a machine without a GPU -- but it is never reported
    as a GPU result: `cuda_available` is False, `device_warning` is populated,
    and `job()` copies both onto the receipt where a reader cannot miss them.
    """
    if not _TORCH:
        raise RuntimeError(
            "REFUSED: torch is not importable, and this module will not "
            "substitute a different model class under a neural heading.")
    info: dict = {
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_requested": bool(prefer_cuda),
    }
    if prefer_cuda and torch.cuda.is_available():
        dev = torch.device("cuda")
        try:
            cap = torch.cuda.get_device_capability(0)
            info["device_name"] = torch.cuda.get_device_name(0)
            info["device_capability"] = f"sm_{cap[0]}{cap[1]}"
            info["vram_total_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 2**30, 2)
        except Exception as exc:                                    # noqa: BLE001
            info["device_probe_error"] = f"{type(exc).__name__}: {exc}"
        info["device_actually_used"] = "cuda"
        info["device_warning"] = None
    else:
        dev = torch.device("cpu")
        info["device_actually_used"] = "cpu"
        info["device_warning"] = (
            "CUDA was requested and is NOT available. Every number in this "
            "receipt was computed on the CPU and must not be quoted as a GPU "
            "result; timings in particular are not comparable."
            if prefer_cuda else
            "CUDA was not requested; this is a CPU run by choice.")
    return dev, info


# ---------------------------------------------------------- the preprocessing

def make_pipeline() -> Pipeline:
    """median impute -> standardise -> clip at +/-CLIP_SD. `fillna(0)` is banned.

    `ClipSD` is IMPORTED from `learner.encoder`, not re-implemented: a second
    copy of a bound is a second bound, and the reason this step exists (an
    unbounded `ratio` producing a predicted +1,533% excess return) is written
    down in exactly one place.
    """
    return Pipeline([("impute", SimpleImputer(strategy="median")),
                     ("scale", StandardScaler()),
                     ("clip", ENC.ClipSD(CLIP_SD))])


def feature_cols() -> list[str]:
    """The 49 panel features PLUS `prior_1m`, i.e. `models.arm_features(..., 'raw')`.

    IDENTICAL to what `models.fit_predict('lgbm', 'raw', ...)` sees, because the
    comparison in this file is neural-vs-lgbm and a column the incumbent has and
    the challenger does not turns an architecture question into a feature
    question. `prior_1m` is declared VOID on this panel
    (`dataset.build`'s `prior_status`) and is therefore expected to carry very
    little; it is included for parity, not for information.
    """
    return M.arm_features(DS.feature_columns(), "raw", HORIZON)


# ------------------------------------------------------------------- the net

class TrunkNet(nn.Module if _TORCH else object):      # pragma: no cover - torch
    """v2's trunk, with a reconstruction decoder bolted on beside the head.

    ONE trunk serves both jobs. That is the whole point of pre-training: the
    representation the masked-reconstruction loss shapes is the representation
    the supervised head then reads. A separate encoder per job would be two
    models sharing a docstring.
    """

    def __init__(self, n_in: int, hidden: tuple[int, int], dropout: float,
                 n_out: int = 1):
        super().__init__()
        h1, h2 = hidden
        self.trunk = nn.Sequential(
            nn.Linear(n_in, h1), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(h1, h2), nn.GELU(),
        )
        self.head = nn.Sequential(nn.Linear(h2, 16), nn.GELU(), nn.Linear(16, n_out))
        self.recon = nn.Sequential(nn.Linear(h2, h1), nn.GELU(), nn.Linear(h1, n_in))
        self.n_out = int(n_out)

    def forward(self, x):
        return self.head(self.trunk(x))

    def reconstruct(self, x):
        return self.recon(self.trunk(x))


def _pinball(pred, y, quantiles):                     # pragma: no cover - torch
    """Sum of pinball losses, one column per quantile. Never averaged with MSE."""
    loss = 0.0
    for j, q in enumerate(quantiles):
        d = y - pred[:, j]
        loss = loss + torch.maximum(q * d, (q - 1.0) * d).mean()
    return loss


# --------------------------------------------------------------- the training

def pretrain(net, Z, device, seed: int, epochs: int = PRETRAIN_EPOCHS,
             batch: int = BATCH, mask_fraction: float = MASK_FRACTION,
             lr: float = PRETRAIN_LR) -> dict:        # pragma: no cover - torch
    """Masked-feature reconstruction. NO TARGET IS LOADED OR TOUCHED.

    `Z` is the standardised feature tensor and nothing else -- the caller builds
    it from feature columns only, so there is no target column in scope for this
    function to accidentally read. The masked entries are set to 0, which after
    standardisation is the column mean: "we removed this", not "this is zero".
    Loss is computed on the masked entries ONLY; reconstructing the 85% that
    were handed over unchanged is free and would drown the signal.
    """
    torch.manual_seed(seed)
    opt = torch.optim.AdamW(
        list(net.trunk.parameters()) + list(net.recon.parameters()),
        lr=lr, weight_decay=WEIGHT_DECAY)
    gcpu = torch.Generator().manual_seed(seed + 101)
    gdev = torch.Generator(device=device); gdev.manual_seed(seed + 202)
    n = int(Z.shape[0])
    t0 = time.perf_counter()
    last = None
    net.train(True)
    for _ep in range(epochs):
        perm = torch.randperm(n, generator=gcpu)
        tot, seen = 0.0, 0
        for i in range(0, n, batch):
            idx = perm[i:i + batch].to(device)
            xb = Z[idx]
            mask = torch.rand(xb.shape, device=device, generator=gdev) < mask_fraction
            if not bool(mask.any()):
                continue
            xin = xb.masked_fill(mask, 0.0)
            out = net.reconstruct(xin)
            loss = (((out - xb) ** 2) * mask).sum() / mask.sum().clamp(min=1.0)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            tot += float(loss.detach()) * len(idx)
            seen += len(idx)
        last = tot / max(seen, 1)
    net.train(False)
    return {"pretrain_rows": n, "pretrain_epochs": epochs,
            "mask_fraction": mask_fraction,
            "final_masked_recon_mse": (round(last, 6) if last is not None else None),
            "pretrain_seconds": round(time.perf_counter() - t0, 2),
            "targets_seen": 0}


def train_head(net, Zf, yf, Zv, yv, device, seed: int,
               quantiles: tuple[float, ...] | None = None,
               max_epochs: int = MAX_EPOCHS, patience: int = PATIENCE,
               batch: int = BATCH, lr: float = LR) -> dict:  # pragma: no cover
    """Supervised fine-tune with early stopping on a TEMPORAL inner holdout."""
    torch.manual_seed(seed + 7)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=WEIGHT_DECAY)
    gcpu = torch.Generator().manual_seed(seed + 303)
    n = int(Zf.shape[0])
    has_val = int(Zv.shape[0]) > 0

    def _loss(pred, y):
        if quantiles:
            return _pinball(pred, y, quantiles)
        return ((pred[:, 0] - y) ** 2).mean()

    best, best_state, bad, epochs_run = np.inf, None, 0, 0
    t0 = time.perf_counter()
    for _ep in range(max_epochs):
        epochs_run += 1
        net.train(True)
        perm = torch.randperm(n, generator=gcpu)
        for i in range(0, n, batch):
            idx = perm[i:i + batch].to(device)
            opt.zero_grad(set_to_none=True)
            _loss(net(Zf[idx]), yf[idx]).backward()
            opt.step()
        if not has_val:
            continue
        net.train(False)
        with torch.no_grad():
            v = float(_loss(net(Zv), yv))
        if v < best - 1e-7:
            best, bad = v, 0
            best_state = {k: p.detach().clone() for k, p in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    net.train(False)
    return {"epochs_run": epochs_run,
            "inner_val_loss": (None if not np.isfinite(best) else round(best, 6)),
            "fit_seconds": round(time.perf_counter() - t0, 2)}


# -------------------------------------------------------------- the fold pass

def _pretrain_rows(df: pd.DataFrame, year: int, scope: str) -> pd.Index:
    """WHICH ROWS THE UNSUPERVISED PASS MAY SEE. The whole leakage question.

    * `causal` -- rows whose `entry_date` is strictly before 1 Jan of the test
      year. Nothing about the test year, features included.
    * `all`    -- every row of 1999-2024. Targets are still never loaded, but the
      FEATURE DISTRIBUTION of the future is visible. A mild look-ahead, named.
    """
    if scope == "all":
        return df.index
    if scope == "causal":
        return df.index[pd.to_datetime(df["entry_date"]) < pd.Timestamp(f"{year}-01-01")]
    raise ValueError(f"unknown pretrain scope {scope!r}")


def run_neural(df: pd.DataFrame, test_years, *, seeds, width: str = "base",
               pretrain_scope: str | None = None,
               quantiles: tuple[float, ...] | None = None,
               device=None, device_info: dict | None = None,
               verbose: bool = True) -> tuple[dict, dict]:
    """Fit the neural arm on every fold x seed. Returns (pred columns, receipt).

    The prediction for (seed, quantile) is assembled across folds into ONE
    column indexed like `df`, so the evaluator sees exactly the object it sees
    for every other arm in this repo.

    THE PIPELINE IS FITTED WHERE THE PRE-TRAINING LOOKED. For the strictly
    causal arms that is the fold's own training rows; for `pretrain_scope="all"`
    it is the whole panel, because a trunk pre-trained in one standardised space
    cannot be fine-tuned in another. That is the second half of the same mild
    look-ahead and it is not hidden behind the first.
    """
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    if device is None:
        device, device_info = resolve_device()
    cols = feature_cols()
    ycol = f"excess_vw_{HORIZON}m"
    hidden = WIDTHS[width]
    n_out = len(quantiles) if quantiles else 1

    global_pre, global_Zpre = None, None
    if pretrain_scope == "all":
        # ONE pipeline for the whole `all` arm -- see the docstring above. The
        # pretraining tensor is also fold-invariant by definition, so it is built
        # ONCE: rebuilding an identical 925k x 50 tensor 21 times would be 21
        # copies of the same look-ahead, more slowly.
        global_pre = make_pipeline()
        global_pre.fit(df[cols].to_numpy(dtype="float64"))

    preds: dict[str, pd.Series] = {}
    fold_notes: list[dict] = []
    t_start = time.perf_counter()

    for year, tr, te in DS.walk_forward_splits(df, test_years, HORIZON):
        t_fold = time.perf_counter()
        train = df.loc[tr]
        pre = global_pre if global_pre is not None else make_pipeline()
        Xtr = train[cols].to_numpy(dtype="float64")
        if global_pre is None:
            pre.fit(Xtr)
        Ztr_np = pre.transform(Xtr).astype("float32")
        Zte_np = pre.transform(df.loc[te, cols].to_numpy(dtype="float64")).astype("float32")

        # target: standardise on TRAIN, then clip at +/-TARGET_CLIP_SD.
        y_np = train[ycol].to_numpy(dtype="float64")
        mu, sd = float(np.nanmean(y_np)), float(np.nanstd(y_np))
        sd = sd if sd > 1e-12 else 1.0
        ys = np.clip((y_np - mu) / sd, -TARGET_CLIP_SD, TARGET_CLIP_SD).astype("float32")
        n_clipped = int((np.abs((y_np - mu) / sd) > TARGET_CLIP_SD).sum())

        fit_m, val_m = ENC._inner_split(train["month"])      # temporal, never random

        Ztr = torch.as_tensor(Ztr_np, device=device)
        yt = torch.as_tensor(ys, device=device)
        Zte = torch.as_tensor(Zte_np, device=device)
        fit_t = torch.as_tensor(np.flatnonzero(fit_m), device=device)
        val_t = torch.as_tensor(np.flatnonzero(val_m), device=device)
        Zf, yf = Ztr[fit_t], yt[fit_t]
        Zv, yv = Ztr[val_t], yt[val_t]

        Zpre = None
        if pretrain_scope == "all":
            if global_Zpre is None:
                global_Zpre = torch.as_tensor(
                    pre.transform(df.loc[_pretrain_rows(df, year, "all"), cols]
                                  .to_numpy(dtype="float64")).astype("float32"),
                    device=device)
            Zpre = global_Zpre
        elif pretrain_scope is not None:
            pidx = _pretrain_rows(df, year, pretrain_scope)
            Zpre = torch.as_tensor(
                pre.transform(df.loc[pidx, cols].to_numpy(dtype="float64")
                              ).astype("float32"), device=device)

        note = {"year": int(year), "n_train": int(len(tr)), "n_test": int(len(te)),
                "n_train_months": int(train["month"].nunique()),
                "target_mu": round(mu, 6), "target_sd": round(sd, 6),
                "train_rows_clipped_at_5sd": n_clipped,
                "pretrain_rows": (0 if Zpre is None else int(Zpre.shape[0])),
                "seeds": []}

        for s in seeds:
            # SEED BEFORE CONSTRUCTION, not just before training. `nn.Linear`
            # draws its weights from the global generator at __init__, so a seed
            # set inside `train_head` leaves the INITIALISATION at the mercy of
            # whatever the process did before -- and two identical calls then
            # disagree on the first fold and agree on the rest, which is the most
            # confusing shape a reproducibility bug can take.
            # `backend/tests/test_neural_long.py::test_the_same_seed_reproduces`
            # found exactly that and is the reason this line is here.
            torch.manual_seed(int(s))
            net = TrunkNet(Ztr.shape[1], hidden, DROPOUT, n_out=n_out).to(device)
            smeta: dict = {"seed": int(s)}
            if Zpre is not None:
                smeta["pretrain"] = pretrain(net, Zpre, device, int(s))
            smeta.update(train_head(net, Zf, yf, Zv, yv, device, int(s),
                                    quantiles=quantiles))
            with torch.no_grad():
                out = net(Zte).detach().float().cpu().numpy()
            for j, q in enumerate(quantiles or (None,)):
                # back onto the excess-return scale the evaluator expects
                p = out[:, j].astype("float64") * sd + mu
                key = f"s{int(s)}" if q is None else f"s{int(s)}_q{int(q * 100)}"
                preds.setdefault(key, pd.Series(np.nan, index=df.index,
                                                dtype="float64"))
                preds[key].loc[te] = p
            note["seeds"].append(smeta)
            del net
        del Ztr, yt, Zte, Zf, yf, Zv, yv, fit_t, val_t, Zpre
        if device.type == "cuda":
            torch.cuda.empty_cache()
        note["fold_seconds"] = round(time.perf_counter() - t_fold, 2)
        fold_notes.append(note)
        log(f"    {year}: train {len(tr):,} test {len(te):,} "
            f"({note['fold_seconds']}s for {len(seeds)} seeds)")

    receipt = {
        "device": device_info,
        "width": width, "hidden": list(hidden), "dropout": DROPOUT,
        "n_features": len(cols),
        "feature_source": "learner.dataset.feature_columns() + prior_1m "
                          "(= models.arm_features(..., 'raw'))",
        "horizon_months": HORIZON,
        "target": ycol,
        "target_clip_sd": TARGET_CLIP_SD,
        "feature_clip_sd": CLIP_SD,
        "imputation": "SimpleImputer(median) inside the pipeline; fillna(0) is banned",
        "pretrain_scope": pretrain_scope,
        "quantiles": list(quantiles) if quantiles else None,
        "seeds": [int(s) for s in seeds],
        "folds": fold_notes,
        "n_folds": len(fold_notes),
        "wall_seconds": round(time.perf_counter() - t_start, 1),
        "splitter": "learner.dataset.walk_forward_splits (target matured before the "
                    "test year opened) -- never random, never k-fold",
    }
    return preds, receipt


def run_lgbm(df: pd.DataFrame, test_years, verbose: bool = True
             ) -> tuple[pd.Series, dict]:
    """The incumbent, on the SAME folds, through the house's own machinery.

    `models.fit_predict` and not a local LightGBM call, so the comparison is
    against the thing every other receipt in this repo measured, rather than
    against a re-implementation that could differ in an unnoticed way.
    """
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    fc = DS.feature_columns()
    out = pd.Series(np.nan, index=df.index, dtype="float64")
    notes, t0 = [], time.perf_counter()
    for year, tr, te in DS.walk_forward_splits(df, test_years, HORIZON):
        t1 = time.perf_counter()
        pred, meta = M.fit_predict("lgbm", "raw", df.loc[tr], df.loc[te], fc, HORIZON)
        out.loc[te] = M.arm_reconstruct(pred, df.loc[te], "raw", HORIZON)
        notes.append({"year": int(year), "n_train": int(len(tr)),
                      "n_test": int(len(te)),
                      "best_iteration": meta.get("best_iteration"),
                      "seconds": round(time.perf_counter() - t1, 2)})
        log(f"    lgbm {year}: {notes[-1]['seconds']}s")
    return out, {"kind": "lgbm", "arm": "raw", "n_features": len(fc) + 1,
                 "folds": notes, "wall_seconds": round(time.perf_counter() - t0, 1),
                 "provenance": "learner.models.fit_predict -- the same call W2 makes"}


# ------------------------------------------------------------- the evaluation

def _grade(df: pd.DataFrame, col: str, bps: float) -> dict:
    return evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                         ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                         return_series=True)


#: The house's own execution floor (`evaluate.TRADABLE_DOLLAR_VOL`). Below it a
#: name is OBSERVE_ONLY and a book holding it is a backtest of something
#: unbuyable. IMPORTED, not restated -- one floor, one place.
TRADABLE_FLOOR_USD = evaluate.TRADABLE_DOLLAR_VOL


def robustness(df: pd.DataFrame, col: str, bps: float = 10.0) -> dict:
    """ASK WHAT IT BOUGHT, AND CHECK THE TAIL BEFORE THE MEAN.

    THIS BLOCK EXISTS BECAUSE THE FIRST FULL PASS PRODUCED A 561x TERMINAL
    WEALTH AND THE RECEIPT HAD NO WAY TO SAY WHAT THAT WAS MADE OF. Measured
    2026-09-06 on the champion cell of variant 0: the book's MEDIAN holding
    traded $1.07m a day and cost $6.51 a share, 50% of it sat below the house's
    own $3m/day execution floor, 43% of the whole 251-month excess came from
    FIVE months, and imposing the floor cut terminal wealth from 561 to 93 while
    RAISING LightGBM's from 16.8 to 59.8. The headline number was not a model
    result; it was a microcap-liquidity result with a fat tail.

    None of that is visible in `evaluate.book`'s default output, so a pass that
    did not compute it would publish 561x in good faith. Four questions, every
    pass, on every cell the receipt names:

      * does it survive the tradable floor, and what does the INCUMBENT do under
        the same floor? (the second half matters: a floor that helps lgbm and
        hurts the challenger reverses the comparison)
      * does it survive 25 bps?
      * how much of the excess is the five best months, and what is terminal
        wealth without them -- beside the MARKET's terminal wealth without those
        same months, so the reader is comparing like with like?
      * what did it actually hold -- median cap, price and dollar volume, and
        the share of the book below $5 and below $1m/day?
    """
    out: dict = {"cost_bps": bps, "tradable_floor_usd": TRADABLE_FLOOR_USD}
    plain = evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                          ret_col="fwd_1m", mkt_col="mkt_vw_1m", return_series=True)
    ser = plain.pop("_series", {}) or {}
    out["plain"] = {k: plain.get(k) for k in
                    ("months", "terminal_wealth_net", "terminal_wealth_market_same_months",
                     "annualised_excess", "t_stat_paired_vs_market", "mean_turnover")}
    for label, kw in (("tradable_floor", {"tradable_floor": TRADABLE_FLOOR_USD}),
                      ("at_25bps", {"cost_bps": 25.0})):
        kw = dict(kw)
        kw.setdefault("cost_bps", bps)
        try:
            bk = evaluate.book(df, col, k=50, weight="vw", ret_col="fwd_1m",
                               mkt_col="mkt_vw_1m", **kw)
        except SystemExit as exc:            # the floor REFUSES without a dv column
            out[label] = {"error": str(exc)}
            continue
        out[label] = {k: bk.get(k) for k in
                      ("months", "terminal_wealth_net",
                       "terminal_wealth_market_same_months", "annualised_excess",
                       "t_stat_paired_vs_market", "rows_after_tradable_floor")}

    net, mkt = ser.get("net"), ser.get("market")
    if net is not None and mkt is not None and len(net) > 5:
        top5 = net.sort_values(ascending=False).head(5).index
        ex = (net - mkt).dropna()
        tot = float(ex.sum())
        out["tail"] = {
            "best_5_months": {str(i): round(float(net.loc[i]), 4) for i in top5},
            "share_of_total_excess_from_those_5": (
                round(float(ex.reindex(top5).dropna().sum() / tot), 4) if tot else None),
            "terminal_wealth_without_them": round(float((1 + net.drop(top5)).prod()), 3),
            "market_terminal_wealth_without_them": round(
                float((1 + mkt.drop(top5)).prod()), 3),
            "note": "35 rows of 46,361 once carried 81% of a result in this repo; "
                    "a fat right tail is a finding about the tail, not about the mean",
        }

    need = ["month", col, "fwd_1m", "mkt_vw_1m", "market_cap", "close",
            "log_dollar_vol_20d"]
    have = [c for c in need if c in df.columns]
    if set(("market_cap", "close", "log_dollar_vol_20d")).issubset(have):
        d = df[have].dropna(subset=[col, "fwd_1m", "mkt_vw_1m"])
        rows = []
        for _m, g in d.groupby("month", sort=True):
            sel = g.nlargest(50, col)
            dv = np.expm1(sel["log_dollar_vol_20d"])
            rows.append((float(sel["market_cap"].median()) / 1e6,
                         float(sel["close"].median()), float(dv.median()),
                         float((sel["close"] < 5).mean()), float((dv < 1e6).mean())))
        if rows:
            a = np.asarray(rows, dtype="float64")
            out["holdings"] = {
                "median_market_cap_musd": round(float(np.median(a[:, 0])), 1),
                "median_close_usd": round(float(np.median(a[:, 1])), 2),
                "median_dollar_volume_usd": round(float(np.median(a[:, 2])), 0),
                "share_of_book_under_5_dollars": round(float(np.median(a[:, 3])), 3),
                "share_of_book_under_1m_dollar_volume": round(float(np.median(a[:, 4])), 3),
                "note": "medians ACROSS MONTHS of the within-month median holding",
            }
    else:
        out["holdings"] = {"verdict": "CANNOT DETERMINE",
                           "why": f"missing {sorted(set(need) - set(have))}"}
    return out


def _spread(series_by_cell: dict) -> dict:
    """min / median / max / sd of a per-seed statistic. The headline, not the max."""
    v = [x for x in series_by_cell.values() if x is not None and np.isfinite(x)]
    if not v:
        return {"n": 0}
    a = np.asarray(v, dtype="float64")
    return {"n": int(len(a)), "min": round(float(a.min()), 4),
            "median": round(float(np.median(a)), 4),
            "max": round(float(a.max()), 4),
            "sd": round(float(a.std(ddof=1)), 4) if len(a) > 1 else 0.0,
            "share_positive": round(float((a > 0).mean()), 4)}


# ------------------------------------------------------------------- the job

def _variant_name(variant: int) -> str:
    return VARIANTS[int(variant) % len(VARIANTS)]


def job(variant: int = 0, *, test_years=None, seeds=None, verbose: bool = True,
        panel: pd.DataFrame | None = None) -> dict:
    """One weekend-lab receipt. Shape matches `scripts.weekend_lab_jobs.W2_*`.

    Variants
    --------
    0 `supervised` -- the baseline: no pre-training, base width.
    1 `pretrained` -- masked-feature pre-training, BOTH scopes (`causal` and
      `all`), so the look-ahead's contribution is a measured number rather than
      an argument.
    2 `quantile`   -- pinball heads at q50 and q90: is the right tail more
      predictable than the mean?
    3 `wide`       -- the same question at 4x trunk width. If the binding
      constraint is tape rather than capacity, this moves nothing, which is
      itself the answer.
    """
    from scripts.weekend_lab_jobs import era_sign_table, verdict_from
    name = _variant_name(variant)
    seeds = list(seeds if seeds is not None else
                 [SEED_BASE + i for i in range(N_SEEDS)])
    test_years = list(test_years if test_years is not None
                      else range(FIRST_TEST_YEAR, LAST_TEST_YEAR + 1))
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)

    try:
        device, dev_info = resolve_device()
    except RuntimeError as exc:
        return {"verdict": "FAILED", "question": "does a neural encoder beat lgbm?",
                "family_id": f"weekend-W3-{name}", "cells_looked_at": 0,
                "inference": {}, "headline": str(exc)}

    df = panel if panel is not None else LP.load_long()
    log(f"W3 {name}: panel {len(df):,} rows, {df['month'].nunique()} months, "
        f"test years {test_years[0]}-{test_years[-1]}, {len(seeds)} seeds, "
        f"device {dev_info['device_actually_used']}")

    # ---- the arms this variant runs
    arms: list[dict] = []
    if name == "supervised":
        arms = [{"tag": "nn", "width": "base", "pretrain": None, "quantiles": None}]
    elif name == "pretrained":
        arms = [{"tag": "nn_pre_causal", "width": "base", "pretrain": "causal",
                 "quantiles": None},
                {"tag": "nn_pre_all", "width": "base", "pretrain": "all",
                 "quantiles": None}]
    elif name == "quantile":
        arms = [{"tag": "nn_q", "width": "base", "pretrain": None,
                 "quantiles": QUANTILES}]
    elif name == "wide":
        arms = [{"tag": "nn_wide", "width": "wide", "pretrain": None,
                 "quantiles": None}]

    run_receipts, pred_cols = {}, {}
    for arm in arms:
        log(f"  arm {arm['tag']} (width {arm['width']}, pretrain {arm['pretrain']})")
        preds, rec = run_neural(df, test_years, seeds=seeds, width=arm["width"],
                                pretrain_scope=arm["pretrain"],
                                quantiles=arm["quantiles"], device=device,
                                device_info=dev_info, verbose=verbose)
        run_receipts[arm["tag"]] = rec
        for key, s in preds.items():
            col = f"{arm['tag']}_{key}"
            df[col] = s.to_numpy()
            pred_cols[col] = arm["tag"]
        # THE SEED-MEAN ENSEMBLE, and it is NOT exempt from the family. It is one
        # more cell that the search looked at, and DSR pays for it like any other.
        for q in (arm["quantiles"] or (None,)):
            member = [f"{arm['tag']}_s{int(s)}" + ("" if q is None else f"_q{int(q*100)}")
                      for s in seeds]
            member = [c for c in member if c in df.columns]
            if len(member) > 1:
                col = (f"{arm['tag']}_seedmean" if q is None
                       else f"{arm['tag']}_seedmean_q{int(q*100)}")
                df[col] = df[member].mean(axis=1, skipna=False)
                pred_cols[col] = arm["tag"]

    log("  lgbm on the same folds ...")
    lgbm_pred, lgbm_rec = run_lgbm(df, test_years, verbose=verbose)
    df["lgbm_raw"] = lgbm_pred.to_numpy()

    # ---- grade every cell
    cells, ex_series, net_series = {}, {}, {}
    for col in list(pred_cols) + ["lgbm_raw"]:
        for bps in COSTS:
            key = f"{col}|{int(bps)}bps"
            try:
                bk = _grade(df, col, bps)
            except Exception as exc:                                # noqa: BLE001
                cells[key] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            ser = bk.get("_series") or {}
            cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
            netv, mkt = ser.get("net"), ser.get("market")
            if netv is not None and mkt is not None and len(netv) \
                    and netv.index.equals(mkt.index):
                ex_series[key] = (netv - mkt).astype("float64")
                net_series[key] = netv.astype("float64")

    neural_keys = [k for k in ex_series if not k.startswith("lgbm_raw|")]
    lgbm_keys = [k for k in ex_series if k.startswith("lgbm_raw|")]
    if not neural_keys or not lgbm_keys:
        return {"verdict": "CANNOT DETERMINE",
                "question": "does a neural encoder beat lgbm on the long panel?",
                "family_id": f"weekend-W3-{name}", "cells_looked_at": len(cells),
                "inference": {}, "cells": cells,
                "headline": "no usable paired series on one of the two legs",
                "device": dev_info, "runs": run_receipts, "lgbm": lgbm_rec}

    # ---- LEG 1: against the MARKET, family = every cell the search looked at
    wide = pd.concat({k: ex_series[k] for k in ex_series}, axis=1).dropna()
    fam = {k: wide[k].tolist() for k in wide.columns}
    best = max([k for k in fam if not k.startswith("lgbm_raw|")],
               key=lambda k: float(np.mean(fam[k])))
    inf_mkt = inference.full_report(fam[best], family=fam, paired_excess=fam,
                                    n_trials=len(cells), n_boot=500, seed=17)
    eras = era_sign_table(wide[best])

    # ---- LEG 2: against LIGHTGBM, paired month by month at the SAME cost rate.
    # Two terminal wealths are one draw of a correlated pair; the difference
    # series is the only honest way to ask "did the neural arm beat lgbm?".
    diff_fam, diff_cells = {}, {}
    for k in neural_keys:
        bps = k.rsplit("|", 1)[-1]
        lk = f"lgbm_raw|{bps}"
        if lk not in net_series:
            continue
        a, b = net_series[k], net_series[lk]
        common = a.index.intersection(b.index)
        if len(common) < 12:
            continue
        d = (a.loc[common] - b.loc[common]).astype("float64")
        diff_fam[k] = d
        mu = float(d.mean())
        sd = float(d.std(ddof=1))
        diff_cells[k] = {
            "months": int(len(d)),
            "mean_monthly_vs_lgbm_pct": round(mu * 100, 4),
            "annualised_vs_lgbm_pct": round(mu * 12 * 100, 3),
            "t_paired_vs_lgbm": (round(mu / (sd / np.sqrt(len(d))), 3)
                                 if sd > 0 else None),
            "months_beating_lgbm": round(float((d > 0).mean()), 4),
        }
    inf_lgbm, best_vs_lgbm = {}, None
    if diff_fam:
        wd = pd.concat(diff_fam, axis=1).dropna()
        if len(wd) >= 12:
            dfam = {k: wd[k].tolist() for k in wd.columns}
            best_vs_lgbm = max(dfam, key=lambda k: float(np.mean(dfam[k])))
            inf_lgbm = inference.full_report(
                dfam[best_vs_lgbm], family=dfam, paired_excess=dfam,
                n_trials=len(cells), n_boot=500, seed=23)

    # ---- the seed spread. A single seed's number is not a result.
    spread = {}
    for arm in arms:
        for bps in COSTS:
            for q in (arm["quantiles"] or (None,)):
                suf = "" if q is None else f"_q{int(q * 100)}"
                keys = [f"{arm['tag']}_s{int(s)}{suf}|{int(bps)}bps" for s in seeds]
                lab = f"{arm['tag']}{suf}|{int(bps)}bps"
                ens = f"{arm['tag']}_seedmean{suf}|{int(bps)}bps"
                spread[lab] = {
                    "per_seed_cells": keys,
                    "annualised_excess_vs_market": _spread(
                        {k: (cells.get(k) or {}).get("annualised_excess") for k in keys}),
                    "terminal_wealth_net": _spread(
                        {k: (cells.get(k) or {}).get("terminal_wealth_net") for k in keys}),
                    "t_paired_vs_market": _spread(
                        {k: (cells.get(k) or {}).get("t_stat_paired_vs_market")
                         for k in keys}),
                    "vs_lgbm_annualised_pct": _spread(
                        {k: (diff_cells.get(k) or {}).get("annualised_vs_lgbm_pct")
                         for k in keys}),
                    "seed_mean_ensemble": {
                        "cell": ens,
                        "annualised_excess": (cells.get(ens) or {}).get("annualised_excess"),
                        "terminal_wealth_net": (cells.get(ens) or {}).get("terminal_wealth_net"),
                        "vs_lgbm_annualised_pct": (diff_cells.get(ens) or {}
                                                   ).get("annualised_vs_lgbm_pct"),
                    },
                }

    # ---- WHAT THE HEADLINE NUMBER IS MADE OF. Computed on the cells the
    # receipt actually names, never on all of them: it is a few seconds each and
    # the point is that no quoted terminal wealth goes out without it.
    rob_cols = {best.rsplit("|", 1)[0]}
    if best_vs_lgbm:
        rob_cols.add(best_vs_lgbm.rsplit("|", 1)[0])
    rob_cols |= {c for c in pred_cols if c.endswith("seedmean")
                 or "_seedmean_q" in c}
    rob_cols.add("lgbm_raw")
    rob = {c: robustness(df, c) for c in sorted(rob_cols) if c in df.columns}

    # THE COMPARISON THAT MATTERS IS THE ONE UNDER THE FLOOR. A neural arm that
    # is 33x the incumbent on paper and behind it once every name has to trade
    # $3m a day has not beaten the incumbent; it has held names the incumbent
    # could not have bought.
    def _tw(c, block):
        return ((rob.get(c) or {}).get(block) or {}).get("terminal_wealth_net")
    bc = best.rsplit("|", 1)[0]
    tw_pl, tw_fl = _tw(bc, "plain"), _tw(bc, "tradable_floor")
    lg_pl, lg_fl = _tw("lgbm_raw", "plain"), _tw("lgbm_raw", "tradable_floor")
    survives = (isinstance(tw_fl, (int, float)) and isinstance(lg_fl, (int, float))
                and tw_fl > lg_fl)
    # AND THE HONEST OBJECT, NOT ONLY THE CHAMPION. The best cell is the top of
    # an 8-draw seed distribution and nobody can pick it in advance; the
    # SEED-MEAN ensemble is what a desk could actually run. On the first full
    # pass they disagreed -- the champion seed cleared the floor (92.8 vs lgbm
    # 59.8) and the ensemble did not (42.8) -- so a receipt that reported only
    # the champion would have read as a pass on a book nobody could have chosen.
    ens_cells = sorted(c for c in rob if c.endswith("seedmean"))
    ens = {}
    for c in ens_cells:
        e_fl = _tw(c, "tradable_floor")
        ens[c] = {
            "terminal_wealth_plain": _tw(c, "plain"),
            "terminal_wealth_under_floor": e_fl,
            "ahead_of_lgbm_under_the_floor": bool(
                isinstance(e_fl, (int, float)) and isinstance(lg_fl, (int, float))
                and e_fl > lg_fl),
        }
    ens_ok = bool(ens) and all(v["ahead_of_lgbm_under_the_floor"] for v in ens.values())
    liq = {
        "best_cell": bc,
        "terminal_wealth_plain": tw_pl,
        "terminal_wealth_under_floor": tw_fl,
        "lgbm_terminal_wealth_plain": lg_pl,
        "lgbm_terminal_wealth_under_floor": lg_fl,
        "still_ahead_of_lgbm_under_the_floor": bool(survives),
        "seed_mean_ensembles": ens,
        "every_ensemble_ahead_of_lgbm_under_the_floor": ens_ok,
        "floor_usd_per_day": TRADABLE_FLOOR_USD,
        "why_the_ensemble_matters": (
            "the best cell is the maximum of an 8-seed draw and is not choosable in "
            "advance; the seed-mean ensemble is the object a desk could run. Where "
            "they disagree, the ensemble is the honest number."),
        "reading": ("the best cell is still ahead of lgbm once every holding must "
                    "trade $3m a day" if survives else
                    "the best cell's lead over lgbm does NOT survive the $3m/day "
                    "execution floor -- the edge is in names the incumbent could "
                    "not have bought"),
    }
    # The verdict's floor leg is judged on the ENSEMBLE where one exists, and on
    # the champion only when there is none.
    survives = ens_ok if ens else survives

    # ---- the verdict. BOTH legs, or it is not a finding.
    base_verdict = verdict_from(inf_mkt, eras)
    beat = _beats_incumbent(inf_lgbm)
    if base_verdict == "NOVEL" and not beat["clears"]:
        verdict = "NOISE (clears the market bar, does NOT beat lgbm)"
    elif base_verdict == "NOVEL" and not survives:
        # Clearing every statistical bar on a book the desk could not have
        # filled is not a finding, and must not be printed as one.
        verdict = "NOISE (clears every bar, dies at the $3m/day execution floor)"
    elif base_verdict == "NOVEL":
        verdict = "NOVEL"
    else:
        verdict = base_verdict

    pw = inf_mkt.get("power", {}) or {}
    lg10 = cells.get("lgbm_raw|10bps") or {}
    bestc = cells.get(best) or {}
    _tail = (rob.get(bc) or {}).get("tail") or {}
    _hold = (rob.get(bc) or {}).get("holdings") or {}
    _tail5 = _tail.get("share_of_total_excess_from_those_5")
    _medv = _hold.get("median_dollar_volume_usd")
    _sub1m = _hold.get("share_of_book_under_1m_dollar_volume")
    headline = (
        f"[{dev_info['device_actually_used']}] best of {len(cells)} cells is {best} "
        f"at {np.mean(fam[best]) * 100:+.3f}%/month vs market over {len(wide)} months "
        f"(TW net {bestc.get('terminal_wealth_net')} vs market "
        f"{bestc.get('terminal_wealth_market_same_months')}); "
        f"DSR {(inf_mkt.get('deflated_sharpe') or {}).get('dsr')}, "
        f"SPA p {(inf_mkt.get('spa') or {}).get('p_spa_consistent')}, "
        f"PBO {(inf_mkt.get('pbo') or {}).get('pbo')}, t2 needs "
        f"{pw.get('years_needed_for_t2')}y vs {pw.get('years_observed')}y on hand. "
        f"vs LGBM (TW {lg10.get('terminal_wealth_net')} @10bps): best neural arm is "
        f"{(diff_cells.get(best_vs_lgbm) or {}).get('annualised_vs_lgbm_pct')}%/yr "
        f"(t {(diff_cells.get(best_vs_lgbm) or {}).get('t_paired_vs_lgbm')}), "
        f"DSR {(inf_lgbm.get('deflated_sharpe') or {}).get('dsr')} -- {beat['reading']}. "
        f"UNDER THE $3m/day FLOOR: best {tw_fl} vs lgbm {lg_fl} (plain {tw_pl} vs "
        f"{lg_pl}); {_tail5} of the excess is 5 months; median holding trades "
        f"${_medv}/day, {_sub1m} of the book under $1m/day")

    return {
        "question": ("does a GPU neural encoder on the 1999-2024 panel beat "
                     "LightGBM on the same walk-forward folds, after the "
                     "multiplicity family?"),
        "family_id": f"weekend-W3-{name}",
        "variant_name": name,
        "cells_looked_at": len(cells),
        "n_common_months": int(len(wide)),
        "common_window": [str(wide.index[0]), str(wide.index[-1])],
        "test_years": [test_years[0], test_years[-1]],
        "panel": "train_table_long.parquet (learner-train-table-3)",
        "device": dev_info,
        "device_warning": dev_info.get("device_warning"),
        "seeds": [int(s) for s in seeds],
        "seed_spread": spread,
        "best_cell": best,
        "best_cell_book": bestc,
        "best_mean_monthly_excess_pct": round(float(np.mean(fam[best])) * 100, 4),
        "cells": cells,
        "inference": inf_mkt,
        "vs_lgbm": {
            "best_cell": best_vs_lgbm,
            "per_cell": diff_cells,
            "inference": inf_lgbm,
            "bar": beat,
            "lgbm_book_10bps": lg10,
            "lgbm_book_25bps": cells.get("lgbm_raw|25bps"),
            "note": ("paired MONTHLY difference of the two books' net returns at the "
                     "same cost rate, on the months both books exist. Two terminal "
                     "wealths are ONE draw of a correlated pair."),
        },
        "era_sign_table": eras,
        "robustness": rob,
        "execution_floor": liq,
        "runs": run_receipts,
        "lgbm": lgbm_rec,
        "leakage_statement": _leakage_statement(),
        "headline": headline,
        "verdict": verdict,
        "licence": "PRODUCT_EXPERIMENT",
    }


def _beats_incumbent(inf_lgbm: dict) -> dict:
    """The extra clause W3 adds to the weekend's four-part bar.

    "Better than the market" is not the question when an incumbent already
    exists on the same folds ([[feedback-ask-better-than-what]]). The neural arm
    clears only if its paired advantage over LightGBM survives the same family
    correction the market leg pays: DSR > 0.95 and SPA p <= 0.10 on the
    DIFFERENCE series.
    """
    if not inf_lgbm:
        return {"clears": False, "reading": "no paired lgbm comparison could be formed"}
    dsr = (inf_lgbm.get("deflated_sharpe") or {}).get("dsr")
    p = (inf_lgbm.get("spa") or {}).get("p_spa_consistent")
    pbo_v = (inf_lgbm.get("pbo") or {}).get("pbo")
    ok = (isinstance(dsr, (int, float)) and dsr >= 0.95
          and isinstance(p, (int, float)) and p <= 0.10
          and (not isinstance(pbo_v, (int, float)) or pbo_v < 0.5))
    return {"clears": bool(ok), "dsr_vs_lgbm": dsr, "spa_p_vs_lgbm": p,
            "pbo_vs_lgbm": pbo_v,
            "rule": "DSR >= 0.95 and SPA p <= 0.10 and PBO < 0.5 on the neural-minus-"
                    "lgbm paired monthly series",
            "reading": ("the neural arm's advantage over lgbm survives the family"
                        if ok else
                        "the neural arm's advantage over lgbm does NOT survive the family")}


def _leakage_statement() -> dict:
    """Said in the receipt, every pass, in the same words -- not in a docstring
    a reader of the JSON will never open."""
    return {
        "supervised_path": (
            "walk-forward by DATE (learner.dataset.walk_forward_splits): a training "
            "row is admitted only if its own target had MATURED before 1 Jan of the "
            "test year. Early stopping uses the last 12 months of the training window "
            "(learner.encoder._inner_split) -- temporal, never random."),
        "pretraining_causal": (
            "masked-feature reconstruction on rows with entry_date < the test year's "
            "1 Jan. No target column is loaded into the pretraining tensor and the "
            "reconstruction loss has none in scope. The impute/scale/clip pipeline is "
            "fitted on the same pre-cutoff rows. STRICTLY POINT-IN-TIME."),
        "pretraining_all": (
            "the same reconstruction over the FEATURE table of all 1999-2024 rows, "
            "targets still absent. THIS IS A MILD LOOK-AHEAD and is labelled one: "
            "knowing the shape of the 1999-2024 feature distribution (that log market "
            "cap drifted up, that vol spiked in 2008 and 2020) is information a 2004 "
            "desk did not have, even though no outcome is in it. The pipeline for this "
            "arm is fitted on all rows too, because a trunk pretrained in one "
            "standardised space cannot be fine-tuned in another. Reported alongside "
            "the causal arm so the advantage it buys is a measured number; a claim may "
            "only be made from the causal arm."),
        "target_handling": (
            "the TRAINING target is standardised on the training rows and clipped at "
            f"+/-{TARGET_CLIP_SD} sd. The EVALUATION target is never clipped anywhere."),
        "seeds": (
            "every seed is its own cell in the multiplicity family, including the "
            "seed-mean ensemble. S36: a model fitted on noise holds one persistent "
            "tilt and a single draw's naive t spans -9..+12."),
    }


def describe() -> dict:
    return {
        "module": "learner.neural_long",
        "question": "does a GPU neural encoder beat lgbm on the long panel, after the family?",
        "reused_from_encoder": ["ClipSD (+/-5 sd on standardised features)",
                                "_inner_split (last-12-months temporal holdout)",
                                "trunk shape Linear->GELU->Dropout->Linear->GELU",
                                "AdamW + early stopping, per-horizon target standardisation",
                                "median impute -> standardise -> clip pipeline order"],
        "changed_from_encoder": [
            "one horizon (1m) instead of four -- the multi-horizon claim is not "
            "what is being tested and would cost multiplicity",
            "target clipped at +/-5 sd rather than winsorised at the 1/99 percentile",
            f"{N_SEEDS} seeds always, spread reported, every seed a family cell",
            "masked-feature self-supervised pre-training (two scopes)",
            "GPU, with the device actually used recorded in every receipt"],
        "variants": list(VARIANTS),
        "seeds": N_SEEDS, "costs_bps": list(COSTS), "horizon_months": HORIZON,
        "widths": {k: list(v) for k, v in WIDTHS.items()},
        "quantiles": list(QUANTILES),
        "bar": ("the four-part weekend bar against the MARKET (DSR > 0.95, SPA p < 0.10, "
                "PBO < 0.5, sign in >= 2 of 3 eras) AND the same DSR/SPA/PBO bar on the "
                "neural-minus-lgbm paired monthly series AND still ahead of lgbm once "
                f"every holding must trade ${TRADABLE_FLOOR_USD:,.0f} a day"),
        "robustness_block": (
            "every receipt re-grades the cells it names under the house execution floor "
            "and at 25 bps, prints the five best months' share of the total excess, and "
            "prints what the book HELD (median cap, price, dollar volume). Added after "
            "the first full pass produced a 561x terminal wealth whose median holding "
            "traded $1.07m a day: 50% of that book sat below the $3m/day floor, 43% of "
            "its excess was five months, and imposing the floor cut it to 93x while "
            "RAISING lgbm's from 16.8 to 59.8."),
        "leakage": _leakage_statement(),
        "torch_available": _TORCH,
    }


__all__ = ["job", "describe", "run_neural", "run_lgbm", "resolve_device",
           "make_pipeline", "feature_cols", "pretrain", "train_head", "TrunkNet",
           "robustness", "VARIANTS", "QUANTILES", "WIDTHS", "SEED_BASE", "N_SEEDS",
           "COSTS", "HORIZON", "TARGET_CLIP_SD", "CLIP_SD", "TRADABLE_FLOOR_USD",
           "FIRST_TEST_YEAR", "LAST_TEST_YEAR"]


def main(argv=None) -> int:                        # pragma: no cover - CLI
    import argparse
    import json
    ap = argparse.ArgumentParser(description="W3: the neural arm on the long panel")
    ap.add_argument("--variant", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=N_SEEDS)
    ap.add_argument("--first-year", type=int, default=FIRST_TEST_YEAR)
    ap.add_argument("--last-year", type=int, default=LAST_TEST_YEAR)
    ap.add_argument("--out", default=None)
    ap.add_argument("--describe", action="store_true")
    a = ap.parse_args(argv)
    if a.describe:
        print(json.dumps(describe(), indent=1))
        return 0
    r = job(a.variant, seeds=[SEED_BASE + i for i in range(a.seeds)],
            test_years=list(range(a.first_year, a.last_year + 1)))
    if a.out:
        from pathlib import Path
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    print(f"{r.get('verdict')} -- {r.get('headline')}")
    return 0


if __name__ == "__main__":                         # pragma: no cover
    raise SystemExit(main())
