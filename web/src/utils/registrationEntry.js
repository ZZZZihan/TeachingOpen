// Resolve the named route so deployments under a router base keep that prefix.
export function registrationUrl (router, origin) {
    return new URL(router.resolve({ name: 'register' }).href, origin).href
}

export function qrPngCanvas (source, document) {
    if (!source || !source.width || !source.height) throw new Error('QR image is not ready')
    // A QR code has at least 21 modules. This conservative border always gives
    // at least four white modules, including the smallest possible symbol.
    const border = Math.ceil(Math.max(source.width, source.height) * 4 / 21)
    const image = document.createElement('canvas')
    image.width = source.width + border * 2
    image.height = source.height + border * 2
    const context = image.getContext('2d')
    if (!context) throw new Error('Canvas is unavailable')
    context.fillStyle = '#fff'
    context.fillRect(0, 0, image.width, image.height)
    context.drawImage(source, border, border)
    return image
}
