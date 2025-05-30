#!/usr/bin/env python3
"""
BigLinux Driver Manager

Main application entry point for the GTK4 version of the BigLinux Driver Manager.
"""
import gi
import os
import sys
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.expanduser('~/.config/bigcontrolcenter-drivers/debug.log'))
    ]
)

logger = logging.getLogger(__name__)

# Ensure the application can find its modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import GTK and Application modules
try:
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw, Gio, GLib
    
    # Import our application modules
    from driver_installer.main_window import MainWindow
    
except ImportError as e:
    logger.critical(f"Failed to import required modules: {e}")
    print(f"Error: Failed to import required modules: {e}")
    print("Make sure GTK4, libadwaita, and required Python packages are installed.")
    sys.exit(1)

class DriverManagerApp(Adw.Application):
    """Main application class for BigLinux Driver Manager."""
    
    def __init__(self):
        """Initialize the application."""
        super().__init__(
            application_id="br.com.biglinux.driver-manager",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        
        # Create config directory if it doesn't exist
        os.makedirs(os.path.expanduser("~/.config/bigcontrolcenter-drivers"), exist_ok=True)
        
        # Connect signals
        self.connect("activate", self._on_activate)
        
        logger.info("Application initialized")
    
    def _on_activate(self, app):
        """Handle application activation."""
        logger.info("Application activated")
        
        # Check for existing windows
        existing_windows = self.get_windows()
        if existing_windows:
            # Reuse existing window
            window = existing_windows[0]
            window.present()
            return
        
        # Create and show the main window
        window = MainWindow(self)
        window.present()

def main():
    """Run the application."""
    app = DriverManagerApp()
    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())
