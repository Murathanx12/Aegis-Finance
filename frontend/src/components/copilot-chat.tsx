"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Sparkles, Wrench, AlertTriangle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { copilotChat, copilotStatus, type CopilotMessage } from "@/lib/api";

const SUGGESTED_QUESTIONS = [
  "How's the market regime right now?",
  "Compare the 60/40 vs all-weather backtests.",
  "Score AAPL — style box, grades, short interest.",
  "Which sectors are leading this rotation?",
  "What's the crash probability at the 3-month horizon?",
];

type ChatEntry = CopilotMessage & { toolCalls?: { name: string; result_preview: string }[] };

export function CopilotChat() {
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    copilotStatus()
      .then((s) => {
        if (!cancelled) setAvailable(s.available);
      })
      .catch((e) => {
        if (!cancelled) {
          setAvailable(false);
          setStatusError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    const next: ChatEntry[] = [...messages, { role: "user", content: trimmed }];
    setMessages(next);
    setInput("");
    setSending(true);
    try {
      const res = await copilotChat(next.map(({ role, content }) => ({ role, content })));
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, toolCalls: res.tool_calls },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `⚠︎ Copilot failed: ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setSending(false);
    }
  }

  if (available === false) {
    return (
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="flex items-start gap-3 p-4">
          <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5" aria-hidden />
          <div className="text-sm">
            <p className="font-medium text-amber-500">Copilot is not configured</p>
            <p className="text-xs text-muted-foreground mt-1">
              Add <code className="px-1 rounded bg-amber-500/10">ANTHROPIC_API_KEY</code> or{" "}
              <code className="px-1 rounded bg-amber-500/10">DEEPSEEK_API_KEY</code> to <code>backend/.env</code>,
              then restart the backend.
            </p>
            {statusError ? (
              <p className="text-xs text-muted-foreground mt-1">({statusError})</p>
            ) : null}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-emerald-500" aria-hidden />
          Aegis Copilot
          <Badge variant="outline" className="text-xs ml-auto">
            Beta
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div ref={scrollRef} className="max-h-[60vh] overflow-y-auto px-4 py-3 space-y-3">
          {messages.length === 0 ? (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Ask in plain English — the copilot calls Aegis tools to answer.
              </p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="text-xs rounded-full border px-3 py-1 hover:bg-muted"
                    type="button"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  "rounded-2xl px-3 py-2 max-w-[85%] whitespace-pre-wrap break-words text-sm " +
                  (m.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted")
                }
              >
                <p>{m.content}</p>
                {m.toolCalls && m.toolCalls.length > 0 ? (
                  <details className="mt-2 text-xs opacity-80">
                    <summary className="cursor-pointer inline-flex items-center gap-1">
                      <Wrench className="h-3 w-3" aria-hidden />
                      {m.toolCalls.length} tool call{m.toolCalls.length > 1 ? "s" : ""}
                    </summary>
                    <ul className="mt-1 space-y-1">
                      {m.toolCalls.map((tc, j) => (
                        <li key={j} className="font-mono">
                          · {tc.name}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>
            </div>
          ))}
          {sending ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Skeleton className="h-3 w-3 rounded-full" />
              <span>Copilot is thinking…</span>
            </div>
          ) : null}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="border-t p-3 flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about a ticker, regime, backtest…"
            className="flex-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            disabled={sending}
            aria-label="Copilot prompt"
          />
          <Button type="submit" size="sm" disabled={sending || !input.trim()}>
            <Send className="h-4 w-4" aria-hidden />
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
