"""
Parses Noita wand entity XML exports (the kind produced by save-game /
entity dumps: an outer <Entity> wand with an AbilityComponent, containing
nested <Entity> spell cards) and renders a single HTML page visualizing
every wand's deck, using spell thumbnails already downloaded to disk
(see the companion download_noita_spell_thumbnails.py script).

For each wand it extracts:
  - ui_name, deck_capacity, mana_max, mana_charge_speed
  - reload time (AbilityComponent.reload_time_frames)
  - spellcast delay (the wand's own base gunaction_config.fire_rate_wait,
    i.e. the entry with action_id="")
  - the ordered list of spells actually loaded into the deck, each spell's
    action_id coming from its nested Entity's ItemActionComponent

The output is a single self-contained HTML file (thumbnails are embedded
as base64 data URIs, so the file works even if moved elsewhere). Each
wand becomes its own section with a stat header, and each spell in the
deck is its own bordered "card" segment showing the thumbnail + name.

Usage:
    python visualize_noita_wands.py

No third-party packages required - standard library only.
Configure the paths below before running.
"""

import argparse
import base64
import glob
import mimetypes
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

# ----------------------------------------------------------------------
# Defaults for a reusable project setup
# ----------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WAND_XML_DIR = PROJECT_ROOT / "input" / "wands"
DEFAULT_THUMBNAILS_DIR = PROJECT_ROOT / "assets" / "thumbnails"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_OUTPUT_FILE = "wands.html"

FRAMES_PER_SECOND = 60

# ----------------------------------------------------------------------
# action_id -> thumbnail filename overrides
#
# Most Noita spell sprites are named "Spell_<action_id lowercased>.png",
# which is what we try by default (e.g. SLOW_BULLET -> Spell_slow_bullet.png,
# BLACK_HOLE -> Spell_black_hole.png). This dict only needs entries for the
# action_ids that DON'T follow that pattern. Extend it if a spell shows up
# without an icon in your output - just add action_id: "filename stem"
# (without "Spell_" prefix or extension, unless the real file has no
# "Spell_" prefix either, like the *_shot Plicate spells below).
# ----------------------------------------------------------------------

ACTION_ID_OVERRIDES = {
    # id: (filename stem, has_spell_prefix)
    "FUNKY_SPELL": ("machinegun_bullet", True),
    "LASER_LUMINOUS_DRILL": ("luminous_drill_timer", True),
    "WORM_SHOT": ("worm", True),
    "EXPLODING_DUCKS": ("duck_2", True),
    "DISC_BULLET_BIGGER": ("omega_disc_bullet", True),
    "MASS_POLYMORPH": ("polymorph", True),
    "BOMB_DETONATOR": ("pipe_bomb_detonator", True),
    "MANA_REDUCE": ("mana", True),
    "CLUSTERMOD": ("clusterbomb", True),
    "HOMING_ROTATE": ("automatic_rotation", True),
    "BLOOD_TO_POWER": ("blood_punch", True),
    "MONEY_MAGIC": ("golden_punch", True),
    # "Plicate" utility spells: filenames have no "Spell_" prefix
    "I_SHOT": ("I_shot", False),
    "Y_SHOT": ("Y_shot", False),
    "T_SHOT": ("T_shot", False),
    "W_SHOT": ("W_shot", False),
    "QUAD_SHOT": ("Quad_shot", False),
    "PENTA_SHOT": ("Penta_shot", False),
    "HEXA_SHOT": ("Hexa_shot", False),
}

