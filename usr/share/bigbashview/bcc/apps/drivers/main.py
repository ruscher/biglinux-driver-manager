#!/usr/bin/env python3
"""
BigLinux Driver Manager - Main Entry Point

This is the main entry point for the BigLinux Driver Manager application.
It initializes the GTK application and starts the main window.
"""
import gi
import sys
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("biglinux-driver-manager")

# Setup GTK imports
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

# Import our application class
from app import DriverManagerApp

def main():
    """Main function that starts the application."""
    # Set application ID
    app_id = "org.biglinux.drivermanager"
    
    # Initialize libadwaita
    Adw.init()
    
    # Create and run the application
    app = DriverManagerApp(application_id=app_id)
    
    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())
