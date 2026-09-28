import assert from 'node:assert/strict'
import test from 'node:test'
import { collectTeamLogos } from '../src/lib/team-visuals.mjs'

test('team logos reuse cached standings and fixture assets without inventing missing logos', () => {
  const logos = collectTeamLogos(
    [{ home_team: 'FC Porto', home_logo: 'https://example.test/porto.png', away_team: 'Real Betis', away_logo: null }],
    [{ rows: [{ team: 'Real Betis', logo: 'https://example.test/betis.png' }, { team: 'FC Porto', logo: '' }] }],
  )

  assert.equal(logos['FC Porto'], 'https://example.test/porto.png')
  assert.equal(logos['Real Betis'], 'https://example.test/betis.png')
  assert.equal(logos['Unknown FC'], undefined)
})
