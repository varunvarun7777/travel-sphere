import { useCallback, useEffect, useRef, useState } from 'react'

export function useToast() {
  const [toast, setToast] = useState(null)
  const timer = useRef()

  const notify = useCallback((message, tone = 'info') => {
    clearTimeout(timer.current)
    setToast({ message, tone, key: Date.now() })
    timer.current = setTimeout(() => setToast(null), tone === 'error' ? 7000 : 4500)
  }, [])

  useEffect(() => () => clearTimeout(timer.current), [])
  return [toast, notify]
}

export function Toast({ toast }) {
  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-[1000] flex justify-center px-4 print:hidden">
      {toast && (
        <div
          key={toast.key}
          role={toast.tone === 'error' ? 'alert' : 'status'}
          className={`pointer-events-auto max-w-lg rounded-md border-l-[6px] bg-ink px-4 py-3 text-sm text-white ${
            toast.tone === 'error' ? 'border-[#DA291C]' : 'border-signal'
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}
