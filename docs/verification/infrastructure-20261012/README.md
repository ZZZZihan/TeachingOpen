# H-01: live dev authorization for infrastructure administration

Baseline: `a3f4e10ceafcbe405093a3abe06a20225a17d3f6`, which already includes the separate Nginx candidate-pin fix. Original Pro finding H-01 was reviewed at `2cbd9c4713a6a7ec830fd6c5b30a02a2a98aface`. This change is a repair and local regression record, not independent Pro acceptance or evidence of a production attack.

## Confirmed code paths

- `/sys/dataSource` exposed list, options, detail, create, edit, delete, batch delete, import and export to any authenticated caller. The old entity returned/exported `dbPassword`. Edit/delete evicted the connection cache before the SQL write.
- `/sys/quartzJob` exposed list, detail, create, edit, delete, batch delete, pause, resume, import and export without an active operations-role check. Create/resume selected executable classes using caller-provided class names.
- The packaged `hibernate-re-2.1.5.jar` supplies nine `org.jeecg.modules.online.*` controllers. In particular `org.jeecg.modules.online.cgreport.a.a`, mapped to `/online/cgreport/api`, implements `POST /testConnection` by calling `Class.forName(dbDriver)` and `DriverManager.getConnection(dbUrl, dbUsername, dbPassword)` from its request. No role annotation surrounds this method/class. The previous Online interceptor only applied to `/online/cgform/api/**`. This is the same infrastructure boundary, not a separate claim of production exploitation.

The legitimate local data-source consumer is `SysBaseApiImpl`'s internal connection lookup. The web management screens are `SysDataSourceList/Modal`, `QuartzJobList/Modal`, and the deferred Online management routes. Repository teaching screens do not call Online endpoints. Therefore this repair retains the operations UI and internal lookup instead of removing those consumers.

## Resulting contract

- `InfrastructureAccessService` reads the current user status/deletion state and current database roles for each management operation. Only exact `dev` is accepted. `admin`, teacher, student, a cached former `dev`, a frozen/deleted user, and an absent principal are denied.
- Both local management controllers and their command services authorize before their reads, parsing or mutations. The internal data-source interface exposes only two connection lookups; the Quartz interface no longer offers generic `IService` save/update/import methods. Imports enter validated command services.
- `InfrastructureManagementInterceptor`, registered on every MVC path, checks the **selected HandlerMethod's class**, covering the actual packaged Online controllers plus both local infrastructure controllers. Authorization is independent of URI-prefix normalization, suffix aliases, matrix parameters and trailing slashes. It writes a real HTTP 403 JSON response itself so `.js` content negotiation cannot convert the denial into a 500. Existing Online per-menu checks continue to apply after the dev boundary.
- Source JSON/Excel output uses `SysDataSourceView`, which has no password field. The stored entity also suppresses passwords from Jackson, Fastjson and generated `toString()`. A create/import must supply a password; an omitted/empty edit password preserves the current value. The edit form explains that behavior. Source codes are immutable, caller-controlled audit/identity columns are not persisted, and complete batches validate before mutation.
- Source cache invalidation runs only after SQL commit. A rollback or failed validation does not close the pool or evict Redis. An invalidation failure is logged without pretending that the committed SQL write rolled back.
- Quartz create/import accepts the server-defined `jobType`: `sample`, `sample-parameter`, or `send-message`. The service maps these to compiled classes, validates cron/status, and does not reflectively load caller-selected job classes. The UI uses this selection. An existing task's type cannot be changed. Unknown legacy rows remain inspectable/deletable but cannot be resumed or edited into execution.

## Local validation performed

- JDK 8u504 / Maven 3.9.16, offline with `api/dev/maven-settings.xml`: complete backend package compilation succeeded.
- `InfrastructureAdministrationTest`: **14 tests, 0 failures/errors/skips**. Coverage includes all local controller operations (including GET/POST export and malformed import requests), service denials, unchanged SQL mapper/cache/scheduler interactions after rejection, same-principal revocation, active-account checks, genuine XLS import and password-free Excel output, password preservation and server-bound identities, failed batches, transaction commit/rollback cache timing, and a real initialized Druid/H2 pool preserved on denial and closed only for an authorized update.
- The suite creates a real RAM Quartz scheduler and exercises allow/pause/resume/edit/delete; denied/revoked operations preserve the registered job and trigger state. It also runs the **actual compiled JDBC controller** with a synthetic JDBC driver: rejected requests do not call its connection method, an authorized request reaches it exactly once without network access, and revocation blocks the same principal. Canonical, trailing-slash, `.json`, `.js`, matrix-parameter and percent-encoded aliases are covered. All packaged Online controller handlers are enumerated and checked against the class-based gate.
- Both changed Vue templates compile with Vue 2.7's template compiler.
- `python3 -m py_compile api/dev/verify-infrastructure-authorization.py` and `git diff --check` passed.

