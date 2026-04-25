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

/**
 * Slug used in URLs.
 *
 * AnimeWitcher object_ids are short titles ("Black Clover") that
 * round-trip safely through base64url. Asia2TV ids are full URLs
 * (~120+ encoded chars of Arabic) — base64-encoding those produces
 * filesystem paths over the 255-char limit when Next.js exports the
 * static page, so we fall back to a 12-hex-char FNV-1a hash. The slug
 * is opaque on the wire either way; the detail page resolves it by
 * matching ``slugify(title.id) === slug``.
 */
const SHORT_SLUG_LIMIT = 96;

export function slugify(id: string): string {
  // 1. URL-safe base64 of the id.
  let slug: string;
  if (typeof window === "undefined") {
    slug = Buffer.from(id, "utf8")
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  } else {
    const b64 = btoa(unescape(encodeURIComponent(id)));
    slug = b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  if (slug.length <= SHORT_SLUG_LIMIT) return slug;
  // 2. Long ids (e.g. Arabic Asia2TV URLs) → 12-char FNV-1a hex.
  return "h" + fnv1aHex(id);
}

function fnv1aHex(s: string): string {
  // 64-bit FNV-1a using BigInt for portability across Node and browsers.
  let h = BigInt("0xcbf29ce484222325");
  const prime = BigInt("0x100000001b3");
  const mask = BigInt("0xffffffffffffffff");
  for (let i = 0; i < s.length; i++) {
    h ^= BigInt(s.charCodeAt(i));
    h = (h * prime) & mask;
  }
  return h.toString(16).padStart(16, "0").slice(0, 12);
}

/** Pixeldrain /u/ID → /api/file/ID rewrite, mirrors urls.py. */
export function prettifyUrl(url: string | null | undefined): string {
  if (!url) return "";
  return url.replace(
    /https?:\/\/pixeldrain\.com\/u\/([A-Za-z0-9]+)/g,
    "https://pixeldrain.com/api/file/$1",
  );
}
