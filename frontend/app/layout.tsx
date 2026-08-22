import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import {
  METADATA_DESCRIPTION,
  METADATA_OG_DESCRIPTION,
  METADATA_OG_TITLE,
  METADATA_TITLE,
} from "@/lib/brand";
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
  title: METADATA_TITLE,
  description: METADATA_DESCRIPTION,
  openGraph: {
    title: METADATA_OG_TITLE,
    description: METADATA_OG_DESCRIPTION,
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
