"""
System Information Provider

This module provides a class for retrieving system hardware information.
"""
import subprocess
import json
import logging

logger = logging.getLogger(__name__)

class SystemInfo:
    """
    System Information provider class.
    
    This class provides methods to retrieve various system hardware information.
    """
    
    def __init__(self):
        """Initialize the SystemInfo class."""
        pass
        
    def get_hardware_info(self):
        """
        Get comprehensive hardware information using inxi.
        
        Returns:
            dict: A dictionary containing hardware information
        """
        try:
            # Run the inxi command to get hardware info in JSON format
            cmd = ["inxi", "-Fxxxza", "--output", "json", "--output-file", "print"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean up the output using sed to remove color codes and other artifacts
            clean_cmd = ["sed", "-e", 's/".*#/"/g']
            clean_process = subprocess.run(clean_cmd, input=result.stdout, 
                                          capture_output=True, text=True)
            
            # Parse the JSON output
            hardware_data = json.loads(clean_process.stdout)
            return hardware_data
            
        except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Error fetching hardware info: {e}")
            return {}
    
    def get_cpu_info(self):
        """
        Get CPU information.
        
        Returns:
            dict: CPU information
        """
        hardware_info = self.get_hardware_info()
        return hardware_info.get('cpu', {})
    
    def get_gpu_info(self):
        """
        Get GPU information.
        
        Returns:
            dict: GPU information
        """
        hardware_info = self.get_hardware_info()
        return hardware_info.get('graphics', {})
    
    def get_memory_info(self):
        """
        Get memory information.
        
        Returns:
            dict: Memory information
        """
        hardware_info = self.get_hardware_info()
        return hardware_info.get('memory', {})
    
    def get_disk_info(self):
        """
        Get storage information.
        
        Returns:
            dict: Storage information
        """
        hardware_info = self.get_hardware_info()
        return hardware_info.get('drives', {})
