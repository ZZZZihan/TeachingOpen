# 注册数据备份与线上一致性

2026-10-09 在已上线的阿里云环境落实。备份工具不启动或重启正式应用，不向正式数据库导入数据，不启用已取消的流量规则。

## 当前配置

- 目标：北京 ECS `i-2ze2jqs9tbjygwhvnepr`，Workbench `teachingopen` profile，网站 `http://101.201.225.116`。
- 数据库：`teachingopen`；备份 `/srv/teachingopen/backups`，目录 0700，数据与配置文件 0600，不在网站公开目录。
- 每日北京时间 **00:20、06:20、12:20、18:20** 自动执行 `teachingopen-backup.timer`。服务器开机后补执行错过的任务；不依赖本机 Codex 是否在线。
- 每份备份均包含 MySQL 事务快照、上传文件、应用配置及服务配置。每份数据库都先实际导入新建隔离库、检查注册数据关联，成功后才原子发布完成目录及 `latest.json`。
- 最近 7 天的全部备份保留；7 至 30 天每个 UTC 日保留最新一份；即使长时间停机也至少保留最后两份成功备份。只有新备份完整成功后才删除本工具创建的过期目录，失败、无关和不完整目录不自动删除。
- 上传目录使用 `rsync --link-dest` 复用旧备份中的相同文件。首份 297 个文件约 5.94 GB，后续未改变的文件不重复占用文件内容空间。每份都有完整 SHA256 清单。
- 每天北京时间 **03:35**，`teachingopen-backup-verify.timer` 完整核验最新备份的文件、配置、数据库指纹，再做一次隔离数据库恢复。
- 磁盘空余低于 4 GiB 时拒绝新增备份并记录失败。不会为腾空间删除最后可用备份或正式文件。

服务器实际安装：`/usr/local/sbin/teachingopen-backup.py`、私有配置 `/etc/teachingopen-backup.json` 和本目录四个 systemd 单元。配置由 `teachingopen-backup.example.json` 结合真实路径生成；凭据仍在服务器原私有配置中，Git 只保存文件路径。

## 检查与手动运行

在目标服务器读取状态：

```sh
systemctl list-timers 'teachingopen-backup*'
systemctl show teachingopen-backup.service teachingopen-backup-verify.service -p Id -p Result -p ExecMainStatus
python3 -c 'import json,pathlib; p=pathlib.Path("/srv/teachingopen/backups"); print(json.dumps({n:json.loads((p/n).read_text()) for n in ("last-backup.json","last-verify.json","latest.json")}))'
```

手动启动已安装的备份或恢复核验（不重启网站）：

```sh
systemctl start teachingopen-backup.service
systemctl start teachingopen-backup-verify.service
```

两个服务使用同一备份锁。不要同时手动运行；如果锁冲突会记录失败，等待当前任务完成后重试对应服务。失败记录只有错误类型，不回显可能包含用户数据的数据库诊断。`.partial-*` 是未完成的私有归档，需要检查，不能当成成功备份使用。

隔离恢复使用随机的 `teachingopen_restore_*` 数据库和只拥有该库权限的临时账号；即使 SQL 中意外出现其他数据库引用，也不能写入正式库。结束时仅删除本次成功创建的随机隔离库和账号。不会自动恢复或覆盖正式库。

## 异机数据库副本和巡检

本机使用已有 Workbench 配置，不复制访问凭据：

```sh
python3 deploy/pull_database_backup.py \
  --workbench /Users/xuzihan/.local/bin/workbench \
  --instance i-2ze2jqs9tbjygwhvnepr \
  --profile teachingopen --region cn-beijing \
  --destination /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backups/cloud-database
```

该命令检查服务、两个定时器和备份新鲜度，将最新完整 `database.sql.gz` 下载到本机私有目录，验证 SHA256 后才改为最终文件名。它不修改线上数据库。已有相同副本会复核指纹，不重复下载。备份超过 8 小时、每日核验超过 28 小时、定时器停用、最近运行失败或应用服务停止都会报错。首次异机副本已在本机 MySQL 实际恢复，并用对应应用完成注册/登录检查。

本聊天的“TeachingOpen 注册与备份巡检”每 6 小时调用该命令。没有异常或有意义的变化时保持安静，只报告失败、漂移或需要用户处理的事项。该异机复制依赖本机在线和 Workbench 网络可用；服务器定时备份独立执行。没有启用邮件、流量轮询或流量暂停规则。

注册只读检查可复用 `scheduled_backup.health(config, 'teachingopen')`，其检查用户、资料和角色关联，身份值、姓名/学校/手机号/口令字段及 utf8mb4。还应读取 `sys_config` 的 `allowReg`、检查 `sys_user` 的手机号及用户名唯一索引和 `sys_role.role_code='student'`。只返回计数/布尔值，不输出姓名、手机号、密码、令牌或 SQL 数据。

## 线上与本地一致性的边界

本轮对实际运行的云端与本机候选核对：后端 JAR 相同、4,902 个前端文件相同；70 张表的列定义和索引定义指纹相同（只归一化 MySQL 整数显示宽度）。线上 MySQL 为 8.0，原本机为 8.4，不能称为数据库软件版本完全相同。云端备份已在本机 8.4 恢复并完成相同的 32 项注册检查。

真实线上用户数据以线上为准，本机的合成用户不回写线上。线上数据库副本只保存到私有备份和任务隔离验证库；不将用户资料提交 Git，不通过双向覆盖来制造“数据一致”。后续发布需比对实际运行包和对应的明确数据库升级；备份巡检不会自动部署其他尚未上线的 PR。

`verify_registration.py` 只能用于保留端口 8082/18259 和 `teachingopen_check_*` 隔离库。它会实际新增 4 个合成用户、注入资料写入失败、检验事务回滚，再检验恢复注册；不用于正式库。测试成功不等于人工验收。

## 恢复能力的限制

- MySQL 所有表必须是 InnoDB；导出采用 `--single-transaction --quick --skip-lock-tables`。备份窗口避免并发 DDL。数据库与文件系统的在线备份不是同一个原子事务；文件在备份期间变化仍可能需要检查。参见 [MySQL 官方 mysqldump 文档](https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html)。
- 服务器快照有全部上传文件和私有运行配置；定期异机复制目前覆盖数据库。不要把数据库异机副本称为所有新附件的异机灾备。
- Redis 会话、验证码、缓存和 Scratch 云变量不在这套 MySQL/上传文件备份中，不自动恢复旧登录会话。本任务不将它表述为整个 Redis 的灾备。
- 定时器启用和手动成功运行已核查；刚创建时不能声称已观察到未来多个定时周期。没有执行整机重启或覆盖正式库的恢复演练。

## 复测

```sh
python3 -m unittest discover -s deploy -p 'test_*backup*.py' -v
python3 -m py_compile deploy/scheduled_backup.py deploy/pull_database_backup.py deploy/verify_registration.py
```

18 项工具测试覆盖保留策略、路径与权限、损坏备份、恢复账号权限、失败后清理、非 InnoDB、导出失败、带配置文件的完整快照发布/发现/核验，以及 Workbench 空响应、错误响应的一次只读重试。首次线上运行曾暴露配置文件循环覆盖归档名的问题，已修复并新增端到端回归测试；首份数据保留并更正目录名，第二份由最终脚本正常生成并恢复成功。发布的验证结论使用修复后的实际结果。
