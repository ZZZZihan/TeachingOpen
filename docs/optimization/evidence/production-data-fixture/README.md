# 脱敏副本工具的安全测试证据

本目录保存默认纯测试的完整原始输出与聚合结果，不包含原始 SQL、匿名账户清单、口令、资源路径清单、课程正文或原素材文件名。工具源码仍为收尾冻结版本，本次只补证据。

## 已落盘的原始输出

- `pure-tool-tests.log`：2026-10-03 重新执行默认工具测试的完整 stdout/stderr。22 项测试，21 项通过；专用 MySQL 项因没有显式专用环境参数而跳过。
- `pure-dev-suite.log`：同日重新执行 `api/dev` 默认全集的完整 stdout/stderr。64 项测试，63 项通过；同一专用 MySQL 项跳过。
- `summary.json`：上述命令、UTC 起止时间、退出码、数量、日志 SHA-256、Python 版本、仓库 HEAD 和当前工具文件 SHA-256，以及历史执行记录。

本次执行前明确移除了 `TEACHING_SNAPSHOT_TEST_RUNTIME` 环境变量，没有操作已经运行的副本数据库，也没有重跑真实 MySQL 用例。默认测试包含受控 mock/临时 HTTP 服务用例，不是生产或运行中副本的检查。

可复现默认测试命令如下；真实 MySQL 项保持跳过：

```sh
env -u TEACHING_SNAPSHOT_TEST_RUNTIME python3 -m unittest discover \
  -s api/dev -p 'test_production_fixture.py' -v
env -u TEACHING_SNAPSHOT_TEST_RUNTIME python3 -m unittest discover \
  -s api/dev -p 'test_*.py' -v
```

## 真实 MySQL 用例的历史执行记录

在首次应用启动之前，工具作者显式指定专用新副本环境，执行过当时的 16 项工具测试，全部通过，没有跳过。`unittest` 输出为 `Ran 16 tests in 12.145s`、`OK`，命令退出码为 0。真实用例验证 Unicode、单引号、反斜杠、多行、控制字符与二进制字节的 HEX 往返；它创建自己的探针表，结束后删除，再执行完整初始数据库/资产基线验证。

那次输出仅保留于本 Codex 子任务的会话工具结果，没有现成原始日志文件。可追溯执行标识为 `exec_command` session **96963**，完成输出由同一 session 的 `write_stdin` 返回。`summary.json` 中这部分是根据已见工具结果写下的执行记录，**不是重建的原始日志，也不是新一次独立重放**。当时完整源码的字节摘要未另存；当前文件摘要只绑定本目录重新保存的默认测试输出。

此前第一次 64 项默认全集的输出同样仅在会话中，session **5967**，结果为 `Ran 64 tests in 1.211s`、`OK (skipped=1)`；本目录的 `pure-dev-suite.log` 来自后续明确允许的默认纯测试重跑，不冒充该次原始输出。

真实 MySQL 用例没有在本证据收尾中再次运行。应用运行会产生 Quartz/审计等正常数据变化；不能为补原始日志在运行中副本再建表，或把完整初始基线不相等当成服务异常。匿名 API、页面、实际健康及用户验收另有独立结果，不由这组单测代替。
