"""SRD 5.1 rules engine for Tablekeeper.

Pure functions over creature dicts (shape documented in srd.py). Randomness is
injectable: every roll takes ``rng`` (anything with ``randint(a, b)``) and
defaults to ``secrets.SystemRandom``.

Mutation contract
-----------------
* ``apply_damage``, ``heal``, ``death_save``, ``cast``, ``short_rest``,
  ``long_rest``, ``add_condition``, ``remove_condition``, ``start_turn``,
  ``end_turn`` and ``concentration_check`` change the creature dicts passed in.
* ``resolve_attack`` and ``monster_action`` roll what happened but never change
  hit points or position unless called with ``apply=True``. ``damage["raw"]``
  and ``damage["type"]`` are the inputs for ``apply_damage``; ``applied`` is the
  amount after resistance, vulnerability and immunity (before temp HP).
"""
from __future__ import annotations

import re
import secrets
from collections import deque

from . import srd

GRID_W, GRID_H = 12, 10
MAX_FORMULA_LEN = 64
MAX_DICE = 100
MAX_SIDES = 1000
MAX_CONSTANT = 100_000

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
_ABILITY_NAMES = {"strength": "str", "dexterity": "dex", "constitution": "con",
                  "intelligence": "int", "wisdom": "wis", "charisma": "cha"}
SKILLS = {
    "acrobatics": "dex", "animal_handling": "wis", "arcana": "int", "athletics": "str",
    "deception": "cha", "history": "int", "insight": "wis", "intimidation": "cha",
    "investigation": "int", "medicine": "wis", "nature": "int", "perception": "wis",
    "performance": "cha", "persuasion": "cha", "religion": "int", "sleight_of_hand": "dex",
    "stealth": "dex", "survival": "wis",
}
DAMAGE_TYPES = frozenset({
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
    "piercing", "poison", "psychic", "radiant", "slashing", "thunder"})
CONDITIONS = frozenset({
    "blinded", "charmed", "frightened", "grappled", "incapacitated", "invisible",
    "paralyzed", "poisoned", "prone", "restrained", "stunned", "unconscious"})
_INCAPACITATED = frozenset({"incapacitated", "paralyzed", "stunned", "unconscious", "dead"})
_ZERO_SPEED = frozenset({"grappled", "restrained", "paralyzed", "stunned", "unconscious", "dead"})
_AUTO_FAIL_STR_DEX = frozenset({"paralyzed", "stunned", "unconscious"})
_ATTACKER_DISADV = ("blinded", "frightened", "poisoned", "prone", "restrained")
_TARGET_ADV = ("blinded", "paralyzed", "restrained", "stunned", "unconscious")
_COVER = (0, 2, 5)


class RuleError(ValueError):
    """A request the rules refuse. The message is safe to narrate."""


def _rng(rng):
    return rng if rng is not None else secrets.SystemRandom()


# ---------------------------------------------------------------- dice

_TERM = re.compile(r"([+-]?)(\d*)(?:d(\d+)(?:k([hl])(\d+))?)?", re.ASCII)


def parse_formula(formula: str) -> list[dict]:
    """Parse ``NdM[khK|klK]`` terms joined by +/-, plus integer constants.

    Input is capped at 64 characters before any matching, and each term is
    matched once left to right, so parse time is linear in the input.
    """
    if not isinstance(formula, str):
        raise RuleError("Dice formula must be text such as 1d20+3")
    if len(formula) > MAX_FORMULA_LEN:
        raise RuleError(f"Dice formula is longer than {MAX_FORMULA_LEN} characters")
    s = "".join(formula.split()).lower()
    if not s:
        raise RuleError("Dice formula is empty")
    terms, pos, total_dice = [], 0, 0
    while pos < len(s):
        m = _TERM.match(s, pos)
        sign, num, sides, keep, keep_n = m.groups()
        if m.end() == pos or (not num and sides is None):
            raise RuleError(f"Cannot read dice formula near {s[pos:pos + 8]!r}")
        if pos > 0 and not sign:
            raise RuleError(f"Cannot read dice formula near {s[pos:pos + 8]!r}")
        sgn = -1 if sign == "-" else 1
        if sides is None:
            value = int(num)
            if value > MAX_CONSTANT:
                raise RuleError("Constant in dice formula is too large")
            terms.append({"sign": sgn, "const": value})
        else:
            count, nsides = int(num or 1), int(sides)
            if count < 1:
                raise RuleError("A dice term needs at least one die")
            if nsides < 1:
                raise RuleError("A die needs at least one side")
            total_dice += count
            if total_dice > MAX_DICE:
                raise RuleError(f"At most {MAX_DICE} dice per roll")
            if nsides > MAX_SIDES:
                raise RuleError(f"At most {MAX_SIDES} sides per die")
            term = {"sign": sgn, "count": count, "sides": nsides}
            if keep:
                kept = int(keep_n)
                if kept < 1 or kept > count:
                    raise RuleError("Keep count must be between 1 and the number of dice")
                term["keep"] = (keep, kept)
            terms.append(term)
        pos = m.end()
    return terms


def _render(term: dict, crit: bool = False) -> str:
    if "const" in term:
        return str(term["const"])
    count = term["count"] * 2 if crit else term["count"]
    text = f"{count}d{term['sides']}"
    if "keep" in term:
        which, n = term["keep"]
        text += f"k{which}{n * 2 if crit else n}"
    return text


def _join(parts: list[tuple[int, str]]) -> str:
    out = ""
    for i, (sign, text) in enumerate(parts):
        out += ("-" if sign < 0 else "" if i == 0 else "+") + text
    return out


def roll(formula: str, *, rng=None, crit: bool = False) -> dict:
    """Roll a dice formula. ``crit=True`` doubles every die count and nothing else."""
    rng = _rng(rng)
    terms = parse_formula(formula)
    out_terms, all_dice, modifier, total, parts = [], [], 0, 0, []
    for t in terms:
        if "const" in t:
            value = t["sign"] * t["const"]
            modifier += value
            total += value
            parts.append((t["sign"], _render(t)))
            out_terms.append({"term": _render(t), "sign": t["sign"], "subtotal": value})
            continue
        count = t["count"] * 2 if crit else t["count"]
        dice = [rng.randint(1, t["sides"]) for _ in range(count)]
        kept, dropped = dice, []
        if "keep" in t:
            which, n = t["keep"]
            n = n * 2 if crit else n
            order = sorted(range(len(dice)), key=lambda i: dice[i], reverse=(which == "h"))
            keep_idx = set(order[:n])
            kept = [d for i, d in enumerate(dice) if i in keep_idx]
            dropped = [d for i, d in enumerate(dice) if i not in keep_idx]
        subtotal = t["sign"] * sum(kept)
        total += subtotal
        all_dice.extend(dice)
        text = _render(t, crit)
        parts.append((t["sign"], text))
        out_terms.append({"term": text, "sign": t["sign"], "dice": dice, "kept": kept,
                          "dropped": dropped, "subtotal": subtotal})
    return {"formula": _join(parts), "terms": out_terms, "dice": all_dice,
            "modifier": modifier, "total": total}


