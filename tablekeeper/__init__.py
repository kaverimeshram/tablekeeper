"""Tablekeeper: code-authoritative tabletop campaigns for Hermes chats.

Python owns dice, hit points, positions, initiative and turn order. The model narrates the
structured results the tk_ tools return. Identity comes from the gateway turn context
(``get_session_env``): a character acts only for its owner, and in combat only on its turn.
"""
from __future__ import annotations

import json
import re
import threading

from gateway.session_context import get_session_env
from plugins.plugin_storage import plugin_data_dir

from . import rules, srd, store

LOCK = threading.RLock()
RNG = None  # tests inject a seeded random.Random; None means the rules module's secure default
GRID_W, GRID_H, FEET = rules.GRID_W, rules.GRID_H, 5
LOCAL_SURFACES = {"", "cli", "tui", "desktop", "local", "acp"}
CONTEXT_CHARS = 2200  # about 600 tokens of compact text
MAX_MONSTERS = 12
_DBS: dict[str, object] = {}
_TURNS: dict[str, dict] = {}
_PLAYING: dict[str, None] = {}  # local sessions that used a tk_ tool or /table; only they get the state block
# ponytail: in memory, so a resumed CLI session gets the state block again after its first tk_ call or /table use


class Refusal(Exception):
    """A rule the table enforces, returned to the model as an explicit result to narrate."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


# ---------------------------------------------------------------- identity

def _identity(source=None, platform: str = "") -> dict:
    """Who is speaking and in which chat: the gateway turn context, or the command's source."""
    if source is not None:
        platform = str(getattr(getattr(source, "platform", ""), "value", getattr(source, "platform", "")) or "")
        chat_id, user = str(getattr(source, "chat_id", "") or ""), str(getattr(source, "user_id", "") or "")
        name = str(getattr(source, "user_name", "") or user)
    else:
        platform = platform or get_session_env("HERMES_SESSION_PLATFORM")
        chat_id = get_session_env("HERMES_SESSION_CHAT_ID")
        user = get_session_env("HERMES_SESSION_ACTOR_ID") or get_session_env("HERMES_SESSION_USER_ID")
        name = get_session_env("HERMES_SESSION_ACTOR_NAME") or get_session_env("HERMES_SESSION_USER_NAME") or user
    platform = platform.strip().lower()
    if platform in LOCAL_SURFACES and not (platform == "" and (chat_id or user)):
        return {"chat": "local:table", "user": "local", "name": "local", "local": True}
    if not chat_id or not user:
        raise Refusal("identity_unavailable", "The sender could not be identified, so no character can act. "
                      "Tell the player Tablekeeper needs a message from an identified user.")
    return {"chat": f"{platform or 'unknown'}:{chat_id}", "user": user, "name": name, "local": False}


def _is_gm(camp: dict, who: dict) -> bool:
    return who["local"] or camp["gm"] == who["user"]


def _need_gm(camp: dict, who: dict, what: str) -> None:
    if not _is_gm(camp, who):
        raise Refusal("gm_only", f"Only the game master (the player who started the campaign) can {what}.")


# ---------------------------------------------------------------- campaign access

def _db():
    path = str(plugin_data_dir("tablekeeper") / "campaigns.sqlite3")
    if path not in _DBS:
        _DBS[path] = store.connect(path)
    return _DBS[path]


def close() -> None:
    """Drop cached connections (profile switch, or a restart in tests)."""
    for db in _DBS.values():
        db.close()
    _DBS.clear()


def _load(who: dict, *, required: bool = True) -> dict | None:
    camp = store.load(_db(), who["chat"])
    if camp is None:
        if required:
            raise Refusal("no_campaign", "There is no campaign in this chat. Call tk_new_campaign first.")
        return None
    camp["_rolls"], camp["_log"] = [], []
    return camp


def _save(camp: dict) -> None:
    for c in camp["creatures"]:
        c["status"] = rules.state(c)
    store.save(_db(), camp, rolls=camp.pop("_rolls"), log=camp.pop("_log"))


def _log(camp: dict, kind: str, text: str) -> None:
    camp["_log"].append((kind, text))


def _by_id(camp: dict) -> dict:
    return {c["id"]: c for c in camp["creatures"]}


def _slug(text) -> str:
    """Lowercase letters and digits only, so 'Goblin 1', 'goblin-1' and 'goblin1' are one reference."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _find(camp: dict, ref, *, kind: str | None = None) -> dict:
    ref = _slug(ref)
    pool = [c for c in camp["creatures"] if kind in (None, c["kind"])]
    hits = [c for c in pool if ref in (_slug(c["id"]), _slug(c["name"]))]
    if not hits and ref:
        hits = [c for c in pool if _slug(c["name"]).startswith(ref) or _slug(c["id"]).startswith(ref)]
        hits = [c for c in hits if not _dead(c)] or hits
    if len(hits) != 1:
        names = ", ".join(c["id"] for c in (hits or pool)) or "none yet"
        raise Refusal("unknown_target" if not hits else "ambiguous_target",
                      f"{'No creature matches' if not hits else 'More than one creature matches'} {ref!r}. "
                      f"Use one of these ids: {names}.")
    return hits[0]


def _dead(c: dict) -> bool:
    return rules.state(c) == "dead"


# ---------------------------------------------------------------- grid

def _dist(a: dict, b: dict) -> int:
    return FEET * rules.grid_distance(a, b)


def _occupied(camp: dict, pos, skip: str = "") -> bool:
    return any(c["id"] != skip and not _dead(c) and list(c["pos"]) == list(pos) for c in camp["creatures"])


def _on_grid(x: int, y: int) -> None:
    if not (0 <= x < GRID_W and 0 <= y < GRID_H):
        raise Refusal("off_grid", f"The grid is {GRID_W} columns (x 0-{GRID_W - 1}) by {GRID_H} rows (y 0-{GRID_H - 1}).")


def _spawn_pos(camp: dict, side: str, want=None) -> list[int]:
    if want is not None:
        _on_grid(*want)
        if _occupied(camp, want):
            raise Refusal("occupied", f"Square ({want[0]},{want[1]}) is occupied.")
        return list(want)
    columns = range(0, 3) if side == "pc" else range(GRID_W - 1, GRID_W - 4, -1)
    for x in columns:
        for y in sorted(range(GRID_H), key=lambda y: abs(y - GRID_H // 2)):
            if not _occupied(camp, (x, y)):
                return [x, y]
    raise Refusal("grid_full", "No free square is left on that side of the grid.")


def _nearest_free(camp: dict, anchor) -> list[int]:
    """The free square closest to anchor (ties go to the lower row, then column)."""
    _on_grid(*anchor)
    squares = sorted(((x, y) for x in range(GRID_W) for y in range(GRID_H) if not _occupied(camp, (x, y))),
                     key=lambda p: (max(abs(p[0] - anchor[0]), abs(p[1] - anchor[1])), p[1], p[0]))
    if not squares:
        raise Refusal("grid_full", "No free square is left on the grid.")
    return list(squares[0])


def _hostile(a: dict, b: dict) -> bool:
    return a["kind"] != b["kind"]


def _engaged(camp: dict, c: dict) -> list[dict]:
    """Conscious hostile creatures within 5 ft of c."""
    return [o for o in camp["creatures"] if o is not c and _hostile(c, o) and rules.can_act(o) and _dist(c, o) <= FEET]


def _reach(c: dict) -> int:
    return max([a.get("reach") or 0 for a in c["attacks"]] + [FEET])


def _speed_left(c: dict) -> int:
    return max(0, rules.effective_speed(c) - c["turn"]["moved"])


def _walk(camp: dict, c: dict, dest) -> dict:
    """Move c to dest if its speed allows. Returns {from, to, feet, left_reach_of}; raises Refusal."""
    x, y = dest
    _on_grid(x, y)
    if _occupied(camp, dest, c["id"]):
        raise Refusal("occupied", f"Square ({x},{y}) is occupied.")
    origin = list(c["pos"])
    feet = FEET * max(abs(origin[0] - x), abs(origin[1] - y))
    cost = feet * 2 if "prone" in c["conditions"] else feet  # crawling
    if cost > _speed_left(c):
        raise Refusal("too_far", f"{c['name']} has {_speed_left(c)} ft of movement left; that move costs {cost} ft.",
                      movement_left=_speed_left(c), cost=cost)
    watchers = _engaged(camp, c)
    c["pos"], c["turn"]["moved"] = [x, y], c["turn"]["moved"] + cost
    left = [o["id"] for o in watchers if _dist(c, o) > _reach(o) and not o["turn"]["reaction"]]
    return {"from": origin, "to": [x, y], "feet": feet, "left_reach_of": left}


# ---------------------------------------------------------------- dice records

def _rec(camp: dict, c, kind: str, why: str, *, dice, total, modifier=0, formula="1d20", **extra) -> None:
    """Append one roll to the campaign's dice tray."""
    camp["_rolls"].append({"who": c["id"] if c else "", "name": c["name"] if c else "", "kind": kind, "why": why,
                           "round": camp["round"], "dice": list(dice), "total": total, "modifier": modifier,
                           "formula": formula, **extra})


