import threading
import time
from tkinter import filedialog
from models.slite_api import SliteAPI
from models.notion_api import NotionAPI
from pathlib import Path
from models.html_engine import HTMLEngine
from models.translator import NotionTranslator

class MainController:
    def __init__(self):
        # 1. Set default states
        self.prefs_window = None
        self.main_window = None
        self.selected_local_path = ""
        
        self.slite_api_key = ""
        self.notion_api_key = ""
        self.notion_spaces_map = {} # Maps "Page Name" -> "uuid-1234"

    def set_main_window(self, window):
        # 2. Attach the window
        self.main_window = window
        
        # 3. NOW pull the saved keys from the UI's memory into the controller!
        self.slite_api_key = self.main_window.saved_config.get("slite_key", "")
        self.notion_api_key = self.main_window.saved_config.get("notion_key", "")
        
        # --- NEW: Auto-fetch Notion spaces on boot if we have a key! ---
        if self.notion_api_key:
            self.main_window.append_log("Found saved Notion API key. Auto-fetching spaces...", "info")
            
            # We run this in a quick background thread so it doesn't freeze 
            # your UI while it talks to the Notion servers during startup.
            threading.Thread(target=self.fetch_notion_spaces, daemon=True).start()

    def set_preferences_window(self, window):
        self.prefs_window = window

    def select_local_folder(self):
        # Opens standard macOS folder picker
        folder_selected = filedialog.askdirectory(title="Select Backup Folder")
        if folder_selected:
            self.selected_local_path = folder_selected
            self.main_window.update_local_path_label(folder_selected)

    def test_slite_connection(self):
        api_key = self.prefs_window.get_slite_key()
        if not api_key:
            self.prefs_window.update_slite_status("error", "Key cannot be empty")
            return

        self.prefs_window.update_slite_status("loading")

        def run_test():
            success, message = SliteAPI.test_connection(api_key)
            if success:
                self.slite_api_key = api_key # Save to memory for later
                self.prefs_window.update_slite_status("success", message)
            else:
                self.slite_api_key = None
                self.prefs_window.update_slite_status("error", message)

        threading.Thread(target=run_test, daemon=True).start()

    def test_notion_connection(self):
        api_key = self.prefs_window.get_notion_key()
        if not api_key:
            self.prefs_window.update_notion_status("error", "Key cannot be empty")
            return

        self.prefs_window.update_notion_status("loading")

        def run_test():
            success = NotionAPI.test_connection(api_key)
            if success:
                self.notion_api_key = api_key # Save to memory for later
                self.prefs_window.update_notion_status("success", "Connected")
            else:
                self.notion_api_key = None
                self.prefs_window.update_notion_status("error", "Connection Failed")

        threading.Thread(target=run_test, daemon=True).start()

    def fetch_notion_spaces(self):
        if not self.notion_api_key:
            self.main_window.update_space_dropdown(["⚠️ Configure Notion API First"])
            return

        # Show loading state in the UI dropdown
        self.main_window.update_space_dropdown(["Fetching spaces..."])

        def run_fetch():
            success, result = NotionAPI.get_available_spaces(self.notion_api_key)
            if success:
                self.notion_spaces_map = result # Save the {Title: ID} dictionary
                space_names = list(result.keys())
                
                if space_names:
                    self.main_window.update_space_dropdown(space_names)
                else:
                    self.main_window.update_space_dropdown(["No connected pages found"])
            else:
                self.main_window.update_space_dropdown(["Error fetching spaces"])

        threading.Thread(target=run_fetch, daemon=True).start()

    def start_transfer(self):
        doc_id = self.main_window.doc_id_entry.get().strip()
        target_space_name = self.main_window.space_dropdown.get()
        target_space_id = self.notion_spaces_map.get(target_space_name, None)
        
        # Capture the toggle states
        push_to_notion = self.main_window.push_switch.get() == 1
        include_subdocs = self.main_window.subdoc_switch.get() == 1
        save_local = self.main_window.local_switch.get() == 1
        local_path = self.selected_local_path

        if not self.slite_api_key:
            self.main_window.append_log("🔴 Error: Slite API Key not configured.", "error")
            return
        if push_to_notion and not target_space_id:
            self.main_window.append_log("🔴 Error: Please select a valid Target Notion Space.", "error")
            return
        if not doc_id:
            self.main_window.append_log("🔴 Error: Document ID is empty.", "error")
            return

        self.main_window.save_config(self.slite_api_key, self.notion_api_key, doc_id)

        self.main_window.terminal_box.configure(state="normal")
        self.main_window.terminal_box.delete("0.0", "end")
        self.main_window.terminal_box.configure(state="disabled")
        self.main_window.append_log(f"--- STARTING MIGRATION ---", "info")

        def extraction_process():
            try:
                import time
                from pathlib import Path
                
                # ==========================================
                # PHASE 1: WORKSPACE INDEXING & CACHING
                # ==========================================
                self.main_window.append_log("Phase 1: Indexing Workspace Structure & Schemas...", "info")
                self.main_window.update_progress(0.02, "Phase 1: Indexing...")
                
                total_discovered = 0
                
                def build_tree_map(current_id, is_db_row=False, parent_schema=None):
                    nonlocal total_discovered
                    
                    # We fetch the full note once and cache it to prevent the "Double-Fetch" bottleneck
                    note_info = SliteAPI.get_note(self.slite_api_key, current_id)
                    
                    title = note_info.get("title", "Untitled")
                    icon_shape = note_info.get("iconShape")
                    is_database = (icon_shape == "#collection_table")
                    
                    node = {
                        "id": current_id, 
                        "title": title, 
                        "content": note_info.get("content", ""),
                        "is_database": is_database,
                        "is_db_row": is_db_row,
                        "attributes": note_info.get("attributes", []),
                        "parent_schema": parent_schema,
                        "db_schema": None,
                        "children": []
                    }
                    
                    total_discovered += 1
                    visual_progress = min(0.10, total_discovered * 0.005)
                    self.main_window.update_progress(visual_progress, f"Indexing: Found {total_discovered} docs...")
                    
                    if include_subdocs:
                        kids = SliteAPI.get_children(self.slite_api_key, current_id)
                        
                        # If this is a database, peek at the first child to get the column schema
                        db_schema = None
                        if is_database and kids:
                            db_schema = SliteAPI.get_database_schema(self.slite_api_key, kids[0]["id"])
                            node["db_schema"] = db_schema
                            self.main_window.append_log(f"  ↳ Discovered Database: {title}", "warn")
                            
                        for k in kids:
                            # If parent is a database, the children are flagged as rows
                            node["children"].append(build_tree_map(k["id"], is_db_row=is_database, parent_schema=db_schema))
                            
                    return node

                root_node = build_tree_map(doc_id)
                self.main_window.append_log(f"✓ Phase 1 Complete. Mapped {total_discovered} total documents.", "success")

                # ==========================================
                # PHASE 2: CONTENT MIGRATION
                # ==========================================
                self.main_window.append_log("Phase 2: Starting Content Migration...", "info")
                
                docs_processed = 0
                docs_processed_local = 0
                docs_processed_notion = 0
                
                active_pipelines = (1 if save_local else 0) + (1 if push_to_notion else 0)
                if active_pipelines == 0: active_pipelines = 1 
                
                work_root = Path(local_path) if save_local and local_path else Path("./Slite_Export")
                stack = [(root_node, work_root, target_space_id)]
                
                while stack:
                    current_node, parent_dir, current_notion_parent = stack.pop()
                    title = current_node['title']
                    md_content = current_node["content"]
                    
                    # --- DYNAMIC PROGRESS CALCULATOR ---
                    def refresh_ui(notion_chunk_progress=0.0, local_chunk_progress=0.0, custom_text=None):
                        l_val = ((docs_processed_local + local_chunk_progress) / total_discovered) if save_local else 0.0
                        n_val = ((docs_processed_notion + notion_chunk_progress) / total_discovered) if push_to_notion else 0.0
                        combo_val = (l_val + n_val) / active_pipelines if (save_local or push_to_notion) else (docs_processed / total_discovered)
                        main_val = 0.10 + (combo_val * 0.90)
                        text = custom_text or f"Migrating ({docs_processed+1}/{total_discovered}): {title[:15]}..."
                        self.main_window.update_progress(main_val, text, local_val=l_val, notion_val=n_val)

                    refresh_ui(custom_text=f"Reading: {title[:15]}...")
                    self.main_window.append_log(f"\nProcessing: {title}", "info")
                    
                    # --- 1. LOCAL HTML LOGIC ---
                    this_dir = parent_dir / HTMLEngine.sanitize_dir(title)
                    if save_local:
                        refresh_ui(custom_text=f"Saving Local: {title[:15]}...")
                        i = 2
                        base = this_dir
                        while this_dir.exists():
                            this_dir = base.parent / f"{base.name} ({i})"
                            i += 1
                            
                        def local_progress_ping(current_item, total_items):
                            ratio = current_item / max(total_items, 1) 
                            refresh_ui(local_chunk_progress=ratio, custom_text=f"Downloading assets ({current_item}/{total_items})...")

                        HTMLEngine.generate_html(title, md_content, this_dir, progress_callback=local_progress_ping)
                        self.main_window.append_log(f"  ↳ Saved local HTML", "success")
                        docs_processed_local += 1 

                    # --- 2. NOTION PUSH LOGIC ---
                    new_notion_parent_for_children = current_notion_parent                    
                    if push_to_notion:
                        notion_blocks = NotionTranslator.parse_slite_to_notion_blocks(md_content)
                        total_blocks = len(notion_blocks)
                        
                        # 1. CREATE THE NODE (As a Row OR a Standard Page)
                        if current_node.get("is_db_row"):
                            refresh_ui(custom_text=f"Injecting Row: {title[:15]}...")
                            
                            # --- MAGIC FIX 1: Target the system ID "title" directly ---
                            row_props = {"title": {"title": [{"text": {"content": title}}]}}
                            
                            schema = current_node.get("parent_schema") or ["Column 1"]
                            attrs = current_node.get("attributes") or []
                            
                            for idx, col_name in enumerate(schema):
                                safe_name = col_name if col_name.strip() else f"Column {idx + 1}"
                                # Prevent Slite from overwriting the primary Notion key
                                if safe_name.lower() in ["name", "title"]: 
                                    safe_name = f"{safe_name} (Slite Data)"
                                    
                                val = attrs[idx] if idx < len(attrs) else ""
                                col_lower = safe_name.lower()
                                
                                if "video" in col_lower or "link" in col_lower or "url" in col_lower:
                                    row_props[safe_name] = {"url": val} if isinstance(val, str) and val.startswith("http") else {"url": None}
                                elif "tag" in col_lower or "status" in col_lower or "category" in col_lower:
                                    tags = []
                                    if isinstance(val, str) and val.strip():
                                        # --- MAGIC FIX 2: The corrected Python array parser! ---
                                        tags = [{"name": t.strip()[:100]} for t in val.split(",") if t.strip()]
                                    elif isinstance(val, list):
                                        tags = [{"name": str(t).strip()[:100]} for t in val if str(t).strip()]
                                    row_props[safe_name] = {"multi_select": tags}
                                elif "done" in col_lower or "check" in col_lower or "complete" in col_lower:
                                    is_checked = str(val).lower().strip() in ["true", "yes", "checked", "1", "x"]
                                    row_props[safe_name] = {"checkbox": is_checked}
                                else:
                                    str_val = str(val) if val is not None else ""
                                    row_props[safe_name] = {"rich_text": [{"text": {"content": str_val[:2000]}}]} if str_val else {"rich_text": []}

                            success, result = NotionAPI.create_page(
                                self.notion_api_key, current_notion_parent, title, notion_blocks[:100], 
                                is_database_row=True, row_properties=row_props
                            )
                            
                            # --- MAGIC FIX 3: Prevent Cascading Schema Errors ---
                            if not success:
                                # If this row fails to build, tell its children to just become normal pages 
                                # so they don't try to inject into the wrong database!
                                for child in current_node["children"]:
                                    child["is_db_row"] = False
                        else:
                            refresh_ui(custom_text=f"Creating Page: {title[:15]}...")
                            success, result = NotionAPI.create_page(self.notion_api_key, current_notion_parent, title, notion_blocks[:100])
                            
                        # 2. POST-CREATION ROUTING (Database Shells & Blocks)
                        if success:
                            new_notion_parent_for_children = result
                            self.main_window.append_log(f"  ↳ Node created in Notion", "success")
                            
                            # --- THE NESTED DATABASE FIX ---
                            # Whether it's a page or a row, if it's flagged as a DB, build the inline table inside it!
                            if current_node.get("is_database"):
                                self.main_window.append_log(f"  ↳ Building Inline Database...", "warn")
                                schema_to_use = current_node.get("db_schema")
                                if not schema_to_use: schema_to_use = ["Data"] 
                                    
                                db_success, db_result = NotionAPI.create_database(
                                    self.notion_api_key, result, f"{title} Database", schema_to_use
                                )
                                if db_success:
                                    new_notion_parent_for_children = db_result 
                                    self.main_window.append_log(f"  ↳ Inline Database created successfully", "success")
                                else:
                                    self.main_window.append_log(f"  ↳ Inline DB Failed: {db_result}", "error")
                                    # Safety Switch: Prevent children from crashing if the DB shell fails
                                    for child in current_node["children"]:
                                        child["is_db_row"] = False

                            # Handle remaining blocks (for both pages and rows)
                            if total_blocks > 100:
                                for i in range(100, total_blocks, 100):
                                    chunk = notion_blocks[i:i+100]
                                    chunk_ratio = min(1.0, (i + len(chunk)) / total_blocks)
                                    refresh_ui(notion_chunk_progress=chunk_ratio, custom_text=f"Uploading blocks {i} to {i+len(chunk)}...")
                                    NotionAPI.append_blocks(self.notion_api_key, result, chunk)
                                    time.sleep(0.4) 
                        else:
                            self.main_window.append_log(f"  ↳ Notion Push Failed: {result}", "error")

                        docs_processed_notion += 1
                        refresh_ui()

                    docs_processed += 1
                    
                    for child in reversed(current_node["children"]):
                        stack.append((child, this_dir, new_notion_parent_for_children))

                self.main_window.append_log(f"\n✅ Migration Complete! Successfully transferred {total_discovered} documents.", "success")
                self.main_window.update_progress(1.0, f"Transfer Complete ({total_discovered} docs)", local_val=1.0 if save_local else 0.0, notion_val=1.0 if push_to_notion else 0.0)

            except Exception as e:
                self.main_window.append_log(f"🔴 Fatal Error: {str(e)}", "error")

        threading.Thread(target=extraction_process, daemon=True).start()