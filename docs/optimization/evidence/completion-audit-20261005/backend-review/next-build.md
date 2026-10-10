> 后续状态：根已在另一新私有clean-backend目录完成空缓存构建并报告exit0/158.103s及条目对比。下文是本审阅此前准备但未执行的命令，不需再次运行，也不能当作这次实际执行命令。实际证据以根build.log/审计报告为准。

# 当前候选的新空 Maven cache 复现：准备好的精确命令，尚未执行

当前现有构建使用缓存；这份命令由审阅者只写入私有artifact，未运行。后续执行者需在新的私有目录执行，不能复用/覆盖本文件里的结果目录。任务仅构建，不启动服务、不请求登录、不连接业务数据库/缓存/短信服务。

输入：candidate `06ab2040780f33296e93c97d29d00e80cbcc2f65`，固定既有Java8/Maven工具；完整Git归档不会带入未跟踪output/.playwright-cli、node_modules、已有target、dist或配置秘密。输出和m2在`completion-audit-20261005/maven-repro-01`，必须此前不存在。

```python
from pathlib import Path
import os, subprocess, tarfile, json, hashlib, datetime

workspace = Path('/Users/xuzihan/Documents/Projects/TeachingOpen')
candidate = workspace / '.devspace/worktrees/product-candidate'
commit = '06ab2040780f33296e93c97d29d00e80cbcc2f65'
task_dir = workspace / '.devspace/artifacts/completion-audit-20261005/maven-repro-01'
tools = workspace / '.devspace/backend-runtime/tools'
java_home = tools / 'zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home'
maven = tools / 'apache-maven-3.9.16/bin/mvn'
assert (java_home / 'bin/java').is_file() and maven.is_file()
assert subprocess.check_output(['git', 'rev-parse', commit + '^{commit}'], cwd=candidate).decode().strip() == commit
task_dir.mkdir(mode=0o700)  # 已存在时中止，保留以前的结果
source = task_dir / 'source'
source.mkdir(mode=0o700)
archive = task_dir / 'source.tar'
with archive.open('xb') as output:
    subprocess.run(['git', 'archive', '--format=tar', commit], cwd=candidate, stdout=output, check=True)
with tarfile.open(archive) as frozen:
    frozen.extractall(source, filter='data')
cache = task_dir / 'm2'
cache.mkdir(mode=0o700)  # 刚创建且空，禁止回退到既有m2
api = source / 'api'
settings = api / 'dev/maven-settings.xml'
command = [str(maven), '-B', '-s', str(settings),
           '-Dmaven.repo.local=' + str(cache),
           '-DskipTests=false',
           '-Dtest=AccountRecoveryServiceTest,AccountRecoverySessionTest',
           '-Dsurefire.failIfNoSpecifiedTests=false', 'clean', 'package']
environment = dict(os.environ)
environment['JAVA_HOME'] = str(java_home)
environment['PATH'] = str(java_home / 'bin') + os.pathsep + environment.get('PATH', '')
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
log = task_dir / 'build.log'
with log.open('xb') as output:
    result = subprocess.run(command, cwd=api, env=environment, stdout=output, stderr=subprocess.STDOUT)
receipt = {'source_commit': commit, 'command': command, 'cwd': str(api),
           'java_home': str(java_home), 'new_maven_cache': str(cache),
           'started_at_utc': started, 'finished_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'exit_code': result.returncode, 'services_started': False,
           'settings_sha256': hashlib.sha256(settings.read_bytes()).hexdigest(),
           'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
           'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}
with (task_dir / 'receipt.json').open('x') as output:
    json.dump(receipt, output, ensure_ascii=False, indent=2)
    output.write('\n')
raise SystemExit(result.returncode)
```

精确Maven命令是：`mvn -B -s <归档源码>/api/dev/maven-settings.xml -Dmaven.repo.local=<全新m2> -DskipTests=false -Dtest=AccountRecoveryServiceTest,AccountRecoverySessionTest -Dsurefire.failIfNoSpecifiedTests=false clean package`。两组已有JUnit需要在日志/XML中实查30 tests/0失败/0错误/0跳过；failIfNoSpecifiedTests=false仅让没有该类的base-common模块不因筛选而失败，不应据此把“0 tests”误记为执行30个。

现有settings为`C/api/dev/maven-settings.xml`（本报告C的候选路径）：mirror `central-https`，URL `https://repo.maven.apache.org/maven2`，mirrorOf `*,!jeecg,!jeecg-snapshots`；没有server凭据。普通依赖/插件由Maven Central HTTPS解析；保留的项目官方仓库是`https://maven.jeecg.org/nexus/content/repositories/jeecg`，插件snapshots例外为`https://oss.sonatype.org/content/repositories/snapshots`。POM中的Aliyun public声明被该mirror替换；不能在报告中误写实际全部从Aliyun下载。是否仍能解析只由新缓存这次真实结果决定，本文未发请求。

现有工具官方来源与摘要在归档内`api/dev/toolchain.json`：Zulu8u504归档SHA256 `58bb3c08f2aa63d9743cf31899fa4b8c6c9effefce9479e7288c26621c3bb21b`，Maven3.9.16归档SHA256 `80ffca22aed9e8b9713a232f3394fd81d7f20322df75efdb2b047dbd3e3a23bb`。复用这些已核查工具，不修改全局配置；如执行者发现文件缺失/不同，先报告真实限制，不擅自换版本。

后续证据最少包括工具实际版本、命令和真实退出状态、m2此前为空、归档commit、settings摘要、Reactor各模块结果、下载失败/成功实际仓库、JAR摘要和内嵌依赖清单。若失败，保留日志和新目录，不混成“已通过”；不为刷绿关闭tests或改仓库来源。日志仅限构建，不打印任何本机运行环境配置/凭据。

当前正式冻结JAR为`67568eea…`。新构建的整体ZIP摘要可能因时间戳或打包元数据不同，不能仅据JAR哈希不同判业务源码漂移；应检查1,030个源码/POM输入、208外部库与解包class/resource。新构建不会替换正式候选产物；无需启动它或重复API/浏览器矩阵来证明依赖安装成功。
