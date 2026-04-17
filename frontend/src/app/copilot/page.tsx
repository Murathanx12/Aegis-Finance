import { CopilotChat } from "@/components/copilot-chat";

export const metadata = {
  title: "Copilot — Aegis Finance",
  description: "Ask the Aegis analytics engine in plain English.",
};

export default function CopilotPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Copilot</h1>
        <p className="text-sm text-muted-foreground">
          Natural-language access to every analytics module — Monte Carlo, crash model, style
          box, factor grades, sector rotation, allocation backtests, and more. Copilot picks
          the right Aegis tools behind the scenes.
        </p>
      </header>
      <CopilotChat />
      <p className="text-xs text-muted-foreground text-center">
        Educational only. Aegis is not financial advice.
      </p>
    </main>
  );
}
