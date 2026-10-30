import { formatKm, formatMinutes, formatPrice } from '../lib/format'

export default function MetricsStrip({ metrics, symbol }) {
  const cells = [
    { label: 'Stops', value: metrics.stops },
    { label: 'Total distance', value: formatKm(metrics.km) },
    { label: 'On foot', value: formatKm(metrics.walk_km) },
    { label: 'Moving time', value: formatMinutes(metrics.travel_min) },
    { label: 'Entry fees', value: formatPrice(metrics.fees, symbol) },
  ]
  if (metrics.saved_pct > 0) {
    cells.push({ label: 'Than visiting in list order', value: `${metrics.saved_pct}% shorter`, highlight: true })
  }
  return (
    <dl className="mt-5 grid grid-cols-2 border-y border-rule sm:grid-cols-3 lg:flex lg:flex-wrap">
      {cells.map((c) => (
        <div key={c.label} className="border-rule px-0 py-3 pr-6 lg:border-r lg:px-5 lg:first:pl-0 lg:last:border-r-0">
          <dt className="font-mono text-[11px] uppercase tracking-[0.12em] text-steel">{c.label}</dt>
          <dd className={`font-mono text-lg font-semibold tabular-nums ${c.highlight ? 'inline-block bg-signal px-1' : ''}`}>{c.value}</dd>
        </div>
      ))}
    </dl>
  )
}
