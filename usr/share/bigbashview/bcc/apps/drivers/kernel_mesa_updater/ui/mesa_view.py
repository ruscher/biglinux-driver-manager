"""
Mesa View

UI component for managing Mesa driver installations and updates.
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

class MesaView(Gtk.Box):
    """View for managing Mesa driver installations and updates."""
    
    def __init__(self, mesa_manager):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.mesa_manager = mesa_manager
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_margin_start(20)
        self.set_margin_end(20)
        
        # Current Mesa Section
        current_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        current_section.set_margin_bottom(15)
        
        current_title = Gtk.Label()
        current_title.set_markup("<span weight='bold'>Current Mesa Version</span>")
        current_title.set_halign(Gtk.Align.START)
        
        self.current_mesa_label = Gtk.Label(label="Detecting Mesa version...")
        self.current_mesa_label.set_halign(Gtk.Align.START)
        
        current_section.append(current_title)
        current_section.append(self.current_mesa_label)
        
        # Mesa Options Section
        options_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        options_title = Gtk.Label()
        options_title.set_markup("<span weight='bold'>Mesa Driver Options</span>")
        options_title.set_halign(Gtk.Align.START)
        options_section.append(options_title)
        
        # Create options for stable and git versions
        self.stable_radio = Gtk.CheckButton(label="Mesa Stable")
        self.stable_radio.set_active(True)
        options_section.append(self.stable_radio)
        
        self.git_radio = Gtk.CheckButton(label="Mesa Git (Development)")
        self.git_radio.set_group(self.stable_radio)
        options_section.append(self.git_radio)
        
        # Multilib support checkbox
        self.multilib_check = Gtk.CheckButton(label="Include 32-bit libraries (multilib)")
        self.multilib_check.set_active(True)
        self.multilib_check.set_margin_top(5)
        options_section.append(self.multilib_check)
        
        # Action Buttons Section
        buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons_box.set_homogeneous(True)
        buttons_box.set_margin_top(15)
        
        # Update button
        self.update_button = Gtk.Button(label="Update Mesa Drivers")
        self.update_button.connect("clicked", self._on_update_clicked)
        buttons_box.append(self.update_button)
        
        # Revert button
        self.revert_button = Gtk.Button(label="Revert to Previous")
        self.revert_button.connect("clicked", self._on_revert_clicked)
        buttons_box.append(self.revert_button)
        
        # Refresh button
        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.connect("clicked", self._on_refresh_clicked)
        buttons_box.append(self.refresh_button)
        
        # Progress bar for operations
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("Ready")
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_margin_top(10)
        
        # Status label
        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_margin_top(5)
        
        # Add all sections to the main view
        self.append(current_section)
        self.append(options_section)
        self.append(buttons_box)
        self.append(self.progress_bar)
        self.append(self.status_label)
        
        # Initialize the view
        self._init_view()
    
    def _init_view(self):
        """Initialize view data asynchronously."""
        self._run_async(self._load_data())
    
    async def _load_data(self):
        """Load Mesa data asynchronously."""
        # Detect current Mesa version
        current_mesa = await self.mesa_manager.detect_current_mesa()
        GLib.idle_add(self._update_current_mesa, current_mesa)
    
    def _update_current_mesa(self, mesa_version):
        """Update the current Mesa version label."""
        self.current_mesa_label.set_text(f"{mesa_version} (Current)")
    
    def _on_update_clicked(self, button):
        """Handle update button click."""
        use_git = self.git_radio.get_active()
        use_multilib = self.multilib_check.get_active()
        self._run_async(self._update_mesa(use_git, use_multilib))
    
    def _on_revert_clicked(self, button):
        """Handle revert button click."""
        self._run_async(self._rollback_mesa())
    
    def _on_refresh_clicked(self, button):
        """Handle refresh button click."""
        self._init_view()
    
    async def _update_mesa(self, use_git, use_multilib):
        """Update Mesa drivers asynchronously."""
        version_type = "Git" if use_git else "Stable"
        multilib_text = "with" if use_multilib else "without"
        
        self._update_progress(0.0, f"Preparing to install Mesa {version_type} {multilib_text} multilib...")
        success = await self.mesa_manager.install_mesa(use_git, use_multilib, self._progress_callback)
        
        if success:
            # Update current Mesa version
            current_mesa = await self.mesa_manager.detect_current_mesa()
            GLib.idle_add(self._update_current_mesa, current_mesa)
    
    async def _rollback_mesa(self):
        """Rollback to previous Mesa version asynchronously."""
        self._update_progress(0.0, "Preparing to rollback to previous Mesa version...")
        success = await self.mesa_manager.rollback_mesa(self._progress_callback)
        
        if success:
            # Update current Mesa version
            current_mesa = await self.mesa_manager.detect_current_mesa()
            GLib.idle_add(self._update_current_mesa, current_mesa)
    
    def _progress_callback(self, progress, status):
        """Callback for progress updates from Mesa operations."""
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