def _rec_roll(camp: dict, c, kind: str, why: str, rolled: dict, **extra) -> None:
    _rec(camp, c, kind, why, dice=rolled["dice"], total=rolled["total"], modifier=rolled["modifier"],
         formula=rolled["formula"], **extra)


def _rec_d20(camp: dict, c, kind: str, why: str, d: dict, bonus: int, total, **extra) -> None:
    _rec(camp, c, kind, why, dice=d["dice"], total=total, modifier=bonus, formula=f"1d20{bonus:+d}",
         natural=d["natural"], **extra)


def _rec_save(camp: dict, c, why: str, s: dict, **extra) -> None:
    if s["total"] is not None:
        _rec_d20(camp, c, "save", why, s, s["bonus"], s["total"], dc=s["dc"], success=s["success"], **extra)


def _new_turn() -> dict:
    return {"action": False, "bonus": False, "reaction": False, "moved": 0}


def _brief(c: dict) -> dict:
    keys = ("id", "name", "kind", "owner", "hp", "max_hp", "temp_hp", "ac", "pos", "status", "conditions", "speed")
    return {**{k: c[k] for k in keys}, "status": rules.state(c)}


# ---------------------------------------------------------------- attacks and damage

def _concentration(camp: dict, c: dict, damage: int) -> dict | None:
    if damage <= 0 or not c["concentration"]:
        return None
    check = rules.concentration_check(c, damage, rng=RNG, creatures=camp["creatures"])
    _rec_save(camp, c, f"concentration on {check['spell']}", check["save"])
    if check["broken"]:
        _log(camp, "concentration", f"{c['name']} loses concentration on {check['spell']}.")
    return {"spell": check["spell"], "dc": check["dc"], "total": check["save"]["total"], "kept": not check["broken"]}


def _outcome(camp: dict) -> str | None:
    if not any(c["kind"] == "monster" and not _dead(c) for c in camp["creatures"]):
        return "victory"
    if not any(c["kind"] == "pc" and not _dead(c) for c in camp["creatures"]):
        return "defeat"
    return None


def _finish(camp: dict, outcome: str) -> dict:
    xp = sum(c.get("xp", 0) for c in camp["creatures"] if c["kind"] == "monster") if outcome == "victory" else 0
    camp["in_combat"], camp["active"], camp["initiative"] = False, "", []
    for c in camp["creatures"]:
        c["turn"] = _new_turn()
        c["effects"] = {}
    _log(camp, "combat", f"Combat over: {outcome}." + (f" The party earns {xp} XP." if xp else ""))
    return {"outcome": outcome, "xp": xp}


def _close_if_over(camp: dict) -> dict:
    done = _outcome(camp) if camp["in_combat"] else None
    return {"combat_over": _finish(camp, done)} if done else {}


def _report_attack(camp: dict, att: dict, tgt: dict, atk: dict, res: dict, dist: int) -> dict:
    d = res["attack_roll"]
    _rec_d20(camp, att, "attack", f"{atk['name']} vs {tgt['name']}", d, res["bonus"], res["to_hit"], hit=res["hit"],
             crit=res["critical"], target=tgt["id"], dc=res["ac"])
    out = {"attacker": att["id"], "target": tgt["id"], "attack": atk["name"], "melee": res["melee"], "distance_ft": dist,
           "natural": d["natural"], "attack_total": res["to_hit"], "target_ac": res["ac"], "hit": res["hit"],
           "critical": res["critical"], "notes": list(res["notes"])}
    outcome = res.get("outcome")
    if res["hit"]:
        for r, dtype in zip(res["damage"]["rolls"], res["damage"]["types"]):
            _rec_roll(camp, att, "damage", f"{atk['name']} damage", r, type=dtype, crit=res["critical"], target=tgt["id"])
        out.update(damage=outcome["applied"], damage_type=res["damage"]["type"], hp=tgt["hp"], temp_hp=tgt["temp_hp"],
                   target_state=rules.state(tgt))
        out["notes"] += res["damage"]["notes"] + outcome["notes"]
        conc = _concentration(camp, tgt, outcome["applied"])
        if conc:
            out["concentration"] = conc
        rider = res.get("rider")
        if rider and rider["triggered"]:
            out["rider"] = {"condition": rider["condition"], "applied": rider["applied"]}
            _rec_save(camp, tgt, f"{rider['condition']} rider", rider["save"])
    _log(camp, "attack", f"{att['name']} {'hits' if res['hit'] else 'misses'} {tgt['name']} with {atk['name']}"
         + (f" for {out['damage']} {out['damage_type']}{' (critical)' if res['critical'] else ''}; "
            f"{tgt['name']} {tgt['hp']}/{tgt['max_hp']} HP" if res["hit"] else "") + ".")
    return out


def _strike(camp: dict, att: dict, tgt: dict, atk: dict, *, melee: bool, dist: int, advantage=False,
            disadvantage=False, cover=0) -> dict:
    ally = any(o is not att and o["kind"] == att["kind"] and rules.can_act(o) and _dist(o, tgt) <= FEET
               for o in camp["creatures"])
    res = rules.resolve_attack(att, tgt, atk, melee=melee, cover=cover, rng=RNG, advantage=advantage,
                               disadvantage=disadvantage, ally_adjacent=ally, in_melee=bool(_engaged(camp, att)), apply=True)
    return _report_attack(camp, att, tgt, atk, res, dist)


# ---------------------------------------------------------------- monster and turn flow

def _monster_turn(camp: dict, m: dict) -> dict:
    ids = _by_id(camp)
    act = rules.monster_action(m, camp["creatures"], rng=RNG, apply=True)
    report = {"monster": m["id"], "name": m["name"], "action": act["action"]}
    if act["action"] == "none":
        report["reason"] = act.get("reason", "")
        _log(camp, "turn", f"{m['name']} does nothing: {report['reason']}.")
    elif act["action"] == "flee":
        report["flee"] = act["flee"]
        _log(camp, "move", f"{m['name']} flees to ({act['flee']['to'][0]},{act['flee']['to'][1]}).")
    else:
        if act.get("move"):
            report["move"] = act["move"]
            _log(camp, "move", f"{m['name']} moves to ({act['move']['to'][0]},{act['move']['to'][1]}).")
        if act["action"] == "attack":
            tgt, report["attacks"] = ids[act["target"]], []
            for res, outcome in zip(act["attacks"], act["outcomes"]):
                res["outcome"] = outcome
                atk = next(a for a in m["attacks"] if a["name"] == res["attack"])
                report["attacks"].append(_report_attack(camp, m, tgt, atk, res, _dist(m, tgt)))
    return report


def _start_turn(camp: dict, c: dict) -> None:
    camp["active"], c["turn"] = c["id"], _new_turn()
    for note in rules.start_turn(c, camp["creatures"])["notes"]:
        _log(camp, "effect", note)


