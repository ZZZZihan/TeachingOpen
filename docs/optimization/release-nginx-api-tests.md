# Release Nginx API contract regression

The two fixed release configurations pass the same 60 real HTTP checks that each original configuration failed in 29 places. This verifies Nginx method handling, API namespace routing, URI preservation, and the retained static-file restrictions in an isolated Linux container. It does not establish backend authorization, full application acceptance, or production delivery.

The regression script is [`web/tests/release-nginx/probe.py`](../../web/tests/release-nginx/probe.py). It uses Python's standard library and a fixed official Nginx image; no test framework or application dependencies are added.

## Frozen contract

API requests below `/api/` reach the upstream with their original method, path encoding, and query. This includes GET, HEAD, POST, PUT, DELETE and OPTIONS. Bare `/api`, with or without query parameters, returns 308 to `/api/`; the script checks the exact redirect path/query and makes an explicit follow-up using the original method. `/apiculture` and `/apiXYZ/...` remain frontend requests.

The suite also checks encoded spaces, `%2F`, percent-encoded Unicode, repeated and empty query parameters, plus signs, and an existing double slash supplied by the client. It separately checks SPA fallback and static GET/HEAD, static `.map`/`.sql` and sensitive-directory 404 rules, root traversal 400 responses, static write-method 405 responses, and the existing TRACE/TRACK/WebDAV-style method restrictions.

The before and after runs used byte-identical case lists. Expected behavior came from the API contract and the explicit bare-API redirect decision. The synthetic upstream returns 204 plus its received method and raw request URI in response headers; it does not simulate the Java controller's response.

## Recorded run

Run date: 2026-10-05 Asia/Shanghai. The original configuration bytes were captured from candidate `49bea7da3552c554a8412f777eeec48d9a5ac9f2`; their SHA256 hashes were also checked against the PR worktree's unchanged Git base.

| Configuration | Original | Fixed |
| --- | --- | --- |
| `web/nginx/default.conf` | 31 / 60 pass; 29 fail | 60 / 60 pass |
| `资料/nginx.example.conf` | 31 / 60 pass; 29 fail | 60 / 60 pass |

Representative original observations:

- PUT and DELETE `/api/probe?...` returned Nginx 405 and never reached the synthetic upstream.
- GET, HEAD, POST and OPTIONS `/api/probe?cursor=%2F&text=a%20b` arrived as `/api//probe?cursor=%2F&text=a%20b`.
- `/api/probe%2Fencoded?x=a%2Fb` arrived as `/api//probe/encoded?x=a%2Fb`.
- `/apiculture` arrived at the upstream as `/api/culture`; `/apiXYZ/probe?...` arrived as `/api/XYZ/probe?...`.

The fixed files tested were:

- `web/nginx/default.conf`: SHA256 `93b019f547c36b708d46ac175368aee69a234495e6456b3e48e75d681e799a40`.
- `资料/nginx.example.conf`: SHA256 `00b2d82e81b4d0817de75846b6f258fc916464a809eeb2a867dacd257ee5b134`.

Runtime: Nginx 1.30.5, Linux/arm64 container through the already-running OrbStack Docker daemon 29.4.0. Official image digest: `nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94`. Image ID on this machine: `sha256:a805dc02b9a7ee985b411db35996123b9bb3df80e79a9ab5b194751d3087defe`. The local architecture-specific manifest digest is `sha256:3abad30db61dfb2a339ea21acc9f3e6bbe78e291fcff2f835f4510c8fdfcbd83`.

Local evidence lives outside the repository in `.devspace/artifacts/nginx-release-20261005/` relative to the outer TeachingOpen workspace:

- `frozen-contract-60.json`: expected cases and redirect comparison scope, frozen before the after-run.
- `before-contract60/` and `after-contract60/`: image receipt, identical `contract-cases.json`, summary, and one directory for each configuration.
- Each configuration directory contains `results.json` with exact expected/observed values, `config-test.log`, `server.conf`, `server.environment.diff`, Nginx request/error logs, and `shutdown.json`.
- `final-script/`: final portable script replay with default source-root discovery; both configurations passed 60/60 and completed guarded cleanup.
- `old/`: the initial 42-case reproduction, retained separately. Its immediate post-removal port bind check encountered asynchronous OrbStack port release; guarded stop/removal and subsequent free-port recovery are recorded. The final reusable harness waits at most 10 seconds for each released port, and both 60-case runs completed cleanly.

All owned HTTP-test containers were stopped and removed after checking their unique ownership label. Both published loopback ports were free after cleanup. No existing container, service, application runtime, database, Redis instance, browser session, or credential fixture was used.

## Reproduce

Use a running local Docker daemon, Python 3, a fresh dedicated output directory, and free loopback ports 18186 and 18187. Download the immutable official image once if it is not present, then run from the source checkout:

```sh
docker pull nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
python3 web/tests/release-nginx/probe.py \
  --output-dir /tmp/teachingopen-release-nginx-api-check \
  --expect-pass
```

The script uses `docker` from PATH, falling back to `/usr/local/bin/docker`; `--docker /absolute/path/to/docker` overrides the executable. `--source-root` selects another checkout, and `--prefix` gives the new result directory a distinct name. The script does not overwrite an existing per-configuration result directory. With `--expect-pass`, any contract failure produces exit code 1; without it, failures are retained as before-change evidence and summarized. Setup, runtime, or cleanup errors also fail the command.

The copied server config changes only the listener (`80` to `8080` inside the test container), static root, and upstream address. A saved unified diff shows each substitution. The real proxy still sends an HTTP request to a separate synthetic echo listener at container port 8081. Only host `127.0.0.1:18186` and `127.0.0.1:18187` are published. Only the dedicated artifact directory is mounted, read-only. The HTTP-test container runs as UID/GID 101, drops capabilities, and enables no-new-privileges. The config syntax check uses a separate disposable container with networking disabled.

No request bodies or authorization headers are supplied or logged. The only forwarded test header is a newly generated canary. Logs retain method, URI and status; response bodies are discarded.

Nginx may make a relative redirect absolute using its listener port. The test deliberately compares the `Location` path and query, retains the full raw header, and follows the redirect at the bound loopback port. Therefore it verifies the 308 status plus method/query continuation, not deployment-specific redirect origin, TLS, or externally mapped ports. Browser redirect behavior, payload forwarding, authentication/authorization and real controller responses remain separate application checks.

The URI behavior follows the official [`proxy_pass` documentation](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass): specifying a URI replaces the matched part of the normalized request URI; omitting it forwards the original client URI when no rewrite has changed that request. The runtime image is from the [Docker Official Nginx image](https://hub.docker.com/_/nginx).
