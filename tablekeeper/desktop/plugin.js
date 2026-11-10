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
@keyframes tk-live{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--ui-green) 55%,transparent)}70%,100%{box-shadow:0 0 0 7px transparent}}
@keyframes tk-pulse{0%,100%{opacity:.95;transform:scale(1)}50%{opacity:.3;transform:scale(1.16)}}
@keyframes tk-float{0%{opacity:0;transform:translateY(0)}12%{opacity:1}100%{opacity:0;transform:translateY(-34px)}}
@keyframes tk-tumble{0%{opacity:0;transform:rotate(-260deg) scale(.2) translateY(-14px)}60%{opacity:1}100%{opacity:1;transform:rotate(0) scale(1) translateY(0)}}
@container (min-width:900px){.tk-wrap{height:100%}.tk-layout{flex:1;min-height:0;grid-template-columns:minmax(0,1.5fr) minmax(340px,1fr);grid-template-rows:auto minmax(0,1fr)}.tk-frame{grid-area:1/1}.tk-logp{grid-area:2/1;max-height:100%}.tk-logp .tk-log{max-height:none;flex:1}.tk-side{grid-area:1/2/3/2;max-height:100%;overflow:auto;padding-right:2px}}
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
    return { ...c, tint: c.kind === 'pc' ? tone(OWNER_TONES[owners.indexOf(c.owner) % OWNER_TONES.length]) : tone('red') }
  })
  const rolls = list(campaign?.rolls).map(rollView)
  const byKey = new Map(creatures.map(c => [c.key, c]))
  const order = list(campaign?.initiative).map(id => byKey.get(clip(id, 64))).filter(Boolean)
  const combat = Boolean(campaign?.in_combat) && order.length > 0
  const activeKey = combat ? clip(campaign?.active, 64) : ''
  return { creatures, rolls, combat, activeKey, active: byKey.get(activeKey), shown: combat ? order : creatures }
}

function Tabletop({ ctx }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const data = useCampaign(ctx)
  const model = buildModel(data.campaign)
  const { floats, fresh } = useStage(ctx, data.campaign?.chat, model.creatures, model.rolls)
  return h(TabletopView, { data, model, floats, fresh, uid })
}

export function TabletopView({ data, model, floats, fresh, uid }) {
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
          h('span', { className: 'tk-chip', title: ok ? 'Updating every second' : error }, h('i', { className: 'tk-live', 'data-ok': ok }), ok ? 'Live' : 'Reconnecting'))),
      h('div', { className: 'tk-layout' },
        h('div', { className: 'tk-frame' }, h(Board, { creatures, activeKey, floats, uid })),
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
    ctx.registerMany([
      { id: 'battle', area: PANES_AREA, title: 'Tabletop', data: { placement: 'right', width: '480px' }, render: () => h(Tabletop, { ctx }) },
      { id: 'page', area: ROUTES_AREA, data: { path: '/tabletop' }, render: () => h(Tabletop, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/tabletop', label: 'Tabletop', codicon: 'table' } }
    ])
  }
}
