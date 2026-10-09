/**
 * Midterm chat Markdown formatter.
 * Contract mirrored by pawplan/web/chat_markdown.py for unit tests.
 */
(function (global) {
  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function splitRow(line) {
    let raw = line.trim();
    if (raw.startsWith("|")) raw = raw.slice(1);
    if (raw.endsWith("|")) raw = raw.slice(0, -1);
    return raw.split("|").map((c) => c.trim());
  }

  function isSeparator(line) {
    const cells = splitRow(line).filter((c) => c !== "");
    if (!cells.length) return false;
    return cells.every((c) => /^:?-{3,}:?$/.test(c.replace(/\s/g, "")));
  }

  function formatInline(text) {
    let s = escapeHtml(text);
    s = s.replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-md-link">$1</a>'
    );
    s = s.replace(
      /(^|[^"'>])(https?:\/\/[^\s<]+)/g,
      '$1<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-md-link">$2</a>'
    );
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    return s;
  }

  function formatChatMarkdown(text) {
    const lines = String(text || "").split(/\r?\n/);
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (line.includes("|") && i + 1 < lines.length && isSeparator(lines[i + 1])) {
        const header = splitRow(line);
        i += 2;
        const body = [];
        while (i < lines.length && lines[i].includes("|") && !isSeparator(lines[i])) {
          body.push(splitRow(lines[i]));
          i += 1;
        }
        let html = '<div class="chat-md-table-wrap"><table class="chat-md-table"><thead><tr>';
        header.forEach((cell) => {
          html += `<th>${formatInline(cell)}</th>`;
        });
        html += "</tr></thead><tbody>";
        body.forEach((row) => {
          html += "<tr>";
          for (let c = 0; c < header.length; c += 1) {
            html += `<td>${formatInline(row[c] || "")}</td>`;
          }
          html += "</tr>";
        });
        html += "</tbody></table></div>";
        out.push(html);
        continue;
      }
      if (line.trim() === "") out.push("<br>");
      else out.push(formatInline(line) + "<br>");
      i += 1;
    }
    let htmlOut = out.join("");
    if (htmlOut.endsWith("<br>")) htmlOut = htmlOut.slice(0, -4);
    return htmlOut;
  }

  global.formatChatMarkdown = formatChatMarkdown;
  global.escapeHtml = global.escapeHtml || escapeHtml;
})(typeof window !== "undefined" ? window : globalThis);
