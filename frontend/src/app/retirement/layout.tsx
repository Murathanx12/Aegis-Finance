import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Retirement Calculator",
  description: "Project your savings growth with compound interest, inflation adjustment, and milestone tracking",
};

export default function RetirementLayout({ children }: { children: React.ReactNode }) {
  return children;
}
