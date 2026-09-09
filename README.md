# Postfix Queue Viewer

A small, read-only emergency web inbox for messages waiting in a Postfix queue.

It is designed for a store-and-forward MX setup where a public VPS accepts mail and queues it while a downstream mail server is unavailable.

## Features

- Lists queued messages with sender, recipient, subject, size and delivery error
- Opens the queued message body
- Shows full headers and raw message source
- Allows attachment download
- Uses Postfix's own `postqueue` and `postcat` tools
- Read-only access to the queue volume
- No Docker socket and no destructive queue controls
- HTML mail is not executed by default
- Intended to be exposed only on a Tailscale address

## Current deployment values

This repository is already configured for:

- Hetzner Tailscale IP: `100.84.54.3`
- Web port: `8085`
- Existing Docker volume: `smtp-relay_postfix-queue`

The Compose file therefore binds only to:

```text
100.84.54.3:8085
```

and mounts the existing queue volume read-only.

## Deploy

On the Hetzner VPS:

```bash
cd /opt
git clone https://github.com/devnulluk/postfix-queue-viewer.git
cd postfix-queue-viewer
docker compose up -d --build
```

Then test locally on the VPS:

```bash
curl http://100.84.54.3:8085/health
```

Expected response:

```json
{"ok":true}
```

From any device connected to the same Tailnet, open:

```text
http://100.84.54.3:8085
```

## Existing queue volume

The viewer uses the existing Docker volume:

```text
smtp-relay_postfix-queue
```

The Compose declaration is:

```yaml
volumes:
  postfix-queue:
    external: true
    name: smtp-relay_postfix-queue
```

and the service mounts it as:

```yaml
volumes:
  - postfix-queue:/var/spool/postfix:ro
```

The `:ro` is intentional: the web app cannot modify, delete or requeue messages.

## Testing an outage

Temporarily make the downstream SMTP server unavailable, send a test message, then verify Postfix has queued it:

```bash
docker exec postfix-relay postqueue -p
```

The same message should then appear in the viewer.

When the downstream mail server becomes available again, normal Postfix delivery can continue without the viewer changing the queued message.

## Security notes

This application exposes the contents of queued email, including downloadable attachments. Keep it restricted to your Tailnet.

Do not change the Compose binding to `8085:8080` unless you intentionally want the service to listen on all interfaces.

HTML-only messages are displayed as escaped source rather than executed. This avoids remote tracking pixels, scripts and other active HTML content in the emergency viewer.
