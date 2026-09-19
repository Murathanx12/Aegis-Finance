/**
 * PERSONAL MODE — one env read, in one place (chunk 17).
 *
 * Aegis ships twice out of one codebase: a public tool other people run, which
 * carries "educational tool, not financial advice" on every surface, and
 * Murat's own desktop build, where that sentence is a man disclaiming to
 * himself — noise that teaches the reader to skim whatever sits beside it.
 *
 * Spec: `docs/research_notes/2026-09-19/spec_decision_contract_and_path_audit.md` §5.
 *
 * WHAT THIS FLAG DOES AND DOES NOT DO
 * -----------------------------------
 * It hides disclaimer SENTENCES. It changes no number, no sizing, no
 * permission and no route. Statements about what a model actually is — "paper
 * only", "backtest, not the track record", "crash probabilities are model
 * estimates, not guarantees" — are findings, not boilerplate, and they stay in
 * BOTH builds. If a sentence would still be true and useful to the only person
 * who will ever read this build, it stays.
 *
 * `process.env.NEXT_PUBLIC_AEGIS_PERSONAL_MODE` is written out literally here
 * and nowhere else: Next.js inlines a `NEXT_PUBLIC_*` read only when it sees
 * the full member expression at build time, so a computed key would silently
 * evaluate to `undefined` in the browser bundle — a flag that reads as OFF in
 * exactly the build it was meant to change.
 *
 * Absent (the default, and what CI, the deployed website and the public build
 * all see) it is OFF. Only the exact string "1" turns it on.
 */
export function isPersonalMode(): boolean {
  return process.env.NEXT_PUBLIC_AEGIS_PERSONAL_MODE === "1";
}

/** The env var's name, for documentation and error messages. */
export const PERSONAL_MODE_ENV = "NEXT_PUBLIC_AEGIS_PERSONAL_MODE";
