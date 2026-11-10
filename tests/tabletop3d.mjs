// Pure-math checks for the 3D tabletop. Imports the real plugin.js (React and the SDK shimmed) and prints
// { check: [failures] }. Nothing here touches a DOM or a GL context.
import {
  DIE_SIDES, MINI_LOOKS, box, buildMini, combine, cone, cyl, diceOf, diceShape, dieMesh, faceUpQuat, fitDistance, lathe, lookOf,
  m4look, m4mul, m4persp, orbitEye, project, qrot, seeded, sphere, throwPlan, throwPose, topValue, torus, trayLayout, cellWorld, stagedWorld, xf
} from './plugin.mjs'

const out = {}
const check = (name, fn) => { const bad = []; try { fn(msg => bad.push(msg)) } catch (e) { bad.push(String(e && e.stack || e)) } out[name] = bad }
const near = (a, b, eps = 1e-9) => Math.abs(a - b) <= eps
const len3 = v => Math.hypot(v[0], v[1], v[2])

check('dice_shapes_label_every_face_once', fail => {
  for (const s of DIE_SIDES) {
    const d = diceShape(s)
    const values = d.faces.map(f => f.value).sort((a, b) => a - b)
    if (values.length !== s || values.some((v, i) => v !== i + 1)) fail(`d${s} faces are not 1..${s}: ${values}`)
    if (s !== 4) for (const f of d.faces) {
      const anti = d.faces.find(o => o.n[0] * f.n[0] + o.n[1] * f.n[1] + o.n[2] * f.n[2] < -0.999)
      if (!anti || anti.value + f.value !== s + 1) fail(`d${s} face ${f.value} is not opposite ${s + 1 - f.value}`)
    }
  }
})

check('every_face_of_every_die_lands_face_up', fail => {
  const rnd = seeded(5)
  for (const s of DIE_SIDES) {
    const d = diceShape(s)
    for (let v = 1; v <= s; v++) {
      const q = faceUpQuat(d, v, rnd() * 6.28)
      const up = qrot(q, d.upOf(v))
      if (!(near(up[0], 0, 1e-9) && near(up[1], 1, 1e-9) && near(up[2], 0, 1e-9))) fail(`d${s} face ${v}: up vector is ${up}`)
      const lowest = Math.min(...d.verts.map(p => qrot(q, p)[1]))
      if (!near(lowest, -d.inr, 1e-9)) fail(`d${s} face ${v}: rests ${lowest} instead of ${-d.inr}`)
      if (topValue(d, q) !== v) fail(`d${s}: asked for ${v}, the rendered top reads ${topValue(d, q)}`)
    }
  }
})

check('a_throw_ends_on_the_rolled_face_and_never_dips_below_the_tray', fail => {
  for (const s of DIE_SIDES) {
    const d = diceShape(s)
    for (let v = 1; v <= s; v++) {
      const plan = throwPlan(d, v, [1, 2], seeded(v * 31 + s), 0.2 + d.inr)
      const end = throwPose(plan, plan.dur + 0.5)
      if (!end.done || topValue(d, end.quat) !== v) fail(`d${s} ${v}: lands showing ${topValue(d, end.quat)}`)
      if (!near(end.pos[0], 1) || !near(end.pos[2], 2) || !near(end.pos[1], 0.2 + d.inr)) fail(`d${s} ${v}: lands at ${end.pos}`)
      for (let t = 0; t < plan.dur; t += plan.dur / 40) { const p = throwPose(plan, t); if (p.pos[1] < 0.2 + d.inr - 1e-9) fail(`d${s} ${v}: below the tray at t=${t}`); if (p.done) fail(`done early at ${t}`) }
    }
  }
  const d = diceShape(20)
  const mid = throwPose(throwPlan(d, 17, [0, 0], seeded(1), 0.6), 0.3)
  if (topValue(d, mid.quat) === 17 && mid.pos[1] < 0.8) fail('a die in flight should not already be at rest')
})

check('tray_layout_never_overlaps', fail => {
  for (let n = 1; n <= 8; n++) for (let seed = 0; seed < 20; seed++) {
    const spots = trayLayout(n, 0.6, seeded(seed))
    if (spots.length !== n) fail(`${n} dice got ${spots.length} spots`)
    for (let i = 0; i < n; i++) {
      if (Math.abs(spots[i][0]) > 4.4 || Math.abs(spots[i][1]) > 1.6) fail(`spot ${spots[i]} is outside the tray`)
      for (let j = i + 1; j < n; j++) if (Math.hypot(spots[i][0] - spots[j][0], spots[i][1] - spots[j][1]) < 1.2) fail(`dice ${i} and ${j} overlap for n=${n} seed=${seed}`)
    }
  }
})

