"""Port of ``com.animewitcher.AnimeWitcherProvider`` (Algolia + Firestore)."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional

import httpx


FIREBASE_PROJECT_ID = "animewitcher-1c66d"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
    "/databases/(default)/documents"
)
DEFAULT_ALGOLIA_APP_ID = "XC5QF67TBB"
DEFAULT_ALGOLIA_API_KEY = "3c3b61d7c280fd05ea1d496a40bd2b64"

_ALGOLIA_EXTRA_HEADERS = {
    "User-Agent": "Algolia for Android (3.27.0); Android (13)",
    "Content-Type": "application/json; charset=UTF-8",
}
_SEARCH_ATTRIBUTES = (
    '["objectID","name","poster_uri","type","details","tags","story",'
    '"english_title","_highlightResult"]'
)


@dataclass
class AnimeSearchResult:
    object_id: str
    name: str
    english_title: Optional[str] = None
    type: Optional[str] = None
    poster: Optional[str] = None
    story: Optional[str] = None


@dataclass
class AnimeEpisode:
    doc_id: str
    number: int
    name: Optional[str] = None
    thumb: Optional[str] = None
    bunny_video_id: Optional[str] = None


@dataclass
class AnimeTitle:
    object_id: str
    name: str
    english_title: Optional[str] = None
    type: Optional[str] = None
    poster: Optional[str] = None
    story: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    episodes: List[AnimeEpisode] = field(default_factory=list)


@dataclass
class AnimeServer:
    name: str
    quality: Optional[str]
    link: str
    open_browser: bool = False


def _sv(fields: dict, key: str) -> Optional[str]:
    v = fields.get(key)
    return v.get("stringValue") if isinstance(v, dict) else None


def _iv(fields: dict, key: str) -> Optional[int]:
    v = fields.get(key)
    if not isinstance(v, dict):
        return None
    raw = v.get("integerValue") or v.get("doubleValue")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _bv(fields: dict, key: str, default: bool = False) -> bool:
    v = fields.get(key)
    if not isinstance(v, dict) or "booleanValue" not in v:
        return default
    return bool(v["booleanValue"])


def _string_list(field_value: Optional[dict]) -> List[str]:
    if not isinstance(field_value, dict):
        return []
    out: List[str] = []
    for v in field_value.get("arrayValue", {}).get("values", []) or []:
        if isinstance(v, dict) and v.get("stringValue"):
            out.append(v["stringValue"])
    return out


class AnimeWitcherScraper:
    def __init__(self, timeout: float = 20.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        self._algolia_app_id = DEFAULT_ALGOLIA_APP_ID
        self._algolia_api_key = DEFAULT_ALGOLIA_API_KEY
        self._keys_refreshed = False

    async def aclose(self) -> None:
        await self._client.aclose()

    async def refresh_algolia_keys(self) -> None:
        try:
            resp = await self._client.get(f"{FIRESTORE_BASE}/Settings/constants")
            resp.raise_for_status()
            ss = (
                resp.json()
                .get("fields", {})
                .get("search_settings", {})
                .get("mapValue", {})
                .get("fields", {})
            )
            new_app_id = (ss.get("app_id_v3") or ss.get("app_id") or {}).get(
                "stringValue"
            )
            new_api_key = (ss.get("api_key") or {}).get("stringValue")
            if new_app_id and new_api_key:
                self._algolia_app_id = new_app_id
                self._algolia_api_key = new_api_key
        except Exception:
            pass
        finally:
            self._keys_refreshed = True

    def _algolia_headers(self) -> dict:
        return {
            "X-Algolia-Application-Id": self._algolia_app_id,
            "X-Algolia-API-Key": self._algolia_api_key,
            **_ALGOLIA_EXTRA_HEADERS,
        }

    def _algolia_url(self, index: str) -> str:
        return (
            f"https://{self._algolia_app_id.lower()}-dsn.algolia.net/1/indexes/"
            f"{index}/query"
        )

    async def _algolia_query(
        self, query: str, *, page: int, hits_per_page: int
    ) -> dict:
        if not self._keys_refreshed:
            await self.refresh_algolia_keys()
        encoded_query = urllib.parse.quote(query, safe="")
        encoded_attrs = urllib.parse.quote(_SEARCH_ATTRIBUTES, safe="")
        payload = {
            "params": (
                f"attributesToRetrieve={encoded_attrs}&hitsPerPage={hits_per_page}"
                f"&page={page}&query={encoded_query}"
            )
        }
        resp = await self._client.post(
            self._algolia_url("series"),
            headers=self._algolia_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _hit_to_result(h: dict) -> "AnimeSearchResult":
        return AnimeSearchResult(
            object_id=h.get("objectID") or "",
            name=h.get("name") or h.get("english_title") or "Unknown",
            english_title=h.get("english_title"),
            type=h.get("type"),
            poster=h.get("poster_uri"),
            story=h.get("story"),
        )

    async def search(self, query: str, limit: int = 20) -> List[AnimeSearchResult]:
        data = await self._algolia_query(query, page=0, hits_per_page=limit)
        return [self._hit_to_result(h) for h in data.get("hits", []) or []]

    async def browse_page(
        self, page: int, hits_per_page: int = 100
    ) -> tuple[List[AnimeSearchResult], int]:
        """Return one Algolia page of the ``series`` index plus total page count.

        Used by the static-site dump script to enumerate the whole catalog.
        """
        data = await self._algolia_query("", page=page, hits_per_page=hits_per_page)
        hits = [self._hit_to_result(h) for h in data.get("hits", []) or []]
        return hits, int(data.get("nbPages") or 1)

    async def load(self, object_id: str) -> AnimeTitle:
        resp = await self._client.get(
            f"{FIRESTORE_BASE}/anime_list/{urllib.parse.quote(object_id, safe='')}"
        )
        resp.raise_for_status()
        fields = resp.json().get("fields", {}) or {}
        title = AnimeTitle(
            object_id=object_id,
            name=_sv(fields, "name") or object_id,
            english_title=_sv(fields, "english_title"),
            type=_sv(fields, "type"),
            poster=_sv(fields, "poster_uri"),
            story=_sv(fields, "story"),
            tags=_string_list(fields.get("tags")),
        )
        title.episodes = await self.fetch_episodes(object_id)
        return title

    async def fetch_episodes(self, object_id: str) -> List[AnimeEpisode]:
        url = (
            f"{FIRESTORE_BASE}/anime_list/"
            f"{urllib.parse.quote(object_id, safe='')}/episodes?pageSize=300"
        )
        out: List[AnimeEpisode] = []
        next_token: Optional[str] = None
        for _ in range(20):
            params = {"pageToken": next_token} if next_token else None
            resp = await self._client.get(url, params=params)
            if resp.status_code != 200:
                break
            data = resp.json()
            for doc in data.get("documents", []) or []:
                fields = doc.get("fields", {}) or {}
                doc_id = doc.get("name", "").rsplit("/", 1)[-1]
                num = _iv(fields, "number")
                if num is None:
                    m = re.match(r"^\D*(\d+)", doc_id)
                    num = int(m.group(1)) if m else len(out) + 1
                out.append(
                    AnimeEpisode(
                        doc_id=doc_id,
                        number=num,
                        name=_sv(fields, "name") or _sv(fields, "title_en"),
                        thumb=_sv(fields, "thumb_uri"),
                        bunny_video_id=_sv(fields, "bunny_video_id"),
                    )
                )
            next_token = data.get("nextPageToken")
            if not next_token:
                break
        out.sort(key=lambda e: e.number)
        return out

    async def fetch_servers(
        self, object_id: str, episode_doc_id: str
    ) -> List[AnimeServer]:
        oid = urllib.parse.quote(object_id, safe="")
        eid = urllib.parse.quote(episode_doc_id, safe="")
        out: List[AnimeServer] = []

        agg_url = (
            f"{FIRESTORE_BASE}/anime_list/{oid}/episodes/{eid}/servers2/all_servers"
        )
        resp = await self._client.get(agg_url)
        if resp.status_code == 200:
            fields = resp.json().get("fields", {}) or {}
            values = (
                fields.get("servers", {}).get("arrayValue", {}).get("values", [])
            )
            for v in values:
                f = v.get("mapValue", {}).get("fields", {})
                if not _bv(f, "visible", default=True):
                    continue
                link = _sv(f, "link")
                if not link:
                    continue
                out.append(
                    AnimeServer(
                        name=_sv(f, "name") or "Server",
                        quality=_sv(f, "quality"),
                        link=link,
                        open_browser=_bv(f, "open_browser", default=False),
                    )
                )
            if out:
                return out

        coll_url = (
            f"{FIRESTORE_BASE}/anime_list/{oid}/episodes/{eid}/servers?pageSize=100"
        )
        resp = await self._client.get(coll_url)
        if resp.status_code == 200:
            for doc in resp.json().get("documents", []) or []:
                f = doc.get("fields", {}) or {}
                if not _bv(f, "visible", default=True):
                    continue
                link = _sv(f, "link")
                if not link:
                    continue
                out.append(
                    AnimeServer(
                        name=_sv(f, "name") or "Server",
                        quality=_sv(f, "quality"),
                        link=link,
                        open_browser=_bv(f, "open_browser", default=False),
                    )
                )
        return out
