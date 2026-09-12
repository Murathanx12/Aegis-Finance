"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BookOpen } from "lucide-react";
import {
  ApiState,
  DASH,
  EstimateValue,
  Field,
  RawPayload,
  fmtUtc,
} from "@/components/desktop/primitives";
import {
  getBooks,
  isNotBuilt,
  type BookRow,
  type BookTwin,
  type BooksResponse,
} from "@/lib/control-api";

/**
 * Paper books (lane B).
 *
 * A book is a frozen `Strategy` contract, a cadence, where it came from, and a
 * CONTROL TWIN created with it. This page has one rule, and it is the reason
 * the endpoint nests twins inside each book rather than returning two lists:
 *
 * **a book's number is never rendered without its twin's.**
 *
 * So every book is a block, and inside the block the twins' rows sit directly
 * beneath the book's own, in the same table, with the same columns. There is no
 * layout in which a reader sees the book's since-inception and has to go
 * looking for the control's.
 *
 * The second rule is the fleet page's, unchanged: the mean daily excess vs the
 * twin is rendered ONLY through `EstimateValue`, which refuses to print a value
 * that arrived without a standard error; where `estimable` is false the page
 * prints the payload's own sentence instead of a t-statistic. Realised
 * quantities — NAV, a since-inception return, a mark count — are OBSERVATIONS
 * and are printed as they arrived.
 */

function pct(v: number | null | undefined, digits = 3): string {
  return typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(digits)}%` : DASH;
}
function num(v: number | null | undefined, digits = 2): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : DASH;
}
function usd(v: number | null | undefined): string {
  return typeof v === "number" && Number.isFinite(v)
    ? `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : DASH;
}

function TwinRow({ twin }: { twin: BookTwin }) {
  return (
    <tr className="border-t border-border/30 text-muted-foreground">
      <td className="py-1 pr-3 pl-4">
        ↳ {twin.kind ?? "twin"}
        <span className="ml-2 font-mono text-[10px]">{twin.book_id.slice(0, 13)}</span>
      </td>
      <td className="py-1 pr-3 text-right tabular-nums">{num(twin.nav)}</td>
      <td className="py-1 pr-3 text-right tabular-nums">{pct(twin.since_inception_pct)}</td>
      <td className="py-1 pr-3 text-right tabular-nums">{twin.n_marks}</td>
      <td className="py-1">{twin.last_mark ?? DASH}</td>
    </tr>
  );
}

