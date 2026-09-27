export const DEFAULT_UCL_SIMULATION_RUNS = 100

export function uclSimulationPath(runs = DEFAULT_UCL_SIMULATION_RUNS) {
  return `/simulate_ucl?runs=${runs}`
}

export function hasUclSimulationResults(data) {
  return Boolean(data && data.status !== 'unavailable' && Array.isArray(data.results))
}
