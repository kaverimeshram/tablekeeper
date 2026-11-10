"""Rules engine tests. Dice are scripted (Seq) or seeded so every case is exact."""
import importlib
import random
import sys
import time
import types
import unittest
from pathlib import Path

# Load rules and srd through a bare package so these tests do not depend on the
# plugin __init__ (which other code may be mid-edit).
_PKG = "tk_rules_under_test"
if _PKG not in sys.modules:
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tablekeeper")]
    sys.modules[_PKG] = pkg
rules = importlib.import_module(f"{_PKG}.rules")
srd = importlib.import_module(f"{_PKG}.srd")
RuleError = rules.RuleError


class Seq:
    """Scripted rng: returns the queued values and checks each fits the die asked for."""

    def __init__(self, *values):
        self.values = list(values)

    def randint(self, a, b):
        v = self.values.pop(0)
        assert a <= v <= b, f"scripted {v} outside d{b}"
        return v

    def done(self):
        return not self.values


def pc(key="fighter", **kw):
    c = srd.new_character(key, id=kw.pop("id", key), owner=kw.pop("owner", "u1"))
    c.update(kw)
    return c


def mon(key="goblin", **kw):
    m = srd.new_monster(key, id=kw.pop("id", key))
    m.update(kw)
    return m


def lowdown(c):
    c["hp"] = 0
    c["conditions"] = ["unconscious", "prone"]
    return c


class DiceTests(unittest.TestCase):
    def test_roll_basic_shape(self):
        r = rules.roll("1d20+3", rng=Seq(7))
        self.assertEqual((r["formula"], r["dice"], r["modifier"], r["total"]), ("1d20+3", [7], 3, 10))
        self.assertEqual(r["terms"][0]["term"], "1d20")

    def test_multiple_terms(self):
        r = rules.roll("1d8+1d6+3", rng=Seq(4, 5))
        self.assertEqual((r["dice"], r["modifier"], r["total"]), ([4, 5], 3, 12))
        self.assertEqual(len(r["terms"]), 3)

    def test_subtraction(self):
        self.assertEqual(rules.roll("1d8-2", rng=Seq(6))["total"], 4)
        self.assertEqual(rules.roll("2-1d4", rng=Seq(3))["total"], -1)

    def test_keep_highest_drops_lowest(self):
        r = rules.roll("4d6kh3", rng=Seq(1, 6, 5, 4))
        self.assertEqual(r["total"], 15)
        self.assertEqual(r["terms"][0]["dropped"], [1])

    def test_keep_lowest(self):
        self.assertEqual(rules.roll("2d20kl1", rng=Seq(15, 3))["total"], 3)

    def test_keep_count_must_fit(self):
        for bad in ("4d6kh0", "4d6kh5", "2d6kl3"):
            with self.assertRaises(RuleError, msg=bad):
                rules.roll(bad)

    def test_dice_count_limit(self):
        self.assertEqual(len(rules.roll("100d6", rng=random.Random(1))["dice"]), 100)
        with self.assertRaises(RuleError):
            rules.roll("101d6")
        with self.assertRaises(RuleError):
            rules.roll("60d6+60d6")

    def test_sides_limit(self):
        rules.roll("1d1000", rng=random.Random(1))
        with self.assertRaises(RuleError):
            rules.roll("1d1001")

    def test_length_limit_checked_before_parsing(self):
        rules.roll("1d6" + "+1" * 30, rng=random.Random(1))
        with self.assertRaises(RuleError):
            rules.roll("1d6" + "+1" * 31)
        start = time.perf_counter()
        for huge in (" " * 5_000_000 + "1d6", "9" * 5_000_000, "1d6+" * 1_000_000):
            with self.assertRaises(RuleError):
                rules.roll(huge)
        self.assertLess(time.perf_counter() - start, 1.0)

    def test_garbage_rejected(self):
        for bad in ("", "   ", "abc", "1d", "d", "2d6+", "1d20 1d4", "+-3", "5d6+-2", "0d6", "1d0",
                    "1.5d6", "1d6kh", "１d6", "1d6;DROP", "--5", None, 20):
            with self.assertRaises(RuleError, msg=repr(bad)):
                rules.roll(bad)

    def test_whitespace_and_case(self):
        r = rules.roll(" 2D6 + 1 ", rng=Seq(2, 3))
        self.assertEqual((r["formula"], r["total"]), ("2d6+1", 6))

    def test_bare_d_means_one_die(self):
        self.assertEqual(rules.roll("d20", rng=Seq(12))["total"], 12)

    def test_crit_doubles_dice_only(self):
        r = rules.roll("1d8+3", rng=Seq(4, 5), crit=True)
        self.assertEqual((r["formula"], r["dice"], r["modifier"], r["total"]), ("2d8+3", [4, 5], 3, 12))

    def test_average(self):
        self.assertEqual(rules.average("2d6+3"), 10.0)
        self.assertEqual(rules.average("1d8-1"), 3.5)

    def test_default_rng_is_usable(self):
        r = rules.roll("3d6")
        self.assertTrue(3 <= r["total"] <= 18)


class D20Tests(unittest.TestCase):
    def test_normal_single_die(self):
        r = rules.d20(rng=Seq(11))
        self.assertEqual((r["dice"], r["natural"], r["total"], r["mode"]), ([11], 11, 11, "normal"))

    def test_advantage_takes_higher(self):
        self.assertEqual(rules.d20(advantage=True, rng=Seq(4, 19))["natural"], 19)

    def test_disadvantage_takes_lower(self):
        self.assertEqual(rules.d20(disadvantage=True, rng=Seq(4, 19))["natural"], 4)

    def test_advantage_and_disadvantage_cancel(self):
        rng = Seq(4, 19)
        r = rules.d20(advantage=True, disadvantage=True, rng=rng)
        self.assertEqual((r["dice"], r["mode"]), ([4], "normal"))
        self.assertEqual(rng.values, [19])

    def test_lucky_rerolls_a_one(self):
        r = rules.d20(rng=Seq(1, 14), lucky=True)
        self.assertEqual((r["natural"], r["rerolled"]), (14, [1]))

    def test_lucky_leaves_other_results(self):
        self.assertEqual(rules.d20(rng=Seq(2), lucky=True)["natural"], 2)
        self.assertEqual(rules.d20(rng=Seq(1), lucky=False)["natural"], 1)


class AbilityTests(unittest.TestCase):
    def test_modifier_table(self):
        got = [rules.mod(s) for s in (1, 8, 9, 10, 11, 12, 15, 16, 20, 30)]
        self.assertEqual(got, [-5, -1, -1, 0, 0, 1, 2, 3, 5, 10])

    def test_skill_proficiency_and_expertise(self):
        self.assertEqual(rules.ability_check(pc("fighter"), "athletics", 10, rng=Seq(10))["bonus"], 5)
        self.assertEqual(rules.ability_check(pc("fighter"), "stealth", 10, rng=Seq(10))["bonus"], 2)
        self.assertEqual(rules.ability_check(pc("rogue"), "stealth", 10, rng=Seq(10))["bonus"], 7)
        self.assertEqual(rules.ability_check(pc("rogue"), "acrobatics", 10, rng=Seq(10))["bonus"], 5)

    def test_raw_ability_check_has_no_proficiency(self):
        self.assertEqual(rules.ability_check(pc("fighter"), "str", 10, rng=Seq(10))["bonus"], 3)
        self.assertEqual(rules.ability_check(pc("fighter"), "Strength", 10, rng=Seq(10))["bonus"], 3)

    def test_skill_names_normalise(self):
        r = rules.ability_check(pc("rogue"), "sleight of hand", 10, rng=Seq(10))
        self.assertEqual((r["ability"], r["bonus"]), ("dex", 5))
        self.assertEqual(rules.ability_check(pc("rogue"), "Sleight_of_Hand", 10, rng=Seq(10))["bonus"], 5)

    def test_check_dc_boundary_and_no_auto_success(self):
        self.assertTrue(rules.ability_check(pc("fighter"), "athletics", 15, rng=Seq(10))["success"])
        self.assertFalse(rules.ability_check(pc("fighter"), "athletics", 16, rng=Seq(10))["success"])
        self.assertFalse(rules.ability_check(pc("fighter"), "athletics", 30, rng=Seq(20))["success"])
        self.assertTrue(rules.ability_check(pc("fighter"), "athletics", 1, rng=Seq(1))["success"])

    def test_check_without_dc_reports_no_verdict(self):
        self.assertIsNone(rules.ability_check(pc("fighter"), "athletics", None, rng=Seq(10))["success"])

    def test_unknown_skill_raises(self):
        with self.assertRaises(RuleError):
            rules.ability_check(pc(), "juggling", 10)

    def test_poisoned_and_frightened_disadvantage_on_checks(self):
        c = pc("fighter", conditions=["poisoned"])
        r = rules.ability_check(c, "athletics", 10, rng=Seq(17, 3))
        self.assertEqual((r["mode"], r["natural"]), ("disadvantage", 3))
        c = pc("fighter", conditions=["frightened"])
        self.assertEqual(rules.ability_check(c, "athletics", 10, rng=Seq(17, 3))["natural"], 3)

    def test_advantage_and_poison_cancel_on_check(self):
        c = pc("fighter", conditions=["poisoned"])
        r = rules.ability_check(c, "athletics", 10, advantage=True, rng=Seq(17))
        self.assertEqual(r["mode"], "normal")

    def test_saves_use_proficiency_only_where_listed(self):
        f = pc("fighter")
        self.assertEqual(rules.saving_throw(f, "con", 10, rng=Seq(10))["bonus"], 4)
        self.assertEqual(rules.saving_throw(f, "dex", 10, rng=Seq(10))["bonus"], 2)
        self.assertEqual(rules.saving_throw(f, "Wisdom", 10, rng=Seq(10))["bonus"], 1)

    def test_save_natural_twenty_is_not_automatic_success(self):
        self.assertFalse(rules.saving_throw(pc("wizard"), "str", 30, rng=Seq(20))["success"])

    def test_paralyzed_auto_fails_str_and_dex_only(self):
        c = pc("fighter", conditions=["paralyzed"])
        r = rules.saving_throw(c, "dex", 1, rng=Seq())
        self.assertTrue(r["auto_fail"] and not r["success"])
        self.assertTrue(rules.saving_throw(c, "wis", 5, rng=Seq(15))["success"])
        for cond in ("stunned", "unconscious"):
            c2 = pc("fighter", conditions=[cond])
            self.assertTrue(rules.saving_throw(c2, "str", 1, rng=Seq())["auto_fail"])

    def test_restrained_disadvantage_on_dex_saves(self):
        c = pc("fighter", conditions=["restrained"])
        self.assertEqual(rules.saving_throw(c, "dex", 10, rng=Seq(18, 2))["natural"], 2)
        self.assertEqual(rules.saving_throw(c, "con", 10, rng=Seq(18))["natural"], 18)

    def test_cover_adds_to_dex_saves_only(self):
        c = pc("fighter")
        self.assertEqual(rules.saving_throw(c, "dex", 12, cover=2, rng=Seq(8))["total"], 12)
        self.assertEqual(rules.saving_throw(c, "con", 12, cover=2, rng=Seq(8))["total"], 12)
        with self.assertRaises(RuleError):
            rules.saving_throw(c, "dex", 12, cover=3)

    def test_halfling_lucky_applies_to_saves_and_checks(self):
        r = pc("rogue")
        self.assertEqual(rules.saving_throw(r, "dex", 10, rng=Seq(1, 12))["natural"], 12)
        self.assertEqual(rules.ability_check(r, "stealth", 10, rng=Seq(1, 12))["natural"], 12)

    def test_passive_perception(self):
        self.assertEqual(rules.passive_perception(pc("fighter")), 13)
        self.assertEqual(rules.passive_perception(pc("rogue")), 15)
        self.assertEqual(rules.passive_perception(pc("rogue", conditions=["poisoned"])), 10)
        self.assertEqual(rules.passive_score(pc("fighter"), "perception", advantage=True), 18)
        self.assertEqual(rules.passive_score(pc("fighter"), "perception", disadvantage=True), 8)

    def test_bless_adds_d4_to_saves(self):
        c = pc("fighter", effects={"bless": {"by": "x"}})
        r = rules.saving_throw(c, "con", 10, rng=Seq(5, 3))
        self.assertEqual(r["total"], 5 + 4 + 3)


