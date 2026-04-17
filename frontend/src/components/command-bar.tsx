"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  CommandDef,
  parseCommand,
  searchCommands,
  allCommands,
} from "@/lib/commands";

type Mode = "search" | "grammar";

/**
 * Global Ctrl/Cmd-K command palette.
 *
 * Two modes, switched by whether the input starts with a space or contains
 * a space between a function code and a ticker:
 *   - "grammar": typing `AAPL GP`, `PORT`, `ECO`, `NI AAPL` — ENTER executes
 *     the parsed action.
 *   - "search": typing `eco`, `screener`, `news` — ARROW keys navigate
 *     the matching function list, ENTER opens the selected one.
 * Both modes coexist — we show ranked suggestions AND attempt to parse
 * on enter, picking whichever gives a concrete action.
 */
export function CommandBar({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const [index, setIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Reset state every time the palette opens
  React.useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      // Focus the input on the next tick so radix has mounted it
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const suggestions: CommandDef[] = React.useMemo(() => {
    return query ? searchCommands(query, 8) : allCommands().slice(0, 8);
  }, [query]);

  React.useEffect(() => {
    setIndex(0);
  }, [query]);

  const mode: Mode = query.includes(" ") ? "grammar" : "search";
  const parsed = React.useMemo(() => (query ? parseCommand(query) : null), [query]);

  const executeSelected = () => {
    // Grammar parse wins when it succeeds (e.g. "AAPL GP" vs fuzzy match)
    if (parsed) {
      router.push(parsed.href);
      onOpenChange(false);
      return;
    }
    const choice = suggestions[index];
    if (!choice) return;
    if (choice.needsTicker) {
      // Let the user type the ticker — fill the input
      setQuery(choice.code + " ");
      return;
    }
    const href =
      typeof choice.href === "function" ? choice.href() : choice.href;
    router.push(href);
    onOpenChange(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      executeSelected();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="top-[10%] p-0 overflow-hidden max-w-xl"
        aria-describedby="command-bar-desc"
        showCloseButton={false}
      >
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <DialogDescription id="command-bar-desc" className="sr-only">
          Type a function code like PORT, EQS, GP AAPL, or a ticker like NVDA.
        </DialogDescription>
        <div className="border-b border-border">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a function (PORT, EQS, ECO) or ticker (AAPL, SPY AAPL GP)…"
            className={cn(
              "w-full bg-transparent px-4 py-3 text-base",
              "focus:outline-none placeholder:text-muted-foreground",
            )}
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
          />
        </div>
        <div className="max-h-[360px] overflow-y-auto py-2">
          {parsed && mode === "grammar" && (
            <button
              onClick={executeSelected}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-accent"
            >
              <span className="inline-flex h-6 min-w-12 items-center justify-center rounded bg-primary/10 px-2 font-mono text-xs font-semibold text-primary">
                {parsed.functionCode ?? "GO"}
              </span>
              <span className="flex-1 text-sm">{parsed.label}</span>
              <span className="text-xs text-muted-foreground">enter ↵</span>
            </button>
          )}
          {suggestions.length === 0 && !parsed && (
            <p className="px-4 py-6 text-sm text-muted-foreground">
              No functions match. Try <code className="font-mono">PORT</code>,{" "}
              <code className="font-mono">EQS</code>,{" "}
              <code className="font-mono">NI AAPL</code>, or{" "}
              <code className="font-mono">?</code> for help.
            </p>
          )}
          {suggestions.map((def, i) => (
            <button
              key={def.code}
              onMouseEnter={() => setIndex(i)}
              onClick={() => {
                setIndex(i);
                executeSelected();
              }}
              className={cn(
                "flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors",
                i === index ? "bg-accent" : "hover:bg-accent/60",
              )}
            >
              <span
                className={cn(
                  "inline-flex h-6 min-w-12 items-center justify-center rounded px-2 font-mono text-xs font-semibold",
                  i === index
                    ? "bg-primary/15 text-primary"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {def.code}
              </span>
              <span className="flex-1">
                <span className="block text-sm font-medium">{def.label}</span>
                <span className="block text-xs text-muted-foreground truncate">
                  {def.description}
                </span>
              </span>
              {def.needsTicker && (
                <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  needs ticker
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground flex items-center justify-between">
          <span className="font-mono">↑↓ navigate · ↵ open · esc close</span>
          <span className="font-mono">Ctrl+K anywhere</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
