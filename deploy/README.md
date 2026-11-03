# Deployment

This installs the service on a Linux server that holds the News lake. It runs as a rootless
container, with a read-only view of the data, on `127.0.0.1:8801`. Steps 1 to 6 set up the loopback
demonstration, which you reach through an SSH tunnel. Step 7 switches it to staging, with Keycloak
logins over private HTTPS; see also [the M6 checklist](../docs/OPERATIONS.md#m6-staging-checklist).

Steps 1 to 6 were run on the real host on 2026-11-01, except that step 5's job has not yet had its
first scheduled run. [Remove it](#remove-it) has not been tested. Commands marked **sudo** need an
administrator. Run everything on the host, as the account that owns the News lake. Set `LAKE` to the
News lake folder, the one holding `parquet/` and `bodies/`.

## What you need

- A News lake written by the `stram_data` pipeline.
- Rootless Podman with Quadlet support. This was tested on Podman 6.1.4.
- `uv`, Git and `openssl`.
- `sudo` on the host, and about 1 GB of free disk for the image.
- A `stram_data` checkout holding the commit this repository pins.
- About 5 GB of spare memory.

## What gets created

| Item | Why |
|---|---|
| Non-login user `stram-qual` | Separates the service from the account that writes the lake |
| Read-only mounts under `/srv/stram-qual/news/` | Gives it `parquet` and `bodies` only, never the raw archive |
| Podman volume `stram-qual-audit` | Holds the audit journal |
| Podman secret `stram-qual-audit-key` | Signs the audit journal |
| Pod `stram-qual` | The service. The demonstration adds a small server for its public signing key |
| Files in `~stram-qual/.config/` | Service settings and the public key |

## 1. Build the image

On the host, from a clone of this repository:

```bash
sh deploy/build_image.sh "$HOME/path/to/stram_data"
```

Expected: `{"status":"worker_network_isolated"}`, then `Saved /tmp/stram-qualitative-mcp.tar`. If a
download from `snapshot.debian.org` returns 503, wait a minute and run it again.

## 2. Test the image on the real lake

This changes nothing, because the mounts are read-only and the containers are removed afterwards.

```bash
for check in worker-interface-probe preflight; do
  podman run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
    --mount type=bind,src="$LAKE/parquet",dst=/news/parquet,ro \
    --mount type=bind,src="$LAKE/bodies",dst=/news/bodies,ro \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=2g \
    localhost/stram-qualitative-mcp:m5 "$check"
done
```

Expected: `{"status":"worker_interface_ok"}`, then a line with `"status": "preflight_ok"`.

## 3. Create the demonstration key

The private key stays in a folder you choose, with mode 0600. Only the public key goes to the service.
Use any Python that has PyJWT and cryptography, such as this repository's environment:

```bash
uv run python deploy/issue_demo_token.py "$HOME/.config/stram-qual-demo" --jwks-out /tmp/stram-qual-jwks.json
```

Expected: `token written, valid for 60 minutes`.

## 4. Install and start

**sudo.** Read [setup_host.sh](setup_host.sh) first:

```bash
sudo bash deploy/setup_host.sh "$LAKE" /tmp/stram-qualitative-mcp.tar demo /tmp/stram-qual-jwks.json
```

Expected: it ends with `Setup finished in demo mode. Only 127.0.0.1:8801 is published.` and shows
`stram-qual-mcp.service` as active.

Running it again is safe, and that is also how you update the service. It keeps the user, audit
journal and key, then replaces the image and settings and restarts.

## 5. Add weekly compaction

Run this as the account that owns the News services, with no `sudo`:

```bash
sh deploy/install_compaction_timer.sh "$HOME/path/to/news-pipeline"
```

Compaction merges small Parquet files so reads stay fast. It runs on Sundays at 07:23 host time. It
needs the Parquet sink stopped, so the job stops it and restarts it, and Kafka holds new items
meanwhile.

## 6. Check it

```bash
curl -s http://127.0.0.1:8801/health/ready
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8801/mcp
uv run python tools/try_client.py --endpoint http://127.0.0.1:8801/mcp \
  --token-file "$HOME/.config/stram-qual-demo/token"
ss -ltn | grep 8801
findmnt -n -o TARGET,OPTIONS /srv/stram-qual/news/parquet
```

Expected: `{"status":"ready"}`, then `401`, then a line from each tool, then only `127.0.0.1:8801`
listening, then mount options starting with `ro`.

To connect and to run it day to day, see [Operations](../docs/OPERATIONS.md).

## 7. Switch to staging

**Not yet run on the host.** Staging replaces the test login with the shared Keycloak realm and
publishes the service on the tailnet. Tailscale provides the HTTPS certificate. You need the realm
set up with this service's audience and `qual:*` scopes, and its client secrets.

1. Copy [staging.env.example](staging.env.example) to a root-owned file outside the repository, such
   as `/etc/stram-qual/staging.env`, and fill it in. It names a private host, so never commit it.
2. **sudo.** Switch the service. It checks that the container trusts Keycloak before restarting
   anything, and stops the demonstration key server:

   ```bash
   sudo bash deploy/setup_host.sh "$LAKE" /tmp/stram-qualitative-mcp.tar staging /etc/stram-qual/staging.env
   ```

   Expected: `Keycloak reachable from the container, with a trusted certificate.`, then
   `Setup finished in staging mode.`
3. **sudo.** Publish it on the tailnet, on the port from the settings file:

   ```bash
   sudo tailscale serve --bg --https=8443 http://127.0.0.1:8801
   tailscale serve status
   ```

4. From a laptop on the tailnet, with each client secret in its own file:

   ```bash
   uv run python tools/m6_check.py --endpoint "https://$HOST:8443/mcp" \
     --issuer "https://$HOST/realms/stram-staging" --smoke-secret-file smoke.secret \
     --text-secret-file text.secret --discovery-secret-file discovery.secret
   ```

   Expected: every line starts with `PASS`, then `all checks passed`.

**To go back to the demonstration,** run `sudo tailscale serve --https=8443 off`, then step 4 in
demo mode. Neither mode touches the audit journal or the lake.

## Remove it

**sudo. Not yet tested.** This deletes the audit journal and key. Back them up first if you may need them; see
[Operations](../docs/OPERATIONS.md#audit).

```bash
sudo tailscale serve --https=8443 off
sudo -u stram-qual XDG_RUNTIME_DIR="/run/user/$(id -u stram-qual)" \
  systemctl --user stop stram-qual-mcp.service stram-qual-jwks.service stram-qual-pod.service
sudo systemctl disable --now 'srv-stram\x2dqual-news-parquet.mount' 'srv-stram\x2dqual-news-bodies.mount'
sudo rm '/etc/systemd/system/srv-stram\x2dqual-news-parquet.mount' \
  '/etc/systemd/system/srv-stram\x2dqual-news-bodies.mount'
sudo loginctl disable-linger stram-qual
sudo userdel --remove stram-qual
```

To remove compaction, run `systemctl --user disable --now stram-news-compact.timer` as the account
that owns the News services.
