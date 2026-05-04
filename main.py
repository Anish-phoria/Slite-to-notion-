from controllers.main_controller import MainController
from views.main_window import MigrationApp

if __name__ == "__main__":
    # 1. Initialize the central controller
    app_controller = MainController()
    
    # 2. Initialize the main window, handing it the controller
    app = MigrationApp(app_controller)
    
    # Give the controller access to the main window
    app_controller.set_main_window(app)
    
    # 3. Start the application loop
    app.mainloop()