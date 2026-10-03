// Peripheral dependency replacement; same empty-value semantics as the real filterObj.
export function filterObj (obj) {
  for (const key of Object.keys(obj)) if (obj[key] == null || obj[key] === '') delete obj[key]
  return obj
}
