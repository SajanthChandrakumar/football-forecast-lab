import { sharedTipIsOpen } from './fixture-status.mjs'

export function openUnsubmittedTips(matches, archive, now = Date.now()) {
  if (!archive) return []
  return matches.filter((match) => {
    const saved = archive[match.id]
    const kickoff = match.raw_match?.commence_time
    return Boolean(saved)
      && !match.completed
      && !match.actual_score
      && sharedTipIsOpen(kickoff, now)
      && !(typeof saved.prediction?.user_tip === 'string' && saved.prediction.user_tip.trim())
  })
}
