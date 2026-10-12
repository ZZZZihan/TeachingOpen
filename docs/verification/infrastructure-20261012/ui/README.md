# H-01 real browser evidence

[Structured result](browser-result.json): **37/37 checks passed**, 14 screenshots, four recorded synthetic HTTP form submissions, no uncaught JavaScript errors, no console errors, and no attempted external requests. This is Astra's local regression evidence, not independent Pro acceptance.

The runner compiles the actual `SysDataSourceModal`, `QuartzJobModal`, `JDictSelectTag`, `JCron`, and `JCronModal` SFCs using the repository's Vue loader and Ant Design. Only the API transport boundary, duplicate-code lookup and dictionary records are synthetic. All requests target fresh loopback recorder servers; no application backend, production service or real database connection is involved. There are no real credentials or login tokens in this bundle. The explicit password in the recorded connection-test request is a synthetic fixture string.

Before: `a3f4e10ceafcbe405093a3abe06a20225a17d3f6`. After: `46c7e4a0` (resolved full commit and each compiled source SHA-256 are in the result). The report records the viewport and actual PNG dimensions for every image. The widths/heights are **1440 × 1000** and **390 × 1200**, without scaling or image editing. Ant modal entry animations are allowed to settle before capture.

| View | Before | After |
| --- | --- | --- |
| Desktop source edit | [Required blank password](before-1440x1000-source-edit.png) | [Blank preserves saved password](after-1440x1000-source-edit.png) |
| Desktop existing task | [Free class field](before-1440x1000-quartz-existing.png) | [Selected immutable type](after-1440x1000-quartz-existing.png) |
| Desktop new task | [Free class entry](before-1440x1000-quartz-free-class.png) | [Three reviewed types](after-1440x1000-quartz-type-options.png) |
| Narrow source edit | [Before](before-390x1200-source-edit.png) | [After](after-390x1200-source-edit.png) |
| Narrow existing task | [Before](before-390x1200-quartz-existing.png) | [After](after-390x1200-quartz-existing.png) |
| Narrow new task | [Before](before-390x1200-quartz-free-class.png) | [After](after-390x1200-quartz-type-options.png) |

Additional checks/screens: [Create still requires a password](after-1440x1000-source-add-password-required.png); [connection testing explains the separate password requirement](after-1440x1000-source-test-password-hint.png).

The password edit check submits a real PUT without a stored credential and without changing the immutable source code. A new source with a blank password is blocked. Clicking Test while editing with no password produces a clear hint and **zero requests**; filling an explicit synthetic password restores the connection-test request. Clearing it again still permits editing and saving. [Pre-prompt reproduction](blank-password-test-before.json) shows that the intermediate form previously sent a connection-test request with no password; this recorder evidence makes no claim of a real database connection succeeding.

The existing-job flow verifies a disabled, correctly selected `sample` type and preserved Cron/identity, changes the description and stopped state through the real Ant controls, and verifies the PUT fields. New-job creation offers exactly `sample`, `sample-parameter`, and `send-message`; the POST uses the selected type and a scalar status, without an arbitrary class field. Both screen sizes are checked. The narrow data-source Test button retains the prior compact column layout and has a crowded label; this is not a new regression or a high-risk finding. Saving remains available.

## Reproduce

Use the repository's installed frontend dependencies and an already installed/cached Playwright CLI; the runner never installs packages. Supply paths appropriate to the machine. `REPO/web/node_modules` must resolve the supplied modules for Vue's compiler resolution (a normal frontend install already does this).

```sh
python3 docs/verification/infrastructure-20261012/ui/run.py \
  --repo "$PWD" \
  --before a3f4e10ceafcbe405093a3abe06a20225a17d3f6 \
  --after HEAD \
  --node-modules "$PWD/web/node_modules" \
  --cli /path/to/node_modules/@playwright/cli/playwright-cli.js \
  --output /tmp/teachingopen-h01-ui
```

The runner builds the exact refs, allocates two loopback ports, launches a uniquely named browser session, saves raw logs and the result, then terminates only its own browser and servers. It exits nonzero on build or scenario failure. [Source and screenshot digests](files.sha256.json) provide an inventory of this review copy. Machine-local repository paths in the report's manifests have been removed; the original report digest is retained. Earlier exploratory runs are kept in the task's private evidence directory, not presented here as final results.
