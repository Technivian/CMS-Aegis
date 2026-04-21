# Free Render Preview Deploy

This repo now includes a free-first Render Blueprint for a preview deploy.

## What It Creates

- a free Python web service
- a free Render Postgres database
- automatic static file collection during build
- database migrations on startup

## Important Limits

Render free services are for preview and testing, not production:

- free web services spin down after idle time
- free Postgres databases expire after 30 days
- free Postgres databases do not include backups

## How To Deploy

1. Sign in to Render.
2. Create a new Blueprint from this repository's `render.yaml`.
3. Accept the free web service and free Postgres database.
4. Deploy the preview service.
5. Open the Render service URL and sign in with the app's admin account.

## After Creation

If you want the service to be reachable on the preview URL immediately, ensure the Blueprint-created database and web service are both active and the first deploy succeeds.

If you want to change the branch later, update `branch` in [render.yaml](/Users/haroonwahed/Documents/Projects/CMS-Aegis/render.yaml).
