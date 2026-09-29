import test from 'node:test'
import assert from 'node:assert/strict'
import { lineupRows } from '../src/lib/lineup-layout.mjs'

test('places ESPN position codes into football pitch rows', () => {
  const players = [
    { name: 'Goalkeeper', position: 'G' },
    { name: 'Centre Back', position: 'CD-L' },
    { name: 'Wing Back', position: 'RB' },
    { name: 'Central Midfielder', position: 'CM-R' },
    { name: 'Wide Midfielder', position: 'LM' },
    { name: 'Forward', position: 'CF-L' },
    { name: 'Striker', position: 'F' },
  ]

  assert.deepEqual(lineupRows(players), [
    { role: 'Angriff', players: [players[5], players[6]] },
    { role: 'Mittelfeld', players: [players[3], players[4]] },
    { role: 'Abwehr', players: [players[1], players[2]] },
    { role: 'Tor', players: [players[0]] },
  ])
})

test('keeps players with missing positions visible on the pitch', () => {
  const player = { name: 'Unknown', position: null }
  assert.deepEqual(lineupRows([player]), [{ role: 'Weitere', players: [player] }])
})
