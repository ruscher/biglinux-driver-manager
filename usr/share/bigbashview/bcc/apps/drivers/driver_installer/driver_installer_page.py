"""
Driver Installer Page - NavigationSplitView Version

This module provides a modern driver installer page using NavigationSplitView
with categories in the sidebar and driver listings in the content area.
"""
import gi
import logging
import subprocess
import json
import os
import threading
import shutil
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, GObject, Pango

# Get the absolute path to the current script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Get parent directory for scripts (bcc/apps/drivers)
PARENT_DIR = os.path.dirname(SCRIPT_DIR)

# Constants
DEFAULT_MARGINS = 16
LOADING_TIMEOUT = 30  # seconds
OPERATION_TIMEOUT = 300  # 5 minutes for package operations

# Define script paths with absolute paths
DRIVERS_SCRIPT = os.path.join(PARENT_DIR, "list_drivers.sh")
DRIVERS_JSON_OUTPUT = "/tmp/drivers_list.json"
HARDWARE_DETECT_SCRIPT = os.path.join(PARENT_DIR, "hardware_detect.sh")

# Set up logger
logger = logging.getLogger(__name__)

# Ensure the logger is properly configured
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Debug information at startup
logger.info(f"Script directory: {SCRIPT_DIR}")
logger.info(f"Parent directory: {PARENT_DIR}")
logger.info(f"Drivers script path: {DRIVERS_SCRIPT}")
logger.info(f"Hardware detect script path: {HARDWARE_DETECT_SCRIPT}")

# Log if scripts exist
logger.info(f"Drivers script exists: {os.path.exists(DRIVERS_SCRIPT)}")
logger.info(f"Hardware detect script exists: {os.path.exists(HARDWARE_DETECT_SCRIPT)}")

class CategoryItem(GObject.Object):
    """Category item for the sidebar."""
    def __init__(self, key: str, label: str, count: int = 0):
        super().__init__()
        self.key = key
        self.label = label
        self.count = count

class CategoryRow(Gtk.ListBoxRow):
    def __init__(self, category_id: str, title: str, icon_name: str):
        super().__init__()
        self.category_id = category_id
        self.set_name(f"category-row-{category_id.lower().replace(' ', '-')}")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            box.append(icon)
        label = Gtk.Label(label=title)
        label.set_xalign(0)
        box.append(label)
        self.set_child(box)

