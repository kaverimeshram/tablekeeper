"""Hermes tabletop campaign plugin. Rules and state remain code-authoritative."""
from __future__ import annotations

import json
import re
import threading

from . import rules, store

LOCK = threading.RLock()
DB = None
IDENTITIES = {}
TURN_NUMBERS = {}
MONSTERS = {
    "goblin": (15, 7, 2, "1d6+2", 30), "wolf": (11, 13, 4, "2d4+2", 40),
    "skeleton": (13, 13, 4, "1d6+2", 40), "orc": (15, 13, 5, "1d12+3", 30),
    "bandit": (11, 11, 3, "1d6+1", 30), "giant rat": (7, 12, 4, "1d4+2", 30),
    "ogre": (59, 11, 6, "2d8+4", 40),
}
CHARACTERS = {
    "fighter": {"name": "Fighter", "hp": 28, "max_hp": 28, "ac": 18, "attack": 5, "damage": "1d8+3", "damage_type": "slashing", "level": 3, "slots": {}, "inventory": ["chain mail", "shield", "longsword", "shortbow", "20 arrows"], "modifiers": {"str": 3, "dex": 1, "con": 2, "int": 0, "wis": 0, "cha": 0}, "hit_dice": 3, "hit_die": 10},
    "rogue": {"name": "Rogue", "hp": 24, "max_hp": 24, "ac": 15, "attack": 5, "damage": "1d8+3", "damage_type": "piercing", "level": 3, "slots": {}, "inventory": ["leather armor", "rapier", "shortbow", "20 arrows", "thieves' tools"], "modifiers": {"str": 0, "dex": 3, "con": 2, "int": 1, "wis": 1, "cha": 0}, "hit_dice": 3, "hit_die": 8},
    "wizard": {"name": "Wizard", "hp": 17, "max_hp": 17, "ac": 12, "attack": 5, "damage": "1d10", "level": 3, "slots": {1: 4, 2: 2}, "inventory": ["spellbook", "quarterstaff", "component pouch"], "modifiers": {"str": -1, "dex": 2, "con": 1, "int": 3, "wis": 1, "cha": 0}, "hit_dice": 3, "hit_die": 6},
}
VULNERABILITIES = {"skeleton": ["bludgeoning"]}
SPELLS = {"fire bolt": ("attack", "1d10", 0), "magic missile": ("auto", "3d4+3", 1),
          "cure wounds": ("heal", "1d8+3", 1), "shield": ("condition", "shield", 1),
          "sleep": ("save", "5d8", 1)}


def _env(name):
    from gateway.session_context import get_session_env
    return str(get_session_env("HERMES_SESSION_" + name, "") or "").strip()


def _identity():
    platform = _env("PLATFORM") or "cli"
    chat = _env("CHAT_ID") or _env("KEY") or _env("ID") or "local"
    user = _env("ACTOR_ID") or _env("USER_ID")
    if platform in {"cli", "tui", "desktop", "local"} and not user:
        user = "local-owner"
    return f"{platform}:{chat}", user


def _state():
    chat, _ = _identity()
    return chat, store.load(DB, chat)


def _owned(state, name, user):
    character = state["characters"].get(name.lower())
    if not character:
        raise ValueError("Unknown character; use tk_claim_character")
    if not user or character["owner"] != user:
        raise PermissionError("Only the character's owner may act for it")
    return character


def _turn(state, name):
    order = state["initiative"]
    if order and (state["turn"] >= len(order) or order[state["turn"]]["name"] != name):
        raise PermissionError("It is not that character's turn")


def _result(chat, state, payload):
    store.save(DB, chat, state)
    return payload


def _snapshot():
    chat, s = _state()
    return s


def _claim(character: str):
    chat, user = _identity()
    if not user:
        raise PermissionError("Sender identity unavailable")
    key = character.lower().strip()
    if key not in CHARACTERS:
        raise ValueError("Choose fighter, rogue, or wizard")
    with LOCK:
        chat, s = _state()
        if key in s["characters"]:
            raise ValueError("Character already claimed")
        s["characters"][key] = {**CHARACTERS[key], "owner": user, "conditions": [], "death_successes": 0, "death_failures": 0}
        return _result(chat, s, {"claimed": key, "owner": user})


