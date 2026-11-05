# How to operate the service

Day-to-day tasks for the deployed service. To install it, see [Deploy the service](deploy-the-service.md).

Commands marked **service user** run as `stram-qual`, which needs `sudo`. This helper keeps them
short:

```bash
qual() { sudo -u stram-qual XDG_RUNTIME_DIR="/run/user/$(id -u stram-qual)" "$@"; }
```

## Check that it is healthy

```bash
curl -s http://127.0.0.1:8801/health/live
curl -s http://127.0.0.1:8801/health/ready
```

`live` shows the HTTP process answers. `ready` shows it can serve: the audit journal is good, the
worker is up, versions match, and Keycloak's signing keys were read. Neither needs a token or exposes
detail. For a full check, follow [Check staging](check-staging.md).

**Service user:**

```bash
qual systemctl --user status stram-qual-mcp.service
qual journalctl --user -u stram-qual-mcp.service -n 50 --no-pager
qual podman ps
```

Logs are structured JSON. They never hold tokens, arguments, results or paths.

## Stop, start or restart it

**Service user.** Stop both units, then start from the pod:

```bash
qual systemctl --user stop stram-qual-mcp.service stram-qual-pod.service
qual systemctl --user start stram-qual-pod.service
qual systemctl --user start stram-qual-mcp.service
```

A plain `restart` of the service fails with "A dependency job failed", because stopping the container
takes the pod down with it. In demo mode, start `stram-qual-jwks.service` after the pod as well.
Stopping the service does not affect the News pipelines.

## Update to a new version

1. Pull this repository on the host.
2. Repeat steps 1 to 3 of [Deploy the service](deploy-the-service.md). Step 3 keeps the audit journal
   and key.
3. Follow [Check staging](check-staging.md).

The image bundles its own `stram_data`, so updating it does not touch the pipelines.

## Roll back to the previous release

Keep the previous release's image archive. To deploy it, name its tag:

```bash
sudo env IMAGE=localhost/stram-qualitative-mcp:m7 bash deploy/setup_host.sh "$LAKE" "$PREVIOUS_TAR" staging /etc/stram-qual/staging.env
```

Then follow [Check staging](check-staging.md). Rolling back never touches the lake or the audit
journal. The `m7` image is the FastMCP server before the clean view. The `m5` image is the
hand-wired server from before the FastMCP move; its source is the `old-mcp-archive` branch. To
return, run step 3 of the deployment again with the current archive.

## Back up and verify the audit journal

A daily timer backs the journal up while the service runs, verifies the copy, and keeps 30 days in
`/var/backups/stram-qual/`. To install it, or to change which account copies backups off the host:

```bash
sudo bash deploy/install_audit_backup_timer.sh siddu
```

Expected: a line starting `audit backup` and ending with the checkpoint, then the timer's next run. To
take a backup now, run `sudo systemctl start stram-qual-audit-backup.service`, and read the result with
`journalctl -u stram-qual-audit-backup.service -n 3`.

[Check staging](check-staging.md#2-check-the-host) also backs up, verifies and restores the journal. To
only verify the live journal, stop the service first so nothing writes while it checks:

**Service user:**

```bash
qual systemctl --user stop stram-qual-mcp.service stram-qual-pod.service
qual podman run --rm --read-only --network none \
  --volume stram-qual-audit:/audit \
  --secret stram-qual-audit-key,type=mount,target=audit-key,uid=10001,gid=10001,mode=0400 \
  --entrypoint /opt/venv/bin/python localhost/stram-qualitative-mcp:m8 \
  -m stram_qualitative_mcp.audit verify --db /audit/audit.sqlite3 --key-file /run/secrets/audit-key
qual systemctl --user start stram-qual-pod.service
qual systemctl --user start stram-qual-mcp.service
```

Keep the journal and its key together, because one cannot be verified without the other. Never edit
or truncate the journal. If verification fails, keep the files and treat it as an incident.

To replace a lost key, stop the service, move the old volume aside, and run
[setup_host.sh](../../deploy/setup_host.sh) again, which creates a new journal and key.

## Copy the audit backups off the host

Once a week, from your laptop, copy the latest backup, its checkpoint and the key into a folder only
you can read. In PowerShell:

```powershell
New-Item -ItemType Directory -Force $HOME\.stram-qual\backups
scp -i $HOME\.ssh\stram_siddu "siddu@SERVER:/var/backups/stram-qual-outbox/*" $HOME\.stram-qual\backups\
```

Each copy replaces the last, so keep older ones by renaming the folder if you need them. The key lets
anyone holding it forge a matching journal, so keep that folder private and never commit or share it.
The checkpoint alone is enough to prove the journal has not been rewritten since.

## Check compaction

```bash
systemctl --user list-timers stram-news-compact.timer
journalctl --user -u stram-news-compact.service -n 20 --no-pager
systemctl --user is-active stram-news-parquet-sink.service
```

The last line should print `active`. If a run failed partway, start the sink yourself. To compact now,
run `systemctl --user start stram-news-compact.service`; it stops the Parquet sink for a few minutes.
Compaction keeps the files it replaced, and removing them needs the `stram_data` owner's approval.

## Fix common problems

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl` cannot connect | The container is stopped | Check status and logs, then start it as above |
| `not_ready` | Audit, worker or Keycloak keys | Read the logs. After three worker failures in a row, readiness stays false until you restart |
| Every staging call gets 401 | Wrong audience or scopes, or Keycloak unreachable | Check the token's `aud`, then run step 3 of the deployment, which checks Keycloak from a container |
| Client gets 421 | The URL host is wrong | Use the tailnet URL in staging, `127.0.0.1:8801` in demo mode |
| A client sees fewer tools | Its token lacks those scopes | Request the scope, or use a client that holds it |
| `access_denied` on every call | The caller was throttled after repeated denials | Wait a minute, and fix whatever caused the denials |
| `unavailable` on every tool | The mounts are missing or the lake moved | `findmnt /srv/stram-qual/news/parquet`, then `sudo systemctl restart` that mount |
| Results stop at an old date | The pipeline stalled | Check the News services; this service only reads |
| Slow searches, or article reads past their deadline | Too many small Parquet files | Check compaction ran, or run it now |
| `overloaded` | Too many calls at once | Queries run one at a time, with 30 calls a minute per caller |
| `unavailable` on wide searches | The worker hit its 4 GB limit | Narrow the request |

## Respond to an incident

1. Stop the service. Do not delete containers, volumes, logs or keys.
2. Note the UTC time, and which calls were involved, using request IDs from the logs.
3. Back up the audit journal as above.
4. Decide what happened: login abuse, data correctness, resource exhaustion, or host compromise.
5. Send data correctness problems to `stram_data`. This service never changes the lake.
6. Start it again only once the cause is understood.
