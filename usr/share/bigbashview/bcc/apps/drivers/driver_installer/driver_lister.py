"""
Driver Lister Module

This module provides functions to list all available drivers on the system.
"""
import os
import subprocess
import re
import json
import logging
from typing import Dict, List, Any, Optional

# Set up logger
logger = logging.getLogger(__name__)

# Category labels mapping - used by other modules for consistent UI display
CATEGORY_LABELS = {
    "Star": "Principais",
    "Cpu": "Processador",
    "Gpu": "Placa de vídeo",
    "Video": "Placa de vídeo",
    "Machine": "Placa mãe",
    "Memory": "Memória",
    "Network": "Rede",
    "Usb": "USB",
    "Pci": "PCI",
    "Printer": "Impressora",
    "Scanner": "Scanner",
    "Bluetooth": "Bluetooth",
    "Sound": "Áudio",
    "Webcam": "Webcam"
}

def list_all_drivers() -> List[Dict[str, Any]]:
    """
    List all available drivers on the system.
    
    Returns:
        A list of dictionaries containing driver information.
    """
    drivers = []
    
    # Get drivers from device-ids
    drivers.extend(_get_device_id_drivers())
    
    # Get drivers from firmware
    drivers.extend(_get_firmware_drivers())
    
    # Get drivers from mhwd
    drivers.extend(_get_mhwd_drivers())
    
    # Get standalone drivers (printer, scanner, etc.)
    drivers.extend(_get_standalone_drivers())
    
    return drivers

def _get_device_id_drivers() -> List[Dict[str, Any]]:
    """
    Get drivers from device-ids directory.
    
    Returns:
        A list of dictionaries containing driver information.
    """
    drivers = []
    device_ids_dir = "/usr/share/bigbashview/bcc/apps/drivers/device-ids"
    
    if not os.path.exists(device_ids_dir):
        logger.warning(f"Device IDs directory not found: {device_ids_dir}")
        return drivers
    
    try:
        # Get list of PCI devices
        pci_devices = _get_pci_devices()
        
        # List modules in device-ids directory
        modules = [d for d in os.listdir(device_ids_dir) 
                  if os.path.isdir(os.path.join(device_ids_dir, d))]
        
        for module in modules:
            module_dir = os.path.join(device_ids_dir, module)
            
            # Get module information
            try:
                with open(os.path.join(module_dir, "category"), 'r') as f:
                    category = f.read().strip()
                
                with open(os.path.join(module_dir, "pkg"), 'r') as f:
                    package = f.read().strip()
                
                with open(os.path.join(module_dir, "description"), 'r') as f:
                    description = f.read().strip()
                
                # Read PCI IDs
                pci_ids_file = os.path.join(module_dir, "pci.ids")
                if os.path.exists(pci_ids_file):
                    with open(pci_ids_file, 'r') as f:
                        pci_ids = [line.strip() for line in f.readlines()]
                else:
                    pci_ids = []
                
                # Check if module is compatible with the system
                is_compatible = False
                for pci_id in pci_ids:
                    id_parts = pci_id.split(':')
                    if len(id_parts) >= 2:
                        vendor_id, device_id = id_parts[0], id_parts[1]
                        pattern = f"{vendor_id}:{device_id}"
                        
                        for device in pci_devices:
                            if pattern.lower() in device.lower():
                                is_compatible = True
                                break
                    
                    if is_compatible:
                        break
                
                # Check if package is installed
                is_installed = _is_package_installed(package)
                
                # Check if module is loaded
                is_loaded = _is_module_loaded(module)
                
                # Map category to label
                category_label = _get_category_label(category)
                
                # Add driver to the list
                drivers.append({
                    "name": module,
                    "package": package,
                    "description": description,
                    "category": category,
                    "category_label": category_label,
                    "compatible": is_compatible,
                    "installed": is_installed,
                    "loaded": is_loaded,
                    "source": "device-ids"
                })
                
            except Exception as e:
                logger.error(f"Error processing module {module}: {e}")
    
    except Exception as e:
        logger.error(f"Error getting device ID drivers: {e}")
    
    return drivers