check('unreadable_dice_are_dropped_not_invented', fail => {
  const roll = { dice: [{ value: 17, sides: 20, dropped: false }, { value: 0, sides: 6 }, { value: 7, sides: 6 }, { value: 40, sides: 0 }, { value: 3, sides: 0 }, { value: 4, sides: 13 }] }
  const got = diceOf(roll).map(d => `${d.sides}:${d.value}`)
  const want = ['20:17', '4:3', '4:4']
  if (got.join() !== want.join()) fail(`got ${got}, wanted ${want}`)
  if (diceOf({ dice: Array.from({ length: 30 }, () => ({ value: 2, sides: 6 })) }).length !== 8) fail('a big roll must show at most eight dice')
})

check('projection_and_orbit', fail => {
  const eye = orbitEye([0, 0.4, 2], 0, 0.8, 20)
  if (!near(len3([eye[0], eye[1] - 0.4, eye[2] - 2]), 20, 1e-9)) fail('orbit distance is not preserved')
  if (!(eye[2] > 2 && eye[1] > 0.4)) fail('az 0 should look from the south, above')
  const vp = m4mul(m4persp(0.66, 1.5, 0.5, 140), m4look(eye, [0, 0.4, 2]))
  const c = project([0, 0.4, 2], vp, 1500, 1000)
  if (!c.ok || !near(c.x, 750, 1e-6) || !near(c.y, 500, 1e-6)) fail(`target projects to ${c.x},${c.y}`)
  const right = project([3, 0.4, 2], vp, 1500, 1000), left = project([-3, 0.4, 2], vp, 1500, 1000)
  if (!(right.x > 750 && left.x < 750 && near(right.x - 750, 750 - left.x, 1e-6))) fail('x should map left to right, symmetrically')
  const up = project([0, 3.4, 2], vp, 1500, 1000)
  if (!(up.y < 500)) fail('higher world points must sit higher on screen (smaller y)')
  if (project(eye.map((v, i) => v + (i === 2 ? 5 : 0)), vp, 1500, 1000).ok) fail('a point behind the camera must not project')
  if (!near(Math.hypot(...cellWorld(0, 0).map((v, i) => v - [-5.5, -4.5][i])), 0)) fail('square A1 should be the far-left corner')
  if (!(stagedWorld(0)[1] < cellWorld(0, 0)[1] - 1)) fail('staged minis stand beyond the far edge')
})

check('camera_fit_frames_board_and_tray_at_every_aspect', fail => {
  let prev = 0
  for (const aspect of [2.4, 1.8, 1.45, 1, 0.7, 0.45]) {
    const d = fitDistance(aspect)
    if (d < prev - 1e-9) fail(`distance should grow as the pane narrows (${aspect}: ${d} <= ${prev})`)
    prev = d
    const m = m4mul(m4persp((38 * Math.PI) / 180, aspect, 0.5, 140), m4look(orbitEye([0, 0.4, 2.2], 0, 0.74, d), [0, 0.4, 2.2]))
    for (const p of [[-7.05, 0, -6.05], [7.05, 0, -6.05], [-7.05, 0, 6.05], [7.05, 0, 6.05], [-4.7, 0.3, 10.8], [4.7, 0.3, 10.8]]) {
      const s = project(p, m, 1000, 1000)
      const nx = s.x / 500 - 1
      if (!s.ok || Math.abs(nx) > 1 || s.y < 0 || s.y > 1000) fail(`aspect ${aspect}: corner ${p} falls outside at distance ${d}`)
    }
  }
})

const meshChecks = (label, mesh, fail, { winding = true, maxVerts = 4000 } = {}) => {
  const v = mesh.v, idx = mesh.i
  const n = v.length / 12
  if (n >= 65535 || n > maxVerts) fail(`${label}: ${n} vertices`)
  if (!idx.length || idx.length % 3) fail(`${label}: index count ${idx.length}`)
  for (const x of v) if (!Number.isFinite(x)) { fail(`${label}: non-finite vertex data`); break }
  let wrong = 0, degenerate = 0
  for (let t = 0; t < idx.length; t += 3) {
    const [a, b, c] = [idx[t], idx[t + 1], idx[t + 2]]
    if (a >= n || b >= n || c >= n) { fail(`${label}: index out of range`); return }
    const P = i => [v[i * 12], v[i * 12 + 1], v[i * 12 + 2]], N = i => [v[i * 12 + 3], v[i * 12 + 4], v[i * 12 + 5]]
    const e1 = [0, 1, 2].map(k => P(b)[k] - P(a)[k]), e2 = [0, 1, 2].map(k => P(c)[k] - P(a)[k])
    const cr = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
    if (len3(cr) < 1e-12) { degenerate++; continue }
    const nn = [0, 1, 2].map(k => N(a)[k] + N(b)[k] + N(c)[k])
    if (cr[0] * nn[0] + cr[1] * nn[1] + cr[2] * nn[2] < 0) wrong++
  }
  if (degenerate > idx.length / 30) fail(`${label}: ${degenerate} degenerate triangles`)
  if (winding && wrong) fail(`${label}: ${wrong} triangles wind against their normals`)
  for (let i = 0; i < n; i++) if (!near(len3([v[i * 12 + 3], v[i * 12 + 4], v[i * 12 + 5]]), 1, 1e-3)) { fail(`${label}: vertex ${i} normal is not unit length`); break }
}