class ConditionTests(unittest.TestCase):
    def test_add_and_remove(self):
        c = pc()
        self.assertTrue(rules.add_condition(c, "Poisoned")["added"])
        self.assertFalse(rules.add_condition(c, "poisoned")["added"])
        self.assertEqual(c["conditions"], ["poisoned"])
        self.assertTrue(rules.remove_condition(c, "poisoned")["removed"])
        self.assertFalse(rules.remove_condition(c, "poisoned")["removed"])

    def test_unknown_condition_rejected(self):
        with self.assertRaises(RuleError):
            rules.add_condition(pc(), "sparkly")

    def test_unconscious_adds_prone(self):
        c = pc()
        rules.add_condition(c, "unconscious")
        self.assertEqual(set(c["conditions"]), {"unconscious", "prone"})

    def test_condition_immunity(self):
        z = mon("zombie")
        self.assertFalse(rules.add_condition(z, "poisoned")["added"])
        self.assertEqual(z["conditions"], [])

    def test_can_act(self):
        for cond in ("incapacitated", "paralyzed", "stunned", "unconscious"):
            self.assertFalse(rules.can_act(pc(conditions=[cond])), cond)
        self.assertTrue(rules.can_act(pc(conditions=["poisoned", "prone"])))
        self.assertFalse(rules.can_act(pc(hp=0)))

    def test_speed_effects(self):
        self.assertEqual(rules.effective_speed(pc()), 30)
        self.assertEqual(rules.effective_speed(pc(conditions=["grappled"])), 0)
        self.assertEqual(rules.effective_speed(pc(conditions=["restrained"])), 0)
        slowed = pc(effects={"ray_of_frost": {"speed_penalty": 10}})
        self.assertEqual(rules.effective_speed(slowed), 20)


class AttackModifierTests(unittest.TestCase):
    def mods(self, a_conds=(), t_conds=(), melee=True, **kw):
        a, t = pc("fighter", conditions=list(a_conds)), mon("goblin", conditions=list(t_conds))
        return rules.attack_modifiers(a, t, melee, **kw)

    def test_clean_attack(self):
        m = self.mods()
        self.assertEqual((m["advantage"], m["disadvantage"], m["auto_crit"]), (False, False, False))

    def test_attacker_conditions_disadvantage(self):
        for cond in ("blinded", "frightened", "poisoned", "prone", "restrained"):
            self.assertTrue(self.mods(a_conds=[cond])["disadvantage"], cond)

    def test_invisible_attacker_advantage_and_target_disadvantage(self):
        self.assertTrue(self.mods(a_conds=["invisible"])["advantage"])
        self.assertTrue(self.mods(t_conds=["invisible"])["disadvantage"])

    def test_target_conditions_give_advantage(self):
        for cond in ("blinded", "paralyzed", "restrained", "stunned", "unconscious"):
            self.assertTrue(self.mods(t_conds=[cond])["advantage"], cond)

    def test_prone_target_melee_advantage_ranged_disadvantage(self):
        self.assertTrue(self.mods(t_conds=["prone"], melee=True)["advantage"])
        far = rules.attack_modifiers(pc(pos=[0, 0]), mon(pos=[6, 0], conditions=["prone"]), False)
        self.assertTrue(far["disadvantage"] and not far["advantage"])

    def test_paralyzed_and_unconscious_auto_crit_within_five_feet(self):
        for cond in ("paralyzed", "unconscious"):
            self.assertTrue(self.mods(t_conds=[cond])["auto_crit"], cond)
        far = rules.attack_modifiers(pc(pos=[0, 0]), mon(pos=[6, 0], conditions=["paralyzed"]), False)
        self.assertFalse(far["auto_crit"])
        near = rules.attack_modifiers(pc(pos=[0, 0]), mon(pos=[1, 1], conditions=["paralyzed"]), False)
        self.assertTrue(near["auto_crit"])

    def test_ranged_attack_in_melee_flag(self):
        self.assertTrue(self.mods(melee=False, in_melee=True)["disadvantage"])
        self.assertFalse(self.mods(melee=False, in_melee=False)["disadvantage"])

    def test_guiding_bolt_mark_gives_advantage(self):
        a, t = pc(), mon(effects={"guiding_bolt": {"by": "x"}})
        self.assertTrue(rules.attack_modifiers(a, t, True)["advantage"])


class AttackTests(unittest.TestCase):
    def setUp(self):
        self.fighter = pc("fighter")
        self.gob = mon("goblin")
        self.sword = self.fighter["attacks"][0]

    def atk(self, rng, target=None, **kw):
        return rules.resolve_attack(self.fighter, target or self.gob, self.sword, rng=rng, **kw)

    def test_hit_equals_ac_hits(self):
        r = self.atk(Seq(10, 4))
        self.assertEqual((r["to_hit"], r["ac"], r["hit"]), (15, 15, True))
        self.assertEqual(r["damage"]["raw"], 9)

    def test_one_below_ac_misses(self):
        r = self.atk(Seq(9))
        self.assertEqual((r["to_hit"], r["hit"]), (14, False))
        self.assertEqual(r["damage"]["raw"], 0)
        self.assertEqual(r["damage"]["notes"], ["miss"])

    def test_natural_one_always_misses(self):
        self.fighter["attacks"][0]["to_hit"] = 100
        r = self.atk(Seq(1))
        self.assertFalse(r["hit"])

    def test_natural_twenty_always_hits(self):
        self.sword["to_hit"] = -100
        r = self.atk(Seq(20, 3, 4))
        self.assertTrue(r["hit"] and r["critical"])

    def test_critical_doubles_dice_not_modifier(self):
        r = self.atk(Seq(20, 3, 4))
        self.assertEqual(r["damage"]["rolls"][0]["formula"], "2d8+5")
        self.assertEqual(r["damage"]["raw"], 3 + 4 + 5)

    def test_normal_hit_does_not_double(self):
        r = self.atk(Seq(15, 3))
        self.assertEqual((r["critical"], r["damage"]["raw"]), (False, 8))

    def test_advantage_disadvantage_cancel_in_attack(self):
        rng = Seq(12, 4)
        r = self.atk(rng, advantage=True, disadvantage=True)
        self.assertEqual((r["attack_roll"]["mode"], r["attack_roll"]["dice"]), ("normal", [12]))
        self.assertEqual(r["damage"]["rolls"][0]["dice"], [4])

    def test_condition_advantage_and_caller_disadvantage_cancel(self):
        self.gob["conditions"] = ["stunned"]
        r = self.atk(Seq(12, 2), disadvantage=True)
        self.assertEqual(r["attack_roll"]["mode"], "normal")

    def test_cover_changes_target_ac(self):
        self.assertTrue(self.atk(Seq(10, 1), cover=0)["hit"])
        r = self.atk(Seq(10), cover=2)
        self.assertEqual((r["ac"], r["hit"]), (17, False))
        r = self.atk(Seq(12, 1), cover=2)
        self.assertEqual((r["to_hit"], r["hit"]), (17, True))
        r = self.atk(Seq(12), cover=5)
        self.assertEqual((r["ac"], r["hit"]), (20, False))

    def test_invalid_cover_rejected(self):
        for bad in (1, 3, 4, 10, -2):
            with self.assertRaises(RuleError):
                self.atk(Seq(10), cover=bad)

    def test_ranged_in_melee_has_disadvantage(self):
        bow = self.fighter["attacks"][1]
        r = rules.resolve_attack(self.fighter, self.gob, bow, melee=False, in_melee=True, rng=Seq(18, 3))
        self.assertEqual((r["attack_roll"]["mode"], r["attack_roll"]["natural"]), ("disadvantage", 3))

    def test_paralyzed_target_melee_hit_is_critical(self):
        self.gob["conditions"] = ["paralyzed"]
        r = self.atk(Seq(12, 2, 2, 2))
        self.assertTrue(r["hit"] and r["critical"] and r["auto_crit"])
        self.assertEqual(r["damage"]["rolls"][0]["formula"], "2d8+5")

    def test_paralyzed_target_ranged_far_not_critical(self):
        self.fighter["pos"], self.gob["pos"] = [0, 0], [8, 0]
        self.gob["conditions"] = ["paralyzed"]
        r = rules.resolve_attack(self.fighter, self.gob, self.fighter["attacks"][1], melee=False, rng=Seq(15, 12, 3))
        self.assertTrue(r["hit"])
        self.assertFalse(r["critical"])

    def test_champion_crits_on_nineteen_but_must_hit(self):
        r = self.atk(Seq(19, 2, 2))
        self.assertTrue(r["hit"] and r["critical"])
        self.gob["ac"] = 40
        r = self.atk(Seq(19))
        self.assertFalse(r["hit"] or r["critical"])

    def test_incapacitated_attacker_refused(self):
        self.fighter["conditions"] = ["stunned"]
        with self.assertRaises(RuleError):
            self.atk(Seq(10))

    def test_dead_target_refused(self):
        self.gob["conditions"] = ["dead"]
        with self.assertRaises(RuleError):
            self.atk(Seq(10))

    def test_damage_floor_is_zero(self):
        wiz = pc("wizard")
        r = rules.resolve_attack(wiz, self.gob, wiz["attacks"][0], rng=Seq(18, 1))
        self.assertEqual(r["damage"]["raw"], 0)

    def test_resistance_and_vulnerability_reflected_in_applied(self):
        skel = mon("skeleton")
        r = self.atk(Seq(15, 5), target=skel)
        self.assertEqual(r["damage"]["applied"], r["damage"]["raw"])  # slashing, no change
        mace = pc("cleric")
        r = rules.resolve_attack(mace, skel, mace["attacks"][0], rng=Seq(15, 4))
        self.assertEqual((r["damage"]["raw"], r["damage"]["applied"]), (5, 10))

    def test_default_never_changes_hit_points(self):
        self.atk(Seq(15, 8))
        self.assertEqual(self.gob["hp"], 7)

    def test_apply_true_applies_damage(self):
        r = self.atk(Seq(15, 8), apply=True)
        self.assertEqual(self.gob["hp"], 0)
        self.assertEqual(r["outcome"]["state"], "dead")

    def test_sneak_attack_needs_advantage_or_ally(self):
        rogue = pc("rogue")
        sw = rogue["attacks"][0]
        r = rules.resolve_attack(rogue, self.gob, sw, rng=Seq(15, 3))
        self.assertEqual(len(r["damage"]["rolls"]), 1)
        r = rules.resolve_attack(rogue, self.gob, sw, advantage=True, rng=Seq(12, 15, 3, 4, 5))
        self.assertEqual([x["formula"] for x in r["damage"]["rolls"]], ["1d6+3", "2d6"])
        self.assertEqual(r["damage"]["raw"], 6 + 9)
        r = rules.resolve_attack(rogue, self.gob, sw, ally_adjacent=True, rng=Seq(15, 3, 4, 5))
        self.assertEqual(r["damage"]["raw"], 6 + 9)

    def test_sneak_attack_blocked_by_disadvantage_and_crit_doubles_it(self):
        rogue = pc("rogue")
        sw = rogue["attacks"][0]
        r = rules.resolve_attack(rogue, self.gob, sw, ally_adjacent=True, disadvantage=True, rng=Seq(15, 12, 3))
        self.assertEqual(len(r["damage"]["rolls"]), 1)
        r = rules.resolve_attack(rogue, self.gob, sw, ally_adjacent=True, rng=Seq(20, 1, 1, 1, 1, 1, 1))
        self.assertEqual([x["formula"] for x in r["damage"]["rolls"]], ["2d6+3", "4d6"])

    def test_martial_advantage_needs_adjacent_ally(self):
        hob = mon("hobgoblin")
        target = pc("wizard")
        sw = hob["attacks"][0]
        r = rules.resolve_attack(hob, target, sw, rng=Seq(18, 4))
        self.assertEqual(len(r["damage"]["rolls"]), 1)
        r = rules.resolve_attack(hob, target, sw, ally_adjacent=True, rng=Seq(18, 4, 3, 3))
        self.assertEqual(r["damage"]["raw"], 5 + 6)

    def test_wolf_bite_knocks_prone_on_failed_save(self):
        wolf = mon("wolf")
        wiz = pc("wizard")
        r = rules.resolve_attack(wolf, wiz, wolf["attacks"][0], rng=Seq(18, 2, 2, 3), apply=True)
        self.assertTrue(r["rider"]["triggered"] and r["rider"]["applied"])
        self.assertIn("prone", wiz["conditions"])
        wiz2 = pc("wizard")
        r = rules.resolve_attack(wolf, wiz2, wolf["attacks"][0], rng=Seq(18, 2, 2, 20), apply=True)
        self.assertFalse(r["rider"]["triggered"])
        self.assertNotIn("prone", wiz2["conditions"])

    def test_guiding_bolt_mark_consumed_by_first_attack(self):
        self.gob["effects"] = {"guiding_bolt": {"by": "c"}}
        r = self.atk(Seq(12, 5, 3))
        self.assertEqual(r["attack_roll"]["mode"], "advantage")
        self.assertNotIn("guiding_bolt", self.gob["effects"])
        r = self.atk(Seq(12, 1))
        self.assertEqual(r["attack_roll"]["mode"], "normal")

    def test_bless_adds_d4_to_attack(self):
        self.fighter["effects"] = {"bless": {"by": "c"}}
        r = self.atk(Seq(5, 4, 2))
        self.assertEqual(r["to_hit"], 5 + 5 + 4)

    def test_halfling_lucky_on_attack(self):
        rogue = pc("rogue")
        r = rules.resolve_attack(rogue, self.gob, rogue["attacks"][0], rng=Seq(1, 20, 1, 1, 1))
        self.assertTrue(r["hit"] and r["critical"])


