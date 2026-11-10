"""Desktop pane backend and renderer: read-only route, store parity, inert strings.

Run from the repository root with the Hermes interpreter:
    PYTHONPATH=<hermes>:. <hermes>/.venv/bin/python -m unittest tests.test_dashboard
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PLUGIN = Path(__file__).resolve().parent.parent / "tablekeeper"
HOSTILE = "<script>alert(1)</script>"
HOSTILE_ATTR = '"><img src=x onerror=alert(2)>'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def creature(cid, name, kind="pc", **extra):
    base = {"id": cid, "name": name, "kind": kind, "owner": "1001", "ac": 14, "hp": 10, "max_hp": 12, "temp_hp": 0,
            "conditions": [], "death_saves": {"s": 0, "f": 0}, "pos": [2, 3], "status": "ok"}
    return {**base, **extra}


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="tk-dash-")).resolve()
        self.old_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(self.home)
        self.store = load("tk_store_under_test", PLUGIN / "store.py")
        self.api = load("tk_dashboard_api_under_test", PLUGIN / "dashboard" / "plugin_api.py")
        app = FastAPI()
        app.include_router(self.api.router, prefix="/api/plugins/tablekeeper")
        self.client = TestClient(app)
        self.base = "/api/plugins/tablekeeper"
        self.db_path = self.home / "plugin-data" / "tablekeeper" / self.api.DB_NAME

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.old_home
        shutil.rmtree(self.home, ignore_errors=True)

    def seed(self, chat="telegram:42", **fields):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        db = self.store.connect(self.db_path)
        state = self.store.create(db, chat, "1001")
        state.update(scene=fields.pop("scene", "Goblin cave"), round=2, active="fighter", in_combat=True,
                     creatures=fields.pop("creatures", [creature("fighter", "Brann"), creature("goblin-1", "Goblin", "monster", hp=3)]),
                     initiative=["fighter", "goblin-1"])
        self.store.save(db, state, rolls=fields.pop("rolls", [{"who": "fighter", "name": "Brann", "kind": "attack", "dice": [17], "natural": 17, "modifier": 5, "total": 22, "formula": "1d20+5"}]),
                        log=fields.pop("log", [("attack", "Brann hits Goblin")]))
        db.close()

    def digest(self):
        """Main database bytes plus every WAL byte: reading may open the -shm index, it may not add data."""
        wal = self.db_path.with_name(self.db_path.name + "-wal")
        return hashlib.sha256(self.db_path.read_bytes()).hexdigest(), (wal.read_bytes() if wal.exists() else b"")

    def test_no_database_yet_is_an_empty_table_and_creates_nothing(self):
        self.assertEqual(self.client.get(f"{self.base}/campaigns").json(), {"campaigns": []})
        self.assertEqual(self.client.get(f"{self.base}/campaign").json(), {"campaign": None})
        self.assertFalse(self.db_path.exists())

    def test_campaign_is_exactly_the_store_snapshot(self):
        self.seed()
        db = self.store.connect(self.db_path)
        expected = self.store.load(db, "telegram:42")
        db.close()
        got = self.client.get(f"{self.base}/campaign").json()["campaign"]
        self.assertEqual(got, expected)
        self.assertEqual([c["id"] for c in got["creatures"]], ["fighter", "goblin-1"])
        self.assertEqual(got["initiative"], ["fighter", "goblin-1"])
        self.assertEqual((got["round"], got["active"], got["in_combat"]), (2, "fighter", True))
        self.assertEqual(got["rolls"][0]["total"], 22)
        self.assertEqual(got["log"][0]["text"], "Brann hits Goblin")
        self.assertEqual(got["creatures"][0]["pos"], [2, 3])

    def test_chat_selection_latest_default_and_unknown_chat(self):
        self.seed("telegram:1", scene="First")
        self.seed("telegram:2", scene="Second")
        listing = self.client.get(f"{self.base}/campaigns").json()["campaigns"]
        self.assertEqual([c["chat"] for c in listing], ["telegram:2", "telegram:1"])
        self.assertEqual(listing[0]["creatures"], 2)
        self.assertEqual(self.client.get(f"{self.base}/campaign").json()["campaign"]["scene"], "Second")
        self.assertEqual(self.client.get(f"{self.base}/campaign", params={"chat": "telegram:1"}).json()["campaign"]["scene"], "First")
        self.assertEqual(self.client.get(f"{self.base}/campaign", params={"chat": "telegram:404"}).status_code, 404)
        self.assertEqual(self.client.get(f"{self.base}/campaign", params={"chat": "x" * 300}).status_code, 422)

    def test_route_never_writes(self):
        self.seed()
        before = self.digest()
        for _ in range(3):
            self.client.get(f"{self.base}/campaign")
            self.client.get(f"{self.base}/campaigns")
        for method in ("post", "put", "patch", "delete"):
            for path in ("campaign", "campaigns"):
                self.assertEqual(getattr(self.client, method)(f"{self.base}/{path}").status_code, 405, (method, path))
        self.assertEqual(self.digest(), before)
        self.assertEqual({r.methods.pop() for r in self.api.router.routes}, {"GET"})

    def test_connection_is_physically_read_only(self):
        self.seed()
        db = self.api._open_readonly()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM creatures")
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("INSERT INTO log(chat, ts, kind, text) VALUES('x', 0, 'k', 't')")
        finally:
            db.close()

    def test_newer_schema_is_reported_not_guessed(self):
        self.seed()
        db = sqlite3.connect(self.db_path)
        db.execute("PRAGMA user_version=99")
        db.close()
        res = self.client.get(f"{self.base}/campaign")
        self.assertEqual(res.status_code, 503)
        self.assertIn("schema v99", res.json()["detail"])

    def test_hostile_strings_travel_as_inert_json(self):
        self.seed(scene=HOSTILE, creatures=[creature("fighter", HOSTILE, owner=HOSTILE_ATTR, conditions=[HOSTILE])],
                  rolls=[{"who": HOSTILE, "name": HOSTILE, "kind": HOSTILE_ATTR, "why": HOSTILE, "dice": [4], "total": 4, "formula": "1d4"}],
                  log=[(HOSTILE_ATTR, HOSTILE)])
        res = self.client.get(f"{self.base}/campaign")
        self.assertTrue(res.headers["content-type"].startswith("application/json"))
        state = res.json()["campaign"]
        self.assertEqual(state["scene"], HOSTILE)
        self.assertEqual(state["creatures"][0]["name"], HOSTILE)
        self.assertEqual(state["log"][0]["text"], HOSTILE)


NODE = shutil.which("node")
SDK_SHIM = "export const PANES_AREA='panes',ROUTES_AREA='routes',SIDEBAR_NAV_AREA='sidebar.nav';export const relativeTime=()=>'now'\n"
REACT_SHIM = """
const flat = k => k.flat(Infinity).filter(x => x !== null && x !== undefined && x !== false)
export const createElement = (type, props, ...kids) => ({ type, props: { ...(props || {}), children: flat(kids) } })
export const useEffect = () => {}
export const useId = () => ':r0:'
export const useRef = v => ({ current: v })
export const useState = v => [typeof v === 'function' ? v() : v, () => {}]
"""
HARNESS = """
import plugin, { buildModel, TabletopView, creatureView, rollView } from './plugin.mjs'
const hostile = JSON.parse(process.env.TK_HOSTILE)
const expand = (el, out) => {
  if (el === null || el === undefined || el === false) return
  if (typeof el === 'string' || typeof el === 'number') { out.texts.push(String(el)); return }
  if (typeof el.type === 'function') return expand(el.type(el.props), out)
  out.tags.add(el.type)
  for (const [k, v] of Object.entries(el.props)) if (k !== 'children') out.attrs.push([el.type, k, typeof v === 'object' ? JSON.stringify(v) : String(v)])
  for (const c of el.props.children) expand(c, out)
}
const campaign = {
  chat: hostile.text, scene: hostile.text, round: 2, active: 'a', in_combat: true, initiative: ['a', hostile.text],
  creatures: [
    { id: 'a', name: hostile.text, kind: 'pc', owner: hostile.attr, hp: 5, max_hp: 9, conditions: [hostile.text, 'prone'], pos: [1, 1], concentration: hostile.text },
    { id: hostile.text, name: hostile.attr, kind: 'monster', hp: 0, max_hp: 7, conditions: [], pos: [99, -4] }
  ],
  rolls: [{ seq: 1, ts: 1, name: hostile.text, kind: hostile.attr, why: hostile.text, type: hostile.text, formula: '1d20', dice: [20], natural: 20, modifier: 2, total: 22, crit: true }],
  log: [{ seq: 1, ts: 1, kind: hostile.attr, text: hostile.text }]
}
const data = { status: 'live', campaign, campaigns: [{ chat: hostile.text, scene: hostile.attr }, { chat: 'b', scene: 'b' }], error: '', chat: hostile.text, pick: () => {} }
const out = { tags: new Set(), attrs: [], texts: [] }
expand(TabletopView({ data, model: buildModel(campaign), floats: [{ id: 'f', key: 'a', delta: -3 }], fresh: new Set([1]), uid: 'u' }), out)
const registered = []
plugin.register({ registerMany: cs => registered.push(...cs), onDispose: () => {} })
const longName = creatureView({ id: 'x', name: 'n'.repeat(500), hp: 4, max_hp: 4, pos: [50, 50], death_saves: { f: 3 } }, 0)
const roll = rollView({ formula: 'f'.repeat(500), dice: Array(200).fill(3), total: 'NaN' })
console.log(JSON.stringify({ tags: [...out.tags], attrs: out.attrs, texts: out.texts, registered: registered.map(c => [c.id, c.area, c.data || null]), longName, roll }))
"""


@unittest.skipUnless(NODE, "node is required to render the pane")
class PaneRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (PLUGIN / "desktop" / "plugin.js").read_text()
        work = Path(tempfile.mkdtemp(prefix="tk-pane-"))
        cls.addClassCleanup(shutil.rmtree, work, ignore_errors=True)
        rewritten = cls.source.replace("from 'react'", "from './react.mjs'").replace("from '@hermes/plugin-sdk'", "from './sdk.mjs'")
        (work / "plugin.mjs").write_text(rewritten)
        (work / "react.mjs").write_text(REACT_SHIM)
        (work / "sdk.mjs").write_text(SDK_SHIM)
        (work / "run.mjs").write_text(HARNESS)
        env = {"PATH": os.environ.get("PATH", ""), "TK_HOSTILE": json.dumps({"text": HOSTILE, "attr": HOSTILE_ATTR})}
        run = subprocess.run([NODE, "run.mjs"], cwd=work, env=env, capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stderr
        cls.out = json.loads(run.stdout)

    def test_hostile_strings_render_only_as_text(self):
        self.assertTrue(any(HOSTILE in t for t in self.out["texts"]), "the string must be visible, as text")
        self.assertTrue(any(HOSTILE_ATTR in t for t in self.out["texts"]))
        self.assertFalse({"script", "img", "iframe", "a", "object", "embed", "link"} & set(self.out["tags"]))
        for tag, key, value in self.out["attrs"]:
            self.assertNotIn(key, {"dangerouslySetInnerHTML", "href", "src", "srcDoc", "action", "formAction"}, (tag, key))
            if tag != "select":
                self.assertFalse(key.startswith("on"), (tag, key))
            if tag == "style":
                self.assertNotIn("alert", value)
        style_text = [t for t in self.out["texts"] if ".tk{" in t]
        self.assertEqual(len(style_text), 1)
        self.assertNotIn("alert", style_text[0])

    def test_no_raw_html_or_host_escape_sinks_in_source(self):
        banned = ["innerHTML", "outerHTML", "insertAdjacentHTML", "dangerouslySetInnerHTML", "__html", "document.write",
                  "eval(", "new Function", "postMessage", "window.hermesDesktop", "localStorage", "sessionStorage",
                  "document.cookie", "fetch(", "XMLHttpRequest", "WebSocket", "<script", "javascript:"]
        for token in banned:
            self.assertNotIn(token, self.source, token)

    def test_only_documented_sdk_surfaces_and_specifiers(self):
        specifiers = set(re.findall(r"""from\s+['"]([^'"]+)['"]""", self.source)) | set(re.findall(r"""import\s*\(\s*['"]([^'"]+)""", self.source))
        self.assertEqual(specifiers, {"react", "@hermes/plugin-sdk"})
        used = set(re.findall(r"ctx\.(\w+)", self.source))
        self.assertLessEqual(used, {"rest", "setInterval", "setTimeout", "onEvent", "storage", "registerMany", "onDispose", "addEventListener"})
        sdk = re.search(r"import \{([^}]*)\} from '@hermes/plugin-sdk'", self.source).group(1)
        self.assertEqual({n.strip() for n in sdk.split(",")}, {"PANES_AREA", "ROUTES_AREA", "SIDEBAR_NAV_AREA", "relativeTime"})

    def test_colours_come_from_host_tokens_only(self):
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", self.source))
        self.assertIsNone(re.search(r"\brgba?\(|\bhsla?\(", self.source))
        self.assertIsNone(re.search(r"\bfill: '(?:black|white|red|green|blue)'", self.source))

    def test_registers_pane_page_and_nav(self):
        by_id = {c[0]: c for c in self.out["registered"]}
        self.assertEqual(set(by_id), {"battle", "page", "nav"})
        self.assertEqual(by_id["battle"][1:], ["panes", {"placement": "right", "width": "480px"}])
        self.assertEqual(by_id["page"][2], {"path": "/tabletop"})
        self.assertEqual(by_id["nav"][2]["path"], "/tabletop")

    def test_untrusted_numbers_and_lengths_are_bounded(self):
        c = self.out["longName"]
        self.assertLessEqual(len(c["name"]), 60)
        self.assertEqual(c["pos"], [11, 9])
        self.assertEqual(c["state"], "dead")
        r = self.out["roll"]
        self.assertLessEqual(len(r["formula"]), 64)
        self.assertLessEqual(len(r["dice"]), 40)
        self.assertEqual(r["total"], 0)


if __name__ == "__main__":
    unittest.main()
