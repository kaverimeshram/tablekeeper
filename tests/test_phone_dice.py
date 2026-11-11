import asyncio
import json
import re
import sys
import types
import unittest
from unittest import mock

from tests.test_integration import GM, LoadedPlugin


class Task:
    def __init__(self, coro):
        self.coro = coro

    def add_done_callback(self, callback):
        self.callback = callback

    def run(self):
        asyncio.run(self.coro)


class Bot:
    def __init__(self):
        self.sent = []
        self.edited = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return types.SimpleNamespace(message_id=71)

    async def edit_message_text(self, **kwargs):
        self.edited.append(kwargs)


class App:
    def __init__(self):
        self.bot = Bot()
        self.handlers = []
        self.tasks = []

    def add_handler(self, handler):
        self.handlers.append(handler)

    def create_task(self, coro):
        task = Task(coro)
        self.tasks.append(task)
        return task

    def run_tasks(self):
        tasks, self.tasks = self.tasks, []
        for task in tasks:
            task.run()


class FakeCtx:
    def __init__(self):
        self.injected = []
        self.posted = []
        self.accept_injection = True
        self.post_ok = True

    def inject_message(self, text, role="user", *, origin=None, session_key=None):
        self.injected.append((text, role, origin))
        return self.accept_injection

    def post_message(self, text):
        self.posted.append(text)
        return types.SimpleNamespace(ok=self.post_ok)

    def spawn_task(self, coro, name=None):
        coro.close()


class FakeButton:
    def __init__(self, text, callback_data):
        self.text, self.callback_data = text, callback_data


class FakeMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class FakeCallbackQueryHandler:
    def __init__(self, callback, pattern=None):
        self.callback, self.pattern = callback, pattern

    def check_update(self, update):
        return bool(re.search(self.pattern, update.callback_query.data))


class Query:
    def __init__(self, data, user, chat_id):
        self.data = data
        self.from_user = types.SimpleNamespace(id=user)
        self.message = types.SimpleNamespace(chat_id=chat_id)
        self.answers = []
        self.edits = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, text):
        self.edits.append(text)


