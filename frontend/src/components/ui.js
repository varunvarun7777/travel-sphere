// Shared class strings: flat panels, hairline borders, small corners.
export const btn =
  'inline-flex items-center justify-center gap-2 rounded-md border border-rule bg-panel px-3 py-2 text-sm font-semibold text-ink hover:border-ink disabled:cursor-not-allowed disabled:opacity-50'

export const btnPrimary =
  'inline-flex items-center justify-center gap-2 rounded-md border border-ink bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-black disabled:cursor-not-allowed disabled:opacity-50'

export const btnSignal =
  'inline-flex items-center justify-center gap-2 rounded-md border-2 border-ink bg-signal px-5 py-3 font-display wide text-base font-extrabold text-ink hover:bg-[#ffcd3a] disabled:cursor-not-allowed disabled:opacity-60'

export const iconBtn =
  'inline-grid size-8 place-items-center rounded-md border border-rule bg-panel text-ink hover:border-ink disabled:cursor-not-allowed disabled:opacity-40'

export const input =
  'w-full rounded-md border border-rule bg-white px-3 py-2 text-sm text-ink placeholder:text-steel/70 focus:border-ink'

export const fieldLabel = 'font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-steel'

export const panel = 'rounded-md border border-rule bg-panel'

export const signalTag =
  'inline-flex items-center gap-1.5 rounded-sm bg-signal px-1.5 py-0.5 text-xs font-semibold text-ink'

export const segment = (active) =>
  `rounded-md border px-3 py-2 text-left text-sm ${
    active ? 'border-ink bg-ink text-white' : 'border-rule bg-white text-ink hover:border-ink'
  }`