class DriverInstallerPage(Gtk.Box):
    """Modern Driver Installer page with NavigationSplitView.
    
    Features:
    - Sidebar with driver categories
    - Content area with driver listings
    - Install/uninstall functionality
    - Real-time status updates
    """
    
    def __init__(self) -> None:
        """Initialize the driver installer page."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._initialize_properties()
        self._check_dependencies()
        self._create_ui()
        self._load_drivers()
    
    def _initialize_properties(self):
        """Initialize all class properties."""
        self.drivers_data = {}  # Dict[category_key, List[driver]]
        self.detected_drivers_data = []  # List of drivers detected by hardware_detect.sh
        self.current_category = "all"
        self.selected_row = None
        self._operation_lock = threading.Lock()
        self.pulse_id = 0
        self.error_box_container = None
        self.search_results_group = None # For displaying search results
        # UI components
        self.split_view = None
        self.category_list = None
        self.content_scroll = None
        self.content_box = None
        self.content_view = None
        self.progress_bar = None
        self.toast_overlay = Adw.ToastOverlay()  # Initialize here to ensure it exists
        self.detected_drivers_group = None  # Group for detected drivers
        self.category_list = None
        # Create a minimal fallback script immediately to ensure it exists
        if not os.path.exists(DRIVERS_SCRIPT):
            try:
                self._create_drivers_script("/tmp/list_drivers.sh")
            except Exception as e:
                logger.error(f"Error creating fallback script: {e}")
        
    def _check_dependencies(self) -> bool:
        """Check for required system dependencies."""
        required = ["lspci", "lscpu", "pkexec", "pacman", "jq"]
        missing = []
        for cmd in required:
            if not shutil.which(cmd):
                missing.append(cmd)
        if missing:
            self._show_error_dialog(
                "Dependências ausentes",
                f"Os seguintes comandos são necessários:\n{', '.join(missing)}"
            )
            return False
        return True

    def _create_ui(self) -> None:
        """Create the modern UI exactly like hardware_info_page."""
        # Header box with title and refresh button (same as hardware_info_page)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(12)
        header_box.set_margin_start(12)
        header_box.set_margin_end(12)
        title_label = Gtk.Label()
        title_label.set_markup("<b>Gerenciador de Drivers</b>")
        title_label.set_hexpand(True)
        title_label.set_halign(Gtk.Align.START)
        title_label.add_css_class("title-4")
        header_box.append(title_label)
        
        # Add search entry directly in the header
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Buscar drivers...")
        self.search_entry.set_halign(Gtk.Align.CENTER)
        self.search_entry.set_margin_end(8)
        self.search_entry.set_width_chars(25)  # Adjust the width to fit nicely
        self.search_entry.connect("search-changed", self._on_direct_search_changed)
        header_box.append(self.search_entry)
        
        # Refresh button
        refresh_button = Gtk.Button()
        refresh_button.set_icon_name("view-refresh-symbolic")
        refresh_button.set_tooltip_text("Recarregar drivers")
        refresh_button.connect("clicked", self._on_refresh_clicked)
        header_box.append(refresh_button)
        
        self.append(header_box)
        
        # Toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Remove the separate search bar since we now have search in the header
        
        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.append(separator)
        
        # Progress bar (same as hardware_info_page)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_halign(Gtk.Align.CENTER)
        self.progress_bar.set_valign(Gtk.Align.CENTER)
        self.progress_bar.set_vexpand(True)
        self.progress_bar.set_pulse_step(0.1)
        self.progress_bar.set_show_text(False)
        self.progress_bar.set_tooltip_text("Carregando informações dos drivers...")
        main_box.append(self.progress_bar)
        
        # NavigationSplitView (same structure as hardware_info_page)
        self.split_view = Adw.NavigationSplitView()
        self.split_view.set_vexpand(True)
        self.split_view.set_sidebar_width_fraction(0.3)
        self.split_view.set_min_sidebar_width(280)
        self.split_view.set_max_sidebar_width(450)
        self.split_view.set_visible(False)
        
        # Sidebar
        sidebar = Adw.NavigationPage.new(Gtk.Box(), "Categorias de Drivers")
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.category_list = Gtk.ListBox()
        self.category_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.category_list.set_css_classes(["navigation-sidebar"])
        self.category_list.connect("row-selected", self._on_category_selected)
        sidebar_scroll.set_child(self.category_list)
        sidebar.set_child(sidebar_scroll)
        
        # Content area with clamp (same as hardware_info_page)
        self.content_view = Adw.NavigationPage.new(Gtk.Box(), "Detalhes")
        self.content_scroll = Gtk.ScrolledWindow()
        self.content_scroll.set_vexpand(True)
        # Use Adw.Clamp for content like hardware_info_page
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.set_margin_top(12)
        self.content_box.set_margin_bottom(24)
        self.content_box.set_margin_start(18)
        self.content_box.set_margin_end(18)
        self.content_box.set_spacing(18)
        
        # Add a group for detected drivers at the top
        self.detected_drivers_group = Adw.PreferencesGroup()
        self.detected_drivers_group.set_title("Drivers Detectados")
        self.detected_drivers_group.set_description("Drivers recomendados com base no hardware detectado")
        self.detected_drivers_group.set_visible(False)  # Initially hidden until we have data
        self.content_box.append(self.detected_drivers_group)
        
        clamp.set_child(self.content_box)
        self.content_scroll.set_child(clamp)
        self.content_view.set_child(self.content_scroll)
        self.split_view.set_sidebar(sidebar)
        self.split_view.set_content(self.content_view)
        main_box.append(self.split_view)
        
        # Set the toast overlay's child to the main box
        self.toast_overlay.set_child(main_box)
        self.append(self.toast_overlay)
        
        # Add some debug message
        toast = Adw.Toast.new("Iniciando Gerenciador de Drivers")
        toast.set_timeout(2)
        self.toast_overlay.add_toast(toast)

    def _pulse_progress_bar(self) -> bool:
        """Pulse progress bar animation (same as hardware_info_page)."""
        if self.progress_bar.get_visible():
            self.progress_bar.pulse()
            return True
        self.pulse_id = 0
        return False

    def _fetch_drivers_data(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Fetch drivers data using the bash script."""
        try:
            print("Fetching drivers data...")
            
            # Create script if it doesn't exist
            script_path = self._ensure_drivers_script()
            print(f"Using script at: {script_path}")
            
            # Log script content for debugging
            try:
                with open(script_path, 'r') as f:
                    script_content = f.read()
                    logger.info(f"Script content first 100 chars: {script_content[:100]}...")
                    print(f"Script is executable: {os.access(script_path, os.X_OK)}")
            except Exception as e:
                logger.warning(f"Failed to read script content: {e}")
            
            # Run the script with explicit shell=True for better compatibility
            print(f"Executing: bash {script_path}")
            result = subprocess.run(
                ["bash", script_path],
                capture_output=True,
                text=True,
                timeout=LOADING_TIMEOUT,
                check=False
            )
            
            print(f"Script executed with return code: {result.returncode}")
            if result.stdout:
                print(f"Script stdout (first 100 chars): {result.stdout[:100]}...")
            if result.stderr:
                print(f"Script stderr: {result.stderr}")
            
            # Check if JSON file was created
            if not os.path.exists(DRIVERS_JSON_OUTPUT):
                logger.error(f"JSON output file not created at {DRIVERS_JSON_OUTPUT}")
                print(f"JSON output file not created at {DRIVERS_JSON_OUTPUT}")
                
                # Create empty JSON file as fallback
                with open(DRIVERS_JSON_OUTPUT, 'w', encoding='utf-8') as f:
                    f.write('[]')
            
            # Read JSON from file
            with open(DRIVERS_JSON_OUTPUT, 'r', encoding='utf-8') as f:
                drivers_list = json.load(f)
            
            if not isinstance(drivers_list, list):
                logger.error("Invalid JSON format: expected list")
                print("Invalid JSON format: expected list")
                drivers_list = []
            
            # Only show a warning if no drivers were found, don't create fake test data
            if not drivers_list:
                logger.warning("No drivers found in the JSON file")
                print("No drivers found in the JSON file")
            
            # Group by category
            grouped = {}
            for driver in drivers_list:
                if not isinstance(driver, dict):
                    continue
                    
                category = driver.get('category', 'unknown')
                if category not in grouped:
                    grouped[category] = []
                grouped[category].append(driver)
            
            print(f"Loaded {len(drivers_list)} drivers in {len(grouped)} categories")
            logger.info(f"Loaded {len(drivers_list)} drivers in {len(grouped)} categories")
            return grouped
            
        except subprocess.TimeoutExpired:
            logger.error("Script execution timed out")
            print("Script execution timed out")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            print(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching drivers: {e}")
            print(f"Error fetching drivers: {e}")
            return None

    def _fetch_detected_hardware_drivers(self) -> List[Dict[str, Any]]:
        """Fetch drivers recommended by hardware detection."""
        try:
            logger.info("Fetching detected hardware drivers...")
            
            # First, set up the hardware detection script using relative paths
            setup_script_locations = [
                os.path.join(PARENT_DIR, "setup_hardware_detect.sh"),
                os.path.join(SCRIPT_DIR, "setup_hardware_detect.sh"),
                "setup_hardware_detect.sh",
                "../setup_hardware_detect.sh",
                "../../setup_hardware_detect.sh"
            ]
            
            setup_script = None
            for location in setup_script_locations:
                if os.path.exists(location):
                    setup_script = location
                    logger.info(f"Found setup script at: {location}")
                    break
                    
            if setup_script:
                try:
                    logger.info(f"Running setup script: {setup_script}")
                    setup_result = subprocess.run(
                        ["bash", setup_script], 
                        check=True, 
                        timeout=5,
                        capture_output=True,
                        text=True
                    )
                    logger.info(f"Setup script output: {setup_result.stdout}")
                    if setup_result.stderr:
                        logger.warning(f"Setup script stderr: {setup_result.stderr}")
                    logger.info("Hardware detection script setup completed")
                except Exception as e:
                    logger.warning(f"Failed to setup hardware detection script: {e}")
            
            # Check for hardware detection script in standard locations with relative paths
            script_locations = [
                HARDWARE_DETECT_SCRIPT,
                os.path.join(PARENT_DIR, "hardware_detect.sh"),
                os.path.join(SCRIPT_DIR, "hardware_detect.sh"),
                "hardware_detect.sh",
                "../hardware_detect.sh",
                "../../hardware_detect.sh",
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "hardware_detect.sh")
            ]
            
            # Only use system paths as a last resort
            if shutil.which("hardware_detect.sh"):
                script_locations.append(shutil.which("hardware_detect.sh"))
            
            hardware_detect_script = None
            for location in script_locations:
                if os.path.exists(location):
                    hardware_detect_script = location
                    logger.info(f"Found hardware detection script at: {location}")
                    
                    # Check if the script is executable and fix if needed
                    if not os.access(location, os.X_OK):
                        try:
                            os.chmod(location, 0o755)
                            logger.info(f"Added executable permission to: {location}")
                        except Exception as e:
                            logger.warning(f"Could not set executable permission: {e}")
                    
                    break
                    
            if not hardware_detect_script:
                logger.warning("Hardware detection script not found, will use minimal placeholder")
                hardware_detect_script = self._create_minimal_hardware_detect_script()
            
            # Use a timeout to prevent UI freezing
            hardware_detect_timeout = min(LOADING_TIMEOUT, 20)
            logger.info(f"Executing hardware detection script: {hardware_detect_script}")
            
            # Log script content for debugging
            try:
                with open(hardware_detect_script, 'r') as f:
                    script_content = f.read()
                    logger.info(f"Hardware script content (first 100 chars): {script_content[:100]}...")
            except Exception as e:
                logger.warning(f"Failed to read hardware script content: {e}")
            
            # Run the hardware detection script
            try:
                result = subprocess.run(
                    ["bash", hardware_detect_script],
                    capture_output=True,
                    text=True,
                    timeout=hardware_detect_timeout,
                    check=False
                )
                
                logger.info(f"Hardware script executed with return code: {result.returncode}")
                if result.stdout:
                    logger.info(f"Hardware script stdout (first 100 chars): {result.stdout[:100]}...")
                if result.stderr:
                    logger.info(f"Hardware detection stderr: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.error(f"Hardware detection script execution timed out after {hardware_detect_timeout}s")
                return []
            
            if result.returncode != 0:
                logger.error(f"Hardware detection script failed with code {result.returncode}: {result.stderr}")
                return []
            
            if not result.stdout:
                logger.warning("Hardware detection script produced no output")
                return []
            
            # Parse the JSON output with validation
            try:
                detected_drivers = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error from hardware detection: {e}")
                logger.error(f"Raw output was: {result.stdout[:200]}...")
                return []
            
            if not isinstance(detected_drivers, list):
                logger.error(f"Invalid JSON format from hardware detection: expected list, got {type(detected_drivers)}")
                return []
            
            # Log the full count of drivers detected
            print(f"Hardware detection found {len(detected_drivers)} drivers")
            
            # Filter out invalid entries
            valid_drivers = []
            for driver in detected_drivers:
                if not isinstance(driver, dict):
                    continue
                    
                # Validate required fields
                if not driver.get('name') or not driver.get('package'):
                    continue
                    
                valid_drivers.append(driver)
            
            logger.info(f"Loaded {len(valid_drivers)} valid detected hardware drivers")
            return valid_drivers
                
        except Exception as e:
            logger.error(f"Unexpected error fetching detected hardware drivers: {e}", exc_info=True)
            return []

    def _create_minimal_hardware_detect_script(self) -> str:
        """Create a minimal hardware detection script that returns empty JSON."""
        script_path = "/tmp/hardware_detect.sh"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write('''#!/bin/bash
# Minimal hardware detection script
echo "Script executed at $(date)"
echo "Working directory: $(pwd)"
echo "[]"
''')
        os.chmod(script_path, 0o755)
        logger.info(f"Created minimal hardware detection script at {script_path}")
        return script_path

    def _ensure_drivers_script(self) -> str:
        """Ensure the drivers script exists and return its path."""
        # Use more locations with both absolute and relative paths
        script_locations = [
            DRIVERS_SCRIPT,
            os.path.join(PARENT_DIR, "list_drivers.sh"),
            os.path.join(SCRIPT_DIR, "list_drivers.sh"),
            "list_drivers.sh",
            "../list_drivers.sh",
            "../../list_drivers.sh"
        ]
        
        # Only use system paths as a last resort
        if shutil.which("list_drivers.sh"):
            script_locations.append(shutil.which("list_drivers.sh"))
        
        # Check each location
        for location in script_locations:
            if os.path.exists(location):
                # Verify the script is executable
                if not os.access(location, os.X_OK):
                    logger.warning(f"Script exists but not executable: {location}")
                    try:
                        os.chmod(location, 0o755)
                        logger.info(f"Added executable permission to: {location}")
                    except Exception as e:
                        logger.warning(f"Could not set executable permission: {e}")
                
                logger.info(f"Found drivers script at {location}")
                print(f"Using script at: {location}")
                return location
        
        # Create minimal script if not found
        script_path = "/tmp/list_drivers.sh"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write('''#!/bin/bash
# Minimal drivers list script
echo "Script executed at $(date)"
echo "Working directory: $(pwd)"
echo "[]" > /tmp/drivers_list.json
echo "Script execution log: Created empty JSON file at /tmp/drivers_list.json"
echo "[]"
''')
        os.chmod(script_path, 0o755)
        logger.info(f"Created minimal drivers script at {script_path}")
        return script_path

    def _create_drivers_script(self, script_path: str):
        """Create a minimal fallback script that just outputs empty JSON."""
        with open(script_path, 'w') as f:
            f.write('''#!/bin/bash
# Minimal fallback script
echo "Script executed at $(date)"
echo "Working directory: $(pwd)"
echo "[]" > /tmp/drivers_list.json
echo "Script created empty JSON file at /tmp/drivers_list.json"
echo "[]"
''')
        os.chmod(script_path, 0o755)
        logger.info(f"Created minimal fallback script at {script_path}")

    def _on_drivers_loaded(self, drivers_data: Optional[Dict[str, List[Dict[str, Any]]]], detected_drivers: List[Dict[str, Any]]):
        """Handle successful driver loading."""
        if drivers_data is None and not detected_drivers:
            self._show_error_message("Falha ao carregar dados dos drivers")
            return
        
        if drivers_data:
            self.drivers_data = drivers_data
            # Log driver data for debugging
            total_drivers = sum(len(drivers) for drivers in drivers_data.values())
            print(f"Drivers loaded successfully: {len(drivers_data)} categories with {total_drivers} total drivers")
            
            # Log each category and its driver count
            for category, drivers in drivers_data.items():
                print(f"Category '{category}' has {len(drivers)} drivers")
        else:
            self.drivers_data = {}
            print("No categorized drivers data loaded")
        
        self.detected_drivers_data = detected_drivers
        print(f"Detected drivers loaded: {len(detected_drivers)}")
        
        # Simply call update UI with data - no need to clear here, that's done in _update_ui_with_data
        self._update_ui_with_data()
    
    def _update_ui_with_data(self) -> None:
        """Update UI with loaded data (same pattern as hardware_info_page)."""
        if self.pulse_id > 0:
            GLib.source_remove(self.pulse_id)
            self.pulse_id = 0
        
        self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_visible(False)
        self.split_view.set_visible(True)
        
        # Completely rebuild the content area from scratch instead of trying to clear it
        self._rebuild_content_area()
        
        # Clear existing categories
        while child := self.category_list.get_first_child():
            self.category_list.remove(child)
        
        # Add "Principal" category for detected drivers at the top
        has_detected_drivers = len(self.detected_drivers_data) > 0
        
        # Create and add the Principal item (always add it, even if empty)
        principal_row = CategoryRow("principal", f"Principal ({len(self.detected_drivers_data)})", "starred-symbolic")
        principal_row.add_css_class("sidebar-header-row")  # Optional: add custom styling
        self.category_list.append(principal_row)
        
        # Category icon mapping
        category_icon_mapping = {
            "Placa de vídeo": "video-display-symbolic",
            "WiFi": "network-wireless-symbolic",
            "Rede cabeada": "network-wired-symbolic",
            "Bluetooth": "bluetooth-symbolic",
            "Impressora": "printer-symbolic",
            "Impressora 3D": "printer-symbolic",
            "Scanner": "scanner-symbolic",
            "TV Digital": "tv-symbolic",
            "Webcam": "camera-web-symbolic",
            "Touchscreen": "input-touchpad-symbolic",
            "Som": "audio-card-symbolic",
            "Firmware": "application-x-firmware-symbolic",
            "Outros": "package-x-generic-symbolic"
        }
        
        # Category labels mapping
        category_labels = {
            "gpu": "Placa de vídeo",
            "wifi": "WiFi",
            "ethernet": "Rede cabeada",
            "bluetooth": "Bluetooth",
            "printer": "Impressora",
            "printer3d": "Impressora 3D",
            "scanner": "Scanner",
            "dvb": "TV Digital",
            "webcam": "Webcam",
            "touchscreen": "Touchscreen",
            "sound": "Som",
            "firmware": "Firmware",
            "unknown": "Outros"
        }
        
        # Category order (priority-based like hardware_info_page)
        category_order = {
            "Placa de vídeo": 10,
            "Som": 20,
            "WiFi": 30,
            "Rede cabeada": 40,
            "Bluetooth": 50,
            "Impressora": 60,
            "Scanner": 70,
            "Webcam": 80,
            "Touchscreen": 90,
            "TV Digital": 100,
            "Firmware": 110,
            "Outros": 120
        }
        
        # Build categories list
        categories_to_show = []
        for category_key in sorted(self.drivers_data.keys()):
            # Get drivers for this category
            drivers = self.drivers_data.get(category_key, [])
            if not drivers:
                continue
                
            # Get category label from mapping or fallback to capitalized key
            label = category_labels.get(category_key, category_key.capitalize())
            
            # Count number of drivers in this category
            count = len(drivers)
            
            # Skip empty categories
            if count > 0:
                categories_to_show.append((label, category_key, count))
        
        # Sort by priority
        sorted_categories = sorted(categories_to_show, 
                                 key=lambda x: (category_order.get(x[0], 1000), x[0]))
        
        # Add category rows
        for label, category_key, count in sorted_categories:
            icon_name = category_icon_mapping.get(label, "package-x-generic-symbolic")
            row = CategoryRow(category_key, f"{label} ({count})", icon_name)
            self.category_list.append(row)
        
        # Always select the Principal row by default, or fall back to first category
        if has_detected_drivers:
            self.category_list.select_row(principal_row)
        elif self.category_list.get_first_child():
            if principal_row == self.category_list.get_first_child():
                # If Principal is the only item but has no content, select the next item if it exists
                next_row = self.category_list.get_row_at_index(1)
                if (next_row):
                    self.category_list.select_row(next_row)
                else:
                    self.category_list.select_row(principal_row)
            else:
                self.category_list.select_row(self.category_list.get_first_child())
        else:
            self._show_error_message("Nenhuma categoria de drivers pôde ser exibida.")
    
    def _rebuild_content_area(self):
        """Completely rebuild the content area to avoid widget issues."""
        # Remove all existing content
        while child := self.content_box.get_first_child():
            self.content_box.remove(child)
        
        # Create a new detected drivers group from scratch
        self.detected_drivers_group = Adw.PreferencesGroup()
        self.detected_drivers_group.set_title("Drivers Detectados")
        self.detected_drivers_group.set_description("Drivers recomendados com base no hardware detectado")
        
        # Only show and populate if we have data
        if self.detected_drivers_data:
            # Add detected driver rows - with better error handling
            any_rows_added = self._populate_detected_drivers()
            self.detected_drivers_group.set_visible(any_rows_added)
        else:
            self.detected_drivers_group.set_visible(False)
        
        # Add the group to content box
        self.content_box.append(self.detected_drivers_group)
        
        # Clear existing categories
        while child := self.category_list.get_first_child():
            self.category_list.remove(child)
    
    def _populate_detected_drivers(self) -> bool:
        """Populate the detected drivers section.
        
        Returns:
            bool: True if any rows were added, False otherwise
        """
        # Sort detected drivers by name
        sorted_drivers = sorted(self.detected_drivers_data, key=lambda d: d.get('name', ''))
        
        # Track if we added any rows
        rows_added = False
        
        # Add each detected driver as a row
        for driver in sorted_drivers:
            try:
                driver_row = self._create_detected_driver_row(driver)
                if driver_row is not None:
                    self.detected_drivers_group.add(driver_row)
                    rows_added = True
            except Exception as e:
                logger.error(f"Error adding detected driver row: {e}", exc_info=True)
        
        return rows_added
    
    def _create_detected_driver_row(self, driver: Dict[str, Any]) -> Optional[Adw.ActionRow]:
        """Create an action row for a detected driver."""
        try:
            # Extract needed information
            driver_name_display = driver.get('name', 'Driver desconhecido') # Nome descritivo
            device_name = driver.get('device', 'Dispositivo desconhecido')
            driver_package = driver.get('package', '') # Pacote para instalação
            json_driver_field = driver.get('driver', '') # Campo 'driver' do JSON (módulo/identificador)
            is_installed = driver.get('installed', False)
            
            # Create the row - explicitly use Adw.ActionRow which is safe for AdwPreferencesGroup
            row = Adw.ActionRow()
            row.set_title(driver_name_display)
            
            # Description
            description_parts = []
            base_description = driver.get('description')
            if (base_description):
                description_parts.append(base_description)
            else:
                description_parts.append(f"Para {device_name}")

            if json_driver_field and json_driver_field != driver_package and json_driver_field != driver_name_display:
                description_parts.append(f"Módulo/ID: {json_driver_field}")
            
            row.set_subtitle(" • ".join(description_parts))
            
            # Controls box
            controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            
            # Status indicators
            status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            # Add a "Recommended" badge
            recommended_badge = Gtk.Label(label="Recomendado")
            recommended_badge.add_css_class("pill")
            recommended_badge.add_css_class("accent")
            status_box.append(recommended_badge)
            
            # Installation status badge
            if is_installed:
                status_badge = Gtk.Label(label="Instalado")
                status_badge.add_css_class("pill")
                status_badge.add_css_class("success")
            else:
                status_badge = Gtk.Label(label="Não Instalado")
                status_badge.add_css_class("pill")
                status_badge.add_css_class("dim-label")
            status_box.append(status_badge)
            
            controls_box.append(status_box)
            
            # Action button
            if is_installed:
                # Uninstall button
                action_btn = Gtk.Button()
                action_btn.set_icon_name("user-trash-symbolic")
                action_btn.set_tooltip_text(f"Remover o pacote {driver_package}")
                action_btn.set_valign(Gtk.Align.CENTER)
                action_btn.connect("clicked", self._on_uninstall_detected_clicked, driver)
            else:
                # Install button
                action_btn = Gtk.Button()
                action_btn.set_icon_name("software-install-symbolic")
                action_btn.set_tooltip_text(f"Instalar o pacote {driver_package}")
                action_btn.set_valign(Gtk.Align.CENTER)
                action_btn.connect("clicked", self._on_install_detected_clicked, driver)
            
            controls_box.append(action_btn)
            
            # Info button
            info_btn = Gtk.Button()
            info_btn.set_icon_name("help-about-symbolic")
            info_btn.set_tooltip_text("Mais informações sobre este driver")
            info_btn.set_valign(Gtk.Align.CENTER)
            info_btn.connect("clicked", self._on_detected_driver_info_clicked, driver)
            controls_box.append(info_btn)
            
            row.add_suffix(controls_box)
            
            # Add appropriate icon as prefix
            device_type = driver.get('device', '').lower()
            icon_name = "computer-symbolic"  # Default icon
            
            # Choose appropriate icon based on device type
            if "gpu" in device_type or "video" in device_type:
                icon_name = "video-display-symbolic"
            elif "wifi" in device_type or "wireless" in device_type:
                icon_name = "network-wireless-symbolic"
            elif "ethernet" in device_type or "network" in device_type:
                icon_name = "network-wired-symbolic"
            elif "bluetooth" in device_type:
                icon_name = "bluetooth-symbolic"
            elif "audio" in device_type or "sound" in device_type:
                icon_name = "audio-card-symbolic"
            elif "printer" in device_type:
                icon_name = "printer-symbolic"
            
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_tooltip_text(f"Tipo: {device_type}")
            row.add_prefix(icon)
            
            return row
        except Exception as e:
            logger.error(f"Error creating detected driver row: {e}")
            return None
    
    def _on_category_selected(self, listbox: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]):
        """Handle category selection (same pattern as hardware_info_page)."""
        if row is None or not isinstance(row, CategoryRow):
            return
        
        category_key = row.category_id
        self.content_view.set_tag(None)
        
        # Special handling for the Principal (detected drivers) category
        if category_key == "principal":
            self.content_view.set_title("Principal - Drivers Detectados")
            self._populate_principal_view()
            return
        
        # Get category display name
        category_labels = {
            "gpu": "Placa de vídeo",
            "wifi": "WiFi",
            "ethernet": "Rede cabeada",
            "bluetooth": "Bluetooth",
            "printer": "Impressora",
            "printer3d": "Impressora 3D",
            "scanner": "Scanner",
            "dvb": "TV Digital",
            "webcam": "Webcam",
            "touchscreen": "Touchscreen",
            "sound": "Som",
            "firmware": "Firmware",
            "unknown": "Outros"
        }
        
        category_display_name = category_labels.get(category_key, category_key.title())
        self.content_view.set_title(category_display_name)
        self.current_category = category_key
        self._populate_drivers_for_category(category_key)
    
    def _group_drivers_by_device_id(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group drivers by device ID to show all packages available for each device."""
        device_groups = {}
        
        # First pass: group by ID
        for driver in self.detected_drivers_data:
            # Use device ID as primary key, fallback to device name
            device_key = driver.get('id', '')
            if not device_key:
                device_key = driver.get('device', 'unknown')
                
            # Add to dictionary
            if device_key not in device_groups:
                device_groups[device_key] = []
            device_groups[device_key].append(driver)
        
        # Print debug info
        print(f"Found {len(device_groups)} unique devices with drivers:")
        for device_key, drivers in device_groups.items():
            package_names = [d.get('package', 'unknown') for d in drivers]
            print(f"Device: {device_key} - Available packages ({len(package_names)}): {', '.join(package_names)}")
        
        return device_groups

    def _populate_principal_view(self):
        """Populate the Principal view with detected drivers."""
        # Clear existing content
        while child := self.content_box.get_first_child():
            self.content_box.remove(child)
        
        # Create an enhanced header with an icon and better styling
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        header_box.set_margin_top(18)
        header_box.set_margin_bottom(16)
        header_box.set_margin_start(16)
        header_box.set_margin_end(16)
        
        # Add a prominent icon
        header_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        header_icon.set_pixel_size(32)
        header_icon.add_css_class("accent")
        header_box.append(header_icon)
        
        # Header text container for title and subtitle
        header_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header_text.set_hexpand(True)
        
        title_label = Gtk.Label()
        title_label.set_markup("<span size='large'><b>Driver(s) detectado(s)</b></span>")
        title_label.add_css_class("title-3")
        title_label.set_xalign(0)
        header_text.append(title_label)
        
        # Add a subtitle directly in the header
        subtitle_label = Gtk.Label()
        subtitle_label.set_markup("<span foreground='dimgray'>Otimize seu sistema com drivers específicos para seu hardware</span>")
        subtitle_label.set_xalign(0)
        subtitle_label.add_css_class("dim-label")
        header_text.append(subtitle_label)
        
        header_box.append(header_text)
        
        # No need for duplicate action buttons - we'll use only the buttons in the main header
        self.content_box.append(header_box)
        
        # Replace the previous Banner with a more attractive StatusPage for empty state
        if not self.detected_drivers_data:
            empty_status = Adw.StatusPage()
            empty_status.set_icon_name("computer-symbolic")
            empty_status.set_title("Nenhum driver adicional detectado")
            empty_status.set_description("Seu hardware parece estar funcionando com os drivers padrão do sistema")
            empty_status.set_vexpand(True)
            
            self.content_box.append(empty_status)
            return
        else:
            # Create a more visually appealing info card
            info_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            info_card.add_css_class("card")
            info_card.set_margin_bottom(24)
            info_card.set_margin_start(16)
            info_card.set_margin_end(16)
            info_card.set_margin_top(4)
            # Replace set_padding with proper margin settings for internal padding
            info_card.set_margin_start(16)
            info_card.set_margin_end(16)
            info_card.set_margin_top(16)
            info_card.set_margin_bottom(16)
            
            # Add an info icon
            info_icon = Gtk.Image.new_from_icon_name("info-symbolic")
            info_icon.add_css_class("accent")
            info_card.append(info_icon)
            
            # Add the descriptive text
            info_label = Gtk.Label()
            info_label.set_markup("Os drivers abaixo foram automaticamente detectados com base no seu hardware. A instalação destes drivers pode melhorar o desempenho e funcionalidades do seu sistema.")
            info_label.set_wrap(True)
            info_label.set_xalign(0)
            info_label.set_hexpand(True)
            info_card.append(info_label)
            
            self.content_box.append(info_card)
        
        # Log the total number of drivers to help with debugging
        total_drivers = len(self.detected_drivers_data)
        print(f"Total detected drivers to display in UI: {total_drivers}")
        
        # Group drivers by device ID to see all available packages for each device
        device_packages = self._group_drivers_by_device_id()
        
        # First create a summary of available drivers
        summary_group = Adw.PreferencesGroup()
        summary_group.set_title("Drivers por Dispositivo")
        summary_group.set_description(f"Total de {len(device_packages)} dispositivo(s) com {total_drivers} driver(s) disponível(is)")
        
        # Add each device group with its available packages
        for device_id, drivers in device_packages.items():
            # Get a representative driver to show device info
            sample_driver = drivers[0]
            device_name = sample_driver.get('device', 'Dispositivo')
            
            # Create a row for each device
            device_row = Adw.ExpanderRow()
            # Change title to use name instead of device
            device_row.set_title(f"{sample_driver.get('name', 'Driver')}")
            
            # Store device_id as a property for search filtering
            device_row.device_id = device_id
            
            # Add device name and ID as subtitle if available
            if device_id and device_id != "unknown":
                device_row.set_subtitle(f"{device_name} | ID: {device_id}")
            else:
                # If no ID is available, at least show the device name
                device_row.set_subtitle(f"{device_name}")
            
            # Add appropriate icon as prefix
            device_type = device_name.lower()
            icon_name = "computer-symbolic"  # Default icon
            
            # Choose appropriate icon based on device type
            if "placa de vídeo" in device_type or "gpu" in device_type or "graphics" in device_type:
                icon_name = "video-display-symbolic"
            elif "wifi" in device_type or "wireless" in device_type:
                icon_name = "network-wireless-symbolic"
            elif "rede" in device_type or "ethernet" in device_type or "network" in device_type:
                icon_name = "network-wired-symbolic"
            elif "bluetooth" in device_type:
                icon_name = "bluetooth-symbolic"
            elif "audio" in device_type or "som" in device_type or "sound" in device_type:
                icon_name = "audio-card-symbolic"
            elif "impressora" in device_type:
                icon_name = "printer-symbolic"
            
            icon = Gtk.Image.new_from_icon_name(icon_name)
            device_row.add_prefix(icon)
            
            # Count installed vs available packages
            installed_packages = []
            available_packages = []
            for driver in drivers:
                pkg_name = driver.get('package', 'unknown')
                if driver.get('installed', False):
                    installed_packages.append(pkg_name)
                else:
                    available_packages.append(pkg_name)
            
            # Add a badge showing package count
            package_badge = Gtk.Label()
            if installed_packages:
                package_badge.set_markup(f"<b>{len(installed_packages)}</b> instalado(s), <b>{len(available_packages)}</b> disponível(is)")
            else:
                package_badge.set_markup(f"<b>{len(drivers)}</b> pacote(s) disponível(is)")
            package_badge.set_margin_end(12)
            device_row.add_suffix(package_badge)
            
            # Add each package as a child row in the expander
            for driver in drivers:
                package_name = driver.get('package', 'unknown')
                is_installed = driver.get('installed', False)
                
                # Create a row for the package
                package_row = Adw.ActionRow()
                package_row.set_title(package_name)
                
                # Add description if available
                if driver.get('description'):
                    package_row.set_subtitle(driver.get('description'))
                
                # Add status badge
                if is_installed:
                    status_badge = Gtk.Label(label="Instalado")
                    status_badge.add_css_class("pill")
                    status_badge.add_css_class("success")
                    package_row.add_suffix(status_badge)
                
                # Add action button
                if is_installed:
                    action_btn = Gtk.Button()
                    action_btn.set_icon_name("user-trash-symbolic")
                    action_btn.set_tooltip_text(f"Remover o pacote {package_name}")
                    action_btn.set_valign(Gtk.Align.CENTER)
                    action_btn.connect("clicked", self._on_uninstall_detected_clicked, driver)
                    package_row.add_suffix(action_btn)
                else:
                    action_btn = Gtk.Button()
                    action_btn.set_icon_name("software-install-symbolic")
                    action_btn.set_tooltip_text(f"Instalar o pacote {package_name}")
                    action_btn.set_valign(Gtk.Align.CENTER)
                    action_btn.connect("clicked", self._on_install_detected_clicked, driver)
                    package_row.add_suffix(action_btn)
                
                # Add package row to expander
                device_row.add_row(package_row)
            
            # Add the expander row to the group
            summary_group.add(device_row)
        
        self.content_box.append(summary_group)

    def _on_search_toggled(self, button):
        """Handle search button toggle state."""
        is_active = button.get_active()
        self.search_bar.set_search_mode(is_active)
        
        if (is_active):
            # When activated, focus the search entry
            self.search_entry.grab_focus()
        else:
            # When deactivated, clear the search
            self.search_entry.set_text("")
            self._filter_drivers_by_search("")
    
    def _on_search_text_changed(self, entry):
        """Filter drivers based on search text."""
        search_text = entry.get_text().lower()
        self._filter_drivers_by_search(search_text)
    
    def _search_drivers_in_json(self, search_text: str) -> List[Dict[str, Any]]:
        """Search directly in the drivers_list.json file without loading all data in memory.
        
        This is more efficient for large driver databases as it reads directly from the file.
        
        Args:
            search_text: Text to search for in driver attributes
            
        Returns:
            List of matching driver dictionaries
        """
        search_text = search_text.lower().strip()
        if not search_text:
            return []
            
        try:
            # Check if JSON file exists
            if not os.path.exists(DRIVERS_JSON_OUTPUT):
                logger.error(f"JSON file not found at {DRIVERS_JSON_OUTPUT}")
                return []
                
            logger.info(f"Searching for '{search_text}' in drivers JSON file")
            
            # Read JSON file and search
            with open(DRIVERS_JSON_OUTPUT, 'r', encoding='utf-8') as f:
                all_drivers = json.load(f)
                
            if not isinstance(all_drivers, list):
                logger.error("Invalid JSON format: expected list")
                return []
                
            # Filter drivers based on search text
            matching_drivers = []
            for driver in all_drivers:
                if not isinstance(driver, dict):
                    continue
                    
                # Check various fields for matches
                name = driver.get('name', '').lower()
                description = driver.get('description', '').lower()
                package = driver.get('package', '').lower()
                driver_field = driver.get('driver', '').lower()
                category = driver.get('category', '').lower()
                category_label = driver.get('category_label', '').lower()
                
                if (search_text in name or
                    search_text in description or
                    search_text in package or
                    search_text in driver_field or
                    search_text in category or
                    search_text in category_label):
                    matching_drivers.append(driver)
                    
            logger.info(f"Found {len(matching_drivers)} drivers matching '{search_text}'")
            return matching_drivers
        except Exception as e:
            logger.error(f"Error searching drivers in JSON: {e}", exc_info=True)
            return []

    def _filter_drivers_by_search(self, search_text: str):
        """Apply search filter to displayed drivers. Shows results in a dedicated group."""
        search_text = search_text.lower().strip()

        if not self.content_box:
            logger.error("content_box is not initialized for search.")
            return

        if not search_text:
            # === RESTORE NORMAL VIEW ===
            if self.search_results_group and self.search_results_group.get_parent() == self.content_box:
                self.content_box.remove(self.search_results_group)
            self.search_results_group = None

            if self.split_view:
                self.split_view.set_sidebar_visible(True)

            # Repopulate content based on the currently selected category.
            # The _populate_ methods called by _on_category_selected will clear and rebuild self.content_box.
            selected_list_row = self.category_list.get_selected_row()
            if selected_list_row:
                self._on_category_selected(self.category_list, selected_list_row)
            elif self.category_list.get_first_child(): # If nothing selected, try selecting the first category
                first_category_row = self.category_list.get_row_at_index(0)
                if first_category_row:
                    self.category_list.select_row(first_category_row) # This triggers _on_category_selected
            else: # No categories loaded or list is empty
                # Clear content box manually if _on_category_selected didn't run
                while child := self.content_box.get_first_child():
                    self.content_box.remove(child)
                # Optionally show a default "select a category" or "no content" message
                status_page = Adw.StatusPage(title="Nenhum conteúdo para exibir", 
                                             description="Selecione uma categoria ou recarregue os drivers.",
                                             icon_name="face-disappointed-symbolic")
                self.content_box.append(status_page)
            return

        # === SEARCH MODE ===
        # Hide sidebar to give more space for search results
        if self.split_view:
            self.split_view.set_sidebar_visible(False)

        # Clear current content box to make space for search results only
        while child := self.content_box.get_first_child():
            self.content_box.remove(child)

        # Create search header with improved styling
        search_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        search_header.set_margin_top(18)
        search_header.set_margin_bottom(16)
        search_header.set_margin_start(16)
        search_header.set_margin_end(16)
        
        search_icon = Gtk.Image.new_from_icon_name("edit-find-symbolic")
        search_icon.set_pixel_size(32)
        search_icon.add_css_class("accent")
        search_header.append(search_icon)
        
        # Title with search term in header area
        header_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header_text.set_hexpand(True)
        
        title_label = Gtk.Label()
        title_label.set_markup(f"<span size='large'><b>Resultados da busca: '{search_text}'</b></span>")
        title_label.add_css_class("title-3")
        title_label.set_xalign(0)
        header_text.append(title_label)
        
        # Add a subtitle directly in the header
        subtitle_label = Gtk.Label()
        subtitle_label.set_markup("<span foreground='dimgray'>Buscando em todos os drivers disponíveis</span>")
        subtitle_label.set_xalign(0)
        subtitle_label.add_css_class("dim-label")
        header_text.append(subtitle_label)
        
        search_header.append(header_text)
        
        # Add a clear button to easily clear search
        clear_btn = Gtk.Button()
        clear_btn.set_icon_name("edit-clear-symbolic")
        clear_btn.set_tooltip_text("Limpar busca")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", lambda _: self._clear_search())
        search_header.append(clear_btn)
        
        self.content_box.append(search_header)

        # Add spinner for loading results
        spinner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spinner_box.set_halign(Gtk.Align.CENTER)
        spinner_box.set_margin_top(12)
        spinner_box.set_margin_bottom(12)
        
        spinner = Gtk.Spinner()
        spinner.start()
        spinner_box.append(spinner)
        
        loading_label = Gtk.Label(label=f"Buscando por '{search_text}'...")
        spinner_box.append(loading_label)
        
        self.content_box.append(spinner_box)
        
        # Use a separate thread to perform the search to keep UI responsive
        def search_thread():
            # Search directly in the JSON file
            matching_drivers = self._search_drivers_in_json(search_text)
            
            # Process detected drivers separately for better categorization
            detected_matches = []
            for driver in self.detected_drivers_data:
                name = driver.get('name', '').lower()
                description = driver.get('description', '').lower()
                package = driver.get('package', '').lower()
                driver_field = driver.get('driver', '').lower()
                device = driver.get('device', '').lower()
                
                if (search_text in name or
                    search_text in description or
                    search_text in package or
                    search_text in driver_field or
                    search_text in device):
                    detected_matches.append(driver)
            
            # Update UI on main thread
            GLib.idle_add(self._display_search_results, search_text, matching_drivers, detected_matches, spinner_box)
        
        # Start search thread
        threading.Thread(target=search_thread, daemon=True).start()

    def _display_search_results(self, search_text: str, file_matches: List[Dict], detected_matches: List[Dict], spinner_box: Gtk.Box):
        """Display search results after search is complete."""
        # Remove spinner
        if spinner_box.get_parent():
            self.content_box.remove(spinner_box)
        
        # Add info card explaining search scope
        info_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        info_card.add_css_class("card")
        info_card.set_margin_bottom(24)
        info_card.set_margin_start(16)
        info_card.set_margin_end(16)
        info_card.set_margin_top(4)
        # Internal padding
        info_card.set_margin_start(16)
        info_card.set_margin_end(16)
        info_card.set_margin_top(16)
        info_card.set_margin_bottom(16)
        
        # Add an info icon
        info_icon = Gtk.Image.new_from_icon_name("info-symbolic")
        info_icon.add_css_class("accent")
        info_card.append(info_icon)
        
        # Add the descriptive text
        info_label = Gtk.Label()
        info_label.set_markup(f"Buscando por <b>'{search_text}'</b> em nomes, descrições, pacotes e categorias de drivers.")
        info_label.set_wrap(True)
        info_label.set_xalign(0)
        info_label.set_hexpand(True)
        info_card.append(info_label)
        
        self.content_box.append(info_card)
        
        # Create groups for detected and regular drivers
        all_rows = []
        total_detected = len(detected_matches)
        total_regular = len(file_matches)
        
        # Create and add the search results group
        self.search_results_group = Adw.PreferencesGroup()
        self.search_results_group.set_title("Drivers encontrados")
        self.search_results_group.set_description(
            f"{total_detected + total_regular} driver(s) encontrado(s): {total_detected} detectados, {total_regular} por categoria"
        )
        self.content_box.append(self.search_results_group)
        
        # First add detected driver matches with a badge indicating they are recommended
        for driver in detected_matches:
            try:
                row = self._create_detected_driver_row(driver)
                if row:
                    all_rows.append(row)
            except Exception as e:
                logger.error(f"Error creating detected driver row: {e}")
        
        # Then add regular driver matches
        for driver in file_matches:
            try:
                row = self._create_driver_action_row(driver)
                if row:
                    all_rows.append(row)
            except Exception as e:
                logger.error(f"Error creating driver row: {e}")
        
        # Check if we have any results
        if all_rows:
            # Sort rows by name for better readability
            all_rows.sort(key=lambda row: row.get_title().lower())
            
            # Add rows to the group
            for row in all_rows:
                self.search_results_group.add(row)
            
            # Show toast notification for search results
            toast = Adw.Toast.new(f"Encontrados {len(all_rows)} drivers para '{search_text}'")
            toast.set_timeout(3)
            self.toast_overlay.add_toast(toast)
        else:
            # Remove the info card if no results
            if info_card.get_parent() == self.content_box:
                self.content_box.remove(info_card)
                
            # Create a nice empty state for no results
            empty_state = Adw.StatusPage()
            empty_state.set_icon_name("edit-find-symbolic")
            empty_state.set_title(f"Nenhum resultado para '{search_text}'")
            empty_state.set_description("Tente termos mais gerais ou verifique a ortografia")
            empty_state.set_vexpand(True)
            
            # Add a button to clear search
            action_button = Gtk.Button(label="Limpar busca")
            action_button.add_css_class("pill")
            action_button.add_css_class("suggested-action") 
            action_button.connect("clicked", lambda _: self._clear_search())
            empty_state.set_child(action_button)
            
            self.content_box.append(empty_state)

    def _clear_search(self):
        """Clear the search entry and restore normal view."""
        self.search_entry.set_text("")
        # Focus back on search entry for convenience
        self.search_entry.grab_focus()

    def _on_direct_search_changed(self, entry):
        """Handle direct search from the header search entry."""
        search_text = entry.get_text().lower().strip()
        
        # Only trigger search if we have at least 2 characters to avoid too many results
        if len(search_text) >= 2 or not search_text:
            self._filter_drivers_by_search(search_text)
        
        # Focus on search results if there's a search term
        if search_text and self.content_scroll:
            self.content_scroll.get_vadjustment().set_value(0)  # Scroll to top
        
        # Log the search term for debugging
        if search_text:
            print(f"Searching for: '{search_text}'")

    def _populate_drivers_for_category(self, category_key: str):
        """Populate drivers for the selected category."""
        # Completely rebuild the content area from scratch
        while child := self.content_box.get_first_child():
            self.content_box.remove(child)
        
        # Get drivers for specific category only
        drivers_to_show = self.drivers_data.get(category_key, [])
        
        if not drivers_to_show:
            # Show empty state
            self._show_empty_state()
            return
        
        # Create a header for the category
        category_labels = {
            "gpu": "Placa de vídeo",
            "wifi": "WiFi",
            "ethernet": "Rede cabeada",
            "bluetooth": "Bluetooth",
            "printer": "Impressora",
            "printer3d": "Impressora 3D",
            "scanner": "Scanner",
            "dvb": "TV Digital",
            "webcam": "Webcam",
            "touchscreen": "Touchscreen",
            "sound": "Som",
            "firmware": "Firmware",
            "unknown": "Outros"
        }
        
        category_display_name = category_labels.get(category_key, category_key.title())
        
        # Add a category header
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(16)
        header_box.set_margin_start(16)
        header_box.set_margin_end(16)
        
        # Choose appropriate icon for this category
        category_icon_mapping = {
            "gpu": "video-display-symbolic",
            "wifi": "network-wireless-symbolic",
            "ethernet": "network-wired-symbolic",
            "bluetooth": "bluetooth-symbolic",
            "printer": "printer-symbolic",
            "printer3d": "printer-symbolic",
            "scanner": "scanner-symbolic",
            "dvb": "tv-symbolic",
            "webcam": "camera-web-symbolic",
            "touchscreen": "input-touchpad-symbolic",
            "sound": "audio-card-symbolic",
            "firmware": "application-x-firmware-symbolic",
            "unknown": "package-x-generic-symbolic"
        }
        
        icon_name = category_icon_mapping.get(category_key, "package-x-generic-symbolic")
        header_icon = Gtk.Image.new_from_icon_name(icon_name)
        header_icon.set_pixel_size(24)
        header_box.append(header_icon)
        
        title_label = Gtk.Label()
        title_label.set_markup(f"<b>Drivers para {category_display_name}</b>")
        title_label.add_css_class("heading")
        title_label.set_hexpand(True)
        title_label.set_xalign(0)
        header_box.append(title_label)
        
        self.content_box.append(header_box)
        
        # Create a single group for all drivers (flat list)
        group = Adw.PreferencesGroup()
        group.set_description(f"{len(drivers_to_show)} driver(s) encontrado(s)")
        
        # Sort drivers by installation status (installed first) then by name
        drivers_to_show.sort(key=lambda d: (not d.get('installed', False), d.get('name', '')))
        
        # Add each driver as a direct action row (no expander)
        rows_added = False
        for driver in drivers_to_show:
            try:
                driver_row = self._create_driver_action_row(driver)
                if driver_row is not None:
                    group.add(driver_row)
                    rows_added = True
            except Exception as e:
                logger.error(f"Error adding driver row: {e}", exc_info=True)
        
        # Only add the group if we added rows
        if rows_added:
            self.content_box.append(group)
        else:
            self._show_empty_state()
    
    def _show_empty_state(self):
        """Show empty state when no drivers are found."""
        group = Adw.PreferencesGroup()
        group.set_title("Nenhum driver encontrado")
        
        status_page = Adw.StatusPage()
        status_page.set_title("Categoria vazia")
        status_page.set_description("Não há drivers disponíveis nesta categoria")
        status_page.set_icon_name("emblem-documents-symbolic")
        status_page.set_vexpand(True)
        
        group.add(status_page)
        self.content_box.append(group)
    
    def _get_source_icon(self, source: str) -> str:
        """Get icon name for driver source."""
        icons = {
            "device-ids": "computer-symbolic",
            "firmware": "application-x-firmware-symbolic",
            "printer": "printer-symbolic",
            "scanner": "scanner-symbolic",
            "unknown": "package-x-generic-symbolic"
        }
        return icons.get(source, "package-x-generic-symbolic")
    
    def _create_driver_action_row(self, driver: Dict[str, Any]) -> Adw.ActionRow:
        """Create an action row for a driver with all controls."""
        row = Adw.ActionRow()
        driver_name_display = driver.get('name', 'Driver desconhecido')
        row.set_title(driver_name_display)
        
        # Create detailed description
        description_parts = []
        base_desc = driver.get('description', 'Sem descrição')
        description_parts.append(base_desc)
        pkg_name = driver.get('package', '')
        json_driver_field = driver.get('driver', '') # Campo 'driver' do JSON
        if pkg_name and pkg_name != driver_name_display:
            description_parts.append(f"Pacote: {pkg_name}")
        if json_driver_field and json_driver_field != pkg_name and json_driver_field != driver_name_display:
            description_parts.append(f"Módulo/ID: {json_driver_field}")
        driver_type = driver.get('type', '')
        if driver_type and driver_type != 'unknown':
            description_parts.append(f"Tipo: {driver_type.upper()}")
        row.set_subtitle(" • ".join(filter(None, description_parts))) # filter(None, ...) para remover strings vazias
        
        # Create status and action container
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        # Status indicators
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        is_installed = driver.get('installed', False)
        is_loaded = driver.get('loaded', False)
        
        # Status badges
        if is_installed:
            if is_loaded:
                status_badge = Gtk.Label(label="Em uso")
                status_badge.add_css_class("pill")
                status_badge.add_css_class("success")
            else:
                status_badge = Gtk.Label(label="Instalado")
                status_badge.add_css_class("pill")
                status_badge.add_css_class("accent")
            status_box.append(status_badge)
            # Show loaded indicator
            if is_loaded:
                loaded_icon = Gtk.Image.new_from_icon_name("emblem-default-symbolic")
                loaded_icon.set_tooltip_text("Driver carregado no kernel")
                loaded_icon.add_css_class("success")
                status_box.append(loaded_icon)
        else:
            status_badge = Gtk.Label(label="Disponível")
            status_badge.add_css_class("pill")
            status_badge.add_css_class("dim-label")
            status_box.append(status_badge)
        
        controls_box.append(status_box)
        
        # Action button - Replace with icon buttons like in kernel_mesa_page.py
        if is_installed:
            # Uninstall button (trash icon)
            action_btn = Gtk.Button()
            action_btn.set_icon_name("user-trash-symbolic")
            action_btn.set_tooltip_text(f"Remover o pacote {driver.get('package', 'driver')}")
            action_btn.set_valign(Gtk.Align.CENTER)
            action_btn.connect("clicked", self._on_uninstall_clicked, driver)
        else:
            # Install button (download/software-install icon)
            action_btn = Gtk.Button()
            action_btn.set_icon_name("software-install-symbolic")
            action_btn.set_tooltip_text(f"Instalar o pacote {driver.get('package', 'driver')}")
            action_btn.set_valign(Gtk.Align.CENTER)
            action_btn.connect("clicked", self._on_install_clicked, driver)
        
        controls_box.append(action_btn)
        
        # Add package info button for more details - match style with action buttons
        info_btn = Gtk.Button()
        info_btn.set_icon_name("help-about-symbolic")
        info_btn.set_tooltip_text("Mais informações sobre este driver")
        info_btn.set_valign(Gtk.Align.CENTER)  # Match vertical alignment with action buttons
        info_btn.connect("clicked", self._on_driver_info_clicked, driver)
        controls_box.append(info_btn)
        
        row.add_suffix(controls_box)
        
        # Add driver type icon as prefix
        type_icon = self._get_driver_type_icon(driver)
        if type_icon:
            icon = Gtk.Image.new_from_icon_name(type_icon)
            icon.set_tooltip_text(f"Tipo: {driver.get('type', 'unknown')}")
            row.add_prefix(icon)
        
        return row
    
    def _get_driver_type_icon(self, driver: Dict[str, Any]) -> str:
        """Get icon for driver type."""
        driver_type = driver.get('type', 'unknown')
        source = driver.get('source', 'unknown')
        
        # Icons based on driver type and source
        if source == "device-ids":
            type_icons = {
                "pci": "preferences-system-symbolic",
                "usb": "usb-symbolic",
                "sdio": "network-wireless-symbolic",
                "unknown": "computer-symbolic"
            }
            return type_icons.get(driver_type, "computer-symbolic")
        elif source == "firmware":
            return "application-x-firmware-symbolic"
        elif source == "printer":
            return "printer-symbolic"
        elif source == "scanner":
            return "scanner-symbolic"
        
        return "package-x-generic-symbolic"
    
    def _on_driver_info_clicked(self, button: Gtk.Button, driver: Dict[str, Any]):
        """Show detailed driver information."""
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            f"Informações: {driver.get('name', 'Driver')}",
            self._format_driver_info(driver)
        )
        dialog.add_response("ok", "Fechar")
        dialog.present()
    
    def _format_driver_info(self, driver: Dict[str, Any]) -> str:
        """Format driver information for display."""
        info_parts = []
        
        # Basic info
        info_parts.append(f"Nome (Exibição): {driver.get('name', 'N/A')}")
        info_parts.append(f"Pacote (Instalação): {driver.get('package', 'N/A')}")
        json_driver_val = driver.get('driver')
        if json_driver_val:
            info_parts.append(f"Driver/Módulo (JSON 'driver'): {json_driver_val}")
        info_parts.append(f"Categoria: {driver.get('category_label', 'N/A')}")
        info_parts.append(f"Origem: {driver.get('source', 'N/A')}")
        info_parts.append(f"Tipo: {driver.get('type', 'N/A')}")
        
        # Status
        is_installed = driver.get('installed', False)
        is_loaded = driver.get('loaded', False)
        info_parts.append(f"Status: {'Instalado' if is_installed else 'Não instalado'}")
        if is_installed:
            info_parts.append(f"Carregado: {'Sim' if is_loaded else 'Não'}")
        
        # Description
        description = driver.get('description', '')
        if description:
            info_parts.append(f"\nDescrição:\n{description}")
        
        # Firmware files if available
        firmware_files = driver.get('firmware_files', [])
        if firmware_files:
            info_parts.append(f"\nArquivos de firmware:")
            for fw_file in firmware_files[:5]:  # Show max 5 files
                info_parts.append(f"• {fw_file}")
            if len(firmware_files) > 5:
                info_parts.append(f"... e mais {len(firmware_files) - 5} arquivos")
        
        return "\n".join(info_parts)
    
    def _on_refresh_clicked(self, button: Optional[Gtk.Button] = None) -> None:
        """Handle refresh button click (same as hardware_info_page)."""
        # Fixed check to avoid NoneType error
        if hasattr(self, 'error_box_container') and self.error_box_container is not None and self.error_box_container.get_parent():
            self.remove(self.error_box_container)
        
        # Clear content by simply removing all children
        while child := self.content_box.get_first_child():
            self.content_box.remove(child)
        
        # Clear category list
        while child := self.category_list.get_first_child():
            self.category_list.remove(child)
        
        # Reset data
        self.drivers_data = {}
        self.detected_drivers_data = []
        
        # Start loading data
        self._load_drivers()
    
    def _on_install_clicked(self, button: Gtk.Button, driver: Dict[str, Any]):
        """Handle install button click."""
        pkg_name = driver.get('package', driver.get('name', 'unknown'))
        
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            f"Instalar {pkg_name}?",
            f"Deseja instalar o driver '{pkg_name}'?\n\nEsta operação requer privilégios de administrador."
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("install", "Instalar")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_install_response, driver) # Pass full driver dict
        dialog.present()
    
    def _on_install_response(self, dialog: Adw.MessageDialog, response: str, driver_info: Dict[str, Any]):
        """Handle install dialog response."""
        dialog.destroy()
        
        if response != "install":
            return
        
        def install_thread():
            success = self._install_package(driver_info)
            GLib.idle_add(self._on_operation_complete, success, driver_info.get('package'), "instalação")
        
        threading.Thread(target=install_thread, daemon=True).start()
    
    def _on_uninstall_clicked(self, button: Gtk.Button, driver: Dict[str, Any]):
        """Handle uninstall button click."""
        pkg_name = driver.get('package', driver.get('name', 'unknown'))
        
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            f"Remover {pkg_name}?",
            f"Deseja remover o driver '{pkg_name}'?\n\nEsta operação requer privilégios de administrador."
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("remove", "Remover")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_uninstall_response, driver) # Pass full driver dict
        dialog.present()
    
    def _on_uninstall_response(self, dialog: Adw.MessageDialog, response: str, driver_info: Dict[str, Any]):
        """Handle uninstall dialog response."""
        dialog.destroy()
        
        if response != "remove":
            return
        
        def uninstall_thread():
            success = self._uninstall_package(driver_info)
            GLib.idle_add(self._on_operation_complete, success, driver_info.get('package'), "remoção")
        
        threading.Thread(target=uninstall_thread, daemon=True).start()
    
    def _install_package(self, driver_info: Dict[str, Any]) -> bool:
        """Install a package using pacman or mhwd."""
        pkg_name = driver_info.get('package')
        source = driver_info.get('source')
        
        if not pkg_name:
            logger.error("Package name is missing in driver_info.")
            return False
        
        try:
            if source == "mhwd":
                logger.info(f"Installing MHWD package: {pkg_name}")
                # For mhwd, the package name is often like 'video-nvidia'
                # MHWD typically installs for 'pci' devices.
                # Ensure the exact command structure mhwd expects.
                # It might need specific device IDs or types if not 'pci'.
                # Assuming 'pci' for now as it's common for video/network drivers.
                result = subprocess.run(
                    ["pkexec", "mhwd", "-i", "pci", pkg_name, "--noconfirm"],
                    capture_output=True,
                    text=True,
                    timeout=OPERATION_TIMEOUT
                )
            else: # Default to pacman
                logger.info(f"Installing pacman package: {pkg_name}")
                result = subprocess.run(
                    ["pkexec", "pacman", "-S", "--noconfirm", pkg_name],
                    capture_output=True,
                    text=True,
                    timeout=OPERATION_TIMEOUT
                )
            
            if result.returncode == 0:
                logger.info(f"Successfully installed {pkg_name}. Output: {result.stdout}")
                return True
            else:
                logger.error(f"Failed to install {pkg_name}. Return code: {result.returncode}. Error: {result.stderr}. Output: {result.stdout}")
                return False
        except Exception as e:
            logger.error(f"Install error for {pkg_name} (source: {source}): {e}")
            return False
    
    def _uninstall_package(self, driver_info: Dict[str, Any]) -> bool:
        """Uninstall a package using pacman or mhwd."""
        pkg_name = driver_info.get('package')
        source = driver_info.get('source')
        
        if not pkg_name:
            logger.error("Package name is missing in driver_info for uninstall.")
            return False
        
        try:
            if source == "mhwd":
                logger.info(f"Removing MHWD package: {pkg_name}")
                # Similar to install, assuming 'pci' for mhwd removal.
                result = subprocess.run(
                    ["pkexec", "mhwd", "-r", "pci", pkg_name, "--noconfirm"],
                    capture_output=True,
                    text=True,
                    timeout=OPERATION_TIMEOUT
                )
            else: # Default to pacman
                logger.info(f"Removing pacman package: {pkg_name}")
                result = subprocess.run(
                    ["pkexec", "pacman", "-Rns", "--noconfirm", pkg_name],
                    capture_output=True,
                    text=True,
                    timeout=OPERATION_TIMEOUT
                )
            
            if result.returncode == 0:
                logger.info(f"Successfully uninstalled {pkg_name}. Output: {result.stdout}")
                return True
            else:
                logger.error(f"Failed to uninstall {pkg_name}. Return code: {result.returncode}. Error: {result.stderr}. Output: {result.stdout}")
                return False
        except Exception as e:
            logger.error(f"Uninstall error for {pkg_name} (source: {source}): {e}")
            return False
    
    def _on_operation_complete(self, success: bool, pkg_name: str, operation: str):
        """Handle package operation completion."""
        if success:
            toast = Adw.Toast.new(f"{operation.title()} de {pkg_name} concluída")
            toast.set_timeout(3)
            self.toast_overlay.add_toast(toast)
            
            # Reload drivers data to refresh status
            self._load_drivers()
        else:
            dialog = Adw.MessageDialog.new(
                self.get_root(),
                f"Falha na {operation}",
                f"Não foi possível completar a {operation} do pacote {pkg_name}."
            )
            dialog.add_response("ok", "OK")
            dialog.present()
    
    def _on_detected_operation_complete(self, success: bool, pkg_name: str, operation: str):
        """Handle package operation completion for detected drivers."""
        if success:
            toast = Adw.Toast.new(f"{operation.title()} de {pkg_name} concluída")
            toast.set_timeout(3)
            self.toast_overlay.add_toast(toast)
            
            # Reload drivers data to refresh status
            self._load_drivers()
        else:
            dialog = Adw.MessageDialog.new(
                self.get_root(),
                f"Falha na {operation}",
                f"Não foi possível completar a {operation} do pacote {pkg_name}."
            )
            dialog.add_response("ok", "OK")
            dialog.present()
    
    def _show_error_message(self, message: str) -> None:
        """Show error message (same as hardware_info_page)."""
        if self.pulse_id > 0:
            GLib.source_remove(self.pulse_id)
            self.pulse_id = 0
        
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_visible(False)
        
        if self.split_view.get_visible():
            self.split_view.set_visible(False)
            while child := self.content_box.get_first_child():
                self.content_box.remove(child)
            while child := self.category_list.get_first_child():
                self.category_list.remove(child)
        
        # Fixed check to avoid NoneType error
        if hasattr(self, 'error_box_container') and self.error_box_container is not None and self.error_box_container.get_parent():
            self.remove(self.error_box_container)
        
        self.error_box_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True, hexpand=True)
        self.error_box_container.set_halign(Gtk.Align.CENTER)
        self.error_box_container.set_valign(Gtk.Align.CENTER)
        
        error_box_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        error_box_content.set_margin_top(24)
        error_box_content.set_margin_bottom(24)
        error_box_content.set_margin_start(24)
        error_box_content.set_margin_end(24)
        error_box_content.set_halign(Gtk.Align.CENTER)
        
        error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        error_icon.set_pixel_size(64)
        error_box_content.append(error_icon)
        
        error_label = Gtk.Label(label=message)
        error_label.set_wrap(True)
        error_label.set_max_width_chars(60)
        error_label.set_justify(Gtk.Justification.CENTER)
        error_label.add_css_class("title-3")
        error_box_content.append(error_label)
        
        retry_button = Gtk.Button(label="Tentar Novamente")
        retry_button.connect("clicked", self._on_refresh_clicked)
        retry_button.set_halign(Gtk.Align.CENTER)
        retry_button.add_css_class("pill")
        retry_button.add_css_class("suggested-action")
        error_box_content.append(retry_button)
        
        self.error_box_container.append(error_box_content)
        self.append(self.error_box_container)
    
    def _show_error_dialog(self, title: str, message: str):
        """Show error dialog."""
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            title,
            message
        )
        dialog.add_response("ok", "OK")
        dialog.present()
    
    def _on_install_detected_clicked(self, button: Gtk.Button, driver: Dict[str, Any]):
        """Handle install button click for detected drivers."""
        pkg_name = driver.get('package', driver.get('driver', 'unknown'))
        
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            f"Instalar {pkg_name}?",
            f"Deseja instalar o driver '{pkg_name}' para {driver.get('device', 'seu hardware')}?\n\nEsta operação requer privilégios de administrador."
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("install", "Instalar")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_install_detected_response, driver) # Pass full driver dict
        dialog.present()
    
    def _on_install_detected_response(self, dialog: Adw.MessageDialog, response: str, driver_info: Dict[str, Any]):
        """Handle install dialog response for detected drivers."""
        dialog.destroy()
        
        if response != "install":
            return
        
        def install_thread():
            success = self._install_package(driver_info) # Pass full driver_info
            GLib.idle_add(self._on_detected_operation_complete, success, driver_info.get('package'), "instalação")
        
        threading.Thread(target=install_thread, daemon=True).start()
    
    def _on_uninstall_detected_clicked(self, button: Gtk.Button, driver: Dict[str, Any]):
        """Handle uninstall button click for detected drivers."""
        pkg_name = driver.get('package', driver.get('driver', 'unknown'))
        
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            f"Remover {pkg_name}?",
            f"Deseja remover o driver '{pkg_name}' para {driver.get('device', 'seu hardware')}?\n\nEsta operação requer privilégios de administrador."
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("remove", "Remover")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_uninstall_detected_response, driver) # Pass full driver dict
        dialog.present()
    
    def _on_uninstall_detected_response(self, dialog: Adw.MessageDialog, response: str, driver_info: Dict[str, Any]):
        """Handle uninstall dialog response for detected drivers."""
        dialog.destroy()
        
        if response != "remove":
            return
        
        def uninstall_thread():
            success = self._uninstall_package(driver_info) # Pass full driver_info
            GLib.idle_add(self._on_detected_operation_complete, success, driver_info.get('package'), "remoção")
        
        threading.Thread(target=uninstall_thread, daemon=True).start()
    
    def _on_detected_driver_info_clicked(self, button: Gtk.Button, driver: Dict[str, Any]):
        """Show detailed detected driver information."""
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            f"Informações: {driver.get('name', 'Driver')}",
            self._format_detected_driver_info(driver)
        )
        dialog.add_response("ok", "Fechar")
        dialog.present()
    
    def _format_detected_driver_info(self, driver: Dict[str, Any]) -> str:
        """Format detected driver information for display."""
        info_parts = []
        
        # Basic info
        info_parts.append(f"Nome (Exibição): {driver.get('name', 'N/A')}")
        info_parts.append(f"Dispositivo: {driver.get('device', 'N/A')}")
        package_name = driver.get('package') # Obtém o valor do campo 'package' do JSON
        json_driver_field = driver.get('driver') # Obtém o valor do campo 'driver' do JSON
        
        # Exibe "Pacote (Instalação)" estritamente do campo 'package' do JSON
        if package_name:
            info_parts.append(f"Pacote (Instalação): {package_name}")
        else:
            info_parts.append("Pacote (Instalação): N/A") # Não há fallback para json_driver_field nesta linha

        # Exibe "Driver/Módulo (JSON 'driver')" do campo 'driver' do JSON
        if json_driver_field:
            info_parts.append(f"Driver/Módulo (JSON 'driver'): {json_driver_field}")
        
        # Status
        is_installed = driver.get('installed', False)
        info_parts.append(f"Status: {'Instalado' if is_installed else 'Não instalado'}")
        
        # Description
        description = driver.get('description', '')
        if description:
            info_parts.append(f"\nDescrição:\n{description}")
                
        # Additional information
        for key, value in driver.items():
            if key not in ['name', 'device', 'package', 'driver', 'installed', 'description']:
                if isinstance(value, (dict, list)):
                    info_parts.append(f"\n{key.capitalize()}:\n{json.dumps(value, indent=2, ensure_ascii=False)}")
                else:
                    info_parts.append(f"\n{key.capitalize()}: {value}")
        
        return "\n".join(info_parts)
    
    def _load_drivers(self):
        """Load drivers data in a separate thread."""
        print("Starting to load drivers...")
        logger.info("Starting to load drivers data")
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        
        # Fixed check to avoid NoneType error
        if hasattr(self, 'error_box_container') and self.error_box_container is not None and self.error_box_container.get_parent():
            self.remove(self.error_box_container)
        
        if self.pulse_id == 0:
            self.pulse_id = GLib.timeout_add(150, self._pulse_progress_bar)
        
        self.split_view.set_visible(False)
        
        # Log environment information for debugging
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"DRIVERS_SCRIPT path: {DRIVERS_SCRIPT}")
        logger.info(f"DRIVERS_SCRIPT exists: {os.path.exists(DRIVERS_SCRIPT)}")
        logger.info(f"HARDWARE_DETECT_SCRIPT path: {HARDWARE_DETECT_SCRIPT}")
        logger.info(f"HARDWARE_DETECT_SCRIPT exists: {os.path.exists(HARDWARE_DETECT_SCRIPT)}")
        
        def load_thread():
            try:
                print("Inside load thread, about to fetch drivers...")
                
                # Carrega os drivers padrão primeiro
                drivers_data = self._fetch_drivers_data()
                print(f"Drivers data loaded: {'Success' if drivers_data else 'Failed'}")
                
                # Tenta carregar drivers detectados com tratamento de erros adicional
                detected_drivers = []
                try:
                    detected_drivers = self._fetch_detected_hardware_drivers()
                    print(f"Detected drivers loaded: {'Success' if detected_drivers else 'Failed'}")
                except Exception as e:
                    # Captura erros específicos da detecção de hardware para não quebrar o carregamento principal
                    logger.error(f"Error in hardware detection (non-fatal): {e}", exc_info=True)
                    print(f"Error in hardware detection: {str(e)}")
                
                # Continua o carregamento mesmo que a detecção de hardware falhe
                GLib.idle_add(self._on_drivers_loaded, drivers_data, detected_drivers)
            except Exception as e:
                print(f"Error in load thread: {str(e)}")
                logger.error(f"Error loading drivers: {e}", exc_info=True)
                GLib.idle_add(self._on_drivers_error, str(e))
        
        thread = threading.Thread(target=load_thread, daemon=True)
        thread.start()
        print("Driver loading thread started")
    
    def _on_search_toggled(self, button):
        """Handle search button toggle state."""
        is_active = button.get_active()
        self.search_bar.set_search_mode(is_active)
        
        if is_active:
            # When activated, focus the search entry
            self.search_entry.grab_focus()
        else:
            # When deactivated, clear the search
            self.search_entry.set_text("")
            self._filter_drivers_by_search("")
            
    def _on_search_text_changed(self, entry):
        """Filter drivers based on search text."""
        search_text = entry.get_text().lower()
        print(f"Search text changed: '{search_text}'")
        self._filter_drivers_by_search(search_text)
    
    def _filter_drivers_by_search(self, search_text):
        """Apply search filter to displayed drivers."""
        # Find all the device groups in the content box
        device_groups = []
        
        # Use proper GTK 4 iteration instead of get_children()
        child = self.content_box.get_first_child()
        while child:
            if isinstance(child, Adw.PreferencesGroup) and child != self.detected_drivers_group:
                device_groups.append(child)
            child = child.get_next_sibling()
        
        if not device_groups:
            return
            
        # Skip filtering if search is empty
        if not search_text:
            # Show all device groups and their rows
            for group in device_groups:
                group.set_visible(True)
                # Iterate through all children of the group using proper GTK 4 methods
                row = group.get_first_child()
                while row:
                    row.set_visible(True)
                    # For ExpanderRow, also make child rows visible
                    if isinstance(row, Adw.ExpanderRow):
                        for child_row in row.get_rows():  # ExpanderRow does have get_rows()
                            child_row.set_visible(True)
                    row = row.get_next_sibling()
            return
        
        # Apply filter based on search text
        for group in device_groups:
            visible_rows = 0
            
            # Iterate through all children of the group using proper GTK 4 methods
            row = group.get_first_child()
            while row:
                row_visible = False
                
                # For ExpanderRow, check the title and all child rows
                if isinstance(row, Adw.ExpanderRow):
                    # Check if the row title matches
                    if search_text in row.get_title().lower():
                        row_visible = True
                    elif row.get_subtitle() and search_text in row.get_subtitle().lower():
                        row_visible = True
                    else:
                        # Check each child row
                        child_visible = False
                        # ExpanderRow has get_rows()
                        for child_row in row.get_rows():
                            if (search_text in child_row.get_title().lower() or 
                                (child_row.get_subtitle() and search_text in child_row.get_subtitle().lower())):
                                child_visible = True
                                break
                        
                        row_visible = child_visible
                
                # For regular ActionRow, just check the title and subtitle
                elif isinstance(row, Adw.ActionRow):
                    if search_text in row.get_title().lower():
                        row_visible = True
                    elif row.get_subtitle() and search_text in row.get_subtitle().lower():
                        row_visible = True
                
                row.set_visible(row_visible)
                if row_visible:
                    visible_rows += 1
                
                row = row.get_next_sibling()
            
            # Only show the group if it has visible rows
            group.set_visible(visible_rows > 0)
    
    def _on_direct_search_changed(self, entry):
        """Handle direct search from the header search entry."""
        search_text = entry.get_text().lower()
        print(f"Search text changed: '{search_text}'")
        self._filter_drivers_by_search(search_text)
    
    def _on_drivers_error(self, error_message: str):
        """Handle errors in driver loading thread."""
        logger.error(f"Driver loading error: {error_message}")
        self._show_error_message(f"Erro ao carregar drivers: {error_message}")
        
        # Stop progress animation
        if self.pulse_id > 0:
            GLib.source_remove(self.pulse_id)
            self.pulse_id = 0
        
        self.progress_bar.set_visible(False)