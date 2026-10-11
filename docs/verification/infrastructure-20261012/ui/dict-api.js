const values = {
  database_type:[{value:'1',text:'MySQL'},{value:'2',text:'Oracle'},{value:'3',text:'SQLServer'}],
  quartz_status:[{value:'0',text:'正常'},{value:'-1',text:'停止'}]
}
export const getDictItemsFromCache = code => values[code]
export const ajaxGetDictItems = code => Promise.resolve({success:true,result:values[code]||[]})
export const addDictItemsCache = () => {throw Error('Synthetic dictionary mutation is unsupported')}
export const deleteDictItems = () => {throw Error('Synthetic dictionary mutation is unsupported')}
export const deleteDictItemsCache = () => {throw Error('Synthetic dictionary mutation is unsupported')}
