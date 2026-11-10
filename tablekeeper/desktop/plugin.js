import { createElement as h, useEffect, useId, useRef, useState } from 'react'
import { PANES_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, relativeTime } from '@hermes/plugin-sdk'

const COLS = 12
const ROWS = 10
const CELL = 48
const PAD = 26
const STAGE = 64
const POLL_MS = 1000
const LIST_EVERY = 5
const FEET_PER_SQUARE = 5
const OWNER_TONES = ['blue', 'purple', 'cyan', 'orange', 'accent', 'accent-secondary']

const CONDITION_CODE = {
  blinded: 'BL', charmed: 'CH', deafened: 'DF', exhaustion: 'EX', frightened: 'FR', grappled: 'GR',
  incapacitated: 'IC', invisible: 'IV', paralyzed: 'PA', petrified: 'PE', poisoned: 'PO', prone: 'PR',
  restrained: 'RS', stunned: 'ST', unconscious: 'UN'
}
const CONDITION_TONE = {
  paralyzed: 'red', stunned: 'red', unconscious: 'red', incapacitated: 'red', petrified: 'red',
  charmed: 'purple', frightened: 'purple', blinded: 'cyan', deafened: 'cyan', invisible: 'cyan',
  grappled: 'orange', restrained: 'orange', prone: 'orange', poisoned: 'green', exhaustion: 'yellow'
}

const DIE_SHAPES = {
  20: { poly: '15,1.5 26.5,8 26.5,22 15,28.5 3.5,22 3.5,8' },
  12: { poly: '15,1.5 27.5,10.5 22.8,26 7.2,26 2.5,10.5' },
  10: { poly: '15,1.5 27,13 15,28.5 3,13' },
  8: { poly: '15,1.5 27.5,15 15,28.5 2.5,15' },
  4: { poly: '15,3 28,26.5 2,26.5' },
  6: { rect: true }
}

const STYLE = `
.tk{--tk-felt:color-mix(in oklab,var(--ui-green) 15%,var(--ui-bg-editor));--tk-felt-deep:color-mix(in oklab,var(--ui-green) 24%,var(--ui-bg-editor));--tk-wood:color-mix(in oklab,var(--ui-orange) 22%,var(--ui-bg-elevated));--tk-wood-edge:color-mix(in oklab,var(--ui-orange) 45%,var(--ui-bg-elevated));--tk-line:color-mix(in srgb,var(--ui-base) 16%,transparent);container-type:inline-size;height:100%;overflow:auto;color:var(--ui-text-primary);font-size:13px;line-height:1.35}
.tk *{box-sizing:border-box}
.tk-num{font-variant-numeric:tabular-nums}
.tk-wrap{display:flex;flex-direction:column;gap:14px;padding:14px;min-height:100%}
.tk-head{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap}
.tk-scene{font-size:20px;font-weight:650;letter-spacing:-.01em;line-height:1.15;max-width:46ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tk-sub{display:flex;gap:8px;align-items:center;margin-top:5px;color:var(--ui-text-secondary);flex-wrap:wrap}
.tk-round{font-weight:650;letter-spacing:.14em;text-transform:uppercase;font-size:11px;color:var(--ui-text-primary);padding:2px 8px;border-radius:5px;background:color-mix(in srgb,var(--ui-accent) 16%,transparent)}
.tk-chip{display:inline-flex;align-items:center;gap:6px;font-size:11px;letter-spacing:.04em;padding:2px 8px;border-radius:999px;color:var(--ui-text-secondary);border:1px solid var(--ui-stroke-secondary)}
.tk-live{width:7px;height:7px;border-radius:50%;background:var(--ui-green);box-shadow:0 0 0 0 color-mix(in srgb,var(--ui-green) 60%,transparent);animation:tk-live 2s infinite}
.tk-live[data-ok="false"]{background:var(--ui-yellow);animation:none}
.tk-pick{background:transparent;color:var(--ui-text-secondary);border:1px solid var(--ui-stroke-secondary);border-radius:6px;padding:3px 6px;font:inherit;font-size:11px;max-width:200px}
.tk-layout{display:grid;gap:14px;grid-template-columns:minmax(0,1fr);align-items:start}
.tk-frame{border-radius:14px;padding:10px;background:linear-gradient(160deg,var(--tk-wood-edge),var(--tk-wood));box-shadow:inset 0 1px 0 color-mix(in srgb,var(--ui-base) 14%,transparent),inset 0 -2px 0 color-mix(in srgb,var(--ui-base) 14%,transparent),0 1px 0 var(--ui-stroke-secondary)}
.tk-board{display:block;width:100%;height:auto;border-radius:8px}
.tk-side{display:flex;flex-direction:column;gap:14px;min-width:0}
.tk-panel{border-radius:12px;background:var(--ui-bg-secondary);border:1px solid var(--ui-stroke-tertiary);min-width:0}
.tk-panel-h{display:flex;justify-content:space-between;align-items:center;padding:9px 12px 7px;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--ui-text-tertiary);font-weight:600}
.tk-list{list-style:none;margin:0;padding:0 6px 6px;display:flex;flex-direction:column;gap:2px}
.tk-row{display:grid;grid-template-columns:20px 28px minmax(0,1fr) auto;gap:8px;align-items:center;padding:2px 8px;border-radius:9px;position:relative;transition:background .3s}
.tk-row[data-active="true"]{background:color-mix(in srgb,var(--ui-accent) 15%,transparent);box-shadow:inset 3px 0 0 var(--ui-accent),0 0 18px -6px var(--ui-accent)}
.tk-row[data-state="dead"]{opacity:.5}
.tk-row[data-state="dead"] .tk-name{text-decoration:line-through}
.tk-ord{font-size:11px;color:var(--ui-text-quaternary);text-align:center}
.tk-line{display:flex;gap:8px;align-items:baseline;min-width:0;white-space:nowrap}
.tk-name{font-weight:600;overflow:hidden;text-overflow:ellipsis;min-width:0}
.tk-meta{font-size:11px;color:var(--ui-text-tertiary);display:flex;gap:6px;align-items:center;flex:none}
.tk-bar{height:5px;border-radius:3px;background:var(--ui-stroke-tertiary);overflow:hidden;margin-top:2px;display:flex}
.tk-bar>i{display:block;height:100%;transition:width .7s cubic-bezier(.3,.7,.2,1),background .4s}
.tk-hp{font-size:12px;font-weight:600;text-align:right;white-space:nowrap}
.tk-hp small{font-weight:500;color:var(--ui-text-tertiary)}
.tk-cond{font-size:9.5px;letter-spacing:.05em;text-transform:uppercase;padding:0 5px;border-radius:4px;font-weight:650}
.tk-tray{background:color-mix(in oklab,var(--ui-base) 5%,var(--tk-felt-deep));box-shadow:inset 0 3px 8px -4px color-mix(in srgb,var(--ui-base) 40%,transparent)}
.tk-roll{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;align-items:center;padding:1px 8px;border-radius:9px}
.tk-roll[data-fresh="true"]{background:color-mix(in srgb,var(--ui-yellow) 12%,transparent)}
.tk-roll[data-hero="true"]{grid-template-columns:minmax(0,1fr) auto;padding:4px 8px 6px;margin-bottom:3px;background:color-mix(in srgb,var(--ui-base) 6%,transparent)}
.tk-who{font-size:11px;color:var(--ui-text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.tk-who b{color:var(--ui-text-primary);font-weight:600}
.tk-faces{display:flex;gap:2px;align-items:center;flex:none}
.tk-roll[data-hero="true"] .tk-faces{margin-top:4px;flex-wrap:wrap}
.tk-mod{font-size:12px;color:var(--ui-text-secondary);padding:0 3px}
.tk-total{font-size:17px;font-weight:700;line-height:1;text-align:right;min-width:2ch}
.tk-roll[data-hero="true"] .tk-total{font-size:32px}
.tk-total[data-tone="crit"]{color:var(--ui-yellow)}
.tk-total[data-tone="fumble"]{color:var(--ui-red)}
.tk-tag{font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;font-weight:650;padding:1px 6px;border-radius:4px;margin-left:6px}
.tk-die{overflow:visible}
.tk-die[data-fresh="true"]{animation:tk-tumble .75s cubic-bezier(.2,.9,.25,1.15) both;transform-box:fill-box;transform-origin:center}
.tk-log{list-style:none;margin:0;padding:0 12px 10px;display:flex;flex-direction:column;gap:5px;max-height:240px;overflow:auto;min-height:0}
.tk-logp{display:flex;flex-direction:column;min-height:0}
.tk-log li{display:grid;grid-template-columns:8px minmax(0,1fr) auto;gap:8px;align-items:baseline;font-size:12px;color:var(--ui-text-secondary)}
.tk-log li>i{width:6px;height:6px;border-radius:50%;display:block;transform:translateY(-1px)}
.tk-log time{font-size:10.5px;color:var(--ui-text-quaternary);white-space:nowrap}
.tk-empty{display:grid;place-items:center;text-align:center;padding:32px 20px;min-height:260px;color:var(--ui-text-secondary)}
.tk-empty b{display:block;font-size:15px;color:var(--ui-text-primary);margin-bottom:4px}
.tk-glow{animation:tk-pulse 1.8s ease-in-out infinite;transform-box:fill-box;transform-origin:center}
.tk-token{transition:transform .7s cubic-bezier(.3,.7,.2,1)}
.tk-ring{transition:stroke-dasharray .7s cubic-bezier(.3,.7,.2,1),stroke .4s}
.tk-token[data-state="dead"] .tk-body,.tk-token[data-state="down"] .tk-body{filter:grayscale(1)}
.tk-token[data-state="dead"] .tk-body{opacity:.5}
.tk-token[data-state="down"] .tk-body{opacity:.75}
.tk-float{animation:tk-float 1.6s ease-out forwards;pointer-events:none}
.tk-ini{font-size:13px;font-weight:700;fill:var(--ui-text-primary);pointer-events:none}
.tk-seg{display:inline-flex;border:1px solid var(--ui-stroke-secondary);border-radius:7px;overflow:hidden}
.tk-segb{background:transparent;color:var(--ui-text-secondary);border:0;padding:3px 10px;font:inherit;font-size:11px;font-weight:650;letter-spacing:.1em;cursor:pointer}
.tk-segb[aria-pressed="true"]{background:color-mix(in srgb,var(--ui-accent) 22%,transparent);color:var(--ui-text-primary)}
.tk-segb:disabled{opacity:.4;cursor:default}
.tk-frame-3d{padding:0;overflow:hidden;background:var(--ui-bg-editor);box-shadow:0 0 0 1px var(--ui-stroke-secondary),0 14px 40px -18px color-mix(in srgb,var(--ui-base) 70%,transparent)}
.tk-view3d{position:relative;width:100%;aspect-ratio:16/11;min-height:300px;max-height:calc(100vh - 160px);background:var(--ui-bg-editor)}
.tk-gl{position:absolute;inset:0;width:100%;height:100%;display:block;touch-action:none;cursor:grab}
.tk-hud{position:absolute;inset:0;overflow:hidden;pointer-events:none;font-variant-numeric:tabular-nums}
.tk-np{position:absolute;left:0;top:0;display:flex;gap:8px;align-items:baseline;white-space:nowrap;padding:3px 11px;border-radius:999px;background:var(--ui-accent);color:var(--ui-bg-editor);font-size:12px;will-change:transform;box-shadow:0 6px 18px -6px color-mix(in srgb,var(--ui-base) 70%,transparent)}
.tk-np span{font-size:10.5px;opacity:.82}
.tk-np-tip{background:var(--ui-bg-elevated);color:var(--ui-text-primary);border:1px solid var(--ui-stroke-secondary)}
.tk-dmg{position:absolute;left:0;top:0;font-size:27px;font-weight:800;letter-spacing:-.01em;will-change:transform,opacity;text-shadow:0 2px 0 var(--ui-bg-editor),0 0 14px var(--ui-bg-editor)}
.tk-dmg-hurt{color:var(--ui-red)}
.tk-dmg-heal{color:var(--ui-green)}
.tk-dmg-miss{color:var(--ui-text-secondary);font-size:16px;letter-spacing:.14em;text-transform:uppercase}
.tk-cap{position:absolute;left:12px;top:10px;display:flex;align-items:baseline;gap:12px;padding:6px 16px;border-radius:12px;white-space:nowrap;max-width:92%;background:color-mix(in srgb,var(--ui-bg-editor) 80%,transparent);border:1px solid var(--ui-stroke-secondary);backdrop-filter:blur(6px)}
.tk-cap-who{font-size:12px;color:var(--ui-text-secondary);overflow:hidden;text-overflow:ellipsis}
.tk-cap-val{font-size:24px;font-weight:750;line-height:1}
.tk-cap-tag{font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;color:var(--ui-text-secondary)}
.tk-cap[data-tone="crit"] .tk-cap-val,.tk-cap[data-tone="crit"] .tk-cap-tag{color:var(--ui-yellow)}
.tk-cap[data-tone="fumble"] .tk-cap-val,.tk-cap[data-tone="fumble"] .tk-cap-tag,.tk-cap[data-tone="miss"] .tk-cap-tag{color:var(--ui-red)}
.tk-cap[data-tone="hit"] .tk-cap-tag{color:var(--ui-green)}
.tk-hint{position:absolute;right:12px;top:10px;font-size:10.5px;letter-spacing:.05em;color:var(--ui-text-tertiary);transition:opacity .8s}
@keyframes tk-live{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--ui-green) 55%,transparent)}70%,100%{box-shadow:0 0 0 7px transparent}}
@keyframes tk-pulse{0%,100%{opacity:.95;transform:scale(1)}50%{opacity:.3;transform:scale(1.16)}}
@keyframes tk-float{0%{opacity:0;transform:translateY(0)}12%{opacity:1}100%{opacity:0;transform:translateY(-34px)}}
@keyframes tk-tumble{0%{opacity:0;transform:rotate(-260deg) scale(.2) translateY(-14px)}60%{opacity:1}100%{opacity:1;transform:rotate(0) scale(1) translateY(0)}}
@container (min-width:900px){.tk-layout[data-view="3d"]{grid-template-columns:minmax(0,2fr) minmax(320px,1fr)}.tk-wrap{height:100%}.tk-layout{flex:1;min-height:0;grid-template-columns:minmax(0,1.5fr) minmax(340px,1fr);grid-template-rows:auto minmax(0,1fr)}.tk-frame{grid-area:1/1}.tk-logp{grid-area:2/1;max-height:100%}.tk-logp .tk-log{max-height:none;flex:1}.tk-side{grid-area:1/2/3/2;max-height:100%;overflow:auto;padding-right:2px}}
@media (prefers-reduced-motion:reduce){.tk *{animation:none!important;transition:none!important}}
`

const num = (v, d = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : d)
const clip = (v, n = 80) => Array.from(String(v ?? '')).slice(0, n).join('')
const list = v => (Array.isArray(v) ? v : [])
const tone = name => `var(--ui-${name})`
const soft = (color, pct) => `color-mix(in srgb, ${color} ${pct}%, transparent)`

function initials(name) {
  const words = clip(name, 40).trim().split(/\s+/).filter(Boolean)
  if (!words.length) return '?'
  const first = Array.from(words[0])[0]
  const last = words.length > 1 ? Array.from(words[words.length - 1])[0] : ''
  return (first + last).toUpperCase()
}

export function creatureView(raw, index) {
  const hp = num(raw?.hp)
  const max = Math.max(1, num(raw?.max_hp, hp || 1))
  const saves = raw?.death_saves || {}
  const kind = raw?.kind === 'pc' ? 'pc' : 'monster'
  const failures = num(saves.f)
  const conditions = list(raw?.conditions).map(c => clip(c, 24).toLowerCase()).filter(c => c !== 'dead' && c !== 'stable')
  const status = clip(raw?.status, 16)
  const dead = status === 'dead' || raw?.dead === true || failures >= 3 || (kind === 'monster' && hp <= 0)
  const down = !dead && hp <= 0
  const pos = Array.isArray(raw?.pos) && raw.pos.length === 2 ? raw.pos.map(Number) : null
  const placed = pos && pos.every(Number.isFinite)
  return {
    key: clip(raw?.id ?? raw?.name ?? `c${index}`, 64),
    name: clip(raw?.name || raw?.id || 'Unknown', 60),
    kind,
    owner: clip(raw?.owner, 64),
    hp: Math.max(0, hp),
    max,
    temp: Math.max(0, num(raw?.temp_hp)),
    ac: raw?.ac == null ? null : num(raw.ac),
    frac: Math.min(1, Math.max(0, hp / max)),
    state: dead ? 'dead' : down ? (status === 'stable' || raw?.stable === true || num(saves.s) >= 3 ? 'stable' : 'down') : 'ok',
    saves: { s: Math.min(3, Math.max(0, num(saves.s))), f: Math.min(3, Math.max(0, failures)) },
    conditions,
    concentrating: Boolean(raw?.concentration),
    look: lookOf(raw),
    pos: placed ? [Math.min(COLS - 1, Math.max(0, Math.round(pos[0]))), Math.min(ROWS - 1, Math.max(0, Math.round(pos[1])))] : null
  }
}

export function rollView(raw) {
  const formula = clip(raw?.formula, 64)
  const sides = []
  for (const m of formula.matchAll(/(\d{1,3})d(\d{1,4})/g)) for (let i = 0; i < Math.min(100, Number(m[1])); i++) sides.push(Number(m[2]))
  const natural = raw?.natural == null ? null : num(raw.natural)
  let usedNatural = false
  const dice = list(raw?.dice).slice(0, 40).map((d, i) => {
    const value = typeof d === 'object' && d ? num(d.value ?? d.result) : num(d)
    const die = sides[i] || (natural != null ? 20 : 0)
    const spare = natural != null && die === 20 && (usedNatural || value !== natural)
    if (natural != null && die === 20 && value === natural) usedNatural = true
    return { value, sides: die, dropped: (typeof d === 'object' && d ? Boolean(d.dropped) : false) || spare }
  })
  const passed = raw?.success ?? raw?.passed
  return {
    seq: num(raw?.seq, -1),
    ts: num(raw?.ts),
    actor: clip(raw?.who, 64),
    target: clip(raw?.target, 64),
    who: clip(raw?.name || raw?.who || raw?.actor, 40),
    kind: clip(raw?.kind, 24),
    label: clip(raw?.why || raw?.label, 72),
    formula,
    dice,
    modifier: num(raw?.modifier),
    total: raw?.total == null ? null : num(raw.total),
    damageType: clip(raw?.type, 20),
    outcome: raw?.crit || raw?.critical ? 'crit' : raw?.hit === true ? 'hit' : raw?.hit === false ? 'miss' : passed === true ? 'success' : passed === false ? 'fail' : ''
  }
}

const hpTone = frac => (frac > 0.5 ? 'green' : frac > 0.25 ? 'yellow' : 'red')

// ================================================================ 3D tabletop: math and geometry (pure, no DOM)

const TAU = Math.PI * 2
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
const mix = (a, b, t) => a + (b - a) * t
const ease = t => t * t * (3 - 2 * t)
const easeOut = t => 1 - (1 - t) * (1 - t) * (1 - t)

const vadd = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
const vsub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const vmul = (a, s) => [a[0] * s, a[1] * s, a[2] * s]
const vdot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const vcross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const vlen = a => Math.hypot(a[0], a[1], a[2])
const vnorm = a => { const l = vlen(a) || 1; return [a[0] / l, a[1] / l, a[2] / l] }

// Column-major 4x4, the layout WebGL uploads as is.
export function m4mul(a, b) {
  const o = new Array(16)
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3]
  return o
}
export const m4persp = (fovy, aspect, near, far) => {
  const t = 1 / Math.tan(fovy / 2)
  return [t / aspect, 0, 0, 0, 0, t, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, (2 * far * near) / (near - far), 0]
}
export const m4ortho = (l, r, b, t, n, f) => [2 / (r - l), 0, 0, 0, 0, 2 / (t - b), 0, 0, 0, 0, -2 / (f - n), 0, -(r + l) / (r - l), -(t + b) / (t - b), -(f + n) / (f - n), 1]
export function m4look(eye, at, up = [0, 1, 0]) {
  const z = vnorm(vsub(eye, at))
  const x = vnorm(vcross(up, z))
  const y = vcross(z, x)
  return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -vdot(x, eye), -vdot(y, eye), -vdot(z, eye), 1]
}
export const m4xf = (m, v, w = 1) => [
  m[0] * v[0] + m[4] * v[1] + m[8] * v[2] + m[12] * w, m[1] * v[0] + m[5] * v[1] + m[9] * v[2] + m[13] * w,
  m[2] * v[0] + m[6] * v[1] + m[10] * v[2] + m[14] * w, m[3] * v[0] + m[7] * v[1] + m[11] * v[2] + m[15] * w
]

