import re

class NotionTranslator:
    # ----------------------------------------------------------------
    # Class-level constants & compiled patterns
    # ----------------------------------------------------------------
    INLINE_PATTERN = re.compile(
        r'(<mark>.*?</mark>|\[.*?\]\(.*?\)|\*\*.*?\*\*|~~.*?~~|\*.*?\*|`.*?`)'
    )

    HEADING_RE   = re.compile(r'^(#{1,6})\s+(.*)')
    MEDIA_RE     = re.compile(r'^!?\[(.*?)\]\((.*?)\)$')
    HINT_RE      = re.compile(r'>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](.*)', re.IGNORECASE)
    TODO_RE      = re.compile(r'^- \[([ xX])\] (.*)')
    BULLET_RE    = re.compile(r'^[-*] (.*)')
    NUMBERED_RE  = re.compile(r'^(\d+|[a-zA-Z])\.\s+(.*)')
    TABLE_SEP_RE = re.compile(r'^[\s\|-]+$')
    TABLE_ROW_RE = re.compile(r'^\|.+\|$')
    HR_PATTERN = re.compile(r'^(-{3,}|\*{3,}|_{3,})\s*$')

    # Cleanup helpers (compiled once)
    HEADING_IN_CELL_RE = re.compile(r'#{1,6}\s+')
    LIST_MARKER_RE = re.compile(r'(?m)^-\s+')
    STAR_MARKER_RE = re.compile(r'(?m)^\*\s+')

    VALID_LANGS = {
        "abap", "arduino", "bash", "basic", "c", "c++", "c#", "css", "dart",
        "diff", "docker", "elixir", "elm", "erlang", "flow", "fortran", "f#",
        "glsl", "go", "graphql", "groovy", "haskell", "html", "java",
        "javascript", "json", "julia", "kotlin", "latex", "less", "lisp",
        "livescript", "lua", "makefile", "markdown", "markup", "matlab",
        "mermaid", "nix", "objective-c", "ocaml", "pascal", "perl", "php",
        "plain text", "powershell", "prolog", "protobuf", "python", "r",
        "reason", "ruby", "rust", "sass", "scala", "scheme", "scss", "shell",
        "sql", "swift", "typescript", "vb.net", "verilog", "vhdl",
        "visual basic", "webassembly", "xml", "yaml"
    }
    LANG_ALIASES = {
        "js": "javascript", "ts": "typescript", "py": "python", "rb": "ruby",
        "sh": "bash"
    }

    # ----------------------------------------------------------------
    # Public entry point -- kept as a static method for compatibility
    # ----------------------------------------------------------------
    @staticmethod
    def parse_slite_to_notion_blocks(md_content):
        """Convenience static wrapper; creates a fresh instance per call."""
        translator = NotionTranslator()
        return translator.parse(md_content)

    # ----------------------------------------------------------------
    # Initialisation & state reset
    # ----------------------------------------------------------------
    def __init__(self):
        self.blocks = []
        self.stack = [(-1, self.blocks)]   # (indent, parent_list)

        # Multi-line state
        self._in_table = False
        self._table_buffer = []

        self._in_code_block = False
        self._code_buffer = []
        self._code_lang = "plain text"
        self._code_indent = -1

    def _reset_state(self):
        """Reset all parsing state before a new document."""
        self.blocks = []
        self.stack = [(-1, self.blocks)]
        self._in_table = False
        self._table_buffer = []
        self._in_code_block = False
        self._code_buffer = []
        self._code_lang = "plain text"
        self._code_indent = -1

    # ----------------------------------------------------------------
    # Main parse loop
    # ----------------------------------------------------------------
    def parse(self, md_content: str) -> list:
        if not md_content:
            return []
        self._reset_state()
        # Pre-processing
        md_content = self._preprocess_html(md_content)
        md_content = self._unescape(md_content)
        md_content = re.sub(r'<br\s*/?>', '\n', md_content, flags=re.IGNORECASE)
        lines = md_content.split('\n')
        for raw_line in lines:
            self._process_line(raw_line)
        self._flush_table()
        self._flush_code_block()
        self._remove_empty_children(self.blocks)
        return self.blocks

    @staticmethod
    def _preprocess_html(text):
        # Convert basic HTML to Markdown
        text = text.replace('<strong>', '**').replace('</strong>', '**')
        text = text.replace('<em>', '*').replace('</em>', '*')
        text = text.replace('<s>', '~~').replace('</s>', '~~')
        text = text.replace('<code>', '`').replace('</code>', '`')
        # <u> we keep for custom handling in inline parser
        return text

    @staticmethod
    def _unescape(text):
        return re.sub(r'\\([\\`*_{}\[\]()#+\-.!~|])', r'\1', text)

    # ----------------------------------------------------------------
    # Per-line dispatcher
    # ----------------------------------------------------------------
    def _process_line(self, raw_line: str):
        if self._in_code_block:
            self._handle_code_line(raw_line)
            return

        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip())

        # Empty lines flush tables but are otherwise ignored
        if not stripped:
            self._flush_table()
            return

        # Fenced code block start?
        if stripped.startswith('```'):
            self._flush_table()
            self._start_code_block(raw_line, indent)
            return

        # Table row?
        if self.TABLE_ROW_RE.match(stripped):
            self._in_table = True
            self._table_buffer.append(stripped)
            return
        else:
            self._flush_table()

        # Single-line block detection
        block = self._parse_block(stripped, indent)

        # ── NEW: if we are inside a list container and the current line
        #    is indented more than the list item, treat it as a child
        #    of that list item (continuation paragraph / code / etc.)
        if block is None and len(self.stack) > 1 and indent > self.stack[-1][0]:
            # The line didn't match any new block; treat as a paragraph
            # and add it directly to the current list item's children.
            block = {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": self.parse_inline_markdown(stripped)}
            }
            # Do NOT pop the stack – just append to the top‑level children
            self.stack[-1][1].append(block)
            return

        # If we still don't have a block, it's a normal top‑level paragraph
        if block is None:
            block = {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": self.parse_inline_markdown(stripped)}
            }

        # Use the standard nesting logic for list items themselves
        self._push_block(block, indent)

    # ----------------------------------------------------------------
    # Block-level parsers (each returns a dict or None)
    # ----------------------------------------------------------------
    def _parse_block(self, line: str, indent: int):
        # --- Media (images, audio, video) ---
        media = self._parse_media(line)
        if media:
            return media
        
        # --- Horizontal rule ---
        if self.HR_PATTERN.match(line):
            return {"object": "block", "type": "divider", "divider": {}}

        # --- Headings ---
        m = self.HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            type_name = f"heading_{min(level, 3)}"
            return {
                "object": "block", "type": type_name,
                type_name: {"rich_text": self.parse_inline_markdown(m.group(2))}
            }

        # --- Quotes & callouts ---
        if line.startswith('>'):
            return self._parse_quote_or_callout(line)

        # --- Checklists ---
        m = self.TODO_RE.match(line)
        if m:
            checked = m.group(1).lower() == 'x'
            return {
                "object": "block", "type": "to_do",
                "to_do": {
                    "rich_text": self.parse_inline_markdown(m.group(2).strip()),
                    "checked": checked
                },
                "_is_list": True
            }

        # --- Bulleted list ---
        m = self.BULLET_RE.match(line)
        if m:
            return {
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": self.parse_inline_markdown(m.group(1))},
                "_is_list": True
            }

        # --- Numbered list ---
        m = self.NUMBERED_RE.match(line)
        if m:
            return {
                "object": "block", "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": self.parse_inline_markdown(m.group(2))},
                "_is_list": True
            }

        # --- Fallback paragraph ---
        return {
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": self.parse_inline_markdown(line)}
        }

    def _parse_media(self, line: str):
        m = self.MEDIA_RE.match(line)
        if not m:
            return None
        caption_text = m.group(1)
        media_url = m.group(2)
        url_ext = media_url.split('?')[0].lower()   # strip query params

        if url_ext.endswith(('.mp4', '.mov', '.webm', '.mkv')):
            block = {"object": "block", "type": "video",
                     "video": {"type": "external", "external": {"url": media_url}}}
            if caption_text.strip():
                block["video"]["caption"] = self.parse_inline_markdown(caption_text.strip())
            return block

        if url_ext.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
            block = {"object": "block", "type": "audio",
                     "audio": {"type": "external", "external": {"url": media_url}}}
            if caption_text.strip():
                block["audio"]["caption"] = self.parse_inline_markdown(caption_text.strip())
            return block

        if line.startswith('!['):
            block = {"object": "block", "type": "image",
                     "image": {"type": "external", "external": {"url": media_url}}}
            if caption_text.strip():
                block["image"]["caption"] = self.parse_inline_markdown(caption_text.strip())
            return block

        # Fallback: if it looks like a media link but no extension matched,
        # treat as image (original behaviour)
        if line.startswith('!['):
            block = {"object": "block", "type": "image",
                     "image": {"type": "external", "external": {"url": media_url}}}
            if caption_text.strip():
                block["image"]["caption"] = self.parse_inline_markdown(caption_text.strip())
            return block

        return None

    def _parse_quote_or_callout(self, line: str):
        # Check for hint-style callouts
        m = self.HINT_RE.match(line)
        if m:
            hint_type = m.group(1).upper()
            hint_text = m.group(2).strip()

            icon, color = "💡", "gray_background"
            if hint_type in ("WARNING", "CAUTION"):
                icon, color = "⚠️", "orange_background"
            elif hint_type == "IMPORTANT":
                icon, color = "🔥", "red_background"
            elif hint_type == "NOTE":
                icon, color = "ℹ️", "blue_background"

            return {
                "object": "block", "type": "callout",
                "callout": {
                    "rich_text": self.parse_inline_markdown(hint_text),
                    "icon": {"type": "emoji", "emoji": icon},
                    "color": color
                }
            }

        # Standard blockquote
        return {
            "object": "block", "type": "quote",
            "quote": {"rich_text": self.parse_inline_markdown(line[1:].strip())}
        }

    # ----------------------------------------------------------------
    # Nesting logic
    # ----------------------------------------------------------------
    def _push_block(self, block: dict, indent: int):
        # Pop any nested blocks that are deeper than the current one
        while len(self.stack) > 1 and self.stack[-1][0] >= indent:
            self.stack.pop()

        parent_list = self.stack[-1][1]
        parent_list.append(block)

        # If the block is a list container, push a new level for its children
        is_list = block.pop("_is_list", False)
        if is_list:
            b_type = block["type"]
            block[b_type]["children"] = []
            self.stack.append((indent, block[b_type]["children"]))

    # ----------------------------------------------------------------
    # Code block state machine
    # ----------------------------------------------------------------
    def _start_code_block(self, raw_line: str, indent: int):
        self._in_code_block = True
        self._code_indent = indent
        raw_lang = raw_line.strip()[3:].strip().lower()
        raw_lang = self.LANG_ALIASES.get(raw_lang, raw_lang)
        self._code_lang = raw_lang if raw_lang in self.VALID_LANGS else "plain text"

    def _handle_code_line(self, raw_line: str):
        stripped = raw_line.strip()
        # Terminal fence?
        if stripped.startswith('```'):
            self._flush_code_block()
            return

        # Preserve relative indentation
        line_indent = len(raw_line) - len(raw_line.lstrip())
        if line_indent >= self._code_indent:
            clean = raw_line[self._code_indent:]
        else:
            clean = raw_line.lstrip()  # fallback for irregular content
        self._code_buffer.append(clean)

    def _flush_code_block(self):
        if not self._in_code_block:
            return
        code_text = '\n'.join(self._code_buffer) or " "

        # Chunk to respect 2000‑char limit per rich text object
        chunks = self._chunk_text(code_text)
        rich_text = [{"type": "text", "text": {"content": c}} for c in chunks]

        block = {
            "object": "block", "type": "code",
            "code": {"rich_text": rich_text, "language": self._code_lang}
        }

        # Pop the stack to the level where the code block was opened
        while len(self.stack) > 1 and self.stack[-1][0] >= self._code_indent:
            self.stack.pop()
        self.stack[-1][1].append(block)

        # Reset code state
        self._in_code_block = False
        self._code_buffer = []
        self._code_lang = "plain text"
        self._code_indent = -1

    # ----------------------------------------------------------------
    # Table state machine
    # ----------------------------------------------------------------
    def _flush_table(self):
        if not self._in_table:
            return
        table_block = self._process_table_buffer(self._table_buffer)
        if table_block:
            # Tables are always appended at the top level (original behaviour)
            self.blocks.append(table_block)
        self._in_table = False
        self._table_buffer = []

    def _process_table_buffer(self, buffer: list):
        """Convert raw markdown table lines into a Notion table block."""
        if not buffer:
            return None
        # Remove separator lines
        rows = [line for line in buffer if not self.TABLE_SEP_RE.match(line)]
        if not rows:
            return None

        first_row_cells = [c.strip() for c in rows[0].strip('|').split('|')]
        table_width = len(first_row_cells)
        table_children = []

        for row in rows:
            row_cells = [c.strip() for c in row.strip('|').split('|')]
            # Pad or trim to exact width
            while len(row_cells) < table_width:
                row_cells.append("")
            row_cells = row_cells[:table_width]

            notion_cells = []
            for cell in row_cells:
                cleaned = self._clean_table_cell(cell)
                notion_cells.append(self.parse_inline_markdown(cleaned))
            table_children.append({
                "object": "block",
                "type": "table_row",
                "table_row": {"cells": notion_cells}
            })

        return {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": table_width,
                "has_column_header": True,
                "has_row_header": False,
                "children": table_children
            }
        }

    # ----------------------------------------------------------------
    # Inline markdown parsing (unchanged logic, tuned for efficiency)
    # ----------------------------------------------------------------
    @staticmethod
    def parse_inline_markdown(text):
        if not text:
            return []

        parts = NotionTranslator.INLINE_PATTERN.split(text)
        rich_text_array = []

        for part in parts:
            if not part:
                continue
            if part.startswith('<mark>') and part.endswith('</mark>'):
                rich_text_array.extend(
                    NotionTranslator._make_rich_text(part[6:-7], annotations={"color": "yellow_background"})
                )
            elif part.startswith('[') and '](' in part and part.endswith(')'):
                link_text = part[1:part.index(']')]
                link_url = part[part.index('](')+2:-1]
                rich_text_array.extend(
                    NotionTranslator._make_rich_text(link_text, link_url=link_url)
                )
            elif part.startswith('**') and part.endswith('**'):
                rich_text_array.extend(
                    NotionTranslator._make_rich_text(part[2:-2], annotations={"bold": True})
                )
            elif part.startswith('*') and part.endswith('*'):
                rich_text_array.extend(
                    NotionTranslator._make_rich_text(part[1:-1], annotations={"italic": True})
                )
            elif part.startswith('`') and part.endswith('`'):
                rich_text_array.extend(
                    NotionTranslator._make_rich_text(part[1:-1], annotations={"code": True})
                )
            elif part.startswith('~~') and part.endswith('~~'):
                rich_text_array.extend(
                    NotionTranslator._make_rich_text(part[2:-2], annotations={"strikethrough": True})
                )
            elif part.startswith('<u>') and part.endswith('</u>'):
                rich_text_array.extend(
                    NotionTranslator._make_rich_text(part[3:-4], annotations={"underline": True})
                )
            else:
                rich_text_array.extend(NotionTranslator._make_rich_text(part))

        return rich_text_array

    # ----------------------------------------------------------------
    # Rich text chunking (word-boundary aware, respects 2000 char limit)
    # ----------------------------------------------------------------
    @staticmethod
    def _chunk_text(text: str) -> list:
        chunks = []
        while text:
            if len(text) <= 2000:
                chunks.append(text)
                break
            # Try to split at last space within the limit
            split_at = text.rfind(' ', 0, 2000)
            if split_at == -1:          # no space found, hard split
                split_at = 2000
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        return chunks

    @staticmethod
    def _make_rich_text(content, annotations=None, link_url=None):
        """Build a list of rich text objects, chunked to 2000 chars each."""
        if not content:
            return []
        objects = []
        for chunk in NotionTranslator._chunk_text(content):
            obj = {"type": "text", "text": {"content": chunk}}
            if annotations:
                obj["annotations"] = annotations
            if link_url:
                obj["text"]["link"] = {"url": link_url}
            objects.append(obj)
        return objects

    # ----------------------------------------------------------------
    # Table cell cleanup (same as original, but using compiled regex)
    # ----------------------------------------------------------------
    @staticmethod
    def _clean_table_cell(text):
        # Replace <br> variants with a single space (Notion rich text can't have newlines)
        text = re.sub(r'<br\s*/?>', ' ', text, flags=re.IGNORECASE)
        # Collapse multiple spaces into one
        text = re.sub(r' +', ' ', text)

        # Strip headings (they can't be rendered in a table cell)
        text = NotionTranslator.HEADING_IN_CELL_RE.sub('', text)

        # Checkbox markup → readable unicode equivalents
        text = text.replace('- [x]', '☑ ').replace('- [X]', '☑ ').replace('- [ ]', '☐ ')

        # Convert list markers to bullet characters (inline only, no nesting)
        text = NotionTranslator.LIST_MARKER_RE.sub('• ', text)
        text = NotionTranslator.STAR_MARKER_RE.sub('• ', text)

        # Turn images into inline links so they become clickable in the table cell
        #   ![alt](url)  →  [alt](url)   (the inline parser already handles links)
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'[\1](\2)', text)

        return text.strip()

    # ----------------------------------------------------------------
    # Recursively remove empty "children" lists (optional but tidy)
    # ----------------------------------------------------------------
    @staticmethod
    def _remove_empty_children(blocks):
        for block in blocks:
            b_type = block.get("type")
            if b_type and "children" in block[b_type]:
                if not block[b_type]["children"]:
                    del block[b_type]["children"]
                else:
                    NotionTranslator._remove_empty_children(block[b_type]["children"])