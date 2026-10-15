import MarkdownIt from 'markdown-it/dist/browser/markdown-it.umd.min.js'
import { sanitizeRichText } from '@/utils/richText'

const MAX_BYTES = 10 * 1024 * 1024
const markdown = new MarkdownIt({ html: false, linkify: false })
const imageTypes = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp' }

function absoluteLink (value, base) {
    if (value.startsWith('#')) return value
    try {
        const url = new URL(value, base)
        return ['http:', 'https:'].includes(url.protocol) ? url.href : ''
    } catch (error) { return '' }
}
const imageRenderer = markdown.renderer.rules.image
markdown.renderer.rules.image = (tokens, index, options, env, renderer) => {
    const token = tokens[index]
    token.attrSet('src', absoluteLink(token.attrGet('src') || '', env.url))
    return imageRenderer(tokens, index, options, env, renderer)
}
markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
    const token = tokens[index]
    token.attrSet('href', absoluteLink(token.attrGet('href') || '', env.url))
    token.attrSet('target', '_blank')
    token.attrSet('rel', 'noopener noreferrer')
    return renderer.renderToken(tokens, index, options)
}

async function readBounded (response) {
    if (Number(response.headers.get('content-length')) > MAX_BYTES) throw new Error('教案超过 10 MB，请联系老师拆分后重新上传。')
    if (!response.body || !response.body.getReader) {
        const buffer = await response.arrayBuffer()
        if (buffer.byteLength > MAX_BYTES) throw new Error('教案超过 10 MB，请联系老师拆分后重新上传。')
        return new Uint8Array(buffer)
    }
    const reader = response.body.getReader()
    const chunks = []
    let size = 0
    try {
        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            size += value.byteLength
            if (size > MAX_BYTES) {
                await reader.cancel()
                throw new Error('教案超过 10 MB，请联系老师拆分后重新上传。')
            }
            chunks.push(value)
        }
    } finally { reader.releaseLock() }
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
    return bytes
}

// Read the existing authorized attachment endpoint; never navigate to an attachment URL.
export async function loadCoursePlan (value, { signal } = {}) {
    let url
    try { url = new URL(value, window.location.origin) } catch (error) { throw new Error('教案地址不可用，请联系老师。') }
    if (!value || !['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('教案地址不可用，请联系老师。')
    const extension = url.pathname.split('.').pop().toLowerCase()
    if (!['md', 'markdown', 'txt', 'html', 'htm', 'pdf', ...Object.keys(imageTypes)].includes(extension)) {
        throw new Error('此格式暂不支持在线阅读，请联系老师将教案转换为 Markdown 或 PDF。')
    }
    const response = await fetch(url.href, { signal, credentials: url.origin === window.location.origin ? 'same-origin' : 'omit', referrerPolicy: 'same-origin' })
    if (!response.ok) {
        if ([401, 403].includes(response.status)) throw new Error('暂无权限读取教案，请确认登录状态或联系老师。')
        if (response.status === 404) throw new Error('教案文件不存在，请联系老师更新。')
        throw new Error('教案加载失败，请稍后重试。')
    }
    const mime = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase()
    if (mime === 'application/json' || (mime === 'text/html' && !['html', 'htm'].includes(extension))) throw new Error('未能读取教案文件，请确认登录状态后重试。')
    const bytes = await readBounded(response)
    if (!bytes.length) return { type: 'text', content: '' }
    if (extension === 'pdf') return { type: 'pdf', content: new Blob([bytes], { type: 'application/pdf' }) }
    if (imageTypes[extension]) return { type: 'image', content: new Blob([bytes], { type: imageTypes[extension] }) }
    const content = new TextDecoder('utf-8').decode(bytes)
    if (extension === 'txt') return { type: 'text', content }
    return { type: 'html', content: sanitizeRichText(['md', 'markdown'].includes(extension) ? markdown.render(content, { url: url.href }) : content) }
}