// Quaternions as [x, y, z, w].
export const qmul = (a, b) => [
  a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1], a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
  a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3], a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]
]
export const qaxis = (axis, angle) => { const a = vnorm(axis); const s = Math.sin(angle / 2); return [a[0] * s, a[1] * s, a[2] * s, Math.cos(angle / 2)] }
export function qrot(q, v) {
  const u = [q[0], q[1], q[2]]
  const t = vmul(vcross(u, v), 2)
  return vadd(vadd(v, vmul(t, q[3])), vcross(u, t))
}
export function qfromTo(a, b) {
  const d = vdot(a, b)
  if (d > 0.999999) return [0, 0, 0, 1]
  if (d < -0.999999) { const ax = Math.abs(a[0]) < 0.9 ? [1, 0, 0] : [0, 0, 1]; return qaxis(vcross(a, ax), Math.PI) }
  const c = vcross(a, b)
  const q = [c[0], c[1], c[2], 1 + d]
  const l = Math.hypot(q[0], q[1], q[2], q[3])
  return [q[0] / l, q[1] / l, q[2] / l, q[3] / l]
}
const qeuler = (rx, ry, rz) => qmul(qmul(qaxis([0, 1, 0], ry), qaxis([1, 0, 0], rx)), qaxis([0, 0, 1], rz))
export function m4trs(t, q, s) {
  const [x, y, z, w] = q
  const sx = s[0], sy = s[1], sz = s[2]
  return [
    (1 - 2 * (y * y + z * z)) * sx, 2 * (x * y + z * w) * sx, 2 * (x * z - y * w) * sx, 0,
    2 * (x * y - z * w) * sy, (1 - 2 * (x * x + z * z)) * sy, 2 * (y * z + x * w) * sy, 0,
    2 * (x * z + y * w) * sz, 2 * (y * z - x * w) * sz, (1 - 2 * (x * x + y * y)) * sz, 0,
    t[0], t[1], t[2], 1
  ]
}

/** World point to canvas pixels. `ok` is false behind the camera or outside the depth range. */
export function project(p, vp, width, height) {
  const c = m4xf(vp, p)
  if (c[3] <= 1e-6) return { x: NaN, y: NaN, z: Infinity, ok: false }
  const nx = c[0] / c[3], ny = c[1] / c[3], nz = c[2] / c[3]
  return { x: (nx * 0.5 + 0.5) * width, y: (1 - (ny * 0.5 + 0.5)) * height, z: nz, ok: nz > -1 && nz < 1 }
}

export const orbitEye = (target, az, el, dist) => [
  target[0] + dist * Math.sin(az) * Math.cos(el), target[1] + dist * Math.sin(el), target[2] + dist * Math.cos(az) * Math.cos(el)
]

// Board squares are one world unit. Column A and row 1 sit at the far left and far edge of the felt.
export const cellWorld = (x, y) => [x - (COLS - 1) / 2, y - (ROWS - 1) / 2]
export const stagedWorld = i => [-(COLS - 1) / 2 + i * 1.15, -(ROWS / 2 + 1.7)]

/** Small deterministic generator so a roll's throw is the same every time it is replayed. */
export function seeded(seed) {
  let a = (Math.floor(seed) * 2654435761 + 1013904223) >>> 0
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}

// ---------------------------------------------------------------- meshes: { p, n, uv, i } flat arrays

const meshOf = () => ({ p: [], n: [], uv: [], i: [] })

/** Revolve a [radius, height] profile (bottom to top, outside at +radius) around Y. Sharp corners keep their own normals. */
export function lathe(profile, seg = 10) {
  const m = meshOf()
  const segs = []
  for (let k = 0; k < profile.length - 1; k++) {
    const dr = profile[k + 1][0] - profile[k][0], dy = profile[k + 1][1] - profile[k][1]
    const l = Math.hypot(dr, dy) || 1
    segs.push([dy / l, -dr / l])
  }
  const rings = []
  const ring = (r, y, nr, ny) => {
    const start = m.p.length / 3
    for (let s = 0; s <= seg; s++) {
      const a = (s / seg) * TAU, sn = Math.sin(a), cs = Math.cos(a)
      m.p.push(r * sn, y, r * cs)
      m.n.push(nr * sn, ny, nr * cs)
      m.uv.push(s / seg, y)
    }
    return start
  }
  for (let j = 0; j < profile.length; j++) {
    const [r, y] = profile[j]
    const a = segs[j - 1], b = segs[j]
    if (!a || !b) { const n = a || b; rings.push({ below: ring(r, y, n[0], n[1]), above: null }); rings[j].above = rings[j].below; continue }
    if (a[0] * b[0] + a[1] * b[1] < Math.cos(0.9)) rings.push({ below: ring(r, y, a[0], a[1]), above: ring(r, y, b[0], b[1]) })
    else { const x = a[0] + b[0], z = a[1] + b[1], l = Math.hypot(x, z) || 1; const at = ring(r, y, x / l, z / l); rings.push({ below: at, above: at }) }
  }
  for (let k = 0; k < profile.length - 1; k++) {
    const A = rings[k].above, B = rings[k + 1].below
    for (let s = 0; s < seg; s++) {
      if (profile[k][0] > 1e-6) m.i.push(A + s, A + s + 1, B + s)
      if (profile[k + 1][0] > 1e-6) m.i.push(A + s + 1, B + s + 1, B + s)
    }
  }
  return m
}
export const cyl = (r0, r1, h, seg = 10) => lathe([[0, 0], [r0, 0], [r1, h], [0, h]], seg)
export const cone = (r, h, seg = 10) => lathe([[0, 0], [r, 0], [0, h]], seg)
export function sphere(r, seg = 10, rings = 6) {
  const prof = []
  for (let k = 0; k <= rings; k++) { const a = -Math.PI / 2 + (Math.PI * k) / rings; prof.push([Math.max(0, r * Math.cos(a)), r * Math.sin(a)]) }
  return lathe(prof, seg)
}
export function torus(R, r, seg = 18, tube = 6) {
  const m = meshOf()
  for (let s = 0; s <= seg; s++) for (let t = 0; t <= tube; t++) {
    const a = (s / seg) * TAU, b = (t / tube) * TAU
    const nx = Math.cos(b) * Math.sin(a), ny = Math.sin(b), nz = Math.cos(b) * Math.cos(a)
    m.p.push((R + r * Math.cos(b)) * Math.sin(a), r * ny, (R + r * Math.cos(b)) * Math.cos(a))
    m.n.push(nx, ny, nz)
    m.uv.push(s / seg, t / tube)
  }
  for (let s = 0; s < seg; s++) for (let t = 0; t < tube; t++) {
    const a = s * (tube + 1) + t, b = a + tube + 1
    m.i.push(a, b, a + 1, a + 1, b, b + 1)
  }
  return m
}
/** Axis-aligned box centred on the origin. UVs are world-scale planar projections so wood grain keeps its size. */
export function box(w, h, d, uvs = 0.25) {
  const m = meshOf()
  const hw = w / 2, hh = h / 2, hd = d / 2
  const faces = [
    [[1, 0, 0], [0, 0, -1], [0, 1, 0]], [[-1, 0, 0], [0, 0, 1], [0, 1, 0]],
    [[0, 1, 0], [1, 0, 0], [0, 0, -1]], [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
    [[0, 0, 1], [1, 0, 0], [0, 1, 0]], [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]
  ]
  const half = [hw, hh, hd]
  for (const [n, u, v] of faces) {
    const base = m.p.length / 3
    for (const [su, sv] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
      const p = [0, 1, 2].map(a => n[a] * half[a] + u[a] * su * half[a] + v[a] * sv * half[a])
      m.p.push(p[0], p[1], p[2])
      m.n.push(n[0], n[1], n[2])
      m.uv.push((vdot(p, u) + 40) * uvs, (vdot(p, v) + 40) * uvs)
    }
    m.i.push(base, base + 1, base + 2, base, base + 2, base + 3)
  }
  return m
}

/** Scale, then rotate (Euler Y X Z, or a quaternion), then move. Normals follow so ellipsoids stay smooth. */
export function xf(m, t = [0, 0, 0], r = [0, 0, 0], s = [1, 1, 1]) {
  const q = r.length === 4 ? r : qeuler(r[0], r[1], r[2])
  const sc = typeof s === 'number' ? [s, s, s] : s
  const out = { p: [], n: [], uv: m.uv.slice(), i: m.i.slice() }
  for (let k = 0; k < m.p.length; k += 3) {
    const p = qrot(q, [m.p[k] * sc[0], m.p[k + 1] * sc[1], m.p[k + 2] * sc[2]])
    out.p.push(p[0] + t[0], p[1] + t[1], p[2] + t[2])
    const n = vnorm(qrot(q, [m.n[k] / sc[0], m.n[k + 1] / sc[1], m.n[k + 2] / sc[2]]))
    out.n.push(n[0], n[1], n[2])
  }
  return out
}

/** Interleave parts into one vertex buffer: position, normal, colour, flag, uv (12 floats a vertex). */
export function combine(parts) {
  let verts = 0, tris = 0
  for (const part of parts) { verts += part.m.p.length / 3; tris += part.m.i.length }
  const v = new Float32Array(verts * 12)
  const i = verts < 65535 ? new Uint16Array(tris) : new Uint32Array(tris)
  let vo = 0, io = 0, base = 0
  for (const { m, col, flag = 0 } of parts) {
    const n = m.p.length / 3
    for (let k = 0; k < n; k++) {
      v.set([m.p[k * 3], m.p[k * 3 + 1], m.p[k * 3 + 2], m.n[k * 3], m.n[k * 3 + 1], m.n[k * 3 + 2], col[0], col[1], col[2], flag, m.uv[k * 2] || 0, m.uv[k * 2 + 1] || 0], vo)
      vo += 12
    }
    for (const idx of m.i) i[io++] = base + idx
    base += n
  }
  return { v, i, count: tris }
}

/** sRGB triplet from hue (degrees), saturation and lightness (0..1). Scene art is defined in numbers, UI chrome in theme tokens. */
export function paint(h, s, l) {
  const k = n => (n + h / 30) % 12
  const a = s * Math.min(l, 1 - l)
  const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))
  return [f(0), f(8), f(4)]
}

// ---------------------------------------------------------------- dice: polyhedra, faces, resting orientation

const PHI = (1 + Math.sqrt(5)) / 2
const DIE_RADIUS = { 4: 0.66, 6: 0.62, 8: 0.58, 10: 0.58, 12: 0.55, 20: 0.56 }
export const DIE_SIDES = [4, 6, 8, 10, 12, 20]

function sign3() { const o = []; for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) o.push([x, y, z]); return o }
function signed(pairs) {
  const o = []
  for (const [x, y, z] of pairs) for (const sx of x ? [-1, 1] : [1]) for (const sy of y ? [-1, 1] : [1]) for (const sz of z ? [-1, 1] : [1]) o.push([x * sx, y * sy, z * sz])
  return o
}
const ICOSA = signed([[0, 1, PHI], [1, PHI, 0], [PHI, 0, 1]]).map(vnorm)
// The dodecahedron is the icosahedron's dual: its corners are the icosahedron's face centres.
const DODECA = (() => {
  const raw = signed([[0, 1, PHI], [1, PHI, 0], [PHI, 0, 1]])
  const out = []
  for (let a = 0; a < raw.length; a++) for (let b = a + 1; b < raw.length; b++) for (let c = b + 1; c < raw.length; c++) {
    const near = (p, q) => Math.abs(vlen(vsub(raw[p], raw[q])) - 2) < 1e-6
    if (near(a, b) && near(b, c) && near(a, c)) out.push(vnorm(vadd(vadd(raw[a], raw[b]), raw[c])))
  }
  return out
})()

