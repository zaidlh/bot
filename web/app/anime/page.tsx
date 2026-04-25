import { loadAnimewitcher } from "@/lib/data";
import CatalogGrid from "@/components/CatalogGrid";

export default async function AnimePage() {
  const data = await loadAnimewitcher();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">AnimeWitcher</h1>
        <p className="text-white/60 text-sm">
          {data.count.toLocaleString()} titles, last scraped{" "}
          {data.scraped_at
            ? new Date(data.scraped_at * 1000).toISOString().slice(0, 10)
            : "—"}
          .
        </p>
      </div>
      <CatalogGrid source="anime" titles={data.titles} />
    </div>
  );
}
