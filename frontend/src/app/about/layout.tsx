import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "About",
  description: "Methodology, chart reading guide, known limitations, and credits for Aegis Finance",
};

export default function AboutLayout({ children }: { children: React.ReactNode }) {
  return children;
}
