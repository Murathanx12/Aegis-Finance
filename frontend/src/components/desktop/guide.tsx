"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  CircleQuestionMark,
  MessageSquare,
  Moon,
  Server,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * The first-run guide for Aegis Desktop.
 *
 * Every sentence below is a claim about `backend/routers/control.py` and the
 * four pages under `app/desktop/`, and each one is true of that code as read on
 * 2026-09-10. Nothing here describes a feature that does not exist: a guide that
 * promises a button the app does not have is the same failure as a page that
 * prints a number nobody measured.
 *
 * The dismissal key is VERSIONED. When the guide changes materially the version
 * is bumped and everyone sees the new one exactly once — a permanently
 * dismissed guide is a guide that can never be corrected.
 */
export const GUIDE_DISMISSED_KEY = "aegis.guide.dismissed.v1";

/**
 * Read the dismissal flag, or decide it is absent.
 *
 * `localStorage` is not a reliable object. A private window, cleared site data,
 * and a browser configured to block site data each make the ACCESSOR ITSELF
 * throw — not the read, the property lookup — and an uncaught throw during
 * render takes the whole desktop shell down. So both directions are wrapped and
 * every failure resolves to "not dismissed", which shows the guide one extra
 * time and never breaks a page.
 */
function readDismissed(): boolean {
  try {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(GUIDE_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeDismissed(dismissed: boolean): void {
  try {
    if (typeof window === "undefined") return;
    if (dismissed) window.localStorage.setItem(GUIDE_DISMISSED_KEY, "1");
    else window.localStorage.removeItem(GUIDE_DISMISSED_KEY);
  } catch {
    /* storage refused the write: the guide simply appears again next launch */
  }
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-1.5">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        <Icon className="size-3.5 text-muted-foreground" />
        {title}
      </h3>
      <div className="space-y-1.5 text-xs leading-relaxed text-muted-foreground">
        {children}
      </div>
    </section>
  );
}

export function DesktopGuide() {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // First visit only, and only after mount — `localStorage` does not exist
  // during the static export's prerender, and touching it there would make the
  // exported HTML depend on a browser that is not present.
  useEffect(() => {
    const already = readDismissed();
    setDismissed(already);
    if (!already) setOpen(true);
  }, []);

  // Reopening re-reads the stored flag, so the checkbox shows the real state
  // rather than whatever this tab last held in memory.
  const openDeliberately = useCallback(() => {
    setDismissed(readDismissed());
    setOpen(true);
  }, []);

  const toggleDismissed = useCallback((next: boolean) => {
    setDismissed(next);
    writeDismissed(next);
  }, []);

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={openDeliberately}
        aria-haspopup="dialog"
        title="What this app is, and what each tab does"
        className="text-muted-foreground"
      >
        <CircleQuestionMark className="size-3.5" />
        Guide
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        {/* Radix owns Escape-to-close, the focus trap while open, and returning
            focus to the trigger on close. Nothing here re-implements any of it. */}
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Aegis Desktop — what this is</DialogTitle>
            <DialogDescription>
              Four operator pages over this machine&apos;s repository. Read it
              once; the <span className="font-medium">Guide</span> button in the
              tab bar brings it back.
            </DialogDescription>
          </DialogHeader>

          <div className="max-h-[62vh] space-y-4 overflow-y-auto px-5 py-4">
            <div className="rounded-lg border border-border bg-muted/40 p-3 text-xs leading-relaxed">
              <p>
                <span className="font-semibold text-foreground">
                  Everything here runs on this PC, and costs $0.
                </span>{" "}
                The assistant answers on a local model server on this machine
                (default{" "}
                <span className="font-mono">http://127.0.0.1:8080</span>), which
                is why the answer endpoint reports a cost of exactly zero. No
                provider is billed for anything on these pages.
              </p>
              <p className="mt-2">
                <span className="font-semibold text-foreground">
                  The app reads this machine&apos;s repository.
                </span>{" "}
                Night receipts, the leaderboard and the lane NAVs come from the
                checkout on this disk, and every page calls{" "}
                <span className="font-mono">/api/control/*</span> on the same
                origin that served it. There is no cloud round-trip. The one
                exception is paper-account data, which originates at the
                brokerage — and even that is read from what the trading loops
                already wrote here; this app never calls a venue and never places
                an order.
              </p>
            </div>

            <Section icon={Server} title="Services — what is running">
              <p>
                Lists what the control plane has started, each with the PID it
                was registered under, its log size, and when that log last moved.
                It also shows the local AI model server, with{" "}
                <span className="font-medium">Start</span> and{" "}
                <span className="font-medium">Stop</span> buttons.
              </p>
              <p>
                <span className="font-medium text-foreground">
                  Stopping the model frees the VRAM it is holding
                </span>{" "}
                — the card shows how much is in use when the driver reports it.
                Start it again when you next want to ask something; a cold start
                loads several GB from disk, so the page distinguishes{" "}
                <span className="font-mono">listening</span> (the port is bound)
                from <span className="font-mono">ready</span> (it answers).
              </p>
              <p>
                <span className="font-medium text-foreground">
                  A server Aegis did not start needs an explicit confirm.
                </span>{" "}
                The first Stop click on such a process comes back as a question
                rather than an error, because that server may be several GB into
                somebody else&apos;s job. You are shown what it is, and only a
                second, deliberate click stops it.
              </p>
            </Section>

            <Section icon={Moon} title="Night runs — the queue and its receipts">
              <p>
                The leaderboard of night-job receipts, shown as the markdown the
                night factory itself wrote, with a count of the{" "}
                <span className="font-mono">*_run*.json</span> receipts beside
                it. It is not re-parsed into numbers here — a headline number
                belongs to its receipt, not to a second copy in a web page.
              </p>
              <p>
                One click runs tonight&apos;s whole queue in order; individual
                jobs can also be launched on their own. Only job ids the backend
                whitelists can be started — there is no free-text command box.
              </p>
              <p>
                A live tail of the running job&apos;s log refreshes while it
                runs, and{" "}
                <span className="font-medium text-foreground">
                  stopping is by PID
                </span>
                : a STOP file is written first, which ends the queue cleanly
                between jobs, and only a PID this control plane itself registered
                is ever signalled. Nothing is killed by process name.
              </p>
            </Section>

            <Section icon={Activity} title="Fleet vs SPY — paper-lane performance">
              <p>
                Each paper lane against the declared benchmark series, with its
                NAV, its since-inception return, and its mean daily excess.
              </p>
              <p>
                <span className="font-medium text-foreground">
                  Every mean carries its standard error and the number of paired
                  sessions it was computed from.
                </span>{" "}
                Where the backend says a row is below the observation floor, the
                page prints{" "}
                <span className="font-medium text-foreground">
                  &ldquo;not estimable&rdquo;
                </span>{" "}
                together with the reason it gave — never a bare number, not even
                a greyed-out one. A handful of sessions cannot separate an excess
                from zero, and this page says so instead of quoting the figure
                anyway.
              </p>
              <p>
                Read the benchmark label before reading the excess: the
                comparison series is a control lane by default, not literally
                SPY, and the payload states which one it used.
              </p>
            </Section>

            <Section
              icon={MessageSquare}
              title="Ask Aegis — a reader, and only a reader"
            >
              <p>
                A local model that is handed the newest night leaderboards and
                answers questions about them. Those receipts are its only source
                of numbers; asked for one it was not given, it is instructed to
                say it does not have it.
              </p>
              <p>
                <span className="font-medium text-foreground">
                  It cannot run a job, seal a book, arm a lane, size a position
                  or place an order.
                </span>{" "}
                This is an invariant, not a disclaimer: there is no code path
                from the assistant to any of those, and a test walks the control
                router&apos;s source and fails if a broker or order symbol ever
                appears in it.
              </p>
              <p>
                If the model is not ready you get a refusal that names the fix —
                start it on the Services tab — rather than a blank answer.
              </p>
            </Section>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3">
            <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={dismissed}
                onChange={(e) => toggleDismissed(e.target.checked)}
                className="size-3.5 cursor-pointer accent-primary focus-visible:ring-2 focus-visible:ring-ring"
              />
              Don&apos;t show this again
            </label>
            <Button size="sm" onClick={() => setOpen(false)}>
              Got it
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
