# How to check staging

Two scripts gather the evidence for the [staging checklist](../reference/staging-checklist.md). Run
both after every deployment, and record the results in `PLANS.md`.

## 1. Check logins and permissions from a laptop

From a machine on the tailnet, with this repository's environment and each client secret in its own
file:

```bash
uv run python tools/m6_check.py --endpoint "https://$HOST:8443/mcp" \
  --issuer "https://$HOST/realms/stram-staging" \
  --smoke-secret-file "$HOME/.stram-qual/stram-qual-smoke.secret" \
  --text-secret-file "$HOME/.stram-qual/stram-qual-text.secret" \
  --discovery-secret-file "$HOME/.stram-qual/stram-qual-discovery-only.secret"
```

Expected: every line starts with `PASS`, then `all checks passed`. It checks that each token is for
this service with exactly its scopes, that bad tokens, a wrong Host and a foreign Origin are refused,
that each client sees and can call only its own tools, and that denials say `Access denied.` and are
not retryable. It prints request IDs and times, never secrets, tokens or article text.

The denials it makes stay below the throttle's limit of five a minute per client. If you run it
several times in a row, wait a minute between runs.

## 2. Check the host

**sudo.** On the host:

```bash
sudo bash deploy/m6_evidence.sh "$LAKE"
```

Expected: `0 failed`. It checks that the lake cannot be written from the host or the container, that
the query worker runs under seccomp and recovers when killed, and that the service shuts down cleanly.
It also backs up the audit journal, verifies it, and restores the copy into a scratch volume to prove
the backup works. The service is stopped for under a minute. The backup, its key and a checkpoint go
to `/var/backups/stram-qual/`, readable only by root.

## 3. Check readiness after both

```bash
curl -s "https://$HOST:8443/health/ready"
```

Expected: `{"status":"ready"}`.
