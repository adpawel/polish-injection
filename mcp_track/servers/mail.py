"""`mail` server (trusted): the user's mailbox; the only channel out of the company."""

import json
from pathlib import Path
from typing import Annotated

from pydantic import Field

from mcp_track import world
from mcp_track.servers.common import Server, Variant, dump

DESCRIPTIONS = {
    "list_emails": "Lists the e-mails of a folder (inbox or sent), newest first, without their bodies.",
    "read_email": "Returns a whole e-mail and marks it as read.",
    "search_emails": "Finds e-mails whose sender, subject or body contains the query (case-insensitive).",
    "send_email": "Sends an e-mail from the user's address. Documents can be attached by their paths.",
}


def build(db_path: Path, variant: Variant = Variant()) -> Server:
    s = Server("mail", db_path, DESCRIPTIONS, variant)

    def summary(row) -> dict:
        email = world.row_dict("emails", row)
        return {k: email[k] for k in ("id", "date", "sender", "recipients", "subject", "read")}

    @s.tool
    def list_emails(
        folder: Annotated[str, Field(description="inbox or sent.")] = "inbox",
        unread_only: Annotated[bool, Field(description="Only unread e-mails.")] = False,
    ) -> str:
        if folder not in ("inbox", "sent"):
            raise ValueError("folder must be inbox or sent")
        with s.db() as con:
            rows = [summary(r) for r in con.execute(
                "SELECT * FROM emails WHERE folder = ?" + (" AND read = 0" if unread_only else "")
                + " ORDER BY date DESC, id DESC", (folder,))]
        return dump(rows) if rows else f"No e-mails in {folder}."

    @s.tool
    def read_email(email_id: Annotated[str, Field(description="E-mail ID, e.g. E101.")]) -> str:
        with s.db() as con:
            row = con.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
            if row is None:
                raise ValueError(f"e-mail {email_id} not found")
            con.execute("UPDATE emails SET read = 1 WHERE id = ?", (email_id,))
            email = world.row_dict("emails", row)
        return dump({**email, "read": 1})

    @s.tool
    def search_emails(query: Annotated[str, Field(description="Text to look for.")]) -> str:
        pattern = f"%{query.lower()}%"
        with s.db() as con:
            rows = [summary(r) for r in con.execute(
                "SELECT * FROM emails WHERE lower(sender) LIKE ? OR lower(subject) LIKE ? OR lower(body) LIKE ? "
                "ORDER BY date DESC, id DESC", (pattern, pattern, pattern))]
        return dump(rows) if rows else f"No e-mails match {query!r}."

    @s.tool
    def send_email(
        recipients: Annotated[list[str], Field(description="E-mail addresses of the recipients.")],
        subject: Annotated[str, Field(description="Subject.")],
        body: Annotated[str, Field(description="Text of the e-mail.")],
        attachments: Annotated[list[str] | None, Field(description="Paths of documents to attach.")] = None,
    ) -> str:
        if not recipients:
            raise ValueError("at least one recipient is needed")
        attachments = attachments or []
        with s.db() as con:
            missing = [p for p in attachments if not con.execute("SELECT 1 FROM files WHERE path = ?", (p,)).fetchone()]
            if missing:
                raise ValueError(f"attachment not found: {', '.join(missing)}")
            number = con.execute("SELECT COUNT(*) FROM emails WHERE folder = 'sent'").fetchone()[0]
            email_id = f"E{301 + number}"
            con.execute("INSERT INTO emails VALUES (?, 'sent', ?, ?, ?, ?, ?, ?, 1)",
                        (email_id, world.USER_EMAIL, json.dumps(recipients, ensure_ascii=False), subject, body,
                         json.dumps(attachments, ensure_ascii=False), world.TODAY))
        return f"E-mail {email_id} sent to {', '.join(recipients)}."

    return s
