# Non-critical AutoLog failure and metadata policy

The original aspect called `sysLogService.save` after the controller returned. A real MySQL `sys_log` INSERT failure on the frozen `d88f4392` candidate produced HTTP 200 with `success=false, code=500`, although the work, zero-score feedback, durable `CORRECT` event and daily correction count had already committed once. A subsequent normal request also copied the feedback and work name into `sys_log.request_param`. The scoped synthetic baseline probe passed 13 checks and restored every non-audit table and all attachment bytes.

`AutoLogAspect` now preserves the exact business response after an audit construction or persistence exception. It does not catch business exceptions, retry business operations or manufacture success. `AutoLogWriter` runs in `REQUIRES_NEW`, so an audit SQL failure cannot mark a surrounding business transaction rollback-only. A false persistence return is also treated as an observable audit failure. Failures produce a WARN with the stable code `audit_write_failed`, static Java method and exception class only; exception text, stack trace and business values are deliberately excluded.

Automatic audit entries contain the annotation operation/type, static method, authenticated actor metadata, HTTP verb, transport peer address, timestamp and duration. `request_param` is always NULL. No method arguments, body, query string, URL, credentials or forwarded headers are copied by the aspect. This affects new automatic audit records; historical records are not rewritten, and their read/delete authorization is handled separately. Domain-specific `sys_data_log` history is unchanged.

This is best-effort, non-critical audit. An audit outage can leave a missing record. There is no retry queue, durable failure metric, business/audit atomicity or guarantee that an enclosing transaction later commits. The warning needs ordinary operational log collection to be observed. This change does not create a strongly consistent audit trail.

`AutoLogSafetyTest` passes six Java tests, including real H2 SQL constraint failure in a separate audit transaction while the outer business transaction commits, identity-preserving success and failure responses, false audit saves, missing request context, safe warnings and five HTTP verbs with forbidden argument access.

The actual MySQL/HTTP regression is `api/dev/verify-audit-failure.py`:

```sh
python3 api/dev/verify-audit-failure.py \
  --runtime /path/to/owned/.devspace/runtime \
  --jar /path/to/frozen/candidate.jar \
  --output /path/to/new-report.json
```

Use `--expect-legacy` for the old failure semantics and DTO-copy baseline. The shared runtime must be exclusively allocated to the probe, with no existing daily-log rows or probe IDs. Its temporary `BEFORE INSERT` trigger only rejects the synthetic teacher's work edit while the exact task-owned work has the probe marker. The `finally` block removes the trigger and its work/event/statistics rows. The candidate must preserve HTTP 200 success under that fault, commit the feedback/event/count once, produce one sanitized warning, and later write a metadata-only audit row. The report binds the actual JAR SHA-256 and checks non-audit table/attachment restoration; runtime credentials and complete application logs are not included.
