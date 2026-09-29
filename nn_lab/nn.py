"""The network: a small MLP that predicts a DISTRIBUTION per horizon.

For each horizon h in (5, 21, 63) it emits
    mean     -- expected excess return over the cross-sectional median
    q05..q95 -- five quantiles (non-crossing by construction)
    logit    -- log-odds that the name beats the median
Loss = Huber(mean) + pinball(quantiles) + 0.5 * BCE(logit). The `rank` variant
replaces the Huber term with a per-date ListNet loss (plus a 0.1 Huber anchor so
the mean keeps return units).

Small on purpose: 3 hidden layers, dropout, weight decay, early stopping on a
validation block that is strictly earlier than any test block (splits.py).
"""
from __future__ import annotations

import copy
import math

import numpy as np

from nn_lab import config as C

TAUS = (0.05, 0.25, 0.5, 0.75, 0.95)
NH = len(C.HORIZONS)


def _torch():
    import torch
    return torch


def build_net(n_in: int, hidden=(256, 128, 64), dropout: float = 0.15):
    torch = _torch()
    nn = torch.nn

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            layers, d = [], n_in
            for h in hidden:
                layers += [nn.Linear(d, h), nn.SiLU(), nn.Dropout(dropout)]
                d = h
            self.trunk = nn.Sequential(*layers)
            self.head = nn.Linear(d, NH * 7)   # mean, q50, 4 gaps, logit

        def forward(self, x):
            o = self.head(self.trunk(x)).view(-1, NH, 7)
            sp = torch.nn.functional.softplus
            mean, q50, logit = o[..., 0], o[..., 1], o[..., 6]
            q25 = q50 - sp(o[..., 2]); q05 = q25 - sp(o[..., 3])
            q75 = q50 + sp(o[..., 4]); q95 = q75 + sp(o[..., 5])
            q = torch.stack([q05, q25, q50, q75, q95], dim=-1)
            return mean, q, logit
    return Net()


def date_ranges(codes: np.ndarray) -> list[tuple[int, int]]:
    bounds = np.flatnonzero(np.diff(codes)) + 1
    return list(zip(np.r_[0, bounds].tolist(), np.r_[bounds, len(codes)].tolist()))


def _date_batches(codes: np.ndarray, per_batch: int, rng: np.random.Generator):
    """Row ranges covering `per_batch` whole dates (rows sorted by date)."""
    rr = date_ranges(codes)
    order = rng.permutation(len(rr))
    for i in range(0, len(order), per_batch):
        yield [rr[j] for j in order[i:i + per_batch]]


def ic_by_date(score: np.ndarray, y: np.ndarray, codes: np.ndarray) -> float:
    ics = []
    for s, e in date_ranges(codes):
        a, b = score[s:e], y[s:e]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 20:
            continue
        ra = np.argsort(np.argsort(a[m])); rb = np.argsort(np.argsort(b[m]))
        ics.append(np.corrcoef(ra, rb)[0, 1])
    return float(np.mean(ics)) if ics else float("nan")


