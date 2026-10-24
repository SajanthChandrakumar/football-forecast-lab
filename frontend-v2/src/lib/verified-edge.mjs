export function hasVerifiedPreMatchEdge(match) {
  const kickoff = Date.parse(match?.raw_match?.commence_time ?? '')
  const capture = match?.evaluation_forecast ?? {}
  const frozenAt = Date.parse(capture.frozen_at ?? match?.frozen_at ?? '')
  const provenance = capture.input_provenance ?? match?.input_provenance ?? match?.provenance ?? {}
  const sourceTimes = ['odds', 'elo'].map((source) => Date.parse(provenance[source]?.observed_at ?? ''))
  const probabilities = capture.probabilities?.model ?? capture.probabilities
  const completeProbabilities = probabilities && ['home', 'draw', 'away'].every((key) => Number.isFinite(probabilities[key]) && probabilities[key] >= 0)
  return Number.isFinite(kickoff)
    && Number.isFinite(frozenAt)
    && frozenAt < kickoff
    && sourceTimes.every((time) => Number.isFinite(time) && time <= frozenAt && time < kickoff)
    && typeof capture.model_version === 'string'
    && capture.model_version.length > 0
    && completeProbabilities === true
}
