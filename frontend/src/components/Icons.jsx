const base = {
  width: 16,
  height: 16,
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

export const IconUp = () => (
  <svg {...base}>
    <path d="M8 13V3M4 7l4-4 4 4" />
  </svg>
)

export const IconDown = () => (
  <svg {...base}>
    <path d="M8 3v10M4 9l4 4 4-4" />
  </svg>
)

export const IconLock = () => (
  <svg {...base}>
    <rect x="3" y="7" width="10" height="7" rx="1" />
    <path d="M5 7V5a3 3 0 0 1 6 0v2" />
  </svg>
)

export const IconUnlock = () => (
  <svg {...base}>
    <rect x="3" y="7" width="10" height="7" rx="1" />
    <path d="M5 7V5a3 3 0 0 1 5.8-1.1" />
  </svg>
)

export const IconClose = () => (
  <svg {...base}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </svg>
)

export const IconPlus = () => (
  <svg {...base}>
    <path d="M8 3v10M3 8h10" />
  </svg>
)

export const IconGrip = () => (
  <svg {...base} stroke="none" fill="currentColor">
    <circle cx="6" cy="4" r="1.1" />
    <circle cx="10" cy="4" r="1.1" />
    <circle cx="6" cy="8" r="1.1" />
    <circle cx="10" cy="8" r="1.1" />
    <circle cx="6" cy="12" r="1.1" />
    <circle cx="10" cy="12" r="1.1" />
  </svg>
)

export const IconWarning = () => (
  <svg {...base} width={14} height={14}>
    <path d="M8 2.2 14.6 13.5H1.4z" />
    <path d="M8 6.5v3.2M8 11.6v.1" />
  </svg>
)

export const IconExternal = () => (
  <svg {...base} width={14} height={14}>
    <path d="M9 3h4v4M13 3 7.5 8.5M11.5 9.5V13H3V4.5h3.5" />
  </svg>
)

export const IconRoute = () => (
  <svg {...base}>
    <circle cx="4" cy="4" r="1.8" />
    <circle cx="12" cy="12" r="1.8" />
    <path d="M5.8 4H10a2 2 0 0 1 0 4H6a2 2 0 0 0 0 4h4.2" />
  </svg>
)
