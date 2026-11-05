# How to deploy the service

This guide installs the service on the Linux server that holds the News lake, and publishes it on the
tailnet with Keycloak logins. It runs as a rootless container with a read-only view of the data, on
`127.0.0.1:8801`, and Tailscale Serve gives it private HTTPS.

Steps marked **sudo** need an administrator. Run everything on the host, as the account that owns the
News lake, from a clone of this repository. Set `LAKE` to the News lake folder, the one holding
`parquet/` and `bodies/`. What each script creates is in [Deployment](../reference/deployment.md).

## What you need

- A News lake written by the `stram_data` pipeline.
- Rootless Podman with Quadlet support (tested on 6.1.4), `uv`, Git and `openssl`.
- `sudo` on the host, about 1 GB of free disk for the image and about 5 GB of spare memory.
- A `stram_data` checkout holding the commit this repository pins.
- For staging: Tailscale on the host, and the shared Keycloak realm set up with this service's
  audience, `qual:*` scopes and clients.

## 1. Build the image

```bash
sh deploy/build_image.sh "$HOME/path/to/stram_data"
```

Expected: `{"status":"worker_network_isolated"}`, then `Saved /tmp/stram-qualitative-mcp.tar`. The
image is tagged `localhost/stram-qualitative-mcp:m8`. If a download from `snapshot.debian.org` returns
503, wait a minute and run it again.

## 2. Test the image on the real lake

This changes nothing: the mounts are read-only and the containers are removed afterwards.

```bash
for check in worker-interface-probe preflight; do
  podman run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
    --mount type=bind,src="$LAKE/parquet",dst=/news/parquet,ro \
    --mount type=bind,src="$LAKE/bodies",dst=/news/bodies,ro \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=2g \
    localhost/stram-qualitative-mcp:m8 "$check"
done
```

Expected: `{"status":"worker_interface_ok"}`, then a line with `"status": "preflight_ok"`.

## 3. Install and start in staging mode

1. Copy [staging.env.example](../../deploy/staging.env.example) to a root-owned file outside the
   repository, such as `/etc/stram-qual/staging.env`, and fill it in. It names a private host, so
   never commit it.
2. **sudo.** Read [setup_host.sh](../../deploy/setup_host.sh), then run it. It checks that the
   container trusts Keycloak before restarting anything:

   ```bash
   sudo bash deploy/setup_host.sh "$LAKE" /tmp/stram-qualitative-mcp.tar staging /etc/stram-qual/staging.env
   ```

   Expected: `Keycloak reachable from the container, with a trusted certificate.`, then
   `Setup finished in staging mode.`

Running it again is safe, and that is also how you update the service. It keeps the user, audit
journal and key, then replaces the image and settings and restarts.

## 4. Publish it on the tailnet

**sudo.** Use the port from the settings file:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8801
tailscale serve status
```

Expected: a `:8443` entry proxying to `127.0.0.1:8801`, with any other routes unchanged.

## 5. Add compaction

Run this as the account that owns the News services, with no `sudo`:

```bash
sh deploy/install_compaction_timer.sh "$HOME/path/to/news-pipeline"
```

Compaction merges small Parquet files so reads stay fast. Without it, article reads passed their
deadline after about a week.

## 6. Check it

Follow [Check staging](check-staging.md).

## Use demo mode instead

Demo mode needs no Keycloak or tailnet. It uses a local signing key and plain HTTP on loopback, and
you reach it through an SSH tunnel. Never publish it beyond loopback.

```bash
uv run python deploy/issue_demo_token.py "$HOME/.config/stram-qual-demo" --jwks-out /tmp/stram-qual-jwks.json
sudo bash deploy/setup_host.sh "$LAKE" /tmp/stram-qualitative-mcp.tar demo /tmp/stram-qual-jwks.json
```

Switching between modes keeps the audit journal and never touches the lake. Before switching from
staging to demo, run `sudo tailscale serve --https=8443 off`.

## Remove it

**sudo.** This deletes the audit journal and key; [back them up](operate-the-service.md#back-up-and-verify-the-audit-journal)
first if you may need them. These commands have not been run on the host.

```bash
sudo tailscale serve --https=8443 off
sudo -u stram-qual XDG_RUNTIME_DIR="/run/user/$(id -u stram-qual)" \
  systemctl --user stop stram-qual-mcp.service stram-qual-pod.service
sudo systemctl disable --now 'srv-stram\x2dqual-news-parquet.mount' 'srv-stram\x2dqual-news-bodies.mount'
sudo rm '/etc/systemd/system/srv-stram\x2dqual-news-parquet.mount' \
  '/etc/systemd/system/srv-stram\x2dqual-news-bodies.mount'
sudo loginctl disable-linger stram-qual
sudo userdel --remove stram-qual
```

To remove compaction, run `systemctl --user disable --now stram-news-compact.timer` as the account
that owns the News services.
