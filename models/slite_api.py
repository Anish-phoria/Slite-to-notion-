import time
import requests
import urllib.request       
import base64
import json
from datetime import datetime

class SliteAPI:
    BASE_URL = "https://api.slite.com/v1"

    @staticmethod
    def test_connection(api_key):
        url = f"{SliteAPI.BASE_URL}/search-notes?hitsPerPage=1"
        headers = {"x-slite-api-key": api_key, "Accept": "application/json"}
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                return True, "Connected"
            elif response.status_code == 401:
                return False, "401: Invalid API Key"
            return False, f"Error {response.status_code}"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _request_with_retries(method, url, api_key, params=None, max_retries=5):
        headers = {"Accept": "application/json", "x-slite-api-key": api_key}
        backoff = 1.0
        for _ in range(max_retries):
            try:
                resp = requests.request(method, url, headers=headers, params=params, timeout=60)
                if resp.status_code == 429:
                    time.sleep(float(resp.headers.get("Retry-After", backoff)))
                    continue
                if resp.status_code >= 500:
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, 30.0)
                    continue
                return resp
            except requests.RequestException:
                time.sleep(backoff)
                continue
        resp = requests.request(method, url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        return resp

    @staticmethod
    def get_note(api_key, note_id):
        resp = SliteAPI._request_with_retries("GET", f"{SliteAPI.BASE_URL}/notes/{note_id}", api_key)
        return resp.json()

    @staticmethod
    def get_children(api_key, note_id):
        children = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else None
            resp = SliteAPI._request_with_retries(
                "GET",
                f"{SliteAPI.BASE_URL}/notes/{note_id}/children",
                api_key,
                params=params
            )
            data = resp.json()
            children.extend(data.get("notes") or data.get("children") or [])
            cursor = data.get("cursor")
            if not cursor:
                break
        return children

    # ───────────────────── NEW METHODS FOR COLLECTIONS ─────────────────────

    @staticmethod
    def get_note_metadata(api_key, note_id):
        """
        Fetches lightweight metadata for a note (no content body).
        Returns dict with keys:
            id, title, parentNoteId, url, createdAt, updatedAt
        """
        data = SliteAPI.get_note(api_key, note_id)
        return {
            "id": data.get("id"),
            "title": data.get("title", "Untitled"),
            "parentNoteId": data.get("parentNoteId"),
            "url": data.get("url", ""),
            "createdAt": data.get("createdAt", ""),
            "updatedAt": data.get("updatedAt", ""),
        }

    @staticmethod
    def deep_index(api_key, root_note_id, include_children=True):
        """
        DFS walk that returns a flat list of all reachable notes.
        Each note is a dict with keys: id, title, parentNoteId, depth.
        """
        result = []
        stack = [(root_note_id, 0)]  # (note_id, depth)
        while stack:
            current_id, depth = stack.pop()
            # Skip the root note itself (we only want its descendants)
            if depth > 0:
                meta = SliteAPI.get_note_metadata(api_key, current_id)
                result.append(meta)
            if include_children or depth == 0:
                children = SliteAPI.get_children(api_key, current_id)
                for child in children:
                    child_id = child.get("id")
                    if child_id:
                        stack.append((child_id, depth + 1))
        return result

    @staticmethod
    def build_collection_tree(api_key, root_note_id, include_children=True):
        """
        Builds a dict that groups notes by their immediate parent’s title.
        """
        all_notes = SliteAPI.deep_index(api_key, root_note_id, include_children)
        collections = {}
        orphans = []
        root_meta = SliteAPI.get_note_metadata(api_key, root_note_id)
        root_title = root_meta.get("title", "")

        for note in all_notes:
            parent_id = note.get("parentNoteId")
            if parent_id and parent_id != root_note_id:
                parent_meta = SliteAPI.get_note_metadata(api_key, parent_id)
                parent_name = parent_meta.get("title", "Unknown Collection")
            else:
                parent_name = None

            if parent_name:
                collections.setdefault(parent_name, []).append(note)
            else:
                orphans.append(note)

        return {"collections": collections, "orphans": orphans}

    # ───────────────────── NEW SCHEMA PEEK METHOD ─────────────────────

    @staticmethod
    def get_database_schema(api_key, first_child_id):
        """
        Peeks at the first child of a suspected database to extract column headers.
        Returns the list of column names, or None if no columns exist.
        """
        data = SliteAPI.get_note(api_key, first_child_id)
        return data.get("columns")
    
    @staticmethod
    def download_secure_attachment(api_key, url, save_path):
        """
        Surgical downloader with verbose logging. 
        Forces 'phoria' domain and prevents header leakage to Google.
        """
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        print(f"[SECURITY DEBUG] Sending Key: {api_key}...")
        # --- STEP 1: Domain Normalization ---
        # The curl test proved phoria.slite.com works while slite.com fails.
        if "slite.com" in url and "phoria.slite.com" not in url:
            url = url.replace("slite.com", "phoria.slite.com")

        slite_headers = {
            "User-Agent": user_agent,
            "x-slite-api-key": api_key.strip(),
            "Accept": "*/*"
        }
        
        try:
            print("\n" + "="*60)
            print("SLITE SECURE DOWNLOAD START")
            print(f"Target URL: {url[:120]}...")
            
            # Step A: Hit Slite but do NOT follow redirect automatically
            resp = requests.get(url, headers=slite_headers, allow_redirects=False, timeout=30)
            
            
            # Step B: Check for the hand-off to Google Cloud
            if resp.status_code in [301, 302, 303, 307, 308]:
                google_url = resp.headers.get('Location')
                print(f"DEBUG: Found Redirect to Google Storage")
                print(f"Google URL: {google_url[:100]}...")
                
                # Step C: Naked request to Google using urllib (no Slite headers allowed!)
                print("DEBUG: Initiating clean-header download from Google...")
                req = urllib.request.Request(google_url)
                req.add_header("User-Agent", user_agent)
                
                with urllib.request.urlopen(req, timeout=60) as response:
                    print(f"Google Response Status: {response.status}")
                    with open(save_path, 'wb') as out_file:
                        out_file.write(response.read())
                
                print("✓ SUCCESS: File saved to temporary path.")
                print("="*60 + "\n")
                print(f"Slite Response: {resp.status_code}")
                print("\n" + "-"*30)
                print(f"FINAL OUTGOING URL: {url}") # THIS IS THE CRITICAL LINE
                print("-"*30 + "\n")
                return True, save_path
            
            else:
                print(f"✖ FAIL: Slite rejected request. Status: {resp.status_code}")
                if resp.status_code == 403:
                    print(f"Slite Response: {resp.status_code}")
                    print("\n" + "-"*30)
                    print(f"FINAL OUTGOING URL: {url}") # THIS IS THE CRITICAL LINE
                    print("-"*30 + "\n")
                    print("ERROR: Check if the API key has permission for this Note ID.")
                print("="*60 + "\n")
                return False, f"Status {resp.status_code}"
            
        except Exception as e:
            print(f"⚠ EXCEPTION: {str(e)}")
            print("="*60 + "\n")
            return False, str(e)
        
    