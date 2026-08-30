import tempfile
import unittest
from pathlib import Path

from noita_wand_parser import find_thumbnail_for_action, parse_wands_from_xml


SAMPLE_XML = '''
<Entity>
  <AbilityComponent ui_name="Test Wand" mana_max="200" mana_charge_speed="20" reload_time_frames="60" sprite_file="data/items_gfx/wands/wand_1234.png">
    <gun_config deck_capacity="3" shuffle_deck_when_empty="1" />
    <gunaction_config fire_rate_wait="45" spread_degrees="12" />
  </AbilityComponent>
  <Entity>
    <ItemActionComponent action_id="BOMB" />
  </Entity>
  <Entity>
    <ItemActionComponent action_id="FIREBALL" />
  </Entity>
  <Entity>
    <ItemActionComponent action_id="BOUNCY_ORB" />
  </Entity>
</Entity>
'''


class ParseWandsFromXmlTests(unittest.TestCase):
    def test_parses_wand_entities_and_spell_order(self):
        wands = parse_wands_from_xml(SAMPLE_XML)

        self.assertEqual(len(wands), 1)
        self.assertEqual(wands[0]["ui_name"], "Test Wand")
        self.assertEqual(wands[0]["deck_capacity"], 3)
        self.assertEqual(wands[0]["spread_degrees"], 12.0)
        self.assertEqual(wands[0]["sprite_id"], "wand_1234")
        self.assertEqual(wands[0]["shuffle_deck_when_empty"], 1)
        self.assertEqual(wands[0]["spells"], ["BOMB", "FIREBALL", "BOUNCY_ORB"])

    def test_finds_thumbnail_by_spell_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            thumb_path = Path(temp_dir) / "Spell_bouncy_orb.png"
            thumb_path.write_bytes(b"fakepng")

            result = find_thumbnail_for_action("BOUNCY_ORB", temp_dir)

            self.assertEqual(result, str(thumb_path))


if __name__ == "__main__":
    unittest.main()
