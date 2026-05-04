import re
import os
import hashlib
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup
import markdown

try:
    from pygments.formatters import HtmlFormatter
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

class HTMLEngine:
    @staticmethod
    def sanitize_dir(name):
        return re.sub(r"[^a-zA-Z0-9._ \-]+", "", name).strip()[:100] or "Untitled"

    @staticmethod
    def fix_slite_markdown(md_text: str) -> str:
        if not md_text: return ""
        lines = md_text.replace('\r\n', '\n').expandtabs(2).split('\n')
        new_lines = []
        list_marker = re.compile(r'^(\s*)([\*\-\+]|\d+\.)(\s|$)')
        
        for i, line in enumerate(lines):
            if not line.strip():
                new_lines.append("")
                continue

            match_indent = re.match(r'^( +)(.*)', line)
            if match_indent:
                current_indent = match_indent.group(1)
                content = match_indent.group(2)
                new_indent = " " * (len(current_indent) * 2)
                line = new_indent + content
            
            line = re.sub(r'^(\s*\d+\.)([^\s])', r'\1 \2', line)
            line = re.sub(r'^(\s*[\*\-\+])([^\s])', r'\1 \2', line)

            if list_marker.match(line):
                if i > 0 and lines[i-1].strip() and not list_marker.match(new_lines[-1].strip()):
                     if new_lines[-1] != "": 
                         new_lines.append("")
            new_lines.append(line)
        return '\n'.join(new_lines)

    @staticmethod
    def download_asset(url: str, dest_folder: Path) -> str:
        if not url or url.startswith("data:"): return None
        try:
            hash_name = hashlib.md5(url.encode('utf-8')).hexdigest()
            path_clean = unquote(urlparse(url).path)
            ext = Path(path_clean).suffix or ".bin"
            filename = f"{hash_name}{ext}"
            local_path = dest_folder / filename
            if local_path.exists(): return filename
            r = requests.get(url, stream=True, timeout=30)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                return filename
        except Exception: pass
        return None

    @staticmethod
    def generate_html(title: str, md_content: str, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        fixed_md = HTMLEngine.fix_slite_markdown(md_content)
        
        url_pattern = re.compile(r'(?<!\]\()(?<!href=\")(?<!src=\")(https?://[^\s\)]+)')
        fixed_md = url_pattern.sub(r'<\1>', fixed_md)
        
        exts = ['fenced_code', 'tables', 'nl2br', 'sane_lists']
        if HAS_PYGMENTS: exts.append('codehilite')
        
        html = markdown.markdown(fixed_md, extensions=exts)
        
        # Process Assets
        soup = BeautifulSoup(html, "html.parser")
        assets_dir = folder / "_assets"
        assets_created = False

        for img in soup.find_all("img"):
            src = img.get("src")
            if src and src.startswith(("http", "//")):
                if not assets_created: assets_dir.mkdir(exist_ok=True); assets_created = True
                local_name = HTMLEngine.download_asset(src, assets_dir)
                if local_name: img['src'] = f"_assets/{local_name}"

        # Combine with your custom CSS wrapper
        pygments_css = HtmlFormatter(style='monokai').get_style_defs('.codehilite') if HAS_PYGMENTS else ""
        final_html = f"""
        <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>{title}</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #1a1a1a; color: #e0e0e0; padding: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            img, video {{ max-width: 100%; border-radius: 8px; }}
            {pygments_css}
        </style></head><body><div class="container"><h1>{title}</h1>{str(soup)}</div></body></html>
        """
        (folder / "index.html").write_text(final_html, encoding="utf-8")