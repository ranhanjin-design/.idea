"""Chat Markdown formatter used by midterm UI contract tests.

Keeps presentation rules explicit: tables become real HTML tables,
links become clickable anchors, raw `| ... |` source must not remain.
"""

from __future__ import annotations

import html
import re


def escape_html(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _split_row(line: str) -> list[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [c.strip() for c in raw.split("|")]


def _is_separator(line: str) -> bool:
    cells = _split_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells if c != "")


def _format_inline(text: str) -> str:
    text = escape_html(text)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer" class="chat-md-link">\1</a>',
        text,
    )
    text = re.sub(
        r"(?<![\w\"=>/])(https?://[^\s<]+)",
        r'<a href="\1" target="_blank" rel="noopener noreferrer" class="chat-md-link">\1</a>',
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return text


def format_chat_markdown(text: str) -> str:
    """Convert a limited Markdown subset to safe HTML for the chat bubble."""
    lines = (text or "").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "|" in line and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            header = _split_row(line)
            i += 2
            body: list[list[str]] = []
            while i < len(lines) and "|" in lines[i] and not _is_separator(lines[i]):
                body.append(_split_row(lines[i]))
                i += 1
            parts = [
                '<div class="chat-md-table-wrap"><table class="chat-md-table"><thead><tr>'
            ]
            for cell in header:
                parts.append(f"<th>{_format_inline(cell)}</th>")
            parts.append("</tr></thead><tbody>")
            for row in body:
                parts.append("<tr>")
                for idx in range(len(header)):
                    cell = row[idx] if idx < len(row) else ""
                    parts.append(f"<td>{_format_inline(cell)}</td>")
                parts.append("</tr>")
            parts.append("</tbody></table></div>")
            out.append("".join(parts))
            continue

        if line.strip() == "":
            out.append("<br>")
        else:
            out.append(_format_inline(line) + "<br>")
        i += 1

    html_out = "".join(out)
    # trim trailing single <br>
    if html_out.endswith("<br>"):
        html_out = html_out[:-4]
    return html_out
