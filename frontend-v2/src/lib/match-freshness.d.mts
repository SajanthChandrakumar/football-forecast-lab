export type ModelInputFreshness = { status: 'fresh' | 'stale' | 'unknown' | 'failed'; message: string }
export function modelInputFreshness(match: unknown, now?: number): ModelInputFreshness
