import { sharedTipIsOpen } from './fixture-status.mjs'

function nonEmptyTip(value) {
  return typeof value === 'string' && value.trim() ? value : null
}

export function getSavedTipForMatch(match, archive) {
  const archiveId = typeof match.archive_id === 'string' ? match.archive_id.trim() : ''
  const mappedEntry = archiveId ? archive?.[archiveId] : undefined
  if (mappedEntry) return nonEmptyTip(mappedEntry.prediction?.user_tip) ?? nonEmptyTip(match.user_tip) ?? ''

  const canonicalEntry = archive?.[match.id]
  return nonEmptyTip(canonicalEntry?.prediction?.user_tip) ?? nonEmptyTip(match.user_tip) ?? ''
}

export function openUnsubmittedTips(matches, archive, now = Date.now()) {
  if (!archive) return []
  return matches.filter((match) => {
    const kickoff = match.raw_match?.commence_time
    return !match.completed
      && !match.actual_score
      && sharedTipIsOpen(kickoff, now)
      && !getSavedTipForMatch(match, archive)
  })
}
