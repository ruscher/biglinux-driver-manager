import gi
import gettext # Assuming gettext is used for _
from typing import Dict, List, Any, Optional
import subprocess
import json
import threading # Added for asynchronous operations
from gi.repository import GLib # For idle_add

# Set up translation
_ = gettext.gettext # Or your specific setup

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

class SummaryView(Gtk.Box):
    """Summary view showing an overview of system hardware"""
    
    def __init__(self) -> None:
        """Initialize the summary view"""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)
        
        self.value_labels: Dict[str, Gtk.Label] = {}
        
        # Configuration for each information row
        # "id": stable key for internal use (e.g., in self.value_labels)
        # "label": untranslated display label
        # "data_key": key in the summary_data dictionary
        self.info_rows_config: List[Dict[str, str]] = [
            {"id": "os", "label": "Operating System", "data_key": "os_name"},
            {"id": "hostname", "label": "Hostname", "data_key": "hostname"},
            {"id": "kernel", "label": "Kernel", "data_key": "kernel_version"},
            {"id": "cpu", "label": "CPU", "data_key": "cpu_model"},
            {"id": "memory", "label": "Memory", "data_key": "total_memory_gb"},
            {"id": "graphics", "label": "Graphics", "data_key": "gpu_models"},
            {"id": "disk", "label": "Disk", "data_key": "total_storage_gb"},
        ]
        
        self._create_content()
    
    def _create_content(self) -> None:
        """Create the content for the summary view"""
        # Add title
        title = Gtk.Label()
        title.set_markup(f"<span size='xx-large' weight='bold'>{_('System Overview')}</span>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(24)
        self.append(title)
        
        # Create a grid for system information
        grid = Gtk.Grid()
        grid.set_column_spacing(24)
        grid.set_row_spacing(12)
        
        # Add system information based on config
        for i, config_item in enumerate(self.info_rows_config):
            translated_label = _(config_item["label"])
            self._add_info_row(grid, i, translated_label, config_item["id"], _("Loading..."))
        
        # Add grid to view
        self.append(grid)
        
        # Load system information
        self.refresh()
    
    def _add_info_row(self, grid: Gtk.Grid, row: int, translated_label_text: str, widget_id_key: str, value_text: str) -> None:
        """
        Add an information row to the grid
        
        Args:
            grid: The grid to add the row to
            row: The row index
            translated_label_text: The translated label text for display
            widget_id_key: A stable, non-translated key for this row
            value_text: The initial value text
        """
        # Create label
        label = Gtk.Label(label=translated_label_text)
        label.add_css_class("dim-label")
        label.set_halign(Gtk.Align.START)
        
        # Create value
        value = Gtk.Label(label=value_text)
        value.set_halign(Gtk.Align.START)
        value.set_hexpand(True)
        
        # Add to grid
        grid.attach(label, 0, row, 1, 1)
        grid.attach(value, 1, row, 1, 1)
        
        # Keep a reference to the value label for easy updates
        self.value_labels[widget_id_key] = value
    
    def refresh(self) -> None:
        """Refresh the summary information"""
        self.load_summary_data()
    
    def update_info(self, summary_data: Optional[Dict[str, Any]]) -> None:
        """
        Update the summary information displayed.

        Args:
            summary_data: A dictionary containing the summary data. 
                          Keys should correspond to 'data_key' in info_rows_config.
                          If None, all fields will be set to "N/A".
        """
        if not summary_data:
            # Handle case where summary_data might be None or empty
            for key in self.value_labels:
                self.value_labels[key].set_text(_("N/A"))
            return

        for config_item in self.info_rows_config:
            widget_id = config_item["id"]
            data_key = config_item["data_key"]
            
            if widget_id in self.value_labels:
                value_to_set = summary_data.get(data_key) # Get value, could be None
                
                if value_to_set is None:
                    display_text = _("N/A")
                elif isinstance(value_to_set, list): # e.g. for GPUs
                    # Filter out None or empty strings before joining
                    filtered_list = [str(item) for item in value_to_set if item]
                    display_text = ", ".join(filtered_list) if filtered_list else _("N/A")
                else:
                    display_text = str(value_to_set)
                
                self.value_labels[widget_id].set_text(display_text)

    def _parse_system_data(self, raw_inxi_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parses the raw data (expected from inxi -j) and transforms it
        into the structure expected by update_info.
        
        Args:
            raw_inxi_data: The raw JSON data from inxi (typically a list of dictionaries).
                           We expect specific keys based on inxi output.
        
        Returns:
            A dictionary with keys matching self.info_rows_config["data_key"].
        """
        parsed_data: Dict[str, Any] = {}
        
        # Example parsing logic (highly dependent on actual inxi JSON structure)
        # This needs to be robust and handle missing keys gracefully.
        # inxi -j output is a list of dictionaries, each representing a category.
        
        for item in raw_inxi_data:
            if "System" in item:
                system_info = item["System"]
                distro = system_info.get('distro', '')
                release = system_info.get('release', '')
                build = system_info.get('build', '')
                
                # Create a more informative OS name with distro, release and build if available
                os_parts = [part for part in [distro, release, build] if part]
                parsed_data["os_name"] = " ".join(os_parts).strip()
                parsed_data["hostname"] = system_info.get("host", _("Unknown"))
                parsed_data["kernel_version"] = system_info.get("kernel", _("Unknown"))
                
                # Add uptime information if available
                if "uptime" in system_info:
                    parsed_data["uptime"] = system_info["uptime"]
            
            elif "CPU" in item:
                cpu_info = item["CPU"]
                cpu_model = cpu_info.get("model", _("Unknown CPU"))
                
                # Format CPU information with frequencies if available
                if all(key in cpu_info for key in ['speed', 'speed_max', 'speed_min']):
                    parsed_data["cpu_model"] = f"{cpu_model} @ {cpu_info['speed']}MHz"
                    parsed_data["cpu_model"] += f" (Min: {cpu_info['speed_min']}MHz, Max: {cpu_info['speed_max']}MHz)"
                else:
                    parsed_data["cpu_model"] = cpu_model
                
                # Add number of cores/threads if available
                if "cores" in cpu_info:
                    core_info = cpu_info["cores"]
                    if isinstance(core_info, dict):
                        physical = core_info.get("physical", "")
                        logical = core_info.get("logical", "")
                        if physical and logical:
                            parsed_data["cpu_cores"] = f"{physical} cores, {logical} threads"
            
            elif "Memory" in item:
                mem_info = item["Memory"]
                # Handle different inxi output formats
                if isinstance(mem_info, dict):
                    if "System" in mem_info and isinstance(mem_info["System"], dict):
                        # Format from inxi -jmy0
                        system_mem = mem_info["System"]
                        parsed_data["total_memory_gb"] = system_mem.get("total", _("Unknown"))
                        parsed_data["used_memory"] = system_mem.get("used", "")
                        
                        # Calculate memory usage percentage if available
                        if "used" in system_mem and "total" in system_mem and "used_percent" in system_mem:
                            used_percent = system_mem.get("used_percent", "")
                            if used_percent:
                                parsed_data["memory_usage"] = f"{system_mem['used']} ({used_percent})"
                                # Add this combined usage info to the main memory display
                                parsed_data["total_memory_gb"] = f"{system_mem['total']} - {parsed_data['memory_usage']}"
                        
                        # Add swap information if available
                        if "swap" in mem_info and isinstance(mem_info["swap"], dict):
                            swap_info = mem_info["swap"]
                            if "total" in swap_info and "used" in swap_info:
                                swap_total = swap_info["total"]
                                swap_used = swap_info["used"]
                                
                                # Format swap usage
                                if "used_percent" in swap_info:
                                    swap_percent = swap_info["used_percent"]
                                    parsed_data["swap_info"] = f"{swap_total} - {swap_used} ({swap_percent})"
                                else:
                                    parsed_data["swap_info"] = f"{swap_total} - {swap_used}"
                                    
                    elif "total" in mem_info:
                        # Alternative format
                        parsed_data["total_memory_gb"] = mem_info.get("total", _("Unknown"))
                        if "used" in mem_info and "free" in mem_info:
                            used_mem = mem_info["used"]
                            free_mem = mem_info["free"]
                            
                            # Try to calculate percentage if not provided
                            try:
                                # Extract numeric values - this is a simplified approach
                                used_val = float(''.join(filter(lambda x: x.isdigit() or x == '.', used_mem)))
                                total_val = float(''.join(filter(lambda x: x.isdigit() or x == '.', mem_info["total"])))
                                
                                if total_val > 0:
                                    percent = (used_val / total_val) * 100
                                    parsed_data["total_memory_gb"] = f"{mem_info['total']} - {used_mem} ({percent:.1f}%)"
                                else:
                                    parsed_data["total_memory_gb"] = f"{mem_info['total']} - {used_mem}"
                            except (ValueError, TypeError):
                                # Fallback if calculation fails
                                parsed_data["total_memory_gb"] = f"{mem_info['total']} - {used_mem}"
            
            elif "Graphics" in item:
                graphics_info = item["Graphics"]
                gpu_models = []
                gpu_details = []
                
                if "devices" in graphics_info and isinstance(graphics_info["devices"], list):
                    for device in graphics_info["devices"]:
                        # Basic model info
                        model = device.get("model", _("Unknown GPU"))
                        gpu_models.append(model)
                        
                        # Build detailed info with driver and memory if available
                        detail_parts = [model]
                        if "driver" in device:
                            driver_info = f"Driver: {device['driver']}"
                            detail_parts.append(driver_info)
                        
                        if "vram" in device:
                            vram_info = f"VRAM: {device['vram']}"
                            detail_parts.append(vram_info)
                            
                        gpu_details.append(" | ".join(detail_parts))
                
                # Store both simple list and detailed information
                parsed_data["gpu_models"] = gpu_models if gpu_models else [_("N/A")]
                parsed_data["gpu_details"] = gpu_details if gpu_details else [_("N/A")]
                
                # Store display information if available
                if "display" in graphics_info:
                    display_info = []
                    displays = graphics_info["display"]
                    if isinstance(displays, list):
                        for display in displays:
                            if isinstance(display, dict):
                                resolution = display.get("resolution", "")
                                size = display.get("size", "")
                                if resolution and size:
                                    display_info.append(f"{resolution} ({size})")
                                elif resolution:
                                    display_info.append(resolution)
                    
                    if display_info:
                        parsed_data["displays"] = display_info
            
            elif "Drives" in item:
                drives_info = item["Drives"]
                if isinstance(drives_info, dict):
                    # Get total storage
                    if "local" in drives_info and "total_size" in drives_info["local"]:
                        parsed_data["total_storage_gb"] = drives_info["local"]["total_size"]
                    
                    # Get detailed list of drives
                    drives_list = []
                    if "local" in drives_info and "storage" in drives_info["local"]:
                        storage_list = drives_info["local"]["storage"]
                        if isinstance(storage_list, list):
                            for drive in storage_list:
                                if isinstance(drive, dict):
                                    drive_details = []
                                    # Collect key drive information
                                    for key in ["vendor", "model", "size"]:
                                        if key in drive:
                                            drive_details.append(drive[key])
                                    
                                    # Add device type (SSD, HDD, etc.)
                                    if "type" in drive:
                                        drive_details.append(f"({drive['type']})")
                                    
                                    if drive_details:
                                        drives_list.append(" ".join(drive_details))
                    
                    if drives_list:
                        parsed_data["drives_list"] = drives_list

            elif "Network" in item:
                # Add network interface information
                network_info = item["Network"]
                if isinstance(network_info, dict) and "interfaces" in network_info:
                    interfaces = network_info["interfaces"]
                    if isinstance(interfaces, list):
                        network_list = []
                        for interface in interfaces:
                            if isinstance(interface, dict):
                                # Build interface description
                                iface_name = interface.get("ifname", "")
                                device = interface.get("device", "")
                                mac = interface.get("mac", "")
                                
                                if iface_name and device:
                                    network_list.append(f"{iface_name}: {device} ({mac})")
                        
                        if network_list:
                            parsed_data["network_interfaces"] = network_list

        return parsed_data

    def _fetch_and_parse_data_thread(self) -> None:
        """
        Worker function to fetch and parse system data in a separate thread.
        Calls self.update_info via GLib.idle_add on completion or error.
        """
        try:
            # Simplified command to get hardware information
            # Some parameters might not be compatible with the installed inxi version
            # Start with basic parameters
            cmd = ["inxi", "-F", "-J"]  # -F for full output, -J for JSON format
            
            process = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
            raw_data_list = json.loads(process.stdout)
            parsed_data = self._parse_system_data(raw_data_list)
            GLib.idle_add(self.update_info, parsed_data)
        except subprocess.CalledProcessError as e:
            print(f"Error running inxi: {e}")
            # Try an even more basic command as fallback
            try:
                cmd = ["inxi", "-J"]
                process = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
                raw_data_list = json.loads(process.stdout)
                parsed_data = self._parse_system_data(raw_data_list)
                GLib.idle_add(self.update_info, parsed_data)
            except Exception as inner_e:
                print(f"Fallback inxi command also failed: {inner_e}")
                GLib.idle_add(self.update_info, None)
        except json.JSONDecodeError as e:
            print(f"Error parsing inxi JSON output: {e}")
            GLib.idle_add(self.update_info, None)
        except FileNotFoundError:
            print("Error: inxi command not found. Please ensure it is installed and in PATH.")
            GLib.idle_add(self.update_info, None)
        except Exception as e: # Catch any other unexpected errors
            print(f"An unexpected error occurred during data fetching: {e}")
            GLib.idle_add(self.update_info, None)

    def load_summary_data(self) -> None:
        """
        Load the summary data by calling inxi asynchronously.
        """
        # Set all labels to "Loading..." before starting the thread
        for key in self.value_labels:
            self.value_labels[key].set_text(_("Loading..."))

        # Create and start a new thread for data fetching and parsing
        thread = threading.Thread(target=self._fetch_and_parse_data_thread)
        thread.daemon = True  # Allow main program to exit even if thread is running
        thread.start()
