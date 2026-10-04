export const filterObj = value => Object.fromEntries(Object.entries(value).filter(([key, item]) => item !== '' && item !== undefined && item !== null))
