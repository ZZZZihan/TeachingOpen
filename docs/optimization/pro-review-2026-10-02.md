# Pro独立审查记录

此请求发送时未授权提交推送，用户随后授权私有GitHub同步。原通道的发送识别失败；确认指定会话中的实际请求后，恢复读取同一会话的答复。以下保留原文。独立代码判断不等于后端运行、人工验收或上线许可。

会话：https://chatgpt.com/c/6abf708a-4464-83e8-b978-5dacb05d8233

发送SHA-256：`dcb735bfe14bed2bc6ad8793b63555fd2360ee6366aba31d0fe8149bc1641ca0`

答复SHA-256：`fdf106f94aacb296aa375fd3492f4cd7067f5bd708b4bbd41f7041d1072f80a9`

## Message Sent To ChatGPT Pro

请对 TeachingOpen 做资深独立审查并选下一轮优化。用户授权本地修改与测试、要求 Pro 审核；禁止生产变更、生产数据测试及提交推送。上传通道失败，改用以下最小内联证据。请给出3个排序发现、推荐一个本地可验收的修改切片、验收项和发布阻断项。重点比较启动失败恢复、课程列表遗漏、后端权限/隔离基线与8.66MiB入口优化。欢迎否定优先级。区分代码推断、方法测试和实际业务验收。中文约1000字以内。

---

Attached context: TeachingOpen最小代码证据

```text
以下为有意选择的原代码片段；未提供部分不得假定已审查。
main.js 启动请求（后接 new Vue(...).$mount）：
const start = async()=>{
  //获取配置
  let sysConfig = store.getters.sysConfig;
  let getConfigCallback = function(res){
    if (res.success) {
      sysConfig = res.result
      Vue.ls.set(SYS_CONFIG, sysConfig, cacheTime)
      store.commit('SET_SYS_CONFIG', sysConfig)
    }
  }
  if (!sysConfig) {
    await getSysConfig().then(getConfigCallback)
  }else{
    getSysConfig().then(getConfigCallback)
  }
  //获取菜单
  if (store.getters.menuList == null) {
    await getMenu().then(res => {
      const menuData = res.result;
      Vue.ls.set(MENU, menuData, cacheTime)
      store.commit('SET_MENU', menuData)
    })
  }else{
    getMenu().then(res => {
      const menuData = res.result;
      Vue.ls.set(MENU, menuData, cacheTime)
      store.commit('SET_MENU', menuData)
    })
  }


CourseList.vue 请求方法：
        resetData () {
            // Invalidate the previous query before starting a new first-page request.
            this.requestId += 1
            this.loading = false
            this.page = 0
            this.hasMore = true
            this.datasource = []
            this.loadError = ''
            return this.getData()
        },
        getData () {
            if (this.loading || !this.hasMore) {
                return
            }
            const requestId = ++this.requestId
            const nextPage = this.page + 1
            this.loading = true
            this.loadError = ''
            return getAction('/teaching/teachingCourse/getHomeCourse', {
                courseType: this.courseType,
                courseCategory: this.courseCategory,
                courseName: this.courseName,
                orderBy: 'time',
                pageSize: this._isMobile() ? 12 : 24,
                pageNo: nextPage
            }).then((res) => {
                if (requestId !== this.requestId) {
                    return
                }
                if (!res || !res.success || !res.result || !Array.isArray(res.result.records) ||
                    typeof res.result.total !== 'number' || !Number.isFinite(res.result.total) || res.result.total < 0) {
                    throw new Error('Invalid course response')
                }
                const records = res.result.records
                this.datasource = this.datasource.concat(records)
                // Only advance after success so retrying a failed request cannot skip a page.
                this.page = nextPage
                this.hasMore = records.length > 0 && this.datasource.length < res.result.total
            }).catch(() => {
                if (requestId === this.requestId) {
                    this.loadError = '课程加载失败，请重试。'
                }
            }).finally(() => {
                if (requestId === this.requestId) {
                    this.loading = false
                }
            })
        },

其他已核查事实：公共课程接口 getHomeCourse 构建 QueryWrapper 后没有 orderBy；前端 orderBy=time 未在控制器消费。getCurrentConfig 返回 Result<Map>，getUserMenu 返回 Result<JSONArray>。getters.sysConfig/menuList 从 Vue.ls 读取并覆写 store。课程写入接口尚无隔离运行证明，未改后端。生产系统与源码对应关系未知。已有课程方法测试13项、修改页面lint和生产build通过，但无浏览器测试。Vue CLI3/Terser1关闭MD4缓存保留压缩，锁文件保留版本变化0。

```

