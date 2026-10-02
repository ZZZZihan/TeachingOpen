// Summaries are interpolated as text. Rich course content remains in the existing reader.
export function learningSummary (value) {
    return String(value || '')
        .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, '')
        .replace(/<[^>]*>/g, ' ').replace(/&nbsp;/gi, ' ')
        .replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
        .replace(/\s+/g, ' ').trim()
}

export function courseLocation (course) {
    return {
        path: String(course.showType) === '1' ? '/teaching/mineCourse/courseUnitMap' : '/teaching/mineCourse/courseUnitCard',
        query: { id: course.id }
    }
}
