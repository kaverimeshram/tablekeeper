"""SRD 5.1 content: monsters, pregenerated characters and spells.

All numbers are taken from the System Reference Document 5.1 (CC-BY-4.0) and
were cross-checked against the open SRD data at dnd5eapi.co.
"""
from __future__ import annotations

import copy

ATTRIBUTION = (
    "This work includes material taken from the System Reference Document 5.1 "
    "(“SRD 5.1”) by Wizards of the Coast LLC and available at "
    "https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1 "
    "is licensed under the Creative Commons Attribution 4.0 International "
    "License available at https://creativecommons.org/licenses/by/4.0/legalcode."
)

_ABILITY_ORDER = ("str", "dex", "con", "int", "wis", "cha")


def _attack(name, to_hit, damage, dtype, *, reach=5, rng=None, extra=None, rider=None):
    """One attack. reach is feet (None for ranged only), rng is [normal, long] feet."""
    out = {"name": name, "to_hit": to_hit, "damage": damage, "type": dtype,
           "reach": reach, "range": list(rng) if rng else None}
    if extra:
        out["extra"] = extra
    if rider:
        out["rider"] = rider
    return out


def _creature(key, name, kind, *, ctype, size, ac, hp, hit_die, hit_dice_count, speed,
              abilities, proficiency=2, saves=(), skills=None, attacks=(), resist=(),
              immune=(), vuln=(), condition_immune=(), traits=(), features=(), senses="",
              spells=(), slots=None, spell_ability=None, multiattack=None, **extra):
    c = {
        "id": key, "name": name, "kind": kind, "owner": None,
        "type": ctype, "size": size,
        "ac": ac, "hp": hp, "max_hp": hp, "temp_hp": 0,
        "abilities": dict(zip(_ABILITY_ORDER, abilities)),
        "proficiency": proficiency, "saves": list(saves), "skills": dict(skills or {}),
        "attacks": [dict(a) for a in attacks],
        "resist": list(resist), "immune": list(immune), "vuln": list(vuln),
        "condition_immune": list(condition_immune),
        "conditions": [], "effects": {}, "death_saves": {"s": 0, "f": 0},
        "slots": {str(k): list(v) for k, v in (slots or {}).items()},
        "spells": list(spells), "spell_ability": spell_ability,
        "hit_dice": [hit_dice_count, hit_dice_count, hit_die],
        "pos": None, "speed": speed, "concentration": None,
        "traits": list(traits), "features": [dict(f) for f in features], "senses": senses,
    }
    if multiattack:
        c["multiattack"] = {k: list(v) for k, v in multiattack.items()}
    c.update(extra)
    return c


def _monster(key, name, *, cr, xp, hp_formula, **kw):
    return _creature(key, name, "monster", cr=cr, xp=xp, hp_formula=hp_formula, **kw)


def _f(name, text):
    return {"name": name, "text": text}


_PACK = _f("Pack Tactics", "Advantage on an attack roll against a creature if at least one of its allies is within 5 ft. of the creature and the ally isn't incapacitated.")

