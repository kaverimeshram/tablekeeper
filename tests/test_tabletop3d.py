"""3D tabletop: the maths behind it, run with node against the real plugin.js.

Run from the repository root with the Hermes interpreter:
    PYTHONPATH=<hermes>:. <hermes>/.venv/bin/python -m unittest tests.test_tabletop3d
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "tablekeeper" / "desktop" / "plugin.js"
NODE = shutil.which("node")
REACT_SHIM = "export const createElement=()=>null,useEffect=()=>{},useId=()=>'x',useRef=v=>({current:v}),useState=v=>[v,()=>{}]\n"
SDK_SHIM = "export const PANES_AREA='panes',ROUTES_AREA='routes',SIDEBAR_NAV_AREA='nav',relativeTime=()=>'now'\n"


def run_checks(source: str) -> dict:
    work = Path(tempfile.mkdtemp(prefix="tk-3d-"))
    try:
        (work / "plugin.mjs").write_text(source.replace("from 'react'", "from './react.mjs'").replace("from '@hermes/plugin-sdk'", "from './sdk.mjs'"))
        (work / "react.mjs").write_text(REACT_SHIM)
        (work / "sdk.mjs").write_text(SDK_SHIM)
        shutil.copy(HERE / "tabletop3d.mjs", work / "run.mjs")
        done = subprocess.run([NODE, "run.mjs"], cwd=work, env={"PATH": os.environ.get("PATH", "")}, capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)
    finally:
        shutil.rmtree(work, ignore_errors=True)


@unittest.skipUnless(NODE, "node is required to run the 3D maths")
class TabletopMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text()
        cls.results = run_checks(cls.source)

    def test_every_check_ran(self):
        self.assertEqual(len(self.results), 18)

    def test_checks_pass(self):
        for name, failures in self.results.items():
            with self.subTest(name):
                self.assertEqual(failures[:3], [])

    def test_the_dice_check_can_fail(self):
        """Break the orientation maths, confirm the honesty check goes red."""
        broken = self.source.replace("qfromTo(shape.upOf(value), [0, 1, 0])", "qfromTo(shape.upOf(value === 1 ? 2 : value), [0, 1, 0])")
        self.assertNotEqual(broken, self.source)
        results = run_checks(broken)
        self.assertTrue(results["every_face_of_every_die_lands_face_up"])
        self.assertTrue(results["a_throw_ends_on_the_rolled_face_and_never_dips_below_the_tray"])

    def test_the_mesh_check_can_fail(self):
        broken = self.source.replace("m.i.push(a, b, a + 1, a + 1, b, b + 1)", "m.i.push(a, a + 1, b, a + 1, b + 1, b)")
        self.assertNotEqual(broken, self.source)
        self.assertTrue(run_checks(broken)["primitives_are_valid_indexed_geometry"])


class RendererContractTests(unittest.TestCase):
    """The platform rules that apply to a canvas pane, checked on the source."""

    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text()

    def test_canvas_tracks_its_container_and_pauses_when_hidden(self):
        self.assertIn("new ResizeObserver", self.source)
        self.assertIn("new IntersectionObserver", self.source)
        self.assertIn("cancelAnimationFrame", self.source)
        self.assertIn("document.hidden", self.source)
        self.assertRegex(self.source, r"canvas\.width\s*=\s*w")

    def test_listeners_are_tracked_by_the_host(self):
        self.assertNotRegex(self.source, r"(?<!ctx\.)(?<![\w.])(?:window|document|canvas)\.addEventListener\(")
        self.assertIn("ctx.addEventListener(canvas, 'wheel'", self.source)
        self.assertIn("ctx.onDispose", self.source)
        self.assertNotRegex(self.source, r"\bsetInterval\(|\bsetTimeout\(".replace("\\bset", r"(?<!ctx\.)\bset"))

    def test_falls_back_to_the_svg_board_without_webgl(self):
        self.assertIn("canWebGL()", self.source)
        self.assertIn("onGlFail", self.source)
        self.assertIn("h(Board, {", self.source)

    def test_scene_text_is_set_as_text_never_markup(self):
        self.assertNotIn("innerHTML", self.source)
        self.assertGreaterEqual(self.source.count("textContent"), 6)

    def test_no_colour_literals_in_the_source(self):
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", self.source))
        self.assertIsNone(re.search(r"\brgba?\(|\bhsla?\(", self.source))
        for token in ("--ui-accent", "--ui-red", "--ui-bg-editor", "--ui-text-secondary"):
            self.assertIn(token.replace("--ui-", ""), self.source.replace("--ui-", ""))


if __name__ == "__main__":
    unittest.main()
