# ECS 每月公网出流量阶梯限速

本文是通用部署与维护说明，不包含具体账号、实例或生产凭据。部署状态以对应环境的运维记录为准，不能从仓库文件存在推断已启用。下方安装和管理命令均在目标 ECS 上执行。

## 控制规则与适用范围

按北京时间的每个自然月累计公网出流量，以十进制 GB 计量（1 GB = 1,000,000,000 字节）。累计达到 150 GB 后将公网出带宽峰值降至 5 Mbps，达到 200 GB 后降至 1 Mbps；超额后继续按使用流量付费。约定正常带宽由 `baseline_mbps` 配置，当前方案为 100 Mbps。下月先补齐新月截至采集截止点的分钟数据，再依据新月累计流量恢复正常带宽或应用已经达到的阶梯。

该程序只适用于 VPC ECS 固定公网 IP、`PayByTraffic` 计费方式。每次运行都核对实例、地域、公网 IP、计费方式和实际出带宽；绑定了 EIP、身份变化、出带宽为 0 或实际带宽与账本不一致时，需要人工核对。公网带宽 API 仅设置出带宽峰值，不传转换计费方式的参数，参见阿里云 [ModifyInstanceNetworkSpec](https://help.aliyun.com/zh/ecs/developer-reference/api-ecs-2014-05-26-modifyinstancenetworkspec)。

同一管理月份内只降不升。提高阈值或调整正常带宽不会自动撤销当月已经生效的限速。跨月恢复要求分钟覆盖完整、实际带宽仍与程序最后确认值一致；出现缺口时阻止升速，但已采集流量达到阶梯仍可降速。外部带宽修改会阻止自动写入并报告冲突。服务器停机期间控制程序也停机；恢复后查询已有监控，真实停止实例期间可能没有分钟数据，永久缺口按下方“停机缺口核对”处理，不能视为自动补齐。

流量来源为 CloudMonitor 的 `acs_ecs_dashboard / VPC_PublicIP_InternetOutRate`，查询周期为 60 秒，维度为实例 ID 和固定公网 IP。将每分钟 `Average`（bit/s）乘以 `60 / 8` 转为字节，分钟样本按时间戳写入 SQLite，重复查询覆盖同一分钟并重新累计。它是限速判断使用的监控估算；阿里云最终计费流量仍以账单为准。指标说明见 [ECS 基础监控](https://help.aliyun.com/zh/cms/cloudmonitor-1-0/user-guide/overview-of-basic-and-operating-system-monitoring)，账单差异说明见 [计费常见问题](https://help.aliyun.com/zh/user-center/support/billing-faqs)。

## 文件与依赖

| 仓库文件 | 服务器位置 | 用途 |
| --- | --- | --- |
| `deploy/traffic_control.py` | `/usr/local/lib/teachingopen-traffic-control/traffic_control.py` | Python 标准库控制程序 |
| `deploy/teachingopen-traffic-control.example.json` | `/etc/teachingopen-traffic-control.json` | 目标实例、规则和开关 |
| `deploy/teachingopen-traffic-control.service` | `/etc/systemd/system/teachingopen-traffic-control.service` | 单次采集与控制 |
| `deploy/teachingopen-traffic-control.timer` | `/etc/systemd/system/teachingopen-traffic-control.timer` | 每分钟触发 |
| 程序生成 | `/var/lib/teachingopen-traffic-control/state.sqlite3` | 持久分钟样本、确认带宽、待回读意图与停机核对记录 |
| 程序生成 | `/var/lib/teachingopen-traffic-control/state.sqlite3.lock` | 防止手动运行与 timer 并发 |

服务器需要 Linux、systemd、Python 3.10 或以上、可用的 `Asia/Shanghai` 时区数据，以及访问实例元数据、ECS 和 CloudMonitor API 的网络。无需安装 Python 第三方包。service 以 root 运行，配置文件与状态目录仅 root 可读写；`StateDirectory` 是 `ProtectSystem=strict` 下允许程序写入的位置。

timer 每分钟触发，最多额外随机延迟 5 秒。`Persistent=true` 会在服务器恢复或 timer 再次启用时补触发一次错过的日历任务；历史流量由程序查询补齐。它不会逐次重放所有错过的分钟执行。systemd 不会为已经运行的同一 service 再启动一个实例，程序内部还使用 `flock`，参见 [systemd.timer 官方定义](https://github.com/systemd/systemd/blob/main/man/systemd.timer.xml)。单次 service 超时为 120 秒；已成功提交的样本保留，后续执行继续补齐。

## 实例 RAM 角色

创建云服务角色 `TeachingOpenTrafficControl`，信任主体选择云服务器 ECS。信任策略为：

```json
{
  "Version": "1",
  "Statement": [{
    "Effect": "Allow",
    "Action": "sts:AssumeRole",
    "Principal": {"Service": ["ecs.aliyuncs.com"]}
  }]
}
```

为角色附加如下自定义权限策略，替换 `<ACCOUNT_ID>`、`<REGION>` 和 `<INSTANCE_ID>`。运行角色仅需查询分钟监控、读取目标实例与修改该实例出带宽，不需要创建角色、管理权限或 OSS 权限。

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "cms:QueryMetricList",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["ecs:DescribeInstances", "ecs:ModifyInstanceNetworkSpec"],
      "Resource": "acs:ecs:<REGION>:<ACCOUNT_ID>:instance/<INSTANCE_ID>"
    }
  ]
}
```

在 ECS 控制台的实例详情中，通过实例设置里的“授予/收回 RAM 角色”绑定角色。API 操作者需要 `ecs:AttachInstanceRamRole` 与 `ram:PassRole`；运行角色本身无需这些权限。一个实例只能绑定一个实例角色，已有角色时先检查现有用途，不直接替换。操作入口和信任主体见 [授予实例 RAM 角色](https://help.aliyun.com/zh/ecs/user-guide/attach-an-instance-ram-role-to-an-ecs-instance)，API 格式见 [AttachInstanceRamRole](https://help.aliyun.com/zh/ecs/developer-reference/api-ecs-2014-05-26-attachinstanceramrole)。

程序在每次执行时通过 IMDSv2 获取短期凭证，不读取本机 AccessKey 配置，也不把凭证保存到配置、SQLite 或日志。需允许访问 `100.100.100.200` 的元数据服务。不要把获取短期凭证的响应粘贴到运维记录。元数据方式见 [查看实例元数据](https://help.aliyun.com/zh/ecs/user-guide/view-instance-metadata/)。

## 安装与首次补齐

先确认固定公网 IP、计费方式、正常带宽和实例真实创建时间；`created_at` 使用带时区的 ISO 8601 时间。实例在本月创建时，只需从创建时间开始补齐。示例中的实例 ID、IP 和创建时间都是占位内容，必须替换。首次安装保持 `enabled=false`。

在目标服务器的仓库目录执行：

```sh
sudo install -d -m 0755 /usr/local/lib/teachingopen-traffic-control
sudo install -m 0755 deploy/traffic_control.py /usr/local/lib/teachingopen-traffic-control/traffic_control.py
sudo install -m 0600 deploy/teachingopen-traffic-control.example.json /etc/teachingopen-traffic-control.json
sudo install -d -m 0700 /var/lib/teachingopen-traffic-control
sudo install -m 0644 deploy/teachingopen-traffic-control.service /etc/systemd/system/teachingopen-traffic-control.service
sudo install -m 0644 deploy/teachingopen-traffic-control.timer /etc/systemd/system/teachingopen-traffic-control.timer
sudoedit /etc/teachingopen-traffic-control.json
sudo /usr/bin/python3 -m json.tool /etc/teachingopen-traffic-control.json
sudo systemd-analyze verify /etc/systemd/system/teachingopen-traffic-control.service /etc/systemd/system/teachingopen-traffic-control.timer
sudo systemctl daemon-reload
```

仅首次明确建立新账本时使用 `--initialize`：

```sh
sudo /usr/bin/python3 /usr/local/lib/teachingopen-traffic-control/traffic_control.py --config /etc/teachingopen-traffic-control.json --initialize --dry-run
```

普通执行不会自动新建缺失账本。`--dry-run` 不写云带宽，但会采集数据并保存本地样本、账本与报告。首次补齐可能需要多次执行；后续用以下命令继续查询：

```sh
sudo /usr/bin/python3 /usr/local/lib/teachingopen-traffic-control/traffic_control.py --config /etc/teachingopen-traffic-control.json --dry-run
```

检查 JSON 输出：`coverage_complete=true`、`missing_minutes=0`、`status=ok`，并核对 `observed_gb`、`through_utc`、`current_mbps` 和 `target_mbps`。初次实际带宽应与配置的 `baseline_mbps` 一致。缺失数据不视为 0；程序保留 `incomplete` 并重试。CloudMonitor 60 秒数据保存 31 天，每次最多取 1,440 点并使用 `NextToken` 翻页，参见 [DescribeMetricList](https://help.aliyun.com/zh/cms/cloudmonitor-1-0/developer-reference/api-cms-2019-01-01-describemetriclist)。超出保留期的缺口需要另行核对，不能删除账本后按 0 开始。

默认只累计到当前时间前 300 秒的完整分钟；每次刷新最近 30 分钟、补缺，并循环复查更早的一天。监控存在延迟，达到阈值后到下一次成功控制之间可能产生额外流量，300 秒等待不代表阿里云承诺的最大延迟。

## 启用与部署验收

补齐完成后，将配置的 `enabled` 改为 `true`。配置每次运行重新读取；写入前再次核对文件，执行中配置已变化会拒绝本次写入并等下次重算，不必为配置内容执行 `daemon-reload`。unit 文件变更才需要重新安装和 `daemon-reload`。

部署验收先运行一次 `--dry-run`，检查当前目标是否符合本次实际授权。若要验证实例角色的写权限且保持当前正常带宽，先确认 `current_mbps` 与 `target_mbps` 相同，再执行：

```sh
sudo /usr/bin/python3 /usr/local/lib/teachingopen-traffic-control/traffic_control.py --config /etc/teachingopen-traffic-control.json --verify-write
```

`--verify-write` 要求 `enabled=true` 且不带 `--dry-run`。它先采集并演练，只有覆盖完整、无冲突且当前带宽等于计算目标时，才把当前实际出带宽写回同一数值并立即回读；需要调整带宽的场景会拒绝验收写入。成功报告包含 `action=verified-current-bandwidth` 和 `same_bandwidth_write_verified=true`。它验证真实 API 写权限与回读，不代表 5 Mbps 或 1 Mbps 的现场吞吐已经测量。不得为验收把生产阈值改成假值来强制降速。

安装验收通过后启动单次 service，再启用 timer：

```sh
sudo systemctl start teachingopen-traffic-control.service
sudo systemctl enable --now teachingopen-traffic-control.timer
sudo systemctl list-timers teachingopen-traffic-control.timer --all
sudo journalctl -u teachingopen-traffic-control.service -n 50 --no-pager
```

手动执行成功与 timer 实际执行是两项证据。还需在下一次触发后检查日志中的新 `checked_at`，并读取 ECS 实际出带宽。程序输出 `status=ok` 时返回 0，`incomplete`、`conflict` 或待回读返回 2，异常返回 1；systemd 会将非零返回显示为失败，需结合 JSON 详情判断原因。

## 暂停、修改和冲突处理

- **暂停控制：** 将 `enabled` 改为 `false`。后续执行停止写云带宽，继续采集并保存账本，当前已生效带宽保持。输出 `action=paused`。已开始的执行会在带宽 API 调用前复核配置；已发往云端的请求仍可能完成。
- **停止定时采集：** `sudo systemctl disable --now teachingopen-traffic-control.timer`。已启动的 service 可能继续完成，检查其状态后再做需要独占的维护。重新启用前确认时间、账本和配置。
- **调整规则：** `tiers` 是按阈值递增、带宽递减的数组，示例为 `[[150,5],[200,1]]`。配置必须保持 JSON 有效；编辑后先执行 `--dry-run` 查看目标。同月只降不升的约束仍然有效。
- **外部带宽变化或正常带宽修改：** 先设置 `enabled=false`，核对谁进行了修改、实际带宽和目标规则。确认要把同一实例的当前带宽接管为新的已确认值后，执行下面的 `--adopt-current --dry-run`，程序要求暂停和 dry-run。它保留分钟样本，登记配置中的新 `baseline_mbps`，清除已核对的冲突与待回读意图，并在 `bandwidth_adoptions` 保存原确认值、原意图、时间和依据；需要已有且身份一致的账本。若仍有未决请求，且当前值还不等于其目标，必须先核实该请求已明确失败或终结、不会晚到生效，再用 `--evidence '<云端请求结果或运维记录引用>'` 登记依据。当前值仍等于旧确认值不能证明旧请求失败。核对输出后再决定启用。它不适用于换实例、换 IP 或丢失账本。
- **账本缺失或损坏：** 保持暂停，恢复经核验的账本或明确重新初始化并补齐完整历史。普通运行拒绝静默生成空账本；已有分钟样本或停机核对记录但缺少资源/控制状态时，包括 `--initialize` 在内均拒绝沿用这些数据，需要从有效备份恢复或另行核对。不要删除数据库来清除限速或冲突。
- **跨月恢复：** 无需定时手动改回 100 Mbps；程序在新月分钟数据完整且不存在冲突后恢复配置的正常带宽，或按新月已到达阶梯设置更低目标。月初等待数据、断网或停机可能延后恢复，应检查 `through_utc` 和覆盖情况。

```sh
sudo /usr/bin/python3 /usr/local/lib/teachingopen-traffic-control/traffic_control.py --config /etc/teachingopen-traffic-control.json --adopt-current --dry-run
```

`pending` 表示已持久记录写入意图，可能正在等待云端回读。下次执行会先核对实际值再继续，遇到不同于已确认值和待应用值的带宽则报告冲突。跨月或目标档位变化时，未决旧意图保留并输出 `status=pending`、`action=awaiting-prior-write`，不会因为新目标等于当前值而清除，也不会用新的请求覆盖旧意图。旧目标回读确认后，重新依据当前月数据判断；一直没有确定结果时应核对云端请求结果，按上述显式接管流程登记依据。不要用接管命令掩盖尚未查明的外部修改。

### 停机缺口核对

监控空响应、连接失败、程序停机、操作系统重启或某分钟没有点，都不足以证明该分钟流量为 0。程序不会据此自动生成零样本。只有已经通过 ECS 停止/启动事件、实例状态变更记录等权威来源核实“整个分钟内实例处于停止状态且没有公网出流量”的区间，才可由操作者登记；证据应保存在对应环境运维记录中，并包含资源身份、停止/启动时间和核查结论。程序记录引用，无法替代操作者对引用内容真实性和零使用结论的核验。

先设置 `enabled=false` 并暂停 timer，在现有有效账本上执行下方命令。`START` 和 `END` 使用带时区 ISO 8601 时间且必须对齐整分钟，表示停止区间 `[START, END)`；只覆盖起点之后、终点之前结束的完整分钟。若实际停止或启动发生在分钟中间，应将开始向后取整、结束向前取整，边缘不完整分钟继续保留缺口，不能把它们归零。区间必须在实例创建之后、当前采集截止点之前。

```sh
sudo /usr/bin/python3 /usr/local/lib/teachingopen-traffic-control/traffic_control.py \
  --config /etc/teachingopen-traffic-control.json --dry-run \
  --record-stopped-interval '<START_WITH_TIMEZONE>' '<END_WITH_TIMEZONE>' \
  --evidence '<ECS 停止/启动事件或核验记录引用>'
