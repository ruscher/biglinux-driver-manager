"""
Kernel and Mesa Update Page

This module provides the page for updating kernel and Mesa versions.
"""
import gi
from typing import Dict, List, Any, Optional
import logging
import asyncio # Import asyncio
import threading # Import threading

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

# Corrigir importações usando caminho relativo
from .kernel_manager import KernelManager
from .mesa_manager import MesaManager

# Set up logger
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class KernelView(Gtk.Box):
    """View for managing kernel installations and updates."""
    def __init__(self, kernel_manager: KernelManager, main_window: Gtk.Window): # Adicionar main_window para diálogos
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.kernel_manager = kernel_manager
        self.main_window = main_window
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_margin_start(20)
        self.set_margin_end(20)
        
        # Remove the Current Kernel Section
        
        # Available Kernels Section
        available_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        # Replace ListBox with a container for PreferencesGroups
        kernels_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        
        # Create PreferencesGroups for different kernel categories
        self.installed_group = Adw.PreferencesGroup(title="Installed Kernels")
        self.official_group = Adw.PreferencesGroup(title="Official Kernels")
        self.aur_group = Adw.PreferencesGroup(title="AUR Kernels")
        
        # Add the groups to the container
        kernels_container.append(self.installed_group)
        kernels_container.append(self.official_group)
        kernels_container.append(self.aur_group)
        
        scrolled.set_child(kernels_container)
        available_section.append(scrolled)
        
        # Progress indicator in ToolbarView style
        status_bar = Adw.StatusPage()
        status_bar.set_title("")
        status_bar.set_description("")
        status_bar.set_visible(False)
        
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_margin_top(10)
        self.progress_bar.set_visible(False)
        
        # Create a container to place the progress bar at the bottom
        progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        progress_box.append(self.progress_bar)
        status_bar.set_child(progress_box)
        
        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.CENTER)
        self.status_label.set_margin_top(5)
        self.status_label.set_visible(False)
        
        self.append(available_section)
        self.append(status_bar)
        self.append(self.status_label)
        
        # Populate kernels on load using asyncio
        self._run_async_task(self._populate_kernel_data_async())

    def _run_async_task(self, coro):
        """Run an asyncio coroutine in a background thread."""
        def _run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        
        threading.Thread(target=_run_in_thread, daemon=True).start()

    def _update_progress(self, fraction: float, text: str) -> None:
        """Update the UI with progress information in ToolbarView style."""
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(text)
        self.status_label.set_text(text)
        
        # Make status components visible if there's text
        if text and text.strip():
            self.status_label.set_visible(True)
            self.progress_bar.set_visible(True)
        
        logger.info(f"UI Progress: {fraction*100:.0f}% - {text}")

    def _set_buttons_sensitive(self, sensitive: bool):
        # This method is no longer needed as we removed the buttons
        pass

    async def _populate_kernel_data_async(self):
        """Populate current kernel and available kernels list asynchronously."""
        GLib.idle_add(self.progress_bar.set_visible, True)
        GLib.idle_add(self.status_label.set_visible, True)
        
        try:
            GLib.idle_add(self._update_progress, 0.0, "Detecting current kernel...")
            
            # Still detect current kernel for internal use, but don't display it
            current_kernel_version = await self.kernel_manager.detect_current_kernel()
            GLib.idle_add(self._update_progress, 0.1, "Fetching available kernels...") # Adjusted progress

            # Fix: Clear all groups properly for AdwPreferencesGroup
            def clear_groups():
                for group in [self.installed_group, self.official_group, self.aur_group]:
                    # In AdwPreferencesGroup we need to remove all rows directly
                    rows = []
                    # First collect all rows
                    row = group.get_first_child()
                    while row:
                        rows.append(row)
                        row = row.get_next_sibling()
                    
                    # Then remove each row
                    for row in rows:
                        group.remove(row)
                    
            GLib.idle_add(clear_groups)

            populated_successfully = False
            try:
                # Create a temporary script file with the kernel detection bash script
                import tempfile
                import os
                
                script_file = tempfile.NamedTemporaryFile(mode='w+', delete=False)
                script_file.write('''#!/bin/bash

# Force C locale for consistent output from system tools
export LANG=C
export LC_ALL=C

# Get available kernels using mhwd-kernel
# Uses a single sed command to filter lines and extract kernel names.
AVAILABLE_KERNELS=$(mhwd-kernel -l | \\
                    sed -n -E '/^\\s*(\\* )?linux[0-9a-zA-Z._-]+/ { s/^\\s*(\\* )?//; s/\\s.*$//; p }' | \\
                    sort -u)

# Get installed kernels using mhwd-kernel
# Similar single sed command for installed kernels.
INSTALLED_KERNELS_LIST=$(mhwd-kernel -li | \\
                         sed -n -E '/^\\s*(\\* )?linux[0-9a-zA-Z._-]+/ { s/^\\s*(\\* )?//; s/\\s.*$//; p }' | \\
                         sort -u)

# Get current kernel full version string from uname
CURRENT_KERNEL_UNAME=$(uname -r)

# Try to determine the package name of the currently running kernel (e.g., linux61)
RUNNING_KERNEL_PACKAGE_NAME=$(mhwd-kernel -li | grep -i "running" | sed -n 's/.*\\(linux[0-9a-zA-Z-]*\\).*/\\1/p' | head -n 1)
if [ -z "$RUNNING_KERNEL_PACKAGE_NAME" ]; then
    RUNNING_KERNEL_PACKAGE_NAME=$(mhwd-kernel -li | grep -i "running" | awk '{for(i=1;i<=NF;i++) if($i ~ /^linux[0-9]+([a-zA-Z0-9-]*)$/) {print $i; exit}}' | head -n1)
fi
CURRENT_KERNEL_FOR_JSON="${RUNNING_KERNEL_PACKAGE_NAME:-$(uname -r)}"


# Create an array to hold all kernel JSON objects
KERNEL_JSON_ARRAY=()

# Function to get package info (ensures LANG=C for pacman/yay)
get_pkg_info() {
  local kernel_pkg_name="$1"
  local info

  info=$(pacman -Qi "$kernel_pkg_name" 2>/dev/null) # LANG=C is inherited

  if [ -z "$info" ]; then
    info=$(pacman -Si "$kernel_pkg_name" 2>/dev/null) # LANG=C is inherited
    if [ -z "$info" ]; then
        info=$(yay -Si "$kernel_pkg_name" 2>/dev/null) # LANG=C is inherited
    fi
  fi

  echo "$info"
}

# Combine all unique kernel names from available and installed lists
ALL_KERNEL_PACKAGE_NAMES=$(echo -e "${AVAILABLE_KERNELS}\\n${INSTALLED_KERNELS_LIST}" | grep -vE "^\\s*$" | sort -u)

# Process each kernel package name
for kernel_pkg_name in $ALL_KERNEL_PACKAGE_NAMES; do
  if [ -z "$kernel_pkg_name" ]; then
    continue
  fi

  STATUS="unknown"
  is_installed=false
  if echo "$INSTALLED_KERNELS_LIST" | grep -q -w "^${kernel_pkg_name}$"; then
    is_installed=true
  fi

  if $is_installed; then
    if [ -n "$RUNNING_KERNEL_PACKAGE_NAME" ] && [ "$kernel_pkg_name" == "$RUNNING_KERNEL_PACKAGE_NAME" ]; then
      STATUS="in_use"
    else
      kernel_version_short_match=false
      # Extract major.minor from package name: linux510 -> 5.10, linux61 -> 6.1, linux610 -> 6.10
      kernel_base_version=$(echo "$kernel_pkg_name" | sed -n -E 's/^linux([0-9]+)([0-9]+).*/\\1.\\2/p; s/^linux([0-9]+).*/\\1.0/p')

      if [ -n "$kernel_base_version" ] && [[ "$CURRENT_KERNEL_UNAME" == "${kernel_base_version}"* ]]; then
        kernel_version_short_match=true
      fi

      # If we couldn't determine the specific running package name (RUNNING_KERNEL_PACKAGE_NAME is empty),
      # AND this installed kernel's version broadly matches uname -r, mark it as in_use.
      # This is a fallback to catch the running kernel if the specific package name extraction failed.
      # If RUNNING_KERNEL_PACKAGE_NAME *is* set, then this kernel is just "installed" (not the one specifically identified as running).
      if $kernel_version_short_match && [ -z "$RUNNING_KERNEL_PACKAGE_NAME" ]; then
        STATUS="in_use"
      else
        STATUS="installed"
      fi
    fi
  else
    # If not in INSTALLED_KERNELS_LIST, it must be from AVAILABLE_KERNELS
    # We double-check to be sure (though sort -u on combined list should make this robust)
    if echo "$AVAILABLE_KERNELS" | grep -q -w "^${kernel_pkg_name}$"; then
        STATUS="available"
    else
        # This should ideally not be reached if ALL_KERNEL_PACKAGE_NAMES is built correctly
        # echo "Warning: Kernel $kernel_pkg_name not definitively available or installed. Skipping." >&2
        continue
    fi
  fi

  PKG_INFO=$(get_pkg_info "$kernel_pkg_name")

  VERSION=$(echo "$PKG_INFO" | grep -m1 "^Version" | cut -d: -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  REPO=$(echo "$PKG_INFO" | grep -m1 "^Repository" | cut -d: -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  BUILD_DATE=$(echo "$PKG_INFO" | grep -m1 "^Build Date" | cut -d: -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  DESCRIPTION=$(echo "$PKG_INFO" | grep -m1 "^Description" | cut -d: -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

  if [[ "$STATUS" == "available" && -z "$VERSION" ]]; then
      # Kernel listed as available by mhwd, but no package info found (e.g., EOL, not in repos)
      # Keep it, will show empty fields for version, repo etc.
      :
  fi

  KERNEL_JSON=$(jq -n \\
    --arg name "$kernel_pkg_name" \\
    --arg version "${VERSION:-}" \\
    --arg status "$STATUS" \\
    --arg repo "${REPO:-}" \\
    --arg build_date "${BUILD_DATE:-}" \\
    --arg description "${DESCRIPTION:-}" \\
    '{
      name: $name,
      version: $version,
      status: $status,
      repository: $repo,
      build_date: $build_date,
      description: $description
    }')

  KERNEL_JSON_ARRAY+=("$KERNEL_JSON")
done

IFS=$'\\n'
SORTED_KERNELS=($(printf "%s\\n" "${KERNEL_JSON_ARRAY[@]}" | jq -c '.' | jq -s '
  sort_by(.version | if . == "" or . == null then [] else (split("[.-]") | map(tonumber? // .)) end) | reverse | .[]
'))
unset IFS

FINAL_JSON=$(jq -n \\
  --arg current_kernel "$CURRENT_KERNEL_FOR_JSON" \\
  --argjson kernels "$(printf "%s\\n" "${SORTED_KERNELS[@]}" | jq -s '.')" \\
  '{
    current_kernel: $current_kernel,
    kernels: $kernels
  }')

echo "$FINAL_JSON"
''')
                script_file.close()
                os.chmod(script_file.name, 0o755)  # Make executable
                
                # Execute the script and get JSON output
                process = await asyncio.create_subprocess_exec(
                    script_file.name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                # Remove temp script
                os.unlink(script_file.name)
                
                if process.returncode != 0:
                    logger.error(f"Error running kernel detection script: {stderr.decode()}")
                    # Fall back to the previous method
                    GLib.idle_add(self._add_error_row, f"Error detecting kernels: {stderr.decode().strip()}")
                    GLib.idle_add(self._set_buttons_sensitive, True)
                    return
                
                # Parse the JSON output
                import json
                kernel_data = json.loads(stdout.decode())
                
                # Sort and display kernels by status: in_use > installed > available
                installed_kernels = []
                available_kernels = []
                
                current_kernel_name = kernel_data.get('current_kernel', '')
                
                # Process each kernel
                for kernel in kernel_data.get('kernels', []):
                    status = kernel.get('status', '')
                    
                    # Create kernel info dictionary
                    kernel_info = {
                        "name": kernel.get("name", ''),
                        "version": kernel.get("version", ''),
                        "description": kernel.get("description", ''),
                        "source": kernel.get("repository", 'manjaro'),
                        "is_installed": status in ['in_use', 'installed'],
                        "is_running": status == 'in_use'
                    }
                    
                    # Add to appropriate list
                    if status in ['in_use', 'installed']:
                        installed_kernels.append(kernel_info)
                    else:
                        available_kernels.append(kernel_info)
                
                # Update UI with kernel data
                GLib.idle_add(self._update_progress, 0.7, "Adding kernels to UI...")
                
                # Add installed kernels
                for kernel in installed_kernels:
                    GLib.idle_add(self._add_kernel_to_group, kernel, self.installed_group, True)
                
                # Add available kernels
                for kernel in available_kernels:
                    GLib.idle_add(self._add_kernel_to_group, kernel, self.official_group, False)
                
                # Hide AUR group since we're using mhwd-kernel
                GLib.idle_add(self.aur_group.set_visible, False)
                
                GLib.idle_add(self._update_progress, 1.0, "Kernel list populated.")
                populated_successfully = True
            
            except Exception as e_script:
                logger.exception(f"Error using kernel script: {str(e_script)}")
                GLib.idle_add(self._update_progress, 0.5, f"Script method failed: {str(e_script)[:100]}. Trying fallback...")


            if not populated_successfully:
                # Fall back to pacman/AUR approach
                try:
                    # ...existing fallback code...
                    kernels_data = await self.kernel_manager.get_all_available_kernels()
                    if not kernels_data:
                        GLib.idle_add(self._update_progress, 1.0, "No available kernels found or error fetching.")
                        GLib.idle_add(self._add_error_row, "No kernels found or error.")
                        GLib.idle_add(self._set_buttons_sensitive, True)
                        return

                    installed_kernels = kernels_data.get("installed_packages", [])
                    official_kernels = kernels_data.get("official_available", [])
                    aur_kernels = kernels_data.get("aur_available", [])

                    # Add kernels to appropriate groups
                    for kernel in installed_kernels:
                        GLib.idle_add(self._add_kernel_to_group, kernel, self.installed_group, True)
                    
                    for kernel in official_kernels:
                        if not kernel.get("is_installed", False):
                            GLib.idle_add(self._add_kernel_to_group, kernel, self.official_group, False)
                            
                    for kernel in aur_kernels:
                        if not kernel.get("is_installed", False):
                            GLib.idle_add(self._add_kernel_to_group, kernel, self.aur_group, False)
                    
                    GLib.idle_add(self._update_progress, 1.0, "Kernel list populated (fallback).")
                except Exception as e_fallback:
                    logger.exception(f"Error with fallback kernel detection: {str(e_fallback)}")
                    GLib.idle_add(self._update_progress, 1.0, f"Error loading kernels: {str(e_fallback)}")
                    GLib.idle_add(self._add_error_row, "Error loading kernels.")
        finally:
            GLib.idle_add(self.progress_bar.set_visible, False)

    def _add_kernel_to_group(self, kernel_data, group, is_installed=False):
        """Add a kernel to a PreferencesGroup using Adw.ActionRow."""
        try:
            # Create an ActionRow for the kernel
            row = Adw.ActionRow()
            row.kernel_data = kernel_data
            # Set title and subtitle
            name = kernel_data.get("name", "Unknown")
            version = kernel_data.get("version", "")
            description = kernel_data.get("description", "")
            row.set_title(name)
            row.set_subtitle(f"Version: {version}")
            if description:
                row.set_tooltip_text(description)
            # Add status indicators
            if kernel_data.get("is_running", False):
                running_icon = Gtk.Image.new_from_icon_name("starred-symbolic")
                running_icon.set_tooltip_text("Currently running")
                row.add_prefix(running_icon)
            # Add source badge
            source = kernel_data.get("source", "unknown")
            source_label = Gtk.Label(label=source)
            source_label.add_css_class("caption")
            source_label.add_css_class("dim-label")
            row.add_suffix(source_label)
            
            # Add action buttons
            if is_installed and not kernel_data.get("is_running", False):
                # Uninstall button for installed kernels (not running)
                uninstall_btn = Gtk.Button()
                uninstall_btn.set_icon_name("user-trash-symbolic")
                uninstall_btn.set_tooltip_text(f"Uninstall {name}")
                uninstall_btn.connect("clicked", self._on_uninstall_clicked, kernel_data)
                uninstall_btn.set_valign(Gtk.Align.CENTER)
                row.add_suffix(uninstall_btn)
            elif not is_installed:
                # Install button for available kernels
                install_btn = Gtk.Button()
                install_btn.set_icon_name("software-install-symbolic")
                install_btn.set_tooltip_text(f"Install {name}")
                install_btn.connect("clicked", self._on_install_kernel, kernel_data)
                install_btn.set_valign(Gtk.Align.CENTER)
                row.add_suffix(install_btn)
            
            # Add the row to the group and make it activatable
            row.set_activatable(True)
            row.connect("activated", self._on_kernel_selected, kernel_data)
            group.add(row)
        except Exception as e:
            logger.exception(f"Error adding kernel to group: {str(e)}")
            
    def _add_error_row(self, message):
        """Add an error message to all groups."""
        for group in [self.installed_group, self.official_group, self.aur_group]:
            row = Adw.ActionRow()
            row.set_title(message)
            row.set_sensitive(False)
            group.add(row)
            
    def _on_kernel_selected(self, row, kernel_data):
        """Handler for when a kernel is selected."""
        self.selected_kernel = kernel_data
        logger.info(f"Selected kernel: {kernel_data.get('name', 'Unknown')}")
            
    def _on_install_kernel(self, button, kernel_data):
        """Handler for install button clicked directly on a kernel row."""
        kernel_name = kernel_data.get("name", "")
        if kernel_name:
            logger.info(f"Install button clicked for kernel: {kernel_name}")
            self._run_async_task(self._install_kernel_async(kernel_name))
                
    def _on_uninstall_clicked(self, button, kernel_data):
        """Handler for uninstall button clicked on a kernel row."""
        kernel_name = kernel_data.get("name", "")
        if kernel_name:
            # Show confirmation dialog
            dialog = Adw.MessageDialog(
                transient_for=self.main_window,
                heading=f"Uninstall Kernel",
                body=f"Are you sure you want to uninstall {kernel_name}?\n\nThis action cannot be undone."
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("uninstall", "Uninstall")
            dialog.set_response_appearance("uninstall", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_uninstall_confirmed, kernel_name)
            dialog.present()
            
    def _on_uninstall_confirmed(self, dialog, response, kernel_name):
        """Handler for uninstall confirmation dialog."""
        if response == "uninstall":
            logger.info(f"Uninstalling kernel: {kernel_name}")
            # Implementation for kernel uninstallation would go here
            # This is a placeholder - actual code would be needed
            self._show_error_dialog("Uninstall functionality is not implemented yet.")

    async def _install_kernel_async(self, kernel_name: str):
        GLib.idle_add(self.progress_bar.set_visible, True)
        GLib.idle_add(self.status_label.set_visible, True)
        
        success = False
        final_message = ""

        try:
            # Use mhwd-kernel to install the kernel
            process = await asyncio.create_subprocess_exec(
                "pkexec", "mhwd-kernel", "-i", kernel_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitor the installation progress
            current_progress = 0.1
            GLib.idle_add(self._update_progress, current_progress, f"Installing {kernel_name}...")
            
            # Read output line by line for progress updates
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                    
                line_text = line.decode().strip()
                if line_text:
                    # Update progress based on installation steps
                    if "Downloading" in line_text:
                        current_progress = 0.3
                    elif "Installing" in line_text:
                        current_progress = 0.6
                    elif "Configuring" in line_text:
                        current_progress = 0.8
                    GLib.idle_add(self._update_progress, current_progress, line_text)
            await process.wait()
            success = process.returncode == 0
            
            if success:
                final_message = f"Kernel {kernel_name} installation succeeded. Please reboot to use the new kernel."
            else:
                stderr_output = await process.stderr.read()
                error_msg = stderr_output.decode().strip()
                final_message = f"Kernel {kernel_name} installation failed: {error_msg}"
                
        except Exception as e:
            logger.exception(f"Error installing kernel via mhwd-kernel: {str(e)}")
            final_message = f"Error installing kernel: {str(e)}"
            success = False
        
        GLib.idle_add(self._update_progress, 1.0, final_message)
        self._show_info_dialog("Installation Complete" if success else "Installation Failed", final_message)
        
        GLib.idle_add(self.progress_bar.set_visible, False)
            
        if success:
            # Repopulate the kernel list
            self._run_async_task(self._populate_kernel_data_async())
                
    async def _rollback_kernel_async(self):
        GLib.idle_add(self.progress_bar.set_visible, True)
        GLib.idle_add(self.status_label.set_visible, True)

        success = False
        final_message = ""

        try:
            def progress_callback(fraction: float, message: str):
                GLib.idle_add(self._update_progress, fraction, message)

            success = await self.kernel_manager.rollback_kernel(progress_callback)
            
            final_message = f"Kernel rollback {'succeeded' if success else 'failed'}."
            if success:
                final_message += " Please reboot."
        except Exception as e:
            logger.exception(f"Error during kernel rollback: {str(e)}")
            final_message = f"Kernel rollback failed: {str(e)}"
            success = False

        GLib.idle_add(self._update_progress, 1.0, final_message)
        self._show_info_dialog("Rollback Complete" if success else "Rollback Failed", final_message)

        GLib.idle_add(self.progress_bar.set_visible, False)

        if success: # Repopulate list
             self._run_async_task(self._populate_kernel_data_async())

    def _show_error_dialog(self, message: str):
        dialog = Adw.MessageDialog(
            heading="Error",
            body=message,
            transient_for=self.main_window # Use main window as parent
        )
        dialog.add_response("ok", "OK")
        dialog.connect("response", lambda d, r: d.close())
        dialog.present()

    def _show_info_dialog(self, title: str, message: str):
        dialog = Adw.MessageDialog(
            heading=title,
            body=message,
            transient_for=self.main_window
        )
        dialog.add_response("ok", "OK")
        dialog.connect("response", lambda d, r: d.close())
        dialog.present()


class MesaView(Gtk.Box):
    """View for managing Mesa driver installations and updates."""
    def __init__(self, mesa_manager: MesaManager, main_window: Gtk.Window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.mesa_manager = mesa_manager
        self.main_window = main_window
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_margin_start(20)
        self.set_margin_end(20)
        
        current_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        current_section.set_margin_bottom(15)
        
        current_title = Gtk.Label()
        current_title.set_markup("<span weight='bold'>Current Mesa Version</span>")
        current_title.set_halign(Gtk.Align.START)
        
        self.current_mesa_label = Gtk.Label(label="Detecting Mesa version...")
        self.current_mesa_label.set_halign(Gtk.Align.START)
        
        current_section.append(current_title)
        current_section.append(self.current_mesa_label)
        
        options_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        options_title = Gtk.Label()
        options_title.set_markup("<span weight='bold'>Mesa Driver Options</span>")
        options_title.set_halign(Gtk.Align.START)
        options_section.append(options_title)
        
        self.stable_radio = Gtk.CheckButton(label="Mesa Stable")
        self.stable_radio.set_active(True)
        options_section.append(self.stable_radio)
                
        self.git_radio = Gtk.CheckButton(label="Mesa Git (Development)")
        self.git_radio.set_group(self.stable_radio) # Forms a radio group
        options_section.append(self.git_radio)
        
        self.multilib_check = Gtk.CheckButton(label="Include 32-bit libraries (multilib)")
        self.multilib_check.set_active(True)
        self.multilib_check.set_margin_top(5)
        options_section.append(self.multilib_check)
        
        buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons_box.set_homogeneous(True)
        buttons_box.set_margin_top(15)
        
        self.update_button = Gtk.Button(label="Update Mesa Drivers")
        self.update_button.connect("clicked", self._on_update_clicked)
        buttons_box.append(self.update_button)
        
        self.revert_button = Gtk.Button(label="Revert to Previous")
        self.revert_button.connect("clicked", self._on_revert_clicked)
        buttons_box.append(self.revert_button)
                
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_margin_top(10)
        self.progress_bar.set_visible(False) # Initially hidden
        
        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_margin_top(5)
        self.status_label.set_visible(False) # Initially hidden
        
        self.append(current_section)
        self.append(options_section)
        self.append(buttons_box)
        self.append(self.progress_bar)
        self.append(self.status_label)
        
        self._run_async_task(self._detect_mesa_version_async())

    def _run_async_task(self, coro):
        """Run an asyncio coroutine in a background thread."""
        def _run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        
        threading.Thread(target=_run_in_thread, daemon=True).start()

    def _update_progress(self, fraction: float, text: str) -> None:
        """Update the Mesa UI with progress information."""
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(text)
        self.status_label.set_text(text)
        if text and text.strip(): # If there is text, make status label visible
            self.status_label.set_visible(True)
        logger.info(f"Mesa UI Progress: {fraction*100:.0f}% - {text}")
        # In GTK4, we don't use events_pending() and main_iteration()
        # The UI update happens automatically through GLib.idle_add

    def _set_buttons_sensitive(self, sensitive: bool):
        self.update_button.set_sensitive(sensitive)
        self.revert_button.set_sensitive(sensitive)
        self.stable_radio.set_sensitive(sensitive)
        self.git_radio.set_sensitive(sensitive)
        self.multilib_check.set_sensitive(sensitive)

    async def _detect_mesa_version_async(self):
        GLib.idle_add(self.progress_bar.set_visible, True)
        GLib.idle_add(self.status_label.set_visible, True)
        self._set_buttons_sensitive(False)

        version = "Error"
        try:
            GLib.idle_add(self._update_progress, 0.0, "Detecting Mesa version...")
            version = await self.mesa_manager.detect_current_mesa()
            GLib.idle_add(self.current_mesa_label.set_text, f"Mesa {version} (Current)")
            GLib.idle_add(self._update_progress, 1.0, f"Mesa version: {version}")
        except Exception as e:
            logger.exception(f"Error detecting Mesa version: {str(e)}")
            GLib.idle_add(self.current_mesa_label.set_text, "Error detecting Mesa version")
            GLib.idle_add(self._update_progress, 1.0, f"Error: {str(e)}")
        finally:
            GLib.idle_add(self.progress_bar.set_visible, False)
            GLib.idle_add(self._set_buttons_sensitive, True)
    
    def _on_update_clicked(self, button):
        use_git = self.git_radio.get_active()
        use_multilib = self.multilib_check.get_active()
        
        version_type = "Git" if use_git else "Stable"
        multilib_text = "with" if use_multilib else "without"
        logger.info(f"Update Mesa clicked: {version_type}, {multilib_text} multilib.")
        
        self._run_async_task(self._install_mesa_async(use_git, use_multilib))

    async def _install_mesa_async(self, use_git: bool, use_multilib: bool):
        GLib.idle_add(self.progress_bar.set_visible, True)
        GLib.idle_add(self.status_label.set_visible, True)
        self._set_buttons_sensitive(False)

        success = False
        final_message = ""
        version_type = "Git" if use_git else "Stable"

        try:
            GLib.idle_add(self._update_progress, 0.0, f"Preparing to install Mesa {version_type}...")

            def progress_callback(fraction: float, message: str):
                GLib.idle_add(self._update_progress, fraction, message)

            success = await self.mesa_manager.install_mesa(use_git, use_multilib, progress_callback)
            
            final_message = f"Mesa {version_type} installation {'succeeded' if success else 'failed'}."
            if success:
                final_message += " Please reboot or restart your display server."
        except Exception as e:
            logger.exception(f"Error installing Mesa: {str(e)}")
            final_message = f"Mesa {version_type} installation failed: {str(e)}"
            success = False
        
        GLib.idle_add(self._update_progress, 1.0, final_message)
        self._show_info_dialog("Mesa Update Complete" if success else "Mesa Update Failed", final_message)

        GLib.idle_add(self.progress_bar.set_visible, False)
        GLib.idle_add(self._set_buttons_sensitive, True)

        if success: # Re-detect version
            self._run_async_task(self._detect_mesa_version_async())
    
    def _on_revert_clicked(self, button):
        logger.info("Revert Mesa clicked.")
        self._run_async_task(self._rollback_mesa_async())

    async def _rollback_mesa_async(self):
        GLib.idle_add(self.progress_bar.set_visible, True)
        GLib.idle_add(self.status_label.set_visible, True)
        self._set_buttons_sensitive(False)

        success = False
        final_message = ""

        try:
            GLib.idle_add(self._update_progress, 0.0, "Preparing to rollback Mesa...")

            def progress_callback(fraction: float, message: str):
                GLib.idle_add(self._update_progress, fraction, message)

            success = await self.mesa_manager.rollback_mesa(progress_callback)
            
            final_message = f"Mesa rollback {'succeeded' if success else 'failed'}."
            if success:
                 final_message += " Please reboot or restart your display server."
        except Exception as e:
            logger.exception(f"Error rolling back Mesa: {str(e)}")
            final_message = f"Mesa rollback failed: {str(e)}"
            success = False
        
        GLib.idle_add(self._update_progress, 1.0, final_message)
        self._show_info_dialog("Mesa Rollback Complete" if success else "Mesa Rollback Failed", final_message)

        GLib.idle_add(self.progress_bar.set_visible, False)
        GLib.idle_add(self._set_buttons_sensitive, True)

        if success: # Re-detect version
            self._run_async_task(self._detect_mesa_version_async())

    def _show_info_dialog(self, title: str, message: str):
        dialog = Adw.MessageDialog(
            heading=title,
            body=message,
            transient_for=self.main_window
        )
        dialog.add_response("ok", "OK")
        dialog.connect("response", lambda d, r: d.close())
        dialog.present()

class KernelMesaPage(Gtk.Box):
    """
    Kernel and Mesa update page component.
    This page allows users to manage kernel and Mesa versions.
    """
    
    def __init__(self, main_window: Optional[Gtk.Window] = None) -> None:
        """Initialize the Kernel and Mesa update page."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.main_window = main_window # Store main_window
        
        self.kernel_manager = KernelManager()
        self.mesa_manager = MesaManager()
        
        self._create_ui()
    
    def _create_ui(self) -> None:
        """Create the UI components for the page."""
        # Create a header with title
        header_label = Gtk.Label()
        header_label.set_markup("<span size='xx-large'>Kernel and Mesa Updates</span>")
        header_label.set_margin_top(20)
        header_label.set_margin_bottom(20)
        header_label.set_halign(Gtk.Align.CENTER)
        self.append(header_label)
        
        # Create a warning info bar
        self.info_bar = Gtk.InfoBar()
        self.info_bar.set_message_type(Gtk.MessageType.WARNING)
        self.info_bar.set_revealed(True)
        self.info_bar.set_show_close_button(True)
        
        # Add warning message - using GTK4 approach
        message_label = Gtk.Label(label="Warning: Updating kernels and Mesa drivers can affect system stability. Make sure to have a backup.")
        
        # In GTK4, add_child is used to add content directly to the InfoBar
        self.info_bar.add_child(message_label)
        
        # Connect close button
        self.info_bar.connect("response", self._on_info_bar_response)
        
        # Add info bar to the page
        self.append(self.info_bar)
        
        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        notebook.set_margin_top(10)
        notebook.set_margin_start(10)
        notebook.set_margin_end(10)
        notebook.set_margin_bottom(10)
        
        self.kernel_view = KernelView(self.kernel_manager, self.main_window) # Passar main_window
        kernel_label_tab = Gtk.Label(label="Kernels")
        notebook.append_page(self.kernel_view, kernel_label_tab)
        
        self.mesa_view = MesaView(self.mesa_manager, self.main_window) # Passar main_window
        mesa_label_tab = Gtk.Label(label="Mesa Drivers")
        notebook.append_page(self.mesa_view, mesa_label_tab)
                
        self.append(notebook)
        
        # O status bar foi movido para dentro de KernelView e MesaView
        # self.status_bar = Gtk.Label() ...

    def _on_info_bar_response(self, info_bar: Gtk.InfoBar, response_id: int) -> None:
        if response_id == Gtk.ResponseType.CLOSE:
            info_bar.set_revealed(False)


# --- Main Application Class for Testing ---
class MyApp(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = Adw.ApplicationWindow(application=self)
            self.window.set_title("Kernel & Mesa Updater")
            self.window.set_default_size(700, 800)

            # Adicionar Adw.ToastOverlay para mostrar toasts de Adw.MessageDialog
            self.toast_overlay = Adw.ToastOverlay()
            self.window.set_content(self.toast_overlay)

            kernel_mesa_page = KernelMesaPage(self.window) # Passar a janela principal
            
            # Usar Adw.Clamp para centralizar e limitar a largura da página
            clamp = Adw.Clamp()
            clamp.set_child(kernel_mesa_page)
            
            # Adw.ToolbarView para um layout moderno com headerbar
            toolbar_view = Adw.ToolbarView()
            header_bar = Adw.HeaderBar()
            header_bar.set_title_widget(Adw.WindowTitle(title="Kernel & Mesa Updater", subtitle="Manage your system components"))
            toolbar_view.add_top_bar(header_bar)
            toolbar_view.set_content(clamp) # Colocar o clamp (com a página) no conteúdo

            self.toast_overlay.set_child(toolbar_view) # Colocar o toolbar_view dentro do ToastOverlay

        self.window.present()

if __name__ == "__main__":
    # Configurar logging para debug
    logging.basicConfig(level=logging.DEBUG, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Integrar asyncio com o loop GLib
    # Esta é uma forma de fazer. Outra é usar um loop de evento asyncio que se integra com GLib.
    # Para Gtk4/Adwaita, geralmente o loop GLib já é compatível com tarefas asyncio se um loop asyncio estiver definido.
    
    loop = asyncio.get_event_loop() # Obter o loop de evento asyncio padrão

    app = MyApp(application_id="com.example.KernelMesaUpdater")
    exit_status = app.run(None) # loop.run_until_complete(app.run(None)) não é necessário com Gtk.Application.run
                               # Gtk.Application.run() já bloqueia e processa eventos.
                               # Tarefas asyncio criadas com asyncio.create_task() serão executadas.
    
    # O loop asyncio não precisa ser explicitamente executado com run_forever() aqui,
    # pois o Gtk.Application.run() assume o controle do loop principal.
    # No entanto, precisamos garantir que as tarefas asyncio possam ser processadas.
    # GLib.idle_add é crucial para interagir com a UI a partir de tarefas asyncio.
    
    # Em alguns casos, para garantir que o loop asyncio seja executado corretamente
    # junto com o loop GLib, pode ser necessário configurar um loop de evento asyncio
    # específico, como o AsyncGObjectEventLoop do pacote `agobject`.
    # Mas para muitos casos, o default funciona com `asyncio.create_task` e `GLib.idle_add`.

    # Se houver problemas com asyncio não rodando, pode-se tentar:
    # import sys
    # from agobject import GObjectEventLoop # pip install agobject
    # asyncio.set_event_loop(GObjectEventLoop())
    # loop = asyncio.get_event_loop()
    # sys.exit(loop.run_until_complete(app.run_async(sys.argv)))
    # Mas vamos tentar sem dependências extras primeiro.

    # A forma mais simples: Gtk.Application.run() e asyncio.create_task()
    # devem funcionar em ambientes modernos.