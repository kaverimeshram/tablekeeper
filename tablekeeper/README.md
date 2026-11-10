# Tablekeeper

Tablekeeper turns a Hermes chat into a tabletop campaign table. Python rolls every die and owns hit points, positions, initiative and turn order, so the model narrates results it cannot change. Each player controls only the character they claimed, and in combat only on that character's turn. Monsters play their own turns, from SRD 5.1 stat blocks, the moment a player ends theirs.

![Tablekeeper Desktop page: battle grid, initiative and dice tray](https://raw.githubusercontent.com/kaverimeshram/tablekeeper/main/docs/pane.png)

```text
Alice (game master): /table new A goblin cave
Alice:               /table claim fighter
Bob:                 /table claim rogue
Alice:               Two goblins jump us!
  tk_start_combat   -> initiative: Pip 21, Goblin 1 17, Brann 17, Goblin 2 9. Pip's turn.
Alice:               Brann charges in and swings!
  tk_attack         -> refused: not_your_turn. It is Pip Underbough's turn, not Brann Hollis's.
Alice:               Then I take Pip's turn for him.
  tk_attack         -> refused: not_owner. Pip Underbough belongs to another player.
Bob:                 Pip sprints up and looses his shortbow at the nearest goblin.
  tk_move           -> (0,4) to (5,4), 25 ft, 0 ft left
  tk_attack         -> d20 6 + 5 = 11 against AC 15: miss
Bob:                 Pip's done.
  tk_next_turn      -> Goblin 1 runs 25 ft to (6,3), scimitar: d20 17 + 4 = 21 against AC 14, hit for 6 slashing. Pip 18/24 HP. Brann's turn.
Hermes:              The goblin skids in under Pip's guard and opens a gash across his arm. Pip, 18 of 24. Brann, you are up.
```

## What it does

- **Authoritative state.** A SQLite campaign per chat holds every creature, position, condition, initiative slot, roll and log line. A narration guard appends a visible correction when the model states a number no tool produced, a roll a player only claimed, or an action by a creature at 0 HP.
- **SRD 5.1 content.** Twelve monsters, four level 3 characters (fighter, rogue, wizard, cleric) and fourteen spells with their SRD numbers, on a 12 by 10 grid at 5 ft per square. Advantage and disadvantage cancel, critical hits double dice only, resistance halves and rounds down, temporary hit points absorb first, damage at 0 HP costs death saves, concentration is checked, opportunity attacks fire.
- **Monster turns without prompting.** `tk_next_turn` plays every monster turn up to the next player character and returns what each monster did, so the model narrates a complete round from one call.
- **Identity.** The sender comes from the gateway turn context (`HERMES_SESSION_ACTOR_ID`, falling back to `HERMES_SESSION_USER_ID`), and the campaign is keyed by platform and chat id. A message without an identified sender can claim and move nothing. The local CLI, TUI and Desktop user owns every character.
- **Game master.** The player who starts the campaign adjudicates with `tk_start_combat`, `tk_damage`, `tk_heal`, `tk_condition` and a long `tk_rest`. Players cannot.

## Tools

| Tool | Who | What it does |
|---|---|---|
| `tk_new_campaign` | anyone, then game master | Starts a campaign in this chat. |
| `tk_claim_character` | anyone | Claims fighter, rogue, wizard or cleric. One per player. |
| `tk_state` | anyone | Grid, initiative, HP, positions, conditions, who the sender controls. |
| `tk_roll` | anyone | Plain dice such as `2d6+3` or `4d6kh3`, logged to the dice tray. |
| `tk_check`, `tk_save` | character owner | Ability or skill check, saving throw. |
| `tk_attack` | owner, on their turn | To-hit against AC, cover, damage, range and reach. |
| `tk_cast` | owner, on their turn | Slots, attacks, saves, upcasting, concentration. |
| `tk_move` | owner, on their turn | Speed limited movement, opportunity attacks, disengage. |
| `tk_death_save` | owner, on their turn | Death saving throw; ends the turn. |
| `tk_next_turn` | owner of the active character | Ends the turn and plays the monsters. |
| `tk_rest` | owner (short), game master (long) | Hit dice, full recovery. Outside combat. |
| `tk_start_combat` | game master | Spawns monsters at positions, rolls initiative. |
| `tk_damage`, `tk_heal`, `tk_condition` | game master | Rulings for traps, hazards and story effects. |
| `tk_recap` | anyone | The story so far for a previously-on summary. |

A refused action comes back as a result with `refused` and a `message`; the model relays it to the player.

## Command

`/table status`, `/table map`, `/table log`, `/table recap`, `/table claim <character>`, `/table new [scene]`, `/table end`.

`/table map` prints the grid in a monospace block that renders on Telegram and Discord. `/table end` ends the running combat (game master). `/table new confirm` replaces a campaign that already has characters.

## Setup

```bash
hermes plugins install kaverimeshram/tablekeeper/tablekeeper --enable
```

The `tablekeeper` toolset turns on with the plugin. Requires Hermes 0.23.1 or newer. Send `/table new` in the chat where the game happens.

## What it touches

- **Storage.** `<hermes home>/plugin-data/tablekeeper/campaigns.sqlite3`, resolved per profile, WAL mode, file mode 0600. The Desktop pane and dashboard route open it read-only.
- **Prompt.** In a chat that has a campaign, a compact state summary of at most about 600 tokens is added to each turn, and the reply passes through the narration guard. Chats without a campaign are untouched.
- **Network and processes.** None. The plugin makes no network requests, starts no subprocess and reads no credentials.
- **Identity.** Platform, chat id and sender id from the turn context, used as the campaign and owner keys.

## SRD attribution

This work includes material taken from the System Reference Document 5.1 ("SRD 5.1") by Wizards of the Coast LLC and available at https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1 is licensed under the Creative Commons Attribution 4.0 International License available at https://creativecommons.org/licenses/by/4.0/legalcode. See [NOTICE](NOTICE).

## Tests

```bash
python -m unittest discover -s tests -t .
```

`tests/test_integration.py` loads the plugin through Hermes' own loader in a temporary Hermes home and drives every tool through the registry, including a seeded three round combat, identity and turn refusals, persistence across a reload, per profile storage and the narration guard.
