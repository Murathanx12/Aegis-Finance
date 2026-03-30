import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { Providers } from "@/components/providers";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
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
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex" suppressHydrationWarning>
        <Providers>
          <Sidebar />
          <main className="flex-1 overflow-auto">
            <div className="mx-auto max-w-[1440px] px-6 py-8 lg:px-10 animate-fade-in">
              {children}
            </div>
          </main>
        </Providers>
      </body>
    </html>
  );
}
