# Deploys

Pushing to `main` in this repo or in `retyped_frontend` deploys to the Hetzner server (`retyped`) through `.github/workflows/deploy.yml`:

1. Lint and tests run. The frontend has no test step; its image build runs `next build`, which type-checks.
2. The image is built and pushed to GHCR, tagged with the full commit SHA:
   - backend: `ghcr.io/nuwaves/retyped_processing:<sha>`
   - frontend: `ghcr.io/nuwaves/retyped_frontend:<sha>`
3. The runner joins the tailnet as `tag:ci` and runs `ssh deploy@retyped "<backend|frontend> <sha>"`. The job's `GITHUB_TOKEN` is sent over stdin so the server can pull the image. The token expires when the job ends.
4. On the server, `retyped-deploy` does the following:
   - pulls the image
   - sets `BACKEND_IMAGE`/`BACKEND_TAG` (or the `FRONTEND_` pair) in `/opt/retyped/.env`
   - recreates the services: `web worker beat` for the backend, `frontend` for the frontend
   - waits up to 4 minutes for them to come up healthy
   - if they don't, puts the previous image back and fails the job

`web` runs `migrate` on startup. Migrations are **not** rolled back, so keep them backwards-compatible with the previous release.

## Server pieces

| Path | What |
|---|---|
| `/usr/local/sbin/retyped-deploy` | `deploy/retyped-deploy` from this repo (root:root 755) |
| `/usr/local/bin/retyped-deploy-shell` | `deploy/deploy-shell`; the login shell of the `deploy` user |
| `/etc/sudoers.d/retyped-deploy` | `deploy ALL=(root) NOPASSWD: /usr/local/sbin/retyped-deploy` |
| `/opt/retyped/.env` | Image names and tags that compose reads |
| `/var/log/retyped-deploy.log` | One block per deploy |

The `deploy` user is not in the `docker` group. Its only allowed action is running `retyped-deploy` with a target and a SHA.

After changing either script, reinstall it from the repo with:

```bash
sudo install -o root -g root -m 755 deploy/retyped-deploy /usr/local/sbin/retyped-deploy
```

## Manual deploy or rollback

From the server:

```bash
sudo retyped-deploy backend <sha> < /dev/null
```

An image that is already on the server is reused. The deploy script keeps the three newest images per repo. To roll back to an older image that has been pruned, either pass a GHCR token on stdin, or re-run that commit's Deploy workflow from the Actions tab.

## One-time setup (Tailscale + GitHub)

1. **Tailscale ACL.** Add the tag owner, the network rule and the SSH rule:
   ```jsonc
   "tagOwners": { "tag:ci": ["autogroup:admin"] },
   // in "grants" (or "acls"):
   { "src": ["tag:ci"], "dst": ["tag:retyped"], "ip": ["tcp:22"] },
   // in "ssh":
   { "action": "accept", "src": ["tag:ci"], "dst": ["tag:retyped"], "users": ["deploy"] }
   ```
2. **Tailscale OAuth client.** Go to Settings → OAuth clients. Give it the `auth_keys` write scope and tag `tag:ci`.
3. **GitHub secrets.** Add `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET` to both repos, under Settings → Secrets and variables → Actions.
