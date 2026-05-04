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

        # --- NEW: Save the keys and Doc ID to local memory so they persist ---
        self.main_window.save_config(self.slite_api_key, self.notion_api_key, doc_id)

        self.main_window.terminal_box.configure(state="normal")
        self.main_window.terminal_box.delete("0.0", "end")
        self.main_window.terminal_box.configure(state="disabled")

        self.main_window.append_log(f"--- STARTING MIGRATION ---", "info")

        def extraction_process():
            try:
                from pathlib import Path
                
                # ==========================================
                # PHASE 1: WORKSPACE INDEXING
                # ==========================================
                self.main_window.append_log("Phase 1: Indexing Workspace Structure...", "info")
                self.main_window.update_progress(0.02, "Phase 1: Indexing...")
                
                total_discovered = 0
                
                def build_tree_map(current_id):
                    nonlocal total_discovered
                    note_info = SliteAPI.get_note(self.slite_api_key, current_id)
                    title = note_info.get("title", "Untitled")
                    
                    node = {"id": current_id, "title": title, "children": []}
                    total_discovered += 1
                    
                    visual_progress = min(0.10, total_discovered * 0.005)
                    self.main_window.update_progress(visual_progress, f"Indexing: Found {total_discovered} docs...")
                    
                    # ONLY fetch children if the user wants sub-docs included!
                    if include_subdocs:
                        kids = SliteAPI.get_children(self.slite_api_key, current_id)
                        for k in kids:
                            node["children"].append(build_tree_map(k["id"]))
                            
                    return node

                root_node = build_tree_map(doc_id)
                self.main_window.append_log(f"✓ Phase 1 Complete. Mapped {total_discovered} total documents.", "success")

                # ==========================================
                # PHASE 2: CONTENT MIGRATION
                # ==========================================
                self.main_window.append_log("Phase 2: Starting Content Migration...", "info")
                
                docs_processed = 0
                work_root = Path(local_path) if save_local and local_path else Path("./Slite_Export")
                
                stack = [(root_node, work_root, target_space_id)]
                
                while stack:
                    current_node, parent_dir, current_notion_parent = stack.pop()
                    
                    main_progress = 0.10 + (docs_processed / total_discovered) * 0.90
                    
                    self.main_window.update_progress(
                        main_progress, 
                        f"Migrating ({docs_processed+1}/{total_discovered}): {current_node['title'][:15]}...",
                        local_val=main_progress if save_local else 0.0,
                        notion_val=main_progress if push_to_notion else 0.0
                    )
                    
                    self.main_window.append_log(f"\nProcessing: {current_node['title']}", "info")
                    
                    note_data = SliteAPI.get_note(self.slite_api_key, current_node["id"])
                    md_content = note_data.get("content") or ""
                    
                    # --- LOCAL HTML LOGIC ---
                    this_dir = parent_dir / HTMLEngine.sanitize_dir(current_node["title"])
                    if save_local:
                        i = 2
                        base = this_dir
                        while this_dir.exists():
                            this_dir = base.parent / f"{base.name} ({i})"
                            i += 1
                        HTMLEngine.generate_html(current_node["title"], md_content, this_dir)
                        self.main_window.append_log(f"  ↳ Saved local HTML", "success")

                    # --- NOTION PUSH LOGIC ---
                    new_notion_page_id = current_notion_parent
                    if push_to_notion:
                        notion_blocks = NotionTranslator.parse_slite_to_notion_blocks(md_content)
                        total_blocks = len(notion_blocks)
                        
                        success, result = NotionAPI.create_page(self.notion_api_key, current_notion_parent, current_node["title"], notion_blocks)
                        
                        if success:
                            new_notion_page_id = result
                            self.main_window.append_log(f"  ↳ Page created in Notion ({min(total_blocks, 100)} blocks)", "success")
                            
                            if total_blocks > 100:
                                self.main_window.append_log(f"  ↳ Large document detected. Appending {total_blocks - 100} remaining blocks...", "warn")
                                
                                for i in range(100, total_blocks, 100):
                                    chunk = notion_blocks[i:i+100]
                                    chunk_ratio = min(1.0, (i + len(chunk)) / total_blocks)
                                    self.main_window.update_progress(
                                        main_progress, 
                                        f"Uploading blocks {i} to {i+len(chunk)}...",
                                        notion_val=chunk_ratio
                                    )
                                    
                                    app_success, app_msg = NotionAPI.append_blocks(self.notion_api_key, new_notion_page_id, chunk)
                                    if app_success:
                                        self.main_window.append_log(f"    ↳ Appended blocks {i} to {i+len(chunk)}", "success")
                                    else:
                                        self.main_window.append_log(f"    ↳ Append Failed: {app_msg}", "error")
                                        break
                                    
                                    time.sleep(0.4) 
                        else:
                            self.main_window.append_log(f"  ↳ Notion Push Failed: {result}", "error")

                    docs_processed += 1
                    
                    for child in reversed(current_node["children"]):
                        stack.append((child, this_dir, new_notion_page_id))

                self.main_window.append_log(f"\n✅ Migration Complete! Successfully transferred {total_discovered} documents.", "success")
                self.main_window.update_progress(1.0, f"Transfer Complete ({total_discovered} docs)", local_val=1.0 if save_local else 0.0, notion_val=1.0 if push_to_notion else 0.0)

            except Exception as e:
                self.main_window.append_log(f"🔴 Fatal Error: {str(e)}", "error")

        threading.Thread(target=extraction_process, daemon=True).start()