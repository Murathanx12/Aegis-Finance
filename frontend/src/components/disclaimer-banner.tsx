"use client";

import { AlertTriangle } from "lucide-react";
import { isPersonalMode } from "@/lib/personal-mode";

export function DisclaimerBanner() {
  // Personal mode (chunk 17): the whole of this banner is the disclaimer, so
  // the whole of it goes. Every other surface drops only its advice sentence
  // and keeps what it says about the model.
  if (isPersonalMode()) return null;
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 flex items-center gap-2 text-xs text-amber-400/80">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
      <span>
        Educational tool only. Not financial advice. All predictions are probabilistic estimates with significant uncertainty.
      </span>
    </div>
  );
}