function shapeVerts(sides) {
  if (sides === 4) return [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]].map(vnorm)
  if (sides === 6) return sign3().map(vnorm)
  if (sides === 8) return [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
  if (sides === 12) return DODECA
  if (sides === 20) return ICOSA
  const h = 0.105, H = h * (2 / (1 - Math.cos(Math.PI / 5)) - 1)
  const v = [[0, H, 0], [0, -H, 0]]
  for (let k = 0; k < 10; k++) v.push([Math.sin((k * Math.PI) / 5), k % 2 ? h : -h, Math.cos((k * Math.PI) / 5)])
  const norm = Math.max(...v.map(vlen))
  return v.map(p => vmul(p, 1 / norm))
}
function shapeFaces(sides, verts) {
  if (sides === 10) {
    const R = k => 2 + (((k % 10) + 10) % 10)
    const out = []
    for (let j = 0; j < 5; j++) out.push([0, R(2 * j - 1), R(2 * j), R(2 * j + 1)], [1, R(2 * j), R(2 * j + 1), R(2 * j + 2)])
    return out
  }
  const normals = sides === 4 ? verts.map(v => vmul(v, -1)) : sides === 6 ? [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
    : sides === 8 ? sign3().map(vnorm) : sides === 12 ? ICOSA : DODECA
  return normals.map(n => {
    const d = Math.max(...verts.map(v => vdot(v, n)))
    return verts.map((v, k) => [k, vdot(v, n)]).filter(([, dp]) => Math.abs(dp - d) < 1e-6).map(([k]) => k)
  })
}

/** A die's geometry and labelling: faces with outward normals, face values, inradius and the vector that reads as "up" for a value. */
export function diceShape(sides) {
  if (!DIE_SIDES.includes(sides)) throw new Error(`no ${sides}-sided die`)
  const R = DIE_RADIUS[sides]
  const verts = shapeVerts(sides).map(v => vmul(v, R))
  const faces = shapeFaces(sides, verts).map(list => {
    const c = vmul(list.map(k => verts[k]).reduce(vadd, [0, 0, 0]), 1 / list.length)
    let n = vnorm(vcross(vsub(verts[list[1]], verts[list[0]]), vsub(verts[list[2]], verts[list[0]])))
    if (vdot(n, c) < 0) n = vmul(n, -1)
    const first = vsub(verts[list[0]], c)
    let up = vnorm(vsub(first, vmul(n, vdot(first, n))))
    if (sides === 6) {
      const mate = list.slice(1).sort((a, b) => vlen(vsub(verts[a], verts[list[0]])) - vlen(vsub(verts[b], verts[list[0]])))[0]
      up = vnorm(vsub(vmul(vadd(verts[list[0]], verts[mate]), 0.5), c))
    }
    const right = vcross(up, n)
    const idx = list.slice().sort((a, b) => {
      const pa = vsub(verts[a], c), pb = vsub(verts[b], c)
      return Math.atan2(vdot(pa, right), vdot(pa, up)) - Math.atan2(vdot(pb, right), vdot(pb, up))
    }).reverse()
    return { idx, n, c, up, right, value: 0, dist: vdot(c, n) }
  })
  faces.sort((a, b) => b.n[1] - a.n[1] || a.n[0] - b.n[0] || a.n[2] - b.n[2])
  if (sides === 4) faces.forEach((f, k) => { f.value = verts.findIndex(v => vdot(v, f.n) < -0.9 * R) + 1 || k + 1 })
  else {
    let next = 1
    for (const f of faces) {
      if (f.value) continue
      const anti = faces.find(o => o !== f && !o.value && vdot(o.n, f.n) < -0.999)
      f.value = next++
      if (anti) anti.value = sides + 1 - f.value
    }
  }
  const inr = Math.min(...faces.map(f => f.dist))
  const upOf = value => (sides === 4 ? vnorm(verts[value - 1]) : faces.find(f => f.value === value).n)
  return { sides, R, verts, faces, inr, upOf }
}

/** The pose that rests the die on the table with `value` on top, turned `yaw` about the vertical. d4 reads its top corner. */
export function faceUpQuat(shape, value, yaw = 0) {
  if (!(value >= 1 && value <= shape.sides)) throw new Error(`d${shape.sides} has no face ${value}`)
  return qmul(qaxis([0, 1, 0], yaw), qfromTo(shape.upOf(value), [0, 1, 0]))
}

/** Triangle fan around each face centre. UVs address one atlas cell per face (value for most dice, face index for d4). */
export function dieMesh(shape) {
  const m = meshOf()
  const cols = Math.ceil(Math.sqrt(shape.sides))
  shape.faces.forEach((f, fi) => {
    const cell = shape.sides === 4 ? fi : f.value - 1
    const cx = (cell % cols + 0.5) / cols, cy = (Math.floor(cell / cols) + 0.5) / cols
    const rmax = Math.max(...f.idx.map(k => vlen(vsub(shape.verts[k], f.c))))
    const k = 0.47 / cols / rmax
    const at = pt => { const d = vsub(pt, f.c); return [cx + vdot(d, f.right) * k, cy - vdot(d, f.up) * k] }
    const base = m.p.length / 3
    const ring = [f.c, ...f.idx.map(i => shape.verts[i])]
    for (const pt of ring) { m.p.push(...pt); m.n.push(...f.n); m.uv.push(...at(pt)) }
    for (let j = 1; j <= f.idx.length; j++) m.i.push(base, base + j, base + (j % f.idx.length) + 1)
  })
  return m
}

/** Where each die of a roll comes to rest in the tray: a grid centred on the tray, jittered but never overlapping. */
export function trayLayout(count, radius, rnd) {
  const per = count <= 4 ? count : Math.ceil(count / 2)
  const rows = Math.ceil(count / per)
  const gap = radius * 2.4
  const out = []
  for (let k = 0; k < count; k++) {
    const row = Math.floor(k / per), col = k % per
    const inRow = Math.min(per, count - row * per)
    const x = (col - (inRow - 1) / 2) * gap + (rnd() - 0.5) * radius * 0.2
    const z = (row - (rows - 1) / 2) * gap + (rnd() - 0.5) * radius * 0.2
    out.push([x, z])
  }
  return out
}

/** One die's flight: a throw from the edge, two bounces, a spin that decays into the exact resting pose. */
export function throwPlan(shape, value, target, rnd, rest) {
  const start = [target[0] + 5.5 + rnd() * 2, target[1] + 3.4 + rnd() * 1.5]
  const axis = vnorm([rnd() - 0.5, rnd() - 0.5 + 0.15, rnd() - 0.5])
  return {
    shape, value, target, start, rest, dur: 1.25 + rnd() * 0.25, axis, turns: 2.2 + rnd() * 1.8, yaw: rnd() * TAU,
    peak: 1.9 + rnd() * 0.7, mid: [mix(start[0], target[0], 0.62) + (rnd() - 0.5) * 0.6, mix(start[1], target[1], 0.62) + (rnd() - 0.5) * 0.4],
    q: faceUpQuat(shape, value, 0)
  }
}
export function throwPose(plan, t) {
  const u = clamp(t / plan.dur, 0, 1)
  const q = qmul(qaxis([0, 1, 0], plan.yaw), plan.q)
  const spin = (1 - easeOut(u)) * plan.turns * TAU
  const quat = u >= 1 ? q : qmul(qaxis(plan.axis, spin), q)
  let x, z, h
  if (u < 0.55) { const a = u / 0.55; x = mix(plan.start[0], plan.mid[0], a); z = mix(plan.start[1], plan.mid[1], a); h = plan.peak * 4 * a * (1 - a) }
  else if (u < 0.85) { const a = (u - 0.55) / 0.3; x = mix(plan.mid[0], plan.target[0], a * 0.85); z = mix(plan.mid[1], plan.target[1], a * 0.85); h = 0.55 * 4 * a * (1 - a) }
  else { const a = (u - 0.85) / 0.15; x = mix(mix(plan.mid[0], plan.target[0], 0.85), plan.target[0], ease(a)); z = mix(mix(plan.mid[1], plan.target[1], 0.85), plan.target[1], ease(a)); h = 0.1 * 4 * a * (1 - a) }
  return { pos: [x, plan.rest + h * (u < 1 ? 1 : 0), z], quat, done: u >= 1 }
}

// ---------------------------------------------------------------- painted miniatures, built from primitives

// Flags read by the surface shader: 1 team paint (vertex colour is a shade), 2 metal, 3 glow, 4 lacquer.
const F_TEAM = 1, F_METAL = 2, F_GLOW = 3, F_LACQUER = 4
const ART = {
  skin: paint(26, 0.5, 0.68), skinTan: paint(22, 0.42, 0.55), steel: paint(214, 0.1, 0.66), steelDark: paint(216, 0.12, 0.4),
  gold: paint(44, 0.78, 0.56), leather: paint(24, 0.5, 0.27), leatherLight: paint(30, 0.44, 0.4), cloth: paint(32, 0.2, 0.78),
  bone: paint(42, 0.24, 0.82), wood: paint(26, 0.5, 0.3), ink: paint(220, 0.2, 0.14), white: [0.92, 0.92, 0.92],
  goblin: paint(96, 0.46, 0.46), hobgoblin: paint(14, 0.6, 0.44), kobold: paint(18, 0.5, 0.42), zombie: paint(86, 0.2, 0.5),
  orc: paint(112, 0.34, 0.34), ogre: paint(36, 0.4, 0.6), wolf: paint(212, 0.08, 0.46), direWolf: paint(218, 0.1, 0.27), rat: paint(26, 0.22, 0.34),
  eyeGold: paint(52, 1, 0.6), eyeRed: paint(2, 0.9, 0.55), hair: paint(24, 0.4, 0.2), rust: paint(20, 0.5, 0.34), cyan: paint(190, 0.9, 0.62)
}
const shade = (c, k) => [c[0] * k, c[1] * k, c[2] * k]
const TEAM = [0.92, 0.92, 0.92]

function figure(radius = 0.43, k = 1) {
  const parts = []
  const to = (t, s) => [t[0] * k, 0.105 + t[1] * k, t[2] * k]
  const add = (m, col, flag = 0, t = [0, 0, 0], r = [0, 0, 0], s = [1, 1, 1]) => {
    const sc = typeof s === 'number' ? [s, s, s] : s
    parts.push({ m: xf(m, to(t), r, [sc[0] * k, sc[1] * k, sc[2] * k]), col, flag })
  }
  // A limb or blade between two points (feet-relative, before scale).
  const bar = (a, b, r0, r1, col, flag = 0) => {
    const d = vsub(b, a)
    const len = vlen(d)
    add(cyl(r0, r1, len, 7), col, flag, a, qfromTo([0, 1, 0], vnorm(d)))
  }
  const blade = (a, b, w, d, col, flag = F_METAL) => {
    const dir = vsub(b, a), len = vlen(dir)
    add(box(w, len, d), col, flag, vmul(vadd(a, b), 0.5), qfromTo([0, 1, 0], vnorm(dir)))
  }
  const raw = (m, col, flag, t, r, s) => parts.push({ m: xf(m, t, r, s), col, flag })
  raw(lathe([[0, 0], [radius, 0], [radius + 0.025, 0.03], [radius + 0.025, 0.075], [radius - 0.03, 0.105], [0, 0.105]], 22), [0.8, 0.8, 0.8], F_TEAM)
  raw(cyl(radius - 0.05, radius - 0.07, 0.01, 22), shade(ART.ink, 1.7), 0, [0, 0.1, 0])
  return { parts, add, bar, blade }
}

/** The common biped: legs, torso, arms, head. Returns the head centre so hats and helms can sit on it. */
function biped(b, o) {
  const { legs = ART.leather, torso = ART.leather, tf = 0, skin = ART.skin, arm = torso, af = tf, lean = 0, thick = 1, head = 0.15 } = o
  for (const s of [-1, 1]) {
    b.bar([s * 0.1 * thick, 0, 0], [s * 0.1 * thick, 0.44, 0], 0.075 * thick, 0.065 * thick, legs)
    b.add(box(0.14 * thick, 0.08, 0.22), shade(legs, 0.6), 0, [s * 0.1 * thick, 0.04, 0.04])
  }
  b.add(lathe([[0, 0], [0.17 * thick, 0], [0.2 * thick, 0.1], [0.235 * thick, 0.28], [0.2 * thick, 0.38], [0.11, 0.44], [0, 0.44]], 10), torso, tf, [0, 0.4, 0], [lean, 0, 0])
  for (const s of [-1, 1]) {
    b.bar([s * 0.25 * thick, 0.8, lean * 0.1], [s * 0.31 * thick, 0.5, 0.1 + lean * 0.5], 0.058 * thick, 0.046 * thick, arm, af)
    b.add(sphere(0.058, 8, 5), skin, 0, [s * 0.31 * thick, 0.47, 0.1 + lean * 0.5])
  }
  const h = [0, 0.99 + lean * 0.05, lean * 0.18]
  b.add(sphere(head, 10, 6), skin, 0, h, [0, 0, 0], [1, 1.08, 1])
  return h
}
const eyes = (b, h, col, r = 0.022, y = 0.02, spread = 0.062, z = 0.13) => { for (const s of [-1, 1]) b.add(sphere(r, 6, 4), col, F_GLOW, [h[0] + s * spread, h[1] + y, h[2] + z]) }

const MINI_BUILDERS = {
  fighter(b) {
    const h = biped(b, { torso: ART.steelDark, tf: F_METAL, legs: shade(ART.leather, 0.8), arm: ART.steel, af: F_METAL })
    b.add(box(0.27, 0.34, 0.03), TEAM, F_TEAM, [0, 0.58, 0.215])
    b.add(sphere(0.17, 10, 6), ART.steel, F_METAL, [h[0], h[1] + 0.03, h[2]], [0, 0, 0], [1, 0.82, 1])
    b.add(box(0.035, 0.12, 0.03), ART.steel, F_METAL, [0, h[1] - 0.01, 0.17])
    b.add(box(0.03, 0.2, 0.2), TEAM, F_TEAM, [0, h[1] + 0.18, 0], [0, 0, 0])
    b.add(cyl(0.27, 0.27, 0.045, 14), TEAM, F_TEAM, [-0.36, 0.58, 0.2], [Math.PI / 2, 0, 0])
    b.add(sphere(0.07, 8, 5), ART.gold, F_METAL, [-0.36, 0.58, 0.245], [0, 0, 0], [1, 1, 0.6])
    b.blade([0.33, 0.52, 0.12], [0.36, 1.22, 0.3], 0.065, 0.022, ART.steel)
    b.add(box(0.22, 0.04, 0.05), ART.gold, F_METAL, [0.33, 0.55, 0.13])
    b.add(sphere(0.04, 6, 4), ART.gold, F_METAL, [0.325, 0.47, 0.11])
  },
  rogue(b) {
    const h = biped(b, { torso: shade(ART.ink, 1.3), legs: ART.ink, arm: ART.leather, thick: 0.88 })
    b.add(cone(0.2, 0.46, 10), TEAM, F_TEAM, [h[0], h[1] - 0.02, h[2] - 0.03], [-0.5, 0, 0])
    b.add(sphere(0.175, 10, 6), shade(TEAM, 0.7), F_TEAM, [h[0], h[1] + 0.02, h[2] - 0.02], [0, 0, 0], [1, 0.95, 1])
    b.add(box(0.2, 0.09, 0.05), shade(ART.ink, 0.8), 0, [0, h[1] - 0.07, 0.125])
    b.add(lathe([[0, 0], [0.3, 0], [0.22, 0.4], [0.16, 0.8], [0, 0.82]], 9), TEAM, F_TEAM, [0, 0.02, -0.13], [0, 0, 0], [1, 1, 0.45])
    b.blade([0.31, 0.46, 0.1], [0.4, 0.78, 0.34], 0.045, 0.014, ART.steel)
    b.blade([-0.2, 0.44, 0.18], [-0.26, 0.2, 0.2], 0.04, 0.014, ART.steel)
    b.add(box(0.28, 0.05, 0.05), ART.leatherLight, 0, [0, 0.42, 0.1])
  },
  wizard(b) {
    b.add(lathe([[0, 0], [0.34, 0], [0.3, 0.2], [0.22, 0.5], [0.21, 0.82], [0.12, 0.9], [0, 0.92]], 12), TEAM, F_TEAM, [0, 0, 0])
    for (const s of [-1, 1]) {
      b.bar([s * 0.22, 0.8, 0], [s * 0.34, 0.5, 0.14], 0.07, 0.1, shade(TEAM, 0.82), F_TEAM)
      b.add(sphere(0.055, 8, 5), ART.skin, 0, [s * 0.33, 0.45, 0.16])
    }
    const h = [0, 1.0, 0]
    b.add(sphere(0.15, 10, 6), ART.skin, 0, h, [0, 0, 0], [1, 1.08, 1])
    b.add(cone(0.12, 0.34, 8), ART.cloth, 0, [0, 0.78, 0.14], [Math.PI + 0.12, 0, 0])
    b.add(cyl(0.28, 0.28, 0.03, 14), shade(TEAM, 0.7), F_TEAM, [0, 1.08, 0], [0.12, 0, 0])
    b.add(cone(0.18, 0.34, 10), shade(TEAM, 0.7), F_TEAM, [0, 1.1, 0.01], [0.12, 0, 0])
    b.add(cone(0.1, 0.3, 8), shade(TEAM, 0.7), F_TEAM, [0, 1.38, 0.09], [0.55, 0, 0])
    b.add(torus(0.17, 0.018, 12, 4), ART.gold, F_METAL, [0, 1.12, 0], [0.12, 0, 0])
    b.bar([0.36, 0, 0.14], [0.36, 1.36, 0.14], 0.03, 0.026, ART.wood)
    b.add(sphere(0.075, 8, 5), ART.cyan, F_GLOW, [0.36, 1.44, 0.14])
    b.add(torus(0.09, 0.012, 10, 4), ART.gold, F_METAL, [0.36, 1.38, 0.14], [Math.PI / 2, 0, 0])
    eyes(b, h, ART.ink, 0.016)
  },
  cleric(b) {
    const h = biped(b, { torso: ART.steel, tf: F_METAL, legs: ART.leatherLight, arm: ART.steel, af: F_METAL, skin: ART.skinTan })
    b.add(box(0.3, 0.4, 0.03), ART.cloth, 0, [0, 0.56, 0.22])
    b.add(box(0.07, 0.4, 0.035), TEAM, F_TEAM, [0, 0.56, 0.225])
    b.add(box(0.2, 0.06, 0.035), TEAM, F_TEAM, [0, 0.66, 0.226])
    b.add(sphere(0.16, 10, 6), ART.hair, 0, [h[0], h[1] + 0.05, h[2] - 0.02], [0, 0, 0], [1, 0.7, 1])
    b.add(cyl(0.2, 0.2, 0.04, 12), ART.gold, F_METAL, [-0.37, 0.56, 0.16], [Math.PI / 2, 0, 0])
    b.add(sphere(0.06, 8, 5), TEAM, F_TEAM, [-0.37, 0.56, 0.2], [0, 0, 0], [1, 1, 0.6])
    b.bar([0.31, 0.44, 0.12], [0.33, 1.0, 0.26], 0.035, 0.03, ART.wood)
    b.add(sphere(0.1, 8, 5), ART.steel, F_METAL, [0.33, 1.06, 0.28])
    for (const [dx, dy, dz] of [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, -1]]) b.add(cone(0.035, 0.09, 5), ART.steel, F_METAL, [0.33 + dx * 0.1, 1.06 + dy * 0.1, 0.28 + dz * 0.1], qfromTo([0, 1, 0], [dx, dy, dz]))
    b.add(sphere(0.045, 8, 5), ART.gold, F_GLOW, [0, 0.74, 0.245], [0, 0, 0], [1, 1, 0.4])
  },
  goblin(b) {
    const h = biped(b, { skin: ART.goblin, torso: ART.leather, legs: ART.goblin, arm: ART.goblin, head: 0.17, thick: 0.9 })
    for (const s of [-1, 1]) b.add(cone(0.06, 0.26, 6), ART.goblin, 0, [h[0] + s * 0.16, h[1] + 0.02, h[2]], [0, 0, -s * 1.25])
    b.add(cone(0.035, 0.12, 6), ART.goblin, 0, [h[0], h[1] - 0.02, h[2] + 0.15], [Math.PI / 2, 0, 0])
    eyes(b, h, ART.eyeGold, 0.026, 0.035, 0.07, 0.14)
    b.add(box(0.28, 0.18, 0.03), ART.leatherLight, 0, [0, 0.36, 0.17])
    b.blade([0.31, 0.5, 0.12], [0.45, 0.9, 0.32], 0.07, 0.02, ART.steel)
  },
  hobgoblin(b) {
    const h = biped(b, { skin: ART.hobgoblin, torso: shade(ART.hobgoblin, 0.5), tf: F_METAL, legs: ART.leather, arm: ART.leatherLight, thick: 1.08 })
    b.add(sphere(0.165, 10, 6), ART.steelDark, F_METAL, [h[0], h[1] + 0.04, h[2]], [0, 0, 0], [1, 0.8, 1])
    b.add(box(0.18, 0.16, 0.03), ART.steelDark, F_METAL, [0, h[1] - 0.04, 0.15])
    b.add(cone(0.05, 0.24, 6), shade(ART.hobgoblin, 0.7), 0, [0, h[1] + 0.2, -0.02], [-0.35, 0, 0])
    for (const s of [-1, 1]) b.add(sphere(0.1, 8, 5), ART.steelDark, F_METAL, [s * 0.28, 0.84, 0])
    eyes(b, h, ART.eyeGold, 0.022, 0.0, 0.06, 0.14)
    b.blade([0.33, 0.5, 0.14], [0.38, 1.24, 0.3], 0.07, 0.02, ART.steel)
    b.add(box(0.2, 0.035, 0.05), ART.gold, F_METAL, [0.33, 0.54, 0.15])
  },
  kobold(b) {
    const h = biped(b, { skin: ART.kobold, torso: ART.leatherLight, legs: ART.kobold, arm: ART.kobold, head: 0.16, thick: 0.8 })
    b.add(cone(0.07, 0.17, 7), ART.kobold, 0, [h[0], h[1] - 0.04, h[2] + 0.17], [Math.PI / 2, 0, 0])
    for (const s of [-1, 1]) b.add(cone(0.03, 0.14, 5), ART.bone, 0, [h[0] + s * 0.09, h[1] + 0.14, h[2] - 0.02], [-0.3, 0, -s * 0.3])
    b.add(cone(0.06, 0.34, 6), ART.kobold, 0, [0, 0.36, -0.2], [-1.2, 0, 0])
    eyes(b, h, ART.eyeGold, 0.026, 0.05, 0.065, 0.12)
    b.bar([0.34, 0.2, 0.1], [0.4, 1.12, 0.28], 0.022, 0.02, ART.wood)
    b.add(cone(0.04, 0.16, 5), ART.steel, F_METAL, [0.4, 1.12, 0.28], qfromTo([0, 1, 0], vnorm([0.06, 0.92, 0.18])))
  },
  skeleton(b) {
    const h = [0, 1.0, 0.01]
    for (const s of [-1, 1]) { b.bar([s * 0.09, 0, 0], [s * 0.09, 0.44, 0], 0.035, 0.03, ART.bone); b.add(box(0.11, 0.05, 0.18), ART.bone, 0, [s * 0.09, 0.025, 0.04]) }
    b.add(box(0.26, 0.09, 0.12), ART.bone, 0, [0, 0.46, 0])
    b.bar([0, 0.5, -0.02], [0, 0.88, -0.02], 0.03, 0.03, ART.bone)
    for (let k = 0; k < 4; k++) b.add(sphere(0.2 - k * 0.012, 10, 4), shade(ART.bone, 0.96 - k * 0.04), 0, [0, 0.56 + k * 0.085, 0.02], [0, 0, 0], [1, 0.2, 0.62])
    b.add(box(0.5, 0.05, 0.1), ART.bone, 0, [0, 0.88, 0])
    for (const s of [-1, 1]) {
      b.bar([s * 0.26, 0.86, 0], [s * 0.3, 0.48, 0.1], 0.032, 0.026, ART.bone)
      b.add(sphere(0.04, 6, 4), ART.bone, 0, [s * 0.3, 0.45, 0.1])
    }
    b.add(sphere(0.15, 10, 6), ART.bone, 0, h, [0, 0, 0], [0.95, 1.08, 1])
    b.add(box(0.14, 0.06, 0.12), ART.bone, 0, [0, h[1] - 0.14, 0.05])
    for (const s of [-1, 1]) b.add(sphere(0.036, 6, 4), ART.ink, 0, [s * 0.06, h[1] + 0.01, 0.13])
    b.blade([0.31, 0.5, 0.12], [0.36, 1.12, 0.3], 0.055, 0.016, ART.rust, 0)
    b.add(box(0.18, 0.03, 0.04), ART.wood, 0, [0.32, 0.54, 0.13])
    b.add(cyl(0.2, 0.2, 0.035, 12), ART.wood, 0, [-0.36, 0.55, 0.16], [Math.PI / 2, 0, 0])
  },
  zombie(b) {
    const h = biped(b, { skin: ART.zombie, torso: ART.rust, legs: shade(ART.leather, 0.7), arm: ART.zombie, lean: 0.34, head: 0.16 })
    for (const s of [-1, 1]) {
      b.bar([s * 0.25, 0.78, 0.12], [s * 0.2, 0.7, 0.62], 0.055, 0.045, ART.zombie)
      b.add(sphere(0.06, 8, 5), ART.zombie, 0, [s * 0.2, 0.7, 0.64])
    }
    b.add(box(0.1, 0.03, 0.03), ART.ink, 0, [h[0], h[1] - 0.07, h[2] + 0.15])
    eyes(b, h, ART.bone, 0.03, 0.03, 0.065, 0.13)
    b.add(box(0.3, 0.14, 0.04), shade(ART.rust, 0.7), 0, [0, 0.35, 0.16])
  },
  orc(b) {
    const h = biped(b, { skin: ART.orc, torso: ART.leather, legs: shade(ART.leather, 0.8), arm: ART.orc, thick: 1.25, head: 0.16 })
    for (const s of [-1, 1]) {
      b.add(cone(0.032, 0.11, 6), ART.bone, 0, [h[0] + s * 0.07, h[1] - 0.06, h[2] + 0.12], [0.2, 0, 0])
      b.add(sphere(0.12, 8, 5), ART.steelDark, F_METAL, [s * 0.34, 0.83, 0])
      b.add(cone(0.035, 0.1, 5), ART.steel, F_METAL, [s * 0.38, 0.93, 0])
    }
    b.add(box(0.2, 0.07, 0.07), shade(ART.orc, 0.7), 0, [0, h[1] + 0.05, 0.12])
    eyes(b, h, ART.eyeRed, 0.02, 0.025, 0.06, 0.135)
    b.add(box(0.6, 0.06, 0.34), ART.leatherLight, 0, [0, 0.42, 0])
    b.bar([0.4, 0.4, 0.1], [0.44, 1.12, 0.26], 0.03, 0.028, ART.wood)
    b.add(box(0.06, 0.28, 0.26), ART.steel, F_METAL, [0.44, 1.05, 0.34])
    b.add(box(0.05, 0.22, 0.2), ART.steel, F_METAL, [0.44, 1.05, 0.12])
  },
  bandit(b) {
    const h = biped(b, { torso: ART.leatherLight, legs: ART.ink, arm: ART.cloth, skin: ART.skinTan })
    b.add(sphere(0.158, 10, 6), shade(ART.eyeRed, 0.7), 0, [h[0], h[1] + 0.05, h[2] - 0.005], [0, 0, 0], [1, 0.72, 1])
    b.add(cone(0.05, 0.14, 6), shade(ART.eyeRed, 0.7), 0, [0.1, h[1] + 0.06, -0.12], [-1.2, 0, -0.6])
    b.add(box(0.2, 0.09, 0.05), ART.ink, 0, [0, h[1] - 0.06, 0.125])
    b.add(box(0.3, 0.07, 0.07), ART.leather, 0, [0, 0.42, 0.1])
    b.blade([0.31, 0.5, 0.12], [0.36, 0.92, 0.28], 0.05, 0.016, ART.steel)
    b.add(cyl(0.18, 0.18, 0.035, 12), ART.wood, 0, [-0.34, 0.5, 0.18], [Math.PI / 2, 0, 0])
  },
  bandit_captain(b) {
    const h = biped(b, { torso: shade(ART.eyeRed, 0.45), legs: ART.ink, arm: shade(ART.eyeRed, 0.55), skin: ART.skinTan, thick: 1.08 })
    b.add(lathe([[0, 0], [0.36, 0], [0.26, 0.5], [0.18, 0.84], [0, 0.86]], 9), shade(ART.eyeRed, 0.4), 0, [0, 0.03, -0.14], [0, 0, 0], [1, 1, 0.42])
    b.add(cyl(0.26, 0.26, 0.03, 14), ART.ink, 0, [h[0], h[1] + 0.08, h[2]], [-0.1, 0, 0])
    b.add(cyl(0.16, 0.14, 0.14, 12), ART.ink, 0, [h[0], h[1] + 0.09, h[2]])
    b.bar([0.1, h[1] + 0.16, -0.05], [0.24, h[1] + 0.42, -0.2], 0.012, 0.004, ART.eyeRed)
    b.add(box(0.34, 0.05, 0.06), ART.gold, F_METAL, [0, 0.62, 0.21])
    b.blade([0.33, 0.52, 0.12], [0.4, 1.22, 0.3], 0.05, 0.016, ART.steel)
    b.add(box(0.2, 0.035, 0.05), ART.gold, F_METAL, [0.33, 0.55, 0.13])
  },
  giant_rat(b) {
    b.add(sphere(0.2, 10, 6), ART.rat, 0, [0, 0.22, -0.02], [0, 0, 0], [0.85, 0.7, 1.45])
    b.add(sphere(0.12, 8, 5), ART.rat, 0, [0, 0.26, 0.3], [0, 0, 0], [0.9, 0.85, 1.15])
    b.add(cone(0.075, 0.2, 7), shade(ART.rat, 1.3), 0, [0, 0.25, 0.43], [Math.PI / 2, 0, 0])
    b.add(sphere(0.03, 6, 4), shade(ART.skin, 1.1), 0, [0, 0.26, 0.54])
    for (const s of [-1, 1]) {
      b.add(sphere(0.06, 8, 5), shade(ART.skin, 0.95), 0, [s * 0.09, 0.37, 0.24], [0, 0, 0], [1, 1, 0.3])
      b.add(sphere(0.022, 6, 4), ART.eyeRed, F_GLOW, [s * 0.06, 0.3, 0.38])
      b.add(box(0.016, 0.05, 0.012), ART.bone, 0, [s * 0.015, 0.2, 0.52])
      for (const z of [0.12, -0.14]) b.bar([s * 0.1, 0, z], [s * 0.1, 0.18, z], 0.03, 0.026, ART.rat)
    }
    let p = [0, 0.2, -0.26]
    for (let k = 0; k < 5; k++) { const q = [0, 0.2 + Math.sin(k * 0.7) * 0.08 + k * 0.02, -0.26 - (k + 1) * 0.1]; b.bar(p, q, 0.02 - k * 0.002, 0.018 - k * 0.002, shade(ART.skin, 0.95)); p = q }
  },
  wolf(b, o = {}) {
    const fur = o.fur || ART.wolf
    b.add(sphere(0.2, 10, 6), fur, 0, [0, 0.43, -0.05], [0, 0, 0], [0.9, 0.95, 1.7])
    b.add(sphere(0.18, 10, 6), shade(fur, 1.25), 0, [0, 0.38, 0.0], [0, 0, 0], [0.85, 0.8, 1.5])
    b.add(sphere(0.15, 8, 5), fur, 0, [0, 0.52, 0.34], [0, 0, 0], [1, 0.95, 1.05])
    b.add(cone(0.075, 0.24, 8), shade(fur, 1.25), 0, [0, 0.47, 0.5], [Math.PI / 2 + 0.2, 0, 0])
    b.add(sphere(0.03, 6, 4), ART.ink, 0, [0, 0.45, 0.63])
    for (const s of [-1, 1]) {
      b.add(cone(0.045, 0.14, 5), shade(fur, 0.8), 0, [s * 0.08, 0.66, 0.3], [0, 0, -s * 0.2])
      b.add(sphere(0.024, 6, 4), o.eye || ART.eyeGold, F_GLOW, [s * 0.075, 0.55, 0.44])
      b.add(cone(0.012, 0.05, 4), ART.bone, 0, [s * 0.03, 0.4, 0.58], [Math.PI, 0, 0])
      for (const z of [0.22, -0.28]) { b.bar([s * 0.12, 0, z], [s * 0.12, 0.4, z], 0.05, 0.038, fur); b.add(box(0.07, 0.04, 0.12), shade(fur, 0.6), 0, [s * 0.12, 0.02, z + 0.03]) }
    }
    b.add(cone(0.07, 0.38, 7), shade(fur, 0.9), 0, [0, 0.5, -0.48], [-1.95, 0, 0])
  },
  dire_wolf(b) {
    MINI_BUILDERS.wolf(b, { fur: ART.direWolf, eye: ART.eyeRed })
    for (let k = 0; k < 6; k++) b.add(cone(0.035, 0.12, 5), shade(ART.direWolf, 0.6), 0, [0, 0.62 - k * 0.012, 0.3 - k * 0.13], [-0.1, 0, 0])
  },
  ogre(b) {
    const h = biped(b, { skin: ART.ogre, torso: ART.ogre, legs: ART.ogre, arm: ART.ogre, thick: 1.5, head: 0.14, lean: 0.12 })
    b.add(sphere(0.3, 10, 6), ART.ogre, 0, [0, 0.55, 0.06], [0, 0, 0], [1.1, 1, 0.95])
    b.add(lathe([[0, 0], [0.34, 0], [0.3, 0.2], [0.26, 0.3], [0, 0.3]], 10), ART.leather, 0, [0, 0.38, 0], [0, 0, 0], [1, 1, 0.95])
    b.add(box(0.5, 0.06, 0.3), ART.leather, 0, [0, 0.62, 0.08])
    for (const s of [-1, 1]) b.add(cone(0.032, 0.12, 5), ART.bone, 0, [h[0] + s * 0.07, h[1] - 0.06, h[2] + 0.12], [0.2, 0, 0])
    eyes(b, h, ART.eyeRed, 0.022, 0.03, 0.06, 0.13)
    b.bar([0.5, 0.35, 0.1], [0.55, 1.35, 0.35], 0.045, 0.1, ART.wood)
    for (let k = 0; k < 4; k++) b.add(cone(0.03, 0.08, 5), ART.steel, F_METAL, [0.55 + Math.cos(k * 1.6) * 0.1, 1.15 + k * 0.05, 0.33 + Math.sin(k * 1.6) * 0.1], qfromTo([0, 1, 0], [Math.cos(k * 1.6), 0.2, Math.sin(k * 1.6)]))
    b.add(sphere(0.07, 6, 4), ART.skin, 0, [0.5, 0.33, 0.1], [0, 0, 0], [1.3, 1.3, 1.3])
  },
  generic(b) {
    b.add(lathe([[0, 0], [0.24, 0], [0.22, 0.07], [0.13, 0.26], [0.1, 0.46], [0.18, 0.5], [0.12, 0.55], [0.14, 0.6], [0, 0.62]], 12), TEAM, F_TEAM)
    b.add(sphere(0.17, 10, 6), TEAM, F_TEAM, [0, 0.76, 0])
  }
}
const MINI_SCALE = { goblin: 0.82, kobold: 0.78, hobgoblin: 1, orc: 1.1, bandit_captain: 1.08, wolf: 1, dire_wolf: 1.3, giant_rat: 0.9, ogre: 1.38, skeleton: 1, zombie: 1, generic: 1 }
const MINI_BASE = { ogre: 0.62, dire_wolf: 0.52, wolf: 0.45, orc: 0.45, goblin: 0.38, kobold: 0.36, giant_rat: 0.38 }
export const MINI_LOOKS = Object.keys(MINI_BUILDERS)

