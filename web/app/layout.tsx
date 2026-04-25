import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cloudstream Bot — Catalog",
  description:
    "Static catalog of AnimeWitcher and Asia2TV titles, scraped via the Cloudstream Bot pipeline.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans">
        <header className="sticky top-0 z-10 backdrop-blur bg-ink/70 border-b border-white/5">
          <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-6">
            <Link href="/" className="font-semibold tracking-tight">
              <span className="text-accent">▶</span> Cloudstream Bot
            </Link>
            <nav className="flex gap-4 text-sm text-white/70">
              <Link href="/anime/" className="hover:text-white">AnimeWitcher</Link>
              <Link href="/asia/" className="hover:text-white">Asia2TV</Link>
              <a
                href="https://github.com/zaidlh/bot"
                className="hover:text-white"
                target="_blank"
                rel="noreferrer"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-4 py-8">{children}</main>
        <footer className="max-w-6xl mx-auto px-4 py-10 text-xs text-white/40">
          Catalog auto-scraped from AnimeWitcher and Asia2TV. All metadata,
          posters and links belong to their respective owners. This site is
          a static read-only index — episodes stream from third-party hosts.
        </footer>
      </body>
    </html>
  );
}
