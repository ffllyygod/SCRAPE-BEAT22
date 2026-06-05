#!/usr/bin/env python3
"""
beat22 — Download beat previews from illpeoplemusic.com

  # by producer handle (API-filtered, gets everything)
  python3 beat22.py -u runalosangeet

  # search for artist type beats, cap at 15
  python3 beat22.py -s "juice wrld" -n 15

  # search + genre + key + BPM range
  python3 beat22.py -s "durk" -g drill -k cm --bpm-min 130 --bpm-max 160 -n 10

  # search + mood + sort by plays
  python3 beat22.py -s "travis scott" -m dark --sort plays -n 5

  # just list what would be downloaded (dry-run)
  python3 beat22.py -s "yeat" -n 20 --dry-run

  # metadata only, no MP3 download
  python3 beat22.py -s "kanye" -n 10 --no-download
"""

import argparse
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
REQUEST_GAP = 0.3


def safe_filename(text: str) -> str:
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


def fetch_beats_by_handle(handle: str) -> list:
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


def get_producer_handle(beat: dict) -> str:
    ch = beat.get("created_by", {})
    if isinstance(ch, dict):
        return ch.get("handle", "").lstrip("@")
    return ""


def match_search(beat: dict, query: str) -> bool:
    q = query.lower()
    title = beat.get("title", "").lower()
    tags = " ".join(beat.get("tag", []) if isinstance(beat.get("tag"), list) else beat.get("tag", [])).lower()
    pname = get_producer_handle(beat).lower()
    return q in title or q in tags or q in pname


def normalize_key(key: str) -> str:
    """Normalize key strings for comparison (cm -> c_minor, c#m -> c_sharp_minor, etc.)"""
    k = key.lower().strip().replace(" ", "_")
    # expand sharps: c# -> c_sharp
    k = re.sub(r"([a-g])#", r"\1_sharp", k)
    # expand minor/major shorthand: cm -> c_minor, fmaj -> f_major
    k = re.sub(r"^([a-g](?:_flat|_sharp|b)?)m$", r"\1_minor", k)
    k = re.sub(r"^([a-g](?:_flat|_sharp|b)?)maj$", r"\1_major", k)
    # collapse all multi-underscores to single (API sometimes has c_sharp__minor)
    k = re.sub(r"_{2,}", "_", k)
    return k


def match_filters(beat: dict, args) -> bool:
    if args.genre:
        api_genre = beat.get("genre", "").lower().replace(" ", "_").replace("-", "_")
        user_genre = args.genre.lower().replace(" ", "_").replace("-", "_")
        if api_genre != user_genre:
            return False

    if args.mood:
        moods = [m.lower() for m in beat.get("mood", [])]
        if args.mood.lower() not in moods:
            return False

    if args.key:
        api_key = normalize_key(beat.get("key", ""))
        user_key = normalize_key(args.key)
        if api_key != user_key:
            return False

    if args.bpm_min is not None:
        if (beat.get("tempo") or 0) < args.bpm_min:
            return False

    if args.bpm_max is not None:
        if (beat.get("tempo") or 0) > args.bpm_max:
            return False

    if args.type:
        if beat.get("type", "").lower() != args.type.lower():
            return False

    return True


