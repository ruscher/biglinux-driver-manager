#!/usr/bin/env python3

"""
Diagnostic tool for kernel management.
Run this script to check kernel data and display results.
"""

import asyncio
import logging
import sys
import json
from kernel_manager import KernelManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("kernel_diagnostic")

async def run_diagnostic():
    """Run diagnostics on kernel data and detection."""
    print("\n=== BigLinux Kernel Manager Diagnostic Tool ===\n")
    
    # Create kernel manager
    manager = KernelManager()
    
    # Test 1: Current kernel detection
    print("Test 1: Current kernel detection")
    try:
        current_kernel = await manager.detect_current_kernel()
        print(f"  Current kernel: {current_kernel}")
        print("  ✓ Current kernel detection successful")
    except Exception as e:
        print(f"  ✗ Current kernel detection failed: {str(e)}")
    
    # Test 2: Get installed kernels
    print("\nTest 2: Installed kernels detection")
    try:
        installed_kernels = await manager._get_installed_kernels()
        if installed_kernels:
            print(f"  Found {len(installed_kernels)} installed kernel(s):")
            for k in installed_kernels:
                running = "→ RUNNING" if k.get("is_running") else ""
                print(f"  - {k['name']} {k['version']} {running}")
            print("  ✓ Installed kernels detection successful")
        else:
            print("  ⚠ No installed kernels found (unusual, please investigate)")
    except Exception as e:
        print(f"  ✗ Installed kernels detection failed: {str(e)}")
    
    # Test 3: Official available kernels
    print("\nTest 3: Official repository kernels")
    try:
        official_kernels = await manager.get_available_kernels()
        if official_kernels:
            print(f"  Found {len(official_kernels)} official kernels:")
            for k in official_kernels[:5]:  # Show first 5
                print(f"  - {k['name']} {k['version']}")
            if len(official_kernels) > 5:
                print(f"  ...(and {len(official_kernels) - 5} more)")
            print("  ✓ Official kernels detection successful")
        else:
            print("  ⚠ No official kernels found (possible connectivity or repository issue)")
    except Exception as e:
        print(f"  ✗ Official kernels detection failed: {str(e)}")
    
    # Test 4: AUR kernels
    print("\nTest 4: AUR kernels")
    try:
        aur_kernels = await manager.get_aur_kernels()
        if aur_kernels:
            print(f"  Found {len(aur_kernels)} AUR kernels:")
            for k in aur_kernels[:5]:  # Show first 5
                print(f"  - {k['name']} {k['version']}")
            if len(aur_kernels) > 5:
                print(f"  ...(and {len(aur_kernels) - 5} more)")
            print("  ✓ AUR kernels detection successful")
        else:
            print("  ⚠ No AUR kernels found (AUR helper may be missing or connectivity issue)")
    except Exception as e:
        print(f"  ✗ AUR kernels detection failed: {str(e)}")
    
    # Test 5: Full kernel data JSON
    print("\nTest 5: Full kernel data JSON")
    try:
        kernels_json = await manager.get_kernels_json(use_cache=False)
        official_count = len(kernels_json.get("official_available", []))
        aur_count = len(kernels_json.get("aur_available", []))
        installed_count = len(kernels_json.get("installed_packages", []))
        
        print(f"  JSON data contains:")
        print(f"  - {official_count} official kernels")
        print(f"  - {aur_count} AUR kernels")
        print(f"  - {installed_count} installed kernels")
        
        if official_count > 0 or aur_count > 0 or installed_count > 0:
            print("  ✓ Kernel JSON data generated successfully")
            # Save to file for inspection
            with open("/tmp/kernel_data.json", "w") as f:
                json.dump(kernels_json, f, indent=2)
            print("  ✓ Saved complete kernel data to /tmp/kernel_data.json")
        else:
            print("  ⚠ Kernel JSON data appears empty or incomplete")
    except Exception as e:
        print(f"  ✗ Kernel JSON generation failed: {str(e)}")
    
    # Summary
    print("\n=== Diagnostic Summary ===")
    print("If you're experiencing issues with kernel detection or display:")
    print("1. Check that you have internet connectivity")
    print("2. Ensure your package databases are up-to-date (run 'sudo pacman -Sy')")
    print("3. For AUR kernels, make sure you have yay or paru installed")
    print("4. Examine detailed data in /tmp/kernel_data.json")
    print("5. Check UI logs for render/display issues")

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