def average(formula: str) -> float:
    """Expected value of a formula (keep terms use the unreduced pool)."""
    total = 0.0
    for t in parse_formula(formula):
        total += t["sign"] * (t["const"] if "const" in t else t["count"] * (t["sides"] + 1) / 2)
    return total


def d20(*, advantage=False, disadvantage=False, rng=None, lucky=False) -> dict:
    """Roll a d20. Advantage and disadvantage cancel. ``lucky`` rerolls a 1 once per die."""
    rng = _rng(rng)
    mode = "normal"
    if advantage and not disadvantage:
        mode = "advantage"
    elif disadvantage and not advantage:
        mode = "disadvantage"
    dice, rerolled = [], []
    for _ in range(1 if mode == "normal" else 2):
        value = rng.randint(1, 20)
        if lucky and value == 1:
            rerolled.append(1)
            value = rng.randint(1, 20)
        dice.append(value)
    natural = max(dice) if mode == "advantage" else min(dice) if mode == "disadvantage" else dice[0]
    return {"dice": dice, "natural": natural, "total": natural, "mode": mode, "rerolled": rerolled}


# ---------------------------------------------------------------- creature helpers

def mod(score: int) -> int:
    return (score - 10) // 2


def ability_key(name: str) -> str:
    key = str(name).strip().lower()
    key = _ABILITY_NAMES.get(key, key)
    if key not in ABILITIES:
        raise RuleError(f"Unknown ability: {name}")
    return key


