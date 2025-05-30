"""
Driver Manager Category View

This module provides a GTK4/Libadwaita interface for the driver manager with a
navigation split view to browse drivers by category.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, GObject

import sys
import os
import logging
from typing import Dict, List, Any, Optional

# Import driver lister module
from driver_installer.driver_lister import list_all_drivers, CATEGORY_LABELS

# Setup logger
logger = logging.getLogger(__name__)

class DriverRow(Adw.ActionRow):
    """Row representing a driver in the list."""
    
    def __init__(self, driver_info: Dict[str, Any]):
        super().__init__()
        
        self.driver_info = driver_info
        
        # Set up the row
        self.set_title(driver_info["name"])
        self.set_subtitle(driver_info["description"])
        
        # Add install/remove button based on installation status
        button = Gtk.Button()
        if driver_info.get("installed", False):
            button.set_label("Remove")
            button.add_css_class("destructive-action")
        else:
            button.set_label("Install")
            button.add_css_class("suggested-action")
        
        button.connect("clicked", self._on_button_clicked)
        self.add_suffix(button)
        
        # Add status icon
        if driver_info.get("installed", False):
            icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            self.add_prefix(icon)
            self.add_css_class("success")
    
    def _on_button_clicked(self, button):
        # Handle installation/removal logic here
        package = self.driver_info["package"]
        installed = self.driver_info.get("installed", False)
        
        if installed:
            # TODO: Implement package removal
            logger.info(f"Removing package: {package}")
            # You can implement actual removal here
            button.set_label("Install")
            button.remove_css_class("destructive-action")
            button.add_css_class("suggested-action")
            self.driver_info["installed"] = False
        else:
            # TODO: Implement package installation
            logger.info(f"Installing package: {package}")
            # You can implement actual installation here
            button.set_label("Remove")
            button.remove_css_class("suggested-action")
            button.add_css_class("destructive-action") 
            self.driver_info["installed"] = True


class DriverCategoryView(Adw.Application):
    """Main application for Driver Manager with category navigation."""
    
    def __init__(self):
        super().__init__(
            application_id="org.biglinux.driver-manager",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        
        self.connect("activate", self._on_activate)
        self.drivers_by_category = {}
        
    def _on_activate(self, app):
        # Create main window
        self.window = Adw.ApplicationWindow(application=app)
        self.window.set_default_size(900, 600)
        self.window.set_title("BigLinux Driver Manager")
        
        # Create main box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Create header bar
        header = Adw.HeaderBar()
        main_box.append(header)
        
        # Create navigation split view
        self.split_view = Adw.NavigationSplitView()
        main_box.append(self.split_view)
        
        # Create sidebar
        sidebar = Adw.NavigationPage()
        sidebar_toolbar_view = Adw.ToolbarView()
        sidebar_toolbar_view.add_css_class("background")
        
        sidebar_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_content.set_margin_top(12)
        sidebar_content.set_margin_bottom(12)
        sidebar_content.set_margin_start(12)
        sidebar_content.set_margin_end(12)
        
        # Create list box for categories
        self.category_list = Gtk.ListBox()
        self.category_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.category_list.add_css_class("navigation-sidebar")
        self.category_list.connect("row-selected", self._on_category_selected)
        
        # Add an "All Drivers" option
        all_row = Adw.ActionRow()
        all_row.set_title("All Drivers")
        all_row.set_icon_name("view-grid-symbolic")
        all_row.category_key = "all"
        self.category_list.append(all_row)
        
        # Load drivers and populate categories
        self._load_drivers()
        
        # Create category rows
        for category_key, category_label in CATEGORY_LABELS.items():
            if category_key in self.drivers_by_category:
                row = Adw.ActionRow()
                row.set_title(category_label)
                
                # Set appropriate icon based on category
                icon_name = self._get_icon_for_category(category_key)
                row.set_icon_name(icon_name)
                
                # Store category key in the row for later reference
                row.category_key = category_key
                
                # Add count badge
                count = len(self.drivers_by_category.get(category_key, []))
                if count > 0:
                    badge = Gtk.Label(label=str(count))
                    badge.add_css_class("badge")
                    badge.add_css_class("numeric")
                    row.add_suffix(badge)
                
                self.category_list.append(row)
        
        sidebar_content.append(self.category_list)
        sidebar_toolbar_view.set_content(sidebar_content)
        sidebar.set_child(sidebar_toolbar_view)
        
        # Create content area
        self.content_page = Adw.NavigationPage()
        self.content_view = Adw.ToolbarView()
        self.content_view.add_css_class("background")
        
        self.content_header = Adw.HeaderBar()
        self.content_view.add_top_bar(self.content_header)
        
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.set_margin_top(12)
        self.content_box.set_margin_bottom(12)
        self.content_box.set_margin_start(12)
        self.content_box.set_margin_end(12)
        
        self.content_view.set_content(self.content_box)
        self.content_page.set_child(self.content_view)
        
        # Set initial title
        self.content_page.set_title("All Drivers")
        
        # Add sidebar and content to split view
        self.split_view.set_sidebar(sidebar)
        self.split_view.set_content(self.content_page)
        
        # Show the all drivers view initially
        self._populate_drivers_list("all")
        
        # Set window content and show
        self.window.set_content(main_box)
        self.window.present()
    
    def _load_drivers(self):
        """Load drivers and organize them by category."""
        all_drivers = list_all_drivers()
        
        # Group by category
        self.drivers_by_category = {"all": all_drivers}
        
        for driver in all_drivers:
            category = driver.get("category", "unknown")
            if category not in self.drivers_by_category:
                self.drivers_by_category[category] = []
            self.drivers_by_category[category].append(driver)
    
    def _get_icon_for_category(self, category: str) -> str:
        """Get an appropriate icon name for a category."""
        icons = {
            "gpu": "graphics-card-symbolic",
            "wifi": "network-wireless-symbolic",
            "ethernet": "network-wired-symbolic",
            "bluetooth": "bluetooth-symbolic",
            "printer": "printer-symbolic",
            "printer3d": "printer-symbolic",
            "scanner": "scanner-symbolic",
            "dvb": "tv-symbolic",
            "webcam": "camera-web-symbolic",
            "touchscreen": "input-touchscreen-symbolic",
            "sound": "audio-card-symbolic",
            "firmware": "application-x-firmware-symbolic"
        }
        return icons.get(category, "application-x-executable-symbolic")
    
    def _on_category_selected(self, listbox, row):
        """Handle category selection."""
        if row is None:
            return
        
        category_key = getattr(row, "category_key", "all")
        
        # Update content title
        if category_key == "all":
            self.content_page.set_title("All Drivers")
        else:
            self.content_page.set_title(CATEGORY_LABELS.get(category_key, "Drivers"))
        
        # Populate drivers list for the selected category
        self._populate_drivers_list(category_key)
    
    def _populate_drivers_list(self, category_key: str):
        """Populate the drivers list for the selected category."""
        # Clear existing content
        while child := self.content_box.get_first_child():
            self.content_box.remove(child)
        
        # Get drivers for this category
        drivers = self.drivers_by_category.get(category_key, [])
        
        if not drivers:
            label = Gtk.Label(label="No drivers found for this category")
            label.add_css_class("dim-label")
            self.content_box.append(label)
            return
        
        # Create ListBox for drivers
        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        
        # Add driver rows
        for driver in drivers:
            row = DriverRow(driver)
            listbox.append(row)
        
        self.content_box.append(listbox)


def main():
    """Run the application."""
    app = DriverCategoryView()
    return app.run(sys.argv)

if __name__ == "__main__":
    main()
