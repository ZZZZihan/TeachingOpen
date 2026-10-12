import Axios from 'axios'
function checkedUrl(url) {
  if (!/^\/(sys\/dataSource|sys\/quartzJob|online\/cgreport\/api)\//.test(url)) throw new Error('Unexpected synthetic API URL: '+url)
  return url
}
export const httpAction = (url,data,method) => Axios({url:checkedUrl(url),data,method}).then(r=>r.data)
export const postAction = (url,data) => httpAction(url,data,'post')