/** Which miniature a creature gets: its srd key, then its class, then the words in its name, else a pawn. */
export function lookOf(raw) {
  const key = String(raw?.id ?? '').toLowerCase().replace(/-\d+$/, '').replace(/[^a-z]+/g, '_').replace(/^_|_$/g, '')
  if (MINI_BUILDERS[key] && key !== 'generic') return key
  const klass = String(raw?.class ?? raw?.klass ?? '').toLowerCase()
  const classes = { fighter: 'fighter', barbarian: 'fighter', paladin: 'fighter', rogue: 'rogue', ranger: 'rogue', bard: 'rogue', wizard: 'wizard', sorcerer: 'wizard', warlock: 'wizard', cleric: 'cleric', druid: 'cleric', monk: 'cleric' }
  if (classes[klass]) return classes[klass]
  const words = String(raw?.name ?? '').toLowerCase().replace(/[^a-z ]+/g, ' ').trim().replace(/\s+/g, '_')
  const hit = MINI_LOOKS.filter(k => k !== 'generic').sort((a, b) => b.length - a.length).find(k => words.includes(k))
  return hit || 'generic'
}

const miniCache = new Map()
/** Merged vertex data for a look, plus the base radius used for its ring and shadow. */
export function buildMini(look) {
  if (miniCache.has(look)) return miniCache.get(look)
  const radius = MINI_BASE[look] || 0.43
  const b = figure(radius, MINI_SCALE[look] || 1)
  ;(MINI_BUILDERS[look] || MINI_BUILDERS.generic)(b)
  const out = { ...combine(b.parts), radius, look }
  miniCache.set(look, out)
  return out
}

// ================================================================ 3D tabletop: shaders and procedural textures

const GLSL_HI = '#ifdef GL_FRAGMENT_PRECISION_HIGH\nprecision highp float;\n#else\nprecision mediump float;\n#endif\n'
const SURF_VS = `
attribute vec3 aPos; attribute vec3 aNor; attribute vec3 aCol; attribute float aFlag; attribute vec2 aUv;
uniform mat4 uModel; uniform mat4 uVP; uniform mat4 uLVP;
varying vec3 vW; varying vec3 vN; varying vec3 vC; varying float vF; varying vec2 vUV; varying vec4 vL;
void main(){
  vec4 w = uModel * vec4(aPos, 1.0);
  vW = w.xyz; vN = mat3(uModel) * aNor; vC = aCol; vF = aFlag; vUV = aUv;
  vL = uLVP * vec4(w.xyz + normalize(vN) * 0.03, 1.0);
  gl_Position = uVP * w;
}`
const SURF_FS = `
varying vec3 vW; varying vec3 vN; varying vec3 vC; varying float vF; varying vec2 vUV; varying vec4 vL;
uniform vec3 uCam; uniform vec3 uSun; uniform vec3 uSunCol; uniform vec3 uSky; uniform vec3 uGround; uniform vec3 uFog; uniform float uFogD;
uniform vec3 uTeam; uniform vec3 uGlow; uniform vec4 uFlash; uniform float uDesat; uniform float uTexMode;
uniform float uShine; uniform float uSpec; uniform vec3 uBody; uniform vec3 uInk;
uniform vec4 uPL0; uniform vec4 uPL1; uniform vec3 uPLCol; uniform vec2 uTexel; uniform float uShadowOn;
uniform sampler2D uTex; uniform sampler2D uShadow;
float unpackD(vec4 c){ return dot(c, vec4(1.0, 1.0/255.0, 1.0/65025.0, 1.0/16581375.0)); }
float shadowAt(){
  vec3 p = vL.xyz / vL.w * 0.5 + 0.5;
  if (uShadowOn < 0.5 || p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0) return 1.0;
  float s = 0.0;
  for (int x = -1; x <= 1; x++) for (int y = -1; y <= 1; y++) {
    float d = unpackD(texture2D(uShadow, p.xy + vec2(float(x), float(y)) * uTexel * 1.7));
    s += (p.z - 0.0032 > d) ? 0.0 : 1.0;
  }
  return s / 9.0;
}
vec3 lin(vec3 c){ return pow(max(c, vec3(0.0)), vec3(2.2)); }
vec3 aces(vec3 x){ return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
vec3 candle(vec4 pl, vec3 N){
  vec3 d = pl.xyz - vW; float r2 = dot(d, d);
  return uPLCol * pl.w * max(dot(N, normalize(d)), 0.0) / (1.0 + 0.16 * r2);
}
void main(){
  vec3 N = normalize(vN); vec3 V = normalize(uCam - vW);
  float team = step(0.5, vF) * step(vF, 1.5);
  float metal = step(1.5, vF) * step(vF, 2.5);
  float glow = step(2.5, vF) * step(vF, 3.5);
  float lacq = step(3.5, vF) * step(vF, 4.5);
  float tglow = step(4.5, vF);
  vec3 alb = lin(vC);
  if (team > 0.5) alb = lin(uTeam) * (vC.r * 1.08);
  if (tglow > 0.5) alb = lin(uTeam);
  if (uTexMode > 0.5 && uTexMode < 1.5) alb = lin(texture2D(uTex, vUV).rgb) * lin(vC);
  if (uTexMode > 1.5) alb = mix(lin(uBody), lin(uInk), texture2D(uTex, vUV).r);
  float ndl = max(dot(N, uSun), 0.0);
  float sh = ndl > 0.0 ? shadowAt() : 1.0;
  float pool = mix(0.46, 1.0, smoothstep(26.0, 6.0, length(vW.xz - vec2(0.0, 1.5))));
  vec3 hemi = mix(uGround, uSky, N.y * 0.5 + 0.5);
  vec3 diff = uSunCol * ndl * sh * pool + hemi + candle(uPL0, N) + candle(uPL1, N);
  float shin = metal > 0.5 ? 70.0 : (lacq > 0.5 ? 90.0 : uShine);
  float ks = metal > 0.5 ? 0.85 : (lacq > 0.5 ? 0.5 : uSpec);
  vec3 H = normalize(uSun + V);
  vec3 spec = uSunCol * pow(max(dot(N, H), 0.0), shin) * ks * sh * pool;
  float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
  vec3 col = alb * diff + spec + uSky * rim * 0.16;
  if (metal > 0.5) { vec3 rf = reflect(-V, N); col = mix(col, alb * mix(uGround * 1.5, uSky * 2.2, rf.y * 0.5 + 0.5) + spec, 0.55); }
  col += uGlow;
  if (glow > 0.5 || tglow > 0.5) col = alb * 1.9;
  col = mix(col, vec3(dot(col, vec3(0.3, 0.59, 0.11))), uDesat);
  col += uFlash.rgb * uFlash.a;
  float dist = length(uCam - vW);
  col = mix(col, lin(uFog), 1.0 - exp(-uFogD * uFogD * dist * dist));
  gl_FragColor = vec4(pow(aces(col), vec3(1.0 / 2.2)), 1.0);
}`
const DEPTH_VS = `attribute vec3 aPos; uniform mat4 uModel; uniform mat4 uLVP; void main(){ gl_Position = uLVP * uModel * vec4(aPos, 1.0); }`
const DEPTH_FS = `
void main(){
  float d = gl_FragCoord.z;
  vec4 e = fract(d * vec4(1.0, 255.0, 65025.0, 16581375.0));
  e -= e.yzww * vec4(1.0 / 255.0, 1.0 / 255.0, 1.0 / 255.0, 0.0);
  gl_FragColor = e;
}`
const DECAL_VS = `attribute vec3 aPos; uniform mat4 uModel; uniform mat4 uVP; varying vec2 vP; void main(){ vP = aPos.xy; gl_Position = uVP * uModel * vec4(aPos.xy, 0.0, 1.0); }`
const DECAL_FS = `
varying vec2 vP; uniform vec4 uCol; uniform float uMode; uniform float uFrac; uniform float uA; uniform float uTime;
void main(){
  float r = length(vP);
  vec3 c = uCol.rgb; float a = 0.0;
  if (uMode < 0.5) { a = (1.0 - smoothstep(0.05, 1.0, r)) * uA; }
  else if (uMode < 1.5) {
    float edge = smoothstep(0.74, 0.79, r) * (1.0 - smoothstep(0.95, 1.0, r));
    float ang = atan(vP.x, vP.y); if (ang < 0.0) ang += 6.2831853;
    float on = 1.0 - smoothstep(uFrac - 0.004, uFrac + 0.004, ang / 6.2831853);
    c = mix(vec3(0.04), uCol.rgb, on) * (0.85 + 0.35 * on);
    a = edge * (0.5 + 0.5 * on) * uA;
  }
  else if (uMode < 2.5) { float g = exp(-pow((r - 0.8) * 4.2, 2.0)); a = g * uA * (0.7 + 0.3 * sin(uTime * 3.2)); }
  else if (uMode < 3.5) { a = exp(-r * r * 3.4) * uA; }
  else {
    vec2 p = vec2(vP.x * 1.9, vP.y * 0.5 + 0.5);
    float w = (1.0 - p.y) * 0.5 + 0.02;
    float body = smoothstep(w + 0.1, w - 0.02, abs(p.x)) * smoothstep(1.0, 0.55, p.y) * smoothstep(0.0, 0.1, p.y);
    c = mix(vec3(1.0, 0.5, 0.1), vec3(1.0, 0.93, 0.62), 1.0 - p.y);
    a = body * uA;
  }
  if (a < 0.003) discard;
  gl_FragColor = vec4(c, a);
}`
const BEAM_FS = `
varying vec3 vW; varying vec3 vN; varying vec2 vUV;
uniform vec3 uCam; uniform vec3 uGlow; uniform float uA;
void main(){
  float f = abs(dot(normalize(vN), normalize(uCam - vW)));
  float a = uA * pow(clamp(1.0 - vUV.y, 0.0, 1.0), 1.7) * (0.12 + 0.88 * f * f);
  gl_FragColor = vec4(uGlow, a);
}`
const VIG_VS = `attribute vec3 aPos; varying vec2 vP; void main(){ vP = aPos.xy; gl_Position = vec4(aPos.xy, 0.0, 1.0); }`
const VIG_FS = `
varying vec2 vP; uniform vec3 uCol; uniform float uA; uniform float uAsp;
void main(){
  float r = length(vP * vec2(0.82, 1.0));
  float a = smoothstep(0.55, 1.45, r) * uA;
  gl_FragColor = vec4(uCol, a);
}`

// Canvas colours are written as color(srgb ...) so every hue stays a number in the art palette, never a literal in UI code.
const css = (c, a = 1) => `color(srgb ${c[0].toFixed(4)} ${c[1].toFixed(4)} ${c[2].toFixed(4)} / ${a})`
const sheet = size => { const c = document.createElement('canvas'); c.width = c.height = size; return [c, c.getContext('2d')] }

function noiseTile(g, size, strength, rnd) {
  const img = g.createImageData(size, size)
  for (let k = 0; k < img.data.length; k += 4) { const v = rnd() * 255; img.data[k] = img.data[k + 1] = img.data[k + 2] = v; img.data[k + 3] = strength }
  const [t, tg] = sheet(size)
  tg.putImageData(img, 0, 0)
  return g.createPattern(t, 'repeat')
}

function woodSheet(size = 1024) {
  const [c, g] = sheet(size)
  const rnd = seeded(11)
  const planks = 7, ph = size / planks
  for (let p = 0; p < planks; p++) {
    const hue = 22 + rnd() * 8, light = 0.2 + rnd() * 0.07
    g.fillStyle = css(paint(hue, 0.52, light))
    g.fillRect(0, p * ph, size, ph)
    for (let k = 0; k < 90; k++) {
      const y0 = p * ph + rnd() * ph, amp = 0.8 + rnd() * 2.4, f1 = 1 + Math.floor(rnd() * 3), f2 = 3 + Math.floor(rnd() * 5), ph1 = rnd() * 6, ph2 = rnd() * 6
      g.strokeStyle = css(paint(hue - 3, 0.5, light * (rnd() < 0.55 ? 0.66 : 1.4)), 0.07 + rnd() * 0.16)
      g.lineWidth = 0.6 + rnd() * 1.8
      g.beginPath()
      for (let x = 0; x <= size; x += 16) {
        const y = y0 + Math.sin((x / size) * Math.PI * 2 * f1 + ph1) * amp + Math.sin((x / size) * Math.PI * 2 * f2 + ph2) * amp * 0.4
        x ? g.lineTo(x, y) : g.moveTo(x, y)
      }
      g.stroke()
    }
    for (let k = 0; k < 2; k++) {
      const kx = rnd() * size, ky = p * ph + ph * (0.25 + rnd() * 0.5), kr = 7 + rnd() * 12
      for (let ring = 4; ring > 0; ring--) { g.strokeStyle = css(paint(hue - 4, 0.55, light * 0.55), 0.18); g.lineWidth = 1.4; g.beginPath(); g.ellipse(kx, ky, kr * ring * 0.45, kr * ring * 0.22, 0, 0, Math.PI * 2); g.stroke() }
    }
    g.fillStyle = css(paint(20, 0.5, 0.06), 0.85)
    g.fillRect(0, p * ph - 1.5, size, 3)
    const joint = rnd() * size
    g.fillRect(joint, p * ph, 2.5, ph)
  }
  g.globalAlpha = 0.07
  g.fillStyle = noiseTile(g, 128, 255, rnd)
  g.fillRect(0, 0, size, size)
  return c
}

function feltSheet(size, tint, speckle = 0.16) {
  const [c, g] = sheet(size)
  const rnd = seeded(23)
  g.fillStyle = css(tint)
  g.fillRect(0, 0, size, size)
  for (let k = 0; k < 40; k++) {
    const x = rnd() * size, y = rnd() * size, r = size * (0.08 + rnd() * 0.22)
    const grad = g.createRadialGradient(x, y, 0, x, y, r)
    const lift = rnd() < 0.5
    grad.addColorStop(0, css(lift ? shade(tint, 1.25) : shade(tint, 0.7), 0.22))
    grad.addColorStop(1, css(tint, 0))
    g.fillStyle = grad
    g.fillRect(x - r, y - r, r * 2, r * 2)
  }
  g.globalCompositeOperation = 'overlay'
  g.globalAlpha = speckle
  g.fillStyle = noiseTile(g, 256, 255, rnd)
  g.fillRect(0, 0, size, size)
  g.globalAlpha = speckle * 0.6
  g.fillStyle = noiseTile(g, 64, 255, rnd)
  g.fillRect(0, 0, size, size)
  g.globalCompositeOperation = 'source-over'
  g.globalAlpha = 1
  return c
}

const BOARD_W = 13, BOARD_D = 11
/** The felt: 12 by 10 squares with hairline grid, a brass keyline and A-L / 1-10 labels on every edge. Mapped 1:1 onto the felt quad. */
function boardSheet(size = 2048) {
  const c = feltSheet(size, paint(150, 0.4, 0.22), 0.42)
  const g = c.getContext('2d')
  const sx = size / BOARD_W, sy = size / BOARD_D
  const edge = g.createRadialGradient(size / 2, size / 2, size * 0.22, size / 2, size / 2, size * 0.78)
  edge.addColorStop(0, css([0, 0, 0], 0))
  edge.addColorStop(1, css([0, 0, 0], 0.5))
  g.fillStyle = edge
  g.fillRect(0, 0, size, size)
  g.setTransform(sx, 0, 0, sy, (BOARD_W / 2) * sx, (BOARD_D / 2) * sy)
  const cream = paint(44, 0.35, 0.86)
  for (let x = 0; x < COLS; x++) for (let y = 0; y < ROWS; y++) {
    if ((x + y) % 2) { g.fillStyle = css(cream, 0.028); g.fillRect(x - COLS / 2, y - ROWS / 2, 1, 1) }
  }
  g.strokeStyle = css(cream, 0.34)
  g.lineWidth = 2.2 / sx
  g.beginPath()
  for (let i = 0; i <= COLS; i++) { g.moveTo(i - COLS / 2, -ROWS / 2); g.lineTo(i - COLS / 2, ROWS / 2) }
  for (let i = 0; i <= ROWS; i++) { g.moveTo(-COLS / 2, i - ROWS / 2); g.lineTo(COLS / 2, i - ROWS / 2) }
  g.stroke()
  g.strokeStyle = css(paint(44, 0.7, 0.58), 0.75)
  g.lineWidth = 4 / sx
  g.strokeRect(-COLS / 2 - 0.04, -ROWS / 2 - 0.04, COLS + 0.08, ROWS + 0.08)
  g.fillStyle = css(cream, 0.95)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  const label = (text, x, y) => { g.save(); g.translate(x, y); g.scale(1 / sx, 1 / sy); g.font = '700 58px ui-monospace, SFMono-Regular, Menlo, monospace'; g.fillText(text, 0, 0); g.restore() }
  for (let i = 0; i < COLS; i++) { const l = String.fromCharCode(65 + i); label(l, i - COLS / 2 + 0.5, -ROWS / 2 - 0.27); label(l, i - COLS / 2 + 0.5, ROWS / 2 + 0.27) }
  for (let i = 0; i < ROWS; i++) { label(String(i + 1), -COLS / 2 - 0.27, i - ROWS / 2 + 0.5); label(String(i + 1), COLS / 2 + 0.27, i - ROWS / 2 + 0.5) }
  return c
}

