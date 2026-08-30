# Noita Wand Visualizer

This project reads exported Noita wand XML files and renders a single HTML page showing each wand's deck, stats, and spell thumbnails.

## What this project does

- Parses wand XML from Noita save exports
- Reads the deck order and wand attributes
- Looks up each spell's icon thumbnail
- Builds a standalone HTML page that can be opened in a browser
- Works without hardcoded personal file paths

## Project layout

- `visualize_noita_wandsv2.py` — generator script
- `assets/thumbnails/` — spell icon files (copy your downloaded thumbnails here)
- `input/wands/` — wand XML files to visualize
- `output/` — generated HTML output

## Setup

1. Create the folders:
   - `input/wands/`
   - `assets/thumbnails/`
2. Put your wand XML files into `input/wands/`
3. Copy the downloaded spell thumbnails into `assets/thumbnails/`
4. Run:

   python visualize_noita_wandsv2.py

Optional overrides:

- `--wand-dir path/to/wands`
- `--thumbnails-dir path/to/thumbnails`
- `--output-dir path/to/output`
- `--output-file wands.html`

Example:

python visualize_noita_wandsv2.py --wand-dir ./input/wands --thumbnails-dir ./assets/thumbnails --output-dir ./output

## Serving it as a web page

Because the script outputs a plain HTML file, you can either:

- open the file directly in a browser, or
- serve it locally from the project folder:

  python -m http.server 8000 --directory output

Then visit:

http://localhost:8000/wands.html

This makes the project usable by others without any machine-specific path configuration.

## Notes

- The script is intentionally written to use project-relative defaults instead of `C:\Users\...` paths.
- If a spell icon is missing, the page will still render the card with a placeholder `?` and list the missing spell id in the terminal output.
