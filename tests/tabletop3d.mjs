// Pure-math checks for the 3D tabletop. Imports the real plugin.js (React and the SDK shimmed) and prints
// { check: [failures] }. Nothing here touches a DOM or a GL context.
import {
  DIE_SIDES, MINI_LOOKS, box, buildMini, combine, cone, cyl, diceOf, diceShape, dieMesh, faceUpQuat, homeFrame, HOME_EL, homeProj, insetRect, insetView, MINI_SCALE_UP, MINI_XZ, SWAY_AZ, swayDistance, lathe, lookOf, rollView, wantsCinematic,
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

check('young_red_dragon_has_a_large_hand_built_mini_and_breath_roll_metadata', fail => {
  const look = lookOf({ id: 'young-red-dragon-1', name: 'Young Red Dragon' })
  const mini = buildMini(look)
  const xs = Array.from({ length: mini.v.length / 12 }, (_, k) => mini.v[k * 12])
  if (look !== 'young_red_dragon') fail(`dragon look is ${look}`)
  if (!(mini.radius * MINI_XZ >= 0.9)) fail(`base radius is ${mini.radius * MINI_XZ}`)
  if (!(Math.max(...xs) - Math.min(...xs) > 1.5)) fail('dragon wings do not span a large miniature')
  if (!(mini.top > 0.7 && mini.i.length > 500)) fail('dragon shape is missing its sculpted parts')
  const event = rollView({ kind: 'breath', formula: '16d6', dice: Array(16).fill(2), total: 32,
    targets: ['fighter'], area: { shape: 'cone', origin: [8, 4], toward: [2, 4], cells: [[7, 4], [6, 4]] } })
  if (event.kind !== 'breath' || event.targets[0] !== 'fighter' || event.area.cells.length !== 2) fail('breath event metadata was lost')
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

const FOV = (38 * Math.PI) / 180
const frameOf = (cells, aspect, az = 0) => {
  const f = homeFrame(cells, aspect)
  const eye = orbitEye(f.target, az, HOME_EL, swayDistance(f.dist, az))
  return { f, vp: m4mul(homeProj(aspect), m4look(eye, f.target)) }
}
const inFrame = (p, vp) => { const s = project(p, vp, 1000, 1000); return s.ok && Math.abs(s.x / 500 - 1) <= 1 && s.y >= 0 && s.y <= 1000 }

check('home_camera_frames_the_occupied_squares_plus_one_ring_closely', fail => {
  const skirmish = [cellWorld(6, 5), cellWorld(7, 4), cellWorld(7, 5), cellWorld(7, 6)]
  const full = homeFrame([], 1.7).dist
  for (const aspect of [2.4, 1.8, 1.45, 1.1]) {
    const { f, vp } = frameOf(skirmish, aspect)
    const xs = skirmish.map(c => c[0]), zs = skirmish.map(c => c[1])
    for (const x of [Math.min(...xs) - 1.5, Math.max(...xs) + 1.5]) for (const z of [Math.min(...zs) - 1.5, Math.max(...zs) + 1.5]) {
      if (!inFrame([x, 0.16, z], vp)) fail(`aspect ${aspect}: ring corner ${x},${z} falls outside`)
    }
    for (const c of skirmish) if (!inFrame([c[0], 0.16 + 1.8 * 1.35, c[1]], vp)) fail(`aspect ${aspect}: a miniature's head leaves the frame`)
    if (aspect >= 1.45 && !(f.dist < homeFrame([], aspect).dist * 0.8)) fail(`aspect ${aspect}: a skirmish should sit closer than the whole-board shot`)
  }
  if (!(full > 0)) fail('whole-board distance missing')
})

check('home_camera_never_loses_a_creature_even_when_they_spread_over_the_board', fail => {
  const spread = [cellWorld(0, 0), cellWorld(11, 9), cellWorld(0, 9), cellWorld(11, 0), cellWorld(5, 4)]
  for (const aspect of [2.4, 1.8, 1.45, 1.1]) {
    for (const az of [-SWAY_AZ, 0, SWAY_AZ]) {
      const { vp } = frameOf(spread, aspect, az)
      for (const c of spread) if (!inFrame([c[0], 0.16, c[1]], vp)) fail(`aspect ${aspect}, sway ${az}: creature at ${c} leaves the frame`)
    }
  }
  const empty = frameOf([], 1.6).vp
  for (const p of [[-6.5, 0.2, -5.5], [6.5, 0.2, -5.5], [-6.5, 0.2, 5.5], [6.5, 0.2, 5.5]]) if (!inFrame(p, empty)) fail(`an empty table should frame the whole felt, ${p} is outside`)
})

check('home_camera_keeps_the_occupied_squares_clear_of_the_dice_window', fail => {
  const clusters = [[cellWorld(6, 5), cellWorld(7, 4), cellWorld(7, 5), cellWorld(7, 6)], [cellWorld(1, 1), cellWorld(9, 8)], [cellWorld(5, 5)], [cellWorld(10, 1), cellWorld(1, 8)], [cellWorld(9, 0), cellWorld(8, 1)]]
  for (const aspect of [1.78, 1.45]) for (const cells of clusters) {
    const { vp } = frameOf(cells, aspect)
    const W = 1000 * aspect, r = insetRect(W, 1000, 0)
    for (const c of cells) for (const y of [0.16, 0.16 + 1.8 * 1.35]) {
      const s = project([c[0], y, c[1]], vp, W, 1000)
      if (s.ok && s.x >= r.x && s.x <= r.x + r.w && s.y >= r.y && s.y <= r.y + r.h) fail(`aspect ${aspect}: a creature at ${c} sits under the dice window`)
    }
  }
})

check('home_camera_sits_lower_than_the_old_three_quarter_view', fail => {
  if (!(HOME_EL <= 0.58)) fail(`camera elevation ${HOME_EL} should be a low angle (<= 0.58 rad)`)
})

check('idle_sway_never_pushes_the_occupied_squares_out_of_frame', fail => {
  const cells = [cellWorld(2, 2), cellWorld(8, 6)]
  for (const aspect of [1.8, 1.45, 1.1]) for (const az of [-SWAY_AZ, -SWAY_AZ / 2, SWAY_AZ / 2, SWAY_AZ]) {
    const { vp } = frameOf(cells, aspect, az)
    for (const c of cells) if (!inFrame([c[0], 0.16, c[1]], vp)) fail(`aspect ${aspect}, sway ${az.toFixed(2)}: ${c} leaves the frame`)
  }
})

check('miniatures_are_scaled_up_but_bases_stay_inside_their_square', fail => {
  if (!(MINI_SCALE_UP / 1.12 >= 1.6)) fail(`height scale ${MINI_SCALE_UP} should be about 1.8x the old 1.12`)
  for (const look of MINI_LOOKS) {
    const g = buildMini(look)
    const foot = g.radius * MINI_XZ
    const large = look === 'ogre' || look === 'dire_wolf'
    const dragon = look === 'young_red_dragon'
    if (foot > (dragon ? 0.95 : large ? 0.72 : 0.5)) fail(`${look}: base radius ${foot.toFixed(2)} exceeds its footprint`)
    if (foot < 0.3) fail(`${look}: base radius ${foot.toFixed(2)} is too small to read`)
    if (!(g.top > 0.3)) fail(`${look}: the mesh reports no height`)
    let max = 0
    for (let k = 1; k < g.v.length; k += 12) max = Math.max(max, g.v[k])
    if (Math.abs(max - g.top) > 1e-6) fail(`${look}: top ${g.top} does not match the tallest vertex ${max}`)
  }
})

check('dice_inset_sits_top_right_and_grows_during_a_throw', fail => {
  for (const [w, h] of [[1920, 1080], [1030, 700], [820, 560], [523, 360]]) {
    const a = insetRect(w, h, 0), b = insetRect(w, h, 1)
    for (const [name, r] of [['rest', a], ['throw', b]]) {
      if (r.x < 0 || r.y < 0 || r.x + r.w > w || r.y + r.h > h) fail(`${w}x${h} ${name}: inset ${JSON.stringify(r)} leaves the canvas`)
      if (r.x + r.w < w - 24 || r.y > 24) fail(`${w}x${h} ${name}: inset is not tucked into the top-right corner`)
    }
    if (a.w * a.h > w * h * 0.13) fail(`${w}x${h}: the resting inset covers too much of the table`)
    if (w >= 800 && !(b.w >= a.w * 1.25)) fail(`${w}x${h}: the throw inset should grow by at least 1.25x`)
    if (b.w * b.h > w * h * 0.27) fail(`${w}x${h}: the throw inset swallows the table`)
  }
})

check('dice_inset_camera_frames_every_resting_die_and_the_flight_in', fail => {
  const aspect = 4 / 3
  const { eye, target, fov } = insetView(aspect)
  const vp = m4mul(m4persp(fov, aspect, 0.3, 80), m4look(eye, target))
  for (let n = 1; n <= 6; n++) {
    const spots = trayLayout(n, 0.6, seeded(n))
    for (const [x, z] of spots) {
      const s = project([target[0] + x, 0.5, target[2] + z], vp, 1000, 1000)
      if (!s.ok || Math.abs(s.x / 500 - 1) > 0.8 || Math.abs(s.y / 500 - 1) > 0.8) fail(`${n} dice: a die at ${x.toFixed(2)},${z.toFixed(2)} leaves the inset`)
    }
  }
})

check('cinematic_mode_is_requested_by_the_url', fail => {
  const yes = [['?cinematic=1', ''], ['', '#/tabletop?cinematic=1'], ['?profile=hackdemo&cinematic=1', '#/tabletop'], ['?cinematic=true', '']]
  const no = [['', ''], ['?cinematic=0', ''], ['?profile=x', '#/tabletop'], ['?cinematic', ''], ['?notcinematic=1', ''], ['', '#/tabletop?cinematic=0']]
  for (const [s, h] of yes) if (wantsCinematic(s, h) !== true) fail(`${s}${h} should turn cinematic on`)
  for (const [s, h] of no) if (wantsCinematic(s, h) !== false) fail(`${s}${h} should leave cinematic off`)
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
    if (hi[1] * MINI_SCALE_UP > 4.2) fail(`${look}: ${(hi[1] * MINI_SCALE_UP).toFixed(1)} squares tall once scaled`)
    const dragon = look === 'young_red_dragon'
    if (Math.max(Math.abs(lo[0]), hi[0], Math.abs(lo[2]), hi[2]) * MINI_XZ > (dragon ? 3 : look === "ogre" || look === "dire_wolf" ? 2.6 : 1.7)) fail(`${look}: reaches beyond its footprint (${lo}/${hi})`)
    if (!(m.radius * MINI_XZ >= 0.3 && m.radius * MINI_XZ <= (dragon ? 0.95 : 0.72))) fail(`${look}: base radius ${m.radius * MINI_XZ}`)
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