class DamageTests(unittest.TestCase):
    def test_resistance_rounds_down(self):
        self.assertEqual(rules.mitigate(pc("cleric"), 5, "poison")[0], 2)
        self.assertEqual(rules.mitigate(pc("cleric"), 1, "poison")[0], 0)

    def test_vulnerability_doubles(self):
        self.assertEqual(rules.mitigate(mon("skeleton"), 5, "bludgeoning")[0], 10)

    def test_immunity_zero(self):
        self.assertEqual(rules.mitigate(mon("skeleton"), 50, "poison")[0], 0)

    def test_resistance_then_vulnerability_order(self):
        c = pc(resist=["fire"], vuln=["fire"])
        self.assertEqual(rules.mitigate(c, 5, "fire")[0], 4)

    def test_immunity_beats_vulnerability(self):
        self.assertEqual(rules.mitigate(pc(immune=["fire"], vuln=["fire"]), 9, "fire")[0], 0)

    def test_bad_input_rejected(self):
        with self.assertRaises(RuleError):
            rules.apply_damage(pc(), 3, "sparkles")
        with self.assertRaises(RuleError):
            rules.apply_damage(pc(), -3, "fire")
        with self.assertRaises(RuleError):
            rules.apply_damage(pc(), 2.5, "fire")

    def test_plain_damage(self):
        c = pc("fighter")
        r = rules.apply_damage(c, 10, "slashing")
        self.assertEqual((r["applied"], r["hp"], r["state"]), (10, 18, "ok"))

    def test_resistance_applied_inside_apply_damage(self):
        c = pc("cleric")
        r = rules.apply_damage(c, 9, "poison")
        self.assertEqual((r["applied"], c["hp"]), (4, 26))

    def test_temp_hp_absorbs_first(self):
        c = pc("fighter", temp_hp=5)
        r = rules.apply_damage(c, 3, "fire")
        self.assertEqual((c["temp_hp"], c["hp"], r["absorbed"]), (2, 28, 3))
        r = rules.apply_damage(c, 6, "fire")
        self.assertEqual((c["temp_hp"], c["hp"], r["hp_lost"]), (0, 24, 4))

    def test_temp_hp_does_not_trigger_down(self):
        c = pc("fighter", hp=3, temp_hp=10)
        r = rules.apply_damage(c, 9, "fire")
        self.assertEqual((c["hp"], c["temp_hp"], r["state"]), (3, 1, "ok"))

    def test_pc_at_zero_is_down_not_dead(self):
        c = pc("fighter", hp=5)
        r = rules.apply_damage(c, 5, "fire")
        self.assertEqual((r["state"], c["hp"]), ("down", 0))
        self.assertEqual(set(c["conditions"]), {"unconscious", "prone"})
        self.assertEqual(c["death_saves"], {"s": 0, "f": 0})

    def test_monster_at_zero_is_dead(self):
        g = mon("goblin")
        self.assertEqual(rules.apply_damage(g, 7, "slashing")["state"], "dead")
        self.assertIn("dead", g["conditions"])

    def test_massive_damage_boundary(self):
        c = pc("fighter", hp=10)  # max 28
        r = rules.apply_damage(c, 10 + 27, "fire")
        self.assertEqual(r["state"], "down")
        c = pc("fighter", hp=10)
        r = rules.apply_damage(c, 10 + 28, "fire")
        self.assertEqual(r["state"], "dead")
        self.assertIn("massive damage", " ".join(r["notes"]))

    def test_massive_damage_at_zero_hp(self):
        c = lowdown(pc("fighter"))
        self.assertEqual(rules.apply_damage(c, 27, "fire")["state"], "down")
        c = lowdown(pc("fighter"))
        self.assertEqual(rules.apply_damage(c, 28, "fire")["state"], "dead")

    def test_damage_at_zero_is_one_failure_and_crit_is_two(self):
        c = lowdown(pc("fighter"))
        rules.apply_damage(c, 3, "fire")
        self.assertEqual(c["death_saves"]["f"], 1)
        r = rules.apply_damage(c, 3, "fire", critical=True)
        self.assertEqual(c["death_saves"]["f"], 3)
        self.assertEqual(r["state"], "dead")

    def test_zero_damage_at_zero_hp_is_free(self):
        c = lowdown(pc("fighter"))
        rules.apply_damage(c, 0, "fire")
        self.assertEqual(c["death_saves"]["f"], 0)

    def test_stable_creature_damaged_is_unstable_again(self):
        c = lowdown(pc("fighter", conditions=["unconscious", "prone", "stable"]))
        r = rules.apply_damage(c, 2, "fire")
        self.assertEqual(r["state"], "down")
        self.assertNotIn("stable", c["conditions"])
        self.assertEqual(c["death_saves"]["f"], 1)

    def test_dead_stays_dead(self):
        c = pc("fighter", conditions=["dead"], hp=0)
        r = rules.apply_damage(c, 5, "fire")
        self.assertEqual((r["applied"], r["state"]), (0, "dead"))

    def test_undead_fortitude(self):
        z = mon("zombie", hp=3)
        r = rules.apply_damage(z, 4, "slashing", rng=Seq(8))  # DC 9, +3 con = 11
        self.assertEqual((z["hp"], r["state"]), (1, "ok"))
        z = mon("zombie", hp=3)
        self.assertEqual(rules.apply_damage(z, 4, "slashing", rng=Seq(5))["state"], "dead")
        z = mon("zombie", hp=3)
        self.assertEqual(rules.apply_damage(z, 4, "radiant", rng=Seq(20))["state"], "dead")
        z = mon("zombie", hp=3)
        self.assertEqual(rules.apply_damage(z, 4, "slashing", critical=True, rng=Seq(20))["state"], "dead")

    def test_damage_wakes_a_sleeper(self):
        c = pc("fighter", conditions=["unconscious", "prone"], effects={"asleep": {"by": "w"}})
        rules.apply_damage(c, 1, "fire")
        self.assertNotIn("unconscious", c["conditions"])
        self.assertNotIn("asleep", c["effects"])

    def test_concentration_dc_reported(self):
        c = pc("cleric", concentration={"spell": "bless", "targets": []}, hp=100, max_hp=100)
        self.assertEqual(rules.apply_damage(c, 4, "fire")["concentration_dc"], 10)
        self.assertEqual(rules.apply_damage(c, 30, "fire")["concentration_dc"], 15)
        self.assertIsNone(rules.apply_damage(pc("fighter"), 4, "fire")["concentration_dc"])

    def test_going_down_ends_concentration(self):
        c = pc("cleric", hp=2, concentration={"spell": "bless", "targets": []})
        rules.apply_damage(c, 5, "fire")
        self.assertIsNone(c["concentration"])


class HealTests(unittest.TestCase):
    def test_heal_caps_at_max(self):
        c = pc("fighter", hp=20)
        r = rules.heal(c, 100)
        self.assertEqual((r["healed"], c["hp"]), (8, 28))

    def test_heal_at_zero_revives_and_resets_saves(self):
        c = lowdown(pc("fighter"))
        c["death_saves"] = {"s": 2, "f": 2}
        r = rules.heal(c, 1)
        self.assertEqual((c["hp"], r["state"]), (1, "ok"))
        self.assertNotIn("unconscious", c["conditions"])
        self.assertEqual(c["death_saves"], {"s": 0, "f": 0})

    def test_zero_heal_does_not_revive(self):
        c = lowdown(pc("fighter"))
        self.assertEqual(rules.heal(c, 0)["state"], "down")

    def test_dead_cannot_be_healed(self):
        c = pc("fighter", hp=0, conditions=["dead"])
        r = rules.heal(c, 10)
        self.assertEqual((r["healed"], c["hp"]), (0, 0))

    def test_negative_heal_rejected(self):
        with self.assertRaises(RuleError):
            rules.heal(pc(), -1)

    def test_heal_stable_creature(self):
        c = lowdown(pc("fighter", conditions=["unconscious", "prone", "stable"]))
        rules.heal(c, 3)
        self.assertNotIn("stable", c["conditions"])


