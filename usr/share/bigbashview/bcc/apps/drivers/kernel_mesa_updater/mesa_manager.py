"""
Mesa Manager

This module provides functionality for managing Mesa driver installations and updates.
"""
import subprocess
import asyncio
import os
import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple, Callable

# Set up logger
logger = logging.getLogger(__name__)

class MesaManager:
    """Manager for Mesa operations including detection, installation, and rollback."""
    
    def __init__(self) -> None:
        """Initialize the Mesa Manager."""
        self.current_mesa = None
        self.config_dir = os.path.expanduser("~/.config/kernel-mesa-updater")
        
        # Create config directory if it doesn't exist
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Path to mesa history file
        self.mesa_history_file = os.path.join(self.config_dir, "mesa_history.json")
        
        # Initialize mesa history if it doesn't exist
        if not os.path.exists(self.mesa_history_file):
            with open(self.mesa_history_file, "w") as f:
                json.dump([], f)
    
    async def detect_current_mesa(self) -> str:
        """Detect the currently installed Mesa version."""
        try:
            # Using glxinfo to get Mesa version
            process = await asyncio.create_subprocess_exec(
                "glxinfo", "-B",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Error detecting Mesa: {stderr.decode().strip()}")
                return "Unknown"
                
            output = stdout.decode()
            
            # Extract Mesa version using regex
            match = re.search(r"OpenGL version string:.*Mesa ([0-9\.]+)", output)
            if match:
                version = match.group(1)
                self.current_mesa = version
                logger.info(f"Detected Mesa version: {version}")
                return version
            else:
                logger.error("Could not find Mesa version in glxinfo output")
                return "Unknown"
                
        except Exception as e:
            logger.error(f"Exception detecting Mesa version: {str(e)}")
            return "Error"
    
    async def _check_disk_space(self, required_gb: float = 0.5) -> bool: # 500MB
        """Check if there's enough disk space for Mesa installation."""
        try:
            process_gb = await asyncio.create_subprocess_exec(
                "df", "-BG", "--output=avail", "/", # Só verificamos / para Mesa
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_gb, stderr_gb = await process_gb.communicate()

            if process_gb.returncode != 0:
                logger.error(f"Error checking disk space (Mesa): {stderr_gb.decode().strip()}")
                # Fallback se df -BG falhar (raro, mas possível)
                process_kb = await asyncio.create_subprocess_exec(
                    "df", "--output=avail", "/",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_kb, stderr_kb_fallback = await process_kb.communicate()
                if process_kb.returncode != 0:
                    logger.error(f"Fallback disk space check failed: {stderr_kb_fallback.decode().strip()}")
                    return False # Falha segura

                lines = stdout_kb.decode().strip().split('\n')[1:] # Pular header
                if not lines: return False
                try:
                    avail_kb = int(lines[0].strip())
                    avail_gb = avail_kb / (1024 * 1024)
                    if avail_gb < required_gb:
                        logger.warning(f"Insufficient disk space for Mesa: {avail_gb:.2f}GB available, {required_gb}GB required.")
                        return False
                    return True
                except ValueError:
                    logger.error(f"Could not parse fallback disk space value: {lines[0].strip()}")
                    return False
            else: # Método preferido com -BG
                lines = stdout_gb.decode().strip().split('\n')[1:]
                if not lines: return False
                try:
                    avail_val_str = lines[0].strip()
                    if avail_val_str.upper().endswith('G'):
                        avail_gb = float(avail_val_str[:-1])
                        if avail_gb < required_gb:
                            logger.warning(f"Insufficient disk space for Mesa: {avail_gb:.2f}GB available, {required_gb}GB required.")
                            return False
                        return True
                    else: # Formato inesperado, assumir M, K ou B
                        # Tentar converter para GB se for M ou K, ou comparar com um limite menor
                        # Para simplificar, se não for G, e o requerido for >0, pode ser um problema
                        logger.warning(f"Disk space for / not in GB from df -BG: {avail_val_str}. Check manually.")
                        # Se required_gb é pequeno (ex: 0.5GB), e temos "500M", pode ser ok.
                        # Esta lógica pode ser expandida. Por ora, se não for 'G', e exigimos GB, melhor avisar.
                        if 'M' in avail_val_str.upper():
                            if float(avail_val_str.upper().replace('M','')) / 1024 < required_gb:
                                return False
                            return True
                        return False # Se não for G nem M, e precisamos de GB, provavelmente não é suficiente
                except ValueError:
                    logger.error(f"Could not parse disk space value for Mesa from df -BG: {lines[0].strip()}")
                    return False
            return True # Default para True se tudo correr bem
            
        except Exception as e:
            logger.exception(f"Exception checking disk space for Mesa: {str(e)}")
            return False