def _advance(camp: dict) -> dict | None:
    """Make the next creature that can take a turn the active one. The round ticks at the top of the order."""
    ids, order = _by_id(camp), camp["initiative"]
    i = order.index(camp["active"]) if camp["active"] in order else -1
    for _ in range(len(order)):
        i += 1
        if i >= len(order):
            i, camp["round"] = 0, camp["round"] + 1
        c = ids[order[i]]
        if rules.state(c) in ("dead", "stable"):
            continue
        _start_turn(camp, c)
        return c
    return None


def _end_turn_effects(camp: dict, c: dict) -> None:
    res = rules.end_turn(c, camp["creatures"], rng=RNG)
    for note in res["notes"]:
        _log(camp, "effect", note)
    for s in res["saves"]:
        _rec_save(camp, c, "repeat save", s)


def _run_monsters(camp: dict) -> dict:
    """Play monster turns until a player character can act (or combat ends). Returns narration data."""
    ids, turns = _by_id(camp), []
    for _ in range(4 * max(1, len(camp["initiative"]))):
        c = ids[camp["active"]]
        if c["kind"] == "pc" and rules.state(c) == "down":
            return {"monster_turns": turns, "needs_death_save": c["id"]}
        if c["kind"] == "pc" and rules.can_act(c):
            return {"monster_turns": turns}
        if c["kind"] == "monster" and rules.can_act(c):
            turns.append(_monster_turn(camp, c))
        else:
            _log(camp, "turn", f"{c['name']} cannot act this turn.")
            turns.append({"creature": c["id"], "name": c["name"], "action": "none", "reason": "incapacitated"})
        _end_turn_effects(camp, c)
        done = _outcome(camp)
        if done:
            return {"monster_turns": turns, "combat_over": _finish(camp, done)}
        _advance(camp)
    return {"monster_turns": turns}


def _end_turn(camp: dict) -> dict:
    cur = _by_id(camp)[camp["active"]]
    _log(camp, "turn", f"{cur['name']} ends their turn.")
    _end_turn_effects(camp, cur)
    _advance(camp)
    flow = _run_monsters(camp)
    active = _by_id(camp).get(camp["active"])
    return {"round": camp["round"], "active": _brief(active) if active else None, **flow}


# ---------------------------------------------------------------- tool plumbing

def _ok(**fields) -> dict:
    return {"ok": True, **fields}


# argument names a model reaches for when the schema is a tool_search away; the canonical name wins when both appear
ALIASES = {"attacker": "character", "actor": "character", "caster": "character", "attack_name": "attack",
           "weapon": "attack", "spell_name": "spell", "targets_ids": "targets", "creature": "target"}


def _canonical(args: dict) -> dict:
    return {**{ALIASES[k]: v for k, v in args.items() if k in ALIASES and ALIASES[k] not in args}, **args}


def _tool(fn):
    """Serialise a tool body and return rule refusals and bad input as explicit JSON results."""
    def handler(args, **_ctx):
        try:
            with LOCK:
                result = fn(_canonical(args) if isinstance(args, dict) else {})
        except Refusal as r:
            result = {"ok": False, "refused": r.code, "message": r.message, **r.extra}
        except rules.RuleError as e:
            result = {"ok": False, "refused": "invalid_input", "message": str(e)}
        return json.dumps(result, ensure_ascii=False, default=str)
    handler.__name__ = fn.__name__
    return handler


def _text(args: dict, key: str, *, required: bool = True, limit: int = 200) -> str:
    value = args.get(key)
    if value is None or str(value).strip() == "":
        if required:
            raise Refusal("invalid_input", f"{key} is required.")
        return ""
    return str(value).strip()[:limit]


def _int(args: dict, key: str, default=None, lo=-1000, hi=1000) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or value is None or not isinstance(value, (int, float, str)):
        raise Refusal("invalid_input", f"{key} must be a whole number.")
    try:
        number = int(value)
    except ValueError:
        raise Refusal("invalid_input", f"{key} must be a whole number.") from None
    if not lo <= number <= hi:
        raise Refusal("invalid_input", f"{key} must be between {lo} and {hi}.")
    return number


def _default_ref(camp: dict, who: dict, ref):
    """A blank character reference means the sender's only character."""
    if str(ref or "").strip():
        return ref
    mine = [c["id"] for c in camp["creatures"] if c["kind"] == "pc" and (who["local"] or c["owner"] == who["user"])]
    if len(mine) != 1:
        raise Refusal("invalid_input", "character is required: " + (f"choose one of {', '.join(mine)}." if mine else
                      "the sender has no character yet; claim one with tk_claim_character."))
    return mine[0]


def _owned(camp: dict, who: dict, ref) -> dict:
    c = _find(camp, _default_ref(camp, who, ref), kind="pc")
    if not (who["local"] or c["owner"] == who["user"]):
        raise Refusal("not_owner", f"{c['name']} belongs to another player. Only their owner can act for them.")
    return c


def _acting(camp: dict, who: dict, ref, *, cost: str | None = None) -> dict:
    """The character `who` may act for right now, or a Refusal the model must narrate."""
    c = _owned(camp, who, ref)
    if camp["in_combat"] and camp["active"] != c["id"]:
        active = _by_id(camp)[camp["active"]]
        raise Refusal("not_your_turn", f"It is {active['name']}'s turn, not {c['name']}'s.", active=active["id"])
    if rules.state(c) == "down":
        raise Refusal("cannot_act", f"{c['name']} is at 0 HP. Use tk_death_save on their turn.")
    if not rules.can_act(c):
        raise Refusal("cannot_act", f"{c['name']} cannot act ({rules.state(c)}; "
                      f"{', '.join(c['conditions']) or 'no conditions'}).")
    if not camp["in_combat"]:
        c["turn"] = _new_turn()
    if cost and c["turn"][cost]:
        raise Refusal("action_used", f"{c['name']} already used their {cost} this turn. End the turn with tk_next_turn.")
    return c


def _spend(camp: dict, c: dict, cost: str) -> None:
    if camp["in_combat"]:
        c["turn"][cost] = True


# ---------------------------------------------------------------- campaign

def _new_campaign(who: dict, scene: str, replace: bool) -> dict:
    old = store.load(_db(), who["chat"])
    if old is not None and (old["creatures"] or old["in_combat"]):
        _need_gm(old, who, "replace this campaign")
        if not replace:
            raise Refusal("campaign_exists", "A campaign with characters already runs in this chat, so it was left untouched. "
                          "Keep playing it with tk_state, tk_claim_character and tk_start_combat. Only if the player "
                          "explicitly asked to wipe it and start over, call again with replace=true.")
    camp = store.create(_db(), who["chat"], who["user"])
    camp["_rolls"], camp["_log"], camp["scene"] = [], [], scene
    _log(camp, "campaign", f"{who['name']} started a campaign." + (f" Scene: {scene}" if scene else ""))
    _save(camp)
    return _ok(chat=who["chat"], game_master=who["user"], scene=scene)


@_tool
def tk_new_campaign(args):
    scene = _text(args, "scene", required=False, limit=500) or _text(args, "description", required=False, limit=500) \
        or _text(args, "name", required=False, limit=500)
    return _new_campaign(_identity(), scene, bool(args.get("replace")))


def _claim(camp: dict, who: dict, key: str) -> dict:
    key = next((k for k, v in srd.CHARACTERS.items() if key.lower().strip() in (k, v["name"].lower())), None)
    if key is None:
        raise Refusal("unknown_character", f"Choose one of: {', '.join(srd.CHARACTERS)}.")
    if camp["in_combat"]:
        raise Refusal("combat_running", "Characters can join between fights, not during one.")
    if any(c["id"] == key for c in camp["creatures"]):
        raise Refusal("already_claimed", f"{srd.CHARACTERS[key]['name']} is already claimed.")
    if not who["local"] and any(c["kind"] == "pc" and c["owner"] == who["user"] for c in camp["creatures"]):
        raise Refusal("one_character", "Each player claims one character.")
    c = srd.new_character(key, owner=who["user"], pos=_spawn_pos(camp, "pc"))
    c.update(status="ok", turn=_new_turn())
    camp["creatures"].append(c)
    _log(camp, "claim", f"{who['name']} claimed {c['name']}.")
    return _brief(c)


