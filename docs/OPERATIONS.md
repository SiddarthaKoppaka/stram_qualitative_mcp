# Operations

How to run the demonstration day to day. To install it, see [Deployment](../deploy/README.md).

The commands marked **service user** run as `stram-qual`, which needs `sudo`. These have not yet been
run on the host, so correct them here if one needs changing. This helper keeps them short:

```bash
qual() { sudo -u stram-qual XDG_RUNTIME_DIR="/run/user/$(id -u stram-qual)" "$@"; }
```

## Is it healthy?

```bash
curl -s http://127.0.0.1:8801/health/live
curl -s http://127.0.0.1:8801/health/ready
```

`live` shows the HTTP process answers. `ready` shows it can serve: the audit journal is good, the
worker is up, and versions match. Neither needs a token or exposes detail. For a full check, run
`tools/try_client.py` as in [Deployment](../deploy/README.md#6-check-it).

**Service user:**

```bash
qual systemctl --user status stram-qual-mcp.service stram-qual-jwks.service
qual journalctl --user -u stram-qual-mcp.service -n 50 --no-pager
qual podman ps
```

Logs are structured JSON. They never hold tokens, arguments, results or paths.

## Connect from a laptop

Open the tunnel and leave it running. Set `SERVER` to the account and host, such as `me@my-server`:

```bash
ssh -N -L 8801:127.0.0.1:8801 "$SERVER"
```

Get a token, which lasts an hour. In a second terminal, on the host:

```bash
python ~/.config/stram-qual-demo/issue_demo_token.py ~/.config/stram-qual-demo
cat ~/.config/stram-qual-demo/token
```

Use the Python that has PyJWT and cryptography. Then connect to `http://127.0.0.1:8801/mcp` as in
[How to consume](HOWTO_CONSUME.md). Keep the URL as `127.0.0.1`, because the service rejects other hosts
with 421.

## Start, stop and restart

**Service user:**

```bash
qual systemctl --user restart stram-qual-mcp.service
qual systemctl --user stop stram-qual-mcp.service stram-qual-jwks.service
qual systemctl --user start stram-qual-jwks.service stram-qual-mcp.service
```

Stopping it does not affect the News pipelines, which do not depend on it.

## Update to a new version

1. Pull this repository on the host.
2. Repeat steps 1, 2 and 4 of [Deployment](../deploy/README.md). Step 4 keeps the audit journal and key.
3. Run the checks in step 6.

The image bundles its own `stram_data`, so updating it does not touch the pipelines. They do share
the lake, so a new image can only read what the pipeline has written.

**To roll back,** check out the previous commit and repeat those steps.

## Common problems

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl` cannot connect | The container is stopped | Check status and logs, then restart |
| `not_ready` | Audit or worker problem | Read the logs. See [Audit](#audit) if the audit check failed |
| Client gets 401 | The token expired | Issue a new one. Also check the host clock |
| Client gets 421 | The URL host is wrong | Use `127.0.0.1:8801` |
| `unavailable` on every tool | The mounts are missing or the lake moved | `findmnt /srv/stram-qual/news/parquet`, then `sudo systemctl restart` that mount |
| Results stop at an old date | The pipeline stalled | Check the News services; this service only reads |
| Slow searches | Too many small Parquet files | Check compaction ran; see below |
| `overloaded` | Too many calls at once | Queries run one at a time, with 30 calls a minute per caller |
| `unavailable` on wide searches | The worker hit its 4 GB limit | Narrow the request. DuckDB gets half the limit and 4 threads |

The worker restarts itself after a crash or timeout. After three failures in a row, readiness stays
false until you restart the service.

## Compaction

The pipeline writes many small Parquet files, and reads slow down as they build up. The weekly timer
merges them.

```bash
systemctl --user list-timers stram-news-compact.timer
journalctl --user -u stram-news-compact.service -n 20 --no-pager
systemctl --user is-active stram-news-parquet-sink.service
```

The last line should print `active`. If a run failed partway, start the sink yourself.

Compaction keeps the files it replaced, so a run can be undone. Disk use therefore grows until
someone removes them, and that removal needs the `stram_data` owner's approval.

## Audit

Each call, including refusals, adds a record to a SQLite journal. Each record is chained to the last
with an HMAC, so tampering shows. If a record cannot be written, the call fails.

To verify the chain, stop the service first, so nothing writes while it checks.

**Service user:**

```bash
qual systemctl --user stop stram-qual-mcp.service
qual podman run --rm --read-only --network none \
  --volume stram-qual-audit:/audit \
  --secret stram-qual-audit-key,type=mount,target=audit-key,uid=10001,gid=10001,mode=0400 \
  --entrypoint /opt/venv/bin/python localhost/stram-qualitative-mcp:m5 \
  -m stram_qualitative_mcp.audit verify --db /audit/audit.sqlite3 --key-file /run/secrets/audit-key
qual systemctl --user start stram-qual-mcp.service
```

To keep a copy, export the volume while the service is stopped:

```bash
qual podman volume export stram-qual-audit --output "$HOME/audit-backup.tar"
```

Keep the journal and its key together, because one cannot be verified without the other. There is
no automatic backup yet. Never edit or truncate the journal. If verification fails, keep the files
and treat it as a security incident.

If you lost the key, or need to replace it, stop the service, move the old volume aside, and re-run
[setup_host.sh](../deploy/setup_host.sh), which then creates a new journal and key.

## Incidents

1. Stop the service. Do not delete containers, volumes, logs or keys.
2. Note the UTC time, and which calls were involved, using request IDs from the logs.
3. Export the audit journal as above.
4. Decide what happened: login abuse, data correctness, resource exhaustion, or host compromise.
5. Send data correctness problems to `stram_data`. This service never changes the lake.
6. Restart only once the cause is understood.

## Security rules

- The service only reads. Never make the mounts writable, or run it as the account that owns the lake.
- Never give `stram-qual` access to the raw archive.
- Never publish the port beyond loopback. The demonstration uses plain HTTP and a test login.
- Never pass secrets as command-line arguments or put them in the settings file.

## M6 staging checklist

All of this is **not yet done**. Staging must not take traffic until each item has an owner and
evidence in [PLANS.md](../PLANS.md).

- [ ] Image pinned by digest, with SBOM, provenance, vulnerability report and a rollback digest.
- [ ] Keycloak client with exact issuer, audience, tenant claim and least scopes. Missing, forged,
  expired, wrong-audience, wrong-tenant and wrong-scope tokens all fail.
- [ ] Private TLS, with exact Host and Origin rules.
- [ ] Host firewall allowing outbound traffic only to the issuer, JWKS and approved telemetry.
- [ ] Unprivileged host and in-container writes to the lake both fail, with evidence.
- [ ] `/proc` shows the seccomp filter on the query worker during a real call.
- [ ] Audit backup, independent verification, external checkpoint and a restore drill.
- [ ] Agreed retention. The proposal is 90 days online and one year archived.
- [ ] Overload, deadline, worker crash, restart limit and graceful shutdown exercised.
- [ ] Dashboards, alerts and owners, with telemetry redaction checked.
- [ ] Rollback to the previous digest restores readiness without touching the lake or journal.
- [ ] Licensing checked before anyone outside the team gets `qual:text`.
