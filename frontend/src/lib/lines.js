// Each day of a trip is a metro line with its own colour (matches the --color-line-* tokens).
export const LINE_COLORS = ['#DA291C', '#0072CE', '#00965E', '#7D3C98', '#D9661F', '#00A3AD', '#A05A2C']

export const lineColor = (index) => LINE_COLORS[index % LINE_COLORS.length]

export const INTERESTS = [
  'art',
  'history',
  'architecture',
  'nature',
  'food',
  'nightlife',
  'shopping',
  'views',
  'religion',
  'local',
]

export const PACES = [
  { id: 'relaxed', label: 'Relaxed', hours: 'about 10:00–18:00', hint: 'Fewer stops, long lunch' },
  { id: 'balanced', label: 'Balanced', hours: 'about 09:00–19:00', hint: 'A full but easy day' },
  { id: 'packed', label: 'Packed', hours: 'about 08:30–21:00', hint: 'As much as fits' },
]

export const MODES = [
  { id: 'auto', label: 'Auto', hint: 'Walk short hops, ride long ones' },
  { id: 'walk', label: 'Walk', hint: 'On foot all day' },
  { id: 'transit', label: 'Transit', hint: 'Metro, tram and bus' },
  { id: 'drive', label: 'Drive', hint: 'Taxi or car' },
]