@_tool
def tk_claim_character(args):
    who = _identity()
    camp = _load(who)
    claimed = _claim(camp, who, _text(args, "character"))
    _save(camp)
    return _ok(character=claimed)


def _state(camp: dict, who: dict) -> dict:
    mine = [c["id"] for c in camp["creatures"] if c["kind"] == "pc" and (who["local"] or c["owner"] == who["user"])]
    return {"chat": camp["chat"], "scene": camp["scene"], "round": camp["round"], "in_combat": camp["in_combat"],
            "active": camp["active"], "initiative": camp["initiative"], "you_control": mine,
            "you_are_game_master": _is_gm(camp, who),
            "grid": {"width": GRID_W, "height": GRID_H, "feet_per_square": FEET},
            "creatures": [{**_brief(c), "attacks": [a["name"] for a in c["attacks"]], "spells": c["spells"],
                           "slots": c["slots"], "concentration": c["concentration"], "effects": c["effects"],
                           "death_saves": c["death_saves"], "turn": c["turn"]} for c in camp["creatures"]]}


@_tool
def tk_state(args):
    who = _identity()
    camp = _load(who, required=False)
    if camp is None:
        return _ok(campaign=None, hint="No campaign in this chat. Call tk_new_campaign to start one.")
    return _ok(**_state(camp, who))


@_tool
def tk_roll(args):
    """Plain dice for the table. Never changes hit points or positions."""
    who = _identity()
    rolled = rules.roll(_text(args, "formula", limit=64), rng=RNG)
    why = _text(args, "why", required=False)
    camp = _load(who, required=False)
    if camp is not None:
        _rec_roll(camp, None, "roll", why or "roll", rolled, by=who["name"])
        _save(camp)
    return _ok(**rolled, why=why)


def _roll_result(camp: dict, c: dict, kind: str, label: str, res: dict) -> dict:
    if res["total"] is not None:
        _rec_d20(camp, c, kind, label, res, res["bonus"], res["total"], dc=res["dc"], success=res["success"])
    versus = f" vs DC {res['dc']}: {'success' if res['success'] else 'failure'}" if res["dc"] else ""
    _log(camp, kind, f"{c['name']} {label} {res['total']}{versus}.")
    return _ok(character=c["id"], **res)


def _not_down(c: dict) -> None:
    if rules.state(c) == "down":
        raise Refusal("cannot_act", f"{c['name']} is at 0 HP and unconscious. Their roll is a death saving throw: "
                      "call tk_death_save on their turn; checks and saves do not apply.")


@_tool
def tk_check(args):
    who = _identity()
    camp = _load(who)
    c = _owned(camp, who, args.get("character"))
    _not_down(c)
    dc = _int(args, "dc", None, 1, 40) if args.get("dc") is not None else None
    res = rules.ability_check(c, _text(args, "skill_or_ability"), dc, advantage=bool(args.get("advantage")),
                              disadvantage=bool(args.get("disadvantage")), rng=RNG)
    out = _roll_result(camp, c, "check", f"{res['check']} check", res)
    _save(camp)
    return out


@_tool
def tk_save(args):
    who = _identity()
    camp = _load(who)
    c = _owned(camp, who, args.get("character"))
    _not_down(c)
    res = rules.saving_throw(c, _text(args, "ability"), _int(args, "dc", None, 1, 40),
                             advantage=bool(args.get("advantage")), disadvantage=bool(args.get("disadvantage")), rng=RNG)
    out = _roll_result(camp, c, "save", f"{res['ability']} save", res)
    _save(camp)
    return out


@_tool
def tk_attack(args):
    who = _identity()
    camp = _load(who)
    att = _acting(camp, who, args.get("character"), cost="action")
    tgt = _find(camp, args.get("target"))
    if not _hostile(att, tgt):
        raise Refusal("friendly_target", "Attacks target enemies. The game master rules harm to allies with tk_damage.")
    if _dead(tgt):
        raise Refusal("invalid_target", f"{tgt['name']} is already dead.")
    name = _slug(_text(args, "attack", required=False) or _text(args, "name", required=False))
    dist = _dist(att, tgt)
    options = ", ".join(f"{a['name']} ({'melee ' + str(a['reach']) + ' ft' if a.get('reach') else 'ranged ' + str(a['range'][1]) + ' ft'})"
                        for a in att["attacks"])
    if name:
        atk = next((a for a in att["attacks"] if _slug(a["name"]) == name), None) \
            or next((a for a in att["attacks"] if name in _slug(a["name"])), None)
    else:  # no weapon named: the first attack that reaches the target, else the first
        atk = next((a for a in att["attacks"] if dist <= (a.get("reach") or 0) or dist <= (a["range"][1] if a.get("range") else 0)),
                   att["attacks"][0])
    if atk is None:
        raise Refusal("unknown_attack", f"{att['name']} can attack with: {options}.")
    reach = atk.get("reach")
    normal, longest = atk["range"] if atk.get("range") else (0, 0)
    melee = bool(reach) and dist <= reach
    if not melee and not (longest and dist <= longest):
        raise Refusal("out_of_range", f"{tgt['name']} is {dist} ft from {att['name']}; {atk['name']} reaches "
                      f"{reach or longest} ft. Attacks: {options}. Use tk_move first, or name another attack.", distance_ft=dist)
    res = _strike(camp, att, tgt, atk, melee=melee, dist=dist, advantage=bool(args.get("advantage")),
                  disadvantage=bool(args.get("disadvantage")) or (not melee and dist > normal),
                  cover=_int(args, "cover", 0, 0, 5))
    _spend(camp, att, "action")
    extra = _close_if_over(camp)
    _save(camp)
    return _ok(**res, **extra)


def _destination(camp: dict, c: dict, args: dict) -> list[int]:
    """x,y (or a to=[x,y] pair), or the free square within reach of the movement left that is closest to `toward`."""
    to = args.get("to") or args.get("position")
    if isinstance(to, (list, tuple)) and len(to) == 2 and "x" not in args:
        args = {**args, "x": to[0], "y": to[1]}
    if args.get("toward") and "x" not in args:
        goal = _find(camp, args["toward"])
        if goal is c:
            raise Refusal("invalid_input", f"{c['name']} cannot move toward themselves.")
        left = _speed_left(c) // (2 * FEET if "prone" in c["conditions"] else FEET)
        ring = [(x, y) for x in range(GRID_W) for y in range(GRID_H)
                if max(abs(x - c["pos"][0]), abs(y - c["pos"][1])) <= left and not _occupied(camp, (x, y), c["id"])]
        if not ring:
            raise Refusal("too_far", f"{c['name']} has no movement left.", movement_left=_speed_left(c))
        return list(min(ring, key=lambda p: (max(abs(p[0] - goal["pos"][0]), abs(p[1] - goal["pos"][1])),
                                             max(abs(p[0] - c["pos"][0]), abs(p[1] - c["pos"][1])), p[1], p[0])))
    return [_int(args, "x", None, 0, GRID_W - 1), _int(args, "y", None, 0, GRID_H - 1)]


@_tool
def tk_move(args):
    who = _identity()
    camp = _load(who)
    c = _acting(camp, who, args.get("character"))
    disengage = bool(args.get("disengage")) and camp["in_combat"]
    if disengage and c["turn"]["action"]:
        raise Refusal("action_used", f"{c['name']} already used their action this turn.")
    mv = _walk(camp, c, _destination(camp, c, args))
    if disengage:
        c["turn"]["action"] = True
    _log(camp, "move", f"{c['name']} moves to ({mv['to'][0]},{mv['to'][1]}).")
    ids, reactions = _by_id(camp), []
    if camp["in_combat"] and not disengage:
        for oid in mv["left_reach_of"]:
            foe = ids[oid]
            melee_attacks = [a for a in foe["attacks"] if a.get("reach")]
            if foe["kind"] == "monster" and melee_attacks:
                foe["turn"]["reaction"] = True
                reactions.append(_strike(camp, foe, c, melee_attacks[0], melee=True, dist=min(_reach(foe), _dist(foe, c))))
    extra = _close_if_over(camp)
    _save(camp)
    return _ok(character=c["id"], **mv, movement_left=_speed_left(c), opportunity_attacks=reactions, **extra)


