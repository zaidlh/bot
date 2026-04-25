import "server-only";

import { promises as fs } from "fs";
import path from "path";
import type { Catalog } from "./types";

const ROOT = path.resolve(process.cwd(), "..");
const DATA_DIR = path.join(ROOT, "data");

async function readJson<T>(file: string, fallback: T): Promise<T> {
  try {
    const txt = await fs.readFile(path.join(DATA_DIR, file), "utf8");
    return JSON.parse(txt) as T;
  } catch {
    return fallback;
  }
}

const EMPTY: Catalog = {
  source: "animewitcher",
  scraped_at: 0,
  count: 0,
  titles: [],
};

export async function loadAnimewitcher(): Promise<Catalog> {
  return readJson<Catalog>("animewitcher.json", { ...EMPTY, source: "animewitcher" });
}

export async function loadAsia2tv(): Promise<Catalog> {
  return readJson<Catalog>("asia2tv.json", { ...EMPTY, source: "asia2tv" });
}

export { displayName, slugify, prettifyUrl } from "./types";
export type { Catalog, Episode, Title } from "./types";