class PhoneDiceTests(LoadedPlugin):
    def setUp(self):
        super().setUp()
        self.old_ctx, self.old_app = self.plugin._CTX, self.plugin._TELEGRAM_APP
        self.ctx, self.app = FakeCtx(), App()
        self.plugin._CTX, self.plugin._TELEGRAM_APP = self.ctx, self.app
        self.addCleanup(self.restore_globals)
        self.install_callback()

    def tearDown(self):
        self.app.run_tasks()

    def restore_globals(self):
        self.plugin._CTX, self.plugin._TELEGRAM_APP = self.old_ctx, self.old_app

    def install_callback(self):
        telegram = types.ModuleType("telegram")
        telegram.InlineKeyboardButton = FakeButton
        telegram.InlineKeyboardMarkup = FakeMarkup
        ext = types.ModuleType("telegram.ext")
        ext.CallbackQueryHandler = FakeCallbackQueryHandler
        patcher = mock.patch.dict(sys.modules, {"telegram": telegram, "telegram.ext": ext})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.plugin._telegram_factory(self.app, None)
        self.handler = self.app.handlers[-1]

    def command(self, line, *, user=GM, chat):
        from hermes_cli.plugins import get_plugin_command_handler
        source = types.SimpleNamespace(platform=types.SimpleNamespace(value="telegram"), chat_id=chat,
                                       user_id=user, user_name=f"user-{user}")
        return get_plugin_command_handler("table")(line, session_id="phone-test", platform="telegram", source=source)

    def setup_fight(self, chat, seed=23):
        self.seed(seed)
        self.assertTrue(self.call("tk_new_campaign", {"scene": "Phone test"}, chat=chat)["ok"])
        self.assertTrue(self.call("tk_claim_character", {"character": "fighter"}, chat=chat)["ok"])
        self.assertTrue(self.call("tk_start_combat", {"monsters": [{"type": "goblin", "x": 1, "y": 5}]}, chat=chat)["ok"])
        self.assertEqual(self.state(chat)["active"], "fighter")

    def tap(self, chat, throw_id, user=GM):
        query = Query(f"tk:throw:{throw_id}", user, chat)
        asyncio.run(self.handler.callback(types.SimpleNamespace(callback_query=query), None))
        return query

    def test_phone_attack_defers_then_resolves_same_seeded_action(self):
        phone_chat, auto_chat = "phone-attack", "auto-attack"
        self.setup_fight(phone_chat)
        self.setup_fight(auto_chat)
        self.assertIn("phone", self.command("dice phone", chat=phone_chat).lower())
        self.assertEqual(self.state(phone_chat)["phone_timeout"], 120)
        self.assertIn("auto", self.command("dice auto", chat=auto_chat).lower())
        self.seed(87)
        rng_state = self.plugin.RNG.getstate()
        before_hp = self.creature(phone_chat, "goblin-1")["hp"]
        pending = self.call("tk_attack", {"character": "fighter", "target": "goblin-1"}, chat=phone_chat)
        self.assertTrue(pending["ok"], pending)
        self.assertEqual(self.plugin.RNG.getstate(), rng_state)
        self.assertEqual(self.creature(phone_chat, "goblin-1")["hp"], before_hp)
        self.assertEqual(self.state(phone_chat)["pending_throw"]["character"], "Brann Hollis")
        self.app.run_tasks()
        button = self.app.bot.sent[0]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.callback_data, f"tk:throw:{pending['pending_throw']}")
        self.assertEqual(button.text, "🎲 Throw d20 · Brann Hollis")
        self.seed(87)
        immediate = self.call("tk_attack", {"character": "fighter", "target": "goblin-1"}, chat=auto_chat)
        self.seed(87)
        query = self.tap(phone_chat, pending["pending_throw"])
        self.assertEqual(self.creature(phone_chat, "goblin-1")["hp"], self.creature(auto_chat, "goblin-1")["hp"])
        self.assertEqual(json.loads(self.ctx.injected[-1][0])["attack_total"], immediate["attack_total"])
        self.assertIn("vs AC", query.edits[0])
        self.assertIn("threw", query.edits[0])
        self.assertEqual(self.ctx.injected[-1][1], "user")
        self.assertEqual(self.state(phone_chat)["last_thrown_by"], "phone")
        self.assertEqual(immediate["ok"], True)
        from gateway.session_context import clear_session_vars, set_session_vars
        self.assertIn(f"telegram:{phone_chat}", self.plugin._PHONE_NUMBERS)
        tokens = set_session_vars(platform="telegram", chat_id=phone_chat, user_id=GM, actor_id=GM, user_name="user-1001")
        try:
            self.plugin._turn_hook(session_id="phone-narration")
            self.assertIn(immediate["attack_total"], self.plugin._TURNS["phone-narration"]["numbers"])
            self.assertIsNone(self.plugin._guard(response_text=f"Brann Hollis rolled a {immediate['attack_total']}.",
                                                 session_id="phone-narration"))
        finally:
            clear_session_vars(tokens)

    def test_wrong_owner_and_repeated_tap_do_not_resolve_twice(self):
        chat = "phone-owner"
        self.setup_fight(chat)
        self.command("dice phone", chat=chat)
        pending = self.call("tk_attack", {"character": "fighter", "target": "goblin-1"}, chat=chat)
        before = self.state(chat)
        stale = self.tap(chat, "ffffffff")
        self.assertEqual(stale.answers, [("This throw is done.", False)])
        self.assertEqual(self.state(chat), before)
        wrong = self.tap(chat, pending["pending_throw"], user="9999")
        self.assertEqual(wrong.answers, [("Not your die. user-1001 throws for Brann Hollis.", False)])
        self.assertEqual(self.state(chat), before)
        owner = self.tap(chat, pending["pending_throw"])
        hp = self.creature(chat, "goblin-1")["hp"]
        stale = self.tap(chat, pending["pending_throw"])
        self.assertEqual(stale.answers, [("This throw is done.", False)])
        self.assertEqual(self.creature(chat, "goblin-1")["hp"], hp)
        self.assertEqual(len(owner.edits), 1)

    def test_invalid_action_and_second_roll_do_not_create_or_replace_pending(self):
        chat = "phone-validation"
        self.setup_fight(chat)
        self.command("dice phone", chat=chat)
        camp = self.plugin._load({"chat": f"telegram:{chat}"})
        camp["creatures"][1]["pos"] = [11, 9]
        self.plugin._save(camp)
        invalid = self.call("tk_attack", {"character": "fighter", "target": "goblin-1", "attack": "longsword"}, chat=chat)
        self.assertEqual(invalid["refused"], "out_of_range")
        self.assertIsNone(self.plugin._load({"chat": f"telegram:{chat}"})["pending_throw"])
        camp = self.plugin._load({"chat": f"telegram:{chat}"})
        camp["creatures"][1]["pos"] = [1, 5]
        camp["active"] = "goblin-1"
        self.plugin._save(camp)
        wrong_turn = self.call("tk_attack", {"character": "fighter", "target": "goblin-1"}, chat=chat)
        self.assertEqual(wrong_turn["refused"], "not_your_turn")
        camp = self.plugin._load({"chat": f"telegram:{chat}"})
        camp["active"] = "fighter"
        self.plugin._save(camp)
        pending = self.call("tk_attack", {"character": "fighter", "target": "goblin-1"}, chat=chat)
        self.assertTrue(pending.get("pending_throw"), pending)
        blocked = self.call("tk_save", {"character": "fighter", "ability": "str", "dc": 10}, chat=chat)
        self.assertEqual(blocked["error"], "waiting for Brann Hollis to throw")
        reserved = self.call("tk_move", {"character": "fighter", "square": "A4", "disengage": True}, chat=chat)
        self.assertEqual(reserved["refused"], "action_used")
        next_turn = self.call("tk_next_turn", {}, chat=chat)
        self.assertIn("waiting for Brann Hollis", next_turn["error"])

    def test_expiry_auto_rolls_and_non_telegram_falls_back(self):
        chat = "phone-expiry"
        self.setup_fight(chat)
        self.command("dice phone 15", chat=chat)
        pending = self.call("tk_check", {"character": "fighter", "skill_or_ability": "athletics", "dc": 10}, chat=chat)
        self.app.run_tasks()
        with mock.patch("tablekeeper.time.time", return_value=self.plugin._load({"chat": f"telegram:{chat}"})["pending_throw"]["created_at"] + 16):
            self.plugin._expire_pending(f"telegram:{chat}")
        self.assertIsNone(self.state(chat)["pending_throw"])
        self.assertEqual(self.state(chat)["last_thrown_by"], "auto")
        self.assertIn("auto-thrown after", json.dumps(self.ctx.injected[-1][0]))
        self.app.run_tasks()
        self.assertTrue(self.app.bot.edited)
        self.call("tk_new_campaign", {"replace": True}, platform="cli", chat="")
        self.call("tk_claim_character", {"character": "fighter"}, platform="cli", chat="")
        local_source = types.SimpleNamespace(platform=types.SimpleNamespace(value="cli"), chat_id="", user_id="local", user_name="local")
        self.plugin._command("dice phone", platform="cli", source=local_source)
        local = self.call("tk_check", {"character": "fighter", "skill_or_ability": "athletics", "dc": 10}, platform="cli", chat="")
        self.assertIn("unavailable", local["note"].lower())
        self.assertTrue(local["ok"])
        self.assertTrue(pending["ok"])
        no_app_chat = "phone-no-app"
        self.setup_fight(no_app_chat)
        self.command("dice phone", chat=no_app_chat)
        app, self.plugin._TELEGRAM_APP = self.plugin._TELEGRAM_APP, None
        try:
            immediate = self.call("tk_check", {"character": "fighter", "skill_or_ability": "athletics", "dc": 10}, chat=no_app_chat)
        finally:
            self.plugin._TELEGRAM_APP = app
        self.assertTrue(immediate["ok"])
        self.assertIn("unavailable", immediate["note"].lower())

    def test_auto_mode_and_monsters_roll_immediately(self):
        chat = "phone-auto"
        self.setup_fight(chat)
        check = self.call("tk_check", {"character": "fighter", "skill_or_ability": "athletics", "dc": 10}, chat=chat)
        self.assertTrue(check["ok"])
        self.assertNotIn("pending_throw", check)
        self.assertEqual(self.state(chat)["last_thrown_by"], "engine")

    def test_monster_turns_stay_engine_rolled_in_phone_mode(self):
        chat = "phone-monster"
        self.seed(31)
        self.call("tk_new_campaign", {"scene": "Phone monster"}, chat=chat)
        self.call("tk_claim_character", {"character": "fighter"}, chat=chat)
        self.command("dice phone", chat=chat)
        started = self.call("tk_start_combat", {"monsters": [{"type": "goblin", "x": 1, "y": 5}]}, chat=chat)
        self.assertTrue(started["ok"], started)
        self.assertIsNone(self.state(chat)["pending_throw"])
        self.assertEqual(self.state(chat)["last_thrown_by"], "engine")

    def test_spell_attack_and_save_use_phone_resolution(self):
        chat = "phone-spell"
        self.seed(9)
        self.call("tk_new_campaign", {"scene": "Phone spell"}, chat=chat)
        self.call("tk_claim_character", {"character": "wizard"}, chat=chat)
        self.call("tk_start_combat", {"monsters": [{"type": "goblin", "x": 1, "y": 5}]}, chat=chat)
        self.command("dice phone", chat=chat)
        cast = self.call("tk_cast", {"character": "wizard", "spell": "scorching ray", "targets": ["goblin-1"]}, chat=chat)
        self.assertTrue(cast.get("pending_throw"), cast)
        self.tap(chat, cast["pending_throw"])
        self.assertEqual(self.state(chat)["last_thrown_by"], "phone")
        save = self.call("tk_save", {"character": "wizard", "ability": "wis", "dc": 12}, chat=chat)
        self.assertTrue(save.get("pending_throw"), save)
        self.tap(chat, save["pending_throw"])
        self.assertEqual(self.state(chat)["last_thrown_by"], "phone")

    def test_death_save_uses_phone_resolution(self):
        chat = "phone-death-save"
        self.seed(11)
        self.call("tk_new_campaign", {"scene": "Phone death save"}, chat=chat)
        self.call("tk_claim_character", {"character": "fighter"}, chat=chat)
        self.call("tk_start_combat", {"monsters": [{"type": "goblin", "x": 1, "y": 5}]}, chat=chat)
        self.command("dice phone", chat=chat)
        camp = self.plugin._load({"chat": f"telegram:{chat}"})
        fighter = next(c for c in camp["creatures"] if c["id"] == "fighter")
        fighter["hp"], camp["active"] = 0, "fighter"
        self.plugin._save(camp)
        pending = self.call("tk_death_save", {"character": "fighter"}, chat=chat)
        self.assertTrue(pending.get("pending_throw"), pending)
        self.tap(chat, pending["pending_throw"])
        self.assertEqual(json.loads(self.ctx.injected[-1][0])["thrown_by"], "phone")
        death_roll = next(r for r in reversed(self.plugin._load({"chat": f"telegram:{chat}"})["rolls"])
                          if r["kind"] == "death")
        self.assertEqual(death_roll["thrown_by"], "phone")

    def test_injection_refusal_uses_post_message_and_reports_failure(self):
        pending = {"chat_id": "42", "owner": "1001", "owner_name": "Ann"}
        self.ctx.accept_injection = False
        self.plugin._notify_result(pending, '{"ok": true}')
        self.assertEqual(self.ctx.posted, ['{"ok": true}'])
        self.ctx.post_ok = False
        with self.assertRaisesRegex(RuntimeError, "could not wake the session"):
            self.plugin._notify_result(pending, '{"ok": true}')

    def test_callback_pattern_is_scoped_and_gm_setting_is_enforced(self):
        update = lambda data: types.SimpleNamespace(callback_query=types.SimpleNamespace(data=data))
        self.assertEqual(self.handler.pattern, r"^tk:throw:[0-9a-f]{8}$")
        self.assertTrue(self.handler.check_update(update("tk:throw:0123abcd")))
        self.assertFalse(self.handler.check_update(update("approve:7")))
        self.assertFalse(self.handler.check_update(update("tk:throw:xyz")))
        chat = "phone-gm"
        self.setup_fight(chat)
        self.assertIn("Only the game master", self.command("dice phone", user="1002", chat=chat))
        self.assertIn("Dice mode: phone", self.command("dice phone 60", chat=chat))
        self.assertEqual(self.state(chat)["phone_timeout"], 60)


if __name__ == "__main__":
    unittest.main()
