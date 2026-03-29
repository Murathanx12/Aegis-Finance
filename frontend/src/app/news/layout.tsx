import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "News & Intelligence",
  description: "GDELT-powered market sentiment analysis with AI-generated insights and event scoring",
};

export default function NewsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
