"""Tablekeeper through Hermes' real plugin loader, registry and hook dispatcher.

The plugin is copied into a temporary HERMES_HOME/plugins, enabled in that home's config.yaml,
discovered by PluginManager, and every tool is invoked through tools.registry. Sender identity is
bound with the gateway's own set_session_vars, the way the gateway binds a turn.
"""
import json
import os
import random
import shutil
import sqlite3
import stat
import tempfile
import types
import unittest
from pathlib import Path

PLUGIN_SRC = Path(__file__).resolve().parent.parent / "tablekeeper"
GM, BOB, CAROL = "1001", "1002", "1003"


class LoadedPlugin(unittest.TestCase):
    """Load the plugin once per class from a copy, inside a throwaway Hermes home."""

    @classmethod
    def setUpClass(cls):
        cls.home = Path(tempfile.mkdtemp(prefix="tk-home-")).resolve()
        cls._old_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(cls.home)
        shutil.copytree(PLUGIN_SRC, cls.home / "plugins" / "tablekeeper", ignore=shutil.ignore_patterns("__pycache__"))
        (cls.home / "config.yaml").write_text("plugins:\n  enabled:\n    - tablekeeper\n")
        from hermes_cli import plugins
        plugins._reset_plugin_managers_for_tests()
        cls.mgr = plugins.get_plugin_manager()
        cls.mgr.discover_and_load()
        cls.loaded = cls.mgr._plugins["tablekeeper"]
        assert cls.loaded.error is None, cls.loaded.error

    @classmethod
    def tearDownClass(cls):
        from hermes_cli import plugins
        cls.loaded.module.close()
        plugins._reset_plugin_managers_for_tests()
        if cls._old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = cls._old_home
        shutil.rmtree(cls.home, ignore_errors=True)

    @property
    def plugin(self):
        return self.loaded.module

    def seed(self, n):
        self.plugin.RNG = random.Random(n)

    def tearDown(self):
        self.plugin.RNG = None

    def call(self, tool, args=None, *, user=GM, chat="g1", platform="telegram", actor_only=False, mgr=None):
        from gateway.session_context import clear_session_vars, set_session_vars
        from tools.registry import registry
        mgr = mgr or self.mgr
        tokens = set_session_vars(platform=platform, chat_id=chat, user_id="" if actor_only else user,
                                  user_name=f"user-{user}", actor_id=user)
        try:
            return json.loads(registry.dispatch(tool, args or {}, scope=mgr.scope_key))
        finally:
            clear_session_vars(tokens)

    def party(self, chat):
        """GM + fighter, rogue, wizard claimed by three different Telegram users."""
        self.assertTrue(self.call("tk_new_campaign", {"scene": "A goblin cave"}, chat=chat)["ok"])
        for user, who in ((GM, "fighter"), (BOB, "rogue"), (CAROL, "wizard")):
            self.assertTrue(self.call("tk_claim_character", {"character": who}, user=user, chat=chat)["ok"])

    def state(self, chat="g1", user=GM):
        return self.call("tk_state", chat=chat, user=user)

    OWNERS = {"fighter": GM, "rogue": BOB, "wizard": CAROL}

    def advance_to(self, chat, who):
        """End turns (rolling death saves for the dying) until `who` is the active character."""
        for _ in range(12):
            active = self.state(chat)["active"]
            if active == who:
                return
            owner = self.OWNERS[active]
            res = self.call("tk_next_turn", user=owner, chat=chat)
            if res.get("refused") == "death_save_required":
                res = self.call("tk_death_save", {"character": active}, user=owner, chat=chat)
            self.assertTrue(res["ok"], res)
        self.fail(f"{who} never became active")

    def creature(self, chat, cid):
        return next(c for c in self.state(chat)["creatures"] if c["id"] == cid)


class RegistrationTests(LoadedPlugin):
    def test_loader_registers_exactly_the_manifest(self):
        import hermes_yaml as yaml
        manifest = yaml.safe_load((PLUGIN_SRC / "plugin.yaml").read_text())
        self.assertEqual(sorted(self.loaded.tools_registered), sorted(manifest["provides_tools"]))
        self.assertEqual(sorted(set(self.loaded.hooks_registered)), sorted(manifest["provides_hooks"]))
        self.assertEqual(self.loaded.commands_registered, ["table"])
        self.assertEqual(manifest["author"], "kaverimeshram")
        self.assertEqual(manifest["license"], "MIT")

    def test_notice_carries_srd_attribution(self):
        from tablekeeper import srd
        notice = " ".join((PLUGIN_SRC / "NOTICE").read_text().split())
        self.assertIn(" ".join(srd.ATTRIBUTION.split()), notice)

    def test_state_is_a_read_only_tool_result(self):
        self.assertEqual(self.call("tk_state", chat="empty")["campaign"], None)


