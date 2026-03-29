import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Stock Analysis",
  description: "Per-ticker Monte Carlo projections with fundamental analysis, SHAP explainability, and analyst consensus",
};

export default function StockLayout({ children }: { children: React.ReactNode }) {
  return children;
}
