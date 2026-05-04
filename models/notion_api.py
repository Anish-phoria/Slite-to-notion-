import requests

class NotionAPI:
    @staticmethod
    def _get_headers(api_key):
        """Helper to generate standard Notion API headers."""
        return {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    @staticmethod
    def test_connection(api_key):
        url = "https://api.notion.com/v1/users/me"
        # Test connection doesn't need Content-Type
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28" 
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
        
        # Sort by recently edited so the most relevant spaces show up first
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
                    # Logic for Databases
                    if item["object"] == "database":
                        if item.get("title"):
                            title = item["title"][0]["plain_text"]
                    
                    # Logic for Pages
                    elif item["object"] == "page":
                        properties = item.get("properties", {})
                        # Find whichever property acts as the 'title'
                        for prop_name, prop_data in properties.items():
                            if prop_data.get("type") == "title" and prop_data.get("title"):
                                title = prop_data["title"][0]["plain_text"]
                                break
                except (KeyError, IndexError):
                    pass # Fallback to "Untitled" if parsing fails
                
                # Use the extracted title as the dictionary key, and the ID as the value
                if title != "Untitled":
                    spaces[title] = item["id"]

            return True, spaces

        except Exception as e:
            return False, str(e)
        
    @staticmethod
    def create_page(api_key, parent_id, title, blocks=None, is_database_row=False, row_properties=None):
        """
        Creates a new page. Upgraded to act as a standard sub-page OR a database row.
        """
        url = "https://api.notion.com/v1/pages"
        headers = NotionAPI._get_headers(api_key)
        
        # 1. Determine the parent type (Page vs Database)
        if is_database_row:
            parent = {"type": "database_id", "database_id": parent_id}
        else:
            parent = {"type": "page_id", "page_id": parent_id}
            
        # 2. Setup the Properties (Metadata)
        if is_database_row and row_properties:
            properties = row_properties
        else:
            # Default fallback for a standard page
            properties = {
                "title": [
                    {"text": {"content": title}}
                ]
            }
            
        payload = {
            "parent": parent,
            "properties": properties
        }
        
        # 3. Attach initial blocks if we have them (Max 100 allowed by Notion)
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
        """
        Creates an inline database at the bottom of a parent page.
        Automatically maps Slite column headers to Notion property schemas.
        """
        url = "https://api.notion.com/v1/databases"
        headers = NotionAPI._get_headers(api_key)
        
        # --- SCHEMA MAPPING HEURISTIC ---
        properties = {}
        
        for index, col_name in enumerate(slite_columns):
            safe_name = col_name if col_name.strip() else f"Column {index + 1}"
            
            # First column is always the Notion Title
            if index == 0:
                properties[safe_name] = {"title": {}}
            else:
                col_lower = safe_name.lower()
                # Map obvious links to URL properties
                if "video" in col_lower or "link" in col_lower or "url" in col_lower:
                    properties[safe_name] = {"url": {}}
                # Default everything else to rich_text to prevent API crashes
                else:
                    properties[safe_name] = {"rich_text": {}}
                    
        payload = {
            "parent": {
                "type": "page_id",
                "page_id": parent_page_id
            },
            "title": [
                {
                    "type": "text",
                    "text": {"content": db_title}
                }
            ],
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