/** One atlas cell per face. White ink on black: the shader paints the body and ink colours, so a crit can turn the same die gold. */
function atlasSheet(shape, size = 1024) {
  const [c, g] = sheet(size)
  const cols = Math.ceil(Math.sqrt(shape.sides)), cell = size / cols
  g.fillStyle = css([0, 0, 0])
  g.fillRect(0, 0, size, size)
  g.fillStyle = css([1, 1, 1])
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  const pips = { 1: [[0, 0]], 2: [[-1, -1], [1, 1]], 3: [[-1, -1], [0, 0], [1, 1]], 4: [[-1, -1], [1, -1], [-1, 1], [1, 1]], 5: [[-1, -1], [1, -1], [0, 0], [-1, 1], [1, 1]], 6: [[-1, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [1, 1]] }
  shape.faces.forEach((f, fi) => {
    const idx = shape.sides === 4 ? fi : f.value - 1
    const cx = (idx % cols + 0.5) * cell, cy = (Math.floor(idx / cols) + 0.5) * cell
    if (shape.sides === 6) {
      for (const [px, py] of pips[f.value]) { g.beginPath(); g.arc(cx + px * cell * 0.22, cy + py * cell * 0.22, cell * 0.075, 0, Math.PI * 2); g.fill() }
    } else if (shape.sides === 4) {
      const rmax = Math.max(...f.idx.map(k => vlen(vsub(shape.verts[k], f.c))))
      const px = (0.47 * cell) / rmax
      g.font = `700 ${cell * 0.17}px ui-serif, Georgia, serif`
      for (const k of f.idx) {
        const d = vsub(shape.verts[k], f.c)
        const lx = vdot(d, f.right) * px * 0.6, ly = vdot(d, f.up) * px * 0.6
        g.save(); g.translate(cx + lx, cy - ly); g.rotate(Math.atan2(lx, ly)); g.fillText(String(k + 1), 0, 0); g.restore()
      }
    } else {
      const text = f.value === 6 || f.value === 9 ? `${f.value}.` : String(f.value)
      g.font = `700 ${cell * (shape.sides === 20 ? 0.34 : shape.sides === 12 ? 0.3 : 0.36)}px ui-serif, Georgia, serif`
      const shift = shape.sides === 20 || shape.sides === 8 ? 0.06 : shape.sides === 10 ? 0.12 : 0
      g.fillText(text, cx, cy + cell * 0.02 - shift * cell)
    }
  })
  return c
}

// ================================================================ 3D tabletop: the stage

const BOARD_Y = 0.16
const TRAY = { x: 0, z: 8.6, w: 9.4, d: 3.4, floor: 0.2 }
const SUN = vnorm([-0.5, 0.82, -0.3])
const CANDLES = [[-7.9, -6.2], [7.8, -6.0]]
const FOV = (38 * Math.PI) / 180
const SHADOW_SIZE = 2048
const MINI_SCALE_UP = 1.12
const HOME = { az: 0, el: 0.74, zoom: 1 }
const TONE_VARS = ['bg-editor', 'bg-elevated', 'red', 'green', 'yellow', 'blue', 'purple', 'cyan', 'orange', 'accent', 'accent-secondary', 'text-primary', 'text-secondary']
const TONE_FALLBACK = { 'bg-editor': [0.1, 0.1, 0.12], 'bg-elevated': [0.16, 0.16, 0.19], red: [0.9, 0.3, 0.3], green: [0.35, 0.78, 0.45], yellow: [0.95, 0.8, 0.3], blue: [0.35, 0.55, 0.95], purple: [0.65, 0.45, 0.9], cyan: [0.35, 0.8, 0.85], orange: [0.95, 0.6, 0.3], accent: [0.45, 0.6, 1], 'accent-secondary': [0.9, 0.5, 0.8], 'text-primary': [0.95, 0.95, 0.95], 'text-secondary': [0.7, 0.7, 0.75] }

const FIT_POINTS = [[-7.1, 0.2, -6.1], [7.1, 0.2, -6.1], [-7.1, 0.2, 6.1], [7.1, 0.2, 6.1], [-4.4, 0.5, 6.35 + 3.0], [4.4, 0.5, 6.35 + 3.0], [-4.4, 0.5, 10.0], [4.4, 0.5, 10.0], [-6, 1.9, -5], [6, 1.9, -5]]
const FIT_TARGET = [0, 0.4, 2.2]
const fitMemo = new Map()
/** Camera distance that frames the felt, the minis' height and the dice tray at the home angle for a given aspect ratio. */
export function fitDistance(aspect, el = HOME.el) {
  const key = `${aspect.toFixed(3)}:${el}`
  if (fitMemo.has(key)) return fitMemo.get(key)
  const proj = m4persp(FOV, aspect, 0.5, 140)
  const inside = d => {
    const m = m4mul(proj, m4look(orbitEye(FIT_TARGET, 0, el, d), FIT_TARGET))
    return FIT_POINTS.every(p => { const c = m4xf(m, p); return c[3] > 0 && Math.abs(c[0] / c[3]) <= 0.97 && Math.abs(c[1] / c[3]) <= 0.95 })
  }
  let lo = 4, hi = 90
  for (let k = 0; k < 22; k++) { const mid = (lo + hi) / 2; if (inside(mid)) hi = mid; else lo = mid }
  if (fitMemo.size > 20) fitMemo.clear()
  fitMemo.set(key, hi)
  return hi
}

/** Dice for a roll: sides from the formula, value from the engine; anything unreadable is dropped, never invented. */
export function diceOf(roll) {
  const out = []
  for (const d of roll.dice) {
    const sides = DIE_SIDES.includes(d.sides) ? d.sides : DIE_SIDES.find(s => s >= d.value) || 0
    if (!sides || !(d.value >= 1 && d.value <= sides)) continue
    out.push({ sides, value: d.value, dropped: d.dropped })
  }
  return out.slice(0, 8)
}

/** The value a die actually shows: the face whose normal points most nearly up after its live rotation. */
export function topValue(shape, quat) {
  if (shape.sides === 4) { let best = 1, y = -2; shape.verts.forEach((v, k) => { const d = qrot(quat, v)[1]; if (d > y) { y = d; best = k + 1 } }); return best }
  let best = 0, y = -2
  for (const f of shape.faces) { const d = qrot(quat, f.n)[1]; if (d > y) { y = d; best = f.value } }
  return best
}

const quadMesh = () => ({ v: new Float32Array([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0]), i: new Uint16Array([0, 1, 2, 0, 2, 3]), quad: true })
const slabXZ = (w, d, y, uvs) => {
  const m = { p: [-w / 2, y, -d / 2, w / 2, y, -d / 2, w / 2, y, d / 2, -w / 2, y, d / 2], n: [0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0], uv: [0, 0, uvs[0], 0, uvs[0], uvs[1], 0, uvs[1]], i: [0, 2, 1, 0, 3, 2] }
  return m
}
const DIE_PALETTE = {
  d20: { body: paint(206, 0.5, 0.2), ink: paint(44, 0.55, 0.9) },
  damage: { body: paint(356, 0.62, 0.3), ink: paint(44, 0.45, 0.92) },
  heal: { body: paint(150, 0.5, 0.24), ink: paint(60, 0.4, 0.92) },
  crit: { body: paint(44, 0.9, 0.5), ink: paint(28, 0.7, 0.1) },
  fumble: { body: paint(0, 0.7, 0.24), ink: paint(30, 0.4, 0.9) }
}

export function createStage(ctx, host, canvas, hud, hooks = {}) {
  const gl = canvas.getContext('webgl', { antialias: true, alpha: false, powerPreference: 'high-performance' })
  if (!gl) throw new Error('WebGL is unavailable')
  const aniso = gl.getExtension('EXT_texture_filter_anisotropic')
  const offs = []
  let disposed = false, visible = true, raf = 0, running = false

  // ---------------------------------------------------------------- GL plumbing
  const compile = (type, src) => {
    const s = gl.createShader(type)
    gl.shaderSource(s, src)
    gl.compileShader(s)
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || 'shader failed')
    return s
  }
  const program = (vs, fs) => {
    const p = gl.createProgram()
    gl.attachShader(p, compile(gl.VERTEX_SHADER, vs))
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, GLSL_HI + fs))
    ;['aPos', 'aNor', 'aCol', 'aFlag', 'aUv'].forEach((n, i) => gl.bindAttribLocation(p, i, n))
    gl.linkProgram(p)
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || 'link failed')
    const cache = {}
    const at = n => (n in cache ? cache[n] : (cache[n] = gl.getUniformLocation(p, n)))
    return {
      p, use: () => gl.useProgram(p),
      f: (n, v) => gl.uniform1f(at(n), v), v2: (n, v) => gl.uniform2f(at(n), v[0], v[1]), v3: (n, v) => gl.uniform3f(at(n), v[0], v[1], v[2]),
      v4: (n, v) => gl.uniform4f(at(n), v[0], v[1], v[2], v[3]), m: (n, v) => gl.uniformMatrix4fv(at(n), false, v), i: (n, v) => gl.uniform1i(at(n), v)
    }
  }
  const surf = program(SURF_VS, SURF_FS), depthP = program(DEPTH_VS, DEPTH_FS), decal = program(DECAL_VS, DECAL_FS), beamP = program(SURF_VS, BEAM_FS), vigP = program(VIG_VS, VIG_FS)
  const upload = mesh => {
    const vbo = gl.createBuffer(), ibo = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo); gl.bufferData(gl.ARRAY_BUFFER, mesh.v, gl.STATIC_DRAW)
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.i, gl.STATIC_DRAW)
    return { vbo, ibo, n: mesh.i.length, quad: Boolean(mesh.quad), radius: mesh.radius, top: mesh.top }
  }
  const mergeMesh = (m, col, flag = 0) => upload(combine([{ m, col, flag }]))
  const bindGeo = g => {
    gl.bindBuffer(gl.ARRAY_BUFFER, g.vbo); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, g.ibo)
    if (g.quad) { gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 12, 0); gl.enableVertexAttribArray(0); for (let k = 1; k < 5; k++) gl.disableVertexAttribArray(k); return }
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 48, 0); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 48, 12)
    gl.vertexAttribPointer(2, 3, gl.FLOAT, false, 48, 24); gl.vertexAttribPointer(3, 1, gl.FLOAT, false, 48, 36); gl.vertexAttribPointer(4, 2, gl.FLOAT, false, 48, 40)
    for (let k = 0; k < 5; k++) gl.enableVertexAttribArray(k)
  }
  const texture = (canvasEl, { repeat = false, mip = true } = {}) => {
    const t = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, t)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvasEl)
    if (mip) gl.generateMipmap(gl.TEXTURE_2D)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mip ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, repeat ? gl.REPEAT : gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, repeat ? gl.REPEAT : gl.CLAMP_TO_EDGE)
    if (aniso) gl.texParameterf(gl.TEXTURE_2D, aniso.TEXTURE_MAX_ANISOTROPY_EXT, Math.min(8, gl.getParameter(aniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT)))
    return t
  }

  // Shadow map: depth packed into RGBA8 so it needs no extension.
  let shadowOK = true
  const shadowTex = gl.createTexture(), shadowFbo = gl.createFramebuffer(), shadowDepth = gl.createRenderbuffer()
  gl.bindTexture(gl.TEXTURE_2D, shadowTex)
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, SHADOW_SIZE, SHADOW_SIZE, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.NEAREST], [gl.TEXTURE_MAG_FILTER, gl.NEAREST], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v)
  gl.bindRenderbuffer(gl.RENDERBUFFER, shadowDepth)
  gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, SHADOW_SIZE, SHADOW_SIZE)
  gl.bindFramebuffer(gl.FRAMEBUFFER, shadowFbo)
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, shadowTex, 0)
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, shadowDepth)
  if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) shadowOK = false
  gl.bindFramebuffer(gl.FRAMEBUFFER, null)

  // ---------------------------------------------------------------- theme tokens, read live so a theme switch reskins the scene
  const probe = document.createElement('span')
  probe.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden'
  host.appendChild(probe)
  const pxc = document.createElement('canvas')
  pxc.width = pxc.height = 1
  const px = pxc.getContext('2d', { willReadFrequently: true })
  let theme = {}
  const readTheme = () => {
    for (const name of TONE_VARS) {
      probe.style.color = ''
      probe.style.color = `var(--ui-${name}, ${css(TONE_FALLBACK[name])})`
      px.clearRect(0, 0, 1, 1)
      px.fillStyle = css(TONE_FALLBACK[name])
      px.fillStyle = getComputedStyle(probe).color
      px.fillRect(0, 0, 1, 1)
      const d = px.getImageData(0, 0, 1, 1).data
      theme[name] = [d[0] / 255, d[1] / 255, d[2] / 255]
    }
  }
  readTheme()

  // ---------------------------------------------------------------- static scene
  const woodTex = texture(woodSheet(1024), { repeat: true })
  const feltTex = texture(boardSheet(2048))
  const trayTex = texture(feltSheet(512, paint(352, 0.55, 0.2), 0.5), { repeat: true })
  const white = texture(feltSheet(4, [1, 1, 1], 0), {})
  const dark = shade(ART.ink, 1)
  const statics = []
  const place = (g, t, o = {}) => statics.push({ g, model: m4trs(t, qaxis([0, 1, 0], o.yaw || 0), [1, 1, 1]), tex: o.tex || woodTex, mode: o.mode ?? 1, spec: o.spec ?? 0.1, shine: o.shine ?? 14, cast: o.cast !== false })
  const woodBox = (w, h, d, t, col = [1, 1, 1], uvs = 0.3, o = {}) => place(mergeMesh(box(w, h, d, uvs), col), t, o)
  place(mergeMesh(box(64, 0.6, 46, 0.075), [0.92, 0.92, 0.94]), [0, -0.3, 0], { cast: false, spec: 0.16, shine: 22 })
  // board slab, felt, and rim
  woodBox(14.1, BOARD_Y, 12.1, [0, BOARD_Y / 2, 0], [0.5, 0.48, 0.5])
  place(mergeMesh(slabXZ(BOARD_W, BOARD_D, BOARD_Y + 0.003, [1, 1]), [1, 1, 1]), [0, 0, 0], { tex: feltTex, spec: 0.03, shine: 6, cast: false })
  const rimH = BOARD_Y + 0.1
  woodBox(0.55, rimH, 12.1, [-6.775, rimH / 2, 0], [0.62, 0.6, 0.62], 0.4)
  woodBox(0.55, rimH, 12.1, [6.775, rimH / 2, 0], [0.62, 0.6, 0.62], 0.4)
  woodBox(13, rimH, 0.55, [0, rimH / 2, -5.775], [0.62, 0.6, 0.62], 0.4)
  woodBox(13, rimH, 0.55, [0, rimH / 2, 5.775], [0.62, 0.6, 0.62], 0.4)
  for (const [sx, sz] of [[-6.775, -5.775], [6.775, -5.775], [-6.775, 5.775], [6.775, 5.775]]) place(mergeMesh(xf(sphere(0.2, 12, 7), [0, 0, 0], [0, 0, 0], [1, 0.7, 1]), ART.gold, F_METAL), [sx, rimH, sz], { mode: 0, spec: 0.3 })
  // dice tray: a lined well with a raised wooden lip
  woodBox(TRAY.w + 1.1, TRAY.floor - 0.02, TRAY.d + 1.1, [TRAY.x, (TRAY.floor - 0.02) / 2, TRAY.z], [0.5, 0.48, 0.5])
  place(mergeMesh(slabXZ(TRAY.w, TRAY.d, TRAY.floor, [TRAY.w * 0.5, TRAY.d * 0.5]), [1, 1, 1]), [TRAY.x, 0, TRAY.z], { tex: trayTex, spec: 0.05, shine: 8, cast: false })
  const lip = 0.5
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) place(mergeMesh(xf(sphere(0.2, 12, 7), [0, 0, 0], [0, 0, 0], [1, 0.7, 1]), ART.gold, F_METAL), [TRAY.x + sx * (TRAY.w / 2 + 0.275), lip, TRAY.z + sz * (TRAY.d / 2 + 0.275)], { mode: 0, spec: 0.3 })
  woodBox(0.55, lip, TRAY.d + 1.1, [TRAY.x - TRAY.w / 2 - 0.275, lip / 2, TRAY.z], [0.66, 0.62, 0.64], 0.4)
  woodBox(0.55, lip, TRAY.d + 1.1, [TRAY.x + TRAY.w / 2 + 0.275, lip / 2, TRAY.z], [0.66, 0.62, 0.64], 0.4)
  woodBox(TRAY.w, lip, 0.55, [TRAY.x, lip / 2, TRAY.z - TRAY.d / 2 - 0.275], [0.66, 0.62, 0.64], 0.4)
  woodBox(TRAY.w, lip, 0.55, [TRAY.x, lip / 2, TRAY.z + TRAY.d / 2 + 0.275], [0.66, 0.62, 0.64], 0.4)
  // props: coin stacks, a tankard and a closed book
  const coinRnd = seeded(3)
  for (const [cx, cz, n] of [[-9.1, 4.6, 7], [-8.5, 5.3, 4], [-9.7, 5.4, 3]]) for (let k = 0; k < n; k++) place(mergeMesh(cyl(0.24, 0.24, 0.05, 14), ART.gold, F_METAL), [cx + (coinRnd() - 0.5) * 0.05, k * 0.052, cz + (coinRnd() - 0.5) * 0.05], { mode: 0, spec: 0.3, yaw: coinRnd() * 3 })
  place(mergeMesh(lathe([[0, 0], [0.4, 0], [0.45, 0.06], [0.42, 0.7], [0.36, 0.74], [0.32, 0.7], [0.3, 0.12], [0, 0.12]], 18), shade(ART.steel, 0.85), F_METAL), [9.6, 0, 6.2], { mode: 0, spec: 0.3 })
  place(mergeMesh(xf(torus(0.2, 0.045, 14, 6), [0.5, 0.38, 0], [Math.PI / 2, 0, 0]), shade(ART.steel, 0.85), F_METAL), [9.6, 0, 6.2], { mode: 0, spec: 0.3 })
  place(mergeMesh(box(1.5, 0.22, 1.05, 0.3), shade(ART.leather, 1.2)), [-9.6, 0.11, 0.8], { yaw: 0.35, spec: 0.2 })
  place(mergeMesh(xf(box(1.4, 0.16, 0.96, 0.3), [0.04, 0, 0.02]), ART.cloth), [-9.6, 0.12, 0.8], { yaw: 0.35, mode: 0 })
  // candles
  const waxG = upload(combine([
    { m: lathe([[0, 0], [0.34, 0], [0.34, 0.06], [0.24, 0.1], [0, 0.1]], 16), col: shade(ART.gold, 0.75), flag: F_METAL },
    { m: cyl(0.2, 0.19, 1.15, 14), col: ART.cloth, flag: 0, },
    { m: cone(0.17, 0.05, 12), col: ART.cloth },
    { m: cyl(0.012, 0.012, 0.16, 5), col: ART.ink }
  ].map((p, k) => ({ ...p, m: xf(p.m, k === 1 ? [0, 0.1, 0] : k === 2 ? [0, 1.25, 0] : k === 3 ? [0, 1.25, 0] : [0, 0, 0]) }))))
  for (const [cx, cz] of CANDLES) statics.push({ g: waxG, model: m4trs([cx, 0, cz], [0, 0, 0, 1], [1, 1, 1]), tex: white, mode: 0, spec: 0.3, shine: 30, cast: true, flameAt: [cx, 1.5, cz] })

  const quad = upload(quadMesh())
  const gemG = mergeMesh(xf(lathe([[0, -0.5], [0.5, 0], [0, 0.5]], 4), [0, 0, 0]), [1, 1, 1], 5)
  const ballG = mergeMesh(sphere(0.5, 10, 6), [1, 1, 1], 5)
  const ringG = mergeMesh(torus(0.5, 0.06, 20, 6), [1, 1, 1], 5)
  const beamG = mergeMesh(xf(lathe([[0.62, 0], [0.16, 1]], 18), [0, 0, 0], [0, 0, 0], [1, 4.4, 1]), [1, 1, 1])
  const miniGeo = new Map()
  const geoFor = look => {
    if (!miniGeo.has(look)) { const m = buildMini(look); let top = 0; for (let k = 1; k < m.v.length; k += 12) top = Math.max(top, m.v[k]); miniGeo.set(look, upload({ ...m, top })) }
    return miniGeo.get(look)
  }
  const dieGeo = new Map()
  const dieFor = sides => {
    if (!dieGeo.has(sides)) {
      const shape = diceShape(sides)
      dieGeo.set(sides, { shape, g: mergeMesh(dieMesh(shape), [1, 1, 1], F_LACQUER), tex: texture(atlasSheet(shape, 1024)) })
    }
    return dieGeo.get(sides)
  }

  // ---------------------------------------------------------------- scene state
  const S = {
    time: 0, minis: new Map(), chat: undefined, seq: -1, queue: [], actions: [], dice: [], nextAt: 0, floats: [], shots: [], active: '', combat: false,
    caption: null, hover: '', tray: null, frames: 0, fpsAt: 0, fps: 0, cpu: 0
  }
  const cam = { az: HOME.az, el: HOME.el, zoom: HOME.zoom, tx: 0, tz: 2.2, cur: { az: HOME.az, el: HOME.el, zoom: HOME.zoom, tx: 0, tz: 2.2 }, lastInput: -100, aspect: 1.6 }
  let vp = m4look([0, 5, 5], [0, 0, 0]), view = vp, eyePos = [0, 5, 5], size = [2, 2], dpr = 1

  const makeEl = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e }
  const plate = makeEl('div', 'tk-np')
  const plateName = makeEl('b'), plateMeta = makeEl('span')
  plate.append(plateName, plateMeta)
  plate.style.display = 'none'
  const tip = makeEl('div', 'tk-np tk-np-tip')
  const tipName = makeEl('b'), tipMeta = makeEl('span')
  tip.append(tipName, tipMeta)
  tip.style.display = 'none'
  const cap = makeEl('div', 'tk-cap')
  cap.style.display = 'none'
  const capWho = makeEl('span', 'tk-cap-who'), capVal = makeEl('b', 'tk-cap-val'), capTag = makeEl('span', 'tk-cap-tag')
  cap.append(capWho, capVal, capTag)
  const hint = makeEl('div', 'tk-hint', 'Drag to orbit. Scroll to zoom. Double-click to reset.')
  hud.append(plate, tip, cap, hint)

  const worldOf = (c, staged) => (c.pos ? cellWorld(c.pos[0], c.pos[1]) : stagedWorld(staged.indexOf(c)))
  const toneOf = name => theme[name] || TONE_FALLBACK[name] || [1, 1, 1]
  const hpColor = frac => toneOf(hpTone(frac))

  function reset() {
    S.minis.clear(); S.queue.length = 0; S.actions.length = 0; S.dice.length = 0; S.floats.forEach(f => f.el.remove()); S.floats.length = 0; S.shots.length = 0
    S.seq = -1; S.caption = null; cap.style.display = 'none'
  }

  function spawnFloat(m, text, kind) {
    const el = makeEl('div', `tk-dmg tk-dmg-${kind}`, text)
    hud.appendChild(el)
    S.floats.push({ el, key: m.key, born: S.time, drift: (Math.random() - 0.5) * 24 })
  }
  function flash(m, tint, strength = 0.9) { m.flash = { tint, t: S.time, strength } }
  function commit(m) {
    const next = m.truth, was = m.v
    const delta = next.hp - was.hp
    if (delta < 0) { flash(m, toneOf('red')); spawnFloat(m, String(delta), 'hurt'); m.shake = S.time }
    else if (delta > 0) { flash(m, toneOf('green'), 0.7); spawnFloat(m, `+${delta}`, 'heal') }
    m.v = { ...next }
    m.fallGoal = next.state === 'dead' ? 1 : next.state === 'down' || next.state === 'stable' ? 0.9 : 0
    m.pending = 0
  }
  function ensureMini(c, cell, animate) {
    let m = S.minis.get(c.key)
    if (m) return m
    const geo = geoFor(c.look)
    m = {
      key: c.key, look: c.look, geo, pos: cell.slice(), from: cell.slice(), to: cell.slice(), moveAt: -9, moveDur: 0, yaw: Math.PI, yawGoal: Math.PI,
      fall: 0, fallGoal: 0, v: { ...snap(c) }, truth: snap(c), pending: 0, flash: null, lunge: null, shake: -9, phase: Math.random() * 6.28,
      born: animate ? S.time : -9, hp: 0, tone: c.kind === 'pc' ? c.toneName : 'red', c
    }
    m.fallGoal = m.fall = m.v.state === 'dead' ? 1 : m.v.state === 'down' || m.v.state === 'stable' ? 0.9 : 0
    S.minis.set(c.key, m)
    return m
  }
  const snap = c => ({ hp: c.hp, max: c.max, temp: c.temp, state: c.state, saves: { ...c.saves }, frac: c.frac })

  function startRoll(roll, resting) {
    const dice = diceOf(roll)
    if (!dice.length) return 0
    S.dice.forEach(d => { d.leave = S.time })
    const rnd = seeded(roll.seq + 7)
    const spots = trayLayout(dice.length, 0.6, rnd)
    const crit = dice.some(d => d.sides === 20 && d.value === 20 && !d.dropped)
    const fumble = !crit && dice.some(d => d.sides === 20 && d.value === 1 && !d.dropped)
    const palette = crit ? DIE_PALETTE.crit : fumble ? DIE_PALETTE.fumble : roll.kind === 'damage' ? DIE_PALETTE.damage : /heal/i.test(roll.kind + roll.label) ? DIE_PALETTE.heal : DIE_PALETTE.d20
    let last = 0
    const made = dice.map((d, k) => {
      const { shape, g, tex } = dieFor(d.sides)
      const target = [TRAY.x + spots[k][0], TRAY.z + spots[k][1]]
      const plan = throwPlan(shape, d.value, target, rnd, TRAY.floor + shape.inr)
      const t0 = S.time + k * 0.14 - (resting ? 10 : 0)
      last = Math.max(last, k * 0.14 + plan.dur)
      return { shape, g, tex, plan, t0, dropped: d.dropped, palette, value: d.value, sides: d.sides, leave: 0, crit: crit && d.sides === 20 && d.value === 20 && !d.dropped, fumble: fumble && d.sides === 20 && d.value === 1 && !d.dropped }
    })
    S.dice.push(...made)
    S.tray = { roll, made, landAt: S.time + last, crit, fumble, shown: false }
    if (resting) land(S.tray)
    return last
  }
  function land(tray) {
    if (tray.shown) return
    tray.shown = true
    const r = tray.roll
    capWho.textContent = [r.who, r.label || r.kind].filter(Boolean).join(' · ')
    capVal.textContent = r.total != null ? String(r.total) : tray.made.map(d => d.value).join(' + ')
    capTag.textContent = tray.crit ? 'natural 20' : tray.fumble ? 'natural 1' : r.outcome || ''
    cap.dataset.tone = tray.crit ? 'crit' : tray.fumble ? 'fumble' : r.outcome || ''
    cap.style.display = ''
    const top = tray.made.map(d => ({ sides: d.sides, value: d.value, shows: topValue(d.shape, d.pose ? d.pose.quat : throwPose(d.plan, d.plan.dur + 1).quat) }))
    hud.dataset.landed = JSON.stringify({ seq: r.seq, who: r.who, dice: top })
  }

  function lunge(att, tgt) {
    const dx = tgt.pos[0] - att.pos[0], dz = tgt.pos[1] - att.pos[1], l = Math.hypot(dx, dz) || 1
    att.lunge = { at: S.time, dir: [dx / l, dz / l], dur: 0.46, reach: Math.min(0.7, l * 0.45) }
    att.yawGoal = Math.atan2(dx, dz)
  }
  function shoot(att, tgt, tint) {
    S.shots.push({ from: att.pos.slice(), to: tgt.pos.slice(), at: S.time, dur: 0.42 + Math.hypot(att.pos[0] - tgt.pos[0], att.pos[1] - tgt.pos[1]) * 0.03, tint, key: tgt.key })
    att.yawGoal = Math.atan2(tgt.pos[0] - att.pos[0], tgt.pos[1] - att.pos[1])
  }
  function impact(key) { const m = S.minis.get(key); if (m && m.pending) commit(m) }

  function runEvent(ev) {
    const r = ev.roll
    const t = startRoll(r, false)
    const at = S.time + t + 0.25
    const att = S.minis.get(r.actor), tgt = S.minis.get(r.target)
    S.nextAt = at + (r.kind === 'attack' ? 1.05 : 0.9)
    S.actions.push({ at: S.time + t, fn: () => { if (S.tray) land(S.tray) } })
    if (r.kind === 'attack' && att && tgt && att !== tgt) {
      S.actions.push({
        at, fn: () => {
          const far = Math.hypot(att.pos[0] - tgt.pos[0], att.pos[1] - tgt.pos[1]) > 1.9
          far ? shoot(att, tgt, toneOf(r.outcome === 'miss' ? 'text-secondary' : 'yellow')) : lunge(att, tgt)
          const followed = S.queue.some(e => e.roll.kind === 'damage' && e.roll.target === r.target)
          if (r.outcome === 'miss') S.actions.push({ at: S.time + (far ? 0.5 : 0.3), fn: () => { spawnFloat(tgt, 'miss', 'miss'); tgt.dodge = S.time } })
          else if (!followed) S.actions.push({ at: S.time + (far ? 0.5 : 0.3), fn: () => impact(r.target) })
        }
      })
    } else if (r.kind === 'damage' && tgt) S.actions.push({ at: at - 0.05, fn: () => impact(r.target) })
  }

  /** Feed a fresh campaign snapshot. Animation is driven by what changed since the last one. */
  function update(model, campaign) {
    if (disposed) return
    const chat = campaign?.chat ?? ''
    if (chat !== S.chat) { reset(); S.chat = chat; S.fresh = true }
    const first = S.fresh
    S.fresh = false
    const staged = model.creatures.filter(c => !c.pos)
    const seen = new Set()
    const newRolls = first ? [] : model.rolls.filter(r => r.seq > S.seq)
    const rollTargets = new Set(newRolls.filter(r => r.target && (r.kind === 'attack' || r.kind === 'damage')).map(r => r.target))
    for (const c of model.creatures) {
      seen.add(c.key)
      const cell = worldOf(c, staged)
      const known = S.minis.has(c.key)
      const m = ensureMini(c, cell, !first)
      m.c = c
      if (known && (Math.abs(cell[0] - m.to[0]) > 1e-6 || Math.abs(cell[1] - m.to[1]) > 1e-6)) {
        m.from = m.pos.slice(); m.to = cell; m.moveAt = S.time; m.moveDur = 0.28 + Math.hypot(cell[0] - m.pos[0], cell[1] - m.pos[1]) * 0.16
        m.yawGoal = Math.atan2(cell[0] - m.pos[0], cell[1] - m.pos[1])
      }
      const next = snap(c)
      const changed = next.hp !== m.truth.hp || next.state !== m.truth.state
      m.truth = next
      m.v.max = next.max; m.v.temp = next.temp; m.v.saves = next.saves
      if (changed) {
        if (first || !known || !(rollTargets.has(c.key) || S.queue.some(e => e.roll.target === c.key))) commit(m)
        else m.pending = S.time
      }
      m.dead = c.state === 'dead'
    }
    for (const key of [...S.minis.keys()]) if (!seen.has(key)) S.minis.delete(key)
    S.active = model.activeKey
    S.combat = model.combat
    if (S.seq < 0 && !newRolls.length && model.rolls.length) {
      const last = model.rolls[model.rolls.length - 1]
      S.seq = last.seq
      startRoll(last, true)
    } else if (newRolls.length) {
      S.seq = Math.max(S.seq, ...newRolls.map(r => r.seq))
      for (const r of newRolls) S.queue.push({ roll: r })
      while (S.queue.length > 6) S.queue.shift()
    }
    // face the nearest foe when idle
    for (const m of S.minis.values()) {
      if (m.lunge || m.moveAt + m.moveDur > S.time) continue
      let best = null, bd = 1e9
      for (const o of S.minis.values()) if (o !== m && o.c.kind !== m.c.kind && !o.dead) { const d = Math.hypot(o.to[0] - m.to[0], o.to[1] - m.to[1]); if (d < bd) { bd = d; best = o } }
      if (best && m.c.pos) m.yawGoal = Math.atan2(best.to[0] - m.to[0], best.to[1] - m.to[1])
    }
  }

  // ---------------------------------------------------------------- per-frame animation
  function stepMini(m, dt) {
    const t = S.time
    const u = m.moveDur ? clamp((t - m.moveAt) / m.moveDur, 0, 1) : 1
    const moving = u < 1
    const e = ease(u)
    m.pos[0] = mix(m.from[0], m.to[0], e); m.pos[1] = mix(m.from[1], m.to[1], e)
    let dy = 0
    if (moving) dy = Math.abs(Math.sin(u * Math.PI * Math.max(1, Math.hypot(m.to[0] - m.from[0], m.to[1] - m.from[1])))) * 0.13
    if (t - m.born < 0.7) { const a = (t - m.born) / 0.7; dy += (1 - a) * (1 - a) * 3.2 * Math.abs(Math.cos(a * Math.PI * 1.5)) }
    let dx = 0, dz = 0
    if (m.lunge) {
      const a = (t - m.lunge.at) / m.lunge.dur
      if (a >= 1) m.lunge = null
      else { const s = Math.sin(Math.PI * Math.pow(a, 0.7)) * m.lunge.reach; dx = m.lunge.dir[0] * s; dz = m.lunge.dir[1] * s; dy += Math.sin(Math.PI * a) * 0.08 }
    }
    if (m.dodge && t - m.dodge < 0.4) { const a = (t - m.dodge) / 0.4; dx += Math.sin(a * Math.PI) * 0.22 }
    if (t - m.shake < 0.45) { const a = 1 - (t - m.shake) / 0.45; dx += Math.sin((t - m.shake) * 70) * 0.07 * a }
    let d = m.yawGoal - m.yaw
    d = Math.atan2(Math.sin(d), Math.cos(d))
    m.yaw += d * (1 - Math.exp(-dt * 9))
    m.fall += (m.fallGoal - m.fall) * (1 - Math.exp(-dt * (m.fallGoal > m.fall ? 7 : 5)))
    const f = m.fall
    const radius = m.geo.radius * MINI_SCALE_UP
    const breathe = 1 + Math.sin(t * 1.7 + m.phase) * 0.012 * (1 - f)
    const q = qmul(qaxis([0, 1, 0], m.yaw), qaxis([1, 0, 0], -f * 1.42))
    const lift = Math.sin(f * 1.42) * radius * 0.92
    const y = BOARD_Y + dy + lift
    m.model = m4trs([m.pos[0] + dx, y, m.pos[1] + dz], q, [MINI_SCALE_UP, MINI_SCALE_UP * breathe, MINI_SCALE_UP])
    m.eyeAt = [m.pos[0] + dx, BOARD_Y + (m.geo.top || 1.2) * MINI_SCALE_UP * (1 - f * 0.8) + dy + 0.12, m.pos[1] + dz]
    m.ground = [m.pos[0] + dx, m.pos[1] + dz]
    if (m.pending && t - m.pending > 6) commit(m)
    m.vf = m.vf == null ? m.v.frac : m.vf + (m.v.frac - m.vf) * (1 - Math.exp(-dt * 6))
  }

  function stepWorld(dt) {
    S.time += dt
    for (let k = S.actions.length - 1; k >= 0; k--) if (S.time >= S.actions[k].at) { const a = S.actions.splice(k, 1)[0]; a.fn() }
    if (S.queue.length && S.time >= S.nextAt) runEvent(S.queue.shift())
    for (const m of S.minis.values()) stepMini(m, dt)
    S.dice = S.dice.filter(d => !d.leave || S.time - d.leave < 0.35)
    S.shots = S.shots.filter(s => S.time - s.at < s.dur)
    for (let k = S.floats.length - 1; k >= 0; k--) if (S.time - S.floats[k].born > 1.7) { S.floats[k].el.remove(); S.floats.splice(k, 1) }
  }

  // ---------------------------------------------------------------- camera
  function stepCamera(dt) {
    const idle = S.time - cam.lastInput
    const sway = clamp((idle - 5) / 2.5, 0, 1)
    const k = 1 - Math.exp(-dt * 7)
    for (const key of ['az', 'el', 'zoom']) cam.cur[key] += (cam[key] - cam.cur[key]) * k
    cam.cur.tx += (cam.tx - cam.cur.tx) * k; cam.cur.tz += (cam.tz - cam.cur.tz) * k
    const az = cam.cur.az + Math.sin(S.time * 0.16) * 0.52 * sway
    const el = clamp(cam.cur.el + Math.sin(S.time * 0.1 + 1) * 0.07 * sway, 0.3, 1.45)
    const dist = fitDistance(cam.aspect) * cam.cur.zoom * (1 + Math.sin(S.time * 0.07) * 0.04 * sway)
    const target = [cam.cur.tx, 0.4, cam.cur.tz]
    eyePos = orbitEye(target, az, el, dist)
    view = m4look(eyePos, target)
    vp = m4mul(m4persp(FOV, cam.aspect, 0.5, 140), view)
    hint.style.opacity = S.time - cam.lastInput > 8 && cam.lastInput > -50 ? '0' : S.time < 14 ? '1' : '0'
  }

  // ---------------------------------------------------------------- drawing
  const lightEye = vadd([0, 0, 1.6], vmul(SUN, 24))
  const lvp = m4mul(m4ortho(-12.5, 12.5, -12.5, 12.5, 1, 52), m4look(lightEye, [0, 0, 1.6]))
  let pl0 = [0, 0, 0, 0], pl1 = [0, 0, 0, 0]
  const D0 = { team: [1, 1, 1], glow: [0, 0, 0], flash: [0, 0, 0, 0], desat: 0, tex: null, mode: 0, spec: 0.1, shine: 14, body: [1, 1, 1], ink: [0, 0, 0] }
  const drawSurf = (g, model, o = D0) => {
    const d = o === D0 ? o : { ...D0, ...o }
    surf.m('uModel', model); surf.v3('uTeam', d.team); surf.v3('uGlow', d.glow); surf.v4('uFlash', d.flash); surf.f('uDesat', d.desat)
    surf.f('uTexMode', d.tex ? d.mode : 0); surf.f('uSpec', d.spec); surf.f('uShine', d.shine); surf.v3('uBody', d.body); surf.v3('uInk', d.ink)
    if (d.tex) { gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, d.tex) }
    bindGeo(g)
    gl.drawElements(gl.TRIANGLES, g.n, gl.UNSIGNED_SHORT, 0)
  }
  const drawDepth = (g, model) => { depthP.m('uModel', model); bindGeo(g); gl.drawElements(gl.TRIANGLES, g.n, gl.UNSIGNED_SHORT, 0) }
  const drawDecal = (model, mode, col, a, frac = 1) => {
    decal.m('uModel', model); decal.f('uMode', mode); decal.v4('uCol', [col[0], col[1], col[2], 1]); decal.f('uA', a); decal.f('uFrac', frac)
    bindGeo(quad); gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0)
  }
  const flat = (x, y, z, r) => m4trs([x, y, z], qaxis([1, 0, 0], -Math.PI / 2), [r, r, r])
  const bb = (p, r) => {
    const right = [view[0], view[4], view[8]], up = [view[1], view[5], view[9]], fwd = [view[2], view[6], view[10]]
    return [right[0] * r, right[1] * r, right[2] * r, 0, up[0] * r, up[1] * r, up[2] * r, 0, fwd[0], fwd[1], fwd[2], 0, p[0], p[1], p[2], 1]
  }
  const dieModel = d => {
    const t = S.time - d.t0
    if (t < 0) return null
    const pose = throwPose(d.plan, t)
    const out = d.leave ? clamp(1 - (S.time - d.leave) / 0.3, 0, 1) : 1
    if (out <= 0) return null
    d.pose = pose
    return m4trs(pose.pos, pose.quat, [out, out, out])
  }
  const flameSize = k => 0.55 + 0.1 * Math.sin(S.time * 13 + k * 2) + 0.05 * Math.sin(S.time * 31 + k)

  function render() {
    const w = canvas.width, h = canvas.height
    const bg = toneOf('bg-editor')
    const candle = CANDLES.map((c, k) => [c[0], 1.55, c[1], 3.2 * (0.85 + 0.08 * Math.sin(S.time * 11 + k * 3) + 0.06 * Math.sin(S.time * 23 + k))])
    pl0 = candle[0]; pl1 = candle[1]
    const castDraw = () => {
      for (const s of statics) if (s.cast) drawDepth(s.g, s.model)
      for (const m of S.minis.values()) drawDepth(m.geo, m.model)
      for (const d of S.dice) { const mm = dieModel(d); if (mm) drawDepth(d.g, mm) }
    }
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true); gl.disable(gl.BLEND)
    if (shadowOK) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, shadowFbo)
      gl.viewport(0, 0, SHADOW_SIZE, SHADOW_SIZE)
      gl.clearColor(1, 1, 1, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT)
      depthP.use(); depthP.m('uLVP', lvp)
      gl.enable(gl.CULL_FACE); gl.cullFace(gl.FRONT)
      castDraw()
      gl.disable(gl.CULL_FACE)
      gl.bindFramebuffer(gl.FRAMEBUFFER, null)
    }
    gl.viewport(0, 0, w, h)
    gl.clearColor(bg[0], bg[1], bg[2], 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT)
    surf.use()
    surf.m('uVP', vp); surf.m('uLVP', lvp); surf.v3('uCam', eyePos); surf.v3('uSun', SUN)
    surf.v3('uSunCol', [1.85, 1.38, 0.9]); surf.v3('uSky', [0.26, 0.32, 0.5]); surf.v3('uGround', [0.16, 0.11, 0.08]); surf.v3('uFog', bg); surf.f('uFogD', 0.021)
    surf.v4('uPL0', pl0); surf.v4('uPL1', pl1); surf.v3('uPLCol', [1.0, 0.62, 0.3]); surf.v2('uTexel', [1 / SHADOW_SIZE, 1 / SHADOW_SIZE]); surf.f('uShadowOn', shadowOK ? 1 : 0)
    surf.i('uTex', 0); surf.i('uShadow', 1)
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, shadowTex); gl.activeTexture(gl.TEXTURE0)
    for (const s of statics) drawSurf(s.g, s.model, { tex: s.tex, mode: s.mode, spec: s.spec, shine: s.shine })
    for (const m of S.minis.values()) {
      const flashK = m.flash ? clamp(1 - (S.time - m.flash.t) / 0.7, 0, 1) : 0
      const col = m.tone ? toneOf(m.tone) : toneOf('red')
      const dead = m.v.state === 'dead'
      drawSurf(m.geo, m.model, { team: col, flash: flashK > 0 ? [m.flash.tint[0], m.flash.tint[1], m.flash.tint[2], flashK * m.flash.strength] : D0.flash, desat: dead ? 0.92 : m.v.state === 'down' ? 0.45 : 0, glow: m.key === S.active ? [0.03, 0.03, 0.05] : D0.glow })
      // condition gems, concentration halo, death-save pips
      const c = m.c, top = BOARD_Y + (m.geo.top || 1.2) * MINI_SCALE_UP + 0.3
      c.conditions.slice(0, 4).forEach((cond, k, all) => {
        const a = S.time * 1.1 + (k / all.length) * TAU
        drawSurf(gemG, m4trs([m.ground[0] + Math.cos(a) * 0.36, top + Math.sin(S.time * 2 + k) * 0.03, m.ground[1] + Math.sin(a) * 0.36], qaxis([0, 1, 0], S.time * 2), [0.15, 0.2, 0.15]), { team: toneOf(CONDITION_TONE[cond] || 'yellow') })
      })
      if (c.concentrating) drawSurf(ringG, m4trs([m.ground[0], top + 0.14, m.ground[1]], qaxis([1, 0, 0], 0.2), [0.5, 0.5, 0.5]), { team: toneOf('yellow') })
      if (m.v.state === 'down' || m.v.state === 'stable') {
        for (let k = 0; k < 6; k++) {
          const good = k < 3, on = (good ? m.v.saves.s : m.v.saves.f) > (k % 3)
          drawSurf(ballG, m4trs([m.ground[0] + (k - 2.5) * 0.17, BOARD_Y + 0.95, m.ground[1] + 0.05], [0, 0, 0, 1], [0.1, 0.1, 0.1]), { team: on ? toneOf(good ? 'green' : 'red') : mixRgb(toneOf('bg-elevated'), toneOf('text-secondary'), 0.25) })
        }
      }
    }
    for (const d of S.dice) {
      const mm = dieModel(d)
      if (!mm) continue
      const landed = d.pose.done
      const pulse = 0.5 + 0.5 * Math.sin(S.time * 4)
      const glow = landed && d.crit ? [0.1 + 0.07 * pulse, 0.07 + 0.04 * pulse, 0.005] : landed && d.fumble ? [0.1 + 0.05 * pulse, 0.003, 0.003] : D0.glow
      drawSurf(d.g, mm, { tex: d.tex, mode: 2, body: d.palette.body, ink: d.palette.ink, desat: d.dropped ? 0.7 : 0, glow, spec: 0.3, shine: 60 })
    }
    for (const s of S.shots) {
      const u = clamp((S.time - s.at) / s.dur, 0, 1)
      const x = mix(s.from[0], s.to[0], u), z = mix(s.from[1], s.to[1], u), y = BOARD_Y + 0.7 + Math.sin(u * Math.PI) * 0.5
      drawSurf(ballG, m4trs([x, y, z], [0, 0, 0, 1], [0.2, 0.2, 0.2]), { team: s.tint })
    }

    // ground decals: contact shadow, hit-point ring, active glow
    gl.depthMask(false); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
    decal.use(); decal.m('uVP', vp); decal.f('uTime', S.time)
    for (const m of S.minis.values()) {
      const r = m.geo.radius * MINI_SCALE_UP, fl = 1 - m.fall
      drawDecal(flat(m.ground[0], BOARD_Y + 0.005, m.ground[1], r * (1.45 + m.fall * 0.4)), 0, [0.02, 0.01, 0.01], 0.55 * (0.4 + 0.6 * fl))
      const dead = m.v.state === 'dead'
      drawDecal(flat(m.ground[0], BOARD_Y + 0.008, m.ground[1], r * 1.2), 1, dead ? mixRgb(toneOf('text-secondary'), toneOf('bg-elevated'), 0.5) : hpColor(m.v.frac), dead ? 0.55 : 0.95, clamp(m.vf ?? m.v.frac, 0, 1))
      if (m.v.temp > 0) drawDecal(flat(m.ground[0], BOARD_Y + 0.009, m.ground[1], r * 1.34), 1, toneOf('cyan'), 0.9, clamp(m.v.temp / m.v.max, 0, 1))
    }
    for (const d of S.dice) if (d.pose && d.pose.done && (d.crit || d.fumble)) {
      const pulse = 0.5 + 0.5 * Math.sin(S.time * 4)
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE)
      drawDecal(flat(d.plan.target[0], TRAY.floor + 0.01, d.plan.target[1], 1.8 + pulse * 0.2), 3, d.crit ? [1, 0.78, 0.2] : [1, 0.15, 0.1], 0.85)
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
    }
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE)
    const act = S.minis.get(S.active)
    if (act) {
      const a = toneOf('accent')
      drawDecal(flat(act.ground[0], BOARD_Y + 0.01, act.ground[1], act.geo.radius * MINI_SCALE_UP * 1.9), 2, a, 0.9)
      beamP.use(); beamP.m('uVP', vp); beamP.m('uModel', m4trs([act.ground[0], BOARD_Y, act.ground[1]], [0, 0, 0, 1], [(act.geo.radius * MINI_SCALE_UP) / 0.43, 1, (act.geo.radius * MINI_SCALE_UP) / 0.43])); beamP.m('uLVP', lvp)
      beamP.v3('uCam', eyePos); beamP.v3('uGlow', a); beamP.f('uA', 0.5 + 0.1 * Math.sin(S.time * 2.4))
      bindGeo(beamG); gl.drawElements(gl.TRIANGLES, beamG.n, gl.UNSIGNED_SHORT, 0)
      decal.use()
    }
    // candle flames and their glow
    statics.forEach((s, k) => {
      if (!s.flameAt) return
      const fs = flameSize(k)
      drawDecal(bb([s.flameAt[0], s.flameAt[1] + 0.35, s.flameAt[2]], 1.4), 3, [1, 0.55, 0.2], 0.2 + 0.06 * Math.sin(S.time * 9 + k))
      drawDecal(bb([s.flameAt[0], s.flameAt[1], s.flameAt[2]], fs * 0.5), 4, [1, 0.6, 0.2], 1)
    })
    gl.disable(gl.BLEND)
    // vignette toward the pane background
    vigP.use(); vigP.v3('uCol', bg); vigP.f('uA', 0.78); vigP.f('uAsp', cam.aspect)
    gl.disable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
    bindGeo(quad); gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0)
    gl.disable(gl.BLEND); gl.enable(gl.DEPTH_TEST); gl.depthMask(true)
  }

  // ---------------------------------------------------------------- overlays: name plates and damage numbers ride the projection
  function overlay() {
    const [w, h] = size
    const at = (m, lift = 0) => { const p = project([m.eyeAt[0], m.eyeAt[1] + lift, m.eyeAt[2]], vp, w, h); return p }
    const act = S.minis.get(S.active)
    if (act) {
      const p = at(act, 0.22)
      plateName.textContent = clip(act.c.name, 22)
      plateMeta.textContent = `${act.v.hp}/${act.v.max} HP`
      plate.style.display = p.ok ? '' : 'none'
      plate.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px) translate(-50%, -100%)`
    } else plate.style.display = 'none'
    const hov = S.hover && S.hover !== S.active ? S.minis.get(S.hover) : null
    if (hov) {
      const p = at(hov, 0.18)
      tipName.textContent = clip(hov.c.name, 24)
      const st = hov.v.state === 'ok' ? '' : ` · ${hov.v.state}`
      tipMeta.textContent = `${hov.v.hp}/${hov.v.max} HP${hov.c.ac != null ? ` · AC ${hov.c.ac}` : ''}${st}${hov.c.conditions.length ? ` · ${hov.c.conditions.slice(0, 3).join(', ')}` : ''}`
      tip.style.display = p.ok ? '' : 'none'
      tip.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px) translate(-50%, -100%)`
    } else tip.style.display = 'none'
    for (const f of S.floats) {
      const m = S.minis.get(f.key)
      if (!m) { f.el.style.display = 'none'; continue }
      const age = (S.time - f.born) / 1.6
      const p = at(m, 0.25)
      f.el.style.opacity = String(clamp(Math.min(age * 8, 1.6 - age * 1.0), 0, 1))
      f.el.style.transform = `translate(${(p.x + f.drift * age).toFixed(1)}px, ${(p.y - 18 - age * 64).toFixed(1)}px) translate(-50%, -100%) scale(${(1 + Math.max(0, 0.35 - age * 1.4)).toFixed(2)})`
    }
  }

  // ---------------------------------------------------------------- input: drag to orbit, wheel to zoom, double-click to reset
  let drag = null
  const poke = () => { cam.lastInput = S.time }
  const rect = () => canvas.getBoundingClientRect()
  offs.push(ctx.addEventListener(canvas, 'pointerdown', e => {
    if (e.button !== 0 && e.button !== 1) return
    drag = { x: e.clientX, y: e.clientY, moved: 0, id: e.pointerId }
    canvas.setPointerCapture?.(e.pointerId)
    poke()
  }))
  offs.push(ctx.addEventListener(canvas, 'pointermove', e => {
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y
      drag.x = e.clientX; drag.y = e.clientY; drag.moved += Math.abs(dx) + Math.abs(dy)
      cam.az -= dx * 0.0062
      cam.el = clamp(cam.el + dy * 0.0048, 0.3, 1.45)
      poke()
      return
    }
    const r = rect(), mx = e.clientX - r.left, my = e.clientY - r.top
    let best = '', bd = 1e9
    for (const m of S.minis.values()) {
      if (!m.ground) continue
      const p = project([m.ground[0], BOARD_Y + 0.5, m.ground[1]], vp, r.width, r.height)
      const edge = project([m.ground[0] + 0.5, BOARD_Y + 0.5, m.ground[1]], vp, r.width, r.height)
      const rad = Math.max(16, Math.hypot(edge.x - p.x, edge.y - p.y) * 1.1)
      const d = Math.hypot(p.x - mx, p.y - my)
      if (p.ok && d < rad && d < bd) { bd = d; best = m.key }
    }
    S.hover = best
    canvas.style.cursor = best ? 'pointer' : 'grab'
  }))
  const end = () => { if (drag) { canvas.releasePointerCapture?.(drag.id); drag = null } }
  offs.push(ctx.addEventListener(canvas, 'pointerup', end), ctx.addEventListener(canvas, 'pointercancel', end))
  offs.push(ctx.addEventListener(canvas, 'pointerleave', () => { S.hover = '' }))
  offs.push(ctx.addEventListener(canvas, 'wheel', e => { e.preventDefault(); cam.zoom = clamp(cam.zoom * Math.exp(e.deltaY * 0.0012), 0.42, 1.6); poke() }, { passive: false }))
  offs.push(ctx.addEventListener(canvas, 'dblclick', () => { Object.assign(cam, { az: HOME.az, el: HOME.el, zoom: HOME.zoom, tx: 0, tz: 2.2 }); poke() }))
  offs.push(ctx.addEventListener(canvas, 'webglcontextlost', e => { e.preventDefault(); stop(); hooks.onFail?.(new Error('WebGL context lost')) }))

  // ---------------------------------------------------------------- loop, sizing, visibility
  let last = 0, themeTick = 0
  function frame(now) {
    raf = 0
    if (disposed || !running) return
    const dt = clamp((now - last) / 1000, 0, 0.05)
    last = now
    const began = performance.now()
    try {
      stepWorld(dt)
      stepCamera(dt)
      render()
      overlay()
      if (++themeTick % 150 === 0) readTheme()
    } catch (error) { stop(); hooks.onFail?.(error); return }
    S.frames++
    S.cpu += performance.now() - began
    if (now - S.fpsAt >= 1000) {
      S.fps = Math.round((S.frames * 1000) / (now - S.fpsAt))
      canvas.dataset.fps = String(S.fps)
      canvas.dataset.cpuMs = (S.cpu / S.frames).toFixed(2)
      canvas.dataset.minis = String(S.minis.size)
      S.frames = 0; S.cpu = 0; S.fpsAt = now
    }
    raf = window.requestAnimationFrame(frame)
  }
  function start() { if (running || disposed || !visible || document.hidden) return; running = true; last = performance.now(); S.fpsAt = last; S.frames = 0; raf = window.requestAnimationFrame(frame) }
  function stop() { running = false; if (raf) window.cancelAnimationFrame(raf); raf = 0 }
  const fit = () => {
    const r = host.getBoundingClientRect()
    dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = Math.max(2, Math.round(r.width * dpr)), h = Math.max(2, Math.round(r.height * dpr))
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h }
    size = [r.width, r.height]
    cam.aspect = w / h
  }
  fit()
  const ro = new ResizeObserver(() => { fit(); if (!running) start() })
  ro.observe(host)
  const io = new IntersectionObserver(entries => { visible = entries.some(e => e.isIntersecting); visible ? start() : stop() })
  io.observe(host)
  offs.push(ctx.addEventListener(document, 'visibilitychange', () => (document.hidden ? stop() : start())))
  start()

  function dispose() {
    if (disposed) return
    disposed = true
    stop(); ro.disconnect(); io.disconnect()
    offs.forEach(off => off())
    S.floats.forEach(f => f.el.remove())
    hud.replaceChildren()
    gl.getExtension('WEBGL_lose_context')?.loseContext()
  }
  return { update, dispose, state: S, camera: cam }
}