def fetch_beats_by_search(args) -> list:
    query = args.search
    cap = args.limit
    max_pages = args.max_pages

    print(f"[*] Searching for: \"{query}\" (cap: {cap}, max_pages: {max_pages})")
    if args.genre:
        print(f"    genre: {args.genre}")
    if args.mood:
        print(f"    mood: {args.mood}")
    if args.key:
        print(f"    key: {args.key}")
    if args.bpm_min is not None or args.bpm_max is not None:
        print(f"    bpm: {args.bpm_min or 0}-{args.bpm_max or 'any'}")
    if args.type:
        print(f"    type: {args.type}")

    matched = []
    offset = 0
    page = 1

    while True:
        if max_pages is not None and page > max_pages:
            print(f"  Reached max_pages limit ({max_pages})")
            break
        if len(matched) >= cap:
            break

        resp = api_post("beat/public-list", {
            "page": {"offset": offset, "limit": PER_PAGE},
        })
        data = resp.get("data", [])
        if not data:
            break

        found_search = 0
        for b in data:
            if match_search(b, query):
                found_search += 1
                if match_filters(b, args):
                    matched.append(b)
                    if len(matched) >= cap:
                        break

        print(f"  Page {page}: {len(data)} scanned, {found_search} matched \"{query}\""
              f" ({len(matched)} after filters, cap={cap})")

        page += 1
        offset += PER_PAGE
        if len(data) < PER_PAGE:
            break

    print(f"  Done: {len(matched)} beats matched")
    return matched


def sort_beats(beats: list, sort_by: str) -> list:
    if sort_by == "plays" or sort_by == "popular":
        return sorted(beats, key=lambda b: b.get("play_count", 0), reverse=True)
    elif sort_by == "bpm":
        return sorted(beats, key=lambda b: b.get("tempo", 0))
    elif sort_by == "title":
        return sorted(beats, key=lambda b: b.get("title", "").lower())
    elif sort_by == "newest":
        return sorted(beats, key=lambda b: b.get("createdAt", ""), reverse=True)
    elif sort_by == "oldest":
        return sorted(beats, key=lambda b: b.get("createdAt", ""))
    # default: newest first
    return sorted(beats, key=lambda b: b.get("createdAt", ""), reverse=True)


def download_one(beat: dict, outdir: str) -> bool:
    bid = beat.get("_id")
    title = beat.get("title", "Untitled")
    bpm = beat.get("tempo", 0)
    fname = safe_filename(f"{title}-{bpm}BPM")
    path = os.path.join(outdir, f"{fname}.mp3")

    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True

    # try direct preview URL first (faster, no extra API call)
    preview_url = beat.get("preview", "")
    if preview_url:
        for attempt in range(RETRIES):
            try:
                resp = requests.get(preview_url, timeout=60)
                resp.raise_for_status()
                with open(path, "wb") as f:
                    f.write(resp.content)
                return True
            except Exception:
                if attempt < RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))

    # fallback: get signed URL via API
    time.sleep(REQUEST_GAP)
    signed_url = ""
    for attempt in range(RETRIES):
        try:
            resp = SESSION.get(f"{API_BASE}/beat/{bid}/previewUrl", timeout=TIMEOUT)
            resp.raise_for_status()
            signed_url = resp.json().get("url", "")
            break
        except Exception:
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

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


def build_metadata(beats: list) -> dict:
    meta = {}
    for b in beats:
        sid = b.get("serial_number")
        meta[sid] = {
            "id": b.get("_id"),
            "serial_number": sid,
            "title": b.get("title"),
            "genre": b.get("genre"),
            "key": b.get("key"),
            "tempo": b.get("tempo"),
            "moods": b.get("mood", []),
            "tags": b.get("tag", []),
            "instruments": b.get("instrument", []),
            "cover_url": b.get("cover_picture"),
            "play_count": b.get("play_count", 0),
            "producer": get_producer_handle(b),
            "prices": [
                {
                    "licence_id": p.get("licence"),
                    "regular": p.get("regular"),
                    "final": p.get("final_price"),
                    "discount_pct": p.get("discount", {}).get("value", 0),
                }
                for p in b.get("prices", [])
            ],
            "files": [f.get("title") for f in b.get("files", [])],
            "created_at": b.get("createdAt"),
        }
    return meta


