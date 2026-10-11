# Ancillary global management boundaries

Base: `93d4cfe8e911bccbaf1d20094357fa0b88076a86`. This is an Astra implementation-side review and fix, not an independent Pro verdict. The findings below were not promoted to additional verified High vulnerabilities or described as production exploitation.

## Evidence and scope

The active Spring controllers expose global operations behind the general JWT filter, without their own management checks. The existing infrastructure interceptor covers data sources, Quartz and compiled Online handlers; it does not cover these controllers.

| Surface | Observed impact before this change | Final policy |
| --- | --- | --- |
| `/sys/sysUserAgent` — list, detail, username lookup, add, edit, delete, batch delete, import, export | Any authenticated account can read/change delegation configuration. No identity delegation consumer was found in source, so privilege impersonation is **not** established. | Current active `admin` or `dev`, all handlers. |
| `/sys/position` — management reads, mutations, import, export | Any authenticated account can corrupt the position taxonomy. Position/post values were found in user profiles and selectors, not class or role authorization. | Current active `admin` or `dev`. The existing list remains available to all current active authenticated accounts. |
| `/oss/file` and `/sys/upload/uploadMinio` | Global metadata enumeration and unchecked legacy file administration. `OSSFileServiceImpl.delete` removes the database row before its external deletion attempt. Actual object destruction depends on a configured provider and was not attempted. | Current active `admin` or `dev`, all handlers. |
| `/actuator/redis/{info,keysSize,memoryInfo,queryDiskInfo}` | Redis and host operational metadata is visible to ordinary accounts. The implementation reads INFO, DBSIZE and disk capacity; it does not expose Redis values or configuration writes. | Current active `dev`, matching existing infrastructure policy. |

These are management integrity/confidentiality issues with Medium or configuration-dependent impact in the reviewed deployment, not newly established teaching-data or administrator-compromise chains. Filling their common boundary before launch was an explicit implementation decision.

Consumer checks:

- `UserList.vue` / `SysUserAgentModal.vue` are the delegation configuration consumers. Searches of source plus 469 application class/XML entries and 210 nested libraries in the earlier packaged candidate found only this module's own entity/controller/service/mapper references, with no delegation authorization consumer. That inspected JAR was SHA-256 `7fc5d65069f9b04ab0d4285bff50a2e19d16b67f43ac2d51e76ea582c25e9ba3`; it is not claimed to be the final integrated candidate.
- `AddressListRight.vue` and `JSelectPosition.vue` use `/sys/position/list`. Their read operation is preserved, while anonymous, disabled and deleted accounts are refused.
- `OSSFileList.vue` is the only located client for `/oss/file/*` and `/sys/upload/uploadMinio`; no teaching controller or ordinary `JUpload.vue` consumer uses `oss_file`. The teaching `sys_file` ownership flow is separate and unchanged.
- Spring Actuator exposure is `health` in the checked dev/test/prod profiles. The custom Redis controller remains a distinct MVC surface.

`GlobalManagementInterceptor` follows Spring's resolved `HandlerMethod` and controller class instead of a raw URL prefix. The same check therefore applies when a suffix, semicolon, or trailing slash resolves to a protected controller. It returns an explicit 403 JSON refusal before controller invocation, spreadsheet processing or cloud clients. The checks reuse the current database account and role services, including account status/deletion and same-principal revocation. No role or persistent security setting is changed.

## Regression evidence

`GlobalManagementAuthorizationTest` uses the application's actual `WebMvcConfiguration` registration. It exercises all 26 scoped mapped operations, current account/role lookups, ordinary/admin/dev/anonymous accounts, live revocation, denied side effects, and preserved position reads. Actual XLSX parsing/export is used for the successful management flow. The OSS service and Minio client are mocked, and the previous static Minio state and Spring context are restored by the test.

- Before registration: 10 tests, **8 assertion failures, 0 errors**. The original controller and MVC behavior remained unchanged; the new interceptor bean existed but was not registered. Ordinary and revoked identities still reached the management handlers. The required list and authorized management workflows already passed.
- After registration: **10/10 passed**, 0 errors. Denied operations have zero interactions with persistence, Redis and cloud mocks. Authorized JSON results, XLSX output and write/delete calls are verified.
- Machine-readable evidence: `evidence/global-management/java-before.json` and `java-after.json`. Raw logs are retained in the same worktree directory; the JSON records their hashes. Earlier compiler/test-client/headless setup failures are also retained and are not counted as security evidence.
- `python3 -m py_compile api/dev/verify-global-management-authorization.py` and `git diff --check` passed.