class DeathSaveTests(unittest.TestCase):
    def test_ten_or_more_is_success(self):
        c = lowdown(pc())
        r = rules.death_save(c, rng=Seq(10))
        self.assertEqual((r["outcome"], r["successes"], r["failures"]), ("success", 1, 0))

    def test_nine_is_failure(self):
        c = lowdown(pc())
        r = rules.death_save(c, rng=Seq(9))
        self.assertEqual((r["outcome"], r["failures"]), ("failure", 1))

    def test_natural_one_is_two_failures(self):
        c = lowdown(pc())
        r = rules.death_save(c, rng=Seq(1))
        self.assertEqual((r["outcome"], r["failures"]), ("critical_failure", 2))

    def test_natural_twenty_regains_one_hp_and_consciousness(self):
        c = lowdown(pc())
        c["death_saves"] = {"s": 1, "f": 2}
        r = rules.death_save(c, rng=Seq(20))
        self.assertEqual((c["hp"], r["state"]), (1, "ok"))
        self.assertNotIn("unconscious", c["conditions"])
        self.assertEqual(c["death_saves"], {"s": 0, "f": 0})

    def test_three_successes_stable(self):
        c = lowdown(pc())
        for _ in range(3):
            r = rules.death_save(c, rng=Seq(12))
        self.assertEqual(r["state"], "stable")
        self.assertEqual(c["hp"], 0)
        self.assertEqual(c["death_saves"], {"s": 0, "f": 0})

    def test_three_failures_dead(self):
        c = lowdown(pc())
        rules.death_save(c, rng=Seq(5))
        rules.death_save(c, rng=Seq(5))
        r = rules.death_save(c, rng=Seq(5))
        self.assertEqual(r["state"], "dead")

    def test_one_then_failure_is_dead(self):
        c = lowdown(pc())
        rules.death_save(c, rng=Seq(1))
        self.assertEqual(rules.death_save(c, rng=Seq(2))["state"], "dead")

    def test_refused_unless_down(self):
        for c in (pc(), pc(hp=0, conditions=["dead"]), pc(hp=0, conditions=["stable"]), mon("goblin", hp=0)):
            with self.assertRaises(RuleError):
                rules.death_save(c, rng=Seq(10))

    def test_mixed_sequence_boundaries(self):
        c = lowdown(pc())
        for roll_ in (10, 10, 9, 9):
            r = rules.death_save(c, rng=Seq(roll_))
        self.assertEqual((r["successes"], r["failures"], r["state"]), (2, 2, "down"))
        self.assertEqual(rules.death_save(c, rng=Seq(15))["state"], "stable")


class ConcentrationTests(unittest.TestCase):
    def test_dc_is_ten_or_half_damage(self):
        c = pc("cleric", concentration={"spell": "bless", "targets": ["a"], "slot": 1})
        self.assertEqual(rules.concentration_check(c, 6, rng=Seq(10))["dc"], 10)
        self.assertEqual(rules.concentration_check(c, 21, rng=Seq(10))["dc"], 10)
        self.assertEqual(rules.concentration_check(c, 22, rng=Seq(10))["dc"], 11)
        self.assertEqual(rules.concentration_check(c, 40, rng=Seq(10))["dc"], 20)

    def test_success_keeps_concentration(self):
        c = pc("cleric", concentration={"spell": "bless", "targets": [], "slot": 1})
        r = rules.concentration_check(c, 4, rng=Seq(8))  # con +3
        self.assertFalse(r["broken"])
        self.assertIsNotNone(c["concentration"])

    def test_failure_breaks_and_strips_effects(self):
        cl = pc("cleric", concentration={"spell": "bless", "targets": ["fighter"], "slot": 1})
        fighter = pc("fighter", effects={"bless": {"by": "cleric"}})
        other = pc("rogue", effects={"bless": {"by": "someone-else"}})
        r = rules.concentration_check(cl, 4, rng=Seq(2), creatures=[fighter, other])
        self.assertTrue(r["broken"])
        self.assertIsNone(cl["concentration"])
        self.assertNotIn("bless", fighter["effects"])
        self.assertIn("bless", other["effects"])

    def test_not_concentrating(self):
        r = rules.concentration_check(pc(), 20, rng=Seq())
        self.assertFalse(r["concentrating"])

    def test_breaking_hold_person_frees_target(self):
        wiz = pc("wizard", concentration={"spell": "hold person", "targets": ["goblin"], "slot": 2})
        g = mon("goblin", conditions=["paralyzed"], effects={"hold_person": {"by": "wizard", "dc": 13, "ability": "wis"}})
        rules.break_concentration(wiz, [g])
        self.assertNotIn("paralyzed", g["conditions"])


class InitiativeTests(unittest.TestCase):
    def test_orders_by_total_with_dex_mod(self):
        a, b, c = pc("fighter", id="a"), pc("rogue", id="b"), mon("ogre", id="c")  # dex +2, +3, -1
        order = rules.roll_initiative([a, b, c], rng=Seq(10, 5, 20))
        self.assertEqual(order, ["c", "a", "b"])
        self.assertEqual((a["initiative"], b["initiative"], c["initiative"]), (12, 8, 19))

    def test_tie_goes_to_higher_dex_score(self):
        a = pc("fighter", id="a")  # dex 14
        b = pc("rogue", id="b")  # dex 17 -> mod 3
        c = pc("wizard", id="c")  # dex 15 -> mod 2
        a["abilities"]["dex"] = 14
        order = rules.roll_initiative([a, c, b], rng=Seq(11, 11, 10))  # totals 13, 13, 13
        self.assertEqual(order, ["b", "c", "a"])

    def test_identical_ties_roll_off(self):
        a, b = mon("goblin", id="a"), mon("goblin", id="b")
        order = rules.roll_initiative([a, b], rng=Seq(10, 10, 4, 17))
        self.assertEqual(order, ["b", "a"])
        order = rules.roll_initiative([a, b], rng=Seq(10, 10, 9, 9, 3, 12))
        self.assertEqual(order, ["b", "a"])

    def test_returns_every_id_once(self):
        crowd = [mon("goblin", id=f"g{i}") for i in range(8)] + [pc("fighter", id="f")]
        order = rules.roll_initiative(crowd, rng=random.Random(7))
        self.assertEqual(sorted(order), sorted(c["id"] for c in crowd))


class RestTests(unittest.TestCase):
    def test_short_rest_spends_hit_dice(self):
        f = pc("fighter", hp=10)
        r = rules.short_rest(f, 2, rng=Seq(4, 6))  # d10 + con 2
        self.assertEqual((r["spent"], r["healed"], f["hp"], f["hit_dice"][0]), (2, 14, 24, 1))

    def test_short_rest_caps_at_max_hp(self):
        f = pc("fighter", hp=27)
        self.assertEqual(rules.short_rest(f, 1, rng=Seq(10))["healed"], 1)

    def test_short_rest_limited_by_available_dice(self):
        f = pc("fighter", hp=1)
        f["hit_dice"][0] = 1
        r = rules.short_rest(f, 3, rng=Seq(5))
        self.assertEqual((r["spent"], f["hit_dice"][0]), (1, 0))

    def test_short_rest_con_penalty_never_below_zero(self):
        k = mon("kobold", hp=1)  # con 9 -> -1
        k["hit_dice"] = [2, 2, "d6"]
        r = rules.short_rest(k, 1, rng=Seq(1))
        self.assertEqual(r["healed"], 0)

    def test_short_rest_refused_when_down_or_bad_count(self):
        with self.assertRaises(RuleError):
            rules.short_rest(lowdown(pc()), 1)
        with self.assertRaises(RuleError):
            rules.short_rest(pc(), -1)

    def test_long_rest_restores_everything(self):
        w = pc("wizard", hp=3, temp_hp=4)
        w["slots"]["1"][0] = 0
        w["slots"]["2"][0] = 1
        w["hit_dice"][0] = 0
        w["death_saves"] = {"s": 1, "f": 1}
        w["concentration"] = {"spell": "hold person", "targets": []}
        r = rules.long_rest(w)
        self.assertEqual((w["hp"], w["temp_hp"]), (20, 0))
        self.assertEqual((w["slots"]["1"], w["slots"]["2"]), ([4, 4], [2, 2]))
        self.assertEqual(w["hit_dice"][0], 1)  # half of 3, rounded down
        self.assertEqual((r["hit_dice_regained"], w["death_saves"], w["concentration"]), (1, {"s": 0, "f": 0}, None))

    def test_long_rest_regains_half_hit_dice_not_all(self):
        f = pc("fighter")
        f["hit_dice"][0] = 0
        rules.long_rest(f)
        self.assertEqual(f["hit_dice"][0], 1)
        g = srd.new_monster("ogre")
        g["hit_dice"][0] = 0
        rules.long_rest(g)
        self.assertEqual(g["hit_dice"][0], 3)

    def test_long_rest_regains_at_least_one(self):
        c = pc("fighter")
        c["hit_dice"] = [0, 1, "d10"]
        rules.long_rest(c)
        self.assertEqual(c["hit_dice"][0], 1)

    def test_long_rest_never_exceeds_max_dice(self):
        c = pc("fighter")
        rules.long_rest(c)
        self.assertEqual(c["hit_dice"][0], 3)

    def test_long_rest_refused_for_dead_and_wakes_stable(self):
        with self.assertRaises(RuleError):
            rules.long_rest(pc(conditions=["dead"], hp=0))
        c = lowdown(pc(conditions=["unconscious", "prone", "stable"]))
        rules.long_rest(c)
        self.assertNotIn("unconscious", c["conditions"])
        self.assertNotIn("stable", c["conditions"])