class IdentityTests(LoadedPlugin):
    def setUp(self):
        self.seed(1)
        self.chat = f"id-{self._testMethodName}"
        self.party(self.chat)

    def test_unidentified_sender_is_refused(self):
        from gateway.session_context import clear_session_vars, set_session_vars
        from tools.registry import registry
        tokens = set_session_vars(platform="telegram", chat_id=self.chat)
        try:
            res = json.loads(registry.dispatch("tk_attack", {"character": "fighter", "target": "x"}, scope=self.mgr.scope_key))
        finally:
            clear_session_vars(tokens)
        self.assertFalse(res["ok"])
        self.assertEqual(res["refused"], "identity_unavailable")

    def test_character_acts_only_for_its_owner(self):
        res = self.call("tk_check", {"character": "fighter", "skill_or_ability": "athletics", "dc": 10}, user=BOB, chat=self.chat)
        self.assertEqual((res["ok"], res["refused"]), (False, "not_owner"))
        res = self.call("tk_check", {"character": "fighter", "skill_or_ability": "athletics", "dc": 10}, user=GM, chat=self.chat)
        self.assertTrue(res["ok"])

    def test_observe_mode_sender_comes_from_the_actor_id(self):
        res = self.call("tk_check", {"character": "rogue", "skill_or_ability": "stealth", "dc": 12}, user=BOB,
                        chat=self.chat, actor_only=True)
        self.assertTrue(res["ok"], res)
        res = self.call("tk_check", {"character": "rogue", "skill_or_ability": "stealth", "dc": 12}, user=CAROL,
                        chat=self.chat, actor_only=True)
        self.assertEqual(res["refused"], "not_owner")

    def test_campaigns_are_scoped_to_their_chat(self):
        other = self.call("tk_state", chat=self.chat + "-other")
        self.assertIsNone(other["campaign"])
        self.assertEqual(len(self.state(self.chat)["creatures"]), 3)

    def test_only_the_game_master_adjudicates(self):
        for tool, args in (("tk_damage", {"target": "fighter", "amount": 3}), ("tk_heal", {"target": "fighter", "amount": 3}),
                           ("tk_condition", {"target": "fighter", "condition": "prone"}),
                           ("tk_start_combat", {"monsters": [{"type": "goblin"}]}), ("tk_rest", {"kind": "long"})):
            res = self.call(tool, args, user=BOB, chat=self.chat)
            self.assertEqual(res["refused"], "gm_only", tool)

    def test_one_character_per_player_and_no_double_claim(self):
        self.assertEqual(self.call("tk_claim_character", {"character": "cleric"}, user=BOB, chat=self.chat)["refused"], "one_character")
        self.assertEqual(self.call("tk_claim_character", {"character": "fighter"}, user=CAROL + "9", chat=self.chat)["refused"], "already_claimed")

    def test_local_cli_user_owns_every_character(self):
        self.assertTrue(self.call("tk_new_campaign", {}, platform="cli", chat="")["ok"])
        for who in ("fighter", "wizard"):
            self.assertTrue(self.call("tk_claim_character", {"character": who}, platform="cli", chat="")["ok"])
        res = self.call("tk_check", {"character": "wizard", "skill_or_ability": "arcana", "dc": 5}, platform="cli", chat="")
        self.assertTrue(res["ok"])

    def test_replacing_a_campaign_needs_the_game_master_and_confirmation(self):
        self.assertEqual(self.call("tk_new_campaign", {}, user=BOB, chat=self.chat)["refused"], "gm_only")
        self.assertEqual(self.call("tk_new_campaign", {}, chat=self.chat)["refused"], "campaign_exists")
        self.assertTrue(self.call("tk_new_campaign", {"replace": True}, chat=self.chat)["ok"])
        self.assertEqual(self.state(self.chat)["creatures"], [])