Command (use the local Maven/JDK/cache paths configured for this task):

```sh
mvn -o -s api/dev/maven-settings.xml -f api/pom.xml \
  -pl jeecg-boot-module-system -am -DskipTests=false \
  -Dtest=GlobalManagementAuthorizationTest -Dsurefire.failIfNoSpecifiedTests=false test
```

The provided `api/dev/verify-global-management-authorization.py` uses `verify(args)` with `runtime`, `jar`, `output`, and `expect_legacy`. It uses the existing `FixtureApi` and module-level `mysql_command` adapter. It must run alone against the synthetic runtime; it validates the immutable running JAR, uses only fixed fixture accounts, records refusal and unchanged database state, preserves legitimate list/import/export/CRUD, and tests a same-token dev grant/revocation. All original management, role and audit rows are restored after logout, including generated import IDs. It emits `cases`, `passed`, `failed`, `total`, `expected_legacy`, `jar_sha256` and `status`.

```sh
python3 api/dev/verify-global-management-authorization.py \
  --runtime /path/to/synthetic/runtime --jar /path/to/candidate.jar \
  --output /path/to/new-evidence.json
```

Cloud upload denial probes send an empty multipart request, so even an accidentally unguarded controller cannot obtain a file and invoke a cloud client. HTTP deletion probes use a verified absent OSS ID. Actual existing-object deletion and cloud upload success are therefore **mocked Java coverage only**, not real cloud validation. Final integrated packaging and Linux CI remain coordinated by the parent. The authorized local HTTP follow-up below did not invoke external storage.

### Actual HTTP export follow-up

The initial integrated HTTP run stopped at the administrator agent export because the probe required a MIME value containing `excel` or `octet-stream`. Read-only diagnostics against candidate JAR SHA-256 `0292703db84494798cf5740fc6cd22b26b1e131f5e8f0c01d29cae723bfd74da` established that **both agent and position exports return HTTP 200 with no `Content-Type` header**, and their response bodies are valid XLS workbooks. This was a probe false failure, not evidence of a failed export or a new authorization defect. The diagnostic response metadata and original synthetic files are retained in `evidence/global-management/export-diagnostic-728/`; the previous failed parent report was not overwritten.

The probe now compiles `ReadSpreadsheetCells.java` against the verified candidate's own libraries and parses the body with POI `WorkbookFactory`. Success requires the expected workbook title, column names and fixture marker in actual cells. It records the observed MIME, SHA-256 and parsed cell count and saves each synthetic workbook. JSON and HTML bodies containing the same marker, plus a truncated workbook, must fail parsing. No application MIME behavior changed.

The complete localhost HTTP suite passed **389/389**, with zero failures, against the exact JAR above. It includes legitimate list, CRUD, actual XLSX import and XLS export, ordinary/anonymous denial, same-token live dev grant/revocation, and refused-operation state checks. After logout, all six original management/role/audit table snapshots matched. The exclusive runtime window was then returned to the parent. Evidence and synthetic workbook hashes are in `evidence/global-management/http-fixed-728-export-poi.json`; the raw log and two exported files are retained beside it.

The parser was then moved without changing its parsing logic to a dedicated helper so the existing POI-core-only `verify-work-management.py` remains compatible. The original `ReadXlsCells.java` is unchanged. The final helper was independently recompiled against the same candidate JAR and passed **12/12 offline checks** over the saved actual HTTP XLS files, generated XLSX fixtures, and JSON/HTML/truncated negatives; see `export-diagnostic-728/poi-final-helper.json`. The parent still reruns the frozen combined candidate in its final gate. This probe follow-up changes no backend product code, deployment or persistent security settings.

## Finite review remainder

The read-only sweep additionally checked the config controller, demo Redis operations, mock JSON/disk routes, the Minio demo, NgAlain, and the existing management guards. `SysConfig` public reads return all enabled database config keys, including currently configured presentation/contact fields; saving is admin protected. A public-field allowlist remains a separate privacy/hardening consideration; no stored credential exposure was demonstrated. Demo Redis writes use fixed sample keys, and no session-token or arbitrary-key access was found. The demo Minio controller has a hardcoded demo endpoint; it was not contacted or credential-validated. These observations are retained for the next Pro review rather than expanded into unsupported High claims. FillRule, Category and CheckRule are covered by the separate query-agent change, not this commit.