class SpellTests(unittest.TestCase):
    def setUp(self):
        self.wiz = pc("wizard", level=3)
        self.wiz["spells"].append("thunderwave")
        self.cleric = pc("cleric", level=3)
        self.gob = mon("goblin")
        self.ogre = mon("ogre", id="ogre")

    def test_wizard_and_cleric_spell_numbers(self):
        self.assertEqual((rules.spell_dc(self.wiz), rules.spell_attack_bonus(self.wiz)), (13, 5))
        self.assertEqual((rules.spell_dc(self.cleric), rules.spell_attack_bonus(self.cleric)), (13, 5))
        with self.assertRaises(RuleError):
            rules.spell_dc(self.gob)

    def test_cantrip_uses_no_slot_and_hits(self):
        before = {k: list(v) for k, v in self.wiz["slots"].items()}
        r = rules.cast(self.wiz, "Fire Bolt", [self.ogre], rng=Seq(12, 6))
        self.assertIsNone(r["slot_used"])
        self.assertEqual(self.wiz["slots"], before)
        e = r["results"][0]
        self.assertTrue(e["hit"])
        self.assertEqual((e["damage"]["raw"], self.ogre["hp"]), (6, 53))

    def test_cantrip_miss_does_no_damage(self):
        r = rules.cast(self.wiz, "fire bolt", [self.ogre], rng=Seq(4))
        self.assertEqual((r["results"][0]["hit"], self.ogre["hp"]), (False, 59))

    def test_cantrip_critical_doubles_dice(self):
        r = rules.cast(self.wiz, "fire bolt", [self.ogre], rng=Seq(20, 3, 4))
        self.assertTrue(r["results"][0]["critical"])
        self.assertEqual(r["results"][0]["damage"]["raw"], 7)

    def test_cantrip_scales_with_level(self):
        self.wiz["level"] = 5
        r = rules.cast(self.wiz, "fire bolt", [self.ogre], rng=Seq(15, 1, 2))
        self.assertEqual(r["results"][0]["damage"]["rolls"][0]["formula"], "2d10")
        self.wiz["level"] = 17
        r = rules.cast(self.wiz, "fire bolt", [self.ogre], rng=Seq(15, 1, 2, 3, 4))
        self.assertEqual(r["results"][0]["damage"]["rolls"][0]["formula"], "4d10")

    def test_slot_spent_and_missing_slot_refused_without_side_effects(self):
        rules.cast(self.wiz, "burning hands", [self.gob], rng=Seq(5, 1, 1, 1))
        self.assertEqual(self.wiz["slots"]["1"][0], 3)
        self.wiz["slots"]["1"][0] = 0
        before = (dict(self.wiz["slots"]), self.gob["hp"], list(self.gob["conditions"]))
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "burning hands", [self.gob], rng=Seq())
        self.assertEqual(before, (dict(self.wiz["slots"]), self.gob["hp"], list(self.gob["conditions"])))
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "burning hands", [self.gob], slot_level=3, rng=Seq())
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "scorching ray", [self.gob], slot_level=1, rng=Seq())

    def test_unknown_and_unprepared_spells_refused(self):
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "wish", [self.gob])
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "cure wounds", [self.gob])
        with self.assertRaises(RuleError):
            rules.cast(self.gob, "fire bolt", [self.wiz])

    def test_incapacitated_caster_refused(self):
        self.wiz["conditions"] = ["stunned"]
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "fire bolt", [self.gob], rng=Seq(10))

    def test_target_list_required(self):
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "fire bolt", [], rng=Seq())
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "fire bolt", [self.gob, self.ogre], rng=Seq())

    def test_magic_missile_three_darts_never_miss(self):
        r = rules.cast(self.wiz, "magic missile", [self.ogre], rng=Seq(1, 2, 3))
        self.assertEqual(len(r["results"]), 3)
        self.assertEqual(self.ogre["hp"], 59 - (2 + 3 + 4))
        self.assertTrue(all(e["damage"]["type"] == "force" for e in r["results"]))

    def test_magic_missile_upcast_and_split(self):
        a, b = mon("goblin", id="a"), mon("goblin", id="b")
        r = rules.cast(self.wiz, "magic missile", [a, b], slot_level=2, rng=Seq(4, 4, 4, 4))
        self.assertEqual(r["slot_used"], 2)
        self.assertEqual(len(r["results"]), 4)
        self.assertEqual({e["target"] for e in r["results"]}, {"a", "b"})
        self.assertEqual((a["hp"], b["hp"]), (0, 0))

    def test_magic_missile_more_targets_than_darts_refused(self):
        crowd = [mon("goblin", id=f"g{i}") for i in range(4)]
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "magic missile", crowd, rng=Seq())

    def test_shield_negates_magic_missile(self):
        other = pc("wizard", id="w2")
        rules.cast(other, "shield", [], rng=Seq())
        self.assertEqual(rules.effective_ac(other), 17)
        rules.cast(self.wiz, "magic missile", [other], rng=Seq())
        self.assertEqual(other["hp"], 20)

    def test_shield_expires_at_start_of_casters_turn(self):
        rules.cast(self.wiz, "shield", [], rng=Seq())
        self.assertEqual(rules.effective_ac(self.wiz), 17)
        self.assertEqual(self.wiz["slots"]["1"][0], 3)
        rules.start_turn(self.wiz, [self.wiz])
        self.assertEqual(rules.effective_ac(self.wiz), 12)

    def test_burning_hands_save_outcomes_exact(self):
        a, b = mon("hobgoblin", id="a", hp=40, max_hp=40), mon("ogre", id="b")
        # damage 3d6 = 5+5+5 = 15; hobgoblin d20 3 + 1 = 4 < 13 fails; ogre d20 18 - 1 = 17 saves
        r = rules.cast(self.wiz, "burning hands", [a, b], rng=Seq(5, 5, 5, 3, 18))
        self.assertEqual((a["hp"], b["hp"]), (25, 59 - 7))
        self.assertFalse(r["results"][0]["save"]["success"])
        self.assertTrue(r["results"][1]["save"]["success"])

    def test_burning_hands_upcast_adds_a_die(self):
        r = rules.cast(self.wiz, "burning hands", [self.ogre], slot_level=2, rng=Seq(1, 1, 1, 1, 5))
        self.assertEqual(r["results"][0]["damage"]["rolls"][0]["formula"], "4d6")
        self.assertEqual(self.wiz["slots"]["2"][0], 1)

    def test_burning_hands_resistance_after_halving(self):
        t = mon("goblin", id="t", resist=["fire"], hp=50, max_hp=50)
        # 3d6 = 9; failed save, resist -> 4
        rules.cast(self.wiz, "burning hands", [t], rng=Seq(3, 3, 3, 1))
        self.assertEqual(t["hp"], 46)

    def test_thunderwave_pushes_on_failed_save_only(self):
        a, b = mon("goblin", id="a", hp=50, max_hp=50), mon("goblin", id="b", hp=50, max_hp=50)
        r = rules.cast(self.wiz, "thunderwave", [a, b], rng=Seq(4, 4, 2, 20))
        fail, ok = r["results"]
        self.assertEqual(fail["push"], 10)
        self.assertNotIn("push", ok)
        self.assertEqual((a["hp"], b["hp"]), (42, 46))

    def test_sacred_flame_ignores_cover_and_deals_nothing_on_save(self):
        t = mon("ogre", id="o", cover=5)
        r = rules.cast(self.cleric, "sacred flame", [t], rng=Seq(5, 20))
        self.assertTrue(r["results"][0]["save"]["success"])
        self.assertEqual(t["hp"], 59)
        t2 = mon("ogre", id="o2", cover=5)
        r = rules.cast(self.cleric, "sacred flame", [t2], rng=Seq(5, 2))
        self.assertEqual((r["results"][0]["save"]["total"], t2["hp"]), (1, 54))

    def test_cover_applies_to_dex_save_spells(self):
        t = mon("goblin", id="t", cover=5, hp=50, max_hp=50)
        # d20 6 + dex 2 + cover 5 = 13 meets DC 13
        r = rules.cast(self.wiz, "burning hands", [t], rng=Seq(4, 4, 4, 6))
        self.assertTrue(r["results"][0]["save"]["success"])
        self.assertEqual(t["hp"], 44)

    def test_cure_wounds_adds_modifier_and_disciple_of_life(self):
        f = pc("fighter", hp=10)
        r = rules.cast(self.cleric, "cure wounds", [f], rng=Seq(5))
        self.assertEqual(r["results"][0]["amount"], 5 + 3 + 3)
        self.assertEqual(f["hp"], 21)

    def test_cure_wounds_upcast_and_healing_word(self):
        f = pc("fighter", hp=1)
        rules.cast(self.cleric, "cure wounds", [f], slot_level=2, rng=Seq(2, 3))
        self.assertEqual(f["hp"], 1 + 5 + 3 + 4)
        g = pc("fighter", id="g", hp=1)
        rules.cast(self.cleric, "healing word", [g], rng=Seq(4))
        self.assertEqual(g["hp"], 1 + 4 + 3 + 3)

    def test_healing_at_zero_revives(self):
        f = lowdown(pc("fighter"))
        rules.cast(self.cleric, "healing word", [f], rng=Seq(1))
        self.assertGreater(f["hp"], 0)
        self.assertNotIn("unconscious", f["conditions"])

    def test_healing_has_no_effect_on_undead(self):
        z = mon("zombie", hp=5)
        r = rules.cast(self.cleric, "cure wounds", [z], rng=Seq())
        self.assertEqual((z["hp"], r["results"][0]["healed"]), (5, 0))
        self.assertEqual(self.cleric["slots"]["1"][0], 3)

    def test_healing_needs_one_target(self):
        with self.assertRaises(RuleError):
            rules.cast(self.cleric, "cure wounds", [pc("fighter"), pc("rogue")], rng=Seq())

    def test_guiding_bolt_damage_and_mark(self):
        r = rules.cast(self.cleric, "guiding bolt", [self.ogre], rng=Seq(14, 1, 2, 3, 4))
        self.assertEqual(r["results"][0]["damage"]["raw"], 10)
        self.assertIn("guiding_bolt", self.ogre["effects"])
        rules.end_turn(self.cleric, [self.ogre])
        self.assertNotIn("guiding_bolt", self.ogre["effects"])

    def test_guiding_bolt_miss_does_not_mark(self):
        rules.cast(self.cleric, "guiding bolt", [self.ogre], rng=Seq(2))
        self.assertNotIn("guiding_bolt", self.ogre["effects"])

    def test_ray_of_frost_slows_until_casters_next_turn(self):
        rules.cast(self.wiz, "ray of frost", [self.ogre], rng=Seq(15, 4))
        self.assertEqual(rules.effective_speed(self.ogre), 30)
        rules.start_turn(self.wiz, [self.wiz, self.ogre])
        self.assertEqual(rules.effective_speed(self.ogre), 40)

    def test_scorching_ray_three_rays_each_with_own_attack(self):
        r = rules.cast(self.wiz, "scorching ray", [self.ogre], slot_level=2, rng=Seq(15, 1, 1, 2, 20, 3, 3, 4, 4))
        self.assertEqual(len(r["results"]), 3)
        self.assertEqual([e["hit"] for e in r["results"]], [True, False, True])
        self.assertTrue(r["results"][2]["critical"])
        self.assertEqual(self.ogre["hp"], 59 - 2 - (3 + 3 + 4 + 4))

    def test_scorching_ray_upcast_four_rays_across_targets(self):
        self.wiz["slots"]["3"] = [1, 1]
        a, b = mon("goblin", id="a", hp=99, max_hp=99), mon("goblin", id="b", hp=99, max_hp=99)
        r = rules.cast(self.wiz, "scorching ray", [a, a, b, b], slot_level=3,
                       rng=Seq(*([15, 1, 1] * 4)))
        self.assertEqual([e["target"] for e in r["results"]], ["a", "a", "b", "b"])

    def test_bless_targets_cap_upcast_and_concentration(self):
        crew = [pc("fighter", id="f"), pc("rogue", id="r"), pc("wizard", id="w"), pc("cleric", id="c2")]
        with self.assertRaises(RuleError):
            rules.cast(self.cleric, "bless", crew, rng=Seq())
        r = rules.cast(self.cleric, "bless", crew[:3], rng=Seq())
        self.assertTrue(all("bless" in c["effects"] for c in crew[:3]))
        self.assertEqual(self.cleric["concentration"]["spell"], "bless")
        r = rules.cast(self.cleric, "bless", crew, slot_level=2, rng=Seq())
        self.assertEqual(r["slot_used"], 2)

    def test_new_concentration_spell_ends_the_previous_one(self):
        crew = [pc("fighter", id="f")]
        rules.cast(self.cleric, "bless", crew, rng=Seq())
        self.cleric["spells"].append("hold person")
        bandit = mon("bandit", id="b")
        r = rules.cast(self.cleric, "hold person", [bandit], slot_level=2, rng=Seq(1), creatures=crew + [bandit])
        self.assertEqual(r["ended_concentration"], "bless")
        self.assertNotIn("bless", crew[0]["effects"])
        self.assertEqual(self.cleric["concentration"]["spell"], "hold person")

    def test_sleep_lowest_hp_first_and_pool_limit(self):
        a, b, c = mon("goblin", id="a"), mon("hobgoblin", id="b"), mon("orc", id="c")  # 7, 11, 15
        r = rules.cast(self.wiz, "sleep", [c, b, a], rng=Seq(4, 4, 4, 4, 1))  # pool 17
        by = {e["target"]: e["affected"] for e in r["results"]}
        self.assertEqual(by, {"a": True, "b": False, "c": False})
        self.assertEqual([e["target"] for e in r["results"]], ["c", "b", "a"])
        self.assertIn("unconscious", a["conditions"])
        self.assertIn("asleep", a["effects"])

    def test_sleep_pool_exact_fit(self):
        a, b = mon("goblin", id="a"), mon("hobgoblin", id="b")  # 7 + 11 = 18
        r = rules.cast(self.wiz, "sleep", [a, b], rng=Seq(4, 4, 4, 4, 2))  # pool 18
        self.assertTrue(all(e["affected"] for e in r["results"]))

    def test_sleep_ignores_undead_elves_and_unconscious(self):
        z = mon("zombie", id="z", hp=1)
        elf = pc("wizard", id="e", hp=1)
        down = mon("goblin", id="d", conditions=["unconscious"])
        g = mon("goblin", id="g")
        r = rules.cast(self.wiz, "sleep", [z, elf, down, g], rng=Seq(8, 8, 8, 8, 8))
        by = {e["target"]: e["affected"] for e in r["results"]}
        self.assertEqual(by, {"z": False, "e": False, "d": False, "g": True})

    def test_sleep_upcast_adds_two_dice(self):
        a = mon("goblin", id="a")
        r = rules.cast(self.wiz, "sleep", [a], slot_level=2, rng=Seq(*([1] * 7)))
        self.assertIn("7 hit points", r["notes"][0])

    def test_hold_person_paralyzes_on_failed_save(self):
        bandit = mon("bandit", id="b")
        r = rules.cast(self.wiz, "hold person", [bandit], rng=Seq(3))  # d20 3 + wis 0
        self.assertTrue(r["results"][0]["affected"])
        self.assertIn("paralyzed", bandit["conditions"])
        self.assertEqual(self.wiz["slots"]["2"][0], 1)
        self.assertEqual(self.wiz["concentration"]["spell"], "hold person")

    def test_hold_person_save_success_and_non_humanoid(self):
        bandit = mon("bandit", id="b")
        r = rules.cast(self.wiz, "hold person", [bandit], rng=Seq(18))
        self.assertFalse(r["results"][0]["affected"])
        self.assertEqual(bandit["conditions"], [])
        wolf = mon("wolf", id="w")
        r = rules.cast(self.wiz, "hold person", [wolf], rng=Seq())
        self.assertEqual(r["results"][0]["notes"], ["not a humanoid"])

    def test_hold_person_repeat_save_at_end_of_turn(self):
        bandit = mon("bandit", id="b")
        rules.cast(self.wiz, "hold person", [bandit], rng=Seq(3))
        out = rules.end_turn(bandit, [bandit], rng=Seq(4))
        self.assertIn("paralyzed", bandit["conditions"])
        self.assertFalse(out["saves"][0]["success"])
        rules.end_turn(bandit, [bandit], rng=Seq(15))
        self.assertNotIn("paralyzed", bandit["conditions"])
        self.assertNotIn("hold_person", bandit["effects"])

    def test_hold_person_upcast_second_target(self):
        a, b = mon("bandit", id="a"), mon("bandit", id="b")
        self.wiz["slots"]["3"] = [1, 1]
        with self.assertRaises(RuleError):
            rules.cast(self.wiz, "hold person", [a, b], rng=Seq())
        r = rules.cast(self.wiz, "hold person", [a, b], slot_level=3, rng=Seq(1, 1))
        self.assertEqual(len(r["results"]), 2)

    def test_paralyzed_target_of_hold_person_takes_auto_crits(self):
        bandit = mon("bandit", id="b")
        rules.cast(self.wiz, "hold person", [bandit], rng=Seq(1))
        f = pc("fighter")
        r = rules.resolve_attack(f, bandit, f["attacks"][0], rng=Seq(10, 10, 1, 1))
        self.assertTrue(r["critical"] and r["auto_crit"])