def _get_firmware_drivers() -> List[Dict[str, Any]]:
    """
    Get drivers from firmware directory.
    
    Returns:
        A list of dictionaries containing firmware driver information.
    """
    drivers = []
    firmware_dir = "/usr/share/bigbashview/bcc/apps/drivers/firmware"
    
    if not os.path.exists(firmware_dir):
        logger.warning(f"Firmware directory not found: {firmware_dir}")
        return drivers
    
    try:
        # Get list of missing firmware from dmesg
        missing_firmware = _get_missing_firmware()
        
        # List firmware packages
        firmware_pkgs = [d for d in os.listdir(firmware_dir) 
                        if os.path.isdir(os.path.join(firmware_dir, d))]
        
        for pkg in firmware_pkgs:
            pkg_dir = os.path.join(firmware_dir, pkg)
            
            # Get package information
            try:
                with open(os.path.join(pkg_dir, "category"), 'r') as f:
                    category = f.read().strip()
                
                with open(os.path.join(pkg_dir, "description"), 'r') as f:
                    description = f.read().strip()
                
                # Read firmware file list
                firmware_file = os.path.join(pkg_dir, pkg)
                if os.path.exists(firmware_file):
                    with open(firmware_file, 'r') as f:
                        firmware_files = [line.strip() for line in f.readlines()]
                else:
                    firmware_files = []
                
                # Check if firmware is needed
                is_compatible = False
                for firmware in missing_firmware:
                    for fw_file in firmware_files:
                        if firmware.lower() in fw_file.lower():
                            is_compatible = True
                            break
                    
                    if is_compatible:
                        break
                
                # If firmware is needed, add it to the "Star" category as well
                if is_compatible and "Star" not in category:
                    category += " Star"
                
                # Check if package is installed
                is_installed = _is_package_installed(pkg)
                
                # Map category to label
                category_label = _get_category_label(category)
                
                # Create firmware files list for description
                firmware_list = "\n".join([f"- {os.path.basename(f)}" for f in firmware_files[:5]])
                if len(firmware_files) > 5:
                    firmware_list += f"\n- ... ({len(firmware_files) - 5} more)"
                
                # Add firmware info to description if compatible
                if is_compatible:
                    description += "\n\nEste firmware é necessário para seu hardware."
                
                if firmware_list:
                    description += f"\n\nArquivos de firmware incluídos:\n{firmware_list}"
                
                # Add driver to the list
                drivers.append({
                    "name": pkg,
                    "package": pkg,
                    "description": description,
                    "category": category,
                    "category_label": category_label,
                    "compatible": is_compatible,
                    "installed": is_installed,
                    "loaded": False,  # Firmware is not "loaded" like modules
                    "source": "firmware"
                })
                
            except Exception as e:
                logger.error(f"Error processing firmware package {pkg}: {e}")
    
    except Exception as e:
        logger.error(f"Error getting firmware drivers: {e}")
    
    return drivers

