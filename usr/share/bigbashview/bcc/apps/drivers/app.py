#!/usr/bin/env python3
"""
BigLinux Driver Manager Application Launcher

This script launches the GTK4/Libadwaita driver manager application.
"""
import sys
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the current directory to the path to ensure imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import the main window module
from main_window import main

if __name__ == "__main__":
    # Make sure we're running with GTK4 and Adwaita
    os.environ["GTK_THEME"] = "Adwaita"
    
    # Run the application
    sys.exit(main())

"""
BigLinux Driver Manager Application

This module contains the main application class for the BigLinux Driver Manager.
"""
import gi
import logging
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add the current directory to sys.path to ensure modules can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

# Import page modules
from biglinux_hardware_info.hardware_info_page import HardwareInfoPage
from kernel_mesa_updater.kernel_mesa_page import KernelMesaPage
from driver_installer.driver_installer_page import DriverInstallerPage

# Set up logger
logger = logging.getLogger(__name__)

class DriverManagerApp(Adw.Application):
    """
    Main application class for the BigLinux Driver Manager.
    
    This class handles the application lifecycle, window creation,
    and view management.
    """
    
    def __init__(self, application_id: str) -> None:
        """
        Initialize the application.
        
        Args:
            application_id: The application ID
        """
        super().__init__(application_id=application_id,
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        
        # Application settings
        self.window: Optional[Adw.ApplicationWindow] = None
        self.pages: Dict[str, Gtk.Widget] = {}
        
        # Set application properties
        self.set_resource_base_path("/org/biglinux/drivermanager")
        
        # Connect signals
        self.connect("activate", self.on_activate)
    
    def on_activate(self, app: Adw.Application) -> None:
        """
        Handler for the 'activate' signal of the application.
        
        Args:
            app: The application instance
        """
        # Check if window already exists
        if not self.window:
            # Create the main application window
            self.window = Adw.ApplicationWindow(application=self)
            self.window.set_default_size(1000, 700)
            self.window.set_title("BigLinux Driver Manager")
            
            # Create the main UI components
            self._create_ui()
            
            # Load pages
            self._load_pages()
        
        # Show the window
        self.window.present()
    
    def _create_ui(self) -> None:
        """
        Create the main UI components.
        """
        # Create the main content box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Create a view stack for our pages
        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)
        
        # Create a header bar with a view switcher
        header_bar = Adw.HeaderBar()
        
        # Create a view switcher title and add it to the header bar
        self.view_switcher_title = Adw.ViewSwitcherTitle()
        self.view_switcher_title.set_title("BigLinux Driver Manager")
        self.view_switcher_title.set_stack(self.view_stack)
        header_bar.set_title_widget(self.view_switcher_title)
        
        # Add header bar to the main box
        main_box.append(header_bar)
        
        # Create a view switcher bar for the bottom of the window
        self.view_switcher_bar = Adw.ViewSwitcherBar()
        self.view_switcher_bar.set_stack(self.view_stack)
        
        # Add the view stack to the main box
        main_box.append(self.view_stack)
        
        # Add the view switcher bar to the main box
        main_box.append(self.view_switcher_bar)
        
        # Set the content of the window
        self.window.set_content(main_box)
        
        # Connect to window size events to show/hide the bottom switcher bar
        self.window.connect("notify::default-width", self._on_window_size_changed)
    
    def _on_window_size_changed(self, window, param):
        """
        Handle window size changes to show/hide the bottom switcher bar.
        
        Args:
            window: The window that changed size
            param: The parameter that changed
        """
        # Show the bottom switcher when window is narrow
        width = window.get_default_width()
        is_narrow = width < 600
        self.view_switcher_title.set_title_visible(not is_narrow)
        self.view_switcher_bar.set_reveal(is_narrow)
    
    def _load_pages(self) -> None:
        """
        Load and add all application pages.
        """
        # Create and add the Hardware Information page
        hardware_page = HardwareInfoPage()
        self._add_page(hardware_page, "hardware-info", "Hardware Information", "computer-symbolic")
        
        # Create and add the Kernel and Mesa Update page
        kernel_mesa_page = KernelMesaPage()
        self._add_page(kernel_mesa_page, "kernel-mesa", "Kernel and Mesa Updates", "system-software-update-symbolic")
        
        # Create and add the Driver Installer page
        driver_installer_page = DriverInstallerPage()
        self._add_page(driver_installer_page, "driver-installer", "Driver Installer", "preferences-system-devices-symbolic")
    
    def _add_page(self, page: Gtk.Widget, page_id: str, title: str, icon_name: str) -> None:
        """
        Add a page to the view stack.
        
        Args:
            page: The page widget to add
            page_id: Unique ID for the page
            title: Title to display in the view switcher
            icon_name: Name of the icon to use for the page
        """
        # Store the page in our dictionary
        self.pages[page_id] = page
        
        # Create an icon for the page
        icon = Gio.ThemedIcon.new(icon_name)
        
        # Add the page to the view stack with title and icon
        self.view_stack.add_titled_with_icon(page, page_id, title, icon_name)
