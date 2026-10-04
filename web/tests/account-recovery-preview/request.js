export async function axios (options) {
    const query = options.params ? '?' + new URLSearchParams(options.params).toString() : ''
    const response = await fetch('/__recovery' + options.url + query, { method: options.method.toUpperCase(), headers: { 'Content-Type': 'application/json' }, body: options.data ? JSON.stringify(options.data) : undefined })
    if (!response.ok) { const error = new Error('Synthetic HTTP failure'); error.response = { status: response.status }; throw error }
    return response.json()
}
