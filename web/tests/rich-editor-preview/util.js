export function getVmParentByName(vm, name) {
    for (let parent = vm.$parent; parent; parent = parent.$parent) if (parent.$options.name === name) return parent
    return null
}
export function triggerWindowResizeEvent() { window.dispatchEvent(new Event('resize')) }
export function validateDuplicateValue() { return Promise.resolve() }
