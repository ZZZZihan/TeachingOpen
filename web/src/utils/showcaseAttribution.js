import catalogue from '../../../examples/showcase/catalog.json'

// Only the curated work and its versioned upload directory carry this attribution.
// A normal editor save uses another directory and must not retain stale credits.
export function getShowcaseAttribution (work) {
    if (!work || typeof work.workFileKey !== 'string') return null
    const item = catalogue.find(entry => entry.id === work.id && entry.workType === String(work.workType))
    if (!item || !work.workFileKey.startsWith(item.filePrefix)) return null
    const basename = work.workFileKey.slice(item.filePrefix.length)
    const expectedExtension = item.workType === '2' ? '.sb3' : '.py'
    if (!/^[a-f0-9]{32}\.(sb3|py)$/.test(basename) || !basename.endsWith(expectedExtension)) return null
    if (!/^https:\/\//.test(item.sourceUrl) || !/^https:\/\//.test(item.licenseUrl)) return null
    return item
}
