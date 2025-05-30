# kernel_manager.py

import subprocess
import asyncio
import os
import json
import logging
import re
import gi
from typing import Dict, List, Any, Optional, Tuple, Callable

# Add GLib import
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import GLib

# Set up logger
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class KernelManager:
    """Manager for kernel operations including detection, installation, and rollback."""
    
    def __init__(self) -> None:
        """Initialize the Kernel Manager."""
        self.current_kernel_version_str: Optional[str] = None # Armazena a string completa da versão 'uname -r'
        self.available_kernels: List[Dict[str, str]] = [] # Mantido para compatibilidade interna se necessário
        # self.previous_kernels: List[Dict[str, str]] = [] # Não parece estar sendo usado, pode remover
        self.config_dir = os.path.expanduser("~/.config/kernel-mesa-updater")
        os.makedirs(self.config_dir, exist_ok=True)
        self.kernel_history_file = os.path.join(self.config_dir, "kernel_history.json")
        if not os.path.exists(self.kernel_history_file):
            with open(self.kernel_history_file, "w") as f:
                json.dump([], f)
        # Para o cache
        self._kernels_json_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0.0
        self.CACHE_EXPIRY_SECONDS = 300 # Cache por 5 minutos

    async def detect_current_kernel(self) -> str:
        """Detect the currently running kernel version string (from uname -r)."""
        if self.current_kernel_version_str: # Cache simples para uname -r
            return self.current_kernel_version_str
        try:
            process = await asyncio.create_subprocess_exec(
                "uname", "-r",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                logger.error(f"Error detecting kernel: {stderr.decode().strip()}")
                return "Unknown"
            kernel_version = stdout.decode().strip()
            self.current_kernel_version_str = kernel_version
            logger.info(f"Detected current kernel (uname -r): {kernel_version}")
            return kernel_version
        except Exception as e:
            logger.error(f"Exception detecting kernel: {str(e)}")
            return "Error"

    async def get_available_kernels(self) -> List[Dict[str, str]]:
        """Get a list of all available kernels from the official repositories."""
        # Esta função busca kernels *disponíveis para instalação*, não os instalados.
        kernels = []
        try:
            process = await asyncio.create_subprocess_exec(
                "pacman", "-Ss", "^linux[0-9._-]*$", "^linux-(?!headers|firmware|api|tools)[a-z-]+[0-9._-]*$", # Regex mais preciso
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                if "no packages found" in stderr.decode().strip().lower() or "nenhum pacote encontrado" in stderr.decode().strip().lower() :
                    logger.info("No official kernels found matching specific patterns.")
                    return []
                logger.error(f"Error searching for kernels: {stderr.decode().strip()}")
                return []
            
            output = stdout.decode().strip()
            pattern = re.compile(
                r"^(core|extra|community)/([a-zA-Z0-9._-]+(?:-lts|-zen|-hardened|-[a-zA-Z0-9]+)*) +([0-9][^\s]+)(?:\s+\(([^)]+)\))?"
            )
            
            current_pkg_info = None
            for line in output.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                match = pattern.match(line)
                if match:
                    repo, pkg_name, version, groups = match.groups()
                    # Filtro adicional para garantir que são pacotes de kernel primários
                    if any(x in pkg_name for x in ["firmware", "headers", "api", "tools", "docs"]):
                        continue
                    if not (pkg_name == "linux" or pkg_name.startswith("linux-") or \
                            any(pkg_name.endswith(s) for s in ["-lts", "-zen", "-hardened"])): # Mais alguns filtros
                        continue

                    current_pkg_info = {
                        "name": pkg_name,
                        "version": version,
                        "description": "", 
                        "full_name": f"{repo}/{pkg_name}",
                        "repo": repo,
                        "source": "official"
                    }
                    kernels.append(current_pkg_info)
                elif current_pkg_info and (line.startswith("    ") or line.startswith("\t")) and kernels and kernels[-1] is current_pkg_info:
                    kernels[-1]["description"] = line.strip()
                    # Adicionar filtro para descrição também, se for muito genérica pode não ser kernel
                    if "linux kernel" not in kernels[-1]["description"].lower() and \
                       "kernel and modules" not in kernels[-1]["description"].lower():
                        logger.debug(f"Removing {kernels[-1]['name']} due to non-kernel description: {kernels[-1]['description']}")
                        kernels.pop() # Remove o último adicionado se a descrição não bate
                        current_pkg_info = None # Garante que não adicionemos mais descrições a ele
                    else:
                        current_pkg_info = None
            
            self.available_kernels = kernels # Atualiza o atributo da classe se necessário
            logger.info(f"Found {len(kernels)} official kernels available for install: {[k['name'] for k in kernels]}")
            return kernels
            
        except Exception as e:
            logger.exception(f"Exception getting available official kernels: {str(e)}")
            return []
    
    async def get_aur_kernels(self) -> List[Dict[str, str]]:
        """Get available kernels from AUR."""
        aur_kernels = []
        try:
            aur_helpers = ["yay", "paru"]
            aur_helper = None
            for helper in aur_helpers:
                try:
                    process_check = await asyncio.create_subprocess_exec(
                        "which", helper,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    await process_check.wait()
                    if process_check.returncode == 0:
                        aur_helper = helper
                        break
                except FileNotFoundError:
                    logger.debug(f"AUR helper {helper} not found (FileNotFound).")
                except Exception as e_which:
                    logger.debug(f"Error checking for AUR helper {helper}: {e_which}")

            if not aur_helper:
                logger.warning("No AUR helper (yay/paru) found or they are not executable.")
                return []
            
            logger.info(f"Using AUR helper: {aur_helper} to search for AUR kernels")
            # Voltar para uma busca mais abrangente para encontrar todos os kernels
            # Combinar uma busca ampla com filtros inteligentes
            
            # Primeira abordagem: busca ampla para encontrar a maioria dos kernels
            process = await asyncio.create_subprocess_exec(
                aur_helper, "-Ss", "linux",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0 and not stdout:
                logger.warning(f"AUR kernel search failed: {stderr.decode().strip()}")
                return []
            
            output = stdout.decode().strip()
            if not output:
                logger.warning("Empty output from AUR search")
                return []
            
            aur_pattern = re.compile(
                r"^aur/([a-zA-Z0-9._-]+) +([0-9][^\s]+)"
            )
            
            aur_kernels = []
            current_pkg_info = None
            
            for line in output.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                match = aur_pattern.match(line)
                if match:
                    pkg_name, version = match.groups()
                    
                    # Filtros básicos mas não tão restritivos:
                    # 1. Deve começar com "linux"
                    # 2. Não deve ser apenas headers, firmware, etc.
                    if not pkg_name.startswith("linux"):
                        continue
                        
                    # Excluir pacotes que claramente não são kernels
                    if any(x in pkg_name for x in [
                        "-firmware", "-api-headers", "/firmware", 
                        "-docs", "-manual", "-source", "-headers-"
                    ]):
                        continue
                    
                    # Se é um pacote de headers, deve também existir o kernel correspondente
                    if "-headers" in pkg_name:
                        # Verificamos depois se existe o kernel correspondente
                        base_kernel_name = pkg_name.replace("-headers", "")
                        if not any(k["name"] == base_kernel_name for k in aur_kernels):
                            # Se não encontrou o kernel base, pular
                            continue
                    
                    current_pkg_info = {
                        "name": pkg_name,
                        "version": version,
                        "description": "",
                        "full_name": f"aur/{pkg_name}",
                        "repo": "aur",
                        "source": "aur"
                    }
                    # Verificar se já existe
                    if not any(k["name"] == pkg_name for k in aur_kernels):
                        aur_kernels.append(current_pkg_info)
                    else:
                        current_pkg_info = None
                elif current_pkg_info and (line.startswith("    ") or line.startswith("\t")):
                    # Capturar a descrição, mas não filtrar com base nela para ser mais inclusivo
                    current_pkg_info["description"] = line.strip()
                    current_pkg_info = None
            
            # Filtro final para garantir que são kernels reais
            # Este é um compromisso entre inclusividade e precisão
            real_aur_kernels = []
            for k in aur_kernels:
                # Se for um nome de kernel conhecido sem headers/etc., adicionar
                if k["name"] == "linux" or any(k["name"].endswith(suffix) for suffix in [
                    "-lts", "-zen", "-hardened", "-rt", "-xanmod", "-cachyos", "-git", "-custom",
                    "-ck", "-rc", "-clear", "-bore", "-amd", "-intel", "-bfq"
                ]):
                    real_aur_kernels.append(k)
                # Se tiver "kernel" na descrição, adicionar
                elif "kernel" in k.get("description", "").lower():
                    real_aur_kernels.append(k)
                # Se não for um pacote conhecido como não-kernel, adicionar
                elif not any(non_kernel in k["name"] for non_kernel in [
                    "-dkms", "-driver", "-module", "-utils", "-tools", "-config", "-header"
                ]):
                    real_aur_kernels.append(k)
            
            logger.info(f"Found {len(real_aur_kernels)} AUR kernels available for install: {[k['name'] for k in real_aur_kernels]}")
            return real_aur_kernels
                
        except Exception as e:
            logger.exception(f"Exception getting AUR kernels: {str(e)}")
            return []

    async def _get_installed_kernels(self) -> List[Dict[str, str]]:
        """Get list of installed kernel packages and their versions."""
        installed = []
        try:
            # Usar pacman -Q para listar pacotes instalados.
            # Filtrar por aqueles que são kernels. Uma regex pode ser útil aqui.
            # Ex: "linux", "linux-lts", "linux-zen", "linux-customname"
            # Não queremos "linux-headers", "linux-firmware".
            # O comando `pacman -Q | grep -E "^linux[^-]|linux-[a-z]"` é um bom começo.
            # Ou podemos listar tudo e filtrar em Python.

            process_q = await asyncio.create_subprocess_exec(
                "pacman", "-Q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_q, stderr_q = await process_q.communicate()

            if process_q.returncode != 0:
                logger.error(f"Error listing all installed packages: {stderr_q.decode().strip()}")
                return []

            current_uname_r = await self.detect_current_kernel() # String como '6.1.60-1-lts'

            for line in stdout_q.decode().strip().split('\n'):
                if not line:
                    continue
                
                try:
                    name, version = line.split(' ', 1)
                except ValueError:
                    logger.warning(f"Could not parse installed package line: {line}")
                    continue

                # Critérios para ser um kernel instalado:
                # 1. Começa com "linux"
                # 2. Não é "linux-firmware", "linux-api-headers", "linux-headers" (a menos que seja o pacote de headers do kernel principal)
                #    Pacotes de headers são importantes, mas não são o kernel em si.
                #    Para a UI, geralmente mostramos o kernel principal.
                # A sua regex original `pacman -Q linux linux-` é para *procurar* por pacotes que começam com esses nomes.
                # Se queremos apenas os pacotes *kernel* instalados:
                if name == "linux" or \
                   (name.startswith("linux-") and \
                    not name.startswith("linux-firmware") and \
                    not name.startswith("linux-api-headers") and \
                    not name.startswith("linux-headers") and # Exclui headers de forma genérica
                    not name.endswith("-docs") and \
                    not name.endswith("-tools")):
                    
                    # Checar se este kernel instalado é o que está rodando
                    # Isso é um pouco complexo porque 'uname -r' nem sempre mapeia diretamente para o nome do pacote.
                    # Ex: 'uname -r' -> '6.1.1-arch1-1', pacote 'linux'
                    # Ex: 'uname -r' -> '5.15.80-1-lts', pacote 'linux-lts'
                    # Uma heurística: se a versão do pacote está contida em uname -r.
                    is_current_running = False
                    if current_uname_r != "Unknown" and current_uname_r != "Error":
                        # uname -r pode ter sufixos como -arch1-1, -MANJARO, etc.
                        # O nome do pacote (ex: linux, linux-lts) pode não estar em uname -r
                        # A versão do pacote (ex: 6.5.9-1) DEVE estar no uname -r (ex: 6.5.9-arch1-1)
                        # Vamos comparar a parte numérica da versão
                        pkg_ver_base = version.split('-')[0] # "6.5.9" de "6.5.9-1"
                        uname_ver_base = current_uname_r.split('-')[0] # "6.5.9" de "6.5.9-arch1-1"
                        
                        if pkg_ver_base == uname_ver_base:
                            # Agora precisamos ver se o "tipo" de kernel bate (standard, lts, zen etc.)
                            # Se o nome do pacote for 'linux', ele corresponde a uname sem sufixo de tipo.
                            # Se for 'linux-lts', uname deve ter 'lts' ou ser o kernel default se for o único.
                            # Esta parte é a mais complicada.
                            # Simplificação: se a base da versão bate, e o nome do pacote é apenas "linux",
                            # ou se o nome do pacote (ex: "lts") está em uname -r.
                            if name == "linux" and not any(ktype in current_uname_r for ktype in ["lts", "zen", "hardened"]):
                                is_current_running = True
                            elif name.startswith("linux-"):
                                suffix = name.split("linux-", 1)[1] # "lts", "zen"
                                if suffix in current_uname_r:
                                    is_current_running = True
                            # Caso especial: se só temos um kernel instalado e a versão base bate.
                            # Esta lógica pode precisar de refinamento.

                    installed.append({
                        "name": name,
                        "version": version,
                        "is_running": is_current_running # Renomeado de is_current para clareza
                    })
            
            logger.info(f"Found {len(installed)} installed kernel packages: {installed}")
            return installed
            
        except Exception as e:
            logger.exception(f"Exception getting installed kernels: {str(e)}")
            return []

    async def _generate_kernels_json(self) -> Dict[str, Any]:
        """
        Helper to generate the kernel JSON data.
        """
        try:
            logger.info("Generating new kernels JSON data...")
            # Get kernels from both sources
            official_kernels_avail = await self.get_available_kernels() # Disponíveis para instalar
            aur_kernels_avail = await self.get_aur_kernels()          # Disponíveis para instalar
            
            installed_kernel_pkgs = await self._get_installed_kernels() # Já instalados
            current_running_kernel_uname = await self.detect_current_kernel() # uname -r
            
            # Marcar kernels disponíveis que já estão instalados
            installed_names_versions = {f"{k['name']}-{k['version']}": k for k in installed_kernel_pkgs}

            for k_list in [official_kernels_avail, aur_kernels_avail]:
                for k_avail in k_list:
                    k_avail["is_installed"] = f"{k_avail['name']}-{k_avail['version']}" in installed_names_versions
                    # Checar se é o que está rodando (comparando nome e versão base)
                    k_avail["is_running"] = False
                    if k_avail["is_installed"]:
                        installed_version_info = installed_names_versions[f"{k_avail['name']}-{k_avail['version']}"]
                        if installed_version_info.get("is_running", False):
                             k_avail["is_running"] = True
            
            # Log data counts for debugging
            logger.info(f"Kernel data summary - Official: {len(official_kernels_avail)}, AUR: {len(aur_kernels_avail)}, Installed: {len(installed_kernel_pkgs)}")
            
            # If we have no kernels at all, try one more time with less filtering
            if len(official_kernels_avail) == 0 and len(aur_kernels_avail) == 0:
                logger.warning("No kernels found with standard filters, trying broader search")
                # Try a different approach with minimal filtering
                try:
                    # Simpler query for kernels
                    process = await asyncio.create_subprocess_exec(
                        "pacman", "-Ss", "linux",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode == 0 and stdout:
                        output = stdout.decode().strip()
                        pattern = re.compile(r"^(core|extra|community)/([a-zA-Z0-9._-]+) +([0-9][^\s]+)")
                        
                        for line in output.split('\n'):
                            line = line.strip()
                            if not line:
                                continue
                            
                            match = pattern.match(line)
                            if match and "linux" in line:
                                repo, pkg_name, version = match.groups()
                                # Very basic filter - must start with linux and not be headers/firmware
                                if pkg_name.startswith("linux") and not any(x in pkg_name for x in ["headers", "firmware"]):
                                    official_kernels_avail.append({
                                        "name": pkg_name,
                                        "version": version,
                                        "description": "Linux kernel package",
                                        "full_name": f"{repo}/{pkg_name}",
                                        "repo": repo,
                                        "source": "official"
                                    })
                        
                        logger.info(f"Fallback search found {len(official_kernels_avail)} kernel packages")
                except Exception as e:
                    logger.exception("Error in fallback kernel search")
            
            result = {
                "official_available": official_kernels_avail,
                "aur_available": aur_kernels_avail,
                "installed_packages": installed_kernel_pkgs,
                "current_running_uname": current_running_kernel_uname,
                "timestamp": int(asyncio.get_event_loop().time())
            }
            
            # Add diagnostic info
            if len(official_kernels_avail) > 0:
                logger.info(f"First official kernel: {official_kernels_avail[0]['name']} {official_kernels_avail[0]['version']}")
            if len(aur_kernels_avail) > 0:
                logger.info(f"First AUR kernel: {aur_kernels_avail[0]['name']} {aur_kernels_avail[0]['version']}")
            if len(installed_kernel_pkgs) > 0:
                logger.info(f"First installed kernel: {installed_kernel_pkgs[0]['name']} {installed_kernel_pkgs[0]['version']}")
            
            return result
            
        except Exception as e:
            logger.exception(f"Error generating kernels JSON structure: {str(e)}")
            return {
                "error": str(e),
                "timestamp": int(asyncio.get_event_loop().time()),
                "official_available": [],
                "aur_available": [],
                "installed_packages": []
            }

    async def get_kernels_json(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get all available and installed kernels in a structured JSON format.
        Returns a dictionary with official, AUR, installed kernels, and current running.
        Uses a time-based cache.
        """
        current_time = asyncio.get_event_loop().time()
        if use_cache and \
           self._kernels_json_cache is not None and \
           (current_time - self._cache_timestamp) < self.CACHE_EXPIRY_SECONDS:
            logger.info("Returning cached kernels JSON data.")
            # Atualizar o estado is_running no cache rapidamente sem refazer tudo
            current_uname_r = await self.detect_current_kernel()
            self._kernels_json_cache["current_running_uname"] = current_uname_r
            # Re-checar is_running para os instalados e disponíveis no cache (leve)
            for k_list_key in ["official_available", "aur_available"]:
                if k_list_key in self._kernels_json_cache:
                    for k_avail in self._kernels_json_cache[k_list_key]:
                        k_avail["is_running"] = False # Reset
                        if k_avail.get("is_installed"):
                            pkg_ver_base_avail = k_avail['version'].split('-')[0]
                            uname_ver_base = current_uname_r.split('-')[0]
                            if pkg_ver_base_avail == uname_ver_base:
                                if k_avail['name'] == "linux" and not any(ktype in current_uname_r for ktype in ["lts", "zen", "hardened"]):
                                    k_avail["is_running"] = True
                                elif k_avail['name'].startswith("linux-"):
                                    suffix = k_avail['name'].split("linux-", 1)[1]
                                    if suffix in current_uname_r:
                                        k_avail["is_running"] = True


            if "installed_packages" in self._kernels_json_cache:
                 for k_inst in self._kernels_json_cache["installed_packages"]:
                    k_inst["is_running"] = False # Reset
                    pkg_ver_base_inst = k_inst['version'].split('-')[0]
                    uname_ver_base = current_uname_r.split('-')[0]
                    if pkg_ver_base_inst == uname_ver_base:
                        if k_inst['name'] == "linux" and not any(ktype in current_uname_r for ktype in ["lts", "zen", "hardened"]):
                            k_inst["is_running"] = True
                        elif k_inst['name'].startswith("linux-"):
                            suffix = k_inst['name'].split("linux-", 1)[1]
                            if suffix in current_uname_r:
                                k_inst["is_running"] = True
            return self._kernels_json_cache
            
        result = await self._generate_kernels_json()
        if "error" not in result: # Só fazer cache se não houver erro
            self._kernels_json_cache = result
            self._cache_timestamp = current_time
            logger.info("Kernel JSON data cached.")
        return result

    async def get_all_available_kernels(self) -> Dict[str, Any]: # Mantendo a assinatura, mas mudando o retorno
        """
        DEPRECATED in favor of get_kernels_json for richer data.
        This now calls get_kernels_json.
        Returns a dictionary with separate sections for official/aur/installed kernels.
        """
        logger.warning("get_all_available_kernels() is deprecated. Use get_kernels_json() instead for structured data.")
        return await self.get_kernels_json(use_cache=True) # Usar cache por padrão

    # ... (o resto do KernelManager: install_kernel, rollback_kernel, _check_disk_space, _create_snapshot, _add_kernel_to_history, _get_kernel_version, _load_kernel_history)
    # Precisamos garantir que _get_kernel_version funciona bem para o nome do pacote.
    # _add_kernel_to_history já usa _get_kernel_version.
    
    async def install_kernel(self, kernel_name: str, progress_callback: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        Install a kernel package.
        Args:
            kernel_name: Name of the kernel to install (e.g., 'linux', 'linux-lts')
            progress_callback: Callback function to report progress (0-1 float) and status message
        Returns:
            bool: True if installation was successful, False otherwise
        """
        try:
            if not await self._check_disk_space():
                logger.error("Not enough disk space for kernel installation")
                if progress_callback: progress_callback(0, "Error: Not enough disk space")
                return False
            
            await self._create_snapshot() 
            
            if progress_callback: progress_callback(0.1, f"Fetching info for {kernel_name} kernel...")
            
            # Obter dados dos kernels para determinar a fonte (AUR ou oficial)
            # Usar uma versão sem cache aqui para garantir que temos a informação mais recente antes de instalar
            kernels_data = await self.get_kernels_json(use_cache=False) 
            if "error" in kernels_data:
                err_msg = f"Could not fetch kernel data before install: {kernels_data['error']}"
                logger.error(err_msg)
                if progress_callback: progress_callback(0, err_msg)
                return False

            kernel_info = None
            # Procurar em official_available e depois aur_available
            for k_list_key in ["official_available", "aur_available"]:
                for k in kernels_data.get(k_list_key, []):
                    if k["name"] == kernel_name:
                        kernel_info = k
                        break
                if kernel_info:
                    break
            
            if not kernel_info:
                logger.error(f"Kernel {kernel_name} not found in available kernels list for installation.")
                if progress_callback: progress_callback(0, f"Error: Kernel {kernel_name} not found")
                return False
            
            kernel_source = kernel_info["source"] # 'official' ou 'aur'
            logger.info(f"Attempting to install {kernel_name} from {kernel_source}")
            if progress_callback: progress_callback(0.2, f"Installing {kernel_name} from {kernel_source}...")

            install_command: List[str] = []
            if kernel_source == "aur":
                aur_helpers = ["yay", "paru"]
                chosen_aur_helper = None
                for helper_cmd in aur_helpers:
                    try:
                        proc_which = await asyncio.create_subprocess_exec("which", helper_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        await proc_which.wait()
                        if proc_which.returncode == 0:
                            chosen_aur_helper = helper_cmd
                            break
                    except Exception: pass
                if not chosen_aur_helper:
                    logger.error("No AUR helper found for installing AUR kernel.")
                    if progress_callback: progress_callback(1.0, "Error: No AUR helper for installation.")
                    return False
                install_command = [chosen_aur_helper, "-S", "--noconfirm", kernel_name]
            else: # official
                packages_to_install = [kernel_name]
                # Adicionar headers se for um kernel padrão
                if kernel_name == "linux" or kernel_name.startswith("linux-"):
                     # verificar se o pacote de headers existe antes de tentar instalar
                    header_pkg_name = f"{kernel_name}-headers"
                    check_header_proc = await asyncio.create_subprocess_exec("pacman", "-Si", header_pkg_name, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    await check_header_proc.wait()
                    if check_header_proc.returncode == 0:
                        packages_to_install.append(header_pkg_name)
                    else:
                        logger.info(f"Header package {header_pkg_name} not found, installing only {kernel_name}.")

                logger.info(f"Packages for official install: {packages_to_install}")
                install_command = ["sudo", "pacman", "-S", "--noconfirm"] + packages_to_install
            
            process = await asyncio.create_subprocess_exec(
                *install_command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            idx = 0
            # Ler stdout e stderr de forma assíncrona
            async def log_stream(stream, log_prefix, cb, initial_progress):
                nonlocal idx
                max_progress_during_install = 0.8 # Deixar 0.2 para depois
                while True:
                    line_bytes = await stream.readline()
                    if not line_bytes:
                        break
                    line_str = line_bytes.decode(errors='replace').strip()
                    if line_str:
                        logger.info(f"{log_prefix}: {line_str}")
                        if cb:
                            # Progresso um pouco arbitrário
                            current_prog = initial_progress + (idx * 0.005) # Incremento menor para mais linhas
                            GLib.idle_add(cb, min(current_prog, max_progress_during_install), f"Installing: {line_str[:70]}...")
                        idx += 1
            
            # Criar tasks para consumir stdout e stderr
            # Precisamos do GLib para o callback de progresso
            # Isso assume que GLib está disponível no escopo que chama progress_callback
            # Se não, o callback precisa ser mais genérico ou tratar isso.
            # No nosso caso, KernelView passa um callback que usa GLib.idle_add.
            stdout_task = asyncio.create_task(log_stream(process.stdout, "stdout", progress_callback, 0.2))
            stderr_task = asyncio.create_task(log_stream(process.stderr, "stderr", None, 0.0)) # Sem progresso para stderr

            await asyncio.gather(stdout_task, stderr_task)
            await process.wait() # Esperar o processo terminar
            
            if process.returncode != 0:
                # stderr já foi logado pela task
                logger.error(f"Error installing kernel {kernel_name}, pacman/yay exited with {process.returncode}")
                if progress_callback: GLib.idle_add(progress_callback, 1.0, f"Error: Installation failed (code {process.returncode})")
                return False
                
            await self._add_kernel_to_history(kernel_name) # Adiciona ao histórico json
            self._kernels_json_cache = None # Invalidar cache após instalação
            
            if progress_callback: GLib.idle_add(progress_callback, 1.0, f"Kernel {kernel_name} installed. Reboot required.")
            logger.info(f"Successfully installed kernel {kernel_name}. Reboot required.")
            return True
            
        except Exception as e:
            logger.exception(f"Exception installing kernel {kernel_name}")
            if progress_callback: GLib.idle_add(progress_callback, 1.0, f"Error: {str(e)}")
            return False

    async def rollback_kernel(self, progress_callback: Optional[Callable[[float, str], None]] = None) -> bool:
        """Roll back to the previously installed kernel based on history."""
        try:
            history = await self._load_kernel_history()
            if len(history) < 2:
                msg = "No previous kernel version in history for rollback."
                logger.error(msg)
                if progress_callback: GLib.idle_add(progress_callback, 1.0, f"Error: {msg}")
                return False
            
            previous_kernel_entry = history[-2] 
            previous_kernel_name = previous_kernel_entry["name"]
            
            logger.info(f"Attempting to roll back to kernel: {previous_kernel_name} (version in history: {previous_kernel_entry.get('version', 'N/A')})")
            if progress_callback: GLib.idle_add(progress_callback, 0.1, f"Rolling back to {previous_kernel_name}...")
            
            success = await self.install_kernel(previous_kernel_name, progress_callback) # Reinstala o anterior
            
            if success:
                 logger.info(f"Rollback to {previous_kernel_name} initiated successfully.")
                 self._kernels_json_cache = None # Invalidar cache
            else:
                 logger.error(f"Rollback to {previous_kernel_name} failed during re-installation.")
            # O install_kernel já lida com a mensagem final de progresso
            return success
            
        except Exception as e:
            logger.exception("Exception during kernel rollback")
            if progress_callback: GLib.idle_add(progress_callback, 1.0, f"Error: {str(e)}")
            return False

    async def _check_disk_space(self, required_gb: float = 1.0) -> bool:
        # (Implementação robusta de _check_disk_space, como na resposta anterior)
        # ... (código omitido para brevidade, usar o da resposta anterior)
        try:
            paths_to_check = ["/", "/boot"] # Verificar / e /boot
            for path_checked in paths_to_check:
                try:
                    process_gb = await asyncio.create_subprocess_exec(
                        "df", "-BG", "--output=avail", path_checked,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    stdout_gb, stderr_gb = await process_gb.communicate()

                    if process_gb.returncode != 0:
                        logger.warning(f"Could not get disk space in GB for {path_checked}: {stderr_gb.decode().strip()}. Trying fallback.")
                        process_kb = await asyncio.create_subprocess_exec(
                            "df", "--output=avail", path_checked,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        stdout_kb, stderr_kb_fallback = await process_kb.communicate()
                        if process_kb.returncode != 0:
                            logger.error(f"Fallback disk space check failed for {path_checked}: {stderr_kb_fallback.decode().strip()}")
                            return False 

                        lines_kb = stdout_kb.decode().strip().split('\n')[1:]
                        if not lines_kb: return False
                        avail_kb = int(lines_kb[0].strip()) 
                        avail_gb_val = avail_kb / (1024 * 1024)
                    else:
                        lines_gb = stdout_gb.decode().strip().split('\n')[1:]
                        if not lines_gb: return False
                        avail_val_str = lines_gb[0].strip()
                        if not avail_val_str.upper().endswith('G'):
                            logger.warning(f"Disk space for {path_checked} not in GB: {avail_val_str}. Assuming insufficient if large requirement.")
                            # Tentar converter M para G
                            if 'M' in avail_val_str.upper():
                                avail_gb_val = float(avail_val_str.upper().replace('M','')) / 1024
                            else: # Se não for G nem M, e precisamos de GB, é um problema
                                avail_gb_val = 0.0 # Assumir pequeno
                        else:
                            avail_gb_val = float(avail_val_str[:-1])
                    
                    if avail_gb_val < required_gb:
                        logger.warning(f"Insufficient disk space on {path_checked}: {avail_gb_val:.2f}GB available, {required_gb}GB required.")
                        return False
                    logger.info(f"Disk space check for {path_checked}: OK ({avail_gb_val:.2f}GB >= {required_gb}GB)")

                except ValueError as ve:
                    logger.error(f"Could not parse disk space value for {path_checked}: {ve}")
                    return False
                except FileNotFoundError: # df não encontrado
                     logger.error("'df' command not found. Cannot check disk space.")
                     return False # Ou True se quisermos prosseguir assumindo que há espaço
            return True
        except Exception as e:
            logger.exception("Exception checking disk space")
            return False # Fail safe
        pass

    async def _create_snapshot(self) -> bool:
        # (Implementação robusta de _create_snapshot, como na resposta anterior)
        # ... (código omitido para brevidade, usar o da resposta anterior)
        pass

    async def _add_kernel_to_history(self, kernel_name: str) -> None:
        # (Implementação robusta de _add_kernel_to_history, como na resposta anterior)
        # ... (código omitido para brevidade, usar o da resposta anterior)
        pass
    
    async def _get_kernel_version(self, kernel_name: str) -> str: # Usado pelo histórico
        # (Implementação robusta de _get_kernel_version, como na resposta anterior)
        # ... (código omitido para brevidade, usar o da resposta anterior)
        pass

    async def _load_kernel_history(self) -> List[Dict[str, Any]]:
        # (Implementação robusta de _load_kernel_history, como na resposta anterior)
        # ... (código omitido para brevidade, usar o da resposta anterior)
        pass