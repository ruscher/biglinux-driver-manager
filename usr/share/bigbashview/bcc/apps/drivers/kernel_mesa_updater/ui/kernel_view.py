"""
Kernel View

UI component for managing kernel installations and updates.
"""
import gi
import asyncio
import threading
import logging
from typing import Dict, List, Any, Optional

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

# Set up logger
logger = logging.getLogger(__name__)

class KernelView(Gtk.Box):
    """View for managing kernel installations and updates."""
    
    def __init__(self, kernel_manager):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.kernel_manager = kernel_manager
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_margin_start(20)
        self.set_margin_end(20)
        
        # Main content container
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content_box.set_margin_top(24)
        content_box.set_margin_bottom(24)
        content_box.set_margin_start(24)
        content_box.set_margin_end(24)
        
        # Create an Adw.PreferencesPage as the main container
        preferences_page = Adw.PreferencesPage()
        
        # Create container for kernel groups
        self.kernels_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        
        # Add kernel groups container to the page
        preferences_page.set_child(self.kernels_group)
        
        # Progress indicator
        indicator_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        indicator_box.set_halign(Gtk.Align.CENTER)
        indicator_box.set_valign(Gtk.Align.CENTER)
        
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        
        self.progress_label = Gtk.Label(label="Loading...")
        
        indicator_box.append(self.spinner)
        indicator_box.append(self.progress_label)
        
        # Add components to content box
        content_box.append(indicator_box)
        content_box.append(preferences_page)
        
        # Scrollable view
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_child(content_box)
        
        self.append(scrolled_window)
        
        # Initialize kernel manager
        self.kernel_manager = KernelManager()
        
        # Load kernel data
        self._load_kernels_data()
    
    def _init_view(self):
        """Initialize view data asynchronously."""
        self._run_async(self._load_data())
    
    async def _load_data(self):
        """Load kernel data asynchronously."""
        # Detect current kernel
        current_kernel = await self.kernel_manager.detect_current_kernel()
        GLib.idle_add(self._update_current_kernel, current_kernel)
        
        # Get all available kernels (official + AUR)
        kernels = await self.kernel_manager.get_all_available_kernels()
        GLib.idle_add(self._populate_kernel_list, kernels)
    
    def _update_current_kernel(self, kernel_version):
        """Update the current kernel label."""
        self.current_kernel_label.set_text(f"{kernel_version} (Current)")
    
    def _populate_kernel_list(self, kernels_data):
        """Populate the list of available kernels using Adw.PreferencesGroup."""
        # Clear existing rows
        while self.kernels_group.get_first_child():
            self.kernels_group.remove(self.kernels_group.get_first_child())
        
        # Create separate preference groups for each category
        self.installed_group = Adw.PreferencesGroup()
        self.installed_group.set_title("Installed Kernels")
        
        self.official_group = Adw.PreferencesGroup()
        self.official_group.set_title("Official Kernels")
        
        self.aur_group = Adw.PreferencesGroup()
        self.aur_group.set_title("AUR Kernels")
        
        # Add the groups to the main container
        self.kernels_group.append(self.installed_group)
        self.kernels_group.append(self.official_group)
        self.kernels_group.append(self.aur_group)
        
        # Extract kernel lists from data structure
        installed_kernels = kernels_data.get("installed_packages", [])
        official_kernels = kernels_data.get("official_available", [])
        aur_kernels = kernels_data.get("aur_available", [])
        
        # Debug information
        logging.info(f"Populating kernel lists: {len(installed_kernels)} installed, {len(official_kernels)} official, {len(aur_kernels)} AUR")
        
        # Add installed kernels to the installed group
        if installed_kernels:
            for kernel in installed_kernels:
                self._add_kernel_row(kernel, self.installed_group, is_installed=True)
        else:
            # Add a placeholder row if no kernels are installed
            empty_row = Adw.ActionRow()
            empty_row.set_title("No kernels installed")
            self.installed_group.add(empty_row)
        
        # Add official kernels to the official group
        if official_kernels:
            for kernel in official_kernels:
                if not kernel.get("is_installed", False):  # Only show non-installed kernels here
                    self._add_kernel_row(kernel, self.official_group)
        else:
            empty_row = Adw.ActionRow()
            empty_row.set_title("No official kernels available")
            self.official_group.add(empty_row)
        
        # Add AUR kernels to the AUR group
        if aur_kernels:
            for kernel in aur_kernels:
                if not kernel.get("is_installed", False):  # Only show non-installed kernels here
                    self._add_kernel_row(kernel, self.aur_group)
        else:
            empty_row = Adw.ActionRow()
            empty_row.set_title("No AUR kernels available")
            self.aur_group.add(empty_row)

    def _add_kernel_row(self, kernel, group, is_installed=False):
        """Add a kernel row to the specified PreferencesGroup."""
        try:
            # Create an Adw.ActionRow for the kernel
            row = Adw.ActionRow()
            
            # Store kernel data as an attribute for later use
            row.kernel_data = kernel
            
            # Get kernel information
            name = kernel.get("name", "Unknown")
            version = kernel.get("version", "")
            description = kernel.get("description", "")
            
            # Set row title and subtitle
            row.set_title(name)
            row.set_subtitle(f"Version: {version}")
            if description:
                row.set_tooltip_text(description)
            
            # Add status indicators
            if kernel.get("is_running", False):
                running_icon = Gtk.Image.new_from_icon_name("starred-symbolic")
                running_icon.set_tooltip_text("Currently running")
                row.add_prefix(running_icon)
            
            # Add source badge
            source = kernel.get("source", "unknown")
            source_badge = Gtk.Label()
            source_badge.set_text(source)
            source_badge.add_css_class("caption")
            source_badge.add_css_class("dim-label")
            source_badge.set_margin_end(12)
            row.add_suffix(source_badge)
            
            # Add action button based on installation status
            if is_installed and not kernel.get("is_running", False):
                # Show uninstall button if kernel is installed but not running
                uninstall_button = Gtk.Button()
                uninstall_button.set_icon_name("user-trash-symbolic")
                uninstall_button.set_tooltip_text(f"Remove {name}")
                uninstall_button.set_valign(Gtk.Align.CENTER)
                uninstall_button.connect("clicked", self._on_kernel_uninstall_clicked, kernel)
                row.add_suffix(uninstall_button)
            elif not is_installed:
                # Show install button if kernel is not installed
                install_button = Gtk.Button()
                install_button.set_icon_name("software-install-symbolic")
                install_button.set_tooltip_text(f"Install {name}")
                install_button.set_valign(Gtk.Align.CENTER)
                install_button.connect("clicked", self._on_kernel_install_clicked, kernel)
                row.add_suffix(install_button)
            
            # Add the row to the group
            group.add(row)
            
        except Exception as e:
            logging.exception(f"Error adding kernel row: {str(e)}")

    def _on_kernel_row_activated(self, row, check_button):
        """Handle clicking on a kernel row."""
        check_button.set_active(not check_button.get_active())
    
    def _on_check_button_toggled(self, check_button, row):
        """Handle toggling a kernel check button."""
        # Deselect all other checkboxes
        parent = row.get_parent()
        if parent:
            for child in parent.get_children():
                if child != row and hasattr(child, "get_data"):
                    other_check = child.get_data("check-button")
                    if other_check and other_check != check_button:
                        other_check.set_active(False)
        
        # Update the selected kernel and enable/disable install button
        if check_button.get_active():
            self.selected_kernel = row.get_data("kernel-data")
            self.install_button.set_sensitive(True)
        else:
            if self.selected_kernel == row.get_data("kernel-data"):
                self.selected_kernel = None
                self.install_button.set_sensitive(False)
    
    def _on_install_clicked(self, button):
        """Handle install button click."""
        if self.selected_kernel:
            kernel_name = self.selected_kernel["name"]
            self._run_async(self._install_kernel(kernel_name))
    
    def _on_rollback_clicked(self, button):
        """Handle rollback button click."""
        self._run_async(self._rollback_kernel())
    
    def _on_refresh_clicked(self, button):
        """Handle refresh button click."""
        self._init_view()
    
    async def _install_kernel(self, kernel_name):
        """Install a kernel asynchronously."""
        self._update_progress(0.0, f"Preparing to install {kernel_name}...")
        success = await self.kernel_manager.install_kernel(kernel_name, self._progress_callback)
        
        if success:
            # Update current kernel label (it might have changed)
            current_kernel = await self.kernel_manager.detect_current_kernel()
            GLib.idle_add(self._update_current_kernel, current_kernel)
    
    async def _rollback_kernel(self):
        """Rollback to previous kernel asynchronously."""
        self._update_progress(0.0, "Preparing to rollback to previous kernel...")
        success = await self.kernel_manager.rollback_kernel(self._progress_callback)
        
        if success:
            # Update current kernel label
            current_kernel = await self.kernel_manager.detect_current_kernel()
            GLib.idle_add(self._update_current_kernel, current_kernel)
    
    def _progress_callback(self, progress, status):
        """Callback for progress updates from kernel operations."""
        GLib.idle_add(self._update_progress, progress, status)
    
    def _update_progress(self, progress, status):
        """Update the progress bar and status label."""
        self.progress_bar.set_fraction(progress)
        self.progress_bar.set_text(status)
        self.status_label.set_text(status)
    
    def _run_async(self, coro):
        """Run a coroutine asynchronously."""
        def _run_in_thread():
            asyncio.run(coro)
        
        threading.Thread(target=_run_in_thread).start()