const mixRgb = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]

function Rail({ id }) {
  return h('defs', null,
    h('filter', { id: `${id}-felt`, x: 0, y: 0, width: '100%', height: '100%' },
      h('feTurbulence', { type: 'fractalNoise', baseFrequency: 0.85, numOctaves: 2, seed: 7 }),
      h('feColorMatrix', { values: '0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.07 0' })),
    h('radialGradient', { id: `${id}-light`, cx: '50%', cy: '42%', r: '75%' },
      h('stop', { offset: '0%', stopColor: 'var(--ui-base)', stopOpacity: 0.07 }),
      h('stop', { offset: '100%', stopColor: 'var(--ui-base)', stopOpacity: 0 })))
}

function Pips({ saves }) {
  const pip = (i, good) => h('circle', {
    key: (good ? 's' : 'f') + i, cx: (good ? -22 : 6) + i * 8.5, cy: 29, r: 3,
    fill: (good ? saves.s : saves.f) > i ? tone(good ? 'green' : 'red') : 'none', stroke: tone(good ? 'green' : 'red'), strokeWidth: 1.2
  })
  return h('g', null, [0, 1, 2].map(i => pip(i, true)), [0, 1, 2].map(i => pip(i, false)))
}

function Token({ c, x, y, active }) {
  const owner = c.tint
  const ringColor = tone(hpTone(c.frac))
  const body = c.kind === 'pc'
    ? h('circle', { r: 17.5, fill: `color-mix(in srgb, ${owner} 38%, var(--ui-bg-elevated))`, stroke: owner, strokeWidth: 2.2 })
    : h('rect', { x: -16, y: -16, width: 32, height: 32, rx: 6, fill: `color-mix(in srgb, ${owner} 34%, var(--ui-bg-elevated))`, stroke: owner, strokeWidth: 2.2 })
  const badges = c.conditions.slice(0, 3)
  const label = `${c.name}: ${c.hp}/${c.max} HP${c.temp ? ` (+${c.temp} temporary)` : ''}${c.conditions.length ? `, ${c.conditions.join(', ')}` : ''}${c.state === 'dead' ? ', dead' : c.state === 'down' || c.state === 'stable' ? `, ${c.state}` : ''}`
  return h('g', { className: 'tk-token', 'data-state': c.state, style: { transform: `translate(${x}px, ${y}px)` } },
    h('title', null, label),
    active && h('circle', { className: 'tk-glow', r: 26, fill: 'none', stroke: tone('accent'), strokeWidth: 3 }),
    h('circle', { r: 22, fill: 'none', stroke: 'var(--ui-stroke-secondary)', strokeWidth: 4 }),
    h('circle', { className: 'tk-ring', r: 22, fill: 'none', stroke: ringColor, strokeWidth: 4, strokeLinecap: 'round', pathLength: 100, strokeDasharray: `${c.frac * 100} 100`, transform: 'rotate(-90)', opacity: c.frac > 0 ? 1 : 0 }),
    c.temp > 0 && h('circle', { r: 26.5, fill: 'none', stroke: tone('cyan'), strokeWidth: 2, strokeLinecap: 'round', pathLength: 100, strokeDasharray: `${Math.min(100, (c.temp / c.max) * 100)} 100`, transform: 'rotate(-90)' }),
    h('g', { className: 'tk-body' }, body, h('text', { className: 'tk-ini', textAnchor: 'middle', dominantBaseline: 'central' }, initials(c.name))),
    c.state === 'dead' && h('g', { stroke: tone('red'), strokeWidth: 3.2, strokeLinecap: 'round' }, h('path', { d: 'M-13 -13L13 13' }), h('path', { d: 'M13 -13L-13 13' })),
    (c.state === 'down' || c.state === 'stable') && h(Pips, { saves: c.saves }),
    c.concentrating && h('g', { transform: 'translate(-19,-19)' }, h('circle', { r: 6.5, fill: tone('yellow'), stroke: 'var(--ui-bg-editor)', strokeWidth: 1.5 }), h('text', { textAnchor: 'middle', dominantBaseline: 'central', fontSize: 8, fontWeight: 800, fill: 'var(--ui-bg-editor)' }, 'C')),
    badges.map((cond, i) => h('g', { key: cond, transform: `translate(17, ${-20 + i * 11.5})` },
      h('rect', { x: -8, y: -5.5, width: 16, height: 11, rx: 3, fill: tone(CONDITION_TONE[cond] || 'yellow'), stroke: 'var(--ui-bg-editor)', strokeWidth: 1 }),
      h('text', { textAnchor: 'middle', dominantBaseline: 'central', fontSize: 7, fontWeight: 800, fill: 'var(--ui-bg-editor)' }, CONDITION_CODE[cond] || cond.slice(0, 2).toUpperCase()))),
    c.conditions.length > 3 && h('text', { x: 17, y: 16, textAnchor: 'middle', fontSize: 8, fontWeight: 700, fill: 'var(--ui-text-secondary)' }, `+${c.conditions.length - 3}`),
    active && h('g', { transform: 'translate(0,-33)' },
      h('rect', { x: -(Math.min(c.name.length, 16) * 3.4 + 8), y: -9, width: Math.min(c.name.length, 16) * 6.8 + 16, height: 15, rx: 7.5, fill: tone('accent') }),
      h('text', { textAnchor: 'middle', dominantBaseline: 'central', y: -1.5, fontSize: 9.5, fontWeight: 700, fill: 'var(--ui-bg-editor)' }, clip(c.name, 16))))
}

