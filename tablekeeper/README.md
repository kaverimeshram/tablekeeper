# Tablekeeper

Tablekeeper runs shared tabletop campaigns in Hermes group chats. Python code owns dice, hit points, initiative, character ownership, and combat results. Hermes narrates the structured outcomes.

Example:

```text
Player: /table claim fighter
Hermes: Fighter claimed. What do you do?
Player: Attack the goblin.
Hermes: tk_attack rolls 17 + 5 against AC 15. Hit for 7 damage. The goblin has 8 HP.
```

Tools: `tk_state`, `tk_roll`, `tk_check`, `tk_attack`, `tk_cast`, `tk_damage`, `tk_start_combat`, `tk_next_turn`, `tk_monster_turn`, `tk_rest`, `tk_claim_character`.

Command: `/table status|map|log|recap|claim <character>|new`.

Install the `tablekeeper/` directory as a Hermes plugin and enable it. Campaign SQLite data lives in Hermes's profile scoped plugin data directory. The desktop pane reads the same data through the plugin route. The plugin makes no network requests and reads or writes files only under its plugin data directory during campaign play.

The game mechanics, character options, spells, and bestiary are adapted from the System Reference Document 5.1, © 2016, 2020 Wizards of the Coast LLC, licensed under CC-BY-4.0. See [NOTICE](NOTICE) for attribution.

Run tests with `python -m unittest discover -s tests`.