# Friendlier display names for common action_ids. Anything not listed here
# falls back to a title-cased version of the action_id itself.
ACTION_ID_NAMES = {
    "T_SHAPE": "Formation - above and below",
    "COLOUR_ORANGE": "Orange glimmer",
    "SLOW_BULLET": "Energy orb",
    "LASER_EMITTER": "Plasma beam",
    "POISON_BLAST": "Explosion of poison",
    "LIGHT": "Light",
    "TELEPORT_PROJECTILE_SHORT": "Small teleport bolt",
    "GRAVITY": "Gravity",
    "GRAVITY_ANTI": "Anti-gravity",
    "BLACK_HOLE": "Black hole",
    "LASER_LUMINOUS_DRILL": "Luminous drill with timer",
    "BOUNCY_ORB": "Energy sphere",
}


# ----------------------------------------------------------------------
# CLI / project config
# ----------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Render Noita wand XML exports into a single HTML deck viewer."
    )
    parser.add_argument(
        "--wand-dir",
        type=Path,
        default=DEFAULT_WAND_XML_DIR,
        help="Folder containing wand XML files to visualize.",
    )
    parser.add_argument(
        "--thumbnails-dir",
        type=Path,
        default=DEFAULT_THUMBNAILS_DIR,
        help="Folder containing the downloaded spell thumbnails.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where the generated HTML page will be written.",
    )
    parser.add_argument(
        "--output-file",
        default=DEFAULT_OUTPUT_FILE,
        help="Filename for the generated HTML page.",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=FRAMES_PER_SECOND,
        help="Frames per second used when converting frame counts to seconds.",
    )
    return parser.parse_args()


# ----------------------------------------------------------------------
# XML parsing
# ----------------------------------------------------------------------