## Message Received From ChatGPT Pro

结论：下一轮选启动失败恢复；本地可做，发布 NO-GO。否定先拆8.66MiB入口。
三项排序发现
权限/隔离基线：最高发布风险，但非已证漏洞。 未提供完整鉴权链、资源归属检查与隔离运行证据；菜单不能替代后端鉴权。须用合成账号、数据验证未登录、跨角色及他人课程ID访问。
OWASP Cheat Sheet Series
启动恢复：最高可执行修复优先级。 冷缓存请求拒绝会使start拒绝；若挂载依赖其完成，会阻断启动【代码推断】。片段未捕获暖缓存刷新失败；菜单success:false仍写缓存【方法复演确认】。不能只补吞异常的catch。
MDN Web Docs
+1
课程遗漏：仍未闭环。 requestId及成功后翻页有价值，但后端缺少含唯一键的稳定排序。
PostgreSQL
合成重叠页复演出现“48条、47个唯一ID”却hasMore=false。若页大小由12变24也会跳页；_isMobile是否可变未审，不能称真实故障。单纯前端去重不治根因。
**8.66MiB后置：**构建体积不等于传输量，也未证明首屏瓶颈；先测实际传输及JavaScript执行时间，再决定拆包。
Chrome for Developers
+1
推荐切片：启动状态与重试
仅改启动协调、错误壳层及测试，不碰后端、构建链。设置有界超时、显式失败和手动重试；校验success及配置对象、菜单数组契约。无有效数据只显示错误壳，不用空数据冒充启动成功；401/403不沿用菜单。用请求代次挡住迟到写入；鉴于getters回读缓存，须同步维护Vue.ls/store，根实例仅挂载一次。
**验收项：**覆盖冷/暖缓存×配置/菜单的拒绝、超时、业务失败、畸形返回；失败可见、重试恢复、旧响应不覆盖，合法空菜单不误报。补拦截非本地请求的浏览器测试，并回归原13项、lint/build。
**证据等级：**原13项及构建结果来自所报记录；本轮4项内联内存复演仅证方法机制，未跑原工程或浏览器，实际业务未验收。未改源码、触生产或提交推送。
**发布阻断项：**数据库、存储及外部服务隔离未证明；权限矩阵未过，须同时证明合法操作成功、越权拒绝且无副作用；课程完整性、隔离环境核心流程及源码—部署版本对应未闭合。启动切片通过不解除这些阻断。

## 实际补丁复审

以下是实施期间版本的完整复审。Pro提出的三个问题随后修复；本地回归31项通过，修复后的版本未再获Pro独立复审，不把这项自检表述为Pro批准。

## Message Sent To ChatGPT Pro

我已按你的建议落实启动恢复，用户后来另行授权同步私有 GitHub；请复审下面实际补丁的缓存/权限/并发边界，指出必须先改的具体问题；若没有阻断，给出可支持的本地结论和还缺的证据。尤其审查暖缓存立即挂载后后台401/403清空菜单、15秒Promise.race让迟到响应不能写入、代次使重试前刷新失效的组合。请独立判断，中文400字内。

---

Attached context: 实际启动恢复补丁