function BookBlock({ book, minDays }: { book: BookRow; minDays: number | undefined }) {
  const vs = book.vs_twin ?? {};
  const f = book.forecasts;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          <span>{book.title || book.strategy_id}</span>
          <Badge variant="outline">{book.cadence}</Badge>
          <Badge variant="secondary">{book.origin}</Badge>
          <Badge variant="outline">{book.licence}</Badge>
          {book.shadow ? <Badge variant="secondary">shadow</Badge> : null}
        </CardTitle>
        <p className="font-mono text-[10px] text-muted-foreground">{book.book_id}</p>
        {book.origin_text ? (
          <p className="text-[11px] italic text-muted-foreground">“{book.origin_text}”</p>
        ) : null}
      </CardHeader>
      <CardContent>
        {/* THE TABLE. The book first, its twins immediately under it, same
            columns — the rule of this page, expressed as a layout that cannot
            be satisfied while omitting the control. */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-1 pr-3 font-normal">book / control</th>
                <th className="py-1 pr-3 text-right font-normal">NAV</th>
                <th className="py-1 pr-3 text-right font-normal">since inception</th>
                <th className="py-1 pr-3 text-right font-normal">marks</th>
                <th className="py-1 font-normal">last mark</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              <tr>
                <td className="py-1 pr-3">the book</td>
                <td className="py-1 pr-3 text-right tabular-nums">{num(book.nav)}</td>
                <td className="py-1 pr-3 text-right tabular-nums">
                  {pct(book.since_inception_pct)}
                </td>
                <td className="py-1 pr-3 text-right tabular-nums">{book.n_marks}</td>
                <td className="py-1">{book.last_mark ?? DASH}</td>
              </tr>
              {(book.twins ?? []).map((t) => (
                <TwinRow key={t.book_id} twin={t} />
              ))}
            </tbody>
          </table>
        </div>
        {book.why_no_nav ? (
          <p className="mt-2 text-[11px] text-muted-foreground">{book.why_no_nav}</p>
        ) : null}

        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-[11px] font-medium text-muted-foreground">
              daily excess vs the first twin
            </p>
            <EstimateValue
              est={{
                value:
                  typeof vs.mean_daily_excess_pct === "number"
                    ? vs.mean_daily_excess_pct
                    : null,
                se:
                  typeof vs.se_daily_excess_pct === "number"
                    ? vs.se_daily_excess_pct
                    : null,
                ciLo: null,
                ciHi: null,
                n: typeof vs.n_days === "number" ? vs.n_days : null,
              }}
              digits={4}
              suffix="%"
            />
            <Field label="paired sessions" value={vs.n_days ?? null} />
            <Field
              label="estimable"
              value={
                <Badge variant={vs.estimable ? "outline" : "secondary"}>
                  {vs.estimable ? "yes" : "not yet"}
                </Badge>
              }
            />
            {vs.why_not_estimable ? (
              <p className="mt-1 text-[11px] text-muted-foreground">
                {vs.why_not_estimable}
              </p>
            ) : (
              <p className="mt-1 text-[11px] text-muted-foreground">
                {minDays ?? DASH} paired sessions is the floor before a mean is called an
                estimate.
              </p>
            )}
          </div>
          <div>
            <p className="mb-1 text-[11px] font-medium text-muted-foreground">
              forecasts (B5)
            </p>
            <Field label="open" value={f?.n_open ?? null} />
            <Field label="graded" value={f?.n_graded ?? null} />
            <Field label="last grade" value={f?.last_grade ?? null} />
            {/* The engine's Brier NEVER appears alone: the question the ledger
                exists to answer is whether it beats a row that looked at
                nothing. */}
            <Field label="Brier (engine)" value={num(f?.brier, 5)} />
            <Field label="Brier (base rate)" value={num(f?.base_rate_brier, 5)} />
            {f?.why ? (
              <p className="mt-1 text-[11px] text-muted-foreground">{f.why}</p>
            ) : null}
          </div>
        </div>

        <div className="mt-3 border-t border-border/40 pt-2">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">
            worst case, in dollars
          </p>
          <Field label="verdict" value={book.worst_case?.verdict ?? null} />
          <Field label="worst case" value={usd(book.worst_case?.worst_case_usd)} />
          <Field label="gross / equity" value={num(book.worst_case?.gross_over_equity)} />
          <Field label="round trip (bps)" value={num(book.round_trip_bps as number, 1)} />
        </div>

        <p className="mt-2 text-[10px] text-muted-foreground">
          control construction: {book.control_construction || DASH}
        </p>
      </CardContent>
    </Card>
  );
}

export default function BooksPage() {
  const { data, error, isLoading } = useQuery<BooksResponse>({
    queryKey: ["control", "books", "page"],
    queryFn: getBooks,
  });

  if (error && isNotBuilt(error)) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Paper books</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            {DASH} this backend has no <code className="font-mono">/api/control/books</code>{" "}
            endpoint yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  const books = data?.books ?? [];
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm">
            <BookOpen className="size-4" /> Paper books
          </CardTitle>
          <span className="text-[10px] text-muted-foreground">{fmtUtc(data?.utc)}</span>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            A book is a frozen contract, a cadence, where it came from, and a control twin
            created with it. Every book below is drawn with its twins in the same table:{" "}
            <span className="font-medium">a book&apos;s number is never shown without its
            control&apos;s</span>.
          </p>
          <div className="mt-2">
            <Field label="books" value={data?.n_books ?? null} />
            <Field label="twins" value={data?.n_twins ?? null} />
            <Field label="estimable floor (sessions)" value={data?.min_days_for_estimable ?? null} />
          </div>
          {data?.available === false ? (
            <p className="mt-2 text-xs text-muted-foreground">
              {DASH} {data.error ?? "the book table could not be read"}. Nothing is inferred
              from that: a checkout with no books is not a programme with no books.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {error ? (
        <ApiState error={error} what="the paper books" />
      ) : isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : books.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground">
              {DASH} no book has been created yet. Seed one with{" "}
              <code className="font-mono">
                POST /api/control/books/create-from-contract
              </code>{" "}
              (control plane enabled), and the 16:45 ET cadence pass will mark it.
            </p>
          </CardContent>
        </Card>
      ) : (
        books.map((b) => (
          <BookBlock key={b.book_id} book={b} minDays={data?.min_days_for_estimable} />
        ))
      )}

      {data ? <RawPayload data={data} /> : null}
    </div>
  );
}
