import { useEffect, useState } from 'react'

/** Seconds left until `deadlineMs` (a Date.now()-style timestamp), updated every second. */
export function useCountdown(deadlineMs: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [deadlineMs])
  return Math.max(0, Math.ceil((deadlineMs - now) / 1000))
}
