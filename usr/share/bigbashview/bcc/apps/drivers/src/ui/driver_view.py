"""
Driver View

This module provides the DriverView class for displaying drivers.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GObject, Gio
from typing import List, Dict, Any, Optional
import logging

# Assuming DriverManager is in the parent 'src' package
from ..driver_manager import DriverManager

logger = logging.getLogger(__name__)

class DriverView(Gtk.Box):
    """
    A widget to display and manage a list of drivers.
    """
    def __init__(self, driver_manager: DriverManager, category: Optional[str] = None):
        """
        Initialize the DriverView.

        Args:
            driver_manager: An instance of DriverManager.
            category: Optional category to filter drivers by ('detected', 'proprietary', 'free').
                      If None, shows all drivers (or a default set).
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.driver_manager = driver_manager
        self.category = category # Store the category if provided

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.model = None # Will be a Gio.ListStore
        self._create_ui()
        self.refresh()

    def _create_ui(self) -> None:
        """Create the UI components for the driver view."""
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        self.append(scrolled_window)

        # Using Gtk.ListBox and Adwaita styling
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list") # Adwaita style for grouped lists
        scrolled_window.set_child(self.list_box)

    def _create_driver_row(self, driver_data: Dict[str, Any]) -> Adw.ActionRow:
        """Creates a row for a single driver."""
        row = Adw.ActionRow()
        row.set_title(driver_data.get("name", "Unknown Driver"))
        row.set_subtitle(driver_data.get("description", "No description available."))
        
        # Example: Add an install/uninstall button
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_suffix(button_box)

        if driver_data.get("installed"):
            action_button = Gtk.Button(label="Uninstall")
            action_button.get_style_context().add_class("destructive-action")
            action_button.connect("clicked", self._on_uninstall_clicked, driver_data)
        else:
            action_button = Gtk.Button(label="Install")
            action_button.get_style_context().add_class("suggested-action")
            action_button.connect("clicked", self._on_install_clicked, driver_data)
        
        button_box.append(action_button)
        
        # Add an icon based on whether it's free or proprietary (optional)
        icon_name = "drive-harddisk-symbolic" # Default icon
        if driver_data.get("free") is False: # Proprietary
            icon_name = "security-high-symbolic" 
        elif driver_data.get("free") is True: # Free
            icon_name = "security-low-symbolic" 
        
        row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))

        return row

    def refresh(self, drivers_list: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Refresh the list of drivers displayed.
        If drivers_list is provided, it uses that list. Otherwise, fetches from DriverManager.
        """
        logger.info(f"DriverView ({self.category or 'all'}): Refreshing view...")
        
        # Clear existing children from list_box
        child = self.list_box.get_first_child()
        while child:
            self.list_box.remove(child)
            child = self.list_box.get_first_child()

        if drivers_list is None:
            # Fetch drivers based on category
            if self.category == "detected":
                drivers_list = self.driver_manager.get_detected_drivers()
            elif self.category == "proprietary":
                drivers_list = self.driver_manager.get_proprietary_drivers()
            elif self.category == "free":
                drivers_list = self.driver_manager.get_free_drivers()
            else: # Default: show all drivers if no specific category or an unknown one
                drivers_list = self.driver_manager.get_all_drivers()
        
        if not drivers_list:
            label = Gtk.Label(label=f"No drivers found{(' for category: ' + self.category) if self.category else ''}.")
            label.set_halign(Gtk.Align.CENTER)
            label.set_valign(Gtk.Align.CENTER)
            label.set_vexpand(True)
            self.list_box.append(label)
        else:
            for driver_data in drivers_list:
                row = self._create_driver_row(driver_data)
                self.list_box.append(row)
        logger.info(f"DriverView ({self.category or 'all'}): Displaying {len(drivers_list)} drivers.")


    def filter_drivers(self, search_text: str) -> None:
        """
        Filter the displayed drivers based on search text.
        This is a basic implementation. For large lists, consider Gtk.FilterListModel.
        """
        logger.info(f"DriverView ({self.category or 'all'}): Filtering with text '{search_text}'")
        search_text_lower = search_text.lower()
        
        # Fetch initial list based on category
        if self.category == "detected":
            all_category_drivers = self.driver_manager.get_detected_drivers()
        elif self.category == "proprietary":
            all_category_drivers = self.driver_manager.get_proprietary_drivers()
        elif self.category == "free":
            all_category_drivers = self.driver_manager.get_free_drivers()
        else:
            all_category_drivers = self.driver_manager.get_all_drivers()

        if not search_text_lower:
            self.refresh(all_category_drivers) # Show all drivers for the category if search is empty
            return

        filtered_list = []
        for driver_data in all_category_drivers:
            if (search_text_lower in driver_data.get("name", "").lower() or
                search_text_lower in driver_data.get("description", "").lower()):
                filtered_list.append(driver_data)
        
        self.refresh(filtered_list)

    def _on_install_clicked(self, button: Gtk.Button, driver_data: Dict[str, Any]) -> None:
        """Handle install button click."""
        driver_id = driver_data.get("id")
        logger.info(f"DriverView: Install clicked for {driver_id}")
        if driver_id:
            # Here you would typically show a confirmation dialog or start a process
            # For now, just call the driver manager and refresh
            # In a real app, this would be asynchronous
            if self.driver_manager.install_driver(driver_id):
                # Update the specific driver's data or refresh the whole view
                self.refresh() 
            else:
                # Show error dialog
                self._show_error_dialog("Installation Failed", f"Could not install driver {driver_id}.")

    def _on_uninstall_clicked(self, button: Gtk.Button, driver_data: Dict[str, Any]) -> None:
        """Handle uninstall button click."""
        driver_id = driver_data.get("id")
        logger.info(f"DriverView: Uninstall clicked for {driver_id}")
        if driver_id:
            if self.driver_manager.uninstall_driver(driver_id):
                self.refresh()
            else:
                self._show_error_dialog("Uninstallation Failed", f"Could not uninstall driver {driver_id}.")
    
    def _show_error_dialog(self, title: str, message: str) -> None:
        """Shows a simple error dialog."""
        dialog = Adw.MessageDialog.new(self.get_ancestor(Gtk.Window), title, message)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", lambda d, r: d.close())
        dialog.present()

if __name__ == '__main__':
    # Example Usage (requires a Gtk Application loop)
    class TestApp(Adw.Application):
        def __init__(self, **kwargs):
            super().__init__(application_id="com.example.testdriverview", **kwargs)
            self.connect("activate", self.on_activate)

        def on_activate(self, app):
            win = Adw.ApplicationWindow(application=app)
            win.set_default_size(600, 400)
            
            # Create a dummy DriverManager
            logging.basicConfig(level=logging.INFO)
            manager = DriverManager()
            
            # Create DriverView
            # driver_view_all = DriverView(manager) # All drivers
            # driver_view_prop = DriverView(manager, category="proprietary") # Proprietary
            driver_view_free = DriverView(manager, category="free") # Free

            # Simple layout for testing
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            search_entry = Gtk.SearchEntry(placeholder_text="Search in Free Drivers")
            search_entry.connect("search-changed", lambda e: driver_view_free.filter_drivers(e.get_text()))
            
            main_box.append(search_entry)
            main_box.append(driver_view_free)
            
            win.set_content(main_box)
            win.present()

    app = TestApp()
    app.run([])
