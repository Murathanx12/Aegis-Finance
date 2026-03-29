import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Portfolio",
  description: "Analyze your holdings or build a goal-based allocation with Monte Carlo projection",
};

export default function PortfolioLayout({ children }: { children: React.ReactNode }) {
  return children;
}