def _targets(camp: dict, args: dict) -> list[dict]:
    refs = args.get("targets") or []
    refs = [r.strip() for r in refs.split(",")] if isinstance(refs, str) else refs
    if not isinstance(refs, list) or len(refs) > 12:
        raise Refusal("invalid_input", "targets must be a list of up to 12 creature ids.")
    return [_find(camp, r) for r in refs if str(r).strip()]


def _parts(results: list[dict]):
    """Per-ray and per-dart entries when a spell merged them, else the entries themselves."""
    for e in results:
        yield from e.get("rays") or e.get("darts") or [e]


def _record_cast(camp: dict, caster: dict, spell: str, results: list[dict]) -> None:
    ids = _by_id(camp)
    for e in _parts(results):
        tgt = ids.get(e["target"], caster)
        if e.get("attack_roll"):
            natural = e["attack_roll"]["natural"]
            _rec_d20(camp, caster, "attack", f"{spell} vs {tgt['name']}", e["attack_roll"], e["to_hit"] - natural, e["to_hit"],
                     hit=e["hit"], crit=e["critical"], target=tgt["id"], dc=e["ac"])
        if e.get("save"):
            _rec_save(camp, tgt, f"{spell} save", e["save"])
        for r in (e.get("damage") or {}).get("rolls", []):
            _rec_roll(camp, caster, "damage", f"{spell} damage", r, type=e["damage"]["type"], target=tgt["id"])
        for r in e.get("rolls", []):
            _rec_roll(camp, caster, "heal", spell, r, target=tgt["id"])


@_tool
def tk_cast(args):
    who = _identity()
    camp = _load(who)
    spell_key = _text(args, "spell", limit=40).lower().replace("_", " ")
    sp = srd.SPELLS.get(spell_key)
    if sp is None:
        raise Refusal("unknown_spell", f"Spells: {', '.join(srd.SPELLS)}.")
    cost = {"action": "action", "bonus action": "bonus", "reaction": "reaction"}[sp["casting_time"]]
    c = _acting(camp, who, args.get("character"), cost=cost)
    targets = _targets(camp, args)
    for t in targets:
        if _dist(c, t) > max(sp["range"], FEET):
            raise Refusal("out_of_range", f"{t['name']} is {_dist(c, t)} ft away; {sp['name']} reaches {sp['range']} ft. "
                          "Use tk_move first.")
    slot = _int(args, "slot_level", None, 1, 9) if args.get("slot_level") is not None else None
    res = rules.cast(c, spell_key, targets, slot_level=slot, rng=RNG, in_melee=bool(_engaged(camp, c)),
                     creatures=camp["creatures"])
    _spend(camp, c, cost)
    _record_cast(camp, c, sp["name"], res["results"])
    hurt = {}
    for e in _parts(res["results"]):
        hurt[e["target"]] = hurt.get(e["target"], 0) + (e.get("damage") or {}).get("applied", 0)
    for e in res["results"]:
        conc = _concentration(camp, _by_id(camp)[e["target"]], hurt.get(e["target"], 0))
        if conc:
            e["concentration"] = conc
    _log(camp, "cast", f"{c['name']} casts {sp['name']}" + (f" (slot {res['slot_used']})" if res["slot_used"] else "")
         + (" on " + ", ".join(t["name"] for t in targets) if targets else "") + ".")
    extra = _close_if_over(camp)
    _save(camp)
    return _ok(character=c["id"], **res, **extra)


# ---------------------------------------------------------------- game master tools

def _amount(args: dict) -> tuple[int, dict | None]:
    if args.get("formula"):
        rolled = rules.roll(_text(args, "formula", limit=64), rng=RNG)
        return max(0, rolled["total"]), rolled
    return _int(args, "amount", None, 0, 1000), None


@_tool
def tk_damage(args):
    """Game master ruling: damage from a trap, fall or hazard. Resistances and death rules still apply."""
    who = _identity()
    camp = _load(who)
    _need_gm(camp, who, "rule damage")
    tgt = _find(camp, args.get("target"))
    if _dead(tgt):
        raise Refusal("invalid_target", f"{tgt['name']} is already dead.")
    amount, rolled = _amount(args)
    dtype = _text(args, "damage_type", required=False).lower() or "bludgeoning"
    reason = _text(args, "reason", required=False)
    if rolled:
        _rec_roll(camp, tgt, "damage", reason or "ruling", rolled, type=dtype)
    res = rules.apply_damage(tgt, amount, dtype, critical=bool(args.get("critical")), rng=RNG)
    conc = _concentration(camp, tgt, res["applied"])
    _log(camp, "damage", f"Game master: {tgt['name']} takes {res['applied']} {dtype} damage" + (f" ({reason})" if reason else "")
         + f". {tgt['hp']}/{tgt['max_hp']} HP.")
    extra = _close_if_over(camp)
    _save(camp)
    return _ok(target=_brief(tgt), applied=res["applied"], state=res["state"], notes=res["notes"],
               death_saves=res["death_saves"], concentration=conc, **extra)


@_tool
def tk_heal(args):
    who = _identity()
    camp = _load(who)
    _need_gm(camp, who, "rule healing")
    tgt = _find(camp, args.get("target"))
    amount, rolled = _amount(args)
    if rolled:
        _rec_roll(camp, tgt, "heal", _text(args, "reason", required=False) or "ruling", rolled)
    res = rules.heal(tgt, amount)
    _log(camp, "heal", f"Game master: {tgt['name']} regains {res['healed']} HP. {tgt['hp']}/{tgt['max_hp']} HP.")
    _save(camp)
    return _ok(target=_brief(tgt), healed=res["healed"], state=res["state"], notes=res["notes"])


@_tool
def tk_condition(args):
    who = _identity()
    camp = _load(who)
    _need_gm(camp, who, "set conditions")
    tgt = _find(camp, args.get("target"))
    cond, remove = _text(args, "condition", limit=30).lower(), bool(args.get("remove"))
    if cond == "stable":
        if remove or tgt["kind"] != "pc" or rules.state(tgt) != "down":
            raise Refusal("invalid_input", "Only a player character at 0 HP can be stabilised.")
        tgt["conditions"].append("stable")
        tgt["death_saves"] = {"s": 0, "f": 0}
        res = {"conditions": list(tgt["conditions"]), "notes": ["stable at 0 HP"]}
    else:
        res = (rules.remove_condition if remove else rules.add_condition)(tgt, cond)
    _log(camp, "condition", f"{tgt['name']} is {'no longer ' if remove else ''}{cond}.")
    _save(camp)
    return _ok(target=tgt["id"], conditions=res["conditions"], notes=res.get("notes", []))


# ---------------------------------------------------------------- combat flow

def _spawn_monsters(camp: dict, specs) -> list[dict]:
    if not isinstance(specs, list) or not specs:
        raise Refusal("invalid_input", "monsters must be a list such as [{\"type\": \"goblin\", \"count\": 2}].")
    made = []
    for spec in specs:
        spec = {"type": spec} if isinstance(spec, str) else spec
        key = re.sub(r"[^a-z]+", "_", str(spec.get("type") or spec.get("name") or spec.get("monster") or "").lower()).strip("_")
        if key not in srd.MONSTERS:
            raise Refusal("unknown_monster", f"Monsters: {', '.join(srd.MONSTERS)}.")
        count = _int(spec, "count", 1, 1, MAX_MONSTERS)
        for _ in range(count):
            if len(made) >= MAX_MONSTERS:
                raise Refusal("too_many", f"At most {MAX_MONSTERS} monsters per fight.")
            n = 1 + sum(1 for c in camp["creatures"] if c["id"].startswith(key + "-"))
            anchor = [_int(spec, "x", None, 0, GRID_W - 1), _int(spec, "y", None, 0, GRID_H - 1)] if "x" in spec else None
            pos = _nearest_free(camp, anchor) if anchor and count > 1 else _spawn_pos(camp, "monster", anchor)
            m = srd.new_monster(key, id=f"{key}-{n}", name=f"{srd.MONSTERS[key]['name']} {n}", pos=pos)
            m.update(status="ok", turn=_new_turn())
            camp["creatures"].append(m)
            made.append(m)
    return made


