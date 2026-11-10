# Tablekeeper

Tablekeeper runs shared tabletop campaigns in Hermes group chats. Python code owns dice, hit points, initiative, character ownership, and combat results. Hermes narrates the structured outcomes.

Example:

```text
Player: /table claim fighter
Hermes: Fighter claimed. What do you do?
Player: Attack the goblin.
Hermes: tk_attack rolls 17 + 5 against AC 15. Hit for 7 damage. The goblin has 8 HP.
```

Tools: `tk_state`, `tk_roll`, `tk_check`, `tk_attack`, `tk_cast`, `tk_damage`, `tk_start_combat`, `tk_next_turn`, `tk_monster_turn`, `tk_rest`, `tk_condition`, `tk_death_save`, `tk_claim_character`.

Command: `/table status|map|log|recap|claim <character>|new`.

Install the `tablekeeper/` directory as a Hermes plugin and enable it. Campaign SQLite data lives in Hermes's profile scoped plugin data directory. The desktop pane reads the same data through the plugin route. The plugin makes no network requests and reads or writes files only under its plugin data directory during campaign play.

This work includes material taken from the System Reference Document 5.1 (“SRD 5.1”) by Wizards of the Coast LLC and available at https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1 is licensed under the Creative Commons Attribution 4.0 International License available at https://creativecommons.org/licenses/by/4.0/legalcode. Tablekeeper adapts those rules and statistics as code-owned campaign mechanics. See [NOTICE](NOTICE) for attribution.

Run tests with `python -m unittest discover -s tests`.
