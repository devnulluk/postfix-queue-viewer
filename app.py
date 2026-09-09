from __future__ import annotations

import email
import json
import os
import re
import subprocess
from email import policy
from email.header import decode_header, make_header
from io import BytesIO

from flask import Flask, abort, render_template, send_file

app = Flask(__name__)
APP_TITLE = os.environ.get("APP_TITLE", "Emergency Mail Queue")
QUEUE_ID_RE = re.compile(r"^[A-F0-9]+$", re.I)


def run_cmd(args: list[str]) -> str:
    proc = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    return proc.stdout


def safe_queue_id(queue_id: str) -> str:
    if not QUEUE_ID_RE.match(queue_id):
        abort(400)
    return queue_id


def decode_mime(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def queue_json() -> list[dict]:
    rows: list[dict] = []
    for line in run_cmd(["postqueue", "-j"]).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def postcat(queue_id: str) -> str:
    return run_cmd(["postcat", "-q", safe_queue_id(queue_id)])


def extract_message(raw_postcat: str) -> str:
    candidates = ("Received:", "Return-Path:", "From:", "Date:", "Message-ID:")
    starts: list[int] = []
    for marker in candidates:
        pos = raw_postcat.find("\n" + marker)
        if pos >= 0:
            starts.append(pos + 1)
        elif raw_postcat.startswith(marker):
            starts.append(0)
    return raw_postcat[min(starts):] if starts else raw_postcat


def parse_message(queue_id: str):
    raw = extract_message(postcat(queue_id))
    msg = email.message_from_string(raw, policy=policy.default)
    return raw, msg


def get_bodies(msg):
    text_body = None
    html_body = None

    if msg.is_multipart():
        for part in msg.walk():
            if (part.get_content_disposition() or "").lower() == "attachment":
                continue
            try:
                content = part.get_content()
            except Exception:
                continue

            if part.get_content_type() == "text/plain" and text_body is None:
                text_body = str(content)
            elif part.get_content_type() == "text/html" and html_body is None:
                html_body = str(content)
    else:
        try:
            content = msg.get_content()
        except Exception:
            content = ""

        if msg.get_content_type() == "text/html":
            html_body = str(content)
        else:
            text_body = str(content)

    return text_body, html_body


def get_attachments(msg):
    result = []
    for index, part in enumerate(msg.walk()):
        filename = part.get_filename()
        disposition = (part.get_content_disposition() or "").lower()
        if filename or disposition == "attachment":
            result.append(
                {
                    "index": index,
                    "filename": decode_mime(filename) or f"attachment-{index}",
                    "content_type": part.get_content_type(),
                    "size": len(part.get_payload(decode=True) or b""),
                }
            )
    return result


@app.get("/")
def index():
    messages = []

    for row in queue_json():
        queue_id = row.get("queue_id")
        if not queue_id:
            continue

        try:
            _, msg = parse_message(queue_id)
            subject = decode_mime(msg.get("Subject")) or "(no subject)"
        except Exception:
            subject = "(unable to read subject)"

        recipients = row.get("recipients", []) or []

        messages.append(
            {
                "id": queue_id,
                "sender": row.get("sender", ""),
                "recipients": [
                    recipient.get("address", "")
                    for recipient in recipients
                    if isinstance(recipient, dict)
                ],
                "subject": subject,
                "arrival_time": row.get("arrival_time"),
                "message_size": row.get("message_size"),
                "delay_reason": "; ".join(
                    recipient.get("delay_reason", "")
                    for recipient in recipients
                    if isinstance(recipient, dict) and recipient.get("delay_reason")
                ),
            }
        )

    messages.sort(key=lambda item: item.get("arrival_time") or 0, reverse=True)
    return render_template("index.html", title=APP_TITLE, messages=messages)


@app.get("/message/<queue_id>")
def message_view(queue_id):
    raw, msg = parse_message(queue_id)
    text_body, html_body = get_bodies(msg)

    return render_template(
        "message.html",
        title=APP_TITLE,
        queue_id=queue_id,
        sender=decode_mime(msg.get("From")),
        to=decode_mime(msg.get("To")),
        cc=decode_mime(msg.get("Cc")),
        subject=decode_mime(msg.get("Subject")) or "(no subject)",
        date=decode_mime(msg.get("Date")),
        text_body=text_body,
        html_body=html_body,
        headers=[(key, decode_mime(value)) for key, value in msg.items()],
        attachments=get_attachments(msg),
        raw=raw,
    )


@app.get("/message/<queue_id>/attachment/<int:part_index>")
def attachment(queue_id, part_index):
    _, msg = parse_message(queue_id)
    parts = list(msg.walk())

    if part_index < 0 or part_index >= len(parts):
        abort(404)

    part = parts[part_index]
    data = part.get_payload(decode=True)
    if data is None:
        abort(404)

    filename = decode_mime(part.get_filename()) or f"attachment-{part_index}"

    return send_file(
        BytesIO(data),
        mimetype=part.get_content_type(),
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@app.get("/health")
def health():
    try:
        run_cmd(["postqueue", "-j"])
        return {"ok": True}, 200
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500