@_tool
def tk_start_combat(args):
    who = _identity()
    camp = _load(who)
    _need_gm(camp, who, "start combat")
    if camp["in_combat"]:
        raise Refusal("combat_running", "Combat is already running.")
    camp["creatures"] = [c for c in camp["creatures"] if c["kind"] == "pc"]
    if not any(not _dead(c) for c in camp["creatures"]):
        raise Refusal("no_party", "Claim at least one living character with tk_claim_character before combat.")
    made = _spawn_monsters(camp, args.get("monsters"))
    for c in camp["creatures"]:
        c["turn"] = _new_turn()
    order = rules.roll_initiative([c for c in camp["creatures"] if not _dead(c)], rng=RNG)
    ids = _by_id(camp)
    for cid in order:
        c, bonus = ids[cid], rules.ability_mod(ids[cid], "dex")
        _rec(camp, c, "initiative", "initiative", dice=[c["initiative"] - bonus], total=c["initiative"], modifier=bonus,
             formula=f"1d20{bonus:+d}", natural=c["initiative"] - bonus)
    camp.update(initiative=order, in_combat=True, round=1)
    _start_turn(camp, ids[order[0]])
    _log(camp, "combat", "Combat begins: " + ", ".join(ids[i]["name"] for i in order) + ".")
    flow = _run_monsters(camp)
    active = ids.get(camp["active"])
    _save(camp)
    return _ok(round=camp["round"], initiative=[{**_brief(ids[i]), "initiative": ids[i]["initiative"]} for i in order],
               active=_brief(active) if active else None, spawned=[m["id"] for m in made], **flow)


def _end_combat(camp: dict, who: dict) -> dict:
    _need_gm(camp, who, "end combat")
    if not camp["in_combat"]:
        raise Refusal("no_combat", "There is no combat running.")
    return _finish(camp, "ended by the game master")


@_tool
def tk_next_turn(args):
    who = _identity()
    camp = _load(who)
    if not camp["in_combat"]:
        raise Refusal("no_combat", "There is no combat to advance. The game master starts one with tk_start_combat.")
    if args.get("end_combat"):
        res = _end_combat(camp, who)
        _save(camp)
        return _ok(combat_over=res)
    cur = _by_id(camp)[camp["active"]]
    if not (_is_gm(camp, who) or cur["owner"] == who["user"]):
        raise Refusal("not_your_turn", f"It is {cur['name']}'s turn. Only their owner or the game master ends it.", active=cur["id"])
    if rules.state(cur) == "down":
        raise Refusal("death_save_required", f"{cur['name']} is at 0 HP. Roll tk_death_save first; it ends the turn.")
    res = _end_turn(camp)
    _save(camp)
    return _ok(**res)


@_tool
def tk_death_save(args):
    who = _identity()
    camp = _load(who)
    c = _find(camp, _default_ref(camp, who, args.get("character")), kind="pc")
    if not (_is_gm(camp, who) or c["owner"] == who["user"]):
        raise Refusal("not_owner", f"{c['name']} belongs to another player. Only their owner or the game master rolls for them.")
    if camp["in_combat"] and camp["active"] != c["id"]:
        raise Refusal("not_your_turn", f"{c['name']} rolls death saves on their own turn.", active=camp["active"])
    res = rules.death_save(c, rng=RNG)
    _rec(camp, c, "death", "death saving throw", dice=res["dice"], total=res["natural"], natural=res["natural"],
         outcome=res["outcome"])
    _log(camp, "death", f"{c['name']} death save {res['natural']}: {res['outcome'].replace('_', ' ')} "
         f"({res['successes']} successes, {res['failures']} failures).")
    extra = {}
    if camp["in_combat"]:
        done = _outcome(camp)
        extra = {"combat_over": _finish(camp, done)} if done else _end_turn(camp)
    _save(camp)
    return _ok(character=c["id"], **res, **extra)


@_tool
def tk_rest(args):
    who = _identity()
    camp = _load(who)
    if camp["in_combat"]:
        raise Refusal("combat_running", "Nobody rests during combat.")
    kind = _text(args, "kind", limit=10).lower()
    if kind == "long":
        _need_gm(camp, who, "call a long rest")
        out = {c["id"]: rules.long_rest(c) for c in camp["creatures"] if c["kind"] == "pc" and not _dead(c)}
        _log(camp, "rest", "The party takes a long rest.")
    elif kind == "short":
        c = _owned(camp, who, args.get("character"))
        res = rules.short_rest(c, _int(args, "hit_dice", 0, 0, 20), rng=RNG)
        if res["rolls"]:
            _rec(camp, c, "rest", "short rest hit dice", dice=res["rolls"], total=res["healed"], modifier=res["con_mod"],
                 formula=f"{len(res['rolls'])}{c['hit_dice'][2]}{res['con_mod']:+d}")
        _log(camp, "rest", f"{c['name']} takes a short rest and heals {res['healed']} HP.")
        out = {c["id"]: res}
    else:
        raise Refusal("invalid_input", "kind must be short or long.")
    _save(camp)
    return _ok(kind=kind, results=out)


def _recap(camp: dict, entries: list[dict]) -> dict:
    return {"chat": camp["chat"], "scene": camp["scene"], "round": camp["round"], "in_combat": camp["in_combat"],
            "party": [_brief(c) for c in camp["creatures"] if c["kind"] == "pc"],
            "foes": [_brief(c) for c in camp["creatures"] if c["kind"] == "monster"],
            "events": [e["text"] for e in entries]}


@_tool
def tk_recap(args):
    who = _identity()
    camp = _load(who)
    return _ok(**_recap(camp, store.log_entries(_db(), who["chat"], 30)))


# ---------------------------------------------------------------- /table command

def _glyphs(camp: dict) -> dict:
    pcs = [c for c in camp["creatures"] if c["kind"] == "pc"]
    foes = [c for c in camp["creatures"] if c["kind"] == "monster"]
    return {**{c["id"]: "ABCDEFGH"[i] for i, c in enumerate(pcs[:8])},
            **{c["id"]: "123456789abc"[i] for i, c in enumerate(foes[:12])}}


def _map(camp: dict) -> str:
    glyph = _glyphs(camp)
    grid = [["." for _ in range(GRID_W)] for _ in range(GRID_H)]
    for c in sorted(camp["creatures"], key=lambda c: not _dead(c)):
        x, y = c["pos"]
        grid[y][x] = "x" if _dead(c) else glyph.get(c["id"], "?")
    rows = ["    " + "".join(f"{x:<3}" for x in range(GRID_W))]
    rows += [f"{y:>2}  " + "".join(f"{cell:<3}" for cell in row) for y, row in enumerate(grid)]
    legend = [f"{glyph.get(c['id'], '?')} {c['name']} {c['hp']}/{c['max_hp']} HP"
              + (f" [{rules.state(c)}]" if rules.state(c) != "ok" else "") for c in camp["creatures"] if not _dead(c)]
    return "```\n" + "\n".join(rows) + "\n```\n" + "\n".join(legend)


def _status_text(camp: dict) -> str:
    head = f"Round {camp['round']}, {_by_id(camp)[camp['active']]['name']}'s turn." if camp["in_combat"] else "No combat running."
    return "\n".join([head] + [
        f"{c['name']} ({c['id']}) {c['hp']}/{c['max_hp']} HP, AC {c['ac']}, at ({c['pos'][0]},{c['pos'][1]})"
        + (f", {rules.state(c)}" if rules.state(c) != "ok" else "") for c in camp["creatures"]])


def _mark_playing(session_id: str) -> None:
    if session_id:
        _PLAYING.pop(session_id, None)
        _PLAYING[session_id] = None
        if len(_PLAYING) > 256:
            _PLAYING.pop(next(iter(_PLAYING)))