def _roll(formula: str, why: str = "general roll"):
    chat, s = _state(); result = rules.roll(formula)
    record = {**result, "who": _identity()[1], "why": why}
    s["rolls"].append(record); return _result(chat, s, record)


def _check(character: str, ability: str, dc: int, advantage: bool = False, disadvantage: bool = False):
    chat, user = _identity(); _, s = _state(); c = _owned(s, character, user); _turn(s, character.lower())
    d = rules.d20(advantage=advantage, disadvantage=disadvantage)
    result = {"character": character, "ability": ability, **d, "modifier": c.get("modifiers", {}).get(ability, 0), "dc": int(dc)}
    result["total"] += result["modifier"]; result["success"] = result["total"] >= int(dc)
    s["rolls"].append({"formula": "1d20", "dice": d["dice"], "modifier": result["modifier"], "total": result["total"], "who": user, "why": f"{ability} check"}); return _result(chat, s, result)


def _attack(character: str, target: str, advantage: bool = False, disadvantage: bool = False):
    chat, user = _identity(); _, s = _state(); c = _owned(s, character, user); _turn(s, character.lower())
    foe = next((m for m in s["monsters"] if m["name"].lower() == target.lower() and m["hp"] > 0), None)
    if foe is None: raise ValueError("Target is not a living campaign monster")
    d = rules.d20(advantage=advantage, disadvantage=disadvantage)
    hit = rules.attack_bonus(d, c["attack"], foe["ac"], c["damage"])
    if hit["hit"]:
        damage_type = c.get("damage_type", "slashing")
        amount = rules.adjust_damage(hit["damage"]["total"], resistance=damage_type in foe.get("resistances", []), vulnerability=damage_type in foe.get("vulnerabilities", []))
        foe["hp"] = max(0, foe["hp"] - amount)
        hit["damage"]["adjusted"] = amount
    s["rolls"].append({"formula": c["damage"] if hit["hit"] else "1d20", "dice": hit["damage"]["dice"] if hit["hit"] else d["dice"], "modifier": c["attack"] if not hit["critical"] else 0, "total": hit["damage"]["total"] if hit["hit"] else hit["total"], "who": user, "why": f"{character} attacks {target}", "attack": hit})
    return _result(chat, s, hit | {"target_hp": foe["hp"]})


def _damage(character: str, amount: int, heal: bool = False):
    chat, user = _identity(); _, s = _state(); c = _owned(s, character, user); _turn(s, character.lower())
    amount = max(0, int(amount)); c["hp"] = min(c["max_hp"], c["hp"] + amount) if heal else max(0, c["hp"] - amount)
    return _result(chat, s, {"character": character, "hp": c["hp"], "amount": amount, "healed": bool(heal)})


def _cast(character: str, spell: str, target: str = ""):
    chat, user = _identity(); _, s = _state(); c = _owned(s, character, user); _turn(s, character.lower())
    key = spell.lower(); spec = SPELLS.get(key)
    if not spec: raise ValueError("Unknown spell")
    if key != "fire bolt":
        level = spec[2]; slots = c.get("slots", {})
        if slots.get(level, 0) < 1: raise ValueError("No spell slot available")
        slots[level] -= 1
    mode, formula, _ = spec
    if mode == "heal":
        amount = rules.roll(formula)["total"]; c["hp"] = min(c["max_hp"], c["hp"] + amount); result = {"spell": key, "healed": amount, "hp": c["hp"]}
    elif mode == "condition":
        c.setdefault("conditions", []).append("shield"); result = {"spell": key, "condition": "shield", "duration": "until start of next turn"}
    elif mode in {"auto", "save", "attack"}:
        amount = rules.roll(formula)["total"]; foe = next((m for m in s["monsters"] if m["name"].lower() == target.lower() and m["hp"] > 0), None)
        if not foe: raise ValueError("Choose a living monster target")
        if mode == "attack":
            d = rules.d20(); attack = {"natural": d["natural"], "total": d["total"] + c.get("spell_attack", 5), "dice": d["dice"]}
            if d["natural"] == 1 or (d["natural"] != 20 and attack["total"] < foe["ac"]): amount = 0
            if d["natural"] == 20: amount = rules.roll("2d10")["total"]
            result = {"spell": key, "attack": attack, "hit": amount > 0, "damage": amount}
        else:
            result = {"spell": key, "damage": amount}
        foe["hp"] = max(0, foe["hp"] - amount); result = {"spell": key, "damage": amount, "target": target, "target_hp": foe["hp"]}
    else:
        result = {"spell": key, "effect": "attack roll required", "formula": formula}
    return _result(chat, s, result)


