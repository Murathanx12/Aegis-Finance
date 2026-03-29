import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { Providers } from "@/components/providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Aegis Finance — Market Intelligence Platform",
    template: "%s | Aegis Finance",
  },
  description:
    "Free, open-source market intelligence platform. ML crash prediction, Monte Carlo simulation, and macroeconomic analysis.",
  openGraph: {
    title: "Aegis Finance — Market Intelligence Platform",
    description:
      "Institutional-grade analysis accessible to everyone. ML crash prediction, Monte Carlo simulation, portfolio analytics.",
    siteName: "Aegis Finance",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Aegis Finance",
    description: "Free, open-source market intelligence platform",
  },
  icons: {
    icon: "/logo.png",
    apple: "/logo.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex" suppressHydrationWarning>
        <Providers>
          <Sidebar />
          <main className="flex-1 overflow-auto">
            <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 animate-fade-in">
              {children}
            </div>
          </main>
        </Providers>
      </body>
    </html>
  );
}