MONSTERS = {
    "goblin": _monster(
        "goblin", "Goblin", cr="1/4", xp=50, hp_formula="2d6", ctype="humanoid", size="Small",
        ac=15, hp=7, hit_die="d6", hit_dice_count=2, speed=30,
        abilities=(8, 14, 10, 10, 8, 8), skills={"stealth": "expertise"},
        senses="darkvision 60 ft., passive Perception 9",
        attacks=[_attack("Scimitar", 4, "1d6+2", "slashing"),
                 _attack("Shortbow", 4, "1d6+2", "piercing", reach=None, rng=(80, 320))],
        traits=["nimble_escape", "flees_at_quarter_hp"],
        features=[_f("Nimble Escape", "The goblin can take the Disengage or Hide action as a bonus action on each of its turns.")]),
    "hobgoblin": _monster(
        "hobgoblin", "Hobgoblin", cr="1/2", xp=100, hp_formula="2d8+2", ctype="humanoid", size="Medium",
        ac=18, hp=11, hit_die="d8", hit_dice_count=2, speed=30,
        abilities=(13, 12, 12, 10, 10, 9), senses="darkvision 60 ft., passive Perception 10",
        attacks=[_attack("Longsword", 3, "1d8+1", "slashing", extra={"damage": "2d6", "when": "ally_adjacent"}),
                 _attack("Longbow", 3, "1d8+1", "piercing", reach=None, rng=(150, 600),
                         extra={"damage": "2d6", "when": "ally_adjacent"})],
        traits=["martial_advantage"],
        features=[_f("Martial Advantage", "Once per turn, the hobgoblin can deal an extra 7 (2d6) damage to a creature it hits with a weapon attack if that creature is within 5 ft. of an ally of the hobgoblin that isn't incapacitated.")]),
    "kobold": _monster(
        "kobold", "Kobold", cr="1/8", xp=25, hp_formula="2d6-2", ctype="humanoid", size="Small",
        ac=12, hp=5, hit_die="d6", hit_dice_count=2, speed=30,
        abilities=(7, 15, 9, 8, 7, 8), senses="darkvision 60 ft., passive Perception 8",
        attacks=[_attack("Dagger", 4, "1d4+2", "piercing"),
                 _attack("Sling", 4, "1d4+2", "bludgeoning", reach=None, rng=(30, 120))],
        traits=["pack_tactics", "sunlight_sensitivity", "flees_at_quarter_hp"],
        features=[_f("Sunlight Sensitivity", "While in sunlight, the kobold has disadvantage on attack rolls, as well as on Wisdom (Perception) checks that rely on sight."), _PACK]),
    "wolf": _monster(
        "wolf", "Wolf", cr="1/4", xp=50, hp_formula="2d8+2", ctype="beast", size="Medium",
        ac=13, hp=11, hit_die="d8", hit_dice_count=2, speed=40,
        abilities=(12, 15, 12, 3, 12, 6), skills={"perception": "proficient", "stealth": "proficient"},
        senses="passive Perception 13",
        attacks=[_attack("Bite", 4, "2d4+2", "piercing",
                         rider={"save": "str", "dc": 11, "condition": "prone"})],
        traits=["pack_tactics", "keen_hearing_and_smell"],
        features=[_f("Keen Hearing and Smell", "The wolf has advantage on Wisdom (Perception) checks that rely on hearing or smell."), _PACK]),
    "dire_wolf": _monster(
        "dire_wolf", "Dire Wolf", cr="1", xp=200, hp_formula="5d10+10", ctype="beast", size="Large",
        ac=14, hp=37, hit_die="d10", hit_dice_count=5, speed=50,
        abilities=(17, 15, 15, 3, 12, 7), skills={"perception": "proficient", "stealth": "proficient"},
        senses="passive Perception 13",
        attacks=[_attack("Bite", 5, "2d6+3", "piercing",
                         rider={"save": "str", "dc": 13, "condition": "prone"})],
        traits=["pack_tactics", "keen_hearing_and_smell"],
        features=[_f("Keen Hearing and Smell", "The wolf has advantage on Wisdom (Perception) checks that rely on hearing or smell."), _PACK]),
    "skeleton": _monster(
        "skeleton", "Skeleton", cr="1/4", xp=50, hp_formula="2d8+4", ctype="undead", size="Medium",
        ac=13, hp=13, hit_die="d8", hit_dice_count=2, speed=30,
        abilities=(10, 14, 15, 6, 8, 5), vuln=["bludgeoning"], immune=["poison"],
        condition_immune=["exhaustion", "poisoned"],
        senses="darkvision 60 ft., passive Perception 9",
        attacks=[_attack("Shortsword", 4, "1d6+2", "piercing"),
                 _attack("Shortbow", 4, "1d6+2", "piercing", reach=None, rng=(80, 320))]),
    "zombie": _monster(
        "zombie", "Zombie", cr="1/4", xp=50, hp_formula="3d8+9", ctype="undead", size="Medium",
        ac=8, hp=22, hit_die="d8", hit_dice_count=3, speed=20,
        abilities=(13, 6, 16, 3, 6, 5), saves=["wis"], immune=["poison"],
        condition_immune=["poisoned"], senses="darkvision 60 ft., passive Perception 8",
        attacks=[_attack("Slam", 3, "1d6+1", "bludgeoning")],
        traits=["undead_fortitude"],
        features=[_f("Undead Fortitude", "If damage reduces the zombie to 0 hit points, it must make a Constitution saving throw with a DC of 5 + the damage taken, unless the damage is radiant or from a critical hit. On a success, the zombie drops to 1 hit point instead.")]),
    "orc": _monster(
        "orc", "Orc", cr="1/2", xp=100, hp_formula="2d8+6", ctype="humanoid", size="Medium",
        ac=13, hp=15, hit_die="d8", hit_dice_count=2, speed=30,
        abilities=(16, 12, 16, 7, 11, 10), skills={"intimidation": "proficient"},
        senses="darkvision 60 ft., passive Perception 10",
        attacks=[_attack("Greataxe", 5, "1d12+3", "slashing"),
                 _attack("Javelin", 5, "1d6+3", "piercing", rng=(30, 120))],
        traits=["aggressive"],
        features=[_f("Aggressive", "As a bonus action, the orc can move up to its speed toward a hostile creature that it can see.")]),
    "bandit": _monster(
        "bandit", "Bandit", cr="1/8", xp=25, hp_formula="2d8+2", ctype="humanoid", size="Medium",
        ac=12, hp=11, hit_die="d8", hit_dice_count=2, speed=30,
        abilities=(11, 12, 12, 10, 10, 10), senses="passive Perception 10",
        attacks=[_attack("Scimitar", 3, "1d6+1", "slashing"),
                 _attack("Light Crossbow", 3, "1d8+1", "piercing", reach=None, rng=(80, 320))]),
    "bandit_captain": _monster(
        "bandit_captain", "Bandit Captain", cr="2", xp=450, hp_formula="10d8+20", ctype="humanoid", size="Medium",
        ac=15, hp=65, hit_die="d8", hit_dice_count=10, speed=30,
        abilities=(15, 16, 14, 14, 11, 14), saves=["str", "dex", "wis"],
        skills={"athletics": "proficient", "deception": "proficient"}, senses="passive Perception 10",
        attacks=[_attack("Scimitar", 5, "1d6+3", "slashing"),
                 _attack("Dagger", 5, "1d4+3", "piercing", rng=(20, 60))],
        multiattack={"melee": ["Scimitar", "Scimitar", "Dagger"], "ranged": ["Dagger", "Dagger"]},
        traits=["parry"],
        features=[_f("Multiattack", "The captain makes three melee attacks: two with its scimitar and one with its dagger. Or the captain makes two ranged attacks with its daggers."),
                  _f("Parry", "Reaction: the captain adds 2 to its AC against one melee attack that would hit it, if it can see the attacker and is wielding a melee weapon.")]),
    "giant_rat": _monster(
        "giant_rat", "Giant Rat", cr="1/8", xp=25, hp_formula="2d6", ctype="beast", size="Small",
        ac=12, hp=7, hit_die="d6", hit_dice_count=2, speed=30,
        abilities=(7, 15, 11, 2, 10, 4), senses="darkvision 60 ft., passive Perception 10",
        attacks=[_attack("Bite", 4, "1d4+2", "piercing")],
        traits=["pack_tactics", "keen_smell"],
        features=[_f("Keen Smell", "The rat has advantage on Wisdom (Perception) checks that rely on smell."), _PACK]),
    "ogre": _monster(
        "ogre", "Ogre", cr="2", xp=450, hp_formula="7d10+21", ctype="giant", size="Large",
        ac=11, hp=59, hit_die="d10", hit_dice_count=7, speed=40,
        abilities=(19, 8, 16, 5, 7, 7), senses="darkvision 60 ft., passive Perception 8",
        attacks=[_attack("Greatclub", 6, "2d8+4", "bludgeoning"),
                 _attack("Javelin", 6, "2d6+4", "piercing", rng=(30, 120))]),
    "young_red_dragon": _monster(
        "young_red_dragon", "Young Red Dragon", cr="10", xp=5900, hp_formula="17d10+85", ctype="dragon", size="Large",
        ac=18, hp=178, hit_die="d10", hit_dice_count=17, speed=40,
        abilities=(23, 10, 21, 14, 11, 19), proficiency=4, saves=["dex", "con", "wis", "cha"],
        attacks=[_attack("Bite", 10, "2d10+6", "piercing", reach=10,
                         extra={"damage": "1d6", "type": "fire"}),
                 _attack("Claw", 10, "2d6+6", "slashing")],
        multiattack={"melee": ["Bite", "Claw", "Claw"]},
        senses="blindsight 30 ft., darkvision 120 ft., passive Perception 10",
        features=[_f("Fire Breath", "Recharge 5-6. The dragon exhales fire in a 30-foot cone. Each creature in that area must make a DC 17 Dexterity saving throw, taking 56 (16d6) fire damage on a failed save, or half as much damage on a successful one.")],
        speed_modes={"walk": 40, "climb": 40, "fly": 80},
        breath={"name": "Fire Breath", "recharge": [5, 6], "charged": True, "range": 30, "save": "dex", "dc": 17, "damage": "16d6", "type": "fire"}),
}

