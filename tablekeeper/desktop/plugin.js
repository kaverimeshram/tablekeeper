import React from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

function BattlePane({ ctx }) {
  const [campaigns, setCampaigns] = React.useState([])
  const [error, setError] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  React.useEffect(() => {
    let live = true
    const load = () => ctx.rest('/campaigns').then(data => { if (live) { setCampaigns(data.campaigns || []); setError(''); setLoading(false) } }).catch(() => { if (live) { setError('Campaign data is unavailable'); setLoading(false) } })
    load()
    const timer = setInterval(load, 1500)
    return () => { live = false; clearInterval(timer) }
  }, [])
  const campaign = campaigns[0]
  if (error) return jsx('div', { className: 'p-3 text-sm', role: 'alert', children: error })
  if (loading) return jsx('div', { className: 'p-3 text-sm', role: 'status', children: 'Loading campaign…' })
  if (!campaign) return jsx('div', { className: 'p-3 text-sm', children: 'No campaign has been created in this Hermes profile. Start one with /table new.' })
  const units = [...Object.entries(campaign.characters || {}).map(([name, unit]) => ({ ...unit, name })), ...(campaign.monsters || [])]
  return jsxs('div', { className: 'flex flex-col gap-3 overflow-auto p-3 text-sm', children: [
    jsx('h2', { className: 'font-semibold', children: campaign.chat }),
    jsxs('div', { className: 'grid grid-cols-5 gap-1 font-mono', children: Array.from({ length: 25 }, (_, i) => jsx('div', { className: 'rounded border p-2 text-center', children: units[i] ? units[i].name[0].toUpperCase() : '·' }, i)) }),
    jsx('div', { children: `Round ${campaign.round || 0}` }),
    jsxs('ol', { className: 'flex flex-col gap-1', children: (campaign.initiative || []).map((entry, i) => jsx('li', { className: `rounded px-2 py-1 ${i === campaign.turn ? 'bg-blue-500/20 font-semibold' : ''}`, children: `${entry.name} · ${entry.initiative}` }, `${entry.name}-${i}`)) }),
    jsxs('div', { className: 'flex flex-col gap-2', children: units.map(unit => jsx('div', { children: jsxs('div', { children: [jsx('div', { className: 'tabular-nums', children: `${unit.name} · ${unit.hp}/${unit.max_hp} HP` }), jsx('progress', { className: 'w-full', value: unit.hp, max: unit.max_hp, 'aria-label': `${unit.name} hit points` })] }) }, unit.name)) }),
    jsx('h3', { className: 'font-semibold', children: 'Recent rolls' }),
    jsx('pre', { className: 'whitespace-pre-wrap', children: JSON.stringify((campaign.rolls || []).slice(-10).reverse(), null, 2) }),
  ] })
}

export default { id: 'tablekeeper', name: 'Tablekeeper', register(ctx) { ctx.register({ id: 'battle', area: 'panes', title: 'Battle', data: { placement: 'right', width: '320px' }, render: () => jsx(BattlePane, { ctx }) }) } }
