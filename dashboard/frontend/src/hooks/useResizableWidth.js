import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react'

function readStoredWidth(storageKey, minWidth) {
  try {
    const v = parseInt(localStorage.getItem(storageKey), 10)
    return Number.isFinite(v) && v >= minWidth ? v : null
  } catch {
    return null
  }
}

export default function useResizableWidth({ storageKey, minWidth = 160, maxFraction = 0.45, defaultWidthPx }) {
  const initialWidth = readStoredWidth(storageKey, minWidth) ?? defaultWidthPx
  const [currentWidth, setCurrentWidth] = useState(initialWidth)
  const [dragging, setDragging] = useState(false)
  const containerRef = useRef(null)
  const widthRef = useRef(currentWidth)

  useEffect(() => {
    widthRef.current = currentWidth
  }, [currentWidth])

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const measure = () => {
      const w = el.getBoundingClientRect().width
      if (w > 0) {
        const max = Math.max(minWidth, Math.floor(w * maxFraction))
        if (widthRef.current > max) {
          setCurrentWidth(prev => Math.min(prev, max))
        }
      }
    }
    measure()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [minWidth, maxFraction])

  useEffect(() => {
    if (currentWidth == null) return
    try {
      localStorage.setItem(storageKey, String(currentWidth))
    } catch {
      /* ignore */
    }
  }, [storageKey, currentWidth])

  useEffect(() => {
    if (!dragging) return
    const onMove = (e) => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const max = Math.max(minWidth, Math.floor(rect.width * maxFraction))
      setCurrentWidth(Math.min(Math.max(e.clientX - rect.left, minWidth), max))
    }
    const onUp = () => setDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [dragging, minWidth, maxFraction])

  const startDrag = useCallback((e) => {
    e.stopPropagation()
    e.preventDefault()
    setDragging(true)
  }, [])

  return { containerRef, currentWidth, dragging, startDrag, setCurrentWidth }
}