def parse_wand(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    ability = root.find("AbilityComponent")
    if ability is None:
        raise ValueError(f"No AbilityComponent found in {xml_path}")

    gun_config = ability.find("gun_config")
    gunaction_config = ability.find("gunaction_config")

    wand = {
        "file": os.path.basename(xml_path),
        "ui_name": ability.attrib.get("ui_name") or "(unnamed wand)",
        "mana_max": float(ability.attrib.get("mana_max", 0)),
        "mana_charge_speed": float(ability.attrib.get("mana_charge_speed", 0)),
        "reload_time_frames": float(ability.attrib.get("reload_time_frames", 0)),
        "deck_capacity": int(gun_config.attrib.get("deck_capacity", 0)) if gun_config is not None else 0,
        "spellcast_delay_frames": float(gunaction_config.attrib.get("fire_rate_wait", 0)) if gunaction_config is not None else 0,
        "spells": [],
    }

    # Nested <Entity> elements (direct children of the wand) are the spell
    # cards loaded into the deck, in deck order.
    for child in root:
        if child.tag != "Entity":
            continue
        action_id = None
        item_action = child.find("ItemActionComponent")
        if item_action is not None:
            action_id = item_action.attrib.get("action_id")
        if action_id:
            wand["spells"].append(action_id)

    return wand


# ----------------------------------------------------------------------
# Thumbnail lookup + base64 embedding
# ----------------------------------------------------------------------

def find_thumbnail(action_id, thumb_dir, cache={}):
    if action_id in cache:
        return cache[action_id]

    candidates = []
    if action_id in ACTION_ID_OVERRIDES:
        stem, has_prefix = ACTION_ID_OVERRIDES[action_id]
        candidates.append(f"Spell_{stem}.png" if has_prefix else f"{stem}.png")

    # Default guess: Spell_<action_id lowercased>.png
    candidates.append(f"Spell_{action_id.lower()}.png")

    result = None
    for name in candidates:
        matches = glob.glob(os.path.join(thumb_dir, name))
        if not matches:
            target = name.lower()
            for f in os.listdir(thumb_dir):
                if f.lower() == target:
                    matches = [os.path.join(thumb_dir, f)]
                    break
        if matches:
            result = matches[0]
            break

    if result is None:
        # Last resort: fuzzy substring search against filenames on disk
        needle = action_id.lower().replace("_", "")
        for f in os.listdir(thumb_dir):
            stem = re.sub(r"[^a-z0-9]", "", f.lower())
            if needle and needle in stem:
                result = os.path.join(thumb_dir, f)
                break

    cache[action_id] = result
    return result


def to_data_uri(path):
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def display_name(action_id):
    if action_id in ACTION_ID_NAMES:
        return ACTION_ID_NAMES[action_id]
    return action_id.replace("_", " ").title()


# ----------------------------------------------------------------------
# HTML rendering
# ----------------------------------------------------------------------

PAGE_CSS = """
:root {
  --bg-page: #2b160e;
  --bg-section: #4a2416;
  --bg-section-header: #3a1c11;
  --border-warm: #7a4326;
  --slot-filled: #5c2c17;
  --slot-empty: #3a1e13;
  --text-cream: #f0dcc0;
  --text-muted: #c9a37c;
  --accent-gold: #e0a458;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 40px 24px;
  background: var(--bg-page);
  background-image: radial-gradient(circle at 20% 10%, rgba(224, 164, 88, 0.06), transparent 40%),
                     radial-gradient(circle at 80% 90%, rgba(90, 30, 10, 0.4), transparent 50%);
  font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
  color: var(--text-cream);
}
h1.page-title {
  text-align: center;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--accent-gold);
  margin: 0 0 8px;
  text-shadow: 0 2px 6px rgba(0,0,0,0.5);
}
p.page-subtitle {
  text-align: center;
  color: var(--text-muted);
  margin: 0 0 40px;
  font-size: 14px;
}
.wand-section {
  max-width: 980px;
  margin: 0 auto 32px;
  background: var(--bg-section);
  border: 1px solid var(--border-warm);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 6px 18px rgba(0,0,0,0.35);
}
.wand-header {
  background: var(--bg-section-header);
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-warm);
}
.wand-name {
  font-size: 18px;
  font-weight: 600;
  font-family: "Consolas", "Courier New", monospace;
  color: var(--accent-gold);
  margin: 0 0 14px;
}
.wand-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 28px;
}
.stat-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 2px;
}
.stat-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-cream);
}
.spell-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 22px 24px 26px;
}
.spell-card {
  width: 96px;
  background: var(--slot-filled);
  border: 1px solid var(--border-warm);
  border-radius: 10px;
  padding: 8px 6px 6px;
  text-align: center;
  transition: transform 0.15s ease, border-color 0.15s ease;
}
.spell-card:hover {
  transform: translateY(-3px);
  border-color: var(--accent-gold);
}
.spell-card img {
  width: 56px;
  height: 56px;
  object-fit: contain;
  display: block;
  margin: 0 auto 6px;
  background: rgba(0,0,0,0.25);
  border-radius: 6px;
}
.spell-card .missing-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.25);
  border-radius: 6px;
  color: #e07a5f;
  font-size: 22px;
  font-weight: 700;
}
.spell-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-cream);
  line-height: 1.25;
}
.spell-id {
  font-size: 9px;
  color: var(--text-muted);
  margin-top: 2px;
  word-break: break-word;
}
.spell-slot-index {
  font-size: 9px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.empty-slot {
  width: 96px;
  height: 100px;
  border: 1px dashed var(--border-warm);
  border-radius: 10px;
  background: var(--slot-empty);
  opacity: 0.5;
}
"""


def render_stat(label, value):
    return f'<div><div class="stat-label">{label}</div><div class="stat-value">{value}</div></div>'


def render_spell_card(index, action_id, thumb_dir, fps=FRAMES_PER_SECOND):
    name = display_name(action_id)
    thumb_path = find_thumbnail(action_id, thumb_dir)
    if thumb_path:
        img_html = f'<img src="{to_data_uri(thumb_path)}" alt="{name}">'
    else:
        img_html = '<div class="missing-icon">?</div>'
    return f"""<div class="spell-card">
  <div class="spell-slot-index">#{index + 1}</div>
  {img_html}
  <div class="spell-name">{name}</div>
  <div class="spell-id">{action_id}</div>
</div>"""


def render_wand_section(wand, thumb_dir, fps=FRAMES_PER_SECOND):
    reload_s = wand["reload_time_frames"] / fps
    delay_s = wand["spellcast_delay_frames"] / fps

    stats_html = "".join([
        render_stat("Capacity", wand["deck_capacity"]),
        render_stat("Spells loaded", len(wand["spells"])),
        render_stat("Reload time", f'{wand["reload_time_frames"]:.0f}f ({reload_s:.2f}s)'),
        render_stat("Spellcast delay", f'{wand["spellcast_delay_frames"]:.0f}f ({delay_s:.2f}s)'),
        render_stat("Mana", f'{wand["mana_max"]:.0f}'),
    ])

    cards_html = []
    for i, action_id in enumerate(wand["spells"]):
        cards_html.append(render_spell_card(i, action_id, thumb_dir, fps=fps))

    empty_slots = max(0, wand["deck_capacity"] - len(wand["spells"]))
    cards_html.extend(['<div class="empty-slot"></div>'] * empty_slots)

    return f"""<section class="wand-section">
  <div class="wand-header">
    <div class="wand-name">{wand["file"]}</div>
    <div class="wand-stats">{stats_html}</div>
  </div>
  <div class="spell-grid">
    {"".join(cards_html)}
  </div>
</section>"""


def render_page(wands, thumb_dir, fps=FRAMES_PER_SECOND):
    sections = "\n".join(render_wand_section(w, thumb_dir, fps=fps) for w in wands)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Noita wand decks</title>
<style>{PAGE_CSS}</style>
</head>
<body>
  <h1 class="page-title">Noita wand decks</h1>
  <p class="page-subtitle">{len(wands)} wands - capacity, reload time, spellcast delay and deck contents</p>
  {sections}
</body>
</html>"""


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    args = parse_args()
    wand_dir = args.wand_dir.expanduser().resolve()
    thumbnails_dir = args.thumbnails_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_file = args.output_file

    output_dir.mkdir(parents=True, exist_ok=True)

    xml_files = sorted(glob.glob(os.path.join(str(wand_dir), "*.xml")))
    if not xml_files:
        print(f"No .xml files found in {wand_dir}")
        return

    print(f"Found {len(xml_files)} wand file(s) in {wand_dir}\n")

    wands = []
    all_missing = set()
    for xml_path in xml_files:
        wand = parse_wand(xml_path)
        wands.append(wand)

        reload_s = wand["reload_time_frames"] / args.fps
        delay_s = wand["spellcast_delay_frames"] / args.fps
        print(f'{wand["file"]}: "{wand["ui_name"]}"')
        print(f'  capacity={wand["deck_capacity"]}  spells={len(wand["spells"])}  '
              f'reload={wand["reload_time_frames"]:.0f}f ({reload_s:.2f}s)  '
              f'cast_delay={wand["spellcast_delay_frames"]:.0f}f ({delay_s:.2f}s)')
        print(f'  deck: {", ".join(wand["spells"]) if wand["spells"] else "(empty)"}')

        for action_id in wand["spells"]:
            if find_thumbnail(action_id, str(thumbnails_dir)) is None:
                all_missing.add(action_id)
        print()

    html = render_page(wands, str(thumbnails_dir), fps=args.fps)
    out_path = output_dir / output_file
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Saved {out_path}")

    if all_missing:
        print("\nSome spells had no matching thumbnail on disk (shown with a '?' in the page). Either:")
        print("  - re-run the thumbnail downloader against the other")
        print("    spell-type sections (Static Projectile, Projectile Modifier, etc.)")
        print("  - or add an entry to ACTION_ID_OVERRIDES in this script for:")
        for a in sorted(all_missing):
            print(f"      {a}")

    print(f"\nOpen this in a browser or serve it locally with: python -m http.server 8000 --directory {output_dir}")


if __name__ == "__main__":
    main()