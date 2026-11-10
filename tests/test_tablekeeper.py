import json
import random
import sqlite3
import tempfile
import types
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tablekeeper import rules, store
import tablekeeper


class RulesTests(unittest.TestCase):
    def test_critical_doubles_dice_only(self):
        result = rules.attack_bonus({"natural": 20, "total": 20}, 5, 18, "1d8+3", rng=random.Random(2))
        self.assertTrue(result["critical"])
        self.assertEqual(result["damage"]["formula"], "2d8+3")

    def test_advantage_uses_max_and_disadvantage_min(self):
        class Sequence:
            def __init__(self): self.values = iter([4, 19, 4, 19])
            def randint(self, a, b): return next(self.values)
        rng = Sequence()
        self.assertEqual(rules.d20(advantage=True, rng=rng)["total"], 19)
        self.assertEqual(rules.d20(disadvantage=True, rng=rng)["total"], 4)

    def test_resistance_rounds_down(self):
        self.assertEqual(rules.adjust_damage(5, resistance=True), 2)
        self.assertEqual(rules.adjust_damage(5, vulnerability=True), 10)
        self.assertEqual(rules.adjust_damage(5, resistance=True, vulnerability=True), 5)

    def test_death_saves_three_successes_failures_and_nat_cases(self):
        a, b, outcome = rules.death_save(2, 0, 10)
        self.assertEqual((a, b, outcome), (3, 0, "stable"))
        a, b, outcome = rules.death_save(0, 2, 9)
        self.assertEqual((a, b, outcome), (0, 3, "dead"))
        self.assertEqual(rules.death_save(0, 0, 20), (0, 0, "stable"))
        self.assertEqual(rules.death_save(0, 0, 1), (0, 2, None))

    def test_natural_one_misses_and_twenty_hits(self):
        self.assertFalse(rules.attack_bonus({"natural": 1, "total": 100}, 100, 1, "1d4")["hit"])
        self.assertTrue(rules.attack_bonus({"natural": 20, "total": 20}, -100, 100, "1d4")["hit"])


class StoreTests(unittest.TestCase):
    def test_persists_across_connection_reload(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "campaign.sqlite3"
            db = store.connect(path)
            state = store.load(db, "discord:room")
            state["round"] = 7
            store.save(db, "discord:room", state)
            db.close()
            self.assertEqual(store.load(store.connect(path), "discord:room")["round"], 7)


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.db = store.connect(":memory:")
        tablekeeper.DB = self.db
        self.state = store.load(self.db, "discord:room")
        self.state["characters"]["fighter"] = {**tablekeeper.CHARACTERS["fighter"], "owner": "alice", "conditions": [], "death_successes": 0, "death_failures": 0}
        store.save(self.db, "discord:room", self.state)
        self.identity = patch("tablekeeper._identity", return_value=("discord:room", "alice"))
        self.identity.start()
        self.addCleanup(self.identity.stop)

    def tearDown(self):
        self.db.close()

    def test_gateway_actor_identity_uses_transport_ids(self):
        env = {"PLATFORM": "discord", "CHAT_ID": "party-9", "ACTOR_ID": "player-3"}
        gateway = types.ModuleType("gateway")
        session = types.ModuleType("gateway.session_context")
        session.get_session_env = lambda name, default="": env.get(name.removeprefix("HERMES_SESSION_"), default)
        with patch.dict(sys.modules, {"gateway": gateway, "gateway.session_context": session}):
            self.identity.stop()
            self.assertEqual(tablekeeper._identity(), ("discord:party-9", "player-3"))
            self.identity.start()

    def test_wrong_owner_and_out_of_turn_are_refused(self):
        self.identity.stop()
        with patch("tablekeeper._identity", return_value=("discord:room", "mallory")):
            with self.assertRaises(PermissionError): tablekeeper._attack("fighter", "Goblin")
        self.identity.start()
        self.state["initiative"] = [{"name": "rogue", "initiative": 9, "monster": False}]
        store.save(self.db, "discord:room", self.state)
        with self.assertRaises(PermissionError): tablekeeper._attack("fighter", "Goblin")

    def test_monster_turn_is_deterministic_with_injected_rng(self):
        self.state["monsters"] = [{"name": "Goblin", "hp": 7, "max_hp": 7, "ac": 15, "attack": 4, "damage": "1d6+2", "speed": 30}]
        self.state["initiative"] = [{"name": "Goblin", "initiative": 12, "monster": True}]
        store.save(self.db, "discord:room", self.state)
        first = tablekeeper._monster_turn(rng=random.Random(42))
        self.state["characters"]["fighter"]["hp"] = 28
        store.save(self.db, "discord:room", self.state)
        second = tablekeeper._monster_turn(rng=random.Random(42))
        self.assertEqual(first, second)

    def test_contradiction_guard_annotates_dead_creature_action(self):
        self.state["monsters"] = [{"name": "Goblin", "hp": 0}]
        store.save(self.db, "discord:room", self.state)
        self.assertIn("cannot act", tablekeeper._guard(response_text="The goblin attacks the wizard."))
        self.assertEqual(tablekeeper._guard(response_text="The goblin is defeated."), "The goblin is defeated.")

    def test_contradiction_guard_flags_unrecorded_damage_number(self):
        self.state["monsters"] = [{"name": "Goblin", "hp": 12}]
        store.save(self.db, "discord:room", self.state)
        tablekeeper.TURN_NUMBERS.clear()
        self.assertIn("not produced by a tool", tablekeeper._guard(response_text="The goblin takes 99 damage.", session_id="turn-1"))
        tablekeeper.TURN_NUMBERS["turn-1"] = {7, 12}
        self.assertEqual(tablekeeper._guard(response_text="The goblin takes 7 damage.", session_id="turn-1"), "The goblin takes 7 damage.")

    def test_only_numeric_outcomes_from_tools_authorize_claims(self):
        session = types.ModuleType("gateway.session_context")
        session.get_session_env = lambda name, default="": "turn-2" if name.endswith("_ID") else default
        with patch.dict(sys.modules, {"gateway.session_context": session}):
            tablekeeper._post_tool_call(tool_name="tk_roll", result='{"formula":"1d8+3","dice":[2],"modifier":3,"total":5}')
        self.assertEqual(tablekeeper.TURN_NUMBERS["turn-2"], {5})


if __name__ == "__main__":
    unittest.main()