def skill_key(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def ability_mod(c: dict, ability: str) -> int:
    return mod(c.get("abilities", {}).get(ability_key(ability), 10))


def _prof(c: dict) -> int:
    return int(c.get("proficiency", 2))


def conditions(c: dict) -> set:
    return set(c.get("conditions", []))


def effects(c: dict) -> dict:
    return c.setdefault("effects", {})


def _traits(c: dict) -> set:
    return set(c.get("traits", []))


def state(c: dict) -> str:
    """One of ok, down, stable, dead."""
    conds = conditions(c)
    if "dead" in conds:
        return "dead"
    if "stable" in conds:
        return "stable"
    return "down" if c.get("hp", 0) <= 0 else "ok"


def can_act(c: dict) -> bool:
    return state(c) == "ok" and not (conditions(c) & _INCAPACITATED)


def effective_ac(c: dict) -> int:
    return c["ac"] + sum(int(e.get("ac", 0)) for e in effects(c).values() if isinstance(e, dict))


def effective_speed(c: dict) -> int:
    conds = conditions(c)
    if conds & _ZERO_SPEED:
        return 0
    cut = sum(int(e.get("speed_penalty", 0)) for e in effects(c).values() if isinstance(e, dict))
    return max(0, int(c.get("speed", 30)) - cut)


def _add_cond(c: dict, name: str) -> bool:
    conds = c.setdefault("conditions", [])
    if name in conds:
        return False
    conds.append(name)
    return True


def _del_cond(c: dict, name: str) -> bool:
    conds = c.get("conditions", [])
    if name not in conds:
        return False
    c["conditions"] = [x for x in conds if x != name]
    return True


def add_condition(c: dict, name: str) -> dict:
    name = str(name).strip().lower()
    if name not in CONDITIONS:
        raise RuleError(f"Unknown condition: {name}")
    notes = []
    if name in (c.get("condition_immune") or []):
        return {"added": False, "conditions": list(c["conditions"]), "notes": [f"{c['name']} is immune to {name}"]}
    added = _add_cond(c, name)
    if added and name == "unconscious":
        _add_cond(c, "prone")
        notes.append("drops what it holds and falls prone")
    if added and name == "unconscious" and c.get("concentration"):
        c["concentration"] = None
        notes.append("concentration ends")
    return {"added": added, "conditions": list(c["conditions"]), "notes": notes}


def remove_condition(c: dict, name: str) -> dict:
    name = str(name).strip().lower()
    removed = _del_cond(c, name)
    if name == "unconscious":
        effects(c).pop("asleep", None)
    if name == "paralyzed":
        effects(c).pop("hold_person", None)
    return {"removed": removed, "conditions": list(c.get("conditions", []))}


def grid_distance(a: dict, b: dict) -> int:
    """Squares between two creatures (diagonals cost one). Without positions: adjacent."""
    pa, pb = a.get("pos"), b.get("pos")
    if not pa or not pb:
        return 1
    return max(abs(pa[0] - pb[0]), abs(pa[1] - pb[1]))


# ---------------------------------------------------------------- checks, saves, skills

def _skill_multiplier(c: dict, skill: str) -> int:
    value = c.get("skills", {}).get(skill)
    return {"proficient": 1, "expertise": 2, 1: 1, 2: 2}.get(value, 0)


def check_bonus(c: dict, name: str) -> tuple[str, int]:
    """(ability, bonus) for an ability name or a skill name."""
    key = str(name).strip().lower()
    if key in ABILITIES or key in _ABILITY_NAMES:
        ab = ability_key(key)
        return ab, ability_mod(c, ab)
    skill = skill_key(key)
    if skill not in SKILLS:
        raise RuleError(f"Unknown ability or skill: {name}")
    ab = SKILLS[skill]
    return ab, ability_mod(c, ab) + _skill_multiplier(c, skill) * _prof(c)


def _bless_roll(c: dict, rng) -> dict | None:
    if "bless" in effects(c):
        return roll("1d4", rng=rng)
    return None


def saving_throw(creature: dict, ability: str, dc: int, *, advantage=False, disadvantage=False,
                 rng=None, cover: int = 0) -> dict:
    rng = _rng(rng)
    ab = ability_key(ability)
    conds = conditions(creature)
    notes = []
    bonus = ability_mod(creature, ab) + (_prof(creature) if ab in creature.get("saves", []) else 0)
    if ab == "dex":
        if cover not in _COVER:
            raise RuleError("Cover must be 0, 2 or 5")
        bonus += cover
        if cover:
            notes.append(f"+{cover} cover")
        if "restrained" in conds:
            disadvantage = True
            notes.append("restrained: disadvantage on Dexterity saves")
    if ab in ("str", "dex") and conds & _AUTO_FAIL_STR_DEX:
        notes.append("automatically fails Strength and Dexterity saves")
        return {"ability": ab, "dc": dc, "natural": None, "bonus": bonus, "total": None,
                "success": False, "auto_fail": True, "dice": [], "mode": "none", "notes": notes}
    d = d20(advantage=advantage, disadvantage=disadvantage, rng=rng, lucky="lucky" in _traits(creature))
    total = d["natural"] + bonus
    blessed = _bless_roll(creature, rng)
    if blessed:
        total += blessed["total"]
        notes.append(f"bless +{blessed['total']}")
    return {"ability": ab, "dc": dc, "natural": d["natural"], "bonus": bonus, "total": total,
            "success": total >= dc, "auto_fail": False, "dice": d["dice"], "mode": d["mode"],
            "notes": notes}


def ability_check(creature: dict, ability_or_skill: str, dc: int | None = None, *, advantage=False,
                  disadvantage=False, rng=None) -> dict:
    rng = _rng(rng)
    ab, bonus = check_bonus(creature, ability_or_skill)
    notes = []
    conds = conditions(creature)
    for cond in ("poisoned", "frightened"):
        if cond in conds:
            disadvantage = True
            notes.append(f"{cond}: disadvantage on ability checks")
    d = d20(advantage=advantage, disadvantage=disadvantage, rng=rng, lucky="lucky" in _traits(creature))
    total = d["natural"] + bonus
    return {"check": str(ability_or_skill).strip().lower(), "ability": ab, "dc": dc,
            "natural": d["natural"], "bonus": bonus, "total": total,
            "success": None if dc is None else total >= dc,
            "dice": d["dice"], "mode": d["mode"], "notes": notes}


def passive_score(creature: dict, skill: str = "perception", *, advantage=False, disadvantage=False) -> int:
    conds = conditions(creature)
    if conds & {"poisoned", "frightened"}:
        disadvantage = True
    _, bonus = check_bonus(creature, skill)
    return 10 + bonus + (5 if advantage and not disadvantage else -5 if disadvantage and not advantage else 0)


def passive_perception(creature: dict) -> int:
    return passive_score(creature, "perception")


# ---------------------------------------------------------------- attacks

def _close(attacker: dict, target: dict, melee: bool) -> bool:
    if melee:
        return True
    return bool(attacker.get("pos") and target.get("pos")) and grid_distance(attacker, target) <= 1


def attack_modifiers(attacker: dict, target: dict, melee: bool = True, *, in_melee: bool = False) -> dict:
    """Advantage, disadvantage and auto-crit that conditions and effects grant an attack."""
    a, t = conditions(attacker), conditions(target)
    adv, dis, notes = [], [], []
    for cond in _ATTACKER_DISADV:
        if cond in a:
            dis.append(f"attacker {cond}")
    if "invisible" in a:
        adv.append("attacker invisible")
    close = _close(attacker, target, melee)
    for cond in _TARGET_ADV:
        if cond in t:
            adv.append(f"target {cond}")
    if "invisible" in t:
        dis.append("target invisible")
    if "prone" in t:
        (adv if close else dis).append("target prone, attacker " + ("within 5 ft." if close else "at range"))
    if "guiding_bolt" in effects(target):
        adv.append("target marked by guiding bolt")
    if not melee and (in_melee or close):
        dis.append("ranged attack with a hostile within 5 ft.")
    auto_crit = close and bool(t & {"paralyzed", "unconscious"})
    if auto_crit:
        notes.append("hits within 5 ft. of a paralyzed or unconscious target are critical hits")
    return {"advantage": bool(adv), "disadvantage": bool(dis), "auto_crit": auto_crit,
            "sources": {"advantage": adv, "disadvantage": dis}, "notes": notes}


def _attack_roll(attacker: dict, target: dict, bonus: int, *, melee, cover, rng, advantage,
                 disadvantage, in_melee, crit_range=20) -> dict:
    if cover not in _COVER:
        raise RuleError("Cover must be 0 (none), 2 (half) or 5 (three-quarters)")
    mods = attack_modifiers(attacker, target, melee, in_melee=in_melee)
    adv = advantage or mods["advantage"]
    dis = disadvantage or mods["disadvantage"]
    d = d20(advantage=adv, disadvantage=dis, rng=rng, lucky="lucky" in _traits(attacker))
    nat = d["natural"]
    notes = list(mods["notes"])
    blessed = _bless_roll(attacker, rng)
    if blessed:
        bonus += blessed["total"]
        notes.append(f"bless +{blessed['total']}")
    ac = effective_ac(target) + cover
    total = nat + bonus
    hit = nat == 20 or (nat != 1 and total >= ac)
    critical = hit and (nat >= crit_range or mods["auto_crit"])
    if "guiding_bolt" in effects(target):
        effects(target).pop("guiding_bolt")
        notes.append("guiding bolt mark consumed")
    return {"hit": hit, "critical": critical, "auto_crit": hit and mods["auto_crit"] and nat < crit_range,
            "roll": d, "bonus": bonus, "total": total, "ac": ac, "mode": d["mode"],
            "notes": notes, "sources": mods["sources"]}


def _damage_block(target: dict, components: list[tuple[dict, str]], notes: list[str]) -> dict:
    """components: (roll, damage type). Returns the damage dict used in results."""
    raw = applied = 0
    for r, dtype in components:
        amount = max(0, r["total"])
        n, nn = mitigate(target, amount, dtype)
        raw += amount
        applied += n
        notes.extend(nn)
    return {"rolls": [r for r, _ in components], "raw": raw, "type": components[0][1] if components else None,
            "types": [dt for _, dt in components], "amounts": [max(0, r["total"]) for r, _ in components],
            "applied": applied, "notes": notes}


def resolve_attack(attacker: dict, target: dict, attack: dict, *, melee: bool = True, cover: int = 0,
                   rng=None, advantage: bool = False, disadvantage: bool = False,
                   ally_adjacent: bool = False, in_melee: bool = False, apply: bool = False) -> dict:
    """Roll one attack. Natural 1 misses, natural 20 hits, a critical doubles damage dice only."""
    rng = _rng(rng)
    if state(target) == "dead":
        raise RuleError(f"{target['name']} is already dead")
    if not can_act(attacker):
        raise RuleError(f"{attacker['name']} cannot attack right now")
    ar = _attack_roll(attacker, target, int(attack["to_hit"]), melee=melee, cover=cover, rng=rng,
                      advantage=advantage, disadvantage=disadvantage, in_melee=in_melee,
                      crit_range=int(attacker.get("crit_range", 20)))
    result = {"hit": ar["hit"], "critical": ar["critical"], "auto_crit": ar["auto_crit"],
              "attack": attack.get("name"), "melee": melee,
              "attack_roll": ar["roll"], "to_hit": ar["total"], "bonus": ar["bonus"], "ac": ar["ac"],
              "notes": ar["notes"], "damage": None, "rider": None}
    notes: list[str] = []
    if ar["hit"]:
        dtype = attack["type"]
        comps = [(roll(attack["damage"], rng=rng, crit=ar["critical"]), dtype)]
        extra = attack.get("extra")
        if extra:
            when = extra.get("when")
            mode = ar["roll"]["mode"]
            if when == "sneak":
                ok = (mode == "advantage" or ally_adjacent) and mode != "disadvantage"
            elif when == "ally_adjacent":
                ok = ally_adjacent
            else:
                ok = True
            if ok:
                comps.append((roll(extra["damage"], rng=rng, crit=ar["critical"]), extra.get("type", dtype)))
                notes.append(f"{when or 'extra'} damage")
        result["damage"] = _damage_block(target, comps, notes)
        rider = attack.get("rider")
        if rider and state(target) != "dead":
            save = saving_throw(target, rider["save"], rider["dc"], rng=rng)
            result["rider"] = {"save": save, "condition": rider["condition"], "applied": False,
                               "triggered": not save["success"]}
    else:
        result["damage"] = {"rolls": [], "raw": 0, "type": attack.get("type"), "types": [], "amounts": [],
                            "applied": 0, "notes": ["miss"]}
    if apply:
        result["outcome"] = apply_attack(target, result, rng=rng)
    return result


def apply_attack(target: dict, result: dict, *, rng=None) -> dict | None:
    """Apply a resolve_attack result: damage (all types in one instance) and any rider condition."""
    out = None
    dmg = result.get("damage")
    if result.get("hit") and dmg and dmg["raw"] > 0:
        out = _apply(target, list(zip(dmg["amounts"], dmg["types"])), result["critical"], rng)
    rider = result.get("rider")
    if rider and rider["triggered"] and state(target) in ("ok",):
        add = add_condition(target, rider["condition"])
        rider["applied"] = add["added"]
    return out


# ---------------------------------------------------------------- damage, healing, death

def mitigate(creature: dict, amount: int, dtype: str) -> tuple[int, list[str]]:
    """Immunity, then resistance (halve, round down), then vulnerability (double)."""
    if dtype not in DAMAGE_TYPES:
        raise RuleError(f"Unknown damage type: {dtype}")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise RuleError("Damage must be a whole number of at least 0")
    notes = []
    if dtype in creature.get("immune", []):
        return 0, [f"immune to {dtype}"]
    n = amount
    if dtype in creature.get("resist", []):
        n //= 2
        notes.append(f"resistant to {dtype}: halved")
    if dtype in creature.get("vuln", []):
        n *= 2
        notes.append(f"vulnerable to {dtype}: doubled")
    return n, notes


def apply_damage(creature: dict, amount: int, dtype: str, *, critical: bool = False, rng=None) -> dict:
    """Apply damage in SRD order. ``amount`` is the rolled damage before resistances."""
    return _apply(creature, [(amount, dtype)], critical, rng)


def _death_state(c: dict, notes: list[str], why: str) -> None:
    _add_cond(c, "dead")
    _del_cond(c, "stable")
    c["hp"] = 0
    if c.get("concentration"):
        c["concentration"] = None
        notes.append("concentration ends")
    notes.append(why)


def _apply(c: dict, comps: list[tuple[int, str]], critical: bool, rng=None) -> dict:
    notes: list[str] = []
    applied = 0
    for amount, dtype in comps:
        n, nn = mitigate(c, amount, dtype)
        applied += n
        notes.extend(nn)
    last_type = comps[-1][1] if comps else None
    if state(c) == "dead":
        return {"applied": 0, "absorbed": 0, "hp_lost": 0, "hp": c["hp"], "temp_hp": c.get("temp_hp", 0),
                "state": "dead", "notes": notes + ["already dead"], "death_saves": dict(c["death_saves"]),
                "concentration_dc": None}
    temp = c.get("temp_hp", 0)
    absorbed = min(temp, applied)
    if absorbed:
        c["temp_hp"] = temp - absorbed
        notes.append(f"temporary hit points absorb {absorbed}")
    rest = applied - absorbed
    saves = c.setdefault("death_saves", {"s": 0, "f": 0})
    max_hp = c["max_hp"]
    if applied > 0 and "asleep" in effects(c):
        effects(c).pop("asleep")
        _del_cond(c, "unconscious")
        notes.append("damage wakes the sleeper")
    if rest > 0:
        hp = c["hp"]
        if hp > 0:
            c["hp"] = max(0, hp - rest)
            overflow = rest - hp
            if c["hp"] > 0:
                pass
            elif c.get("kind") != "pc":
                if "undead_fortitude" in _traits(c) and last_type != "radiant" and not critical:
                    dc = 5 + applied
                    save = saving_throw(c, "con", dc, rng=rng)
                    if save["success"]:
                        c["hp"] = 1
                        notes.append(f"Undead Fortitude (DC {dc}): drops to 1 hit point instead")
                    else:
                        _death_state(c, notes, "slain")
                else:
                    _death_state(c, notes, "slain")
            elif overflow >= max_hp:
                _death_state(c, notes, f"massive damage: {overflow} remaining damage meets the hit point maximum {max_hp}")
            else:
                _add_cond(c, "unconscious")
                _add_cond(c, "prone")
                saves["s"] = saves["f"] = 0
                notes.append("drops to 0 hit points and falls unconscious")
        else:
            if rest >= max_hp:
                _death_state(c, notes, f"massive damage: {rest} damage meets the hit point maximum {max_hp}")
            elif c.get("kind") != "pc":
                _death_state(c, notes, "slain")
            else:
                if _del_cond(c, "stable"):
                    notes.append("no longer stable")
                gain = 2 if critical else 1
                saves["f"] += gain
                notes.append(f"damage at 0 hit points: {gain} death save failure{'s' if gain > 1 else ''}")
                if saves["f"] >= 3:
                    _death_state(c, notes, "three death save failures")
    st = state(c)
    if st in ("down", "dead") and c.get("concentration"):
        c["concentration"] = None
        notes.append("concentration ends")
    conc_dc = max(10, applied // 2) if st == "ok" and c.get("concentration") and applied > 0 else None
    return {"applied": applied, "absorbed": absorbed, "hp_lost": rest, "hp": c["hp"],
            "temp_hp": c.get("temp_hp", 0), "state": st, "notes": notes,
            "death_saves": dict(saves), "concentration_dc": conc_dc}


def heal(creature: dict, amount: int) -> dict:
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise RuleError("Healing must be a whole number of at least 0")
    notes = []
    if state(creature) == "dead":
        return {"healed": 0, "hp": creature["hp"], "temp_hp": creature.get("temp_hp", 0),
                "state": "dead", "notes": ["dead creatures cannot be healed"]}
    before = creature["hp"]
    creature["hp"] = min(creature["max_hp"], before + amount)
    healed = creature["hp"] - before
    if before <= 0 and creature["hp"] > 0:
        _del_cond(creature, "unconscious")
        _del_cond(creature, "stable")
        effects(creature).pop("asleep", None)
        creature["death_saves"] = {"s": 0, "f": 0}
        notes.append("regains consciousness; death saves reset")
    return {"healed": healed, "hp": creature["hp"], "temp_hp": creature.get("temp_hp", 0),
            "state": state(creature), "notes": notes}


def death_save(creature: dict, *, rng=None) -> dict:
    rng = _rng(rng)
    st = state(creature)
    if st == "dead":
        raise RuleError(f"{creature['name']} is dead")
    if st == "stable":
        raise RuleError(f"{creature['name']} is stable and does not roll death saves")
    if st != "down":
        raise RuleError(f"{creature['name']} is not at 0 hit points")
    if creature.get("kind") != "pc":
        raise RuleError(f"{creature['name']} does not make death saving throws")
    saves = creature.setdefault("death_saves", {"s": 0, "f": 0})
    d = d20(rng=rng)
    nat = d["natural"]
    notes = []
    if nat == 20:
        outcome = "critical_success"
        creature["hp"] = 1
        _del_cond(creature, "unconscious")
        saves["s"] = saves["f"] = 0
        notes.append("natural 20: regains 1 hit point and is conscious")
    elif nat == 1:
        outcome = "critical_failure"
        saves["f"] += 2
    elif nat >= 10:
        outcome = "success"
        saves["s"] += 1
    else:
        outcome = "failure"
        saves["f"] += 1
    if outcome != "critical_success":
        if saves["s"] >= 3:
            _add_cond(creature, "stable")
            saves["s"] = saves["f"] = 0
            notes.append("three successes: stable")
        elif saves["f"] >= 3:
            _death_state(creature, notes, "three failures: dead")
    return {"natural": nat, "dice": d["dice"], "outcome": outcome, "success": nat >= 10,
            "successes": saves["s"], "failures": saves["f"], "hp": creature["hp"],
            "state": state(creature), "notes": notes}


# ---------------------------------------------------------------- concentration and effects

def concentration_check(creature: dict, damage: int, *, rng=None, creatures=None) -> dict:
    """Constitution save, DC 10 or half the damage taken, whichever is higher."""
    conc = creature.get("concentration")
    if not conc:
        return {"concentrating": False, "dc": None, "save": None, "broken": False}
    dc = max(10, damage // 2)
    save = saving_throw(creature, "con", dc, rng=rng)
    out = {"concentrating": True, "spell": conc["spell"], "dc": dc, "save": save, "broken": not save["success"]}
    if out["broken"]:
        out["ended"] = break_concentration(creature, creatures)["ended"]
    return out


def break_concentration(creature: dict, creatures=None) -> dict:
    """End concentration and strip the spell's effects from ``creatures``."""
    conc = creature.get("concentration")
    if not conc:
        return {"ended": None}
    ename = conc["spell"].replace(" ", "_")
    for other in list(creatures or []):
        eff = effects(other)
        if ename in eff and eff[ename].get("by") == creature["id"]:
            eff.pop(ename)
            if ename == "hold_person":
                _del_cond(other, "paralyzed")
    creature["concentration"] = None
    return {"ended": conc["spell"]}


def start_turn(creature: dict, creatures=None) -> dict:
    """Expire effects that last until the start of this creature's turn (shield, ray of frost)."""
    notes = []
    for other in list(creatures or [creature]):
        eff = effects(other)
        for name in [n for n, e in eff.items() if isinstance(e, dict) and e.get("until_start_of") == creature["id"]]:
            eff.pop(name)
            notes.append(f"{name} ends on {other['name']}")
    return {"notes": notes}


def end_turn(creature: dict, creatures=None, *, rng=None) -> dict:
    """Expire effects that last until the end of this creature's turn; repeat hold person saves."""
    rng = _rng(rng)
    notes, saves = [], []
    for other in list(creatures or [creature]):
        eff = effects(other)
        for name in [n for n, e in eff.items() if isinstance(e, dict) and e.get("until_end_of") == creature["id"]]:
            eff.pop(name)
            notes.append(f"{name} ends on {other['name']}")
    hold = effects(creature).get("hold_person")
    if hold and "paralyzed" in conditions(creature):
        s = saving_throw(creature, hold["ability"], hold["dc"], rng=rng)
        saves.append(s)
        if s["success"]:
            effects(creature).pop("hold_person")
            _del_cond(creature, "paralyzed")
            notes.append(f"{creature['name']} shakes off hold person")
    return {"notes": notes, "saves": saves}


# ---------------------------------------------------------------- initiative

def _rolloff(members: list[dict], rng, depth: int = 0) -> list[dict]:
    if len(members) <= 1 or depth >= 20:
        return members
    rolls = {m["id"]: rng.randint(1, 20) for m in members}
    out: list[dict] = []
    for value in sorted(set(rolls.values()), reverse=True):
        tied = [m for m in members if rolls[m["id"]] == value]
        out.extend(_rolloff(tied, rng, depth + 1) if len(tied) > 1 else tied)
    return out


def roll_initiative(combatants: list[dict], *, rng=None) -> list[str]:
    """d20 + Dexterity modifier. Ties go to the higher Dexterity score, then a d20 roll-off.

    Each combatant gets its total stored under ``initiative``.
    """
    rng = _rng(rng)
    for c in combatants:
        c["initiative"] = rng.randint(1, 20) + ability_mod(c, "dex")
    groups: dict[tuple[int, int], list[dict]] = {}
    for c in combatants:
        groups.setdefault((c["initiative"], c.get("abilities", {}).get("dex", 10)), []).append(c)
    ordered: list[dict] = []
    for key in sorted(groups, reverse=True):
        ordered.extend(_rolloff(groups[key], rng))
    return [c["id"] for c in ordered]


# ---------------------------------------------------------------- rests

def short_rest(creature: dict, hit_dice: int, *, rng=None) -> dict:
    rng = _rng(rng)
    if state(creature) != "ok":
        raise RuleError(f"{creature['name']} cannot take a short rest while {state(creature)}")
    if not isinstance(hit_dice, int) or isinstance(hit_dice, bool) or hit_dice < 0:
        raise RuleError("Hit dice to spend must be a whole number of at least 0")
    cur, mx, die = creature["hit_dice"]
    n = min(hit_dice, cur)
    notes = []
    if hit_dice > cur:
        notes.append(f"only {cur} hit dice available")
    sides = int(str(die).lstrip("d"))
    con = ability_mod(creature, "con")
    rolls, total = [], 0
    for _ in range(n):
        r = rng.randint(1, sides)
        rolls.append(r)
        total += max(0, r + con)
    before = creature["hp"]
    creature["hp"] = min(creature["max_hp"], before + total)
    creature["hit_dice"] = [cur - n, mx, die]
    return {"spent": n, "rolls": rolls, "con_mod": con, "healed": creature["hp"] - before,
            "hp": creature["hp"], "hit_dice": list(creature["hit_dice"]), "notes": notes}


def long_rest(creature: dict) -> dict:
    if state(creature) == "dead":
        raise RuleError(f"{creature['name']} is dead")
    creature["hp"] = creature["max_hp"]
    creature["temp_hp"] = 0
    for pair in creature.get("slots", {}).values():
        pair[0] = pair[1]
    cur, mx, die = creature["hit_dice"]
    back = max(1, mx // 2)
    creature["hit_dice"] = [min(mx, cur + back), mx, die]
    creature["death_saves"] = {"s": 0, "f": 0}
    creature["concentration"] = None
    creature["effects"] = {}
    for name in ("unconscious", "stable"):
        _del_cond(creature, name)
    return {"hp": creature["hp"], "slots": {k: list(v) for k, v in creature.get("slots", {}).items()},
            "hit_dice": list(creature["hit_dice"]), "hit_dice_regained": creature["hit_dice"][0] - cur,
            "notes": ["fully rested"]}


# ---------------------------------------------------------------- spells

def spell_dc(caster: dict) -> int:
    ab = caster.get("spell_ability")
    if not ab:
        raise RuleError(f"{caster['name']} has no spellcasting ability")
    return 8 + _prof(caster) + ability_mod(caster, ab)


def spell_attack_bonus(caster: dict) -> int:
    ab = caster.get("spell_ability")
    if not ab:
        raise RuleError(f"{caster['name']} has no spellcasting ability")
    return _prof(caster) + ability_mod(caster, ab)


def _spell_key(name: str) -> str:
    return str(name).strip().lower().replace("_", " ").replace("-", " ")


def _tier(level: int) -> int:
    return 4 if level >= 17 else 3 if level >= 11 else 2 if level >= 5 else 1


def _dice_formula(count: int, sides: int, flat: int = 0) -> str:
    return f"{count}d{sides}" + (f"{flat:+d}" if flat else "")


def _entry(target: dict, **kw) -> dict:
    return {"target": target["id"], "name": target["name"], **kw}


def _hit_entry(caster, target, sp, formula, rng, *, in_melee) -> dict:
    ar = _attack_roll(caster, target, spell_attack_bonus(caster), melee=False,
                      cover=target.get("cover", 0), rng=rng, advantage=False, disadvantage=False,
                      in_melee=in_melee)
    entry = _entry(target, hit=ar["hit"], critical=ar["critical"], attack_roll=ar["roll"],
                   to_hit=ar["total"], ac=ar["ac"], notes=ar["notes"], damage=None)
    if ar["hit"]:
        r = roll(formula, rng=rng, crit=ar["critical"])
        out = _apply(target, [(max(0, r["total"]), sp["dtype"])], ar["critical"], rng)
        entry["damage"] = {"rolls": [r], "raw": max(0, r["total"]), "type": sp["dtype"], **out}
        entry["state"] = out["state"]
        entry["hp"] = out["hp"]
        if sp.get("marks"):
            effects(target)["guiding_bolt"] = {"by": caster["id"], "until_end_of": caster["id"]}
            entry["notes"].append("next attack against the target has advantage")
        if sp.get("slows"):
            effects(target)["slowed"] = {"by": caster["id"], "speed_penalty": sp["slows"],
                                         "until_start_of": caster["id"]}
            entry["notes"].append(f"speed reduced by {sp['slows']} ft.")
    return entry


def _alloc(targets: list[dict], n: int, what: str) -> list[dict]:
    """One target per dart or ray when the counts match, otherwise round-robin."""
    if len(targets) > n:
        raise RuleError(f"{n} {what} cannot cover {len(targets)} targets")
    return list(targets) if len(targets) == n else [targets[i % len(targets)] for i in range(n)]


def cast(caster: dict, spell_name: str, targets: list[dict], *, slot_level: int | None = None,
         rng=None, in_melee: bool = False, creatures=None) -> dict:
    """Cast an SRD spell: spend the slot, roll, apply results to ``targets``.

    Raises RuleError (before anything changes) for unknown or unprepared spells,
    missing slots, an incapacitated caster or an invalid target list.
    """
    rng = _rng(rng)
    key = _spell_key(spell_name)
    sp = srd.SPELLS.get(key)
    if sp is None:
        raise RuleError(f"Unknown spell: {spell_name}")
    if not can_act(caster):
        raise RuleError(f"{caster['name']} cannot cast right now")
    if key not in {_spell_key(s) for s in caster.get("spells", [])}:
        raise RuleError(f"{caster['name']} does not have {sp['name']} prepared")
    level = sp["level"]
    slot = None
    if level > 0:
        slot = slot_level or level
        if slot < level or slot > 9:
            raise RuleError(f"{sp['name']} needs a slot of level {level} or higher")
        pair = caster.get("slots", {}).get(str(slot))
        if not pair or pair[0] <= 0:
            raise RuleError(f"{caster['name']} has no level {slot} spell slot left")
    up = (slot - level) if slot else 0
    kind = sp["kind"]
    targets = list(targets or [])
    if kind != "self" and not targets:
        raise RuleError(f"{sp['name']} needs at least one target")
    cap = None
    if "max_targets" in sp:
        cap = sp["max_targets"] + sp.get("targets_per_level", 0) * up
    if cap is not None and len(targets) > cap:
        raise RuleError(f"{sp['name']} can target at most {cap} creature{'s' if cap != 1 else ''}")
    if kind in ("attack", "rays", "save", "hold", "heal") and not caster.get("spell_ability"):
        raise RuleError(f"{caster['name']} has no spellcasting ability")

    # validated: commit
    ended = None
    if sp["concentration"] and caster.get("concentration"):
        ended = break_concentration(caster, list(creatures or []) + targets + [caster])["ended"]
    if slot:
        caster["slots"][str(slot)][0] -= 1
    notes: list[str] = []
    results: list[dict] = []
    cl = int(caster.get("level", 1))

    if kind == "attack":
        count = _tier(cl) * sp["dice"][0] if sp.get("cantrip_scaling") else sp["dice"][0] + sp.get("per_level", (0, 0))[0] * up
        formula = _dice_formula(count, sp["dice"][1])
        results = [_hit_entry(caster, t, sp, formula, rng, in_melee=in_melee) for t in targets]
    elif kind == "rays":
        n = sp["count"] + sp["count_per_level"] * up
        formula = _dice_formula(*sp["dice"])
        results = [_hit_entry(caster, t, sp, formula, rng, in_melee=in_melee) for t in _alloc(targets, n, "rays")]
        notes.append(f"{n} rays")
    elif kind == "darts":
        n = sp["count"] + sp["count_per_level"] * up
        formula = _dice_formula(sp["dice"][0], sp["dice"][1], sp["flat"])
        for t in _alloc(targets, n, "darts"):
            if state(t) == "dead":
                results.append(_entry(t, damage=None, notes=["already dead"]))
            elif "shield" in effects(t):
                results.append(_entry(t, damage={"rolls": [], "raw": 0, "applied": 0, "type": "force"},
                                      notes=["shield negates magic missile"]))
            else:
                r = roll(formula, rng=rng)
                out = _apply(t, [(max(0, r["total"]), "force")], False, rng)
                results.append(_entry(t, damage={"rolls": [r], "raw": r["total"], "type": "force", **out},
                                    notes=[], state=out["state"], hp=out["hp"]))
        notes.append(f"{n} darts")
    elif kind == "save":
        count = _tier(cl) * sp["dice"][0] if sp.get("cantrip_scaling") else sp["dice"][0] + sp["per_level"][0] * up
        r = roll(_dice_formula(count, sp["dice"][1]), rng=rng)
        dc = spell_dc(caster)
        for t in targets:
            if state(t) == "dead":
                results.append(_entry(t, save=None, damage=None, notes=["already dead"]))
                continue
            cover = 0 if sp.get("ignores_cover") or sp["save"] != "dex" else t.get("cover", 0)
            save = saving_throw(t, sp["save"], dc, rng=rng, cover=cover)
            raw = max(0, r["total"])
            amount = 0 if save["success"] and not sp["half"] else raw // 2 if save["success"] else raw
            out = _apply(t, [(amount, sp["dtype"])], False, rng)
            e = _entry(t, save=save, damage={"rolls": [r], "raw": amount, "type": sp["dtype"], **out},
                       state=out["state"], hp=out["hp"], notes=[])
            if sp.get("push") and not save["success"]:
                e["push"] = sp["push"]
                e["notes"].append(f"pushed {sp['push']} ft.")
            results.append(e)
        notes.append(f"save DC {dc}")
    elif kind == "self":
        effects(caster)["shield"] = {"ac": sp["ac_bonus"], "until_start_of": caster["id"]}
        results = [_entry(caster, ac=effective_ac(caster), notes=[f"+{sp['ac_bonus']} AC until the start of your next turn"])]
    elif kind == "heal":
        spell_mod = ability_mod(caster, caster["spell_ability"])
        count = sp["dice"][0] + sp["per_level"][0] * up
        for t in targets:
            if t.get("type") in ("undead", "construct"):
                results.append(_entry(t, healed=0, notes=[f"{sp['name']} has no effect on {t['type']} creatures"]))
                continue
            r = roll(f"{count}d{sp['dice'][1]}", rng=rng)
            bonus = 0
            if "disciple_of_life" in _traits(caster):
                bonus = 2 + slot
            amount = max(0, r["total"] + spell_mod + bonus)
            out = heal(t, amount)
            note = [f"disciple of life +{bonus}"] if bonus else []
            results.append(_entry(t, rolls=[r], bonus=spell_mod + bonus, amount=amount,
                                  **{**out, "notes": out["notes"] + note}))
    elif kind == "buff":
        for t in targets:
            if state(t) == "dead":
                results.append(_entry(t, affected=False, notes=["already dead"]))
                continue
            effects(t)[sp["effect"]] = {"by": caster["id"]}
            results.append(_entry(t, affected=True, notes=[f"{sp['name']}: +1d4 to attack rolls and saving throws"]))
    elif kind == "hold":
        dc = spell_dc(caster)
        for t in targets:
            if t.get("type") != "humanoid":
                results.append(_entry(t, affected=False, save=None, notes=["not a humanoid"]))
                continue
            if state(t) == "dead":
                results.append(_entry(t, affected=False, save=None, notes=["already dead"]))
                continue
            save = saving_throw(t, sp["save"], dc, rng=rng)
            if not save["success"]:
                _add_cond(t, "paralyzed")
                effects(t)["hold_person"] = {"by": caster["id"], "dc": dc, "ability": sp["save"]}
            results.append(_entry(t, affected=not save["success"], save=save,
                                  notes=[] if save["success"] else ["paralyzed"]))
        notes.append(f"save DC {dc}")
    elif kind == "sleep":
        pool_roll = roll(_dice_formula(sp["dice"][0] + sp["per_level"][0] * up, sp["dice"][1]), rng=rng)
        remaining = pool_roll["total"]
        notes.append(f"{pool_roll['total']} hit points of creatures affected")
        order = sorted(enumerate(targets), key=lambda p: (p[1]["hp"], p[0]))
        by_index = {}
        stop = False
        for idx, t in order:
            tr = _traits(t)
            if state(t) != "ok" or "unconscious" in conditions(t):
                by_index[idx] = _entry(t, affected=False, notes=["already unconscious or down"])
            elif t.get("type") == "undead" or "fey_ancestry" in tr or "immune_charm" in tr or "charmed" in (t.get("condition_immune") or []):
                by_index[idx] = _entry(t, affected=False, notes=["immune to sleep"])
            elif stop or t["hp"] > remaining:
                stop = True
                by_index[idx] = _entry(t, affected=False, notes=["too many hit points for the remaining total"])
            else:
                remaining -= t["hp"]
                add_condition(t, "unconscious")
                effects(t)["asleep"] = {"by": caster["id"]}
                by_index[idx] = _entry(t, affected=True, notes=["falls asleep"])
        results = [by_index[i] for i in range(len(targets))]
        notes.append(f"{remaining} left over")
    else:  # pragma: no cover - data guard
        raise RuleError(f"Spell kind not supported: {kind}")

    if sp["concentration"]:
        caster["concentration"] = {"spell": key, "targets": [t["id"] for t in targets], "slot": slot}
    return {"spell": sp["name"], "key": key, "slot_used": slot, "results": results, "notes": notes,
            "concentration": caster.get("concentration"), "ended_concentration": ended,
            "slots": {k: list(v) for k, v in caster.get("slots", {}).items()}}


# ---------------------------------------------------------------- monster tactics

def _cells(creatures: list[dict], skip: dict) -> dict:
    return {tuple(c["pos"]): c for c in creatures if c.get("pos") and c is not skip and state(c) != "dead"}


def _reachable(m: dict, creatures: list[dict], squares: int) -> dict:
    """Cells the monster can end a move on, with step counts. Allies can be crossed, enemies cannot."""
    occupied = _cells(creatures, m)
    start = tuple(m["pos"])
    seen = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        steps = seen[(x, y)]
        if steps >= squares:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nxt = (x + dx, y + dy)
                if (dx, dy) == (0, 0) or nxt in seen or not (0 <= nxt[0] < GRID_W and 0 <= nxt[1] < GRID_H):
                    continue
                blocker = occupied.get(nxt)
                if blocker is not None and blocker.get("kind") != m.get("kind"):
                    continue
                seen[nxt] = steps + 1
                queue.append(nxt)
    return {c: s for c, s in seen.items() if c == start or c not in occupied}


def _sq(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _best_attack(m: dict, dist: int):
    """(attack, melee) usable at ``dist`` squares: melee first, then ranged, highest average damage."""
    melee = [a for a in m.get("attacks", []) if a.get("reach") and dist * 5 <= a["reach"]]
    if melee:
        return max(melee, key=lambda a: average(a["damage"])), True
    ranged = [a for a in m.get("attacks", []) if a.get("range") and dist * 5 <= a["range"][1]]
    if ranged:
        return max(ranged, key=lambda a: average(a["damage"])), False
    return None, None


def _target_key(t: dict):
    return (effective_ac(t), t.get("hp", 0), t["id"])


def monster_action(monster: dict, combatants: list[dict], *, rng=None, apply: bool = False) -> dict:
    """Deterministic monster turn.

    Flee at 25% hit points (goblins, kobolds) when it gains distance. Otherwise attack the
    lowest-AC conscious PC in melee reach. If none, close on the nearest PC when its movement
    gets a melee attack in reach, else shoot it if a ranged attack reaches, else move closer.
    Pack tactics and martial advantage use the positions of living, able allies. Without
    positions every creature counts as adjacent.
    """
    rng = _rng(rng)
    if not can_act(monster):
        return {"action": "none", "target": None, "reason": f"{monster['name']} cannot act"}
    foes = [c for c in combatants if c.get("kind") != monster.get("kind") and state(c) != "dead"]
    awake = [c for c in foes if state(c) == "ok" and "unconscious" not in conditions(c)]
    pool = awake or foes
    if not pool:
        return {"action": "none", "target": None, "reason": "no targets"}
    has_pos = bool(monster.get("pos"))

    if "flees_at_quarter_hp" in _traits(monster) and monster["hp"] * 4 <= monster["max_hp"] and has_pos and awake:
        cells = _reachable(monster, combatants, max(1, effective_speed(monster) * 2 // 5))
        def safety(cell):
            return min(_sq(cell, f["pos"]) for f in awake if f.get("pos")) if any(f.get("pos") for f in awake) else 0
        here = safety(tuple(monster["pos"]))
        best = max(cells, key=lambda c: (safety(c), -cells[c], -c[0], -c[1]))
        if safety(best) > here:
            nearest = min(awake, key=lambda f: (grid_distance(monster, f), f["id"]))
            out = {"action": "flee", "target": None,
                   "flee": {"from": list(monster["pos"]), "to": list(best), "squares": cells[best],
                            "away_from": nearest["id"], "dash": True}}
            if apply:
                monster["pos"] = list(best)
            return out

    def in_reach(t):
        atk, melee = _best_attack(monster, grid_distance(monster, t))
        return atk is not None and melee

    reachable_foes = [t for t in pool if in_reach(t)]
    move = None
    if reachable_foes:
        target = min(reachable_foes, key=_target_key)
    else:
        target = min(pool, key=lambda t: (grid_distance(monster, t), _target_key(t)))
        if has_pos and target.get("pos"):
            cells = _reachable(monster, combatants, max(0, effective_speed(monster) // 5))
            reach_sq = max([a["reach"] // 5 for a in monster.get("attacks", []) if a.get("reach")] or [0])
            near = [c for c in cells if reach_sq and _sq(c, target["pos"]) <= reach_sq]
            dest = None
            if near:
                dest = min(near, key=lambda c: (cells[c], c))
            elif _best_attack(monster, grid_distance(monster, target))[0] is None:
                dest = min(cells, key=lambda c: (_sq(c, target["pos"]), cells[c], c))
            if dest is not None and dest != tuple(monster["pos"]):
                move = {"from": list(monster["pos"]), "to": list(dest), "squares": cells[dest]}
    final_pos = move["to"] if move else monster.get("pos")
    probe = {**monster, "pos": final_pos}
    dist = grid_distance(probe, target)
    atk, melee = _best_attack(monster, dist)
    if atk is None:
        if move and apply:
            monster["pos"] = list(move["to"])
        return {"action": "move" if move else "none", "target": target["id"], "move": move,
                **({} if move else {"reason": "target out of range"})}

    allies = [c for c in combatants if c is not monster and c.get("kind") == monster.get("kind")
              and can_act(c) and c.get("pos") and target.get("pos") and _sq(c["pos"], target["pos"]) <= 1]
    ally_adjacent = bool(allies) if target.get("pos") else False
    adv = "pack_tactics" in _traits(monster) and ally_adjacent
    hostile_adjacent = (not melee) and any(
        (f.get("pos") and final_pos and _sq(f["pos"], final_pos) <= 1) for f in awake)
    names = None
    multi = monster.get("multiattack")
    if multi:
        names = multi["melee"] if melee else multi.get("ranged")
    sequence = ([next(a for a in monster["attacks"] if a["name"] == n) for n in names] if names else [atk])
    if apply and move:
        monster["pos"] = list(move["to"])
    attacks, outcomes = [], []
    for a in sequence:
        if apply and (state(target) != "ok" and attacks):
            break
        res = resolve_attack(probe, target, a, melee=melee, rng=rng, advantage=adv,
                             ally_adjacent=ally_adjacent, in_melee=hostile_adjacent, apply=apply)
        attacks.append(res)
        if apply:
            outcomes.append(res["outcome"])
    out = {"action": "attack", "target": target["id"], "attack": attacks[0], "attacks": attacks,
           "melee": bool(melee), "move": move, "pack_tactics": adv}
    if apply:
        out["outcomes"] = outcomes
    return out
