# 生产来源副本匿名只读检查

2026-10-03，root 通知 ready 后执行，脚本现已冻结。最终 **12/12、退出0**：首页/SQL集合、过滤、分页、匿名管理401、3封面实际HTTP字节与磁盘及清单SHA一致；7课程业务表前后摘要不变。完成10个业务GET及3个封面GET，不与用例数混计。

现接口只按show_home=1：5课程中3条展示，del_flag均NULL且API/SQL相同；没有非零样本证明删除态过滤。无登录、Redis验证码/token、学生文件、应用/数据库写操作；仅loopback、有界读取、不跟随重定向、输出聚合。证据不等于角色验收或部署。

首轮严格del_flag=0假设错误，1/5、退出1；次轮6/6后因旧列JSON类型假设停止、退出1；旧12/12仅核磁盘封面，由最终HTTP版取代。历史JSON保留，均不累加。完整哈希及阶段见production-content-verification-summary.json。

脚本SHA-256：`8478bd0093a4a0ca8d984a9a30e1e24eea0e77b9221247f3ce48afc69ccd9446`。

确认专用副本ready后从production-data-fixture工作树执行，输出名必须新建；可用--jar显式提供进程绑定JAR，省略则读取已绑定记录：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 api/dev/verify-production-content.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/prod-fixture-1003 \
  --output /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/prod-fixture-1003/production-content-readonly-recheck.json
```
