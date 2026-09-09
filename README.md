# Postfix Queue Viewer

A small, read-only emergency web inbox for messages waiting in a Postfix queue.

It is designed for a store-and-forward MX setup where a public VPS accepts mail and queues it while a downstream mail server is unavailable.

## Security model

- Postfix queue mounted read-only
- No Docker socket
- No destructive queue controls
- HTML mail is not executed by default
- Intended to be bound only to a Tailscale IP

More setup details will be added in this repository.