def _start_combat(monsters: str):
    chat, user = _identity(); _, s = _state()
    names = [x.strip().lower() for x in monsters.split(",") if x.strip()]
    if not names or any(x not in MONSTERS for x in names): raise ValueError("Monsters must be selected from the built-in bestiary")
    s["monsters"] = [{"name": n.title(), "hp": MONSTERS[n][0], "max_hp": MONSTERS[n][0], "ac": MONSTERS[n][1], "attack": MONSTERS[n][2], "damage": MONSTERS[n][3], "speed": MONSTERS[n][4], "vulnerabilities": VULNERABILITIES.get(n, []), "resistances": []} for n in names]
    order = []
    for name, c in s["characters"].items(): order.append({"name": name, "initiative": rules.d20()["total"] + c.get("initiative", 0), "monster": False})
    for m in s["monsters"]: order.append({"name": m["name"], "initiative": rules.d20()["total"], "monster": True})
    s["initiative"] = sorted(order, key=lambda x: x["initiative"], reverse=True); s["round"] = 1; s["turn"] = 0
    return _result(chat, s, {"initiative": s["initiative"], "round": 1, "current": s["initiative"][0] if order else None})


def _next():
    chat, s = _state()
    if not s["initiative"]: raise ValueError("Combat has not started")
    s["turn"] += 1
    if s["turn"] >= len(s["initiative"]): s["turn"] = 0; s["round"] += 1
    return _result(chat, s, {"round": s["round"], "current": s["initiative"][s["turn"]]})


def _monster_turn(*, rng=None):
    chat, s = _state()
    if not s["initiative"]: raise ValueError("Combat has not started")
    turn = s["initiative"][s["turn"]]
    if not turn["monster"]: raise PermissionError("It is a player character's turn")
    m = next((m for m in s["monsters"] if m["name"] == turn["name"] and m["hp"] > 0), None)
    targets = sorted((c for c in s["characters"].values() if c["hp"] > 0), key=lambda c: c["name"])
    if not m or not targets: raise ValueError("No living monster or player target")
    target = targets[0]; d = rules.d20(rng=rng); hit = rules.attack_bonus(d, m["attack"], target["ac"], m["damage"], rng=rng)
    if hit["hit"]: target["hp"] = max(0, target["hp"] - hit["damage"]["total"])
    s["rolls"].append({"formula": m["damage"] if hit["hit"] else "1d20", "dice": hit["damage"]["dice"] if hit["hit"] else d["dice"], "modifier": m["attack"] if not hit["critical"] else 0, "total": hit["damage"]["total"] if hit["hit"] else hit["total"], "who": m["name"], "why": f"{m['name']} attacks {target['name']}", "attack": hit})
    return _result(chat, s, {"monster": m["name"], "target": target["name"], "hit": hit["hit"], "damage": hit.get("damage", {}).get("total", 0), "target_hp": target["hp"]})


def _rest(kind: str):
    chat, s = _state(); _, user = _identity()
    if kind.lower() != "short": raise ValueError("Only short rests are supported")
    for name, c in s["characters"].items():
        if c["owner"] == user:
            if c["hp"] < c["max_hp"] and c["hit_dice"] > 0:
                amount = max(0, rules.roll(f"1d{c['hit_die']}")["total"] + c["modifiers"].get("con", 0))
                c["hp"] = min(c["max_hp"], c["hp"] + amount); c["hit_dice"] -= 1
    return _result(chat, s, {"rest": "short", "characters": s["characters"]})