class CombatTests(LoadedPlugin):
    def setUp(self):
        self.chat = f"cb-{self._testMethodName}"

    def start(self, seed, monsters):
        self.seed(seed)
        self.party(self.chat)
        res = self.call("tk_start_combat", {"monsters": monsters}, chat=self.chat)
        self.assertTrue(res["ok"], res)
        return res

    def owner_of(self, cid):
        return {"fighter": GM, "rogue": BOB, "wizard": CAROL}[cid]

    def test_turn_order_is_enforced(self):
        res = self.start(5, [{"type": "goblin", "count": 2}])
        active = res["active"]["id"]
        others = [c for c in ("fighter", "rogue", "wizard") if c != active]
        foe = next(c["id"] for c in self.state(self.chat)["creatures"] if c["kind"] == "monster")
        refused = self.call("tk_attack", {"character": others[0], "target": foe}, user=self.owner_of(others[0]), chat=self.chat)
        self.assertEqual(refused["refused"], "not_your_turn")
        self.assertEqual(refused["active"], active)
        wrong_player = self.call("tk_attack", {"character": active, "target": foe}, user=CAROL if active != "wizard" else BOB, chat=self.chat)
        self.assertEqual(wrong_player["refused"], "not_owner")
        wrong_end = self.call("tk_next_turn", user=CAROL if active != "wizard" else BOB, chat=self.chat)
        self.assertEqual(wrong_end["refused"], "not_your_turn")
        self.assertEqual(self.state(self.chat)["active"], active)

    def test_one_action_per_turn_and_range_is_enforced(self):
        res = self.start(6, [{"type": "goblin", "x": 11, "y": 0}])
        active = res["active"]["id"]
        user = self.owner_of(active)
        far = self.call("tk_attack", {"character": active, "target": "goblin-1"}, user=user, chat=self.chat)
        self.assertEqual(far["refused"], "out_of_range")
        pos = next(c for c in self.state(self.chat)["creatures"] if c["id"] == active)["pos"]
        moved = self.call("tk_move", {"character": active, "x": 10, "y": 0}, user=user, chat=self.chat)
        self.assertEqual(moved["refused"], "too_far", (pos, moved))
        self.assertGreaterEqual(moved["cost"], moved["movement_left"])

    def test_three_round_combat_ends_in_a_known_state(self):
        monsters = [{"type": "ogre", "x": 6, "y": 4}, {"type": "goblin", "x": 7, "y": 6}]
        first = self.play_rounds(self.chat, 21, monsters, rounds=3)
        again = self.play_rounds(self.chat + "-again", 21, monsters, rounds=3)
        self.assertEqual({**first["snapshot"], "chat": ""}, {**again["snapshot"], "chat": ""}, "same seed, same table")
        self.assertEqual(first["snapshot"]["round"], 4)
        creatures = {c["id"]: c for c in first["snapshot"]["creatures"]}
        ogre = creatures["ogre-1"]
        self.assertEqual(ogre["hp"], ogre["max_hp"] - first["damage_dealt"]["ogre-1"])
        self.assertTrue(all(0 <= c["hp"] <= c["max_hp"] for c in creatures.values()))
        log = [e["text"] for e in first["snapshot"]["log"]]
        self.assertIn("Combat begins", " ".join(log))
        rolls = first["snapshot"]["rolls"]
        self.assertTrue(rolls and all(r["dice"] for r in rolls if r["kind"] in ("attack", "initiative")))
        self.assertEqual(sum(1 for e in log if "ends their turn" in e) >= 9, True)

    def play_rounds(self, chat, seed, monsters, rounds):
        """Drive every character through `rounds` full rounds, moving into reach and attacking."""
        self.chat = chat
        self.seed(seed)
        self.party(chat)
        res = self.call("tk_start_combat", {"monsters": monsters}, chat=chat)
        self.assertTrue(res["ok"], res)
        damage = {"ogre-1": 0, "goblin-1": 0}
        for _ in range(60):
            state = self.state(chat)
            if not state["in_combat"] or state["round"] > rounds:
                break
            active = next(c for c in state["creatures"] if c["id"] == state["active"])
            user = self.owner_of(active["id"])
            if active["status"] == "down":
                step = self.call("tk_death_save", {"character": active["id"]}, user=user, chat=chat)
                self.assertTrue(step["ok"], step)
                continue
            foes = [c for c in state["creatures"] if c["kind"] == "monster" and c["status"] == "ok"]
            target = min(foes, key=lambda f: max(abs(f["pos"][0] - active["pos"][0]), abs(f["pos"][1] - active["pos"][1])))
            ranged = active["id"] == "wizard"
            if ranged:
                step = self.call("tk_cast", {"character": "wizard", "spell": "fire bolt", "targets": [target["id"]]}, user=user, chat=chat)
                if step["ok"]:
                    for e in step["results"]:
                        damage[e["target"]] += (e.get("damage") or {}).get("applied", 0)
            else:
                gap = max(abs(target["pos"][0] - active["pos"][0]), abs(target["pos"][1] - active["pos"][1]))
                reach = min(gap - 1, active["speed"] // 5)
                if gap > 1:
                    dx = 1 if target["pos"][0] > active["pos"][0] else -1
                    dy = (target["pos"][1] > active["pos"][1]) - (target["pos"][1] < active["pos"][1])
                    dest = [active["pos"][0] + dx * reach, active["pos"][1] + dy * min(reach, abs(target["pos"][1] - active["pos"][1]))]
                    self.call("tk_move", {"character": active["id"], "x": dest[0], "y": dest[1]}, user=user, chat=chat)
                step = self.call("tk_attack", {"character": active["id"], "target": target["id"]}, user=user, chat=chat)
                if step["ok"] and step["hit"]:
                    damage[step["target"]] += step["damage"]
            res = self.call("tk_next_turn", user=user, chat=chat)
            self.assertTrue(res["ok"], res)
        snap = self.snapshot(chat)
        return {"snapshot": snap, "damage_dealt": damage}

    def snapshot(self, chat):
        from hermes_cli.plugins import get_plugin_manager  # noqa: F401  (loader already holds the module)
        db = sqlite3.connect(f"file:{self.home / 'plugin-data' / 'tablekeeper' / 'campaigns.sqlite3'}?mode=ro", uri=True)
        try:
            state = json.loads(db.execute("SELECT state FROM campaigns WHERE chat=?", (f"telegram:{chat}",)).fetchone()[0])
        finally:
            db.close()
        for e in state["log"]:
            e.pop("ts"), e.pop("seq")
        for r in state["rolls"]:
            r.pop("ts"), r.pop("seq")
        state.pop("updated")
        return state

    def test_death_saves_and_party_defeat_are_reported(self):
        res = self.start(3, [{"type": "ogre", "count": 1, "x": 1, "y": 5}, {"type": "ogre", "x": 2, "y": 4}])
        hurt = self.call("tk_damage", {"target": "wizard", "amount": 40, "damage_type": "bludgeoning", "reason": "rockfall"}, chat=self.chat)
        self.assertEqual(hurt["state"], "dead", "40 damage meets the wizard's maximum after 0 HP: massive damage")
        down = self.call("tk_damage", {"target": "rogue", "amount": 24, "damage_type": "bludgeoning"}, chat=self.chat)
        self.assertEqual(down["state"], "down")
        stable = self.call("tk_condition", {"target": "rogue", "condition": "stable"}, chat=self.chat)
        self.assertIn("stable", stable["conditions"])
        self.assertEqual(self.call("tk_heal", {"target": "wizard", "amount": 5}, chat=self.chat)["state"], "dead")

    def test_monster_turns_run_inside_next_turn_and_are_reported(self):
        res = self.start(8, [{"type": "wolf", "count": 2}])
        saw_monster = bool(res["monster_turns"])
        for _ in range(12):
            state = self.state(self.chat)
            if not state["in_combat"]:
                break
            active = state["active"]
            step = self.call("tk_next_turn", user=self.owner_of(active), chat=self.chat)
            if step.get("refused") == "death_save_required":
                step = self.call("tk_death_save", {"character": active}, user=self.owner_of(active), chat=self.chat)
            self.assertTrue(step["ok"], step)
            saw_monster = saw_monster or bool(step["monster_turns"])
        self.assertTrue(saw_monster)
        actions = [t["action"] for t in step["monster_turns"]]
        self.assertTrue(set(actions) <= {"attack", "move", "flee", "none"})


class TableRuleTests(LoadedPlugin):
    def setUp(self):
        self.chat = f"tr-{self._testMethodName}"

    def fight(self, seed, monsters, mover):
        self.seed(seed)
        self.party(self.chat)
        self.assertTrue(self.call("tk_start_combat", {"monsters": monsters}, chat=self.chat)["ok"])
        self.advance_to(self.chat, mover)

    def test_leaving_reach_provokes_and_disengage_does_not(self):
        self.fight(1, [{"type": "goblin", "x": 1, "y": 4}], "rogue")
        moved = self.call("tk_move", {"character": "rogue", "x": 0, "y": 2}, user=BOB, chat=self.chat)
        self.assertEqual(moved["left_reach_of"], ["goblin-1"])
        self.assertEqual([a["attacker"] for a in moved["opportunity_attacks"]], ["goblin-1"])
        self.assertEqual(moved["movement_left"], 15)

    def test_disengage_spends_the_action_and_avoids_the_attack(self):
        self.fight(1, [{"type": "goblin", "x": 1, "y": 4}], "rogue")
        moved = self.call("tk_move", {"character": "rogue", "x": 0, "y": 2, "disengage": True}, user=BOB, chat=self.chat)
        self.assertEqual(moved["opportunity_attacks"], [])
        again = self.call("tk_attack", {"character": "rogue", "target": "goblin-1"}, user=BOB, chat=self.chat)
        self.assertEqual(again["refused"], "action_used")

    def test_dying_character_rolls_death_saves_on_their_turn_and_it_ends_the_turn(self):
        self.fight(3, [{"type": "goblin", "x": 11, "y": 0}], "rogue")
        down = self.call("tk_damage", {"target": "rogue", "amount": 24, "damage_type": "slashing"}, chat=self.chat)
        self.assertEqual(down["state"], "down")
        self.assertEqual(self.call("tk_attack", {"character": "rogue", "target": "goblin-1"}, user=BOB, chat=self.chat)["refused"], "cannot_act")
        self.assertEqual(self.call("tk_next_turn", user=BOB, chat=self.chat)["refused"], "death_save_required")
        self.assertEqual(self.call("tk_death_save", {"character": "rogue"}, user=CAROL, chat=self.chat)["refused"], "not_owner")
        saved = self.call("tk_death_save", {"character": "rogue"}, user=BOB, chat=self.chat)
        self.assertTrue(saved["ok"], saved)
        self.assertEqual(saved["successes"] + saved["failures"] > 0 or saved["outcome"] == "critical_success", True)
        self.assertNotEqual(self.state(self.chat)["active"], "rogue")
        stabilise = self.call("tk_condition", {"target": "rogue", "condition": "stable"}, chat=self.chat)
        if saved["state"] == "down":
            self.assertIn("stable", stabilise["conditions"])
            self.assertEqual(self.creature(self.chat, "rogue")["status"], "stable")

    def test_concentration_is_checked_and_a_failed_save_frees_the_target(self):
        for seed, kept in ((2, True), (4, False)):
            chat = f"{self.chat}-{seed}"
            self.chat = chat
            self.fight(seed, [{"type": "bandit", "x": 3, "y": 5}], "wizard")
            cast = self.call("tk_cast", {"character": "wizard", "spell": "hold person", "targets": ["bandit-1"], "slot_level": 2},
                             user=CAROL, chat=chat)
            self.assertTrue(cast["ok"], cast)
            self.assertIn("paralyzed", self.creature(chat, "bandit-1")["conditions"])
            hurt = self.call("tk_damage", {"target": "wizard", "amount": 6, "damage_type": "slashing"}, chat=chat)
            self.assertEqual(hurt["concentration"]["kept"], kept)
            self.assertEqual(hurt["concentration"]["dc"], 10)
            self.assertEqual("paralyzed" in self.creature(chat, "bandit-1")["conditions"], kept)
            self.assertEqual(self.creature(chat, "wizard")["concentration"] is not None, kept)

    def test_spells_spend_slots_and_unprepared_spells_are_refused(self):
        self.fight(5, [{"type": "ogre", "x": 11, "y": 0}], "wizard")
        before = self.creature(self.chat, "wizard")["slots"]["1"][0]
        first = self.call("tk_cast", {"character": "wizard", "spell": "magic missile", "targets": ["ogre-1"]}, user=CAROL, chat=self.chat)
        self.assertTrue(first["ok"], first)
        self.assertEqual(first["slot_used"], 1)
        self.assertEqual(self.creature(self.chat, "wizard")["slots"]["1"][0], before - 1)
        self.assertEqual(self.call("tk_cast", {"character": "wizard", "spell": "burning hands", "targets": ["ogre-1"]}, user=CAROL,
                                   chat=self.chat)["refused"], "action_used")
        self.assertEqual(self.call("tk_cast", {"character": "wizard", "spell": "bless", "targets": ["ogre-1"]}, user=CAROL,
                                   chat=self.chat)["refused"], "action_used")
        self.assertTrue(self.call("tk_next_turn", user=CAROL, chat=self.chat)["ok"])
        self.advance_to(self.chat, "wizard")
        unprepared = self.call("tk_cast", {"character": "wizard", "spell": "bless", "targets": ["fighter"]}, user=CAROL, chat=self.chat)
        self.assertEqual(unprepared["refused"], "invalid_input")
        self.assertIn("prepared", unprepared["message"])

    def test_rests_heal_outside_combat_only(self):
        self.seed(6)
        self.party(self.chat)
        self.call("tk_damage", {"target": "fighter", "amount": 15, "damage_type": "fire"}, chat=self.chat)
        self.assertEqual(self.creature(self.chat, "fighter")["hp"], 13)
        short = self.call("tk_rest", {"kind": "short", "character": "fighter", "hit_dice": 2}, chat=self.chat)
        self.assertGreater(short["results"]["fighter"]["healed"], 0)
        self.assertEqual(short["results"]["fighter"]["hit_dice"][0], 1)
        self.assertEqual(self.call("tk_rest", {"kind": "short", "character": "fighter"}, user=BOB, chat=self.chat)["refused"], "not_owner")
        long = self.call("tk_rest", {"kind": "long"}, chat=self.chat)
        self.assertEqual(long["results"]["fighter"]["hp"], 28)
        self.call("tk_start_combat", {"monsters": [{"type": "goblin"}]}, chat=self.chat)
        self.assertEqual(self.call("tk_rest", {"kind": "long"}, chat=self.chat)["refused"], "combat_running")

    def test_victory_awards_xp_and_ends_combat(self):
        self.fight(7, [{"type": "kobold", "x": 11, "y": 0}], "fighter")
        res = self.call("tk_damage", {"target": "kobold-1", "amount": 50, "damage_type": "fire"}, chat=self.chat)
        self.assertEqual(res["combat_over"], {"outcome": "victory", "xp": 25})
        state = self.state(self.chat)
        self.assertFalse(state["in_combat"])
        self.assertEqual(self.call("tk_next_turn", user=GM, chat=self.chat)["refused"], "no_combat")
        self.assertEqual(self.call("tk_attack", {"character": "fighter", "target": "kobold-1"}, chat=self.chat)["refused"], "invalid_target")


class PersistenceTests(LoadedPlugin):
    def test_state_survives_closing_connections_and_a_forced_reload(self):
        self.seed(4)
        chat = "persist"
        self.party(chat)
        self.call("tk_start_combat", {"monsters": [{"type": "goblin", "count": 2}]}, chat=chat)
        before = self.state(chat)
        self.plugin.close()
        self.mgr.discover_and_load(force=True)
        type(self).loaded = self.mgr._plugins["tablekeeper"]
        self.assertIsNone(self.loaded.error)
        self.assertEqual(self.state(chat), before)

    def test_database_lives_in_the_profile_data_dir_with_private_permissions(self):
        self.party("perms")
        path = self.home / "plugin-data" / "tablekeeper" / "campaigns.sqlite3"
        self.assertTrue(path.exists())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertGreaterEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
        for side in path.parent.glob("campaigns.sqlite3-*"):
            self.assertEqual(stat.S_IMODE(side.stat().st_mode), 0o600, side.name)
        self.assertFalse((Path.home() / ".hermes" / "plugin-data" / "tablekeeper").exists() and
                         (Path.home() / ".hermes" / "plugin-data" / "tablekeeper" / "campaigns.sqlite3").stat().st_mtime > path.stat().st_mtime)

    def test_each_profile_has_its_own_campaigns(self):
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override
        from hermes_cli import plugins
        self.party("shared-name")
        other = Path(tempfile.mkdtemp(prefix="tk-profile-")).resolve()
        shutil.copytree(PLUGIN_SRC, other / "plugins" / "tablekeeper", ignore=shutil.ignore_patterns("__pycache__"))
        (other / "config.yaml").write_text("plugins:\n  enabled:\n    - tablekeeper\n")
        token = set_hermes_home_override(str(other))
        try:
            mgr = plugins.get_plugin_manager()
            mgr.discover_and_load()
            self.assertIsNone(mgr._plugins["tablekeeper"].error)
            self.assertIsNone(self.call("tk_state", chat="shared-name", mgr=mgr)["campaign"])
            self.assertTrue(self.call("tk_new_campaign", {}, chat="shared-name", mgr=mgr)["ok"])
            self.assertTrue((other / "plugin-data" / "tablekeeper" / "campaigns.sqlite3").exists())
            mgr._plugins["tablekeeper"].module.close()
        finally:
            reset_hermes_home_override(token)
            shutil.rmtree(other, ignore_errors=True)
        self.assertEqual(len(self.state("shared-name")["creatures"]), 3)


class HookTests(LoadedPlugin):
    def setUp(self):
        self.seed(9)
        self.chat = f"hk-{self._testMethodName}"
        self.party(self.chat)

    def hook(self, name, *, user=GM, **kw):
        from gateway.session_context import clear_session_vars, set_session_vars
        tokens = set_session_vars(platform="telegram", chat_id=self.chat, user_id=user, actor_id=user)
        try:
            return self.mgr.invoke_hook(name, **kw)
        finally:
            clear_session_vars(tokens)

    def turn(self, narration, tools=()):
        """One model turn: pre_llm_call, the tool results, then the model's final text."""
        ctx = self.hook("pre_llm_call", session_id="s1", user_message="go", conversation_history=[], is_first_turn=False,
                        model="m", platform="telegram")
        for name, result in tools:
            self.hook("post_tool_call", tool_name=name, args={}, result=json.dumps(result), session_id="s1")
        return ctx, self.hook("transform_llm_output", response_text=narration, session_id="s1", model="m", platform="telegram")

    def test_context_is_authoritative_compact_and_names_the_senders_character(self):
        self.call("tk_start_combat", {"monsters": [{"type": "goblin", "count": 3}, {"type": "wolf", "count": 2}, {"type": "ogre"}]}, chat=self.chat)
        ctx = self.hook("pre_llm_call", user=BOB, session_id="s0", user_message="hi", conversation_history=[],
                        is_first_turn=False, model="m", platform="telegram")
        text = ctx[0]["context"]
        self.assertIn("Sender controls: rogue.", text)
        self.assertIn("goblin-3", text)
        self.assertIn("HP 59/59", text)
        self.assertLessEqual(len(text) / 4, 600, f"{len(text)} chars is over the 600 token budget")

    def test_no_campaign_means_no_injection(self):
        from gateway.session_context import clear_session_vars, set_session_vars
        tokens = set_session_vars(platform="telegram", chat_id="nobody-plays-here", user_id=GM, actor_id=GM)
        try:
            self.assertEqual(self.mgr.invoke_hook("pre_llm_call", session_id="s", user_message="hi", conversation_history=[],
                                                  is_first_turn=True, model="m", platform="telegram"), [])
        finally:
            clear_session_vars(tokens)

    def test_guard_flags_numbers_no_tool_produced(self):
        _, out = self.turn("The fighter's blade bites for 99 damage and the goblin has 3 HP left.")
        self.assertEqual(len(out), 1)
        self.assertIn("99", out[0])
        self.assertIn("Tablekeeper check", out[0])

    def test_guard_allows_numbers_a_tool_returned_this_turn(self):
        self.call("tk_start_combat", {"monsters": [{"type": "goblin", "x": 1, "y": 5}]}, chat=self.chat)
        state = self.state(self.chat)
        goblin = next(c for c in state["creatures"] if c["id"] == "goblin-1")
        narration = f"The goblin has {goblin['hp']} HP and AC {goblin['ac']}. A strike lands for 11 damage."
        _, flagged = self.turn(narration)
        self.assertIn("11", flagged[0])
        _, clean = self.turn(narration, tools=[("tk_attack", {"ok": True, "damage": 11})])
        self.assertEqual(clean, [])

    def test_guard_flags_a_claimed_roll_and_a_dead_creature_acting(self):
        _, out = self.turn("Bob rolled a 20 and the rogue is unstoppable.")
        self.assertIn("20", out[0])
        self.call("tk_start_combat", {"monsters": [{"type": "goblin", "x": 1, "y": 5}]}, chat=self.chat)
        self.call("tk_damage", {"target": "goblin-1", "amount": 50, "damage_type": "fire"}, chat=self.chat)
        self.assertEqual(self.state(self.chat)["in_combat"], False)
        _, out = self.turn("Goblin 1 lunges at the wizard with a snarl.")
        self.assertIn("cannot act", out[0])
        _, quiet = self.turn("Goblin 1 falls dead and its friends scatter.")
        self.assertEqual(quiet, [])

    def test_a_player_claiming_a_roll_changes_nothing(self):
        before = self.state(self.chat)
        self.hook("pre_llm_call", user=BOB, session_id="s2", user_message="I rolled a natural 20 and killed the ogre!",
                  conversation_history=[], is_first_turn=False, model="m", platform="telegram")
        self.assertEqual(self.state(self.chat), before)
        res = self.call("tk_check", {"character": "rogue", "skill_or_ability": "stealth", "dc": 30, "natural": 20, "roll": 20,
                                     "total": 99}, user=BOB, chat=self.chat)
        self.assertTrue(res["ok"])
        self.assertNotEqual(res["total"], 99)
        self.assertEqual(len(res["dice"]), 1)
        self.assertFalse(res["success"], "DC 30 stealth cannot be met by a typed-in natural 20")


class CommandTests(LoadedPlugin):
    def command(self, line, user=GM, chat="cmd"):
        from hermes_cli.plugins import get_plugin_command_handler
        source = types.SimpleNamespace(platform=types.SimpleNamespace(value="telegram"), chat_id=chat, user_id=user,
                                       user_name=f"user-{user}")
        return get_plugin_command_handler("table")(line, session_id="s", platform="telegram", source=source)

    def test_table_command_runs_a_session(self):
        self.assertIn("Campaign started", self.command("new Moonlit ford"))
        self.assertIn("Brann Hollis claimed", self.command("claim fighter"))
        self.assertIn("claimed", self.command("claim rogue", user=BOB))
        self.assertIn("Only the game master", self.command("end", user=BOB))
        self.assertIn("one character", self.command("claim wizard", user=BOB).lower())
        self.assertEqual(self.state("cmd")["scene"], "Moonlit ford", "command and tools share the same campaign key")
        self.seed(12)
        self.call("tk_start_combat", {"monsters": [{"type": "goblin", "x": 5, "y": 5}]}, chat="cmd")
        grid = self.command("map")
        self.assertTrue(grid.startswith("```"))
        self.assertIn("A Brann Hollis", grid)
        self.assertIn("1 Goblin 1", grid)
        self.assertIn("Combat begins", self.command("log") + self.command("recap"))
        self.assertIn("Combat ended", self.command("end"))
        self.assertIn("goblin-1", self.command("status"))

    def test_new_over_an_existing_campaign_asks_for_confirmation(self):
        self.command("new", chat="cmd2")
        self.command("claim fighter", chat="cmd2")
        self.assertIn("confirm", self.command("new", chat="cmd2"))
        self.assertEqual(len(self.state("cmd2")["creatures"]), 1)
        self.assertIn("Campaign started", self.command("new confirm", chat="cmd2"))
        self.assertEqual(self.state("cmd2")["creatures"], [])


if __name__ == "__main__":
    unittest.main()


class LivePlayTests(LoadedPlugin):
    """Behaviour a real mid-tier model needed in a live Hermes session (nemotron via OpenRouter)."""

    def setUp(self):
        self.cli = lambda tool, args=None: self.call(tool, args, platform="cli", chat="")
        self.cli("tk_new_campaign", {"replace": True})
        self.cli("tk_claim_character", {"character": "fighter"})

    def spawn_goblins(self, seed=3, monsters=None):
        self.seed(seed)
        res = self.cli("tk_start_combat", {"monsters": monsters or [{"type": "goblin", "count": 3, "x": 5, "y": 5}]})
        self.assertTrue(res["ok"], res)
        return res

    def test_a_group_with_one_position_clusters_around_it(self):
        res = self.cli("tk_start_combat", {"monsters": [{"type": "goblin", "count": 3, "x": 8, "y": 5}]})
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["spawned"], ["goblin-1", "goblin-2", "goblin-3"])
        spots = {tuple(c["pos"]) for c in self.cli("tk_state")["creatures"] if c["kind"] == "monster"}
        self.assertEqual(len(spots), 3)

    def test_creature_references_forgive_case_spaces_and_dashes(self):
        self.spawn_goblins()
        for ref in ("Goblin 1", "goblin 1", "goblin-1", "goblin1", "GOBLIN_1"):
            res = self.cli("tk_damage", {"target": ref, "amount": 0})
            self.assertTrue(res["ok"], (ref, res))
            self.assertEqual(res["target"]["id"], "goblin-1")

    def test_character_defaults_to_the_senders_only_character(self):
        self.assertEqual(self.cli("tk_check", {"skill_or_ability": "perception", "dc": 5})["character"], "fighter")
        self.cli("tk_claim_character", {"character": "wizard"})
        res = self.cli("tk_check", {"skill_or_ability": "perception"})
        self.assertEqual(res["refused"], "invalid_input")
        self.assertIn("fighter, wizard", res["message"])

    def test_character_is_optional_in_every_schema(self):
        from tools.registry import registry
        for name in ("tk_check", "tk_save", "tk_attack", "tk_cast", "tk_move", "tk_death_save", "tk_rest"):
            required = registry.get_entry(name).schema["parameters"]["required"]
            self.assertNotIn("character", required, name)

    def test_move_toward_a_foe_closes_by_the_movement_left(self):
        self.spawn_goblins(monsters=[{"type": "goblin", "x": 11, "y": 0}])
        for _ in range(8):
            if self.cli("tk_state")["active"] == "fighter":
                break
            self.cli("tk_next_turn")

        def gap():
            by = {c["id"]: c["pos"] for c in self.cli("tk_state")["creatures"]}
            return max(abs(by["goblin-1"][0] - by["fighter"][0]), abs(by["goblin-1"][1] - by["fighter"][1]))
        before = gap()
        mv = self.cli("tk_move", {"toward": "goblin 1"})
        self.assertTrue(mv["ok"], mv)
        self.assertGreater(before, 1)
        self.assertEqual(gap(), max(1, before - 6), "30 ft is 6 squares, stopping next to the goblin")
        self.assertLessEqual(mv["feet"], 30)
        self.assertEqual(self.cli("tk_move", {"toward": "fighter"})["refused"], "invalid_input")

    def test_a_character_at_zero_hp_is_pointed_to_the_death_save(self):
        self.cli("tk_damage", {"target": "fighter", "amount": 28})
        for tool, args in (("tk_check", {"skill_or_ability": "constitution", "dc": 10}), ("tk_save", {"ability": "con", "dc": 10})):
            res = self.cli(tool, args)
            self.assertEqual(res["refused"], "cannot_act", tool)
            self.assertIn("tk_death_save", res["message"])

    def test_campaign_exists_refusal_does_not_invite_a_wipe(self):
        res = self.cli("tk_new_campaign", {"name": "Goblin Cave", "description": "A dark cave"})
        self.assertEqual(res["refused"], "campaign_exists")
        self.assertIn("explicitly asked", res["message"])
        self.assertEqual(len(self.cli("tk_state")["creatures"]), 1, "the party survived the refused call")

    def test_new_campaign_reads_the_scene_from_the_names_a_model_uses(self):
        self.assertTrue(self.cli("tk_new_campaign", {"replace": True, "description": "A dark cave"})["ok"])
        self.assertEqual(self.cli("tk_state")["scene"], "A dark cave")
