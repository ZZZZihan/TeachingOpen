# Additional-work browser regression

This harness mounts the actual `TeachingAdditionalWorkModal`, `CourseFormRecovery`, `JUpload`, `JModal`, dictionary and department selector components with Vue and Ant Design in Chrome. Only API adapters, bootstrap account/config state and the peripheral resize helper are replaced. Three real file selections use multipart uploads and file-registration HTTP requests against an ephemeral loopback-only synthetic server. No database, authenticated session, production endpoint or credential is used.

From the repository root, after installing the pinned web dependencies:

```sh
CHROME_BIN=/path/to/chrome-headless-shell \
NODE_PATH=/path/to/web/node_modules \
node web/tests/additional-work-preview/run.cjs /path/to/evidence/m05-ui
```

`CHROME_BIN` can also point to Chromium or Chrome supporting `--remote-debugging-pipe`. The default is macOS Google Chrome. Node 18+ is required. The browser and loopback listener may require a sandbox exception; both terminate and the disposable browser profile/build directory is removed when the run finishes. No global browser settings are changed. Browser requests outside the exact synthetic origin are blocked and fail the run; unexpected local routes also fail it.

Set `M05_SOURCE_ROOT=/path/to/candidate/repository` to compile another checkout read-only. Generated bundles and the browser profile still go exclusively into a new temporary directory. The report records that checkout's commit, any uncommitted `web/src` changes, and the actual component hashes; it also checks the component hashes again after the run to detect concurrent source changes.

The optional final argument overrides the pinned legacy commit (default `a3f4e10ceafcbe405093a3abe06a20225a17d3f6`). The legacy bundle replaces only the additional-work modal with that commit's source, leaving the same harness and other components in place. This isolates the failed-save behavior rather than claiming a full application comparison.

The runner writes `report.json` with source hashes, browser version, viewport, exact field values, request/registration counts, assertions and screenshot names. All six scenarios must pass:

1. Legacy HTTP 403: modal closes and reopening loses the work name and attachment selection.
2. Current HTTP 403 at 1440 × 1100: all fields and three registered attachments stay; the error receives focus; explicit retry succeeds once.
3. Connection reset before response headers: content remains recoverable, with the actual wire request count recorded.
4. Connection truncation after response headers: one failed save request, retained content, then one intentional successful retry.
5. Current HTTP 403 at 390 × 1100: same state checks; top and attachment-area screenshots cover the scrollable dialog.
6. Delayed save at 1440 × 1100: inert fields, disabled upload and footer controls, absent close button, Escape and repeated save/cancel/edit calls cannot replace or close the pending form; one request completes and emits one success callback.

This verifies UI recovery and guards, not backend creation idempotency. Chrome can replay a POST when a connection closes before any response headers; a single click produced two to three synthetic requests in local runs. The truncated-response fixture separately proves one-request recovery. Do not describe the UI as guaranteeing exactly one backend create. The existing unknown-result warning instructs users to check the list before retrying.
