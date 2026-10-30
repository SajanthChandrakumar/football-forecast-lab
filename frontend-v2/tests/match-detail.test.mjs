import test from 'node:test'
import assert from 'node:assert/strict'

let mergeMatchAnalysis
try {
  ({ mergeMatchAnalysis } = await import('../src/lib/match-detail.mjs'))
} catch {
  // The behavior assertion below reports that the merge guard is missing.
}

test('only merges heavy analysis for the same canonical match and prepared version', () => {
  assert.equal(typeof mergeMatchAnalysis, 'function')
  const core = { id: 'canonical-1', view_version: 'source-v2', top_tip: '2:1', detail_level: 'core' }
  const analysis = { id: 'canonical-1', view_version: 'source-v2', home_form: { form: ['W'] }, detail_level: 'analysis' }
  assert.deepEqual(mergeMatchAnalysis(core, analysis), { ...core, ...analysis })
  assert.equal(mergeMatchAnalysis(core, { ...analysis, id: 'canonical-2' }), null)
  assert.equal(mergeMatchAnalysis(core, { ...analysis, view_version: 'source-v1' }), null)
  assert.equal(mergeMatchAnalysis(core, { ...analysis, view_version: undefined }), null)
})