function Board({ creatures, activeKey, floats, uid }) {
  const width = COLS * CELL + PAD * 2
  const staged = creatures.filter(c => !c.pos)
  const height = ROWS * CELL + PAD * 2 + (staged.length ? STAGE : 0)
  const cols = Array.from({ length: COLS }, (_, i) => String.fromCharCode(65 + i))
  const at = c => {
    if (c.pos) return [PAD + c.pos[0] * CELL + CELL / 2, PAD + c.pos[1] * CELL + CELL / 2]
    const i = staged.indexOf(c)
    return [PAD + CELL / 2 + i * (CELL + 4), ROWS * CELL + PAD * 2 + STAGE / 2 - 8]
  }
  const grid = []
  for (let i = 0; i <= COLS; i++) grid.push(h('line', { key: `v${i}`, x1: PAD + i * CELL, y1: PAD, x2: PAD + i * CELL, y2: PAD + ROWS * CELL }))
  for (let i = 0; i <= ROWS; i++) grid.push(h('line', { key: `h${i}`, x1: PAD, y1: PAD + i * CELL, x2: PAD + COLS * CELL, y2: PAD + i * CELL }))
  const placed = creatures.filter(c => c.pos).length
  return h('svg', { className: 'tk-board', viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': `Battle grid, ${COLS} by ${ROWS} squares of ${FEET_PER_SQUARE} feet, ${placed} creatures placed` },
    h(Rail, { id: uid }),
    h('rect', { width, height, fill: 'var(--tk-felt)' }),
    h('rect', { width, height, filter: `url(#${uid}-felt)` }),
    h('rect', { width, height, fill: `url(#${uid}-light)` }),
    h('rect', { x: PAD, y: PAD, width: COLS * CELL, height: ROWS * CELL, fill: 'var(--tk-felt-deep)', opacity: 0.35 }),
    h('g', { stroke: 'var(--tk-line)', strokeWidth: 1 }, grid),
    h('rect', { x: PAD, y: PAD, width: COLS * CELL, height: ROWS * CELL, fill: 'none', stroke: 'var(--ui-stroke-primary)', strokeWidth: 1.5 }),
    h('g', { fill: 'var(--ui-text-tertiary)', fontSize: 10, textAnchor: 'middle', dominantBaseline: 'central', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' },
      cols.map((l, i) => h('text', { key: l, x: PAD + i * CELL + CELL / 2, y: PAD / 2 }, l)),
      Array.from({ length: ROWS }, (_, i) => h('text', { key: i, x: PAD / 2, y: PAD + i * CELL + CELL / 2 }, i + 1))),
    h('text', { x: PAD + COLS * CELL, y: PAD + ROWS * CELL + PAD / 2 + 1, textAnchor: 'end', dominantBaseline: 'central', fontSize: 9.5, letterSpacing: '.12em', fill: 'var(--ui-text-tertiary)' }, `1 SQUARE = ${FEET_PER_SQUARE} FT`),
    staged.length > 0 && h('text', { x: PAD, y: ROWS * CELL + PAD * 2 + 10, fontSize: 9.5, letterSpacing: '.16em', fill: 'var(--ui-text-tertiary)' }, 'OFF MAP'),
    creatures.map(c => { const [x, y] = at(c); return h(Token, { key: c.key, c, x, y, active: c.key === activeKey }) }),
    floats.map(f => { const c = creatures.find(k => k.key === f.key); if (!c) return null; const [x, y] = at(c); return h('text', { key: f.id, className: 'tk-float', x, y: y - 22, textAnchor: 'middle', fontSize: 20, fontWeight: 800, fill: tone(f.delta < 0 ? 'red' : 'green'), stroke: 'var(--ui-bg-editor)', strokeWidth: 3.5, paintOrder: 'stroke' }, f.delta > 0 ? `+${f.delta}` : `${f.delta}`) }))
}

function Glyph({ c }) {
  const owner = c.tint
  return h('svg', { width: 28, height: 28, viewBox: '-15 -15 30 30', 'aria-hidden': true, style: c.state === 'dead' ? { filter: 'grayscale(1)' } : undefined },
    c.kind === 'pc'
      ? h('circle', { r: 12.5, fill: `color-mix(in srgb, ${owner} 38%, var(--ui-bg-elevated))`, stroke: owner, strokeWidth: 2 })
      : h('rect', { x: -11.5, y: -11.5, width: 23, height: 23, rx: 4.5, fill: `color-mix(in srgb, ${owner} 34%, var(--ui-bg-elevated))`, stroke: owner, strokeWidth: 2 }),
    h('text', { textAnchor: 'middle', dominantBaseline: 'central', fontSize: 9.5, fontWeight: 700, fill: 'var(--ui-text-primary)' }, initials(c.name)))
}

function CreatureRow({ c, index, active, ordered }) {
  const color = tone(hpTone(c.frac))
  const status = c.state === 'dead' ? 'dead' : c.state === 'stable' ? 'stable' : c.state === 'down' ? `down ${c.saves.s}/${c.saves.f}` : ''
  return h('li', { className: 'tk-row', 'data-active': active, 'data-state': c.state, 'aria-current': active ? 'step' : undefined },
    h('span', { className: 'tk-ord tk-num' }, ordered ? index + 1 : ''),
    h(Glyph, { c }),
    h('div', { style: { minWidth: 0 } },
      h('div', { className: 'tk-line' },
        h('span', { className: 'tk-name' }, c.name),
        h('span', { className: 'tk-meta' },
          c.ac != null && h('span', { className: 'tk-num' }, `AC ${c.ac}`),
          status && h('span', { style: { color: tone(c.state === 'dead' ? 'red' : 'yellow'), fontWeight: 650 } }, status),
          c.conditions.slice(0, 3).map(cond => h('span', { key: cond, className: 'tk-cond', style: { color: tone(CONDITION_TONE[cond] || 'yellow'), background: soft(tone(CONDITION_TONE[cond] || 'yellow'), 16) } }, cond)))),
      h('div', { className: 'tk-bar', role: 'progressbar', 'aria-label': `${c.name} hit points`, 'aria-valuemin': 0, 'aria-valuemax': c.max, 'aria-valuenow': c.hp },
        h('i', { style: { width: `${c.frac * 100}%`, background: color } }),
        c.temp > 0 && h('i', { style: { width: `${Math.min(100 - c.frac * 100, (c.temp / c.max) * 100)}%`, background: tone('cyan') } }))),
    h('div', { className: 'tk-hp tk-num' }, c.hp, h('small', null, `/${c.max}`), c.temp > 0 && h('small', { style: { color: tone('cyan') } }, ` +${c.temp}`)))
}

function Die({ sides, value, dropped, fresh, delay, size }) {
  const crit = sides === 20 && value === 20 && !dropped
  const fumble = sides === 20 && value === 1 && !dropped
  const edge = crit ? tone('yellow') : fumble ? tone('red') : 'var(--ui-stroke-primary)'
  const fill = crit ? `color-mix(in srgb, ${tone('yellow')} 42%, var(--ui-bg-elevated))` : fumble ? `color-mix(in srgb, ${tone('red')} 38%, var(--ui-bg-elevated))` : 'var(--ui-bg-elevated)'
  const shape = DIE_SHAPES[sides]
  const face = !sides || !shape ? h('circle', { cx: 15, cy: 15, r: 12.5, fill, stroke: edge, strokeWidth: 1.6 })
    : shape.rect ? h('rect', { x: 4, y: 4, width: 22, height: 22, rx: 5, fill, stroke: edge, strokeWidth: 1.6 })
    : h('polygon', { points: shape.poly, fill, stroke: edge, strokeWidth: 1.6, strokeLinejoin: 'round' })
  return h('svg', { className: 'tk-die', 'data-fresh': fresh, width: size, height: size, viewBox: '0 0 30 30', role: 'img', 'aria-label': `d${sides || '?'} showed ${value}${crit ? ', critical' : fumble ? ', natural 1' : ''}${dropped ? ', dropped' : ''}`, style: { opacity: dropped ? 0.35 : 1, animationDelay: `${delay}ms`, filter: crit ? `drop-shadow(0 0 5px ${tone('yellow')})` : fumble ? `drop-shadow(0 0 4px ${tone('red')})` : undefined } },
    face,
    h('text', { x: 15, y: sides === 4 ? 20 : 15.5, textAnchor: 'middle', dominantBaseline: 'central', fontSize: value > 99 ? 8 : value > 9 ? 11.5 : 13, fontWeight: 750, fill: 'var(--ui-text-primary)', style: { fontVariantNumeric: 'tabular-nums' } }, value),
    dropped && h('path', { d: 'M4 26L26 4', stroke: tone('red'), strokeWidth: 2, strokeLinecap: 'round' }))
}

function RollRow({ r, fresh, hero }) {
  const kept = r.dice.filter(d => !d.dropped)
  const nat = r.dice.length && r.dice[0].sides === 20 ? kept[0]?.value : null
  const toneName = nat === 20 ? 'crit' : nat === 1 ? 'fumble' : ''
  const outcomeColor = { crit: 'yellow', hit: 'green', success: 'green', miss: 'red', fail: 'red' }[r.outcome]
  const size = hero ? 40 : 24
  const shown = hero ? r.dice : r.dice.slice(0, 6)
  const faces = h('div', { className: 'tk-faces' },
    shown.map((d, i) => h(Die, { key: i, sides: d.sides, value: d.value, dropped: d.dropped, fresh, delay: i * 90, size })),
    r.dice.length > shown.length && h('span', { className: 'tk-mod tk-num' }, `+${r.dice.length - shown.length}`),
    r.modifier !== 0 && h('span', { className: 'tk-mod tk-num' }, r.modifier > 0 ? `+${r.modifier}` : `${r.modifier}`),
    !r.dice.length && h('span', { className: 'tk-mod' }, r.formula))
  const who = h('div', { className: 'tk-who' }, r.who && h('b', null, r.who), r.who && (r.label || r.kind) ? ' \u00b7 ' : '', r.label || r.kind,
    r.damageType && h('span', { className: 'tk-tag', style: { color: 'var(--ui-text-secondary)', background: 'var(--ui-bg-tertiary)' } }, r.damageType),
    r.outcome && h('span', { className: 'tk-tag', style: { color: tone(outcomeColor), background: soft(tone(outcomeColor), 16) } }, r.outcome))
  const total = r.total != null && h('div', { className: 'tk-total tk-num', 'data-tone': toneName, 'aria-label': `total ${r.total}` }, r.total)
  return h('li', { className: 'tk-roll', 'data-fresh': fresh, 'data-hero': hero },
    hero ? h('div', { style: { minWidth: 0 } }, who, faces) : faces,
    hero ? total : who,
    hero ? null : total)
}

function logTone(kind) {
  const k = String(kind).toLowerCase()
  if (/dam|attack|hit|death|dead|kill/.test(k)) return 'red'
  if (/heal|rest|stable/.test(k)) return 'green'
  if (/turn|round|init|combat/.test(k)) return 'accent'
  if (/cast|spell|magic/.test(k)) return 'purple'
  if (/cond/.test(k)) return 'orange'
  return 'cyan'
}

function useCampaign(ctx) {
  const [chat, setChat] = useState(() => ctx.storage.get('chat', null))
  const [data, setData] = useState({ status: 'loading', campaign: null, campaigns: [], error: '' })
  const sig = useRef('')
  const known = useRef([])
  const pick = value => { ctx.storage.set('chat', value); setChat(value) }
  useEffect(() => {
    let alive = true
    let busy = false
    let tick = 0
    let loaded = false
    const load = async () => {
      if (busy || (loaded && document.hidden)) return
      busy = true
      try {
        const query = chat ? `?chat=${encodeURIComponent(chat)}` : ''
        const body = await ctx.rest('/campaign' + query)
        const campaigns = tick++ % LIST_EVERY === 0 ? (await ctx.rest('/campaigns')).campaigns : null
        if (campaigns) known.current = campaigns
        const next = JSON.stringify(body.campaign)
        if (!alive) return
        loaded = true
        if (next === sig.current && !campaigns) { setData(d => (d.status === 'live' ? d : { ...d, status: 'live', error: '' })); return }
        sig.current = next
        setData(d => ({ status: 'live', campaign: body.campaign, campaigns: campaigns || d.campaigns, error: '' }))
      } catch (error) {
        if (!alive) return
        if (chat && known.current.length && !known.current.some(c => c.chat === chat)) { pick(null); return }
        setData(d => ({ ...d, status: d.campaign ? 'stale' : 'error', error: clip(error?.message || 'Campaign data is unavailable', 160) }))
      } finally {
        busy = false
      }
    }
    load()
    const stop = ctx.setInterval(load, POLL_MS)
    const hooks = [ctx.onEvent('tool.complete', load), ctx.onEvent('plugin.tablekeeper.changed', load)]
    return () => { alive = false; stop(); hooks.forEach(off => off()) }
  }, [chat])
  return { ...data, chat, pick }
}

function useStage(ctx, chat, creatures, rolls) {
  const [floats, setFloats] = useState([])
  const [fresh, setFresh] = useState(() => new Set())
  const memory = useRef(null)
  useEffect(() => {
    const hp = new Map(creatures.map(c => [c.key, c.hp]))
    const top = rolls.reduce((m, r) => Math.max(m, r.seq), -1)
    const before = memory.current
    memory.current = { chat, hp, top }
    if (!before || before.chat !== chat) return
    const added = []
    for (const c of creatures) {
      const was = before.hp.get(c.key)
      if (was !== undefined && was !== c.hp) added.push({ id: `${c.key}:${c.hp}:${Date.now()}`, key: c.key, delta: c.hp - was })
    }
    if (added.length) {
      setFloats(f => [...f, ...added])
      ctx.setTimeout(() => setFloats(f => f.filter(x => !added.includes(x))), 1700)
    }
    const news = rolls.filter(r => r.seq > before.top).map(r => r.seq)
    if (news.length) {
      setFresh(new Set(news))
      ctx.setTimeout(() => setFresh(new Set()), 4500)
    }
  }, [creatures, rolls])
  return { floats, fresh }
}

export function buildModel(campaign) {
  const owners = []
  const creatures = list(campaign?.creatures).map((raw, i) => {
    const c = creatureView(raw, i)
    if (c.kind === 'pc' && !owners.includes(c.owner)) owners.push(c.owner)
    const toneName = c.kind === 'pc' ? OWNER_TONES[owners.indexOf(c.owner) % OWNER_TONES.length] : 'red'
    return { ...c, toneName, tint: tone(toneName) }
  })
  const rolls = list(campaign?.rolls).map(rollView)
  const byKey = new Map(creatures.map(c => [c.key, c]))
  const order = list(campaign?.initiative).map(id => byKey.get(clip(id, 64))).filter(Boolean)
  const combat = Boolean(campaign?.in_combat) && order.length > 0
  const activeKey = combat ? clip(campaign?.active, 64) : ''
  return { creatures, rolls, combat, activeKey, active: byKey.get(activeKey), shown: combat ? order : creatures }
}

let glProbe
/** True when this renderer can create a WebGL context. Probed once; the SVG board stays available either way. */
export function canWebGL() {
  if (glProbe === undefined) {
    try {
      const gl = document.createElement('canvas').getContext('webgl')
      glProbe = Boolean(gl)
      gl?.getExtension('WEBGL_lose_context')?.loseContext()
    } catch {
      glProbe = false
    }
  }
  return glProbe
}

const STAGES = new Set()

function Stage3D({ ctx, campaign, onFail }) {
  const box = useRef(null)
  const canvas = useRef(null)
  const hud = useRef(null)
  const stage = useRef(null)
  useEffect(() => {
    let made
    try { made = createStage(ctx, box.current, canvas.current, hud.current, { onFail }) } catch (error) { onFail(error); return undefined }
    stage.current = made
    STAGES.add(made)
    return () => { STAGES.delete(made); made.dispose(); stage.current = null }
  }, [])
  useEffect(() => { stage.current?.update(buildModel(campaign), campaign) }, [campaign])
  return h('div', { className: 'tk-view3d', ref: box },
    h('canvas', { className: 'tk-gl', ref: canvas, role: 'img', 'aria-label': 'Three-dimensional tabletop. Drag to orbit, scroll to zoom, double-click to reset the camera.' }),
    h('div', { className: 'tk-hud', ref: hud }))
}

function Tabletop({ ctx }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const data = useCampaign(ctx)
  const [view, setViewState] = useState(() => (ctx.storage.get('view', '3d') === '2d' ? '2d' : '3d'))
  const [gl, setGl] = useState(() => canWebGL())
  const model = buildModel(data.campaign)
  const { floats, fresh } = useStage(ctx, data.campaign?.chat, model.creatures, model.rolls)
  const setView = next => { ctx.storage.set('view', next); setViewState(next) }
  return h(TabletopView, { data, model, floats, fresh, uid, ctx, view: gl ? view : '2d', setView, gl, onGlFail: () => setGl(false) })
}

export function TabletopView({ data, model, floats, fresh, uid, ctx, view = '2d', setView, gl = false, onGlFail }) {
  const { status, campaign, campaigns, error, chat, pick } = data
  const { creatures, rolls, combat, activeKey, active, shown } = model
  const recent = rolls.slice(-10).reverse()
  const log = list(campaign?.log).slice(-40).reverse()
  const ok = status === 'live'

  if (!campaign) {
    return h('div', { className: 'tk' }, h('style', null, STYLE),
      h('div', { className: 'tk-empty', role: status === 'error' ? 'alert' : 'status' },
        status === 'loading' ? h('div', null, 'Setting the table\u2026')
          : status === 'error' ? h('div', null, h('b', null, 'Campaign data is unavailable'), error)
          : h('div', null, h('b', null, 'The table is empty'), 'Start a campaign with /table new in any chat. Characters, monsters and every roll appear here as they happen.')))
  }

  return h('div', { className: 'tk' }, h('style', null, STYLE),
    h('div', { className: 'tk-wrap' },
      h('header', { className: 'tk-head' },
        h('div', { style: { minWidth: 0 } },
          h('div', { className: 'tk-scene' }, clip(campaign.scene, 120) || 'Untitled scene'),
          h('div', { className: 'tk-sub' },
            combat ? h('span', { className: 'tk-round tk-num' }, `Round ${num(campaign.round)}`) : h('span', { className: 'tk-chip' }, 'Exploration'),
            active && h('span', null, h('b', { style: { color: 'var(--ui-text-primary)' } }, active.name), "'s turn"))),
        h('div', { className: 'tk-sub', style: { margin: 0 } },
          campaigns.length > 1 && h('select', { className: 'tk-pick', 'aria-label': 'Campaign', value: chat || '', onChange: e => pick(e.target.value || null) },
            h('option', { value: '' }, 'Latest chat'),
            campaigns.map(c => h('option', { key: c.chat, value: c.chat }, clip(c.scene, 28) || clip(c.chat, 28)))),
          setView && h('div', { className: 'tk-seg', role: 'group', 'aria-label': 'Board view' },
            ['3d', '2d'].map(v => h('button', { key: v, type: 'button', className: 'tk-segb', 'aria-pressed': view === v, disabled: v === '3d' && !gl, title: v === '3d' && !gl ? 'WebGL is unavailable here' : `${v.toUpperCase()} board`, onClick: () => setView(v) }, v.toUpperCase()))),
          h('span', { className: 'tk-chip', title: ok ? 'Updating every second' : error }, h('i', { className: 'tk-live', 'data-ok': ok }), ok ? 'Live' : 'Reconnecting'))),
      h('div', { className: 'tk-layout', 'data-view': view === '3d' && ctx ? '3d' : '2d' },
        h('div', { className: view === '3d' && ctx ? 'tk-frame tk-frame-3d' : 'tk-frame' },
          view === '3d' && ctx ? h(Stage3D, { ctx, campaign, onFail: onGlFail }) : h(Board, { creatures, activeKey, floats, uid })),
        h('aside', { className: 'tk-side' },
          h('section', { className: 'tk-panel', 'aria-label': combat ? 'Initiative order' : 'Party and creatures' },
            h('div', { className: 'tk-panel-h' }, h('span', null, combat ? 'Initiative' : 'At the table'), h('span', { className: 'tk-num' }, shown.length)),
            shown.length ? h('ol', { className: 'tk-list' }, shown.map((c, i) => h(CreatureRow, { key: c.key, c, index: i, active: c.key === activeKey, ordered: combat })))
              : h('div', { style: { padding: '4px 12px 14px', color: 'var(--ui-text-tertiary)' } }, 'No characters yet. Claim one with tk_claim_character.')),
          h('section', { className: 'tk-panel tk-tray', 'aria-label': 'Dice tray' },
            h('div', { className: 'tk-panel-h' }, h('span', null, 'Dice tray'), h('span', { className: 'tk-num' }, `last ${recent.length}`)),
            recent.length ? h('ol', { className: 'tk-list' }, recent.map((r, i) => h(RollRow, { key: r.seq, r, fresh: fresh.has(r.seq), hero: i === 0 })))
              : h('div', { style: { padding: '4px 12px 14px', color: 'var(--ui-text-secondary)' } }, 'Nothing rolled yet. Every die is thrown by code, never by the model.'))),
        h('section', { className: 'tk-panel tk-logp', 'aria-label': 'Combat log' },
          h('div', { className: 'tk-panel-h' }, h('span', null, 'Log'), h('span', { className: 'tk-num' }, log.length)),
          log.length ? h('ol', { className: 'tk-log', role: 'log' }, log.map((e, i) => h('li', { key: num(e?.seq, -i) },
            h('i', { style: { background: tone(logTone(e?.kind)) } }), h('span', null, clip(e?.text, 220)), e?.ts ? h('time', null, relativeTime(num(e.ts) * 1000)) : null)))
            : h('div', { style: { padding: '4px 12px 14px', color: 'var(--ui-text-tertiary)' } }, 'The log fills as the story moves.')))))
}

export default {
  id: 'tablekeeper',
  name: 'Tablekeeper',
  register(ctx) {
    ctx.onDispose(() => { for (const stage of STAGES) stage.dispose(); STAGES.clear() })
    ctx.registerMany([
      { id: 'battle', area: PANES_AREA, title: 'Tabletop', data: { placement: 'right', width: '480px' }, render: () => h(Tabletop, { ctx }) },
      { id: 'page', area: ROUTES_AREA, data: { path: '/tabletop' }, render: () => h(Tabletop, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/tabletop', label: 'Tabletop', codicon: 'table' } }
    ])
  }
}
