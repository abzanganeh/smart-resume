import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppChrome } from "@/components/nav/AppChrome";
import { SessionProvider } from "@/components/nav/SessionProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Flint Resume — AI tailoring & company intel",
  description:
    "Build your master resume, tailor it to every job description, extract company intel, and track applications.",
  icons: {
    icon: "/brand/logo.png",
  },
  openGraph: {
    title: "Flint Resume",
    description:
      "AI resume tailoring, company intel, and job search workflow.",
    images: [{ url: "/brand/logo.png", width: 1536, height: 1024, alt: "Flint Resume" }],
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