```text
已完成：26项Node受控方法检查（原课程13+启动13）通过，修改3文件ESLint通过，最新生产build正在执行。此前浏览器用实际dist+本地合成接口验证配置503错误壳/按钮重试恢复。没有Java/Maven，没有业务或后端权限验收。
实际startup.js：
const isConfig = value => value !== null && typeof value === 'object' && !Array.isArray(value)

let startupGeneration = 0
let deniedGeneration = 0

function withDeadline (request, timeoutMs) {
    let timer
    const deadline = new Promise((resolve, reject) => {
        timer = setTimeout(() => reject(new Error('Startup request timed out')), timeoutMs)
    })
    return Promise.race([Promise.resolve().then(request), deadline]).finally(() => clearTimeout(timer))
}

// Cached data can start the UI immediately; expired requests cannot write later.
function loadResource (fetch, cached, validate, save, generation, timeoutMs, clearMenu) {
    const hasCache = validate(cached)
    const refresh = withDeadline(fetch, timeoutMs).then(response => {
        if (!response || response.success !== true || !validate(response.result)) {
            const error = new Error('Invalid startup response')
            error.status = response && response.code
            throw error
        }
        if (generation !== startupGeneration || generation === deniedGeneration) return null
        save(response.result)
        return response.result
    }).catch(error => {
        if (generation !== startupGeneration) return null
        const status = error.response ? error.response.status : error.status
        if (status === 401 || status === 403) {
            deniedGeneration = generation
            clearMenu()
            return null
        }
        return hasCache ? cached : null
    })
    return hasCache ? Promise.resolve(cached) : refresh
}

export async function loadStartupData ({ cachedConfig, cachedMenu, getConfig, getMenu, saveConfig, saveMenu, clearMenu, timeoutMs = 15000 }) {
    const generation = ++startupGeneration
    const [sysConfig, menu] = await Promise.all([
        loadResource(getConfig, cachedConfig, isConfig, saveConfig, generation, timeoutMs, clearMenu),
        loadResource(getMenu, cachedMenu, Array.isArray, saveMenu, generation, timeoutMs, clearMenu)
    ])
    if (generation !== startupGeneration || !isConfig(sysConfig) || !Array.isArray(menu)) {
        throw new Error('Startup data unavailable')
    }
    return { sysConfig, menu }
}

export function showStartupError (retry, document) {
    const app = document.getElementById('app')
    if (!app) return
    app.textContent = ''
    app.className = 'startup-error'
    const message = document.createElement('p')
    message.textContent = '网站暂时无法加载，请检查网络后重试。'
    message.setAttribute('role', 'alert')
    const button = document.createElement('button')
    button.id = 'startup-retry'
    button.type = 'button'
    button.textContent = '重新加载'
    button.addEventListener('click', retry)
    app.appendChild(message)
    app.appendChild(button)
}

main.js协调片段：
let cacheTime = 1800000 // 缓存时间

let starting = false
let started = false

const start = async () => {
    if (starting || started) return
    starting = true
    const retryButton = window.document.getElementById('startup-retry')
    if (retryButton) {
        retryButton.disabled = true
        retryButton.textContent = '正在加载……'
    }
    let sysConfig
    try {
        const data = await loadStartupData({
            cachedConfig: store.getters.sysConfig,
            cachedMenu: store.getters.menuList,
            getConfig: getSysConfig,
            getMenu,
            saveConfig: value => {
                Vue.ls.set(SYS_CONFIG, value, cacheTime)
                store.commit('SET_SYS_CONFIG', value)
            },
            saveMenu: value => {
                Vue.ls.set(MENU, value, cacheTime)
                store.commit('SET_MENU', value)
            },
            clearMenu: () => {
                Vue.ls.set(MENU, [], cacheTime)
                store.commit('SET_MENU', [])
            }
        })
        sysConfig = data.sysConfig
    } catch (error) {
        starting = false
        showStartupError(start, window.document)
        return
    }
    started = true
    starting = false

Vue.ls和store本轮一起维护，getters仍回读Vue.ls；clearMenu保存合法空数组仅用于撤销已缓存菜单，冷启动任一必需资源失败不挂载。暖缓存可能先显示旧菜单，后收到401/403撤销；它不承担后端鉴权。浏览器不会访问非127.0.0.1。

```

## Message Received From ChatGPT Pro

**结论：暖缓存先挂载本身非阻断，但此切片须先修三处。**本轮按内联代码做Node受控复演，非原工程验收。
拒绝后仍启动成功：冷配置＋暖菜单，配置成功与菜单403交错，已清菜单却返回成功。loadStartupData末尾缺拒绝代次判断；返回及挂载前须复核。
撤销被当成有效缓存：冷启403写入[]，重试认作有效缓存，再次403仍可启动成功。应删除缓存或标记失效，区别于成功响应的合法空菜单。
超时后不再处理拒绝：本片段超时后的401/403不会触发撤销。race不取消原请求；须独立处理原请求的同代鉴权拒绝，继续禁止迟到数据写入。
MDN Web Docs
**方法级支持：**截止前拒绝可撤销；迟到成功、旧代次保存及清菜单均被挡住。仍缺最新build结果、上述交错的实际dist浏览器回归、后端权限与隔离证据。这些是启动状态问题，不是已证后端越权。