def print_dry_run(beats: list):
    print(f"\n{'─' * 70}")
    print(f" DRY-RUN: {len(beats)} beat(s) would be downloaded")
    print(f"{'─' * 70}")
    for i, b in enumerate(beats, 1):
        title = b.get("title", "?")
        bpm = b.get("tempo", "?")
        genre = b.get("genre", "?")
        key = b.get("key", "?")
        plays = b.get("play_count", 0)
        tags = ", ".join(b.get("tag", [])[:3])
        producer = get_producer_handle(b) or "?"
        print(f"  {i:>3}. {title:<40} {bpm:>3}BPM  {key:<16} {genre:<14} plays={plays:<6} @{producer}")
        if tags:
            print(f"      tags: {tags}")
    print(f"{'─' * 70}")


def main():
    parser = argparse.ArgumentParser(
        description="beat22 — Download beat previews from illpeoplemusic.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 beat22.py -u runalosangeet
  python3 beat22.py -s "juice wrld" -n 15
  python3 beat22.py -s "durk type beat" -g drill -n 10
  python3 beat22.py -s "travis scott" -m dark --sort plays -n 5
  python3 beat22.py -s "yeat" --bpm-min 140 --bpm-max 160 -n 20
  python3 beat22.py -u plutoonthebeat -g trap -n 5 --dry-run
  python3 beat22.py -s "gunna" -k cm -n 10 --no-download
        """,
    )

    # source: handle or search (at least one required)
    src = parser.add_argument_group("source (at least one required)")
    src.add_argument("-u", "--handle", help="Producer handle (e.g. runalosangeet, @plutoonthebeat)")
    src.add_argument("-s", "--search", help="Search query — matches title, tags, and producer name (e.g. 'juice wrld', 'durk type beat')")

    # result control
    res = parser.add_argument_group("result control")
    res.add_argument("-n", "--limit", type=int, default=15,
                     help="Max beats to download (default: 15 for search, unlimited for --handle)")
    res.add_argument("--max-pages", type=int, default=None,
                     help="Max API pages to scan in search mode (default: unlimited)")
    res.add_argument("--sort", choices=["newest", "oldest", "plays", "popular", "bpm", "title"],
                     default="newest", help="Sort order (default: newest)")

    # filters (client-side, applied on top of handle/search)
    filt = parser.add_argument_group("filters")
    filt.add_argument("-g", "--genre", help="Filter by genre (e.g. trap, drill, hip_hop, emo_hip_hop)")
    filt.add_argument("-m", "--mood", help="Filter by mood (e.g. dark, sad, aggressive, energetic)")
    filt.add_argument("-k", "--key", help="Filter by musical key (e.g. cm, c_sharp__minor, am)")
    filt.add_argument("--bpm-min", type=int, help="Minimum BPM")
    filt.add_argument("--bpm-max", type=int, help="Maximum BPM")
    filt.add_argument("-t", "--type", choices=["independent", "exclusive"],
                      help="Filter by beat type (independent / exclusive)")

    # output / download
    out = parser.add_argument_group("output & download")
    out.add_argument("-o", "--output", help="Output directory (default: ./beat22/<handle-or-search>)")
    out.add_argument("-w", "--workers", type=int, default=4, help="Concurrent download threads (default: 4)")
    out.add_argument("--dry-run", action="store_true", help="List matches without downloading")
    out.add_argument("--no-download", action="store_true", help="Fetch metadata only, skip MP3 downloads")
    out.add_argument("--list-genres", action="store_true", help="List available genres from the marketplace and exit")
    out.add_argument("--list-keys", action="store_true", help="List available musical keys from the marketplace and exit")
    out.add_argument("--list-moods", action="store_true", help="List available moods from the marketplace and exit")

    args = parser.parse_args()

    if not args.handle and not args.search:
        # handle discovery flags that don't need source
        if args.list_genres or args.list_keys or args.list_moods:
            pass  # allowed without source
        else:
            parser.error("Must provide --handle (-u) or --search (-s)")

    # ---- discovery flags ----
    if args.list_genres or args.list_keys or args.list_moods:
        print("[*] Sampling marketplace for available values ...")
        genres_set, keys_set, moods_set = set(), set(), set()
        for page in range(30):
            resp = api_post("beat/public-list", {"page": {"offset": page * 100, "limit": 100}})
            data = resp.get("data", [])
            if not data:
                break
            for b in data:
                if b.get("genre"):
                    genres_set.add(b["genre"])
                if b.get("key"):
                    keys_set.add(b["key"])
                for m in b.get("mood", []):
                    if m:
                        moods_set.add(m)
            if len(data) < 100:
                break

        if args.list_genres:
            print(f"\n--- GENRES ({len(genres_set)}) ---")
            for g in sorted(genres_set):
                print(f"  {g}")

        if args.list_keys:
            print(f"\n--- KEYS ({len(keys_set)}) ---")
            for k in sorted(keys_set):
                print(f"  {k}")

        if args.list_moods:
            print(f"\n--- MOODS ({len(moods_set)}) ---")
            for m in sorted(moods_set):
                print(f"  {m}")

        return

    # ---- fetch beats ----
    if args.handle:
        beats = fetch_beats_by_handle(args.handle.lstrip("@"))
        label = args.handle.lstrip("@")
    else:
        beats = fetch_beats_by_search(args)
        label = re.sub(r"[^\w\-]", "_", args.search)[:40]

    if not beats:
        print("[!] No beats found.")
        return

    # ---- apply client-side filters (for handle mode, API filter is only profile_handle) ----
    if args.handle:
        beats = [b for b in beats if match_filters(b, args)]
        print(f"[*] After client-side filters: {len(beats)} beats")

    # ---- sort ----
    beats = sort_beats(beats, args.sort)

    # ---- cap ----
    cap = args.limit
    # if handle mode and limit not explicitly changed from default 15,
    # and there's no search, treat it as "no cap" for handle mode
    if args.handle and not args.search:
        # check if user explicitly passed -n
        if "--limit" not in sys.argv and "-n" not in sys.argv:
            cap = len(beats)  # no cap for pure handle mode unless user specifies
    if len(beats) > cap:
        beats = beats[:cap]
        print(f"[*] Capped to {cap} beats (sorted by {args.sort})")

    # ---- dry-run ----
    if args.dry_run:
        print_dry_run(beats)
        return

    # ---- setup output ----
    outdir = args.output or f"./beat22/{label}"
    os.makedirs(outdir, exist_ok=True)

    # ---- save metadata ----
    meta = build_metadata(beats)
    json_path = os.path.join(outdir, "beats.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[+] Metadata saved: {json_path} ({len(meta)} beats)")

    if args.no_download:
        print("[*] --no-download set, skipping MP3 downloads.")
        print_dry_run(beats)
        return

    # ---- download MP3s ----
    print(f"[*] Downloading {len(beats)} MP3 previews to {outdir}/ ...")

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(download_one, b, outdir): b.get("title", "?")
            for b in beats
        }
        for i, f in enumerate(as_completed(futures), 1):
            if f.result():
                done += 1
            if i % 20 == 0 or i == len(futures):
                progress = f"  {i}/{len(beats)} ({done} downloaded)"
                if done > 0:
                    try:
                        sz = sum(
                            os.path.getsize(os.path.join(outdir, x))
                            for x in os.listdir(outdir)
                            if x.endswith(".mp3")
                        ) / (1024 * 1024)
                        progress += f" [{sz:.1f} MB]"
                    except Exception:
                        pass
                print(progress)

    print(f"\n[+] Done: {done}/{len(beats)} MP3s downloaded")
    try:
        size_mb = sum(
            os.path.getsize(os.path.join(outdir, x))
            for x in os.listdir(outdir)
            if x.endswith(".mp3")
        ) / (1024 * 1024)
        print(f"    Output: {outdir}/")
        print(f"    Total audio size: {size_mb:.1f} MB")
    except Exception:
        print(f"    Output: {outdir}/")


if __name__ == "__main__":
    main()