_SNEAK = {"damage": "2d6", "when": "sneak"}

CHARACTERS = {
    "fighter": _creature(
        "fighter", "Brann Hollis", "pc", ctype="humanoid", size="Medium",
        race="Human", **{"class": "Fighter"}, subclass="Champion", level=3,
        ac=18, hp=28, hit_die="d10", hit_dice_count=3, speed=30,
        abilities=(16, 14, 15, 11, 13, 9), saves=["str", "con"],
        skills={"athletics": "proficient", "perception": "proficient"},
        senses="passive Perception 13", crit_range=19,
        attacks=[_attack("Longsword", 5, "1d8+5", "slashing"),
                 _attack("Longbow", 4, "1d8+2", "piercing", reach=None, rng=(150, 600))],
        traits=["improved_critical", "dueling"],
        features=[_f("Fighting Style: Dueling", "+2 damage with a melee weapon held in one hand and no other weapons."),
                  _f("Second Wind", "Bonus action: regain 1d10 + 3 hit points once per short or long rest."),
                  _f("Action Surge", "Take one additional action on your turn once per short or long rest."),
                  _f("Improved Critical", "Weapon attacks score a critical hit on a roll of 19 or 20.")],
        equipment="chain mail, shield, longsword, longbow"),
    "rogue": _creature(
        "rogue", "Pip Underbough", "pc", ctype="humanoid", size="Small",
        race="Lightfoot Halfling", **{"class": "Rogue"}, subclass="Thief", level=3,
        ac=14, hp=24, hit_die="d8", hit_dice_count=3, speed=25,
        abilities=(8, 17, 14, 12, 13, 11), saves=["dex", "int"],
        skills={"acrobatics": "proficient", "perception": "expertise", "stealth": "expertise",
                "sleight_of_hand": "proficient"},
        senses="passive Perception 15",
        attacks=[_attack("Shortsword", 5, "1d6+3", "piercing", extra=_SNEAK),
                 _attack("Shortbow", 5, "1d6+3", "piercing", reach=None, rng=(80, 320), extra=_SNEAK)],
        traits=["lucky", "brave", "sneak_attack"],
        features=[_f("Sneak Attack", "Once per turn, 2d6 extra damage with a finesse or ranged weapon when you have advantage, or when another enemy of the target is within 5 ft. of it and you don't have disadvantage."),
                  _f("Cunning Action", "Bonus action: Dash, Disengage or Hide."),
                  _f("Lucky", "Reroll a 1 on an attack roll, ability check or saving throw and use the new roll."),
                  _f("Fast Hands", "Use Cunning Action to make a Sleight of Hand check, use thieves' tools or take the Use an Object action."),
                  _f("Expertise", "Proficiency bonus doubled for Perception and Stealth.")],
        equipment="leather armor, shortsword, shortbow, thieves' tools"),
    "wizard": _creature(
        "wizard", "Elowen Vael", "pc", ctype="humanoid", size="Medium",
        race="High Elf", **{"class": "Wizard"}, subclass="School of Evocation", level=3,
        ac=12, hp=20, hit_die="d6", hit_dice_count=3, speed=30,
        abilities=(8, 15, 14, 16, 12, 10), saves=["int", "wis"],
        skills={"arcana": "proficient", "investigation": "proficient", "perception": "proficient"},
        senses="darkvision 60 ft., passive Perception 13",
        attacks=[_attack("Quarterstaff", 1, "1d6-1", "bludgeoning"),
                 _attack("Dagger", 4, "1d4+2", "piercing", rng=(20, 60))],
        spell_ability="int", slots={1: (4, 4), 2: (2, 2)},
        spells=["fire bolt", "ray of frost", "magic missile", "shield", "burning hands", "sleep",
                "hold person", "scorching ray"],
        spellbook=["magic missile", "shield", "burning hands", "sleep", "thunderwave", "hold person",
                   "scorching ray"],
        traits=["fey_ancestry"],
        features=[_f("Arcane Recovery", "Once per day on a short rest, recover expended spell slots with a combined level of up to 2."),
                  _f("Sculpt Spells", "Choose up to 1 + spell level creatures to automatically succeed on saves against your evocation spells."),
                  _f("Fey Ancestry", "Advantage on saves against being charmed, and magic can't put you to sleep.")],
        equipment="quarterstaff, dagger, spellbook"),
    "cleric": _creature(
        "cleric", "Thordis Ironvein", "pc", ctype="humanoid", size="Medium",
        race="Hill Dwarf", **{"class": "Cleric"}, subclass="Life Domain", level=3,
        ac=18, hp=30, hit_die="d8", hit_dice_count=3, speed=25,
        abilities=(13, 12, 16, 8, 16, 10), saves=["wis", "cha"],
        skills={"insight": "proficient", "medicine": "proficient", "religion": "proficient"},
        senses="darkvision 60 ft., passive Perception 13", resist=["poison"],
        attacks=[_attack("Mace", 3, "1d6+1", "bludgeoning")],
        spell_ability="wis", slots={1: (4, 4), 2: (2, 2)},
        spells=["sacred flame", "bless", "cure wounds", "healing word", "guiding bolt"],
        traits=["disciple_of_life", "dwarven_resilience"],
        features=[_f("Disciple of Life", "When a spell of 1st level or higher restores hit points, the target regains an additional 2 + the spell's level."),
                  _f("Channel Divinity: Preserve Life", "Restore up to 15 hit points (5 x cleric level) divided among creatures within 30 ft., none above half their maximum."),
                  _f("Dwarven Resilience", "Advantage on saving throws against poison, and resistance to poison damage."),
                  _f("Dwarven Toughness", "Hit point maximum increases by 1 per level.")],
        equipment="chain mail, shield, mace, holy symbol"),
}


