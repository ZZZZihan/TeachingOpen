import Axios from 'axios'
import { axios } from '@/utils/request'

// A single assignment file is ready only after both transfer and registration.
export function createFileTask () { return Axios.CancelToken.source() }

export async function uploadAssignmentFile (file, config, task, onStage) {
    const uploadType = config.uploadType || 'local'
    const request = options => axios({ ...options, cancelToken: task.token, localError: true })
    let path = ''
    let location = 1
    if (!['local', 'qiniu'].includes(uploadType)) throw new Error('Unsupported upload storage')
    onStage('uploading')
    const form = new FormData()
    if (uploadType === 'local') {
        form.append('file', file)
        form.append('bizPath', 'temp')
        form.append('isup', '1')
        const result = await request({ url: '/sys/common/upload', method: 'post', data: form, headers: { 'Content-Type': 'multipart/form-data' } })
        if (!result || !result.success || typeof result.message !== 'string' || !result.message.trim()) throw new Error('File transfer failed')
        path = result.message
    } else {
        if (!/^[a-z0-9-]{1,32}$/.test(config.qiniuArea || '')) throw new Error('Invalid upload region')
        const credential = await request({ url: '/common/qiniu/getToken', method: 'get' })
        if (!credential || !credential.success || !credential.result || !credential.keyPrefix) throw new Error('Upload credential unavailable')
        task.token.throwIfRequested()
        const random = new Uint8Array(16)
        window.crypto.getRandomValues(random)
        const suffix = file.name.includes('.') ? '.' + file.name.split('.').pop().replace(/[^a-zA-Z0-9]/g, '').slice(0, 16) : ''
        path = credential.keyPrefix + Array.from(random, byte => byte.toString(16).padStart(2, '0')).join('') + suffix
        form.append('key', path)
        form.append('token', credential.result)
        form.append('file', file)
        // The platform session belongs only to our API, never to the cloud upload.
        const result = await Axios({ url: 'https://upload-' + config.qiniuArea + '.qiniup.com', method: 'post', data: form, timeout: 60000, cancelToken: task.token, withCredentials: false })
        if (!result || !result.data || result.data.key !== path) throw new Error('Cloud file transfer failed')
        location = 2
    }
    task.token.throwIfRequested()
    onStage('registering')
    const registered = await request({ url: '/system/sysFile/add', method: 'post', data: { fileName: file.name, filePath: path, fileLocation: location, fileTag: '学生作业' } })
    task.token.throwIfRequested()
    if (!registered || !registered.success || !registered.result || !registered.result.id || registered.result.filePath !== path) throw new Error('File registration failed')
    return registered.result
}