def _condition(character: str, condition: str, remove: bool = False):
    chat, user = _identity(); _, s = _state(); c = _owned(s, character, user); _turn(s, character.lower())
    allowed = {"prone", "poisoned", "frightened", "restrained", "unconscious"}
    condition = condition.lower()
    if condition not in allowed: raise ValueError("Unsupported condition")
    if remove:
        c["conditions"] = [x for x in c.get("conditions", []) if x != condition]
    elif condition not in c.setdefault("conditions", []):
        c["conditions"].append(condition)
    return _result(chat, s, {"character": character, "conditions": c["conditions"]})


def _death_save(character: str):
    chat, user = _identity(); _, s = _state(); c = _owned(s, character, user); _turn(s, character.lower())
    if c["hp"] != 0: raise ValueError("Death saves are only made at 0 HP")
    result = rules.d20(); nat = result["natural"]
    successes, failures, outcome = rules.death_save(c["death_successes"], c["death_failures"], nat)
    c["death_successes"], c["death_failures"] = successes, failures
    if outcome == "stable": c["stable"] = True
    if nat == 20: c["hp"] = 1
    if outcome == "dead": c["dead"] = True
    record = {"formula": "1d20", "dice": result["dice"], "modifier": 0, "total": nat, "who": user, "why": f"{character} death save"}
    s["rolls"].append(record)
    return _result(chat, s, {"dice": result["dice"], "successes": successes, "failures": failures, "outcome": outcome})


