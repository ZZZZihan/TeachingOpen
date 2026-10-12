# M-05 real-component browser evidence

All six scenarios passed in HeadlessChrome 151.0.7922.34. The final run compiled the integrated repository read-only at `a30018b903822b0d7a834e36434101026293cdda`; `web/src` had no uncommitted changes. It included the integrated `JUpload` transport fix. The actual component source hashes, fields and counts are in [report.json](report.json). No external or unexpected local browser requests were recorded.

Desktop viewport: 1440 × 1100, device scale factor 1. Narrow viewport: 390 × 1100, device scale factor 1; Chrome desktop rendering at that width (not mobile-device emulation). Three actual file selections uploaded and registered `cover.png`, `instructions.txt`, and `starter.txt` with the synthetic HTTP server before each save.

| Scene | Before / during | Result |
| --- | --- | --- |
| Old modal from pinned `a3f4e10`, same harness and other components | [filled form](legacy-forbidden-1440x1100-before-save.png) | [closed after HTTP 403](legacy-forbidden-1440x1100-after-failure.png), [empty when reopened](legacy-forbidden-1440x1100-reopened-empty.png) |
| Current HTTP 403, desktop | [filled form](fixed-forbidden-1440x1100-before-save.png) | [all fields and uploaded attachments retained](fixed-forbidden-1440x1100-after-failure.png), [explicit retry succeeds](fixed-forbidden-1440x1100-success.png) |
| Current connection reset before headers | [filled form](fixed-disconnect-1440x1100-before-save.png) | [content retained with uncertain-result warning](fixed-disconnect-1440x1100-after-failure.png) |
| Current response truncated after headers | [filled form](fixed-truncated-1440x1100-before-save.png) | [one failed request, content retained](fixed-truncated-1440x1100-after-failure.png) |
| Current HTTP 403, narrow viewport | [filled form](fixed-forbidden-390x1100-before-save.png) | [error and fields](fixed-forbidden-390x1100-after-failure.png), [attachments and footer after scrolling](fixed-forbidden-390x1100-after-failure-attachments.png) |
| Current delayed save | [locked pending form](fixed-slow-1440x1100-pending.png) | [success after one request and one callback](fixed-slow-1440x1100-success.png) |

The delayed save verifies disabled footer/upload controls, inert content, the absent modal close button, and rejection of repeat save/cancel/edit plus Escape while the request is pending. Source state, file keys and upload names remain unchanged after each rejected save. The error alert receives focus. The failed form can be submitted successfully when the synthetic backend subsequently returns success.

The APIs, bootstrap config/account state, and resize helper are synthetic; no production credentials, authenticated backend, database writes or full-application session behavior were tested. The browser requests only the ephemeral `127.0.0.1` listener and blocks other origins. No end-to-end create idempotency claim is made: pre-header reset produced two wire POSTs from one click in the integrated run and three in earlier runs. Chrome transport replay is not an application retry. The report keeps this measured count; the post-header truncation fixture separately proves recovery after one failed request. The warning tells users to check the list before choosing to retry.

Earlier branch and exploratory transport-replay records are retained separately in the task evidence. The committed `report.json` and linked screenshots describe the integrated component run.
