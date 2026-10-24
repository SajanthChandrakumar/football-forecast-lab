import test from 'node:test'
import assert from 'node:assert/strict'
import * as teamForm from '../src/lib/team-form.mjs'

test('club form display keeps only verified, pre-kickoff league and cup rows newest first', () => {
  assert.equal(typeof teamForm.verifiedClubFormMatches, 'function')
  const form = {
    scope: 'all_competitions',
    matches: [
      { fixture_id: 'cup', played_at: '2026-10-10T18:00:00Z', identity_verified: true, home_id: '1', home_team: 'Arsenal', away_id: '2', away_team: 'Chelsea', venue: 'home', score: '2:1', competition_kind: 'cup', result: 'W', goals_for: 2, goals_against: 1 },
      { fixture_id: 'late', played_at: '2026-10-20T18:00:00Z', identity_verified: true, home_id: '1', home_team: 'Arsenal', away_id: '3', away_team: 'Liverpool', venue: 'home', score: '1:1', competition_kind: 'league', result: 'D', goals_for: 1, goals_against: 1 },
      { fixture_id: 'unverified', played_at: '2026-10-09T18:00:00Z', identity_verified: false, home_id: '1', home_team: 'Arsenal', away_id: '4', away_team: 'Spurs', venue: 'home', score: '9:0', competition_kind: 'league', result: 'W', goals_for: 9, goals_against: 0 },
      { fixture_id: 'league', played_at: '2026-10-08T18:00:00Z', identity_verified: true, home_id: '5', home_team: 'Newcastle', away_id: '1', away_team: 'Arsenal', venue: 'away', score: '0:1', competition_kind: 'league', result: 'L', goals_for: 0, goals_against: 1 },
      { fixture_id: 'no-identity', played_at: '2026-10-07T18:00:00Z', identity_verified: true, venue: 'home', score: '8:0', competition_kind: 'league', result: 'W', goals_for: 8, goals_against: 0 },
    ],
  }
  const rows = teamForm.verifiedClubFormMatches(form, { before: '2026-10-15T12:00:00Z', competition: 'all' })
  assert.deepEqual(rows.map(({ fixture_id }) => fixture_id), ['cup', 'league'])
  assert.deepEqual(teamForm.clubFormSummary(rows), { played: 2, wins: 1, draws: 0, losses: 1, goalsFor: 2, goalsAgainst: 2 })
})

test('club form display rejects legacy competition-only envelopes and supports cup/europe filters', () => {
  assert.equal(typeof teamForm.verifiedClubFormMatches, 'function')
  const rows = [
    { fixture_id: 'europe', played_at: '2026-10-10T18:00:00Z', identity_verified: true, home_id: '1', home_team: 'Arsenal', away_id: '2', away_team: 'Chelsea', venue: 'home', score: '0:0', competition_kind: 'europe', result: 'D', goals_for: 0, goals_against: 0 },
    { fixture_id: 'cup', played_at: '2026-10-09T18:00:00Z', identity_verified: true, home_id: '1', home_team: 'Arsenal', away_id: '3', away_team: 'Liverpool', venue: 'home', score: '1:0', competition_kind: 'cup', result: 'W', goals_for: 1, goals_against: 0 },
  ]
  assert.deepEqual(teamForm.verifiedClubFormMatches({ scope: 'league', matches: rows }), [])
  assert.deepEqual(teamForm.verifiedClubFormMatches({ scope: 'all_competitions', matches: rows }, { competition: 'europe' }).map(({ fixture_id }) => fixture_id), ['europe'])
})

test('team comparison reads the verified all-competition form attached to that club', () => {
  assert.equal(typeof teamForm.clubFormForTeam, 'function')
  const row = { fixture_id: 'same', played_at: '2026-10-10T18:00:00Z', identity_verified: true, home_id: '1', home_team: 'Arsenal', away_id: '4', away_team: 'Chelsea', venue: 'home', score: '2:0', competition_kind: 'league', result: 'W', goals_for: 2, goals_against: 0 }
  const fixtures = [
    { home_team: 'Arsenal', away_team: 'Chelsea', home_form: { scope: 'all_competitions', matches: [row] }, away_form: { scope: 'all_competitions', matches: [] } },
    { home_team: 'Arsenal', away_team: 'Liverpool', home_form: { scope: 'all_competitions', matches: [row] }, away_form: { scope: 'league', matches: [row] } },
  ]
  assert.deepEqual(teamForm.clubFormForTeam('Arsenal', fixtures)?.matches.map(({ fixture_id }) => fixture_id), ['same'])
  assert.deepEqual(teamForm.clubFormForTeam('Chelsea', fixtures)?.matches, [])
})

test('verified form scores display home-away order for away-team records', () => {
  assert.equal(typeof teamForm.clubFormHomeAwayScore, 'function')
  assert.equal(teamForm.clubFormHomeAwayScore({ venue: 'away', score: '1:2', goals_for: 1, goals_against: 2 }), '2:1')
  assert.equal(teamForm.clubFormHomeAwayScore({ venue: 'home', score: '2:1', goals_for: 2, goals_against: 1 }), '2:1')
})
