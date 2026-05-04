import json
from pathlib import Path
import customtkinter as ctk
from views.preferences_window import PreferencesWindow

class MigrationApp(ctk.CTk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.title("Slite to Notion Converter")
        
        # --- NEW: Setup Config Path & Load Memory ---
        self.config_path = Path.home() / ".slite_notion_config.json"
        self.saved_config = self.load_config()

        # --- NEW: Center Window ---
        self.center_window(650, 750)
        
        self.preferences_window = None

        # --- Header ---
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=10, padx=20, fill="x")
        
        self.title_label = ctk.CTkLabel(self.header_frame, text="Transfer Data to Notion", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(side="left")
        
        self.settings_btn = ctk.CTkButton(self.header_frame, text="⚙️", width=30, fg_color="transparent", text_color=("black", "white"), command=self.open_preferences)
        self.settings_btn.pack(side="right")

        self.subtitle_label = ctk.CTkLabel(self, text="Move your workspace content seamlessly.", text_color="gray")
        self.subtitle_label.pack(anchor="w", padx=20, pady=(0, 20))

        # --- Step 1: Source Selection ---
        self.step1_frame = ctk.CTkFrame(self)
        self.step1_frame.pack(pady=10, padx=20, fill="x")
        
        ctk.CTkLabel(self.step1_frame, text="STEP 1: SOURCE SELECTION", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(15, 5))
        ctk.CTkLabel(self.step1_frame, text="Slite Document ID").pack(anchor="w", padx=15)
        
        self.doc_id_entry = ctk.CTkEntry(self.step1_frame, placeholder_text="e.g., SL-1984-XJ9")
        self.doc_id_entry.pack(fill="x", padx=15, pady=(0, 15))

        # --- Pre-fill Document ID from Memory ---
        if self.saved_config.get("doc_id"):
            self.doc_id_entry.insert(0, self.saved_config.get("doc_id"))

        # --- Step 2: Destination & Options ---
        self.step2_frame = ctk.CTkFrame(self)
        self.step2_frame.pack(pady=10, padx=20, fill="x")
        
        ctk.CTkLabel(self.step2_frame, text="📁 STEP 2: DESTINATION & OPTIONS", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(15, 5))
        ctk.CTkLabel(self.step2_frame, text="Target Notion Space").pack(anchor="w", padx=15)
        
        # Dropdown and Refresh Button Frame
        self.dropdown_frame = ctk.CTkFrame(self.step2_frame, fg_color="transparent")
        self.dropdown_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        self.space_dropdown = ctk.CTkOptionMenu(self.dropdown_frame, values=["Click refresh to load spaces..."])
        self.space_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.refresh_btn = ctk.CTkButton(self.dropdown_frame, text="↻", width=30, command=self.controller.fetch_notion_spaces)
        self.refresh_btn.pack(side="right")

        # --- Toggles Row 1 (Horizontal Frame) ---
        self.toggles_row1_frame = ctk.CTkFrame(self.step2_frame, fg_color="transparent")
        self.toggles_row1_frame.pack(fill="x", padx=15, pady=10)

        self.push_switch = ctk.CTkSwitch(self.toggles_row1_frame, text="Push directly to Notion")
        self.push_switch.select() 
        self.push_switch.pack(side="left")

        self.subdoc_switch = ctk.CTkSwitch(self.toggles_row1_frame, text="Include Sub-docs")
        self.subdoc_switch.select() # Default to ON
        self.subdoc_switch.pack(side="left", padx=(40, 0)) # 40px padding to separate them

        # --- Toggles Row 2 ---
        self.local_switch = ctk.CTkSwitch(self.step2_frame, text="Save a local copy", command=self.toggle_local_path)
        self.local_switch.pack(anchor="w", padx=15, pady=(0, 15))

        # --- Hidden Folder Picker (Only shows if local switch is ON) ---
        self.local_path_frame = ctk.CTkFrame(self.step2_frame, fg_color="transparent")
        
        self.local_path_entry = ctk.CTkEntry(self.local_path_frame, placeholder_text="No folder selected...")
        self.local_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.local_path_entry.configure(state="disabled") # Make it read-only for the user
        
        self.local_path_btn = ctk.CTkButton(self.local_path_frame, text="Browse...", width=80, command=self.controller.select_local_folder)
        self.local_path_btn.pack(side="right")

        # --- Start Button ---
        self.start_btn = ctk.CTkButton(self, text="▶ Start Transfer", height=40, command=self.controller.start_transfer)
        self.start_btn.pack(anchor="e", padx=20, pady=10)

        # --- Progress Area ---
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(pady=5, padx=20, fill="x")
        
        # Main Progress
        self.main_status_frame = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.main_status_frame.pack(fill="x")
        self.status_label = ctk.CTkLabel(self.main_status_frame, text="Ready to transfer...", font=ctk.CTkFont(weight="bold"))
        self.status_label.pack(side="left")
        self.main_pct_label = ctk.CTkLabel(self.main_status_frame, text="0%")
        self.main_pct_label.pack(side="right")
        
        self.main_progress = ctk.CTkProgressBar(self.progress_frame)
        self.main_progress.pack(fill="x", pady=(5, 15))
        self.main_progress.set(0)

        # Sub Progress Bars (Local & Notion)
        self.sub_progress_frame = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.sub_progress_frame.pack(fill="x")

        # Local Cache Bar
        self.local_prog_frame = ctk.CTkFrame(self.sub_progress_frame, fg_color="transparent")
        self.local_prog_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.local_lbl_frame = ctk.CTkFrame(self.local_prog_frame, fg_color="transparent")
        self.local_lbl_frame.pack(fill="x")
        ctk.CTkLabel(self.local_lbl_frame, text="Local Cache", text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left")
        self.local_pct_label = ctk.CTkLabel(self.local_lbl_frame, text="0%", text_color="gray", font=ctk.CTkFont(size=11))
        self.local_pct_label.pack(side="right")
        
        self.local_progress = ctk.CTkProgressBar(self.local_prog_frame, height=6)
        self.local_progress.pack(fill="x", pady=(2, 0))
        self.local_progress.set(0)

        # Notion API Bar
        self.notion_prog_frame = ctk.CTkFrame(self.sub_progress_frame, fg_color="transparent")
        self.notion_prog_frame.pack(side="left", fill="x", expand=True, padx=(10, 0))
        
        self.notion_lbl_frame = ctk.CTkFrame(self.notion_prog_frame, fg_color="transparent")
        self.notion_lbl_frame.pack(fill="x")
        ctk.CTkLabel(self.notion_lbl_frame, text="Notion API", text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left")
        self.notion_pct_label = ctk.CTkLabel(self.notion_lbl_frame, text="0%", text_color="gray", font=ctk.CTkFont(size=11))
        self.notion_pct_label.pack(side="right")
        
        self.notion_progress = ctk.CTkProgressBar(self.notion_prog_frame, height=6)
        self.notion_progress.pack(fill="x", pady=(2, 0))
        self.notion_progress.set(0)

        # --- Terminal Output ---
        self.terminal_box = ctk.CTkTextbox(self, height=130, fg_color="#1e1e1e")
        self.terminal_box.pack(pady=15, padx=20, fill="both", expand=True)
        
        self.terminal_box.tag_config("info", foreground="white")
        self.terminal_box.tag_config("success", foreground="#4ade80")
        self.terminal_box.tag_config("warn", foreground="#facc15")
        self.terminal_box.tag_config("error", foreground="#f87171")
        
        self.terminal_box.insert("0.0", "System initialized. Waiting for transfer command...\n", "info")
        self.terminal_box.configure(state="disabled")


    # ==========================================
    # NEW METHODS: CENTERING & CONFIG MEMORY
    # ==========================================

    def center_window(self, width, height):
        """Forces the window to spawn dead-center on the primary monitor."""
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        x = int((screen_width / 2) - (width / 2))
        y = int((screen_height / 2) - (height / 2))
        
        self.geometry(f"{width}x{height}+{x}+{y}")

    def load_config(self):
        """Silently loads the saved API keys and data from the home directory."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self, slite_key, notion_key, doc_id=""):
        """Saves the API keys and Doc ID so they persist."""
        try:
            with open(self.config_path, "w") as f:
                json.dump({"slite_key": slite_key, "notion_key": notion_key, "doc_id": doc_id}, f)
        except Exception as e:
            print(f"Failed to save config: {e}")


    # ==========================================
    # EXISTING HELPER METHODS
    # ==========================================

    def append_log(self, text, level="info"):
        self.terminal_box.configure(state="normal")
        self.terminal_box.insert("end", f"{text}\n", level)
        self.terminal_box.see("end") 
        self.terminal_box.configure(state="disabled")

    def update_progress(self, main_val, main_text, local_val=None, notion_val=None):
        self.main_progress.set(main_val)
        self.status_label.configure(text=main_text)
        self.main_pct_label.configure(text=f"{int(main_val * 100)}%")
        
        if local_val is not None:
            self.local_progress.set(local_val)
            self.local_pct_label.configure(text=f"{int(local_val * 100)}%")
            
        if notion_val is not None:
            self.notion_progress.set(notion_val)
            self.notion_pct_label.configure(text=f"{int(notion_val * 100)}%")

    def open_preferences(self):
        if self.preferences_window is None or not self.preferences_window.winfo_exists():
            self.preferences_window = PreferencesWindow(self, self.controller)
            self.controller.set_preferences_window(self.preferences_window)
        else:
            self.preferences_window.focus()

    def toggle_local_path(self):
        if self.local_switch.get() == 1:
            self.local_path_frame.pack(fill="x", padx=15, pady=(5, 15))
        else:
            self.local_path_frame.pack_forget()

    def update_space_dropdown(self, spaces):
        self.space_dropdown.configure(values=spaces)
        if spaces:
            self.space_dropdown.set(spaces[0])
    
    def update_local_path_label(self, path):
        self.local_path_entry.configure(state="normal")
        self.local_path_entry.delete(0, "end")
        self.local_path_entry.insert(0, path)
        self.local_path_entry.configure(state="disabled")