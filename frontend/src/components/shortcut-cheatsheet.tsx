"use client";

import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { allCommands } from "@/lib/commands";

const SHORTCUTS = [
  { keys: ["Ctrl", "K"], desc: "Open command palette" },
  { keys: ["/"], desc: "Open command palette (alt)" },
  { keys: ["?"], desc: "Show this cheatsheet" },
  { keys: ["g", "h"], desc: "Go to Dashboard" },
  { keys: ["g", "p"], desc: "Go to Portfolio" },
  { keys: ["g", "s"], desc: "Go to Screener" },
  { keys: ["g", "n"], desc: "Go to News" },
  { keys: ["g", "o"], desc: "Go to Outlook" },
  { keys: ["g", "c"], desc: "Go to Crash Risk" },
  { keys: ["g", "k"], desc: "Go to Copilot" },
  { keys: ["g", "r"], desc: "Go to Retirement" },
  { keys: ["g", "w"], desc: "Go to Workspace" },
  { keys: ["g", "l"], desc: "Go to Watchlist" },
  { keys: ["Esc"], desc: "Close open dialog" },
];

export function ShortcutCheatsheet({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <div className="px-5 py-4 border-b border-border">
          <DialogTitle className="text-base font-semibold">Keyboard shortcuts</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground mt-0.5">
            Bloomberg-style navigation. Press the function code from anywhere.
          </DialogDescription>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-0 divide-y md:divide-y-0 md:divide-x divide-border">
          <div className="p-5 space-y-2">
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Navigation
            </h3>
            {SHORTCUTS.map((s) => (
              <div key={s.desc} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{s.desc}</span>
                <div className="flex gap-1">
                  {s.keys.map((k, i) => (
                    <kbd
                      key={i}
                      className="inline-flex min-w-6 justify-center items-center rounded border border-border bg-muted/50 px-1.5 py-0.5 font-mono text-[11px]"
                    >
                      {k}
                    </kbd>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="p-5 space-y-2">
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Function codes
            </h3>
            <p className="text-xs text-muted-foreground mb-2">
              Type any of these in the palette, with or without a ticker:
            </p>
            <div className="grid grid-cols-2 gap-y-1 gap-x-3 text-sm">
              {allCommands().map((c) => (
                <div key={c.code} className="flex items-center gap-2 min-w-0">
                  <kbd className="inline-flex min-w-10 justify-center rounded border border-border bg-muted/50 px-1.5 py-0.5 font-mono text-[11px]">
                    {c.code}
                  </kbd>
                  <span className="truncate text-muted-foreground">{c.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="border-t border-border px-5 py-3 text-[11px] text-muted-foreground">
          Shortcuts are disabled while typing in a form field (except Ctrl/Cmd+K and Esc).
        </div>
      </DialogContent>
    </Dialog>
  );
}
