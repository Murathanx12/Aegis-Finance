"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { driver, type DriveStep } from "driver.js";
import "driver.js/dist/driver.css";

const TOUR_DONE_KEY = "aegis-tour-done";
export const START_TOUR_EVENT = "aegis:start-tour";

// Coach marks target [data-tour=...] anchors. Six max, skippable at every
// step (Esc, overlay click, or the x) — the tour is an offer, never a gate.
const STEPS: DriveStep[] = [
  {
    element: '[data-tour="nav"]',
    popover: {
      title: "Everything lives here",
      description:
        "Markets, stock analysis, portfolio tools, and our live track record. Casual mode keeps it to the essentials — flip to Advanced anytime for the dense analytics.",
    },
  },
  {
    element: '[data-tour="daily-brief"]',
    popover: {
      title: "Your daily brief",
      description:
        "A plain-English read of what the models see today. Every number on this site is a model output with uncertainty — never a promise, never advice.",
    },
  },
  {
    element: '[data-tour="crash-gauge"]',
    popover: {
      title: "Crash probability, honestly",
      description:
        "A model estimate with error bars, not a verdict. Around 20% means roughly 2 in 10 similar periods saw trouble — closer to a coin flip than a siren.",
    },
  },
  {
    element: '[data-tour="track-record-link"]',
    popover: {
      title: "We keep score in public",
      description:
        "Paper portfolios marked to market daily since inception, with confidence intervals on every statistic. No skill claims before 24 months — the record speaks, we don't.",
    },
  },
  {
    element: '[data-tour="command"]',
    popover: {
      title: "Fast search",
      description:
        "Ctrl+K jumps to any ticker, page, or function from anywhere.",
    },
  },
  {
    element: '[data-tour="mode-switch"]',
    popover: {
      title: "Casual vs Advanced",
      description:
        "You're in Casual mode. Advanced unhides the quant surfaces: risk watch, factor analytics, the workspace, and more.",
    },
  },
];

function startTour() {
  const available = STEPS.filter(
    (s) => typeof s.element === "string" && document.querySelector(s.element),
  );
  if (available.length === 0) return;
  const d = driver({
    showProgress: true,
    animate: true,
    overlayOpacity: 0.6,
    nextBtnText: "Next",
    prevBtnText: "Back",
    doneBtnText: "Done",
    steps: available,
    onDestroyStarted: () => {
      // Any exit — skip, Esc, or finishing — counts as done; never nag again.
      localStorage.setItem(TOUR_DONE_KEY, "true");
      d.destroy();
    },
  });
  d.drive();
}

/**
 * First-run coach marks (driver.js, MIT). Auto-offers ONCE on the dashboard
 * for new visitors; afterwards only runs when explicitly asked via the
 * "Take the tour" button (START_TOUR_EVENT).
 */
export function FirstRunTour() {
  const pathname = usePathname();

  useEffect(() => {
    const onStart = () => startTour();
    window.addEventListener(START_TOUR_EVENT, onStart);
    return () => window.removeEventListener(START_TOUR_EVENT, onStart);
  }, []);

  useEffect(() => {
    if (pathname !== "/") return;
    if (localStorage.getItem(TOUR_DONE_KEY)) return;
    // Let the dashboard render its anchors before pointing at them.
    const id = setTimeout(startTour, 1500);
    return () => clearTimeout(id);
  }, [pathname]);

  return null;
}
