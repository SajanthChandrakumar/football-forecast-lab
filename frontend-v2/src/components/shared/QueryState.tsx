export function QueryState({ title, message, onRetry }: { title: string; message: string; onRetry?: () => void }) {
  return <div role={onRetry ? 'alert' : 'status'} className="rounded-xl border border-line bg-surface px-5 py-8">
    <h2 className="text-base font-semibold text-fg">{title}</h2>
    <p className="mt-2 max-w-prose text-sm leading-relaxed text-fg-2">{message}</p>
    {onRetry && <button type="button" onClick={onRetry} className="mt-4 min-h-11 rounded-lg border border-line-2 px-4 text-sm font-semibold text-fg hover:bg-surface-2">Erneut versuchen</button>}
  </div>
}
