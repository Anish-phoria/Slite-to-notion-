import requests

class NotionAPI:
    @staticmethod
    def test_connection(api_key):
        url = "https://api.notion.com/v1/users/me"
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
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
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
    def create_page(api_key, parent_page_id, title, blocks):
        url = "https://api.notion.com/v1/pages"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        # Slices the array to ensure we NEVER send more than 100 blocks on creation
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {
                "title": [
                    {"text": {"content": title}}
                ]
            },
            "children": blocks[:100] 
        }
        
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
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        payload = {"children": blocks}
        
        try:
            response = requests.patch(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                return True, "Success"
            else:
                return False, f"Error {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)