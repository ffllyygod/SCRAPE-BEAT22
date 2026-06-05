# beat22

Scrape and download beat previews from [illpeoplemusic.com](https://illpeoplemusic.com) (Beat22 — India's biggest beats marketplace).

## Install

```bash
pip install requests
```

## Usage

### By producer handle (gets everything from one producer)

```bash
python3 beat22.py -u runalosangeet
python3 beat22.py -u @plutoonthebeat
```

### By artist / type beat search

```bash
python3 beat22.py -s "juice wrld" -n 15
python3 beat22.py -s "durk type beat" -g drill -n 10
python3 beat22.py -s "travis scott" -m dark --sort plays -n 5
python3 beat22.py -s "yeat" --bpm-min 140 --bpm-max 160 -n 20
python3 beat22.py -s "gunna" -k cm -g trap --bpm-min 130 -n 10
python3 beat22.py -s "kanye" -n 10 --no-download
```

Beats are saved to `beat22/<handle-or-search>/` as `{title}-{BPM}BPM.mp3` along with `beats.json` metadata.

## Flags

| Flag | Description |
|------|-------------|
| `-u, --handle` | Producer handle (e.g. `runalosangeet`) |
| `-s, --search` | Text search — matches title, tags, producer name |
| `-n, --limit` | Max beats to download (default: 15 for search, unlimited for `--handle`) |
| `--max-pages` | Max API pages to scan in search mode |
| `--sort` | `newest`, `oldest`, `plays`, `popular`, `bpm`, `title` (default: newest) |
| `-g, --genre` | Filter by genre: `trap`, `drill`, `hip_hop`, `emo_hip_hop`, `rnb`, etc. |
| `-m, --mood` | Filter by mood: `dark`, `sad`, `aggressive`, `energetic`, etc. |
| `-k, --key` | Filter by key: `cm`, `c#m`, `am`, `c_sharp__minor`, etc. |
| `--bpm-min` | Minimum BPM |
| `--bpm-max` | Maximum BPM |
| `-t, --type` | Beat type: `independent` or `exclusive` |
| `-o, --output` | Custom output directory |
| `-w, --workers` | Concurrent download threads (default: 4) |
| `--dry-run` | List matches, don't download |
| `--no-download` | Metadata only, skip MP3s |
| `--list-genres` | Show all available genres |
| `--list-keys` | Show all available musical keys |
| `--list-moods` | Show all available moods |

## Donate

If this tool saved you time or bandwidth, toss some SOL:

<br>
<img src="sol.svg" width="20" height="16" alt="SOL">
<code>CzuMdRvHi4ehajcxytoZX4uwAv3FYJNtQvd2fJxrVQ7q</code>
