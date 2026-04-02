#!/usr/bin/env python3
"""Fetch GeForce NOW game list from NVIDIA CDN and enrich with Steam review scores."""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

NVIDIA_URL = "https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json"
STEAM_REVIEW_URL = "https://store.steampowered.com/appreviews/{}?json=1&language=all&purchase_type=all"
OUTPUT = "public/data/data.json"
CACHE_FILE = "public/data/score-cache.json"
WORKERS = 10
RETRY = 2

STORE_URLS = {
    "Epic": "https://store.epicgames.com/browse?q={}",
    "Ubisoft Connect": "https://store.ubisoft.com/search?q={}",
    "GOG": "https://www.gog.com/games?query={}",
    "Origin": "https://www.ea.com/games?query={}",
}


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gfnlist-updater/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def extract_steam_id(steam_url):
    if not steam_url:
        return None
    m = re.search(r"/app/(\d+)", steam_url)
    return int(m.group(1)) if m else None


def fetch_steam_score(steam_id):
    for attempt in range(RETRY + 1):
        try:
            data = fetch_json(STEAM_REVIEW_URL.format(steam_id))
            qs = data.get("query_summary", {})
            return {
                "score": qs.get("review_score", 0),
                "scoreText": qs.get("review_score_desc", ""),
                "totalReviews": qs.get("total_reviews", 0),
            }
        except Exception:
            if attempt < RETRY:
                time.sleep(1)
    return None


def build_store_url(game):
    steam_url = game.get("steamUrl", "")
    if steam_url:
        return steam_url
    store = game.get("store", "")
    title = game.get("title", "")
    template = STORE_URLS.get(store)
    if template:
        return template.format(urllib.request.quote(title))
    return ""


def main():
    print("Fetching NVIDIA game list...")
    games = fetch_json(NVIDIA_URL)
    available = [g for g in games if g.get("status") == "AVAILABLE"]
    print(f"  {len(available)} available games (of {len(games)} total)")

    # Load score cache
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            cache = json.load(f)
        print(f"  Score cache: {len(cache)} entries")

    # Build game entries
    entries = []
    steam_ids_to_fetch = {}

    for game in available:
        steam_id = extract_steam_id(game.get("steamUrl", ""))
        entry = {
            "title": game["title"],
            "store": game.get("store", "") or "Other",
            "storeUrl": build_store_url(game),
            "genres": ", ".join(game.get("genres", [])),
            "publisher": game.get("publisher", ""),
            "optimized": game.get("isFullyOptimized", False),
            "score": 0,
            "scoreText": "",
            "totalReviews": 0,
        }

        if steam_id:
            cached = cache.get(str(steam_id))
            if cached:
                entry["score"] = cached["score"]
                entry["scoreText"] = cached["scoreText"]
                entry["totalReviews"] = cached["totalReviews"]
            else:
                steam_ids_to_fetch[steam_id] = entry

        entries.append(entry)

    # Fetch missing Steam scores
    to_fetch = list(steam_ids_to_fetch.keys())
    if to_fetch:
        print(f"  Fetching {len(to_fetch)} Steam scores ({WORKERS} parallel)...")
        done = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_steam_score, sid): sid for sid in to_fetch}
            for future in as_completed(futures):
                sid = futures[future]
                done += 1
                result = future.result()
                if result:
                    entry = steam_ids_to_fetch[sid]
                    entry["score"] = result["score"]
                    entry["scoreText"] = result["scoreText"]
                    entry["totalReviews"] = result["totalReviews"]
                    cache[str(sid)] = result
                if done % 100 == 0 or done == len(to_fetch):
                    print(f"    {done}/{len(to_fetch)}")

        # Save cache
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
        print(f"  Cache updated: {len(cache)} entries")
    else:
        print("  All scores cached, no API calls needed")

    # Sort by title
    entries.sort(key=lambda x: x["title"].lower())

    # Write output
    output = {"data": entries, "updated": date.today().isoformat()}
    with open(OUTPUT, "w") as f:
        json.dump(output, f)

    # Stats
    with_score = sum(1 for e in entries if e["score"] > 0)
    print(f"\nDone: {len(entries)} games, {with_score} with scores")
    print(f"Written to {OUTPUT}")


if __name__ == "__main__":
    main()