def _spell(name, level, school, casting_time, rng, kind, summary, **kw):
    return {"name": name, "level": level, "school": school, "casting_time": casting_time,
            "range": rng, "kind": kind, "concentration": False, "summary": summary, **kw}


SPELLS = {
    "fire bolt": _spell("Fire Bolt", 0, "evocation", "action", 120, "attack",
                        "Ranged spell attack. 1d10 fire, +1d10 at levels 5, 11 and 17.",
                        dice=(1, 10), dtype="fire", cantrip_scaling=True, max_targets=1),
    "ray of frost": _spell("Ray of Frost", 0, "evocation", "action", 60, "attack",
                           "Ranged spell attack. 1d8 cold, speed reduced by 10 ft. until the start of your next turn.",
                           dice=(1, 8), dtype="cold", cantrip_scaling=True, max_targets=1, slows=10),
    "sacred flame": _spell("Sacred Flame", 0, "evocation", "action", 60, "save",
                           "Dexterity save or 1d8 radiant damage. The target gets no benefit from cover.",
                           dice=(1, 8), dtype="radiant", save="dex", half=False, ignores_cover=True,
                           cantrip_scaling=True, max_targets=1),
    "magic missile": _spell("Magic Missile", 1, "evocation", "action", 120, "darts",
                            "Three darts, each 1d4+1 force and never missing. One more dart per slot level above 1st.",
                            count=3, count_per_level=1, dice=(1, 4), flat=1, dtype="force"),
    "burning hands": _spell("Burning Hands", 1, "evocation", "action", 15, "save",
                            "15-ft. cone. Dexterity save, 3d6 fire on a failure and half on a success. +1d6 per slot level above 1st.",
                            dice=(3, 6), per_level=(1, 6), dtype="fire", save="dex", half=True, area="cone"),
    "thunderwave": _spell("Thunderwave", 1, "evocation", "action", 15, "save",
                          "15-ft. cube from you. Constitution save, 2d8 thunder and pushed 10 ft. on a failure, half and no push on a success. +1d8 per slot level above 1st.",
                          dice=(2, 8), per_level=(1, 8), dtype="thunder", save="con", half=True,
                          area="cube", push=10),
    "shield": _spell("Shield", 1, "abjuration", "reaction", 0, "self",
                     "Reaction. +5 AC until the start of your next turn, and no damage from magic missile.",
                     ac_bonus=5),
    "cure wounds": _spell("Cure Wounds", 1, "evocation", "action", 5, "heal",
                          "Touch. Heal 1d8 + spellcasting modifier. +1d8 per slot level above 1st. No effect on undead or constructs.",
                          dice=(1, 8), per_level=(1, 8), max_targets=1),
    "healing word": _spell("Healing Word", 1, "evocation", "bonus action", 60, "heal",
                           "Heal 1d4 + spellcasting modifier at range. +1d4 per slot level above 1st. No effect on undead or constructs.",
                           dice=(1, 4), per_level=(1, 4), max_targets=1),
    "guiding bolt": _spell("Guiding Bolt", 1, "evocation", "action", 120, "attack",
                           "Ranged spell attack. 4d6 radiant, and the next attack against the target before the end of your next turn has advantage. +1d6 per slot level above 1st.",
                           dice=(4, 6), per_level=(1, 6), dtype="radiant", max_targets=1, marks=True),
    "bless": _spell("Bless", 1, "enchantment", "action", 30, "buff",
                    "Concentration, 1 minute. Up to three creatures add 1d4 to attack rolls and saving throws. One more target per slot level above 1st.",
                    concentration=True, max_targets=3, targets_per_level=1, effect="bless"),
    "sleep": _spell("Sleep", 1, "enchantment", "action", 90, "sleep",
                    "Roll 5d8: that many hit points of creatures fall unconscious, lowest hit points first. Undead and creatures immune to being charmed are unaffected. +2d8 per slot level above 1st.",
                    dice=(5, 8), per_level=(2, 8)),
    "hold person": _spell("Hold Person", 2, "enchantment", "action", 60, "hold",
                          "Concentration, 1 minute. A humanoid makes a Wisdom save or is paralyzed, repeating the save at the end of each of its turns. One more humanoid per slot level above 2nd.",
                          concentration=True, save="wis", max_targets=1, targets_per_level=1),
    "scorching ray": _spell("Scorching Ray", 2, "evocation", "action", 120, "rays",
                            "Three rays, each a ranged spell attack for 2d6 fire. One more ray per slot level above 2nd.",
                            count=3, count_per_level=1, dice=(2, 6), dtype="fire"),
}


def new_monster(key: str, *, id: str | None = None, name: str | None = None, pos=None) -> dict:
    """A fresh, independent copy of an SRD monster at full hit points."""
    if key not in MONSTERS:
        raise KeyError(f"unknown monster: {key}")
    m = copy.deepcopy(MONSTERS[key])
    if id:
        m["id"] = id
    if name:
        m["name"] = name
    if pos is not None:
        m["pos"] = list(pos)
    return m


def new_character(key: str, *, id: str | None = None, owner: str | None = None, name: str | None = None, pos=None) -> dict:
    """A fresh, independent copy of a pregenerated character at full hit points."""
    if key not in CHARACTERS:
        raise KeyError(f"unknown character: {key}")
    c = copy.deepcopy(CHARACTERS[key])
    if id:
        c["id"] = id
    if name:
        c["name"] = name
    c["owner"] = owner
    if pos is not None:
        c["pos"] = list(pos)
    return c
