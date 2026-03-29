import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Crash Prediction",
  description: "ML-predicted crash probability across 3, 6, and 12-month horizons with SHAP explainability",
};

export default function CrashLayout({ children }: { children: React.ReactNode }) {
  return children;
}
