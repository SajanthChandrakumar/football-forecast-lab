import { useEffect, useState, type ReactNode } from 'react'
import { cn } from '../../lib/util'

export function ViewTabs<T extends string>({ id, label, items, value, onChange, wrap = false }: {
  id: string
  label: string
  items: readonly { value: T; label: string; count?: number }[]
  value: T
  onChange: (value: T) => void
  wrap?: boolean
}) {
  return <div id={id} className={cn('view-tabs', wrap && 'view-tabs-wrap')} role="tablist" aria-label={label}>
    {items.map((item, index) => <button key={item.value} type="button" role="tab"
      id={`${id}-tab-${item.value}`} aria-controls={`${id}-panel-${item.value}`}
      aria-selected={value === item.value} tabIndex={value === item.value ? 0 : -1}
      className="view-tab" onClick={() => onChange(item.value)}
      onKeyDown={event => {
        let next: number
        if (event.key === 'ArrowRight') next = (index + 1) % items.length
        else if (event.key === 'ArrowLeft') next = (index - 1 + items.length) % items.length
        else if (event.key === 'Home') next = 0
        else if (event.key === 'End') next = items.length - 1
        else return
        event.preventDefault()
        onChange(items[next].value)
        document.getElementById(`${id}-tab-${items[next].value}`)?.focus()
      }}>
      {item.label}{item.count != null && <span className="view-tab-count" aria-hidden="true">{item.count}</span>}
    </button>)}
  </div>
}

export function ViewPanel({ id, value, active, children, className }: {
  id: string; value: string; active: string; children: ReactNode; className?: string
}) {
  const [visited, setVisited] = useState(active === value)
  useEffect(() => { if (active === value) setVisited(true) }, [active, value])
  return <section role="tabpanel" id={`${id}-panel-${value}`} aria-labelledby={`${id}-tab-${value}`}
    hidden={active !== value} tabIndex={0} className={cn('view-panel', className)}>
    {(visited || active === value) && children}
  </section>
}
