"""Deterministic SRD 5.1 rules used by Tablekeeper."""
from __future__ import annotations

import secrets


def roll(formula: str, *, rng=None) -> dict:
    rng = rng or secrets.SystemRandom()
    formula = formula.strip().lower().replace(" ", "")
    import re
    match = re.fullmatch(r"(?:(\d+)d(\d+))?([+-]\d+)?", formula)
    if not match or not (match.group(1) or match.group(3)):
        raise ValueError("Use a dice formula such as 1d20+3")
    count, sides, mod = int(match.group(1) or 0), int(match.group(2) or 0), int(match.group(3) or 0)
    if (count == 0 and mod == 0) or count > 100 or sides > 1000 or sides < 0:
        raise ValueError("Dice formula exceeds limits")
    dice = [rng.randint(1, sides) for _ in range(count)] if count else []
    return {"formula": formula, "dice": dice, "modifier": mod, "total": sum(dice) + mod}


def d20(*, advantage=False, disadvantage=False, rng=None) -> dict:
    rng = rng or secrets.SystemRandom()
    dice = [rng.randint(1, 20) for _ in range(2 if advantage != disadvantage else 1)]
    total = max(dice) if advantage else min(dice) if disadvantage else dice[0]
    return {"dice": dice, "total": total, "natural": total}


def attack_bonus(attack_roll: dict, bonus: int, ac: int, damage: str, *, rng=None) -> dict:
    hit = attack_roll["natural"] == 20 or (attack_roll["natural"] != 1 and attack_roll["total"] + bonus >= ac)
    crit = attack_roll["natural"] == 20
    result = {"hit": hit, "critical": crit, "attack": attack_roll, "total": attack_roll["total"] + bonus}
    if hit:
        if crit:
            import re
            m = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", damage.lower().replace(" ", ""))
            if not m:
                raise ValueError("Critical damage requires NdM[+/-N]")
            doubled = f"{int(m.group(1))*2}d{m.group(2)}{m.group(3) or ''}"
            result["damage"] = roll(doubled, rng=rng)
        else:
            result["damage"] = roll(damage, rng=rng)
    return result


def adjust_damage(amount: int, resistance=False, vulnerability=False) -> int:
    if resistance and not vulnerability:
        return amount // 2
    if vulnerability and not resistance:
        return amount * 2
    return amount


def death_save(successes: int, failures: int, natural: int) -> tuple[int, int, str | None]:
    if natural == 20:
        return 0, 0, "stable"
    successes += natural >= 10
    failures += natural == 1 and 2 or natural < 10
    return successes, failures, "stable" if successes >= 3 else "dead" if failures >= 3 else None
