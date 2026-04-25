"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Title } from "@/lib/types";
import { displayName, slugify } from "@/lib/types";

export default function CatalogGrid({
  source,
  titles,
}: {
  source: "anime" | "asia";
  titles: Title[];
}) {
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string | null>(null);

  const allTags = useMemo(() => {
    const counts = new Map<string, number>();
    for (const t of titles) {
      for (const g of t.tags || []) {
        counts.set(g, (counts.get(g) || 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20)
      .map(([name]) => name);
  }, [titles]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return titles.filter((t) => {
      if (tag && !(t.tags || []).includes(tag)) return false;
      if (!q) return true;
      const fields = [
        t.name,
        t.title,
        t.english_title,
        t.story,
        t.plot,
        ...(t.tags || []),
      ];
      return fields.some((f) => f && f.toLowerCase().includes(q));
    });
  }, [titles, query, tag]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="search"
          placeholder="Search title, plot, tags…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 min-w-[240px] bg-panel/80 border border-white/10 focus:border-accent rounded-md px-3 py-2 outline-none"
        />
        <span className="text-white/50 text-sm">
          {filtered.length.toLocaleString()} / {titles.length.toLocaleString()}
        </span>
      </div>
      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-2 scrollbar-thin">
          <button
            onClick={() => setTag(null)}
            className={`text-xs px-2 py-1 rounded-full border transition ${
              tag === null
                ? "border-accent text-accent"
                : "border-white/10 text-white/60 hover:border-white/30"
            }`}
          >
            all
          </button>
          {allTags.map((g) => (
            <button
              key={g}
              onClick={() => setTag(tag === g ? null : g)}
              className={`text-xs px-2 py-1 rounded-full border transition ${
                tag === g
                  ? "border-accent text-accent"
                  : "border-white/10 text-white/60 hover:border-white/30"
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {filtered.map((t) => (
          <Link
            key={t.id}
            href={`/${source}/${slugify(t.id)}/`}
            className="group block"
          >
            <div className="aspect-[2/3] rounded-md overflow-hidden bg-panel ring-1 ring-white/5 group-hover:ring-accent/60 transition">
              {t.poster ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={t.poster}
                  alt={displayName(t)}
                  className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                  loading="lazy"
                />
              ) : (
                <div className="w-full h-full grid place-items-center text-white/30 text-xs">
                  no poster
                </div>
              )}
            </div>
            <div className="mt-2 text-sm line-clamp-2 group-hover:text-accent">
              {displayName(t)}
            </div>
            <div className="text-xs text-white/40">
              {t.episodes.length} ep{t.episodes.length === 1 ? "" : "s"}
            </div>
          </Link>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-white/40 text-sm text-center py-8">
          No matches.
        </div>
      )}
    </div>
  );
}
