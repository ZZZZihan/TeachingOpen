const isConfig = value => value !== null && typeof value === 'object' && !Array.isArray(value)

let startupGeneration = 0
let deniedGeneration = 0

function withDeadline (request, timeoutMs) {
    let timer
    const deadline = new Promise((resolve, reject) => {
        timer = setTimeout(() => reject(new Error('Startup request timed out')), timeoutMs)
    })
    return Promise.race([request, deadline]).finally(() => clearTimeout(timer))
}

// Cached data can start the UI immediately; expired requests cannot write later.
function loadResource (fetch, cached, validate, save, generation, timeoutMs, clearMenu) {
    const hasCache = validate(cached)
    const revoke = error => {
        const status = Number(error.response ? error.response.status : error.status)
        if (generation === startupGeneration && (status === 401 || status === 403)) {
            deniedGeneration = generation
            clearMenu()
        }
    }
    // Observe authorization on the original request even after the UI deadline.
    // Only the raced result is allowed to persist successful data.
    const request = Promise.resolve().then(fetch).then(response => {
        if (!response || response.success !== true || !validate(response.result)) {
            const error = new Error('Invalid startup response')
            error.status = response && response.code
            throw error
        }
        return response
    }).catch(error => {
        revoke(error)
        throw error
    })
    const refresh = withDeadline(request, timeoutMs).then(response => {
        if (generation !== startupGeneration || generation === deniedGeneration) return null
        save(response.result)
        return response.result
    }).catch(() => {
        if (generation !== startupGeneration || generation === deniedGeneration) return null
        return hasCache ? cached : null
    })
    return hasCache ? Promise.resolve(cached) : refresh
}

export async function loadStartupData ({ cachedConfig, cachedMenu, getConfig, getMenu, saveConfig, saveMenu, clearMenu, timeoutMs = 15000 }) {
    const generation = ++startupGeneration
    const [sysConfig, menu] = await Promise.all([
        loadResource(getConfig, cachedConfig, isConfig, saveConfig, generation, timeoutMs, clearMenu),
        loadResource(getMenu, cachedMenu, Array.isArray, saveMenu, generation, timeoutMs, clearMenu)
    ])
    const isCurrent = () => generation === startupGeneration && generation !== deniedGeneration
    if (!isCurrent() || !isConfig(sysConfig) || !Array.isArray(menu)) {
        throw new Error('Startup data unavailable')
    }
    return { sysConfig, menu, isCurrent }
}

export function showStartupError (retry, document) {
    const app = document.getElementById('app')
    if (!app) return
    app.textContent = ''
    app.className = 'startup-error'
    const message = document.createElement('p')
    message.textContent = '网站暂时无法加载，请检查网络后重试。'
    message.setAttribute('role', 'alert')
    const button = document.createElement('button')
    button.id = 'startup-retry'
    button.type = 'button'
    button.textContent = '重新加载'
    button.addEventListener('click', retry)
    app.appendChild(message)
    app.appendChild(button)
}
