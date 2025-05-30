import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango
import logging
import asyncio

from .kernel_manager import KernelManager

logger = logging.getLogger(__name__)

class AdwKernelView(Gtk.Box):
    """Adwaita-styled view for displaying and managing kernels."""
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_margin_start(20)
        self.set_margin_end(20)
        
        # Create a scrolled window to contain the kernel lists
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_vexpand(True)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        # Create an Adwaita ClampView to constrain the content width
        clamp = Adw.ClampScrollable()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(600)
        
        # Create a main content box
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        
        # Create Adw.PreferencesPage as the main container
        self.preferences_page = Adw.PreferencesPage()
        
        # Create groups for different kernel categories
        self.installed_group = Adw.PreferencesGroup(title="Installed Kernels")
        self.official_group = Adw.PreferencesGroup(title="Official Kernels")
        self.aur_group = Adw.PreferencesGroup(title="AUR Kernels")
        
        # Add the groups to the page
        self.preferences_page.add(self.installed_group)
        self.preferences_page.add(self.official_group)
        self.preferences_page.add(self.aur_group)
        
        # Add loading indicator
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.start()
        
        spinner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        spinner_box.set_halign(Gtk.Align.CENTER)
        spinner_box.set_margin_top(20)
        spinner_box.set_margin_bottom(20)
        spinner_box.append(self.spinner)
        
        # Loading text label
        self.loading_label = Gtk.Label(label="Loading kernel information...")
        spinner_box.append(self.loading_label)
        spinner_box.set_spacing(10)
        
        # Progress bar for operations
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_margin_top(10)
        self.progress_bar.set_margin_bottom(10)
        self.progress_bar.set_visible(False)
        
        # Add elements to the content box
        self.content_box.append(spinner_box)
        self.content_box.append(self.progress_bar)
        self.content_box.append(self.preferences_page)
        
        # Stack setup to switch between loading and content
        self.stack = Adw.ViewStack()
        loading_page = Adw.ViewStackPage.new(spinner_box)
        content_page = Adw.ViewStackPage.new(self.preferences_page)
        
        self.stack.add_page(loading_page)
        self.stack.add_page(content_page)
        
        clamp.set_child(self.content_box)
        scrolled_window.set_child(clamp)
        self.append(scrolled_window)
        
        # Initialize kernel manager
        self.kernel_manager = KernelManager()
        
        # Load kernel data
        self._load_kernel_data()
    
    def _load_kernel_data(self):
        """Load kernel data asynchronously."""
        self.spinner.start()
        self.loading_label.set_text("Loading kernel information...")
        
        async def load():
            try:
                # Get kernel data from KernelManager
                kernels_data = await self.kernel_manager.get_kernels_json()
                
                # Update UI with the kernel data
                GLib.idle_add(self._populate_kernel_groups, kernels_data)
            except Exception as e:
                logger.exception("Error loading kernel data")
                GLib.idle_add(
                    self.loading_label.set_text,
                    f"Error loading kernel data: {str(e)}"
                )
        
        # Start the async task to load kernel data
        asyncio.create_task(load())
    
    def _populate_kernel_groups(self, kernels_data):
        """Populate the preference groups with kernel data."""
        self.spinner.stop()
        
        # Clear existing content
        for child in self.installed_group.get_children():
            self.installed_group.remove(child)
        for child in self.official_group.get_children():
            self.official_group.remove(child)
        for child in self.aur_group.get_children():
            self.aur_group.remove(child)
        
        # Populate installed kernels
        installed_kernels = kernels_data.get("installed_packages", [])
        for kernel in installed_kernels:
            self._add_kernel_to_group(kernel, self.installed_group, is_installed=True)
        
        # Populate official kernels
        official_kernels = kernels_data.get("official_available", [])
        for kernel in official_kernels:
            if not kernel.get("is_installed", False):
                self._add_kernel_to_group(kernel, self.official_group)
        
        # Populate AUR kernels
        aur_kernels = kernels_data.get("aur_available", [])
        for kernel in aur_kernels:
            if not kernel.get("is_installed", False):
                self._add_kernel_to_group(kernel, self.aur_group)
        
        # Show content instead of loading spinner
        self.stack.set_visible_child(self.preferences_page)
        
        # Log completion
        logger.info("UI Progress: 100% - Kernel list populated.")
    
    def _add_kernel_to_group(self, kernel_data, group, is_installed=False):
        """Add a kernel to the specified preferences group."""
        try:
            # Create an action row for the kernel
            row = Adw.ActionRow()
            row.kernel_info = kernel_data  # Store kernel data as attribute
            
            # Title formatting
            name = kernel_data.get("name", "Unknown")
            version = kernel_data.get("version", "")
            
            row.set_title(name)
            row.set_subtitle(version)
            
            # Source badge (official or AUR)
            source = kernel_data.get("source", "unknown")
            source_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            source_box.set_halign(Gtk.Align.CENTER)
            
            source_label = Gtk.Label(label=source)
            source_label.get_style_context().add_class("caption")
            source_label.get_style_context().add_class("dim-label")
            source_box.append(source_label)
            
            # Set up status indicators
            if kernel_data.get("is_running", False):
                running_icon = Gtk.Image.new_from_icon_name("starred-symbolic")
                running_icon.set_tooltip_text("Currently running")
                row.add_prefix(running_icon)
            
            if is_installed:
                # Add uninstall button for installed kernels (except for the running one)
                if not kernel_data.get("is_running", False):
                    uninstall_button = Gtk.Button()
                    uninstall_button.set_icon_name("user-trash-symbolic")
                    uninstall_button.set_tooltip_text(f"Uninstall {name}")
                    uninstall_button.connect("clicked", self._on_uninstall_clicked, kernel_data)
                    row.add_suffix(uninstall_button)
            else:
                # Add install button for non-installed kernels
                install_button = Gtk.Button()
                install_button.set_icon_name("software-install-symbolic")
                install_button.set_tooltip_text(f"Install {name}")
                install_button.connect("clicked", self._on_install_clicked, kernel_data)
                row.add_suffix(install_button)
            
            # Add source badge
            row.add_suffix(source_box)
            
            # Add the row to the group
            group.add(row)
            
        except Exception as e:
            logger.exception(f"Error adding kernel to group: {str(e)}")
    
    def _on_install_clicked(self, button, kernel_data):
        """Handle install button click."""
        kernel_name = kernel_data.get("name", "")
        if not kernel_name:
            return
        
        # Disable the button to prevent multiple clicks
        button.set_sensitive(False)
        
        # Show and reset progress bar
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text(f"Preparing to install {kernel_name}...")
        
        async def install():
            try:
                # Start kernel installation
                success = await self.kernel_manager.install_kernel(kernel_name, self._update_progress)
                
                if success:
                    # Reload kernel data after successful installation
                    GLib.idle_add(self._load_kernel_data)
                else:
                    # Re-enable the button if installation failed
                    GLib.idle_add(button.set_sensitive, True)
                    GLib.idle_add(self.progress_bar.set_text, f"Installation of {kernel_name} failed.")
            except Exception as e:
                logger.exception(f"Error installing kernel {kernel_name}")
                GLib.idle_add(button.set_sensitive, True)
                GLib.idle_add(self.progress_bar.set_text, f"Error: {str(e)}")
        
        # Start the installation task
        asyncio.create_task(install())
    
    def _on_uninstall_clicked(self, button, kernel_data):
        """Handle uninstall button click."""
        # Implementation for uninstall functionality would go here
        kernel_name = kernel_data.get("name", "")
        logger.info(f"Uninstall requested for {kernel_name} (not implemented)")
        
        # Show dialog to confirm uninstall
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            f"Uninstall {kernel_name}?",
            "This will remove the kernel and its related packages. You cannot uninstall the currently running kernel."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("uninstall", "Uninstall")
        dialog.set_response_appearance("uninstall", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_uninstall_dialog_response, kernel_data)
        dialog.present()
    
    def _on_uninstall_dialog_response(self, dialog, response, kernel_data):
        """Handle uninstall dialog response."""
        if response == "uninstall":
            # Uninstall implementation would go here
            # This is a placeholder - actual uninstall code would need to be added
            kernel_name = kernel_data.get("name", "")
            logger.info(f"Uninstalling {kernel_name} (not fully implemented)")
            
            # After uninstall, reload the kernel data
            self._load_kernel_data()
    
    def _update_progress(self, fraction, text):
        """Update progress bar."""
        GLib.idle_add(self.progress_bar.set_fraction, fraction)
        GLib.idle_add(self.progress_bar.set_text, text)
        return False  # Return False to prevent being called again