def _get_mhwd_drivers() -> List[Dict[str, Any]]:
    """
    Get drivers from MHWD (Manjaro Hardware Detection).
    
    Returns:
        A list of dictionaries containing MHWD driver information.
    """
    drivers = []
    
    try:
        # Check if mhwd is available
        if not _command_exists("mhwd"):
            logger.warning("MHWD command not found")
            return drivers
        
        # Get list of MHWD drivers
        result = subprocess.run(
            ["mhwd", "-l"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Error running mhwd -l: {result.stderr}")
            return drivers
        
        # Parse MHWD output
        output = result.stdout
        
        # Clean ANSI color codes
        cleaned_output = re.sub(r'\x1B\[[0-9;]*[mG]', '', output)
        
        # Extract available drivers
        free_section = re.search(r"Free drivers:\s*\n(.*?)(?=Non-free drivers:|\Z)", 
                               cleaned_output, re.DOTALL)
        nonfree_section = re.search(r"Non-free drivers:\s*\n(.*?)(?=\Z)", 
                                   cleaned_output, re.DOTALL)
        
        # Process free drivers
        if free_section:
            free_drivers = re.findall(r"(\w+/\w+)", free_section.group(1))
            for driver in free_drivers:
                # Get more info about the driver
                info = _get_mhwd_driver_info(driver)
                
                name = info.get("name", driver)
                description = info.get("description", "Driver livre detectado pelo MHWD")
                package = info.get("package", name)
                
                # Check if package is installed
                is_installed = info.get("installed", False)
                
                # Add driver to the list
                drivers.append({
                    "name": name,
                    "package": package,
                    "description": description,
                    "category": "Video",
                    "category_label": "Placa de vídeo",
                    "compatible": True,  # MHWD only lists compatible drivers
                    "installed": is_installed,
                    "loaded": is_installed,  # Assume loaded if installed
                    "source": "mhwd-free"
                })
        
        # Process non-free drivers
        if nonfree_section:
            nonfree_drivers = re.findall(r"(\w+/\w+)", nonfree_section.group(1))
            for driver in nonfree_drivers:
                # Get more info about the driver
                info = _get_mhwd_driver_info(driver)
                
                name = info.get("name", driver)
                description = info.get("description", "Driver proprietário detectado pelo MHWD")
                package = info.get("package", name)
                
                # Check if package is installed
                is_installed = info.get("installed", False)
                
                # Add driver to the list
                drivers.append({
                    "name": name,
                    "package": package,
                    "description": description,
                    "category": "Video",
                    "category_label": "Placa de vídeo",
                    "compatible": True,  # MHWD only lists compatible drivers
                    "installed": is_installed,
                    "loaded": is_installed,  # Assume loaded if installed
                    "source": "mhwd-nonfree"
                })
    
    except Exception as e:
        logger.error(f"Error getting MHWD drivers: {e}")
    
    return drivers

def _get_standalone_drivers() -> List[Dict[str, Any]]:
    """
    Get standalone drivers (printer, scanner, etc.).
    
    Returns:
        A list of dictionaries containing standalone driver information.
    """
    drivers = []
    
    # Define standalone drivers with their categories
    standalone_drivers = [
        {
            "name": "cups",
            "package": "cups",
            "description": "Sistema de impressão CUPS (Common Unix Printing System)",
            "category": "Printer",
            "category_label": "Impressora"
        },
        {
            "name": "hplip",
            "package": "hplip",
            "description": "HP Linux Imaging and Printing - Drivers para impressoras HP",
            "category": "Printer",
            "category_label": "Impressora"
        },
        {
            "name": "gutenprint",
            "package": "gutenprint",
            "description": "Drivers de alta qualidade para várias impressoras",
            "category": "Printer",
            "category_label": "Impressora"
        },
        {
            "name": "foomatic-db",
            "package": "foomatic-db",
            "description": "Banco de dados Foomatic - Suporte para várias impressoras",
            "category": "Printer",
            "category_label": "Impressora"
        },
        {
            "name": "sane",
            "package": "sane",
            "description": "Scanner Access Now Easy - Interface de scanner para Linux",
            "category": "Scanner",
            "category_label": "Scanner"
        },
        {
            "name": "xsane",
            "package": "xsane",
            "description": "Interface gráfica para o SANE",
            "category": "Scanner",
            "category_label": "Scanner"
        },
        {
            "name": "bluez",
            "package": "bluez",
            "description": "Pilha de protocolos Bluetooth para Linux",
            "category": "Bluetooth",
            "category_label": "Bluetooth"
        },
        {
            "name": "blueman",
            "package": "blueman",
            "description": "Gerenciador de Bluetooth para ambiente gráfico",
            "category": "Bluetooth",
            "category_label": "Bluetooth"
        }
    ]
    
    try:
        for driver_info in standalone_drivers:
            # Check if package is installed
            is_installed = _is_package_installed(driver_info["package"])
            
            # Add the driver with installation status
            drivers.append({
                "name": driver_info["name"],
                "package": driver_info["package"],
                "description": driver_info["description"],
                "category": driver_info["category"],
                "category_label": driver_info["category_label"],
                "compatible": True,  # Assume all standalone drivers are compatible
                "installed": is_installed,
                "loaded": is_installed,  # Assume loaded if installed
                "source": "standalone"
            })
    
    except Exception as e:
        logger.error(f"Error getting standalone drivers: {e}")
    
    return drivers

def _get_pci_devices() -> List[str]:
    """
    Get list of PCI devices in the system.
    
    Returns:
        A list of PCI device IDs and descriptions.
    """
    try:
        result = subprocess.run(
            ["lspci", "-nn"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Error running lspci: {result.stderr}")
            return []
        
        return result.stdout.strip().split('\n')
    
    except Exception as e:
        logger.error(f"Error getting PCI devices: {e}")
        return []

def _is_package_installed(package: str) -> bool:
    """
    Check if a package is installed.
    
    Args:
        package: Name of the package to check.
        
    Returns:
        True if the package is installed, False otherwise.
    """
    try:
        result = subprocess.run(
            ["pacman", "-Q", package],
            capture_output=True,
            text=True,
            check=False
        )
        
        return result.returncode == 0
    
    except Exception as e:
        logger.error(f"Error checking if package {package} is installed: {e}")
        return False

def _is_module_loaded(module: str) -> bool:
    """
    Check if a kernel module is loaded.
    
    Args:
        module: Name of the module to check.
        
    Returns:
        True if the module is loaded, False otherwise.
    """
    try:
        with open("/proc/modules", "r") as f:
            loaded_modules = f.read()
        
        return module in loaded_modules
    
    except Exception as e:
        logger.error(f"Error checking if module {module} is loaded: {e}")
        return False

def _get_category_label(category: str) -> str:
    """
    Map category ID to human-readable label.
    
    Args:
        category: Category ID.
        
    Returns:
        Human-readable category label.
    """
    category_map = {
        "Star": "Principais",
        "Cpu": "Processador",
        "Gpu": "Placa de vídeo",
        "Video": "Placa de vídeo",
        "Machine": "Placa mãe",
        "Memory": "Memória",
        "Network": "Rede",
        "Usb": "USB",
        "Pci": "PCI",
        "Printer": "Impressora",
        "Scanner": "Scanner",
        "Bluetooth": "Bluetooth",
        "Sound": "Áudio",
        "Webcam": "Webcam"
    }
    
    # If category has multiple values (e.g., "Network Star"), 
    # use the first one for mapping and preserve the others
    parts = category.split()
    if not parts:
        return "Outros"
    
    main_category = parts[0]
    label = category_map.get(main_category, main_category)
    
    # Add "Principais" if "Star" is in the category
    if "Star" in parts[1:]:
        return f"{label} (Recomendado)"
    
    return label

def _get_missing_firmware() -> List[str]:
    """
    Get list of missing firmware from dmesg.
    
    Returns:
        A list of missing firmware filenames.
    """
    try:
        result = subprocess.run(
            ["dmesg"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Error running dmesg: {result.stderr}")
            return []
        
        # Find firmware errors in dmesg output
        firmware_errors = []
        for line in result.stdout.split('\n'):
            if "firmware" in line.lower() and "failed" in line.lower():
                # Try to extract the firmware filename
                match = re.search(r"firmware: failed to load (\S+)", line)
                if match:
                    firmware_errors.append(match.group(1))
        
        return firmware_errors
    
    except Exception as e:
        logger.error(f"Error getting missing firmware: {e}")
        return []

def _get_mhwd_driver_info(driver_name: str) -> Dict[str, Any]:
    """
    Get detailed information about an MHWD driver.
    
    Args:
        driver_name: Name of the MHWD driver.
        
    Returns:
        Dictionary with driver details.
    """
    info = {
        "name": driver_name,
        "description": f"Driver MHWD: {driver_name}",
        "package": driver_name.replace("/", "-"),
        "installed": False
    }
    
    try:
        # Check if driver is installed using mhwd -li
        result = subprocess.run(
            ["mhwd", "-li"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Error running mhwd -li: {result.stderr}")
            return info
        
        # Clean ANSI color codes
        cleaned_output = re.sub(r'\x1B\[[0-9;]*[mG]', '', result.stdout)
        
        # Check if driver is listed as installed
        if driver_name in cleaned_output and "installed" in cleaned_output:
            info["installed"] = True
            
            # Try to extract a better description
            driver_section = re.search(
                r"(?:>.*" + re.escape(driver_name) + r".*\n)(.*?)(?:\n\n|\Z)", 
                cleaned_output, 
                re.MULTILINE
            )
            if driver_section:
                description = driver_section.group(1).strip()
                if description:
                    info["description"] = description
    
    except Exception as e:
        logger.error(f"Error getting MHWD driver info for {driver_name}: {e}")
    
    return info

def _command_exists(command: str) -> bool:
    """
    Check if a command exists in the system.
    
    Args:
        command: Name of the command to check.
        
    Returns:
        True if the command exists, False otherwise.
    """
    try:
        result = subprocess.run(
            ["which", command],
            capture_output=True,
            text=True,
            check=False
        )
        
        return result.returncode == 0
    
    except Exception as e:
        logger.error(f"Error checking if command {command} exists: {e}")
        return False

# Export private functions as public API for use in other modules
is_package_installed = _is_package_installed
is_module_loaded = _is_module_loaded
get_category_label = _get_category_label
get_pci_devices = _get_pci_devices
get_missing_firmware = _get_missing_firmware
get_mhwd_driver_info = _get_mhwd_driver_info
command_exists = _command_exists
