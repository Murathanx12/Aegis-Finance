import { Card, CardContent } from "@/components/ui/card";
import { isPersonalMode } from "@/lib/personal-mode";

/**
 * Shared label for every page whose numbers come from a backtest/replay,
 * NOT from the live forward NAV. Exact copy is governed by
 * docs/TRACK_RECORD_POLICY.md — change it there first.
 *
 * Personal mode (chunk 17) drops the closing advice sentence and NOTHING else.
 * "Backtest, not the track record", the survivorship caveat and the 24-month
 * no-skill-claims rule are findings about the numbers on the page — they are
 * the reason this banner exists, and they are exactly as true for the one
 * person running the personal build as for anybody else.
 */
export function MethodologyBanner() {
  return (
    <Card className="border-amber-500/30 bg-amber-500/5">
      <CardContent className="py-3">
        <p className="text-xs text-amber-400/80">
          <span className="font-semibold">Backtest, not the track record.</span>{" "}
          Numbers on this page are simulated by replaying today&rsquo;s rules over
          2021&ndash;2025 with a fixed universe (survivorship caveat:
          docs/replay_diagnostics_v1.md). Aegis&rsquo;s real performance record is
          the live forward paper-portfolio NAV, marked daily since 2026-06-08 &mdash;
          it is young, and we make no skill claims before 24 months of tracked
          decisions.{isPersonalMode() ? "" : " Educational tool, not financial advice."}
        </p>
      </CardContent>
    </Card>
  );
}