check('primitives_are_valid_indexed_geometry', fail => {
  const prim = { lathe: lathe([[0, 0], [1, 0], [0.5, 1], [0, 1]], 8), cyl: cyl(1, 0.5, 2), cone: cone(1, 2), sphere: sphere(1), torus: torus(1, 0.2), box: box(1, 2, 3), moved: xf(sphere(1), [1, 2, 3], [0.3, 0.2, 0.1], [1, 2, 0.5]) }
  for (const [name, m] of Object.entries(prim)) meshChecks(name, combine([{ m, col: [1, 1, 1] }]), fail)
  const b = combine([{ m: box(1, 1, 1), col: [1, 0, 0], flag: 2 }])
  if (b.v[9] !== 2 || b.v[6] !== 1) fail('combine must carry colour and flag per vertex')
})

check('every_miniature_builds_and_stays_on_its_base', fail => {
  for (const look of MINI_LOOKS) {
    const m = buildMini(look)
    meshChecks(look, m, fail, { maxVerts: 2500 })
    let lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9]
    for (let i = 0; i < m.v.length; i += 12) for (let a = 0; a < 3; a++) { lo[a] = Math.min(lo[a], m.v[i + a]); hi[a] = Math.max(hi[a], m.v[i + a]) }
    if (lo[1] < -1e-6) fail(`${look}: goes below the felt (${lo[1]})`)
    if (hi[1] < 0.4 || hi[1] > 2.4) fail(`${look}: height ${hi[1]}`)
    if (Math.max(Math.abs(lo[0]), hi[0], Math.abs(lo[2]), hi[2]) > 1.2) fail(`${look}: wider than a square (${lo}/${hi})`)
    if (!(m.radius >= 0.35 && m.radius <= 0.65)) fail(`${look}: base radius ${m.radius}`)
  }
  const tall = h => buildMini(h).v.reduce((m, x, i) => (i % 12 === 1 ? Math.max(m, x) : m), 0)
  if (!(tall('ogre') > tall('goblin') * 1.5)) fail('an ogre must tower over a goblin')
  if (!(buildMini('ogre').radius > buildMini('goblin').radius)) fail('an ogre stands on a bigger base')
})

check('creatures_map_to_their_miniature', fail => {
  const cases = [
    [{ id: 'goblin-3', name: 'Goblin 3' }, 'goblin'], [{ id: 'dire_wolf-1', name: 'Dire Wolf' }, 'dire_wolf'], [{ id: 'wolf-2' }, 'wolf'],
    [{ id: 'hobgoblin-1' }, 'hobgoblin'], [{ id: 'bandit_captain-1' }, 'bandit_captain'], [{ id: 'giant_rat-4' }, 'giant_rat'],
    [{ id: 'fighter', name: 'Brann Hollis' }, 'fighter'], [{ id: 'pc-9', name: 'Thordis', class: 'Cleric' }, 'cleric'], [{ id: 'x', class: 'Rogue' }, 'rogue'],
    [{ id: 'm1', name: 'Giant Rat Swarm' }, 'giant_rat'], [{ id: 'skeleton-2' }, 'skeleton'], [{ id: 'zombie-1' }, 'zombie'], [{ id: 'orc-1' }, 'orc'],
    [{ id: 'kobold-2' }, 'kobold'], [{ id: 'ogre-1' }, 'ogre'], [{ id: 'bandit-1' }, 'bandit'], [{ id: 'wizard' }, 'wizard'],
    [{ id: 'q', name: 'Unknown Thing' }, 'generic'], [{}, 'generic'], [{ id: '<script>' }, 'generic']
  ]
  for (const [raw, want] of cases) if (lookOf(raw) !== want) fail(`${JSON.stringify(raw)} -> ${lookOf(raw)}, wanted ${want}`)
})

check('dice_mesh_uvs_address_one_cell_per_face', fail => {
  for (const s of DIE_SIDES) {
    const d = diceShape(s), m = dieMesh(d)
    meshChecks(`d${s}`, combine([{ m, col: [1, 1, 1] }]), fail, { maxVerts: 200 })
    const cols = Math.ceil(Math.sqrt(s))
    for (let k = 0; k < m.uv.length; k += 2) if (m.uv[k] < 0 || m.uv[k] > 1 || m.uv[k + 1] < 0 || m.uv[k + 1] > 1) { fail(`d${s}: uv outside the atlas`); break }
    const cells = new Set()
    for (let k = 0; k < m.uv.length; k += 2) cells.add(`${Math.floor(m.uv[k] * cols)},${Math.floor(m.uv[k + 1] * cols)}`)
    if (cells.size !== s) fail(`d${s}: faces use ${cells.size} atlas cells`)
  }
})

console.log(JSON.stringify(out))