class SrdContentTests(unittest.TestCase):
    # Reference values transcribed from the SRD 5.1 stat blocks (cross-checked with dnd5eapi.co).
    EXPECTED = {
        "goblin": (15, 7, 30, "1/4", 50, "Small"),
        "hobgoblin": (18, 11, 30, "1/2", 100, "Medium"),
        "kobold": (12, 5, 30, "1/8", 25, "Small"),
        "wolf": (13, 11, 40, "1/4", 50, "Medium"),
        "dire_wolf": (14, 37, 50, "1", 200, "Large"),
        "skeleton": (13, 13, 30, "1/4", 50, "Medium"),
        "zombie": (8, 22, 20, "1/4", 50, "Medium"),
        "orc": (13, 15, 30, "1/2", 100, "Medium"),
        "bandit": (12, 11, 30, "1/8", 25, "Medium"),
        "bandit_captain": (15, 65, 30, "2", 450, "Medium"),
        "giant_rat": (12, 7, 30, "1/8", 25, "Small"),
        "ogre": (11, 59, 40, "2", 450, "Large"),
    }
    CONTRACT_KEYS = {"id", "name", "kind", "owner", "ac", "hp", "max_hp", "temp_hp", "abilities", "proficiency",
                     "saves", "skills", "attacks", "resist", "immune", "vuln", "conditions", "death_saves",
                     "slots", "spells", "hit_dice", "pos", "speed", "concentration"}

    def test_twelve_monsters_with_srd_numbers(self):
        self.assertEqual(set(srd.MONSTERS), set(self.EXPECTED))
        for key, (ac, hp, speed, cr, xp, size) in self.EXPECTED.items():
            m = srd.MONSTERS[key]
            self.assertEqual((m["ac"], m["hp"], m["max_hp"], m["speed"], m["cr"], m["xp"], m["size"]),
                             (ac, hp, hp, speed, cr, xp, size), key)

    def test_monster_hp_matches_hit_dice_formula(self):
        for key, m in srd.MONSTERS.items():
            n, rest = m["hp_formula"].split("d")
            sides, _, bonus = rest.replace("-", "+-").partition("+")
            expect = int(int(n) * (int(sides) + 1) / 2 + int(bonus or 0))
            self.assertEqual(m["hp"], expect, key)
            self.assertEqual(m["hit_dice"], [int(n), int(n), f"d{sides}"], key)
            con_bonus = rules.mod(m["abilities"]["con"]) * int(n)
            self.assertEqual(int(bonus or 0), con_bonus, key)

    def test_attack_bonuses_derive_from_ability_and_proficiency(self):
        for key, m in srd.MONSTERS.items():
            best = max(rules.mod(m["abilities"]["str"]), rules.mod(m["abilities"]["dex"]))
            for a in m["attacks"]:
                self.assertEqual(a["to_hit"], m["proficiency"] + best, (key, a["name"]))
                bonus = int(a["damage"].split("+")[1]) if "+" in a["damage"] else 0
                self.assertEqual(bonus, best, (key, a["name"]))

    def test_damage_types_and_ranges_valid(self):
        for key, m in srd.MONSTERS.items():
            for a in m["attacks"]:
                self.assertIn(a["type"], rules.DAMAGE_TYPES)
                self.assertTrue(a["reach"] or a["range"], (key, a["name"]))
                rules.parse_formula(a["damage"])

    def test_resistances_immunities_vulnerabilities(self):
        s, z = srd.MONSTERS["skeleton"], srd.MONSTERS["zombie"]
        self.assertEqual((s["vuln"], s["immune"]), (["bludgeoning"], ["poison"]))
        self.assertEqual(z["immune"], ["poison"])
        self.assertEqual(z["saves"], ["wis"])
        self.assertEqual(rules.saving_throw(z, "wis", 1, rng=Seq(10))["bonus"], 0)
        for key in set(srd.MONSTERS) - {"skeleton", "zombie"}:
            m = srd.MONSTERS[key]
            self.assertEqual((m["vuln"], m["resist"], m["immune"]), ([], [], []), key)

    def test_specific_attacks(self):
        atk = lambda m, n: next(a for a in srd.MONSTERS[m]["attacks"] if a["name"] == n)
        self.assertEqual((atk("goblin", "Shortbow")["range"], atk("goblin", "Shortbow")["damage"]), ([80, 320], "1d6+2"))
        self.assertEqual(atk("hobgoblin", "Longbow")["range"], [150, 600])
        self.assertEqual(atk("kobold", "Sling")["type"], "bludgeoning")
        self.assertEqual((atk("wolf", "Bite")["damage"], atk("wolf", "Bite")["rider"]["dc"]), ("2d4+2", 11))
        self.assertEqual((atk("dire_wolf", "Bite")["damage"], atk("dire_wolf", "Bite")["rider"]["dc"]), ("2d6+3", 13))
        self.assertEqual(atk("ogre", "Greatclub")["damage"], "2d8+4")
        self.assertEqual(atk("ogre", "Javelin")["damage"], "2d6+4")
        self.assertEqual(atk("orc", "Greataxe")["damage"], "1d12+3")
        self.assertEqual(atk("bandit_captain", "Dagger")["range"], [20, 60])
        self.assertEqual(atk("bandit", "Light Crossbow")["damage"], "1d8+1")

    def test_bandit_captain_multiattack(self):
        m = srd.MONSTERS["bandit_captain"]["multiattack"]
        self.assertEqual(m["melee"], ["Scimitar", "Scimitar", "Dagger"])
        self.assertEqual(m["ranged"], ["Dagger", "Dagger"])
        self.assertEqual(srd.MONSTERS["bandit_captain"]["saves"], ["str", "dex", "wis"])

    def test_monster_skills_match_srd(self):
        g = srd.MONSTERS["goblin"]
        self.assertEqual(rules.ability_check(g, "stealth", 10, rng=Seq(10))["bonus"], 6)
        w = srd.MONSTERS["wolf"]
        self.assertEqual(rules.ability_check(w, "perception", 10, rng=Seq(10))["bonus"], 3)
        self.assertEqual(rules.ability_check(w, "stealth", 10, rng=Seq(10))["bonus"], 4)
        self.assertEqual(rules.ability_check(srd.MONSTERS["orc"], "intimidation", 10, rng=Seq(10))["bonus"], 2)
        c = srd.MONSTERS["bandit_captain"]
        self.assertEqual(rules.ability_check(c, "athletics", 10, rng=Seq(10))["bonus"], 4)
        self.assertEqual(rules.ability_check(c, "deception", 10, rng=Seq(10))["bonus"], 4)
        self.assertEqual(rules.saving_throw(c, "dex", 10, rng=Seq(10))["bonus"], 5)

    def test_senses_passive_perception_matches_computation(self):
        for coll in (srd.MONSTERS, srd.CHARACTERS):
            for key, c in coll.items():
                stated = int(c["senses"].rsplit("passive Perception ", 1)[1])
                self.assertEqual(rules.passive_perception(c), stated, key)

    def test_creature_dicts_carry_the_contract_keys(self):
        for coll in (srd.MONSTERS, srd.CHARACTERS):
            for key, c in coll.items():
                self.assertTrue(self.CONTRACT_KEYS <= set(c), (key, self.CONTRACT_KEYS - set(c)))
                self.assertEqual(c["hp"], c["max_hp"])
                self.assertEqual(c["death_saves"], {"s": 0, "f": 0})
                for ab in rules.ABILITIES:
                    self.assertIn(ab, c["abilities"])
                for a in c["attacks"]:
                    self.assertTrue({"name", "to_hit", "damage", "type", "reach", "range"} <= set(a))

    def test_four_level_three_characters(self):
        self.assertEqual(set(srd.CHARACTERS), {"fighter", "rogue", "wizard", "cleric"})
        for c in srd.CHARACTERS.values():
            self.assertEqual((c["level"], c["proficiency"], c["kind"]), (3, 2, "pc"))
            self.assertEqual(c["hit_dice"][:2], [3, 3])

    def test_character_hit_points_follow_class_hit_die(self):
        def hp(c, extra=0):
            die = int(c["hit_dice"][2][1:])
            con = rules.mod(c["abilities"]["con"])
            return die + con + 2 * (die // 2 + 1 + con) + extra
        for key, extra in (("fighter", 0), ("rogue", 0), ("wizard", 0), ("cleric", 3)):
            c = srd.CHARACTERS[key]
            self.assertEqual(c["max_hp"], hp(c, extra), key)

    def test_character_armor_class(self):
        ch = srd.CHARACTERS
        self.assertEqual(ch["fighter"]["ac"], 16 + 2)  # chain mail and shield
        self.assertEqual(ch["rogue"]["ac"], 11 + 3)  # leather and dex
        self.assertEqual(ch["wizard"]["ac"], 10 + 2)
        self.assertEqual(ch["cleric"]["ac"], 16 + 2)

    def test_character_attacks_follow_the_numbers(self):
        f = srd.CHARACTERS["fighter"]
        self.assertEqual((f["attacks"][0]["to_hit"], f["attacks"][0]["damage"]), (5, "1d8+5"))  # str 3 + prof 2, dueling +2
        self.assertEqual((f["attacks"][1]["to_hit"], f["attacks"][1]["range"]), (4, [150, 600]))
        r = srd.CHARACTERS["rogue"]
        self.assertEqual(r["attacks"][0]["to_hit"], 5)
        self.assertEqual(r["attacks"][0]["extra"], {"damage": "2d6", "when": "sneak"})
        w = srd.CHARACTERS["wizard"]
        self.assertEqual((w["attacks"][0]["to_hit"], w["attacks"][0]["damage"]), (1, "1d6-1"))
        self.assertEqual(w["attacks"][1]["to_hit"], 4)
        self.assertEqual(srd.CHARACTERS["cleric"]["attacks"][0]["to_hit"], 3)

    def test_character_proficiencies(self):
        ch = srd.CHARACTERS
        self.assertEqual(ch["fighter"]["saves"], ["str", "con"])
        self.assertEqual(ch["rogue"]["saves"], ["dex", "int"])
        self.assertEqual(ch["wizard"]["saves"], ["int", "wis"])
        self.assertEqual(ch["cleric"]["saves"], ["wis", "cha"])
        self.assertEqual(ch["rogue"]["skills"]["stealth"], "expertise")
        self.assertEqual(ch["fighter"]["crit_range"], 19)
        self.assertEqual(ch["cleric"]["resist"], ["poison"])

    def test_character_spellcasting(self):
        for key in ("wizard", "cleric"):
            c = srd.CHARACTERS[key]
            self.assertEqual(c["slots"], {"1": [4, 4], "2": [2, 2]})
            for name in c["spells"]:
                self.assertIn(name, srd.SPELLS, name)
        self.assertEqual(srd.CHARACTERS["wizard"]["spell_ability"], "int")
        self.assertEqual(srd.CHARACTERS["cleric"]["spell_ability"], "wis")
        self.assertEqual(srd.CHARACTERS["fighter"]["slots"], {})

    def test_fourteen_spells_with_srd_levels(self):
        levels = {"fire bolt": 0, "ray of frost": 0, "sacred flame": 0, "magic missile": 1, "burning hands": 1,
                  "thunderwave": 1, "shield": 1, "cure wounds": 1, "healing word": 1, "guiding bolt": 1,
                  "bless": 1, "sleep": 1, "hold person": 2, "scorching ray": 2}
        self.assertEqual({k: v["level"] for k, v in srd.SPELLS.items()}, levels)
        for k, s in srd.SPELLS.items():
            self.assertEqual(s["concentration"], k in ("bless", "hold person"), k)

    def test_spell_dice_match_srd(self):
        s = srd.SPELLS
        self.assertEqual((s["fire bolt"]["dice"], s["fire bolt"]["dtype"]), ((1, 10), "fire"))
        self.assertEqual((s["ray of frost"]["dice"], s["ray of frost"]["dtype"]), ((1, 8), "cold"))
        self.assertEqual((s["sacred flame"]["dice"], s["sacred flame"]["save"]), ((1, 8), "dex"))
        self.assertEqual((s["magic missile"]["count"], s["magic missile"]["dice"], s["magic missile"]["flat"]), (3, (1, 4), 1))
        self.assertEqual((s["burning hands"]["dice"], s["burning hands"]["per_level"], s["burning hands"]["save"]), ((3, 6), (1, 6), "dex"))
        self.assertEqual((s["thunderwave"]["dice"], s["thunderwave"]["per_level"], s["thunderwave"]["save"], s["thunderwave"]["push"]), ((2, 8), (1, 8), "con", 10))
        self.assertEqual(s["shield"]["ac_bonus"], 5)
        self.assertEqual((s["cure wounds"]["dice"], s["healing word"]["dice"]), ((1, 8), (1, 4)))
        self.assertEqual((s["guiding bolt"]["dice"], s["guiding bolt"]["per_level"]), ((4, 6), (1, 6)))
        self.assertEqual((s["bless"]["max_targets"], s["bless"]["targets_per_level"]), (3, 1))
        self.assertEqual((s["sleep"]["dice"], s["sleep"]["per_level"]), ((5, 8), (2, 8)))
        self.assertEqual((s["hold person"]["save"], s["hold person"]["targets_per_level"]), ("wis", 1))
        self.assertEqual((s["scorching ray"]["count"], s["scorching ray"]["dice"]), (3, (2, 6)))
        for sp in s.values():
            if "dtype" in sp:
                self.assertIn(sp["dtype"], rules.DAMAGE_TYPES)

    def test_new_copies_are_independent(self):
        a, b = srd.new_monster("goblin", id="g1"), srd.new_monster("goblin", id="g2", pos=(3, 4))
        a["hp"] = 1
        a["attacks"][0]["to_hit"] = 99
        a["conditions"].append("prone")
        self.assertEqual((b["hp"], b["attacks"][0]["to_hit"], b["conditions"], b["pos"]), (7, 4, [], [3, 4]))
        self.assertEqual(srd.MONSTERS["goblin"]["hp"], 7)
        w = srd.new_character("wizard", owner="u9")
        w["slots"]["1"][0] = 0
        self.assertEqual(srd.CHARACTERS["wizard"]["slots"]["1"], [4, 4])
        self.assertEqual(w["owner"], "u9")
        with self.assertRaises(KeyError):
            srd.new_monster("dragon")

    def test_attribution_is_cc_by_4(self):
        self.assertIn("System Reference Document 5.1", srd.ATTRIBUTION)
        self.assertIn("Creative Commons Attribution 4.0", srd.ATTRIBUTION)
        self.assertIn("creativecommons.org/licenses/by/4.0", srd.ATTRIBUTION)

    def test_no_em_dashes_in_content(self):
        blob = repr(srd.MONSTERS) + repr(srd.CHARACTERS) + repr(srd.SPELLS)
        self.assertNotIn("—", blob)
        self.assertNotIn(" -- ", blob)


class TacticsTests(unittest.TestCase):
    def arena(self):
        return {
            "f": pc("fighter", id="f", pos=[4, 4]),
            "w": pc("wizard", id="w", pos=[4, 5]),
            "r": pc("rogue", id="r", pos=[8, 8]),
        }

    def test_lowest_ac_pc_in_reach(self):
        pcs = self.arena()
        ogre = mon("ogre", id="o", pos=[5, 4])  # touches f (AC 18) and w at (4,5)
        plan = rules.monster_action(ogre, [ogre, *pcs.values()], rng=Seq(10, 1, 1))
        self.assertEqual((plan["action"], plan["target"]), ("attack", "w"))
        self.assertIsNone(plan["move"])

    def test_ties_break_on_low_hp_then_id(self):
        hi, lo = pc("wizard", id="b", pos=[1, 1], hp=9), pc("wizard", id="a", pos=[1, 2], hp=9)
        ogre = mon("ogre", id="o", pos=[2, 1])
        self.assertEqual(rules.monster_action(ogre, [ogre, hi, lo], rng=Seq(10, 1, 1))["target"], "a")
        lo["hp"] = 12
        self.assertEqual(rules.monster_action(ogre, [ogre, hi, lo], rng=Seq(10, 1, 1))["target"], "b")

    def test_ignores_unconscious_while_others_stand(self):
        pcs = self.arena()
        lowdown(pcs["w"])
        ogre = mon("ogre", id="o", pos=[5, 4])
        plan = rules.monster_action(ogre, [ogre, *pcs.values()], rng=Seq(10, 1, 1))
        self.assertEqual(plan["target"], "f")

    def test_attacks_downed_pc_when_nobody_else_is_up(self):
        w = lowdown(pc("wizard", id="w", pos=[1, 1]))
        ogre = mon("ogre", id="o", pos=[2, 1])
        plan = rules.monster_action(ogre, [ogre, w], rng=Seq(10, 10, 1, 1, 1, 1))
        self.assertEqual((plan["action"], plan["target"]), ("attack", "w"))

    def test_no_foes(self):
        ogre = mon("ogre", id="o", pos=[2, 1])
        plan = rules.monster_action(ogre, [ogre, mon("goblin", id="g", pos=[3, 3])], rng=Seq())
        self.assertEqual(plan["action"], "none")

    def test_incapacitated_or_dead_monster_does_nothing(self):
        pcs = self.arena()
        for cond in ("stunned", "paralyzed", "dead"):
            m = mon("orc", id="o", pos=[5, 4], conditions=[cond])
            self.assertEqual(rules.monster_action(m, [m, *pcs.values()], rng=Seq())["action"], "none")

    def test_moves_to_nearest_and_attacks(self):
        pcs = self.arena()
        orc = mon("orc", id="o", pos=[5, 0])  # speed 30 = 6 squares; fighter is nearest
        plan = rules.monster_action(orc, [orc, *pcs.values()], rng=Seq(15, 1))
        self.assertEqual((plan["action"], plan["target"], plan["melee"]), ("attack", "f", True))
        self.assertEqual(rules._sq(plan["move"]["to"], [4, 4]), 1)
        self.assertEqual(plan["move"]["squares"], 3)
        self.assertEqual(orc["pos"], [5, 0])  # apply=False leaves position alone

    def test_cannot_reach_so_only_moves(self):
        w = pc("wizard", id="w", pos=[0, 0])
        zombie = mon("zombie", id="z", pos=[11, 9])  # speed 20 = 4 squares
        plan = rules.monster_action(zombie, [zombie, w], rng=Seq())
        self.assertEqual(plan["action"], "move")
        self.assertEqual(plan["move"]["squares"], 4)
        self.assertEqual(plan["move"]["to"], [7, 5])

    def test_move_never_ends_on_an_occupied_cell_and_enemies_block_the_path(self):
        w = pc("wizard", id="w", pos=[5, 5])
        wall = [pc("fighter", id=f"x{i}", pos=[6, i]) for i in range(10)]  # a full wall of PCs
        orc = mon("orc", id="o", pos=[9, 5])
        cells = rules._reachable(orc, [orc, w, *wall], 12)
        self.assertTrue(cells and all(x > 6 for x, _ in cells))
        plan = rules.monster_action(orc, [orc, w, *wall], rng=Seq(15, 1))
        self.assertEqual((plan["target"], plan["move"]["to"]), ("x2", [7, 3]))
        ally = mon("goblin", id="g", pos=[7, 3])  # allies can be crossed but not occupied
        plan = rules.monster_action(orc, [orc, ally, w, *wall], rng=Seq(15, 1))
        self.assertNotEqual(plan["move"]["to"], [7, 3])
        self.assertEqual((plan["move"]["squares"], rules._sq(plan["move"]["to"], [6, 2])), (3, 1))

    def test_never_moves_off_grid(self):
        w = pc("wizard", id="w", pos=[0, 0])
        wolf = mon("wolf", id="w1", pos=[11, 9])
        plan = rules.monster_action(wolf, [wolf, w], rng=Seq())
        x, y = plan["move"]["to"]
        self.assertTrue(0 <= x < rules.GRID_W and 0 <= y < rules.GRID_H)

    def test_goblin_flees_at_quarter_hp(self):
        f = pc("fighter", id="f", pos=[4, 4])
        gob = mon("goblin", id="g", pos=[5, 4], hp=1)
        plan = rules.monster_action(gob, [gob, f], rng=Seq())
        self.assertEqual(plan["action"], "flee")
        self.assertGreater(rules._sq(plan["flee"]["to"], [4, 4]), 1)
        self.assertEqual(plan["flee"]["away_from"], "f")

    def test_flee_threshold_is_exactly_quarter(self):
        f = pc("fighter", id="f", pos=[4, 4])
        k = mon("kobold", id="k", pos=[5, 4], hp=2)  # max 5: 2 > 1.25
        self.assertEqual(rules.monster_action(k, [k, f], rng=Seq(10, 1))["action"], "attack")
        k["hp"] = 1
        self.assertEqual(rules.monster_action(k, [k, f], rng=Seq())["action"], "flee")
        g = mon("goblin", id="g", pos=[5, 4], hp=2)  # 2*4 > 7
        self.assertEqual(rules.monster_action(g, [g, f], rng=Seq(10, 1))["action"], "attack")

    def test_other_monsters_do_not_flee(self):
        f = pc("fighter", id="f", pos=[4, 4])
        for key in ("ogre", "orc", "hobgoblin", "wolf", "bandit"):
            m = mon(key, id="m", pos=[5, 4])
            m["hp"] = 1
            self.assertEqual(rules.monster_action(m, [m, f], rng=Seq(10, 1, 1))["action"], "attack", key)

    def test_cornered_goblin_fights_back(self):
        f = pc("fighter", id="f", pos=[1, 0])
        gob = mon("goblin", id="g", pos=[0, 0], hp=1)
        blockers = [pc("rogue", id="r1", pos=[0, 1]), pc("rogue", id="r2", pos=[1, 1])]
        plan = rules.monster_action(gob, [gob, f, *blockers], rng=Seq(10, 1))
        self.assertEqual(plan["action"], "attack")

    def test_flee_apply_moves_the_monster(self):
        f = pc("fighter", id="f", pos=[4, 4])
        gob = mon("goblin", id="g", pos=[5, 4], hp=1)
        plan = rules.monster_action(gob, [gob, f], rng=Seq(), apply=True)
        self.assertEqual(gob["pos"], plan["flee"]["to"])

    def test_pack_tactics_advantage_with_adjacent_ally(self):
        f = pc("fighter", id="f", pos=[4, 4])
        w1, w2 = mon("wolf", id="w1", pos=[5, 4]), mon("wolf", id="w2", pos=[3, 4])
        plan = rules.monster_action(w1, [w1, w2, f], rng=Seq(6, 17, 1, 1, 20))
        self.assertTrue(plan["pack_tactics"])
        self.assertEqual(plan["attack"]["attack_roll"]["mode"], "advantage")
        self.assertEqual(plan["attack"]["attack_roll"]["natural"], 17)

    def test_pack_tactics_needs_an_able_adjacent_ally(self):
        f = pc("fighter", id="f", pos=[4, 4])
        w1 = mon("wolf", id="w1", pos=[5, 4])
        far = mon("wolf", id="w2", pos=[9, 9])
        plan = rules.monster_action(w1, [w1, far, f], rng=Seq(10))
        self.assertFalse(plan["pack_tactics"])
        down = mon("wolf", id="w3", pos=[3, 4], conditions=["stunned"])
        plan = rules.monster_action(w1, [w1, down, f], rng=Seq(10))
        self.assertFalse(plan["pack_tactics"])

    def test_pack_tactics_only_for_pack_monsters(self):
        f = pc("fighter", id="f", pos=[4, 4])
        o1, o2 = mon("ogre", id="o1", pos=[5, 4]), mon("ogre", id="o2", pos=[3, 4])
        plan = rules.monster_action(o1, [o1, o2, f], rng=Seq(10))
        self.assertFalse(plan["pack_tactics"])

    def test_hobgoblin_martial_advantage_uses_neighbouring_ally(self):
        w = pc("wizard", id="w", pos=[4, 4])
        h = mon("hobgoblin", id="h", pos=[5, 4])
        buddy = mon("goblin", id="b", pos=[3, 4])
        plan = rules.monster_action(h, [h, buddy, w], rng=Seq(18, 4, 3, 3))
        self.assertEqual(len(plan["attack"]["damage"]["rolls"]), 2)

    def test_multiattack_makes_three_melee_attacks(self):
        w = pc("wizard", id="w", pos=[4, 4], hp=200, max_hp=200)
        cap = mon("bandit_captain", id="c", pos=[5, 4])
        plan = rules.monster_action(cap, [cap, w], rng=Seq(*([18, 1] * 3)))
        self.assertEqual([a["attack"] for a in plan["attacks"]], ["Scimitar", "Scimitar", "Dagger"])
        self.assertIs(plan["attack"], plan["attacks"][0])

    def test_multiattack_ranged_uses_two_daggers_when_it_cannot_close(self):
        w = pc("wizard", id="w", pos=[0, 0])
        cap = mon("bandit_captain", id="c", pos=[5, 0], effects={"mud": {"speed_penalty": 30}})
        plan = rules.monster_action(cap, [cap, w], rng=Seq(*([18, 1] * 2)))
        self.assertEqual([a["attack"] for a in plan["attacks"]], ["Dagger", "Dagger"])
        self.assertFalse(plan["melee"])

    def test_apply_true_moves_and_wounds(self):
        f = pc("fighter", id="f", pos=[4, 4])
        orc = mon("orc", id="o", pos=[8, 4])
        plan = rules.monster_action(orc, [orc, f], rng=Seq(15, 9), apply=True)
        self.assertEqual(orc["pos"], plan["move"]["to"])
        self.assertEqual(f["hp"], 28 - (9 + 3))
        self.assertEqual(plan["outcomes"][0]["hp"], f["hp"])

    def test_apply_stops_multiattack_when_target_goes_down(self):
        w = pc("wizard", id="w", pos=[4, 4], hp=3)
        cap = mon("bandit_captain", id="c", pos=[5, 4])
        plan = rules.monster_action(cap, [cap, w], rng=Seq(18, 6, 6), apply=True)
        self.assertEqual(len(plan["attacks"]), 1)
        self.assertEqual(w["hp"], 0)

    def test_monster_closes_for_melee_when_it_can_reach(self):
        w = pc("wizard", id="w", pos=[0, 0])
        gob = mon("goblin", id="g", pos=[6, 0])  # 30 ft: shortbow range, but scimitar reach is 5 steps away
        plan = rules.monster_action(gob, [gob, w], rng=Seq(15, 3))
        self.assertEqual((plan["melee"], plan["attack"]["attack"]), (True, "Scimitar"))
        self.assertEqual(plan["move"]["squares"], 5)

    def test_ranged_only_when_cannot_close(self):
        w = pc("wizard", id="w", pos=[0, 0])
        gob = mon("goblin", id="g", pos=[11, 0], effects={"slow": {"speed_penalty": 30}})  # speed 0
        plan = rules.monster_action(gob, [gob, w], rng=Seq(15, 3))
        self.assertEqual((plan["action"], plan["melee"], plan["attack"]["attack"]), ("attack", False, "Shortbow"))

    def test_ranged_attack_next_to_enemy_has_disadvantage(self):
        w = pc("wizard", id="w", pos=[0, 0])
        skel = mon("skeleton", id="s", pos=[1, 0])
        skel["attacks"] = [a for a in skel["attacks"] if a["name"] == "Shortbow"]
        plan = rules.monster_action(skel, [skel, w], rng=Seq(15, 3, 3))
        self.assertEqual(plan["attack"]["attack_roll"]["mode"], "disadvantage")

    def test_no_positions_means_everyone_is_adjacent(self):
        f, ogre = pc("fighter", id="f"), mon("ogre", id="o")
        plan = rules.monster_action(ogre, [ogre, f], rng=Seq(15, 4, 4))
        self.assertEqual((plan["action"], plan["target"], plan["move"]), ("attack", "f", None))

    def test_deterministic_for_equal_state(self):
        def run():
            pcs = self.arena()
            wolf = mon("wolf", id="w1", pos=[9, 9])
            return rules.monster_action(wolf, [wolf, *pcs.values()], rng=random.Random(5))
        a, b = run(), run()
        self.assertEqual((a["target"], a["move"]), (b["target"], b["move"]))
        self.assertEqual(a["attack"]["to_hit"] if "attack" in a else None, b["attack"]["to_hit"] if "attack" in b else None)

    def test_slowed_monster_moves_less(self):
        w = pc("wizard", id="w", pos=[0, 0])
        zombie = mon("zombie", id="z", pos=[11, 9], effects={"ray_of_frost": {"speed_penalty": 10}})
        plan = rules.monster_action(zombie, [zombie, w], rng=Seq())
        self.assertEqual(plan["move"]["squares"], 2)


class IntegrationTests(unittest.TestCase):
    def test_four_round_skirmish_is_reproducible_and_ends_in_a_known_state(self):
        def fight(seed):
            rng = random.Random(seed)
            party = [srd.new_character(k, id=k, owner=k, pos=p) for k, p in
                     (("fighter", (4, 4)), ("rogue", (3, 4)), ("wizard", (2, 4)), ("cleric", (3, 3)))]
            foes = [srd.new_monster("goblin", id="g1", pos=(5, 4)), srd.new_monster("wolf", id="w1", pos=(6, 4)),
                    srd.new_monster("orc", id="o1", pos=(7, 4))]
            everyone = party + foes
            order = rules.roll_initiative(everyone, rng=rng)
            by_id = {c["id"]: c for c in everyone}
            for _ in range(4):
                for cid in order:
                    c = by_id[cid]
                    if rules.state(c) == "dead" or c["hp"] <= 0:
                        continue
                    if c["kind"] == "monster":
                        rules.monster_action(c, everyone, rng=rng, apply=True)
                    else:
                        tgt = next((m for m in foes if rules.state(m) != "dead"), None)
                        if tgt:
                            rules.resolve_attack(c, tgt, c["attacks"][0], melee=True, rng=rng, apply=True)
            return [(c["id"], c["hp"], c["pos"], tuple(c["conditions"])) for c in everyone]
        self.assertEqual(fight(11), fight(11))
        self.assertNotEqual(fight(11), fight(12))
        for _, hp, pos, _ in fight(11):
            self.assertGreaterEqual(hp, 0)
            self.assertTrue(0 <= pos[0] < 12 and 0 <= pos[1] < 10)


if __name__ == "__main__":
    unittest.main()
