import { message } from 'ant-design-vue/es'
// import defaultSettings from '../defaultSettings';

let themeCompilerPromise
let themeBuildQueue = Promise.resolve()

const colorList = [
    {
        key: '薄暮', color: '#F5222D'
    },
    {
        key: '火山', color: '#FA541C'
    },
    {
        key: '日暮', color: '#FAAD14'
    },
    {
        key: '明青', color: '#13C2C2'
    },
    {
        key: '极光绿', color: '#52C41A'
    },
    {
        key: '科技蓝（默认）', color: '#146fc2'
    },
    {
        key: '极客蓝', color: '#2F54EB'
    },
    {
        key: '酱紫', color: '#722ED1'
    }
]

const loadThemeCompiler = () => {
    if (themeCompilerPromise) {
        return themeCompilerPromise
    }
    themeCompilerPromise = new Promise((resolve, reject) => {
        const lessStyleNode = document.createElement('link')
        const lessConfigNode = document.createElement('script')
        const lessScriptNode = document.createElement('script')
        const fail = error => {
            [lessStyleNode, lessConfigNode, lessScriptNode].forEach(node => {
                if (node.parentNode) {
                    node.parentNode.removeChild(node)
                }
            })
            themeCompilerPromise = null
            reject(error)
        }
        lessStyleNode.setAttribute('rel', 'stylesheet/less')
        lessStyleNode.setAttribute('href', '/color.less')
        lessConfigNode.innerHTML = `
            window.less = {
                async: true,
                env: 'production',
                javascriptEnabled: true
            };
        `
        lessScriptNode.src = 'https://gw.alipayobjects.com/os/lib/less.js/3.8.1/less.min.js'
        lessScriptNode.async = true
        lessScriptNode.onerror = () => fail(new Error('Theme compiler failed to load'))
        lessScriptNode.onload = () => {
            lessScriptNode.onload = null
            lessScriptNode.onerror = null
            const less = window.less
            if (!less || !less.modifyVars) {
                fail(new Error('Theme compiler is unavailable'))
                return
            }
            // Less starts a default refresh while loading. Wait before applying
            // the saved choice so its CSS cannot be overwritten by that refresh.
            Promise.resolve(less.pageLoadFinished).then(() => resolve(less), fail)
        }
        document.body.appendChild(lessStyleNode)
        document.body.appendChild(lessConfigNode)
        document.body.appendChild(lessScriptNode)
    })
    return themeCompilerPromise
}

const updateTheme = primaryColor => {
    if (!primaryColor) {
        return
    }
    const hideMessage = message.loading('正在编译主题！', 0)
    // Serialize requests, including choices made before the compiler has loaded.
    // A failed compilation must not prevent the next saved choice from applying.
    const build = themeBuildQueue
        .then(loadThemeCompiler)
        .then(less => less.modifyVars({ '@primary-color': primaryColor }))
    themeBuildQueue = build.catch(() => {})
    return build.then(() => {
        hideMessage()
    }).catch(() => {
        message.error('主题更新失败，请重新选择主题色')
        hideMessage()
    })
}

const updateColorWeak = colorWeak => {
    // document.body.className = colorWeak ? 'colorWeak' : '';
    colorWeak ? document.body.classList.add('colorWeak') : document.body.classList.remove('colorWeak')
}

export { updateTheme, colorList, updateColorWeak }
