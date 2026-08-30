import os
import re
from pathlib import Path
import xml.etree.ElementTree as ET


ACTION_ID_OVERRIDES = {
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
    "I_SHOT": ("I_shot", False),
    "Y_SHOT": ("Y_shot", False),
    "T_SHOT": ("T_shot", False),
    "W_SHOT": ("W_shot", False),
    "QUAD_SHOT": ("Quad_shot", False),
    "PENTA_SHOT": ("Penta_shot", False),
    "HEXA_SHOT": ("Hexa_shot", False),
}


def _parse_spell_entity(entity):
    item_action = entity.find("ItemActionComponent")
    if item_action is None:
        return None
    action_id = item_action.attrib.get("action_id")
    return action_id if action_id else None


def _parse_wand_entity(entity, source_name="uploaded_wand.xml"):
    ability = entity.find("AbilityComponent")
    if ability is None:
        return None

    gun_config = ability.find("gun_config")
    gunaction_config = ability.find("gunaction_config")

    sprite_file = ability.attrib.get("sprite_file") or ""
    sprite_id = ""
    if sprite_file:
        sprite_id = Path(sprite_file).stem

    wand = {
        "file": source_name,
        "ui_name": ability.attrib.get("ui_name") or "(unnamed wand)",
        "sprite_file": sprite_file,
        "sprite_id": sprite_id,
        "mana_max": float(ability.attrib.get("mana_max", 0)),
        "mana_charge_speed": float(ability.attrib.get("mana_charge_speed", 0)),
        "reload_time_frames": float(ability.attrib.get("reload_time_frames", 0)),
        "deck_capacity": int(gun_config.attrib.get("deck_capacity", 0)) if gun_config is not None else 0,
        "spellcast_delay_frames": float(gunaction_config.attrib.get("fire_rate_wait", 0)) if gunaction_config is not None else 0,
        "spread_degrees": float(gunaction_config.attrib.get("spread_degrees", 0)) if gunaction_config is not None else 0,
        "spells": [],
    }

    for child in entity:
        if child.tag != "Entity":
            continue
        action_id = _parse_spell_entity(child)
        if action_id:
            wand["spells"].append(action_id)

    return wand


def parse_wands_from_xml(xml_text, source_name="uploaded_wand.xml"):
    root = ET.fromstring(xml_text)
    wands = []

    for entity in root.iter("Entity"):
        if entity.find("AbilityComponent") is None:
            continue
        wand = _parse_wand_entity(entity, source_name)
        if wand is not None:
            wands.append(wand)

    return wands


def find_thumbnail_for_action(action_id, thumbnail_dir):
    thumbnail_dir = str(thumbnail_dir)
    if not os.path.isdir(thumbnail_dir):
        return None

    candidates = []

    override = ACTION_ID_OVERRIDES.get(action_id)
    if override:
        stem, has_prefix = override
        candidates.append(f"Spell_{stem}.png" if has_prefix else f"{stem}.png")

    candidates.append(f"Spell_{action_id.lower()}.png")

    seen = set()
    files = os.listdir(thumbnail_dir)
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        candidate_path = os.path.join(thumbnail_dir, candidate)
        if os.path.exists(candidate_path):
            return candidate_path

        for file_name in files:
            if file_name.lower() == candidate.lower():
                return os.path.join(thumbnail_dir, file_name)

    needle = action_id.lower().replace("_", "")
    for file_name in files:
        stem = re.sub(r"[^a-z0-9]", "", file_name.lower())
        if needle and needle in stem:
            return os.path.join(thumbnail_dir, file_name)

    return None


def parse_wands_from_folder(xml_texts):
    all_wands = []
    for item in xml_texts:
        if isinstance(item, dict):
            file_name = item.get("filename") or item.get("file_name") or "uploaded_wand.xml"
            xml_text = item.get("content") or item.get("xml_text") or ""
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            file_name, xml_text = item
        else:
            raise ValueError(f"Unsupported uploaded file entry: {item!r}")

        if isinstance(xml_text, bytes):
            xml_text = xml_text.decode("utf-8", errors="replace")

        all_wands.extend(parse_wands_from_xml(xml_text, str(file_name)))
    return all_wands
