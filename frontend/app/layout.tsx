import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { SHARED_OPEN_GRAPH, SHARED_TWITTER } from "./_lib/share-metadata";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Absolute base for canonical/OG URLs. Per-page metadata can use relative
// paths and Next resolves them against this. Set FRONTEND_URL to the real
// origin in production, otherwise these point at localhost.
const siteUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "IndieGameBridge",
  description: "Find Twitch streamers worth pitching your indie game to",
  applicationName: "IndieGameBridge",
  // Inherited by the pages that set no openGraph or twitter of their own; the others spread
  // the same shared fields in (see share-metadata.ts).
  openGraph: SHARED_OPEN_GRAPH,
  twitter: SHARED_TWITTER,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-white text-neutral-900">{children}</body>
    </html>
  );
}
