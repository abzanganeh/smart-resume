import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppChrome } from "@/components/nav/AppChrome";
import { SessionProvider } from "@/components/nav/SessionProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Smart Resume Agent — AI job search co-pilot",
  description:
    "Build your master resume by voice, tailor it to every job description, find matching jobs, write cover letters, and track applications — all in one place.",
  icons: {
    icon: "/brand/logo.png",
  },
  openGraph: {
    title: "Smart Resume Agent",
    description:
      "AI-powered job search platform — master resume, JD tailoring, ATS guidance, and application tracking.",
    images: [{ url: "/brand/logo.png", width: 480, height: 262, alt: "Smart Resume Agent" }],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-slate-950 antialiased flex min-h-screen flex-col`}>
        <SessionProvider>
          <AppChrome>{children}</AppChrome>
        </SessionProvider>
      </body>
    </html>
  );
}