def _command(raw_args: str, *, platform: str = "", source=None, session_id: str = "", **_kw) -> str:
    _mark_playing(session_id)
    sub, _, rest = raw_args.strip().partition(" ")
    sub, rest = (sub or "status").lower(), rest.strip()
    try:
        with LOCK:
            who = _identity(source=source, platform=platform)
            if sub == "new":
                confirmed, scene = rest.split(" ", 1)[0] == "confirm", rest.removeprefix("confirm").strip()
                old = store.load(_db(), who["chat"])
                if old and old["creatures"] and not confirmed:
                    _need_gm(old, who, "replace this campaign")
                    return "A campaign with characters runs here. Send `/table new confirm` to wipe it and start over."
                _new_campaign(who, scene[:500], True)
                return "Campaign started. Players claim a character with /table claim <fighter|rogue|wizard|cleric>."
            camp = _load(who)
            if sub == "claim":
                claimed = _claim(camp, who, rest)
                _save(camp)
                return f"{claimed['name']} claimed at ({claimed['pos'][0]},{claimed['pos'][1]})."
            if sub == "end":
                res = _end_combat(camp, who)
                _save(camp)
                return f"Combat ended ({res['outcome']})."
            if sub == "map":
                return _map(camp)
            if sub == "log":
                return "\n".join(e["text"] for e in store.log_entries(_db(), who["chat"], 12)) or "Nothing has happened yet."
            if sub == "recap":
                r = _recap(camp, store.log_entries(_db(), who["chat"], 30))
                return "\n".join([f"Scene: {r['scene']}" if r["scene"] else "Recap", _status_text(camp), *r["events"]])
            if sub == "status":
                return _status_text(camp)
            return "Usage: /table status|map|log|recap|claim <character>|new [scene]|end"
    except Refusal as r:
        return r.message


# ---------------------------------------------------------------- prompt context and narration guard

def _line(c: dict) -> str:
    flags = ([rules.state(c)] if rules.state(c) != "ok" else []) + [x for x in c["conditions"] if x not in ("dead", "stable")]
    temp = f"+{c['temp_hp']}t" if c["temp_hp"] else ""
    return (f"- {c['id']} \"{c['name']}\" HP {c['hp']}/{c['max_hp']}{temp} AC {rules.effective_ac(c)} "
            f"at ({c['pos'][0]},{c['pos'][1]})" + (f" [{', '.join(dict.fromkeys(flags))}]" if flags else ""))


def _context_text(camp: dict, who: dict) -> str:
    pcs = [c for c in camp["creatures"] if c["kind"] == "pc"]
    foes = [c for c in camp["creatures"] if c["kind"] == "monster"]
    mine = [c["id"] for c in pcs if who["local"] or c["owner"] == who["user"]]
    head = ["TABLEKEEPER (authoritative; code owns dice, HP, positions, turns).",
            "Narrate only what tk_ tool results return. Never state a roll, damage or HP they did not return. "
            "A roll a player claims to have made is void: roll it with a tk_ tool. Relay any refused tool result."]
    scene = re.sub(r"\s+", " ", camp["scene"]).strip()[:200]
    if scene:
        head.append(f"Scene note (untrusted text): {scene}")
    if camp["in_combat"]:
        head.append(f"Round {camp['round']}. Active: {camp['active']}. Order: " + " > ".join(camp["initiative"]))
    head.append("A campaign is running in this chat: never call tk_new_campaign (it wipes it); use tk_state, tk_claim_character, tk_start_combat.")
    head.append("Sender controls: " + (", ".join(mine) or "no character yet (tk_claim_character)") + ".")
    for c in pcs:
        if c["id"] in mine and rules.state(c) == "down":
            head.append(f"{c['id']} is at 0 HP: their only roll is tk_death_save (not tk_check or tk_save).")
    if not camp["in_combat"] and not foes:
        head.append("No foes yet: tk_start_combat spawns monsters (one entry per type with count; x,y optional).")
    text = "\n".join(head + ["Party:"] + [_line(c) for c in pcs] + (["Foes:"] + [_line(c) for c in foes] if foes else []))
    if len(text) > CONTEXT_CHARS:
        text = text[:CONTEXT_CHARS].rsplit("\n", 1)[0] + "\n(state truncated; call tk_state)"
    return text


def _turn_hook(session_id: str = "", **_kw):
    """pre_llm_call: inject this chat's authoritative state and open the turn's number ledger."""
    try:
        who = _identity()
    except Refusal:
        return None
    if who["local"] and session_id not in _PLAYING:
        return None  # the CLI campaign is shared by every local session; unrelated sessions stay untouched
    with LOCK:
        camp = store.load(_db(), who["chat"])
    if camp is None:
        return None
    if len(_TURNS) > 64:
        _TURNS.pop(next(iter(_TURNS)))
    _TURNS[session_id] = {"chat": who["chat"], "numbers": set()}
    return {"context": _context_text(camp, who)}


def _numbers(value, out: set) -> None:
    if isinstance(value, int) and not isinstance(value, bool):
        out.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            _numbers(v, out)
    elif isinstance(value, list):
        for v in value:
            _numbers(v, out)


def _collect(tool_name: str = "", result="", session_id: str = "", **_kw) -> None:
    """post_tool_call: every integer a tk_ tool returned this turn is a number narration may use."""
    if not tool_name.startswith("tk_"):
        return
    _mark_playing(session_id)
    turn = _TURNS.get(session_id)
    if turn is None:  # the first tool call of a session arrives before any state block
        try:
            turn = _TURNS[session_id] = {"chat": _identity()["chat"], "numbers": set()}
        except Refusal:
            return
    try:
        _numbers(json.loads(result) if isinstance(result, str) else result, turn["numbers"])
    except json.JSONDecodeError:
        return


_ACT = r"(?:attacks?|strikes?|swings?|slashes|stabs?|casts?|shoots?|fires?|lunges?|charges|moves?|runs?|leaps?|bites?|slams?|hits?)"
_DEATH_WORDS = re.compile(r"\b(?:dies|died|dead|falls|fallen|collapses|slain|killed|drops?|unconscious|lifeless|cannot|can't|unable|no longer)\b", re.I)
_CLAUSE_BREAK = re.compile(r"[,;:]|\b(?:and|then|but|while|as|before|after)\s+(?-i:[A-Z])", re.I)  # the verb has another subject
_SUBJECT_CUE = re.compile(r"(?:[.!?,;:\n\"'(*_)-]|\b(?:and|but|then|while|as|when|until|before|after|meanwhile|now))\s*(?:the\s+)?$", re.I)  # name opens a clause
_DAMAGE = re.compile(r"\b(\d{1,4})\s*(?:points?\s+of\s+)?(?:[a-z]+\s+)?damage\b", re.I)
_HIT_POINTS = re.compile(r"\b(\d{1,4})\s*(?:hp|hit\s+points?)\b", re.I)
_CLAIMED_ROLL = re.compile(r"\b(?:rolls?|rolled|rolling|natural|nat)\s+(?:a\s+|an\s+)?(?:natural\s+)?(?:total\s+of\s+)?(\d{1,3})\b", re.I)
_CLAIMED_AC = re.compile(r"\bAC\s*(\d{1,2})\b")
_CLAIMED_DC = re.compile(r"\bDC\s*(\d{1,2})\b")


