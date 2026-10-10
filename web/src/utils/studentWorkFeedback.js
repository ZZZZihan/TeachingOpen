// The student work list returns a single score/comment pair per row.
export function studentWorkFeedback (row) {
    const value = row && row.score
    const supported = typeof value === 'number' || (typeof value === 'string' && /^[0-5]$/.test(value.trim()))
    const score = supported && Number.isInteger(Number(value)) && Number(value) >= 0 && Number(value) <= 5 ? Number(value) : null
    const comment = row && typeof row.teacherComment === 'string' && row.teacherComment.trim() ? row.teacherComment : ''
    const characters = Array.from(comment)
    const summary = characters.length > 120 ? characters.slice(0, 120).join('') + '…' : comment
    return { score,
        scoreLabel: score === null ? '未评分' : score + ' / 5',
        comment,
        summary,
        workName: row && typeof row.workName === 'string' && row.workName.trim() ? row.workName : '未命名作品' }
}
