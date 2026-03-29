import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sector Analysis",
  description: "11 S&P 500 sectors ranked by risk-adjusted expected returns with factor model analysis",
};

export default function SectorsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
