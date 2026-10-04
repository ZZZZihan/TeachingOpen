# 找回密码 UI 修复作者记录

范围：`fix/account-recovery-ui`，从成员布局 PR #63 分支基础创建；只修改账号找回页面、请求助手及其测试/合成预览。沿用已有 UserLayout 与天津工业大学顶栏，未新增依赖。

## 行为

- 页面包含明确标题、四步指引、每个输入的可见 label、可键盘操作的图形验证码刷新按钮与内联错误。
- 第一步保留真实 `/sys/randomImage`、`/sys/checkCaptcha` 和最终 `/sys/user/querySysUser` 查询。移除每键账号存在检查，数字学号仍作为账号查询；仅符合大陆 11 位手机号规则的输入使用 phone 查询。
- 查询返回的脱敏手机号仅用作提示。第二步始终使用用户填写的完整绑定手机号发送与验证短信，并携带 username。第三步携带用户输入的 smscode，不读取后端返回的验证码。
- SMS、手机号验证和改密请求使用 POST JSON；改密不把密码或验证码写入 URL，恢复请求不附加旧登录令牌，并由表单处理错误。
- 短信发送成功后才启动 600 秒重发等待；失败允许重试。服务端 `recoveryState=code_active` 明确提示使用现有码或稍后重新获取，不误提示绑定手机号错误，不清除用户已输入的验证码。倒计时仅影响重发按钮，验证码有效性仍由服务端决定。
- 新密码为 8–64 位可打印 ASCII，含英文字母、数字与现有允许集合中的特殊符号，无需同时包含大小写。确认密码比较原始值，不 trim。
- 提交失败或结果不确定后清空密码，取消当前验证码复用，显示返回手机验证路径；`reset_unknown` 与 `reset_committed` 明确区别未知结果与已经改密。清除 inherited resendAt，使已消费验证码能重新申请；正常上一步保留原重发期限。
- 各请求防止重复发送，返回/换账号/换手机号/组件销毁后旧响应不能晋级；组件销毁清理验证码与计时器。成功时父页面仅保留账号，明确返回登录，取消自动跳转计时器。

## 分支验证

2026-10-05 作者自检：专项 Node 测试 23/23，分支完整 Node suite 584/584，0 skipped；对 7 个产品文件执行显式 `eslint --no-ignore`，0 errors / 0 warnings。Node 测试执行实际 SFC 脚本方法，HTTP 与计时器受控，并非真实短信或认证全链路。现有依赖复用 candidate node_modules；两边 package-lock SHA-256 相同、Vue/模板编译器均为 2.7.16。

独立审阅 Agent 已报告冻结版离线行为探针 17/17、无新增 blocker；与作者自检分别表述。根 Agent 正在进行浏览器可见核对和后端组合验证。本记录不将其提前记为完成。

真实 SFC + UserLayout 预览已构建，唯一构建提示为现有 Browserslist 数据较旧。预览使用受控本机 HTTP，服务不代理真实 API，不连接真实账号、短信、登录或密码数据库。真实 CAPTCHA/SMS/密码修改全链路与生产部署不属于本分支验收结论。

## 合成浏览器预览

```sh
cd web
node tests/account-recovery-preview/build.cjs /absolute/private/preview-output
python3 tests/account-recovery-preview/server.py --directory /absolute/private/preview-output --port <owned-loopback-port>
```

访问 `http://127.0.0.1:<port>/user/alteration`。顶部“展示”按钮直接选择合成步骤；选择器配置合成短信首次失败、仍有效、验证失败、未知改密结果、已改密但清理失败、HTTP 503、慢响应、图形验证码失败等响应。合成账号为 demo-student，手机号为 13800000000。`/__state` 的请求记录将 password/smscode/captcha 替换为 redacted，不保存或回显敏感值。合成 API 不返回验证码。

私有日志与产物：`.devspace/artifacts/account-recovery-20261005/ui-author/`。产品文件冻结预览 source-manifest SHA-256：`0707ccd4cd7e647b60dfe90260102b51bba5b25f144267ed88e1220c38cd4e66`。

## 集成注意

必须与新的后端契约一起集成。旧 GET 改密已拒绝，前端不能回退 GET；后端码使用独立恢复 namespace，前端不会自行更改有效期或重用旧认证流程。分支 Node suite 只覆盖分支基线，根 Agent 应对最终 candidate 重新执行必需的组合测试和构建，浏览器与人工验收另行记录。

## 合成预览深链接修正

根 Agent 在 `18303/user/alteration` 的实际 CUA 核对发现预览首屏空白，控制台报 `Unexpected token <`；原 `index.html` 使用相对 `preview.js`，深链接将其解析成 `/user/preview.js`，服务回退 HTML。已将构建器 script src 改为绝对 `/preview.js` 并重建同一预览输出。此修正只涉及预览静态入口与本记录，七个产品源码及其文件哈希保持冻结。无需重跑产品 suite；浏览器核对由根 Agent 继续。
