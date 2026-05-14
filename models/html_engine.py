import re
import os
import hashlib
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup
import markdown
import urllib.request

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
    def download_asset(url: str, dest_folder: Path, api_key: str = None) -> str:
        if not url or url.startswith("data:"): return None
        try:
            # Filename generation logic
            clean_url_for_ext = url.split('?')[0]
            hash_name = hashlib.md5(url.encode('utf-8')).hexdigest()
            filename = f"{hash_name}{Path(unquote(urlparse(clean_url_for_ext).path)).suffix or '.bin'}"
            local_path = dest_folder / filename
            if local_path.exists(): return filename

            print(f"\n[HTML_ENGINE] Attempting asset download: {url[:60]}...")
            
            headers = {"x-slite-api-key": api_key, "User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, allow_redirects=False, timeout=20)
            
            if r.status_code in [301, 302, 307, 308]:
                google_url = r.headers.get('Location')
                # Naked request to Google via urllib
                req = urllib.request.Request(google_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        with open(local_path, 'wb') as f:
                            f.write(response.read())
                        return filename
            
            print(f"[HTML_ENGINE] Failed. Slite Status: {r.status_code}")
                
        except Exception as e:
            print(f"[HTML_ENGINE] Exception: {e}")
        return None

    @staticmethod
    def generate_html(title: str, md_content: str, folder: Path, progress_callback=None, api_key: str=None):
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

        images = soup.find_all("img")
        total_images = len(images)

        for idx, img in enumerate(images):
            if progress_callback:
                progress_callback(idx + 1, max(total_images, 1))
                
            src = img.get("src")
            # Account for Slite relative API paths too
            if src and (src.startswith(("http", "//")) or src.startswith("api/")):
                # Normalize relative Slite paths
                if src.startswith("api/"): src = f"https://slite.com/{src}"
                
                if not assets_created: 
                    assets_dir.mkdir(exist_ok=True)
                    assets_created = True
                    
                # --- NEW: Pass the API key to the downloader ---
                local_name = HTMLEngine.download_asset(src, assets_dir, api_key)
                
                if local_name: 
                    img['src'] = f"_assets/{local_name}"

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
