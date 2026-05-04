import customtkinter as ctk

class PreferencesWindow(ctk.CTkToplevel):
    def __init__(self, master, controller, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.title("Preferences")
        self.geometry("500x350")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        
        self.controller = controller # Link to the controller

        # --- Slite Integration ---
        self.slite_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.slite_frame.pack(pady=20, padx=20, fill="x")
        
        ctk.CTkLabel(self.slite_frame, text="Slite Integration", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 10))
        
        self.slite_key_entry = ctk.CTkEntry(self.slite_frame, placeholder_text="API Key", show="*")
        self.slite_key_entry.pack(fill="x", pady=(0, 10))
        
        # Notice we bind the button to the controller's function
        self.slite_test_btn = ctk.CTkButton(self.slite_frame, text="⚡ Test Connection", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.controller.test_slite_connection)
        self.slite_test_btn.pack(side="left")
        
        self.slite_status = ctk.CTkLabel(self.slite_frame, text="⚪ Not Configured", text_color="gray")
        self.slite_status.pack(side="right")

        # --- Notion Integration ---
        self.notion_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.notion_frame.pack(pady=10, padx=20, fill="x")
        
        ctk.CTkLabel(self.notion_frame, text="Notion Integration", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 10))
        
        self.notion_key_entry = ctk.CTkEntry(self.notion_frame, placeholder_text="Integration Token", show="*")
        self.notion_key_entry.pack(fill="x", pady=(0, 10))
        
        self.notion_test_btn = ctk.CTkButton(self.notion_frame, text="⚡ Test Connection", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.controller.test_notion_connection)
        self.notion_test_btn.pack(side="left")
        
        self.notion_status = ctk.CTkLabel(self.notion_frame, text="⚪ Not Configured", text_color="gray")
        self.notion_status.pack(side="right")
    # ... (Keep all your existing UI init code) ...

    # --- Updated Helper functions for the Controller ---
    def get_slite_key(self):
        return self.slite_key_entry.get()

    def get_notion_key(self):
        return self.notion_key_entry.get()

    def update_slite_status(self, state, message=""):
        if state == "loading":
            self.slite_status.configure(text="🟡 Testing...", text_color="orange")
        elif state == "success":
            self.slite_status.configure(text=f"🟢 {message}", text_color="green")
        elif state == "error":
            # Now displays exactly WHY it failed
            self.slite_status.configure(text=f"🔴 {message}", text_color="red")

    def update_notion_status(self, state, message=""):
        if state == "loading":
            self.notion_status.configure(text="🟡 Testing...", text_color="orange")
        elif state == "success":
            self.notion_status.configure(text=f"🟢 {message}", text_color="green")
        elif state == "error":
            self.notion_status.configure(text=f"🔴 {message}", text_color="red")