"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquarePlus, Save, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CONTROL_PLANE_BUILD,
  errorText,
  getOwnerNotes,
  postOwnerNote,
  type OwnerNote,
} from "@/lib/control-api";

/**
 * "Note to Claude" (CH-22, 2026-11-14).
 *
 * The owner asked for a box where "when I write something there it
 * automatically sends to you directly, or saves it to the cache so you can open
 * it". There is no channel from this app to a Claude session, so the box does
 * the second thing, honestly: it appends one row to
 * `<optimus>/owner_inbox/notes.jsonl`, and the next brain session reads it with
 * `python -m scripts.owner_inbox list --unread`. No model answers it here.
 *
 * Success is shown only with the saved row's own time, read back from the
 * server's answer; a failure shows the server's error text. Never a fake "sent".
 */

/** Mirrors `backend/config.py::OWNER_INBOX_MAX_CHARS`; the server is the one that refuses. */
const OWNER_NOTE_MAX = 8000;

function fmtTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
}

function RecentNotes({ enabled }: { enabled: boolean }) {
  const notes = useQuery({
    queryKey: ["control", "owner-notes", 5],
    queryFn: () => getOwnerNotes(5),
    enabled,
    retry: false,
    staleTime: 0,
  });
  if (!enabled) return null;
  if (notes.isLoading) return <p className="text-xs text-muted-foreground">loading your last notes…</p>;
  if (notes.isError)
    return (
      <p className="text-xs text-red-500" role="alert">
        Could not read the notes: {errorText(notes.error)}
      </p>
    );
  const d = notes.data;
  if (!d || d.notes.length === 0)
    return <p className="text-xs text-muted-foreground">No notes yet.</p>;
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] text-muted-foreground">
        Last {d.notes.length} of {d.n_notes} · {d.n_unread} not yet read by Claude
      </p>
      <ul className="max-h-48 space-y-1 overflow-auto">
        {d.notes.map((n: OwnerNote) => (
          <li key={n.id} className="rounded-md border border-border px-2 py-1 text-xs">
            <div className="mb-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Badge variant={n.status === "unread" ? "secondary" : "outline"} className="text-[10px]">
                {n.status === "unread" ? "unread" : "read by Claude"}
              </Badge>
              <span>{fmtTime(n.utc)}</span>
              {n.page ? <span className="font-mono">{n.page}</span> : null}
            </div>
            <p className="line-clamp-3 whitespace-pre-wrap break-words">{n.text}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The form + the last five notes. Used by the floating button and by /desktop/ask. */
export function OwnerNoteForm({ autoFocus = false }: { autoFocus?: boolean }) {
  const pathname = usePathname();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const save = useMutation({
    mutationFn: (t: string) => postOwnerNote(t, pathname ?? null),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["control", "owner-notes"] });
    },
  });
  const trimmed = text.trim();
  const tooLong = trimmed.length > OWNER_NOTE_MAX;

  return (
    <div className="space-y-2">
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!trimmed || save.isPending) return;
          save.mutate(text);
        }}
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus={autoFocus}
          rows={4}
          placeholder="Write to the Claude session — an idea, a stock to look at, something that looks wrong…"
          aria-label="note to Claude"
          className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" disabled={!trimmed || tooLong || save.isPending}>
            <Save className="size-3.5" />
            {save.isPending ? "Saving…" : "Save note"}
          </Button>
          <span className={cn("text-[11px] text-muted-foreground", tooLong && "text-red-500")}>
            {trimmed.length} / {OWNER_NOTE_MAX}
          </span>
        </div>
      </form>
      {save.isSuccess && save.data?.note ? (
        <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-xs" role="status">
          Saved — Claude reads this at the start of the next session. Saved at{" "}
          {fmtTime(save.data.note.utc)}.
        </p>
      ) : null}
      {save.isError ? (
        <p className="rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs text-red-500" role="alert">
          Not saved: {errorText(save.error)}
        </p>
      ) : null}
      <RecentNotes enabled />
    </div>
  );
}

/** Bottom-right on every page, only in the desktop build (see CONTROL_PLANE_BUILD). */
export function OwnerNoteButton() {
  const [open, setOpen] = useState(false);
  if (!CONTROL_PLANE_BUILD) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-2">
      {open ? (
        <div className="w-[min(380px,calc(100vw-2rem))] rounded-xl border border-border bg-background p-3 shadow-xl">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-semibold">Note to Claude</p>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="close the note box"
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
          <p className="mb-2 text-[11px] text-muted-foreground">
            Saved on this PC for the next Claude session. Nothing is sent and nothing answers here.
          </p>
          <OwnerNoteForm autoFocus />
        </div>
      ) : null}
      <Button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="rounded-full shadow-lg"
        aria-expanded={open}
      >
        <MessageSquarePlus className="size-4" />
        Note to Claude
      </Button>
    </div>
  );
}