def _map():
    chat, s = _state(); glyph = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    units = list(s["characters"].values()) + s["monsters"]
    return "\n".join("".join(glyph[(r * 5 + c) % 26] if (r * 5 + c) < len(units) else "." for c in range(5)) for r in range(max(1, (len(units) + 4) // 5))) + "\n" + " ".join(f"{glyph[i]}={x['name']} HP {x['hp']}" for i, x in enumerate(units))


def _command(raw_args: str, *, session_id="", source=None, platform="", **kwargs):
    args = raw_args.strip().split(maxsplit=1); sub = args[0].lower() if args else "status"
    if sub == "map": return _map()
    if sub == "claim" and len(args) > 1: return json.dumps(_claim(args[1]), ensure_ascii=False)
    if sub == "new":
        chat, _ = _identity(); store.save(DB, chat, {"characters": {}, "monsters": [], "initiative": [], "round": 0, "turn": 0, "rolls": [], "log": []}); return "Campaign created. Claim a fighter, rogue, or wizard."
    chat, state = _state()
    if sub == "log": return json.dumps(state["rolls"][-10:], ensure_ascii=False)
    if sub == "recap": return json.dumps({"round": state["round"], "initiative": state["initiative"], "characters": state["characters"], "monsters": state["monsters"]}, ensure_ascii=False)
    return json.dumps({"chat": chat, "round": state["round"], "current": state["initiative"][state["turn"]] if state["initiative"] else None, "characters": state["characters"], "monsters": state["monsters"]}, ensure_ascii=False)


def _post_tool_call(tool_name: str = "", result: str = "", **kwargs):
    if not tool_name.startswith("tk_"):
        return
    session = _env("ID")
    if not session:
        return
    try:
        payload = json.loads(result) if isinstance(result, str) else result
    except (json.JSONDecodeError, TypeError):
        payload = result
    numbers = set()
    def collect(value, key=""):
        if isinstance(value, dict):
            for child_key, child in value.items(): collect(child, child_key.lower())
        elif isinstance(value, list):
            for child in value: collect(child, key)
        elif key in {"hp", "target_hp", "damage", "damage_applied", "amount", "total"} and isinstance(value, (int, float)):
            numbers.add(int(value))
    collect(payload)
    with LOCK:
        TURN_NUMBERS.setdefault(session, set()).update(numbers)


def _guard(response_text: str = "", session_id: str = "", **kwargs):
    """Flag concrete combat claims that conflict with the latest authoritative snapshot."""
    chat, state = _state()
    dead = {m["name"].lower() for m in state["monsters"] if m["hp"] == 0}
    for name in dead:
        if re.search(rf"\b{re.escape(name)}\b.{{0,50}}\b(attacks?|strikes?|moves?|acts?)\b", response_text, re.I):
            return response_text + f"\n\n[Tablekeeper: {name.title()} has 0 HP and cannot act.]"
    recorded = TURN_NUMBERS.get(session_id or _env("ID"), set())
    state_numbers = {int(c.get("hp", 0)) for c in state["characters"].values()} | {int(m.get("hp", 0)) for m in state["monsters"]}
    unsupported = sorted({int(n) for n in re.findall(r"\b(\d+)\s*(?:HP|hit points|damage)\b", response_text, re.I) if int(n) not in recorded | state_numbers})
    if unsupported:
        return response_text + "\n\n[Tablekeeper: The HP or damage figure in this narration was not produced by a tool this turn. Check tk_state and the latest tool result.]"
    return response_text


def register(ctx):
    global DB
    from plugins.plugin_storage import plugin_data_dir
    DB = store.connect(plugin_data_dir("tablekeeper") / "campaigns.sqlite3")
    schema = lambda **props: {"type": "object", "properties": props, "required": list(props)}
    string = lambda description: {"type": "string", "description": description}
    integer = lambda description: {"type": "integer", "description": description}
    boolean = {"type": "boolean"}
    tools = [
        ("tk_state", "Read authoritative campaign state", {"type": "object", "properties": {}}, _snapshot),
        ("tk_roll", "Roll real dice", schema(formula=string("Dice expression"), why=string("Reason")), _roll),
        ("tk_check", "Resolve ability check", schema(character=string("Character"), ability=string("Ability"), dc=integer("Difficulty"), advantage=boolean, disadvantage=boolean), _check),
        ("tk_attack", "Attack a monster", schema(character=string("Character"), target=string("Monster"), advantage=boolean, disadvantage=boolean), _attack),
        ("tk_cast", "Cast an available spell", schema(character=string("Character"), spell=string("Spell"), target=string("Target")), _cast),
        ("tk_damage", "Apply damage or healing to an owned character", schema(character=string("Character"), amount=integer("Hit points"), heal=boolean), _damage),
        ("tk_start_combat", "Start combat with named bestiary monsters", schema(monsters=string("Comma separated bestiary names")), _start_combat),
        ("tk_next_turn", "Advance initiative", {"type":"object","properties":{}}, _next),
        ("tk_monster_turn", "Run the active monster's deterministic target selection and attack", {"type":"object","properties":{}}, _monster_turn),
        ("tk_rest", "Take a short rest", schema(kind=string("short")), _rest),
        ("tk_condition", "Apply or remove a supported condition", schema(character=string("Character"), condition=string("Condition name"), remove=boolean), _condition),
        ("tk_death_save", "Roll a death saving throw at 0 HP", schema(character=string("Character")), _death_save),
        ("tk_claim_character", "Claim a level 3 pregenerated character", schema(character=string("fighter, rogue, or wizard")), _claim),
    ]
    for name, description, tool_schema, handler in tools:
        ctx.register_tool(name=name, toolset="tablekeeper", description=description, schema=tool_schema, handler=handler)
    ctx.register_hook("pre_llm_call", lambda **kw: {"context": "Tablekeeper state is authoritative. Narrate only outcomes returned by Tablekeeper tools; do not invent rolls, damage, or hit points.\n" + json.dumps(_snapshot(), ensure_ascii=False)})
    ctx.register_hook("pre_llm_call", lambda session_id="", **kw: TURN_NUMBERS.pop(session_id, None))
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("transform_llm_output", _guard, hold_stream=True)
    ctx.register_command("table", _command, description="Show or manage the Tablekeeper campaign", args_hint="status|map|log|recap|claim <character>|new")
