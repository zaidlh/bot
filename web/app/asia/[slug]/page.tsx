import Link from "next/link";
import { notFound } from "next/navigation";
import { displayName, loadAsia2tv, slugify, unslug } from "@/lib/data";

export async function generateStaticParams() {
  const data = await loadAsia2tv();
  return data.titles.map((t) => ({ slug: slugify(t.id) }));
}

export default async function AsiaDetail({
  params,
}: {
  params: { slug: string };
}) {
  const data = await loadAsia2tv();
  const id = unslug(params.slug);
  const title = data.titles.find((t) => t.id === id);
  if (!title) notFound();

  return (
    <article className="space-y-6">
      <Link href="/asia/" className="text-sm text-white/60 hover:text-white">
        ← All Asia2TV
      </Link>
      <div className="grid grid-cols-1 sm:grid-cols-[200px_1fr] gap-6">
        {title.poster && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={title.poster}
            alt={displayName(title)}
            className="w-full sm:w-[200px] aspect-[2/3] object-cover rounded-md ring-1 ring-white/10"
          />
        )}
        <div className="space-y-3">
          <h1 className="text-3xl font-bold leading-tight">
            {displayName(title)}
          </h1>
          <div className="flex flex-wrap gap-2 text-xs text-white/70">
            <span className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10">
              {title.episodes.length} ep
              {title.episodes.length === 1 ? "" : "s"}
            </span>
            {title.tags?.slice(0, 8).map((g) => (
              <span
                key={g}
                className="px-2 py-0.5 rounded-full bg-accent/10 border border-accent/30 text-accent"
              >
                {g}
              </span>
            ))}
            {title.url && (
              <a
                href={title.url}
                className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 hover:border-accent"
                target="_blank"
                rel="noreferrer"
              >
                Source ↗
              </a>
            )}
          </div>
          {title.plot && (
            <p className="text-white/80 leading-relaxed whitespace-pre-line">
              {title.plot}
            </p>
          )}
        </div>
      </div>

      <section>
        <h2 className="text-xl font-semibold mb-3">Episodes</h2>
        <ol className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
          {title.episodes.map((ep) => (
            <li
              key={ep.url || ep.number}
              className="rounded-md border border-white/10 bg-panel/60 px-3 py-2 text-sm"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium">Ep {ep.number}</span>
                {ep.url && (
                  <a
                    href={ep.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-accent hover:underline"
                  >
                    open ↗
                  </a>
                )}
              </div>
            </li>
          ))}
        </ol>
        {title.episodes.length === 0 && (
          <div className="text-white/40 text-sm">No episodes scraped yet.</div>
        )}
      </section>
    </article>
  );
}
