# 未登录和失效凭证返回明确的 401

日期：2026-10-02。基于 [隔离环境 PR #4](https://github.com/ZZZZihan/TeachingOpen/pull/4)，只修改认证失败的响应契约。

## 问题与结果

真实请求受保护的“我的课程”接口时，缺少、空白、格式错误或已退出的凭证原来都会触发 HTTP 500。浏览器因此把需要重新登录的情况当成服务故障。

JwtFilter 现在捕获 Shiro 的认证失败，停止过滤链并返回 HTTP 401 和 UTF-8 JSON（`success: false`、`code: 401`、明确的重新登录提示）。没有扩大匿名访问范围。一般运行异常不在本次捕获范围内。

## 验证

同一独立合成数据库和 Redis，分别启动 #4 的 JAR 和本次干净构建的 JAR，实际执行验证码生成、登录和退出。检查工具先核对数据库、Redis、启动命令与 JAR 摘要，凭据仅在内存和私有环境配置中使用，不写入证据。

| 路径 | 修复前 | 修复后 |
| --- | --- | --- |
| 我的课程：缺少 / 空白 / 格式错误凭证 | 各为 500 | 各为 401，JSON 结构正确 |
| 已登录学生访问我的课程 | 200 | 200 |
| 退出后使用原凭证 | 500 | 401，JSON 结构正确 |
| 匿名查看公开课程 | 200 | 200 |
| OPTIONS 预检 | 200 | 200 |

[修复前证据](evidence/auth-status-before.json) 和 [修复后证据](evidence/auth-status-after.json) 各记录 7/7 个符合预期的行为；前者的预期是复现原有 500，不能解释为旧版没有缺陷。[构建与源码摘要](evidence/auth-status-build.json) 对应本次三模块干净构建。父 POM 跳过 Java 单元测试，这些结果是实际 HTTP 检查和构建，不是 Java 单测或完整业务验收。

在按 [本地运行说明](../../api/BUILDING.md) 启动本分支后，从仓库根目录执行：

```sh
python3 api/dev/verify-auth-status.py --runtime /path/to/TeachingOpen/.devspace/backend-runtime-pr4 --output /tmp/auth-status-after.json
```

对照旧版时使用 `--jar /path/to/old/api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar --expect-legacy`，并先启动该旧版。检查不会以新的源码代替运行中的 JAR。

本 PR 未验证第三方登录、Redis/数据库故障、完整浏览器会话恢复或角色/附件权限；这些仍在后续计划中。无数据结构变更；回退 JwtFilter 即恢复原来的 500 行为，运行环境和数据无需迁移。
