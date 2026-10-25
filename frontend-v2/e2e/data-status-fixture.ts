import type { CompetitionId } from '../src/lib/types'

export function dataStatusFixture(competition: CompetitionId, observedAt: string, unknown = false) {
  const rows = [['fixtures_results', 'Spiele & Resultate', 'espn'], ['standings', 'Tabelle', 'espn'], ['team_form', 'Teamform', 'espn'], ['ratings', 'Elo-Werte', competition === 'wc2026' ? 'local_elo' : 'clubelo'], ['odds', 'Buchmacherquoten', 'odds_api'], ['lineups', 'Aufstellungen & Spielerstatistiken', 'espn']]
  return { competition, generated_at: observedAt,
    datasets: rows.map(([id, label, provider]) => ({ id, label, providers: { configured: [provider], observed: unknown ? [] : [provider] }, source_kind: id === 'standings' && competition === 'ucl2026' ? 'derived' : provider === 'local_elo' ? 'local' : 'provider', status: unknown ? 'unknown' : 'fresh', observed_at: unknown ? null : observedAt, last_attempt_at: null, last_successful_at: unknown ? null : observedAt, error: null, coverage: id === 'team_form' ? { available: 5, required: 10, unit: 'teams' } : null })),
    maintenance: { status: unknown ? null : 'partial', last_run_at: observedAt, last_successful_at: null, next_due_at: null, interval_seconds: 60, error: null, running: false },
    quotas: { scope: 'global_shared_all_competitions', providers: {
      odds: { reported: { remaining: unknown ? null : 0, used: unknown ? null : 500, limit: null, observed_at: unknown ? null : observedAt, status: unknown ? 'unknown' : 'fresh' }, app_budget: { used: unknown ? null : 20, remaining: unknown ? null : 380, limit: 400, unit: 'credits', window_seconds: 2678400, headroom: 100, status: unknown ? 'unknown' : 'available' } },
      football: { reported: { remaining: unknown ? null : 75, used: unknown ? null : 25, limit: unknown ? null : 100, observed_at: unknown ? null : observedAt, status: unknown ? 'unknown' : 'fresh' }, app_budget: { used: unknown ? null : 5, remaining: unknown ? null : 75, limit: 80, unit: 'requests', window_seconds: 86400, headroom: 20, status: unknown ? 'unknown' : 'available' } },
    } },
  }
}