def _check_narration(text: str, camp: dict, produced: set) -> list[str]:
    problems = []
    creatures = camp["creatures"][:24]
    for c in creatures:
        if c["status"] != "ok" or c["hp"] <= 0:
            for m in re.finditer(rf"\b{re.escape(c['name'])}\b(?!')[^.!?\n]{{0,40}}?\b{_ACT}\b", text, re.I):
                subject = m.start() == 0 or _SUBJECT_CUE.search(text[max(0, m.start() - 30):m.start()])
                if subject and not (_DEATH_WORDS.search(m.group(0)) or _CLAUSE_BREAK.search(m.group(0)[len(c["name"]):])):
                    problems.append(f"{c['name']} is at 0 HP ({c['status']}) and cannot act")
                    break
    hp = {n for c in creatures for n in (c["hp"], c["max_hp"], c["temp_hp"])}
    for pattern, label, known in ((_DAMAGE, "damage figure", produced),
                                  (_HIT_POINTS, "hit point figure", produced | hp),
                                  (_CLAIMED_ROLL, "dice roll", produced),
                                  (_CLAIMED_AC, "AC", produced | {rules.effective_ac(c) for c in creatures}),
                                  (_CLAIMED_DC, "DC", produced | {10})):  # 10 is the fixed death save DC, quoted as a rule
        bad = sorted({int(n) for n in pattern.findall(text) if int(n) not in known})
        if bad:
            problems.append(f"{label} {', '.join(map(str, bad))} was not returned by a tk_ tool this turn")
    return problems


def _guard(response_text: str = "", session_id: str = "", **_kw):
    """transform_llm_output: append a visible correction when narration contradicts the table."""
    turn = _TURNS.pop(session_id, None)
    if turn is None or not response_text:
        return None
    with LOCK:
        camp = store.load(_db(), turn["chat"])
    if camp is None:
        return None
    problems = _check_narration(response_text, camp, turn["numbers"])
    if not problems:
        return None
    return response_text + "\n\n[Tablekeeper check: " + "; ".join(problems) + ". The table state is authoritative. Use tk_state.]"


# ---------------------------------------------------------------- registration

def _obj(required=(), **props) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


def _str(description: str) -> dict:
    return {"type": "string", "description": description}


def _num(description: str) -> dict:
    return {"type": "integer", "description": description}


def _flag(description: str) -> dict:
    return {"type": "boolean", "description": description}


_CHAR = _str("Character id: fighter, rogue, wizard or cleric. Omit when the sender has only one character.")
_ROLL = {"advantage": _flag("Grant advantage if the situation earns it."),
         "disadvantage": _flag("Impose disadvantage if the situation earns it.")}
_MONSTER = _obj([], type=_str("goblin, hobgoblin, kobold, wolf, dire_wolf, skeleton, zombie, orc, bandit, "
                                    "bandit_captain, giant_rat or ogre."),
                count=_num("How many, default 1."), x=_num("Column to place it, or to cluster a group around."), y=_num("Row to place it, or to cluster a group around."))

TOOLS = [
    ("tk_state", tk_state, "Read the authoritative campaign: grid, initiative, every creature's HP, position and conditions, and which characters the sender controls. Call it before narrating state and whenever unsure.", _obj()),
    ("tk_new_campaign", tk_new_campaign, "Start a brand-new campaign in this chat. Call it only when the player asks to begin or restart a campaign; never to start a fight, add characters or resume play (use tk_state, tk_claim_character, tk_start_combat). The caller becomes game master. Replacing an existing campaign wipes it and needs replace=true.", _obj(scene=_str("One or two sentences of opening scene."), replace=_flag("Wipe the existing campaign."))),
    ("tk_claim_character", tk_claim_character, "Claim a pregenerated level 3 character (fighter, rogue, wizard, cleric) for the sender. One per player, between fights.", _obj(["character"], character=_CHAR)),
    ("tk_roll", tk_roll, "Roll dice such as 2d6+3, 4d6kh3 or 1d20. Use it for any roll that does not change game state. Never invent dice results.", _obj(["formula"], formula=_str("Dice formula, at most 64 characters."), why=_str("What the roll is for."))),
    ("tk_check", tk_check, "Roll an ability or skill check for the sender's character, optionally against a DC. Works any time and uses no action.", _obj(["skill_or_ability"], character=_CHAR, skill_or_ability=_str("Ability (dex) or skill (stealth, perception)."), dc=_num("Difficulty class, 1-40."), **_ROLL)),
    ("tk_save", tk_save, "Roll a saving throw for the sender's character against a DC. Works any time and uses no action.", _obj(["ability", "dc"], character=_CHAR, ability=_str("str, dex, con, int, wis or cha."), dc=_num("Difficulty class, 1-40."), **_ROLL)),
    ("tk_attack", tk_attack, "Make a weapon attack for the sender's character on their turn. Rolls to hit against AC, applies damage and reports the result. Refuses when out of range or out of turn.", _obj(["target"], character=_CHAR, target=_str("Enemy id such as goblin-1 (a name like Goblin 1 also works)."), attack=_str("Attack name, default the first."), cover=_num("0, 2 or 5."), **_ROLL)),
    ("tk_cast", tk_cast, "Cast a spell for the sender's character on their turn. Spends the slot, rolls attacks or saves and applies the results.", _obj(["spell"], character=_CHAR, spell=_str("Spell name, such as fire bolt."), targets={"type": "array", "items": {"type": "string"}, "description": "Creature ids; empty for self spells."}, slot_level=_num("Slot level to upcast with."))),
    ("tk_move", tk_move, "Move the sender's character to a grid square (x 0-11, y 0-9, 5 ft per square), limited by speed. Give x and y, or toward=<creature id> to get adjacent. Leaving an enemy's reach provokes its opportunity attack unless disengage=true.", _obj([], character=_CHAR, x=_num("Column (with y)."), y=_num("Row (with x)."), toward=_str("Creature id to close in on: moves to the free square nearest it within movement left. Use instead of x and y to get next to a foe."), disengage=_flag("Spend the action to avoid opportunity attacks."))),
    ("tk_next_turn", tk_next_turn, "End the active character's turn. Plays every monster turn until a character is up again and returns what the monsters did. The game master may pass end_combat=true.", _obj(end_combat=_flag("Game master only: end the fight now."))),
    ("tk_death_save", tk_death_save, "Roll a death saving throw for a character at 0 HP on their turn. It ends their turn. Use this, never tk_check or tk_save, whenever a character is at 0 HP.", _obj(character=_CHAR)),
    ("tk_rest", tk_rest, "Short rest (spend hit dice for one character) or long rest (game master, whole party). Not during combat.", _obj(["kind"], kind=_str("short or long."), character=_CHAR, hit_dice=_num("Hit dice to spend on a short rest."))),
    ("tk_start_combat", tk_start_combat, "Game master only. Spawn SRD monsters, roll initiative and start combat. Monsters act automatically until a character is up.", _obj(["monsters"], monsters={"type": "array", "description": "Monsters to spawn.", "items": _MONSTER})),
    ("tk_damage", tk_damage, "Game master only. Apply damage from a trap, fall or other ruling to any creature. Resistance, temp HP and death rules still apply.", _obj(["target"], target=_str("Creature id."), amount=_num("Fixed damage."), formula=_str("Dice formula instead of amount."), damage_type=_str("Damage type, default bludgeoning."), reason=_str("Why."), critical=_flag("Treat as a critical hit."))),
    ("tk_heal", tk_heal, "Game master only. Heal a creature by ruling. Restores consciousness at 0 HP.", _obj(["target"], target=_str("Creature id."), amount=_num("Fixed healing."), formula=_str("Dice formula instead of amount."), reason=_str("Why."))),
    ("tk_condition", tk_condition, "Game master only. Add or remove a condition (blinded, prone, poisoned, ...). Use stable to stabilise a character at 0 HP.", _obj(["target", "condition"], target=_str("Creature id."), condition=_str("Condition name."), remove=_flag("Remove instead of add."))),
    ("tk_recap", tk_recap, "Get the story so far: scene, party, foes and the last 30 logged events, for a previously-on summary.", _obj()),
]


def register(ctx):
    for name, handler, description, schema in TOOLS:
        ctx.register_tool(name=name, toolset="tablekeeper", schema={"name": name, "description": description, "parameters": schema},
                          handler=handler, description=description)
    ctx.register_hook("pre_llm_call", _turn_hook)
    ctx.register_hook("post_tool_call", _collect)
    ctx.register_hook("transform_llm_output", _guard)
    ctx.register_command("table", _command, description="Tablekeeper campaign",
                         args_hint="status|map|log|recap|claim <character>|new [scene]|end")
