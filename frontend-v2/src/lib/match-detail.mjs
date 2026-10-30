export function mergeMatchAnalysis(core, analysis) {
  if (!core?.id || core.id !== analysis?.id || !core.view_version || core.view_version !== analysis.view_version) return null
  return { ...core, ...analysis }
}
