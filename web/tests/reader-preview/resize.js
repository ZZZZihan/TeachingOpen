// Same resize effect used by the production modal, without importing application startup.
export function triggerWindowResizeEvent () { window.dispatchEvent(new Event('resize')) }
