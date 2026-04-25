export type Episode = {
  number: number;
  // AnimeWitcher
  doc_id?: string;
  name?: string | null;
  thumb?: string | null;
  bunny_video_id?: string | null;
  // Asia2TV
  url?: string;
};

export type Title = {
  id: string;
  // AnimeWitcher
  name?: string;
  english_title?: string | null;
  type?: string | null;
  story?: string | null;
  // Asia2TV
  title?: string;
  url?: string;
  plot?: string | null;
  // common
  poster?: string | null;
  tags?: string[];
  episodes: Episode[];
};

export type Catalog = {
  source: "animewitcher" | "asia2tv";
  scraped_at: number;
  count: number;
  titles: Title[];
};

/** Public name regardless of source. */
export function displayName(t: Title): string {
  return t.title || t.english_title || t.name || t.id || "Untitled";
}

/** Slug used in URLs — base64url of the id, safe for any character set. */
export function slugify(id: string): string {
  if (typeof window === "undefined") {
    return Buffer.from(id, "utf8")
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  }
  // Browser fallback (only used if a client component slugifies, currently
  // none do — but keep this isomorphic for safety).
  const b64 = btoa(unescape(encodeURIComponent(id)));
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function unslug(slug: string): string {
  let b64 = slug.replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  if (typeof window === "undefined") {
    return Buffer.from(b64, "base64").toString("utf8");
  }
  return decodeURIComponent(escape(atob(b64)));
}

/** Pixeldrain /u/ID → /api/file/ID rewrite, mirrors urls.py. */
export function prettifyUrl(url: string | null | undefined): string {
  if (!url) return "";
  return url.replace(
    /https?:\/\/pixeldrain\.com\/u\/([A-Za-z0-9]+)/g,
    "https://pixeldrain.com/api/file/$1",
  );
}
