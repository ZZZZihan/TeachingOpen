# Upload credentials follow the actual destination

The original `JUpload` instance captured the platform login token in `created()` and passed that header to every Ant Upload destination, including Qiniu. A refreshed or removed login token could also leave an old credential in the component.

The component now uses Ant Upload's actual request hook, after asynchronous upload preparation. Only its exact configured local API destination receives the current platform token. Other destinations receive their existing provider form data without the platform header or cross-origin cookie credentials. The existing transport, progress/error callbacks and abort contract are retained.

## Verification

- `node --test tests/upload-credentials.test.cjs`: three component-template/installed-Ant-transport regressions. They fail against the original source and pass against this change.
- Targeted upload, ownership and map suites: 20 tests passed.
- `node tests/upload-credentials.browser.cjs` provides the portable loopback browser runner. Set `CHROME_BIN` where the browser is not in a standard location.
- Independent implementation review (not ChatGPT Pro acceptance) exercised the actual Vue component, Ant Upload and Chromium XHR against two isolated loopback origins: 13 checks passed, covering token rotation, Qiniu form credentials, a delayed destination switch, failure/retry, logout and CORS preflight. No request was sent to a third-party service.

The same local destination still relies on the configured platform API being trusted. This change does not claim to assess a compromised server or a deployment that redirects its upload endpoint to another origin. Production Qiniu access was not used.
