#!/usr/bin/env python3
"""
Scrape all beats + download MP3 previews for a given producer handle.
Filenames include metadata: "{title}-{bpm}BPM.mp3"

Usage:
    python3 scrape_producer.py runalosangeet
    python3 scrape_producer.py @plutoonthebeat
"""

import json
import os
import re
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE = "https://api-server.illpeoplemusic.com/api/v2"
SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})

PER_PAGE = 100
WORKERS = 4
TIMEOUT = 30
RETRIES = 3
RETRY_DELAY = 2
REQUEST_GAP = 0.3  # seconds between API calls to avoid rate limiting


def safe_filename(text: str) -> str:
    """Sanitize a string for use as a filename."""
    text = text.replace("/", "-").replace("\\", "-").replace(":", "-")
    text = re.sub(r"[^\w\-\. ]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:100]


def api_post(endpoint: str, data: dict) -> dict:
    for attempt in range(RETRIES):
        try:
            resp = SESSION.post(f"{API_BASE}/{endpoint}", json=data, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    return {"status": "error", "data": []}


def api_get(endpoint: str) -> dict:
    for attempt in range(RETRIES):
        try:
            resp = SESSION.get(f"{API_BASE}/{endpoint}", timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    return {"status": "error"}


def fetch_beats(handle: str) -> list:
    print(f"[*] Fetching beats for @{handle} ...")
    beats = []
    offset = 0
    page = 1

    while True:
        resp = api_post("beat/public-list", {
            "page": {"offset": offset, "limit": PER_PAGE},
            "filter": {"profile_handle": f"@{handle}"},
        })
        data = resp.get("data", [])
        if not data:
            break
        beats.extend(data)
        print(f"  Page {page}: {len(data)} beats (total: {len(beats)})")
        page += 1
        offset += PER_PAGE
        if len(data) < PER_PAGE:
            break

    print(f"  Done: {len(beats)} beats found")
    return beats


def get_signed_url(beat_id: str) -> str:
    time.sleep(REQUEST_GAP)
    for attempt in range(RETRIES):
        try:
            resp = SESSION.get(f"{API_BASE}/beat/{beat_id}/previewUrl", timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json().get("url", "")
        except Exception:
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    return ""


def download_one(beat_id: str, filename: str, outdir: str) -> bool:
    path = os.path.join(outdir, f"{filename}.mp3")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True

    signed_url = get_signed_url(beat_id)
    if not signed_url:
        return False

    for attempt in range(RETRIES):
        try:
            resp = requests.get(signed_url, timeout=60)
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            return True
        except Exception:
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape_producer.py <handle>")
        print("Example: python3 scrape_producer.py runalosangeet")
        sys.exit(1)

    handle = sys.argv[1].lstrip("@")
    outdir = f"./beat22/{handle}"
    os.makedirs(outdir, exist_ok=True)

    beats = fetch_beats(handle)

    if not beats:
        print("[!] No beats found.")
        return

    # Build metadata + filenames
    meta = {}
    tasks = []  # (beat_id, filename)

    for b in beats:
        sid = b.get("serial_number")
        bid = b.get("_id")
        title = b.get("title", "Untitled")
        bpm = b.get("tempo", 0)
        key = b.get("key", "")
        genre = b.get("genre", "")

        fname = safe_filename(f"{title}-{bpm}BPM")
        tasks.append((bid, fname))

        meta[sid] = {
            "id": bid,
            "serial_number": sid,
            "title": title,
            "genre": genre,
            "key": key,
            "tempo": bpm,
            "moods": b.get("mood", []),
            "tags": b.get("tag", []),
            "instruments": b.get("instrument", []),
            "cover_url": b.get("cover_picture"),
            "play_count": b.get("play_count", 0),
            "prices": [
                {"licence_id": p.get("licence"), "regular": p.get("regular"),
                 "final": p.get("final_price"),
                 "discount_pct": p.get("discount", {}).get("value", 0)}
                for p in b.get("prices", [])
            ],
            "files": [f.get("title") for f in b.get("files", [])],
            "created_at": b.get("createdAt"),
        }

    # Save metadata JSON
    json_path = os.path.join(outdir, "beats.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[+] Metadata saved: {json_path} ({len(meta)} beats)")

    # Download MP3 previews with metadata filenames
    print(f"[*] Downloading {len(tasks)} MP3 previews to {outdir}/ ...")

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(download_one, bid, fname, outdir): fname
            for bid, fname in tasks
        }
        for i, f in enumerate(as_completed(futures), 1):
            if f.result():
                done += 1
            if i % 20 == 0 or i == len(futures):
                progress = f"  {i}/{len(tasks)} ({done} downloaded)"
                if done > 0:
                    sz = sum(
                        os.path.getsize(os.path.join(outdir, x))
                        for x in os.listdir(outdir)
                        if x.endswith(".mp3")
                    ) / (1024 * 1024)
                    progress += f" [{sz:.1f} MB]"
                print(progress)

    print(f"\n[+] Done: {done}/{len(tasks)} MP3s downloaded")
    size_mb = sum(
        os.path.getsize(os.path.join(outdir, x))
        for x in os.listdir(outdir)
        if x.endswith(".mp3")
    ) / (1024 * 1024)
    print(f"    Output: {outdir}/")
    print(f"    Total audio size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
