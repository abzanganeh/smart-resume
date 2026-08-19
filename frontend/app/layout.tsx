import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { auth } from "@/auth";
import { AppChrome } from "@/components/nav/AppChrome";
import { SessionProvider } from "@/components/nav/SessionProvider";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { ThemeScript } from "@/components/theme/ThemeScript";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TalioCV — AI tailoring & job search",
  description:
    "Build your master resume, tailor it to every job description, extract company intel, and track applications.",
  openGraph: {
    title: "TalioCV",
    description:
      "AI resume tailoring, company intel, and job search workflow.",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "TalioCV" }],
  },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body
        className={`${inter.className} bg-sr-bg text-sr-fg antialiased flex min-h-screen flex-col`}
      >
        <ThemeProvider>
          <SessionProvider session={session}>
            <AppChrome>{children}</AppChrome>
          </SessionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
