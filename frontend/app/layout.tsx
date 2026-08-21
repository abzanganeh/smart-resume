import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { siteUrl } from "@/lib/siteUrl";
import { auth } from "@/auth";
import { AppChrome } from "@/components/nav/AppChrome";
import { SessionProvider } from "@/components/nav/SessionProvider";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { ThemeScript } from "@/components/theme/ThemeScript";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  // Without this, Next resolves relative OG URLs against http://localhost:3000
  // and warns on every build.
  metadataBase: new URL(siteUrl()),
  title: "TalioCV — AI resume tailoring, ATS optimization & job search",
  description:
    "Discover the job titles you actually fit, then tailor an ATS-optimized resume to every job description. Master resume, cover letters, job search, and application tracking in one place.",
  openGraph: {
    title: "TalioCV",
    description:
      "Find the roles you fit, then tailor an ATS-optimized resume for each one.",
    // No `images` here on purpose. `app/opengraph-image.png` is picked up by
    // file convention and emitted with a cache-busting hash; the previous
    // hand-written entry pointed at an extension-less `/opengraph-image`, which
    // is not a route that serves the image.
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