class Trainer:
    def __init__(self, n_in: int, *, seed: int, variant: str = "dist", lr: float = 1e-3,
                 weight_decay: float = 1e-4, max_epochs: int = 15, patience: int = 3,
                 dates_per_batch: int = 8, device: str | None = None):
        torch = _torch()
        self.torch = torch
        self.seed = int(seed)
        self.variant = variant
        torch.manual_seed(self.seed)
        self.rng = np.random.default_rng(self.seed)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.net = build_net(n_in).to(self.device)
        self.opt = torch.optim.AdamW(self.net.parameters(), lr=lr, weight_decay=weight_decay)
        self.max_epochs, self.patience, self.dpb = max_epochs, patience, dates_per_batch
        self.scale = np.ones(NH, dtype="float32")
        self.history: list[dict] = []
        self.n_in = n_in

    def _loss(self, mean, q, logit, y, ranges):
        torch = self.torch
        F = torch.nn.functional
        mask = torch.isfinite(y)
        y0 = torch.where(mask, y, torch.zeros_like(y))
        mf = mask.float()
        n = mf.sum().clamp(min=1.0)
        hub = (F.huber_loss(mean, y0, reduction="none", delta=1.0) * mf).sum() / n
        taus = torch.tensor(TAUS, device=y.device).view(1, 1, -1)
        diff = y0.unsqueeze(-1) - q
        pin = (torch.maximum(taus * diff, (taus - 1) * diff) * mf.unsqueeze(-1)).sum() / n
        bce = (F.binary_cross_entropy_with_logits(logit, (y0 > 0).float(), reduction="none") * mf).sum() / n
        if self.variant == "rank":
            ln, cnt = 0.0, 0
            for s, e in ranges:
                for h in range(NH):
                    m = mask[s:e, h]
                    if int(m.sum()) < 20:
                        continue
                    yt = y[s:e, h][m]
                    r = torch.argsort(torch.argsort(yt)).float()
                    z = (r - r.mean()) / (r.std() + 1e-6)
                    tgt = torch.softmax(2.0 * z, dim=0)
                    ln = ln - (tgt * torch.log_softmax(mean[s:e, h][m], dim=0)).sum()
                    cnt += 1
            ln = ln / max(cnt, 1)
            return ln + 0.1 * hub + pin + 0.5 * bce
        return hub + pin + 0.5 * bce

    def fit(self, Xtr, Ytr, ctr, Xva, Yva, cva) -> dict:
        torch = self.torch
        self.scale = np.nanstd(Ytr, axis=0).astype("float32")
        self.scale[~np.isfinite(self.scale) | (self.scale <= 0)] = 1.0
        Xt = torch.tensor(Xtr, device=self.device)
        Yt = torch.tensor(Ytr / self.scale, device=self.device)
        best, best_state, bad = -math.inf, None, 0
        for ep in range(self.max_epochs):
            self.net.train(True)
            tot, nb = 0.0, 0
            for batch in _date_batches(ctr, self.dpb, self.rng):
                idx = np.concatenate([np.arange(s, e) for s, e in batch])
                it = torch.tensor(idx, device=self.device)
                xb, yb = Xt[it], Yt[it]
                ranges, off = [], 0
                for s, e in batch:
                    ranges.append((off, off + (e - s)))
                    off += e - s
                mean, q, logit = self.net(xb)
                loss = self._loss(mean, q, logit, yb, ranges)
                self.opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                self.opt.step()
                tot += loss.item()
                nb += 1
            p = self.predict(Xva)
            val_ic = float(np.nanmean([ic_by_date(p["mean"][:, h], Yva[:, h], cva) for h in range(NH)]))
            self.history.append({"epoch": ep, "train_loss": round(tot / max(nb, 1), 5),
                                 "val_ic": round(val_ic, 5)})
            if val_ic > best + 1e-5:
                best, best_state, bad = val_ic, copy.deepcopy(self.net.state_dict()), 0
            else:
                bad += 1
                if bad >= self.patience:
                    break
        if best_state is not None:
            self.net.load_state_dict(best_state)
        del Xt, Yt
        return {"best_val_ic_mean_over_horizons": round(best, 5), "epochs": len(self.history),
                "history": self.history, "seed": self.seed, "variant": self.variant}

    def fit_fixed(self, Xtr, Ytr, ctr, epochs: int) -> dict:
        """Train a FIXED number of epochs on all rows, no validation block (review F5.4:
        the early-stopped model never saw its last validation block + embargo, ten months
        stale; the nightly refits on train+val with the epoch count early stopping chose)."""
        torch = self.torch
        self.scale = np.nanstd(Ytr, axis=0).astype("float32")
        self.scale[~np.isfinite(self.scale) | (self.scale <= 0)] = 1.0
        Xt = torch.tensor(Xtr, device=self.device)
        Yt = torch.tensor(Ytr / self.scale, device=self.device)
        for ep in range(max(1, int(epochs))):
            self.net.train(True)
            for batch in _date_batches(ctr, self.dpb, self.rng):
                idx = np.concatenate([np.arange(s, e) for s, e in batch])
                it = torch.tensor(idx, device=self.device)
                ranges, off = [], 0
                for s, e in batch:
                    ranges.append((off, off + (e - s)))
                    off += e - s
                mean, q, logit = self.net(Xt[it])
                loss = self._loss(mean, q, logit, Yt[it], ranges)
                self.opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                self.opt.step()
        del Xt, Yt
        return {"epochs": int(epochs), "seed": self.seed, "variant": self.variant, "refit": "train+val"}

    def predict(self, X, chunk: int = 200_000) -> dict:
        torch = self.torch
        self.net.train(False)   # inference mode: dropout off
        outs = {"mean": [], "q": [], "prob": []}
        with torch.no_grad():
            for i in range(0, len(X), chunk):
                xb = torch.tensor(X[i:i + chunk], device=self.device)
                mean, q, logit = self.net(xb)
                outs["mean"].append(mean.cpu().numpy())
                outs["q"].append(q.cpu().numpy())
                outs["prob"].append(torch.sigmoid(logit).cpu().numpy())
        sc = self.scale
        return {"mean": np.concatenate(outs["mean"]) * sc,
                "q": np.concatenate(outs["q"]) * sc[None, :, None],
                "prob": np.concatenate(outs["prob"])}

    def save(self, path) -> None:
        self.torch.save({"state_dict": self.net.state_dict(), "scale": self.scale.tolist(),
                         "seed": self.seed, "variant": self.variant, "n_in": self.n_in}, path)

    @classmethod
    def load(cls, path) -> "Trainer":
        torch = _torch()
        blob = torch.load(path, map_location="cpu", weights_only=False)
        t = cls(blob["n_in"], seed=blob["seed"], variant=blob["variant"])
        t.net.load_state_dict(blob["state_dict"])
        t.scale = np.asarray(blob["scale"], dtype="float32")
        return t


def ensemble_predict(trainers: list, X) -> dict:
    ps = [t.predict(X) for t in trainers]
    return {k: np.mean([p[k] for p in ps], axis=0) for k in ps[0]}
