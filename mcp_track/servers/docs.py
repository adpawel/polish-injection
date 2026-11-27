"""`docs` server (trusted): the company's shared documents."""

from pathlib import Path
from typing import Annotated

from pydantic import Field

from mcp_track import world
from mcp_track.servers.common import Server, Variant, dump

DESCRIPTIONS = {
    "list_files": "Lists the documents under a directory (recursively) with their last modification date.",
    "read_file": "Returns the content of a document.",
    "write_file": "Creates a document or replaces its whole content.",
    "delete_file": "Deletes a document permanently.",
    "share_file": "Shares a document with an e-mail address (the recipient gets read access).",
    "list_shares": "Lists the e-mail addresses a document is shared with.",
}


def build(db_path: Path, variant: Variant = Variant()) -> Server:
    s = Server("docs", db_path, DESCRIPTIONS, variant)

    def existing(con, path: str):
        row = con.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
        if row is None:
            raise ValueError(f"file {path} not found")
        return row

    @s.tool
    def list_files(directory: Annotated[str, Field(description="Directory, e.g. / or /catalog.")] = "/") -> str:
        prefix = directory.rstrip("/") + "/"
        with s.db() as con:
            rows = [dict(r) for r in con.execute(
                "SELECT path, modified FROM files WHERE path LIKE ? ORDER BY path", (prefix + "%",))]
        return dump(rows) if rows else f"No files in {directory}."

    @s.tool
    def read_file(path: Annotated[str, Field(description="Full path, e.g. /policies/returns.txt.")]) -> str:
        with s.db() as con:
            return existing(con, path)["content"]

    @s.tool
    def write_file(
        path: Annotated[str, Field(description="Full path of the document.")],
        content: Annotated[str, Field(description="The whole new content.")],
    ) -> str:
        if not path.startswith("/"):
            raise ValueError("the path must start with /")
        with s.db() as con:
            con.execute("INSERT INTO files (path, content, modified) VALUES (?, ?, ?) "
                        "ON CONFLICT(path) DO UPDATE SET content = excluded.content, modified = excluded.modified",
                        (path, content, world.TODAY))
        return f"Saved {path}."

    @s.tool
    def delete_file(path: Annotated[str, Field(description="Full path of the document.")]) -> str:
        with s.db() as con:
            existing(con, path)
            con.execute("DELETE FROM files WHERE path = ?", (path,))
            con.execute("DELETE FROM file_shares WHERE path = ?", (path,))
        return f"Deleted {path}."

    @s.tool
    def share_file(
        path: Annotated[str, Field(description="Full path of the document.")],
        email: Annotated[str, Field(description="E-mail address to share with.")],
    ) -> str:
        with s.db() as con:
            existing(con, path)
            if not con.execute("SELECT 1 FROM file_shares WHERE path = ? AND email = ?", (path, email)).fetchone():
                con.execute("INSERT INTO file_shares VALUES (?, ?)", (path, email))
        return f"{path} is shared with {email}."

    @s.tool
    def list_shares(path: Annotated[str, Field(description="Full path of the document.")]) -> str:
        with s.db() as con:
            existing(con, path)
            emails = [r["email"] for r in con.execute("SELECT email FROM file_shares WHERE path = ?", (path,))]
        return dump(emails) if emails else f"{path} is not shared."

    return s
