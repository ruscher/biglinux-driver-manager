#!/usr/bin/env python3
"""
BigLinux Driver Manager - Main Window

A GTK4/Libadwaita application for managing drivers with a navigation split view.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, GObject

import sys
import os
import logging
import threading
from typing import Dict, List, Any, Optional

# Import driver module
from driver_installer.driver_lister import (
    list_all_drivers, 
    CATEGORY_LABELS,
    is_package_installed
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DriverInstallationRow(Adw.ActionRow):
    """A row displaying a driver with install/remove options."""
    
    def __init__(self, driver_info: Dict[str, Any], parent_window=None):
        super().__init__()
        
        self.driver_info = driver_info
        self.parent_window = parent_window
        
        # Set row information
        self.set_title(driver_info["name"])
        self.set_subtitle(driver_info.get("description", ""))
        
        # Status icon
        if driver_info.get("installed", False):
            status_icon = Gtk.Image(icon_name="emblem-ok-symbolic")
            self.add_prefix(status_icon)
            self.set_css_classes(["success"])
        
        # Action button
        self.action_button = Gtk.Button()
        if driver_info.get("installed", False):
            self.action_button.set_label("Remove")
            self.action_button.add_css_class("destructive-action")
        else:
            self.action_button.set_label("Install")
            self.action_button.add_css_class("suggested-action")
        
        self.action_button.connect("clicked", self.on_action_button_clicked)
        self.add_suffix(self.action_button)
        
        # Make rows activatable
        self.set_activatable(True)
        self.connect("activated", self.on_row_activated)
    
    def on_row_activated(self, row):
        """Show detailed information about the driver."""
        # This would show a dialog with more information
        dialog = Adw.MessageDialog(
            transient_for=self.parent_window,
            heading=self.driver_info["name"],
            body=f"Package: {self.driver_info['package']}\n"
                 f"Category: {self.driver_info['category_label']}\n"
                 f"Type: {self.driver_info['type']}\n"
                 f"Installed: {'Yes' if self.driver_info.get('installed', False) else 'No'}"
        )
        dialog.add_response("close", "Close")
        dialog.present()
    
    def on_action_button_clicked(self, button):
        """Handle driver installation or removal."""
        package = self.driver_info["package"]
        installed = self.driver_info.get("installed", False)
        
        if installed:
            # Remove driver
            self.action_button.set_sensitive(False)
            self.action_button.set_label("Removing...")
            
            # This would be an async call to remove the package
            threading.Thread(
                target=self._remove_package,
                args=(package,),
                daemon=True
            ).start()
        else:
            # Install driver
            self.action_button.set_sensitive(False)
            self.action_button.set_label("Installing...")
            
            # This would be an async call to install the package
            threading.Thread(
                target=self._install_package,
                args=(package,),
                daemon=True
            ).start()
    
    def _install_package(self, package):
        """Install a package (would execute real installation)."""
        # TODO: Replace with actual installation code
        GLib.timeout_add(2000, self._installation_completed, True)
    
    def _remove_package(self, package):
        """Remove a package (would execute real removal)."""
        # TODO: Replace with actual removal code
        GLib.timeout_add(2000, self._installation_completed, False)
    
    def _installation_completed(self, installed):
        """Update UI after installation/removal completes."""
        self.driver_info["installed"] = installed
        
        if installed:
            self.action_button.set_label("Remove")
            self.action_button.remove_css_class("suggested-action")
            self.action_button.add_css_class("destructive-action")
            
            # Add status icon if not present
            if not [c for c in self.get_css_classes() if c == "success"]:
                status_icon = Gtk.Image(icon_name="emblem-ok-symbolic")
                self.add_prefix(status_icon)
                self.add_css_class("success")
        else:
            self.action_button.set_label("Install")
            self.action_button.remove_css_class("destructive-action")
            self.action_button.add_css_class("suggested-action")
            
            # Remove status icon
            self.remove_css_class("success")
            for child in self.observe_children():
                if isinstance(child, Gtk.Image):
                    self.remove(child)
                    break
        
        self.action_button.set_sensitive(True)
        return False  # Stop the timeout


class DriverManagerWindow(Adw.ApplicationWindow):
    """Main window for the driver manager application."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self.set_default_size(900, 600)
        self.set_title("BigLinux Driver Manager")
        
        # Store drivers by category
        self.drivers_by_category = {}
        self.all_drivers = []
        
        # Create UI
        self._create_ui()
        
        # Load drivers
        self._load_drivers()
    
    def _create_ui(self):
        """Create the user interface."""
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Create split view
        self.split_view = Adw.NavigationSplitView()
        main_box.append(self.split_view)
        
        # Create sidebar
        sidebar = self._create_sidebar()
        
        # Create content area
        self.content_page = Adw.NavigationPage(title="Drivers")
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Add a toolbar view to the content
        content_toolbar = Adw.ToolbarView()
        
        # Header with back button for small screens
        self.content_header = Adw.HeaderBar()
        content_toolbar.add_top_bar(self.content_header)
        
        # Create content scrolled window
        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content_scroll.set_vexpand(True)
        
        # Create main content box (will be filled when a category is selected)
        self.drivers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.drivers_box.set_margin_top(12)
        self.drivers_box.set_margin_bottom(12)
        self.drivers_box.set_margin_start(12)
        self.drivers_box.set_margin_end(12)
        self.drivers_box.set_spacing(12)
        
        # Initial content
        loading_label = Gtk.Label(label="Loading drivers...")
        loading_label.add_css_class("title-1")
        self.drivers_box.append(loading_label)
        
        # Add content
        content_scroll.set_child(self.drivers_box)
        content_toolbar.set_content(content_scroll)
        content_box.append(content_toolbar)
        self.content_page.set_child(content_box)
        
        # Add pages to split view
        self.split_view.set_sidebar(sidebar)
        self.split_view.set_content(self.content_page)
        
        # Set the window content
        self.set_content(main_box)
    
    def _create_sidebar(self):
        """Create the sidebar with categories."""
        # Create a page for the sidebar
        sidebar_page = Adw.NavigationPage(title="Categories")
        
        # Create toolbar view for the sidebar
        toolbar_view = Adw.ToolbarView()
        
        # Create the sidebar header
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)
        
        # Create scrolled window for the sidebar content
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        # Create a box for the sidebar content
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.set_margin_top(8)
        sidebar_box.set_margin_bottom(8)
        
        # Create a list box for categories
        self.category_list = Gtk.ListBox()
        self.category_list.add_css_class("navigation-sidebar")
        self.category_list.connect("row-selected", self._on_category_selected)
        sidebar_box.append(self.category_list)
        
        # Add "All Drivers" option
        all_row = Adw.ActionRow()
        all_row.set_title("All Drivers")
        all_row.set_icon_name("view-grid-symbolic")
        all_row.category_id = "all"
        self.category_list.append(all_row)
        
        # Add categories from CATEGORY_LABELS
        for category_id, category_label in CATEGORY_LABELS.items():
            row = Adw.ActionRow()
            row.set_title(category_label)
            row.set_icon_name(self._get_icon_for_category(category_id))
            row.category_id = category_id
            self.category_list.append(row)
        
        # Set up the sidebar structure
        scroll.set_child(sidebar_box)
        toolbar_view.set_content(scroll)
        sidebar_page.set_child(toolbar_view)
        
        return sidebar_page
    
    def _get_icon_for_category(self, category):
        """Get appropriate icon for a category."""
        icons = {
            "gpu": "graphics-card-symbolic",
            "wifi": "network-wireless-symbolic",
            "ethernet": "network-wired-symbolic",
            "bluetooth": "bluetooth-symbolic",
            "printer": "printer-symbolic",
            "printer3d": "printer-3d-symbolic",
            "scanner": "scanner-symbolic",
            "dvb": "tv-symbolic",
            "webcam": "camera-web-symbolic",
            "touchscreen": "input-touchscreen-symbolic",
            "sound": "audio-card-symbolic",
            "firmware": "system-software-update-symbolic",
        }
        return icons.get(category, "drive-harddisk-symbolic")
    
    def _load_drivers(self):
        """Load drivers asynchronously."""
        threading.Thread(target=self._fetch_drivers, daemon=True).start()
    
    def _fetch_drivers(self):
        """Fetch drivers in a background thread."""
        try:
            self.all_drivers = list_all_drivers()
            
            # Group drivers by category
            self.drivers_by_category = {"all": self.all_drivers}
            
            for driver in self.all_drivers:
                category = driver.get("category", "unknown")
                if category not in self.drivers_by_category:
                    self.drivers_by_category[category] = []
                self.drivers_by_category[category].append(driver)
            
            # Update UI in main thread
            GLib.idle_add(self._update_ui_after_loading)
        except Exception as e:
            logger.error(f"Error loading drivers: {e}")
            GLib.idle_add(self._show_error, str(e))
    
    def _update_ui_after_loading(self):
        """Update UI after drivers are loaded."""
        # Update category count badges
        for row in self.category_list:
            category_id = getattr(row, "category_id", None)
            if category_id and category_id in self.drivers_by_category:
                count = len(self.drivers_by_category[category_id])
                badge = Gtk.Label(label=str(count))
                badge.add_css_class("badge")
                badge.add_css_class("numeric")
                row.add_suffix(badge)
        
        # Select the first row (All Drivers)
        self.category_list.select_row(self.category_list.get_row_at_index(0))
        
        return False  # Stop GLib.idle_add from calling again
    
    def _show_error(self, message):
        """Show error message when loading fails."""
        # Clear existing content
        while child := self.drivers_box.get_first_child():
            self.drivers_box.remove(child)
        
        error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        error_box.set_valign(Gtk.Align.CENTER)
        error_box.set_halign(Gtk.Align.CENTER)
        
        error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        error_icon.set_pixel_size(64)
        error_box.append(error_icon)
        
        error_label = Gtk.Label(label="Error Loading Drivers")
        error_label.add_css_class("title-1")
        error_box.append(error_label)
        
        message_label = Gtk.Label(label=message)
        message_label.add_css_class("body")
        error_box.append(message_label)
        
        retry_button = Gtk.Button(label="Retry")
        retry_button.add_css_class("pill")
        retry_button.add_css_class("suggested-action")
        retry_button.connect("clicked", lambda _: self._load_drivers())
        error_box.append(retry_button)
        
        self.drivers_box.append(error_box)
        return False  # Stop GLib.idle_add from calling again
    
    def _on_category_selected(self, list_box, row):
        """Handle category selection."""
        if not row:
            return
        
        category_id = getattr(row, "category_id", "all")
        
        # Update title
        if category_id == "all":
            self.content_page.set_title("All Drivers")
        else:
            self.content_page.set_title(CATEGORY_LABELS.get(category_id, "Drivers"))
        
        # Clear current content
        while child := self.drivers_box.get_first_child():
            self.drivers_box.remove(child)
        
        # Show drivers for selected category
        self._show_drivers_for_category(category_id)
    
    def _show_drivers_for_category(self, category_id):
        """Show drivers for the selected category."""
        drivers = self.drivers_by_category.get(category_id, [])
        
        if not drivers:
            # Show empty state
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            empty_box.set_valign(Gtk.Align.CENTER)
            empty_box.set_halign(Gtk.Align.CENTER)
            
            empty_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
            empty_icon.set_pixel_size(64)
            empty_box.append(empty_icon)
            
            empty_label = Gtk.Label(label="No Drivers Found")
            empty_label.add_css_class("title-1")
            empty_box.append(empty_label)
            
            self.drivers_box.append(empty_box)
            return
        
        # Create group for installed drivers
        installed_count = sum(1 for d in drivers if d.get("installed", False))
        if installed_count > 0:
            installed_group = Adw.PreferencesGroup(title="Installed Drivers")
            self.drivers_box.append(installed_group)
            
            for driver in drivers:
                if driver.get("installed", False):
                    row = DriverInstallationRow(driver, self)
                    installed_group.add(row)
        
        # Create group for available drivers
        available_count = len(drivers) - installed_count
        if available_count > 0:
            available_group = Adw.PreferencesGroup(title="Available Drivers")
            self.drivers_box.append(available_group)
            
            for driver in drivers:
                if not driver.get("installed", False):
                    row = DriverInstallationRow(driver, self)
                    available_group.add(row)


class DriverManagerApplication(Adw.Application):
    """Main application class."""
    
    def __init__(self):
        super().__init__(application_id="org.biglinux.driver-manager",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        
        self.connect("activate", self.on_activate)
    
    def on_activate(self, app):
        """Handle application activation."""
        # Create the main window
        win = DriverManagerWindow(application=app)
        win.present()


def main():
    """Run the application."""
    app = DriverManagerApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    main()