## Integrated runtime and browser evidence

The following reviewable reports are checked into this directory. They identify the tested artifact hashes; final combined candidate CI and independent Pro acceptance remain the root task's responsibility.

| Evidence | Result | Scope |
| --- | --- | --- |
| [Original behavior on the owned baseline](baseline-http.json) | 14/14, complete | 13 observations/restoration checks plus the completion item; ordinary student reads source credentials and inert Quartz metadata, and reaches the harmless Online no-driver error. Baseline JAR SHA-256 `efad54740308684c120895ddfacc5b36ddb6436cc3c4527183cb7d99f00b18c5`. |
| [Fixed real HTTP/MySQL/Redis/Quartz](fixed-http.json) | 305/305 | Root's serial integration run; same-token dev grant/revocation, denied side effects unchanged, source CRUD/password-free XLS export, actual scheduler lifecycle and full cleanup. Candidate JAR SHA-256 `3192bcdd90d35a5bf6f867d51a04f2fdbb3dbb3bb5a44a850a2a35f0ed6c8809`. |
| [Java suite summary](java-result.json) | 14/14 | Individual test names, durations and original JUnit digest; machine environment properties omitted. |
| [Real browser review package](ui/README.md) | 37/37 | Actual compiled before/after Vue SFCs, fourteen screenshots at 1440×1000 and 390×1200, and synthetic request records. |

[Live alias diagnosis](online-alias-diagnostic.json) distinguishes actual authorization denials from unregistered routes. In this full Boot runtime, canonical/trailing paths return 403; `.json`/`.js` return an exact standard Boot 404 and matrix paths return an exact 400 invalid-request shape. The probe records these as three separate categories, preserves the state comparisons and checks the unavailable aliases again with dev authority. It does not accept arbitrary 404/500 or business success as a permission denial. The Java test still deliberately uses suffix-enabled handlers to prove the interceptor covers a handler if such matching is enabled.

The real browser check also reproduced an intermediate UI compatibility issue: the edit form could send Test with no password after stored passwords stopped being returned. The final form explains that testing requires an entered password and makes no request in that case; empty-password saving still succeeds. Explicit-password testing remains bound to the original synthetic endpoint. [Before observation and final assertions](ui/README.md) are included.

Reproduce the Java suite from repository root (supply the local JDK/Maven path as appropriate):

```sh
mvn -o -B -ntp -s api/dev/maven-settings.xml -f api/pom.xml \
  -DskipTests=false -Dtest=InfrastructureAdministrationTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
```

Real runtime probe, intended to run serially under the root integration task:

```sh
python3 api/dev/verify-infrastructure-authorization.py \
  --runtime /tmp/.devspace/teachingopen-highrisk-20261012 \
  --jar api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar \
  --output ci-results/infrastructure-authorization.json
```

Add `--expect-legacy` only for the pinned pre-fix baseline. That branch requires an ordinary student role, inserts an inert (status `-1`) metadata fixture without registering any Quartz job, and checks student access to source detail/list passwords, the task list, and the packaged Online connection-test error with `java.lang.String` plus `jdbc:synthetic-no-driver`. It performs no HTTP administration write, no role grant, no task execution and no network-capable JDBC request. Every observation is bracketed by SQL/Redis/Quartz snapshots; its finally block removes only its two synthetic rows and checks exact state restoration. It emits `expected_legacy`, `passed`, `failed`, `total`, completion and redacted observations, including on a baseline assertion failure. The default fixed route remains the negative/positive regression and now also emits the complete count contract.

The probe requires an owned synthetic MySQL/Redis runtime with JDBC Quartz tables and asserts no configured/scheduled sample tasks before using those identities. It compares SQL tables, dynamic-source Redis values and real Quartz job/trigger tables before/after denials; tests student/teacher/admin and same-token dev revocation; verifies source CRUD/export and fixed-type Quartz lifecycle; then restores only its own fixtures and temporary dev grant. It never targets production. No credential/token is included in its structured report.

## Boundaries and remaining evidence

The full HTTP probe was run serially by the root task; this agent performed the bounded live alias diagnosis and the isolated browser verification. These tests are self-checks. In-process pool state is exercised in Java, not inferred from MySQL snapshots. Genuine XLS positive import uses Spring MockMvc and the actual parser; the live HTTP probe covers negative import before parsing and positive Excel export. This repair does not provide a distributed transaction across JDBC Quartz and application SQL; authorized scheduler faults during a multi-job update/import remain a separate operational consistency consideration. Existing production scheduler contents, active data-source configuration, backups and deployment are uninspected/unmodified. Final immutable candidate CI and independent Pro acceptance are not claimed by this evidence package.