```

此命令要求 `enabled=false`、`--dry-run`、非空依据和已有资源一致的账本，不能与初始化、接管或验收写入混用。重叠记录、已有非零样本、未来或不完整分钟均拒绝。它将区间、资源身份、依据和登记时间写入独立 `stopped_intervals` 表，原始云监控样本保留；后续若查询到区间内非零流量，程序报错并停止本轮带宽写入，需要重新核对，不能静默忽略矛盾。

输出增加 `reconciled_zero_minutes`（本轮由核对记录补足、尚无云样本的分钟数）和 `stopped_interval_reviews`（相关区间及依据）。核对总量、剩余 `missing_minutes`、覆盖情况和目标后再恢复配置和 timer。未核实的缺口仍阻止升速；如果边缘分钟或其他永久缺口无法补齐，应继续保持当前限制并核查，不能使用停机记录掩盖未知使用量。账本升级仅增加此审计表，保留已有分钟样本和控制状态。

检查服务、日志与下一次触发：

```sh
sudo systemctl status teachingopen-traffic-control.service teachingopen-traffic-control.timer --no-pager
sudo systemctl show teachingopen-traffic-control.service -p Result -p ExecMainStatus -p ExecMainStartTimestamp
sudo journalctl -u teachingopen-traffic-control.service --since today --no-pager
sudo systemctl list-timers teachingopen-traffic-control.timer --all
```

备份 SQLite 时使用 SQLite 的一致性备份接口，或确认 timer 已停用且 service、手动进程均已退出后备份；运行中的数据库不要直接复制单个主文件。恢复前保留原损坏文件供核对。数据库的原子提交仅保护本地状态，云端写入仍须通过回读确认，参见 [SQLite 在线备份](https://sqlite.org/backup.html)。

## 与既有守护及记录的关系

本方案不修改、启用或复用旧的 250 GB guard；相关历史脚本与旧记录保留。部署前检查目标上是否已有其他自动修改同一 ECS 带宽的任务，出现重叠时先明确管理归属，避免相互覆盖。此方案依靠目标 ECS 自身的 timer，不依赖本机电脑周期查询。

部署完成后，在对应环境的交接记录中追加实际证据，至少记录：

- 部署时间、服务器与目标资源核对结果；已绑定角色名称与实际权限核验结果。普通记录不包含 AccessKey、SecurityToken 或元数据凭证响应。
- 已安装程序及配置的 SHA-256、Python 版本、systemd unit 校验结果；配置记录需确认不包含任何长期密钥。
- 初始历史补齐报告中的月份、截止时间、累计 GB、缺失分钟与当前/目标带宽。
- 同带宽写入回读结果、单次 service 结果、后续 timer 触发时间及 ECS 实际带宽回读。
- 5/1 Mbps 阶梯、跨月恢复与停机恢复分别说明实际运行、隔离测试或尚未观察，不把当前同带宽验收当成全部行为现场验收。

实际环境的实例标识、累计量、权限和启用回执记录在环境自己的交接文档中，不提交到通用仓库。
