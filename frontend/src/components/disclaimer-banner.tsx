"use client";

import { AlertTriangle } from "lucide-react";

export function DisclaimerBanner() {
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 flex items-center gap-2 text-xs text-amber-400/80">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
      <span>
        Educational tool only. Not financial advice. All predictions are probabilistic estimates with significant uncertainty.
      </span>
    </div>
  );
}
