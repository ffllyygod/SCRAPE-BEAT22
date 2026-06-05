# beat22

Scrape and download beat previews from illpeoplemusic.com.

## Usage

```bash
pip install requests
python3 scrape_producer.py <handle>
```

Example:

```bash
python3 scrape_producer.py runalosangeet
```

Beats are saved to `beat22/<handle>/` as `{title}-{bpm}BPM.mp3` along with `beats.json` metadata.
