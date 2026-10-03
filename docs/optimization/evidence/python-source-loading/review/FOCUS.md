# PR52 基线源码加载链审查关注点

只读准备，固定基线 f906f8e782795ddd670725e85ffa4ea1756b665c；未审 mutable 实现 diff，未改产品、启动服务或跑测试。基线文件 SHA-256、原文与 bundle 定位摘录相邻。后续仅在 root 通知冻结后审最终 diff。

基线 index/player 都加载 appPlayer.js 与 app.js。app entry NHnr 挂 #app；player entry RQgh 挂 #player。每页仅存在自己的容器，另一个 entry 仍会创建组件/执行created/mounted，因而产生无需要的编辑器和源码下载链。app 在 TeachingPython 存在时 created.nextTick → TeachingPython.mount；不在时走url或defaultPython下载。player mounted仅在url存在时downloadFile。删除每页多余app脚本是具体修复，保留vendor/manifest与Worker独立旧模块loader。

默认页面明确硬编码editorType='ace'；CodeMirror是现有可选组件，不将其300ms问题说成当前默认页面已实测失败。两bundle共有Ace外层setCodeContent仅修改wrapper.code；vendor模块o4sT通过异步Vue value watch执行session.setValue，并维护contentBackup。CodeMirror外层setCodeContent在300ms后才coder.setValue，代码没有可取消timer、没有value watcher；getCodeContent返回wrapper.code，由coder change事件更新和emit input。

首要审查点：

1. **ready必须覆盖真实apply。** baseline persistence.load同步调用options.apply，紧接ready=true/busy=false；bridge apply仅host.setCode。新await apply需兼容原同步返回undefined；失败不能ready。等待Ace.editor/CodeMirror.coder应有界，跨nextTick后核验真实getter、host.code和wrapper.code一致。仅检查host.code不能证明可见/可执行内容已落入真实编辑器。
2. **同内容与空文件不能绕过仍待执行setter。** 若目标当前已等于getter，单纯等相等会立即resolve，但原300ms任务仍会在用户编辑后覆盖输入。作者拟把两个JCode setter精确改为同步赋值+coder.setValue，再等真实rawready后apply，针对该确定机制是合适的最小补救。需同时确认正常setCode和openFile继续触发input/hasCode、没有遗留的其它同路径timer。
3. **换行规范化。** vendor CodeMirror doc.setValue通过splitLines保存各行；getValue使用lineSeparator默认'\n'重新join。因此CRLF/混合换行原始文件不必等于实际getter文本。新严格getValue===原始code等待可能超时；savedSnapshot保留原始code可能加载完成即dirty。应以实际规范化内容同步核验/host/ref与savedSnapshot，保持保存快照和getCode一致。Ace也有contentBackup/watch链，应核验跨nextTick后的最终内容。
4. **loading期间不允许用户内容与迟到apply竞争。** baseline bridge update只给Ace.editor setReadOnly；Coder需要setOption('readOnly',...)。mounted前无raw实例时不能误解禁；首次实例ready后仍维持loading/busy。运行按钮UI和runit方法都需按ready/busy守门；baseline只有提交/名称/open的部分守门，Run未守门。player新sourceReady/sourceBusy初始反应式状态也需一致。
5. **离开与generation。** await options.apply后应再校验load turn与live host，防被销毁/替换的旧host将ready/快照写到新会话。持久化beforeunload的busy必须包括真实编辑器等待与apply阶段，initialized/savedSnapshot在成功后设置。cancel/dispose如果返回false不能被await视为成功。超时/error→retry只能有一次当前apply；旧响应或旧等待不得覆盖重试后的用户内容。
6. **workId为保存身份来源。** 保留baseline优先info(workId)→workFileKey_url、type4校验，并恢复courseId/additionalId/departId；显式resetTemplate=1仍为现有例外。完整文件URL、签名query、百分号和literal+继续由现有query解析保持；文件host无X-Access-Token/JWT；身份请求仍走同源API。sourceBusy/sourceReady不得替代或重置state.workId，load-error/retry后submit仍更新同份作品。
7. **单entry不会改Worker/Python2。** app/appPlayer默认入口各独立，Worker的runner-loader仍仅注册模块并取rONZ+21Q0，不启动Vue entry。最终diff应限定Vue组件挂载、源码就绪和必要setter，确保旧引擎/输入/turtle/Worker协议不被顺带重写。

冻结后定向重点：快响应早于Ace初始化；同code重试/空文件；CRLF/mixed newline；加载拒绝后retry；等待应用时销毁host/旧响应迟到；workId恢复元数据与提交id；readonly/Run解禁时getCode与raw一致。以上是源码确认的机制或需核验的边界，不是对尚未冻结实现的已确认缺陷。
