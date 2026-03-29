import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Monte Carlo Simulation",
  description: "Jump-diffusion Monte Carlo simulation with 7 scenario-weighted paths and Merton compensator",
};

export default function SimulationLayout({ children }: { children: React.ReactNode }) {
  return children;
}
