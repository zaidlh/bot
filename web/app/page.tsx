import Link from "next/link";
import { loadAnimewitcher, loadAsia2tv, displayName, slugify } from "@/lib/data";
import type { Title } from "@/lib/data";

export default async function HomePage() {
  const [anime, asia] = await Promise.all([loadAnimewitcher(), loadAsia2tv()]);
  return (
    <div className="space-y-12">
      <section className="space-y-3">
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
          Browse the catalog
        </h1>
        <p className="text-white/60 max-w-2xl">
          Static index of every title scraped from AnimeWitcher and Asia2TV by{" "}
          <a
            href="https://github.com/zaidlh/bot"
            className="text-accent hover:underline"
          >
            zaidlh/bot
          </a>
          . Click a source below to browse, search and filter titles, or open
          an episode directly in your player.
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <SourceCard
            href="/anime/"
            title="AnimeWitcher"
            sub={`${anime.count.toLocaleString()} titles`}
            updated={anime.scraped_at}
          />
          <SourceCard
            href="/asia/"
            title="Asia2TV"
            sub={`${asia.count.toLocaleString()} series`}
            updated={asia.scraped_at}
          />
        </div>
      </section>

      <Featured title="Latest from AnimeWitcher" source="anime" titles={anime.titles.slice(0, 12)} />
      <Featured title="Latest from Asia2TV" source="asia" titles={asia.titles.slice(0, 12)} />
    </div>
  );
}

function SourceCard({
  href,
  title,
  sub,
  updated,
}: {
  href: string;
  title: string;
  sub: string;
  updated: number;
}) {
  const dt =
    updated > 0
      ? new Date(updated * 1000).toISOString().slice(0, 10)
      : "—";
  return (
    <Link
      href={href}
      className="block rounded-lg border border-white/10 bg-panel/60 hover:border-accent/60 p-5 min-w-[220px] transition"
    >
      <div className="text-lg font-medium">{title}</div>
      <div className="text-white/60 text-sm">{sub}</div>
      <div className="text-white/30 text-xs mt-2">Updated {dt}</div>
    </Link>
  );
}

function Featured({
  title,
  source,
  titles,
}: {
  title: string;
  source: "anime" | "asia";
  titles: Title[];
}) {
  if (titles.length === 0) return null;
  return (
    <section>
      <h2 className="text-xl font-semibold mb-4">{title}</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {titles.map((t) => (
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
    </section>
  );
}
