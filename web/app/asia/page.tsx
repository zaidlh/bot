import { loadAsia2tv } from "@/lib/data";
import CatalogGrid from "@/components/CatalogGrid";

export default async function AsiaPage() {
  const data = await loadAsia2tv();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Asia2TV</h1>
        <p className="text-white/60 text-sm">
          {data.count.toLocaleString()} series, last scraped{" "}
          {data.scraped_at
            ? new Date(data.scraped_at * 1000).toISOString().slice(0, 10)
            : "—"}
          .
        </p>
      </div>
      <CatalogGrid source="asia" titles={data.titles} />
    </div>
  );
}
