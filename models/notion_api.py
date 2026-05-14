import os
import math
import requests
import mimetypes

class NotionAPI:
    @staticmethod
    def _get_headers(api_key):
        """Helper to generate standard Notion API headers."""
        return {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2026-03-11",  # CRITICAL: Upgraded to access the File Upload API
            "Content-Type": "application/json"
        }

    @staticmethod
    def test_connection(api_key):
        url = "https://api.notion.com/v1/users/me"
        # Test connection doesn't need Content-Type
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2026-03-11" 
        }
        try:
            response = requests.get(url, headers=headers, timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    @staticmethod
    def get_available_spaces(api_key):
        url = "https://api.notion.com/v1/search"
        headers = NotionAPI._get_headers(api_key)
        
        payload = {
            "sort": {"direction": "descending", "timestamp": "last_edited_time"}
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                return False, f"API Error {response.status_code}"

            results = response.json().get("results", [])
            spaces = {}

            for item in results:
                title = "Untitled"
                try:
                    if item["object"] == "database":
                        if item.get("title"):
                            title = item["title"][0]["plain_text"]
                    elif item["object"] == "page":
                        properties = item.get("properties", {})
                        for prop_name, prop_data in properties.items():
                            if prop_data.get("type") == "title" and prop_data.get("title"):
                                title = prop_data["title"][0]["plain_text"]
                                break
                except (KeyError, IndexError):
                    pass
                
                if title != "Untitled":
                    spaces[title] = item["id"]

            return True, spaces
        except Exception as e:
            return False, str(e)
        
    @staticmethod
    def create_page(api_key, parent_id, title, blocks=None, is_database_row=False, row_properties=None):
        """Creates a new page. Upgraded to act as a standard sub-page OR a database row."""
        url = "https://api.notion.com/v1/pages"
        headers = NotionAPI._get_headers(api_key)
        
        if is_database_row:
            parent = {"type": "database_id", "database_id": parent_id}
        else:
            parent = {"type": "page_id", "page_id": parent_id}
            
        if is_database_row and row_properties:
            properties = row_properties
        else:
            properties = {"title": [{"text": {"content": title}}]}
            
        payload = {
            "parent": parent,
            "properties": properties
        }
        
        if blocks:
            payload["children"] = blocks[:100]
            
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                return True, response.json()["id"] 
            else:
                return False, f"Error {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def append_blocks(api_key, block_id, blocks):
        """Appends additional blocks to an existing page or block."""
        url = f"https://api.notion.com/v1/blocks/{block_id}/children"
        headers = NotionAPI._get_headers(api_key)
        
        payload = {"children": blocks}
        
        try:
            response = requests.patch(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                return True, "Success"
            else:
                return False, f"Error {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def create_database(api_key, parent_page_id, db_title, slite_columns):
        """Creates an inline database at the bottom of a parent page."""
        url = "https://api.notion.com/v1/databases"
        headers = NotionAPI._get_headers(api_key)
        
        properties = {"Name": {"title": {}}}
        
        for index, col_name in enumerate(slite_columns):
            safe_name = col_name if col_name.strip() else f"Column {index + 1}"
            col_lower = safe_name.lower()
            
            if "video" in col_lower or "link" in col_lower or "url" in col_lower:
                properties[safe_name] = {"url": {}}
            elif "tag" in col_lower or "status" in col_lower or "category" in col_lower:
                properties[safe_name] = {"multi_select": {}}
            elif "done" in col_lower or "check" in col_lower or "complete" in col_lower:
                properties[safe_name] = {"checkbox": {}}
            else:
                properties[safe_name] = {"rich_text": {}}
                    
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": db_title}}],
            "properties": properties,
            "is_inline": True
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                return True, response.json()["id"]
            else:
                return False, f"API Error {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    # ───────────────────── NEW DIRECT UPLOAD METHOD ─────────────────────
    
    @staticmethod
    def upload_file(api_key, file_path):
        """
        Handles Notion Direct Upload with a strict 5MB single-part threshold.
        Forces multi-part mode for files over 5MB to avoid validation errors.
        """
        import mimetypes
        import math
        
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)[:250] 
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"
        
        # Notion API single-part limit is strictly 5 MiB
        LIMIT_5MB = 5 * 1024 * 1024 
        is_multipart = file_size > LIMIT_5MB
        
        # Use 5MB chunks for multi-part to stay under the limit
        part_size = LIMIT_5MB
        num_parts = math.ceil(file_size / part_size) if is_multipart else 1
        
        # --- STEP 1: Request Upload Slot ---
        create_url = "https://api.notion.com/v1/file_uploads"
        headers = NotionAPI._get_headers(api_key)
        
        payload = {
            "filename": filename,
            "content_type": mime_type
        }
        if is_multipart:
            payload["mode"] = "multi_part"
            payload["number_of_parts"] = num_parts
            
        try:
            resp1 = requests.post(create_url, headers=headers, json=payload, timeout=10)
            if resp1.status_code != 200:
                return False, f"Upload Step 1 Failed: {resp1.text}"
            
            upload_data = resp1.json()
            upload_id = upload_data["id"]
            
            # --- STEP 2: Send File Content ---
            upload_headers = {
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": "2026-03-11"
            }
            
            upload_endpoint = f"https://api.notion.com/v1/file_uploads/{upload_id}/send"
            send_url = upload_data.get("upload_url", upload_endpoint)
            
            if not is_multipart:
                with open(file_path, 'rb') as f:
                    # Include mime_type to prevent Step 2 mismatch
                    files = {'file': (filename, f, mime_type)}
                    resp2 = requests.post(send_url, headers=upload_headers, files=files, timeout=60)
                    if resp2.status_code != 200:
                        return False, f"Upload Step 2 Failed: {resp2.text}"
            else:
                complete_url = upload_data.get("complete_url", f"https://api.notion.com/v1/file_uploads/{upload_id}/complete")
                
                with open(file_path, 'rb') as f:
                    for part_num in range(1, num_parts + 1):
                        chunk = f.read(part_size)
                        files = {'file': (filename, chunk, mime_type)}
                        data = {'part_number': part_num}
                        
                        resp2 = requests.post(send_url, headers=upload_headers, data=data, files=files, timeout=60)
                        if resp2.status_code != 200:
                            return False, f"Upload Part {part_num} Failed: {resp2.text}"
                            
                # Compile Multi-part Upload
                resp3 = requests.post(complete_url, headers=headers, json={}, timeout=15)
                if resp3.status_code != 200:
                    return False, f"Upload Complete Failed: {resp3.text}"
            
            return True, upload_id
            
        except Exception as e:
            return False, str(e)