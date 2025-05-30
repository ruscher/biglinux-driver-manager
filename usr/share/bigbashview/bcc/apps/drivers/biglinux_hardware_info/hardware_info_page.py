import gi
from typing import Dict, List, Any, Optional, Tuple
import logging
import json
import subprocess
import threading
import re
import os
import tempfile

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('PangoCairo', '1.0') # Para text metrics se usarmos Cairo
from gi.repository import Gtk, Adw, GLib, Pango, Gdk, PangoCairo

# Stub classes
# ... (stubs como antes) ...
logger_stub = logging.getLogger(__name__ + "_stub")
logger_stub.warning("Could not import SystemInfo or CategoryRow. Using stubs.")
class SystemInfo: 
    def __init__(self): pass
class CategoryRow(Gtk.ListBoxRow):
    def __init__(self, category_id: str, title: str, icon_name: str):
        super().__init__()
        self.category_id = category_id
        # ... (resto do stub como antes) ...
        self.set_name(f"category-row-{category_id.lower().replace(' ', '-')}")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(6); box.set_margin_bottom(6); box.set_margin_start(6); box.set_margin_end(6)
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            box.append(icon)
        label = Gtk.Label(label=title); label.set_xalign(0)
        box.append(label)
        self.set_child(box)

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- CSS Provider ---
CSS_PROVIDER = Gtk.CssProvider()
CSS_DATA = """
progressbar.thin {
    min-height: 8px; /* Mais fino */
    border-radius: 4px; /* Bordas arredondadas */
}

/* As classes .success, .warning, .error já são estilizadas pelo Adwaita para ProgressBar */
/* Se precisar de cores customizadas, descomente e ajuste: */
/*
progressbar.low-usage trough {
    background-color: @success_color;
}
progressbar.medium-usage trough {
    background-color: @warning_color;
}
progressbar.high-usage trough {
    background-color: @error_color;
}
*/

.flowbox-tag {
    font-size: small;
    padding: 2px 6px;
    margin: 2px;
    border-radius: 10px;
    background-color: @accent_bg_color;
    color: @accent_fg_color;
}

.expander-title-padding > GtkBox > GtkLabel.title {
    margin-left: 6px; /* Pequeno padding para o título do expander */
}
"""
CSS_PROVIDER.load_from_data(CSS_DATA.encode())
Gtk.StyleContext.add_provider_for_display(
    Gdk.Display.get_default(), CSS_PROVIDER, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
)


class HardwareInfoPage(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        # ... (inicialização como antes) ...
        self.system_info = SystemInfo()
        self.hardware_data: Dict[str, Any] = {} 
        self.raw_inxi_data: Dict[str, List[Dict[str, Any]]] = {}
        self.pulse_id: int = 0 
        self._create_ui()
        self._load_hardware_info()

    def _create_ui(self) -> None:
        # ... (UI creation code como antes, mas vamos garantir que o content_box use Adw.Clamp se quisermos um conteúdo centralizado de largura fixa)
        # Por agora, manteremos o comportamento de preenchimento total.
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header_box.set_margin_top(12); header_box.set_margin_bottom(12); header_box.set_margin_start(12); header_box.set_margin_end(12)
        title_label = Gtk.Label(); title_label.set_markup("<b>System Overview</b>"); title_label.set_hexpand(True)
        title_label.set_halign(Gtk.Align.START); title_label.add_css_class("title-4"); header_box.append(title_label)
        refresh_button = Gtk.Button(); refresh_button.set_icon_name("view-refresh-symbolic")
        refresh_button.set_tooltip_text("Refresh information"); refresh_button.connect("clicked", self._on_refresh_clicked)
        header_box.append(refresh_button); self.append(header_box)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL); self.append(separator)
        self.progress_bar = Gtk.ProgressBar(); self.progress_bar.set_halign(Gtk.Align.CENTER); self.progress_bar.set_valign(Gtk.Align.CENTER)
        self.progress_bar.set_vexpand(True); self.progress_bar.set_pulse_step(0.1); self.progress_bar.set_show_text(False)
        self.progress_bar.set_tooltip_text("Loading hardware information..."); self.append(self.progress_bar)
        self.split_view = Adw.NavigationSplitView(); self.split_view.set_vexpand(True); self.split_view.set_sidebar_width_fraction(0.3)
        self.split_view.set_min_sidebar_width(280); self.split_view.set_max_sidebar_width(450); self.split_view.set_visible(False)
        sidebar = Adw.NavigationPage.new(Gtk.Box(), "Hardware Categories")
        sidebar_scroll = Gtk.ScrolledWindow(); sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.category_list = Gtk.ListBox(); self.category_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.category_list.set_css_classes(["navigation-sidebar"]); self.category_list.connect("row-selected", self._on_category_selected)
        sidebar_scroll.set_child(self.category_list); sidebar.set_child(sidebar_scroll)
        self.content_view = Adw.NavigationPage.new(Gtk.Box(), "Details")
        self.content_scroll = Gtk.ScrolledWindow(); self.content_scroll.set_vexpand(True)
        
        # Usar Adw.Clamp para o conteúdo principal para limitar a largura em telas grandes
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800) # Ajuste conforme necessário
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.set_margin_top(12); self.content_box.set_margin_bottom(24) # Mais margem inferior
        self.content_box.set_margin_start(18); self.content_box.set_margin_end(18)
        self.content_box.set_spacing(18) # Aumentar espaçamento entre grupos
        clamp.set_child(self.content_box)
        
        self.content_scroll.set_child(clamp) # Adicionar clamp ao scrolled window
        self.content_view.set_child(self.content_scroll)
        self.split_view.set_sidebar(sidebar); self.split_view.set_content(self.content_view); self.append(self.split_view)


    def _pulse_progress_bar(self) -> bool:
        # ... (como antes) ...
        if self.progress_bar.get_visible():
            self.progress_bar.pulse()
            return True  
        self.pulse_id = 0
        return False 

    def _load_hardware_info(self) -> None:
        # ... (como antes) ...
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0) 
        if hasattr(self, 'error_box_container') and self.error_box_container.get_parent():
            self.remove(self.error_box_container)
        if self.pulse_id == 0: 
            self.pulse_id = GLib.timeout_add(150, self._pulse_progress_bar) 
        self.split_view.set_visible(False)
        thread = threading.Thread(target=self._fetch_inxi_data)
        thread.daemon = True
        thread.start()

    def _parse_size_string_to_bytes(self, size_str: Optional[str]) -> Optional[float]:
        # ...existing code...
        if not isinstance(size_str, str): return None
        size_str_cleaned = size_str.replace(" ", "").strip()
        logger.debug(f"Parsing size string: '{size_str}' -> cleaned: '{size_str_cleaned}'")
        
        # Tentar diferentes padrões de regex
        patterns = [
            r"([\d.]+)([KMGTPEZY]I?B)",  # Padrão original
            r"([\d.]+)\s*([KMGTPEZY]I?B)",  # Com espaços
            r"([\d.]+)([KMGTPEZY]i?B)",  # Lowercase i
            r"([\d.]+)\s*([KMGTPEZY]i?B)",  # Lowercase i com espaços
        ]
        
        match = None
        for pattern in patterns:
            match = re.match(pattern, size_str_cleaned, re.IGNORECASE)
            if match:
                logger.debug(f"Matched pattern: {pattern}")
                break
        
        if not match:
            # Tentar no string original com espaços
            for pattern in patterns:
                match = re.match(pattern, size_str, re.IGNORECASE)
                if match:
                    logger.debug(f"Matched pattern on original string: {pattern}")
                    break
        
        if not match: 
            logger.debug(f"No pattern matched for: '{size_str}'")
            return None
            
        val_str, unit_str = match.groups()
        logger.debug(f"Extracted value: '{val_str}', unit: '{unit_str}'")
        
        try: value = float(val_str)
        except ValueError: 
            logger.debug(f"Could not convert value to float: '{val_str}'")
            return None
            
        unit = unit_str.upper().replace('I', ''); power = 1
        if unit.startswith("K"): power = 1024
        elif unit.startswith("M"): power = 1024**2
        elif unit.startswith("G"): power = 1024**3
        elif unit.startswith("T"): power = 1024**4
        
        result = value * power
        logger.debug(f"Final result: {result} bytes")
        return result

    def _get_usage_style_context_class(self, percentage: float) -> str:
        """Retorna a classe CSS para a ProgressBar com base na porcentagem."""
        if percentage < 0: return "" # Sem estilo para N/A
        if percentage < 50:
            return "success"  # Adwaita já define cor para .success
        elif percentage < 80:
            return "warning"  # Adwaita já define cor para .warning
        else:
            return "error"    # Adwaita já define cor para .error

    def _add_usage_bar_row(self, group: Adw.PreferencesGroup, title: str,
                           used_bytes: Optional[float], total_bytes: Optional[float],
                           label_override: Optional[str] = None,
                           icon_name: Optional[str] = None) -> None:
        row = Adw.ActionRow()
        row.set_title(title)
        
        if icon_name:
            icon_widget = Gtk.Image.new_from_icon_name(icon_name)
            row.add_prefix(icon_widget)

        progress_bar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        progress_bar_box.set_hexpand(True) # Fazer a box ocupar espaço
        progress_bar_box.set_halign(Gtk.Align.FILL)

        progress_bar = Gtk.ProgressBar()
        progress_bar.set_hexpand(True)
        progress_bar.add_css_class("thin") # Aplicar a classe CSS
        
        # Remover classes de cor anteriores
        for cls in ["success", "warning", "error", "low-usage", "medium-usage", "high-usage"]:
            progress_bar.remove_css_class(cls)

        progress_bar_box.append(progress_bar)
        row.add_suffix(progress_bar_box) 

        percentage = -1.0 # Default para N/A
        if used_bytes is not None and total_bytes is not None and total_bytes > 0:
            percentage = (used_bytes / total_bytes) * 100
            fraction = min(1.0, max(0.0, used_bytes / total_bytes))

            if label_override:
                subtitle_text = label_override
            else:
                used_str = GLib.format_size(int(used_bytes))
                total_str = GLib.format_size(int(total_bytes))
                subtitle_text = f"{used_str} de {total_str} ({percentage:.1f}%)"
            
            row.set_subtitle(subtitle_text)
            progress_bar.set_fraction(fraction)
            progress_bar.set_text(f"{percentage:.0f}%") 
            progress_bar.set_show_text(True)
            
            # Aplicar classe de cor
            style_class = self._get_usage_style_context_class(percentage)
            if style_class:
                progress_bar.add_css_class(style_class)
        else:
            row.set_subtitle("Informação indisponível")
            progress_bar.set_fraction(0)
            progress_bar.set_text("N/A")
            progress_bar.set_show_text(True)
            progress_bar.set_sensitive(False)
            
        row.set_subtitle_selectable(True)
        group.add(row)

    def _create_system_summary(self) -> None:
        # ...existing code...
        while child := self.content_box.get_first_child(): self.content_box.remove(child)
        
        # === GRUPO 1: INFORMAÇÕES DO SISTEMA (mais importante) ===
        system_group = Adw.PreferencesGroup()
        system_group.set_title("Sistema Operacional")
        system_group.set_description("Informações básicas do sistema")
        
        # OS Name
        os_name_str = "Desconhecido"
        system_section = self.raw_inxi_data.get("System")
        if system_section and isinstance(system_section, list):
            for item in system_section:
                if isinstance(item, dict) and "Distro" in item:
                    os_name_str = item.get("Distro", "Desconhecido")
                    break
        self._add_summary_row(system_group, "Sistema Operacional", os_name_str, "computer-symbolic")
        
        # Kernel Version
        kernel_ver_str = "Desconhecido"
        if system_section and isinstance(system_section, list):
            for item in system_section:
                if isinstance(item, dict) and "Kernel" in item:
                    kernel_ver_str = item.get("Kernel", "Desconhecido")
                    break
        self._add_summary_row(system_group, "Versão do Kernel", kernel_ver_str, "preferences-system-symbolic")
        
        # Installation Date
        install_date = self._get_installation_date()
        self._add_summary_row(system_group, "Data de Instalação", install_date or "Não determinada", "calendar-symbolic")
        
        self.content_box.append(system_group)
        
        # === GRUPO 2: HARDWARE PRINCIPAL (segunda prioridade) ===
        hardware_group = Adw.PreferencesGroup()
        hardware_group.set_title("Hardware Principal")
        hardware_group.set_description("Componentes essenciais do sistema")
        
        # CPU
        cpu_model_str = "Desconhecido"
        cpu_section = self.raw_inxi_data.get("CPU")
        if cpu_section and isinstance(cpu_section, list) and len(cpu_section) > 0:
            model = cpu_section[0].get("model", "CPU Desconhecido")
            cores = "N/A"
            if len(cpu_section) > 1 and isinstance(cpu_section[1], dict):
                cores = cpu_section[1].get("cores", "N/A")
            cpu_model_str = f"{model} ({cores} cores)"
        self._add_summary_row(hardware_group, "Processador", cpu_model_str, "cpu-symbolic")

        # Memory with usage bar
        total_mem_bytes, used_mem_bytes = None, None
        mem_label_override = None
        
        # Debug: Log toda a estrutura de dados relacionada à memória
        logger.debug("=== DEBUG MEMORY PARSING ===")
        logger.debug(f"Available sections: {list(self.raw_inxi_data.keys())}")
        
        # ...existing memory parsing logic...
        
        # Primeiro, tentar obter dados da seção Memory dedicada
        memory_section_dedicated = self.raw_inxi_data.get("Memory")
        logger.debug(f"Memory section: {memory_section_dedicated}")
        if memory_section_dedicated and isinstance(memory_section_dedicated, list):
            ram_info_list = [item.get("ram") for item in memory_section_dedicated if isinstance(item, dict) and "ram" in item]
            logger.debug(f"RAM info list: {ram_info_list}")
            if ram_info_list and isinstance(ram_info_list[0], dict):
                ram_info = ram_info_list[0]
                total_obj = ram_info.get('total')
                used_obj = ram_info.get('used')
                logger.debug(f"RAM info - total: {total_obj}, used: {used_obj}")
                if isinstance(total_obj, dict):
                    total_mem_bytes = self._parse_size_string_to_bytes(f"{total_obj.get('value')} {total_obj.get('unit')}")
                elif isinstance(total_obj, str):
                    total_mem_bytes = self._parse_size_string_to_bytes(total_obj)
                if isinstance(used_obj, dict):
                    used_mem_bytes = self._parse_size_string_to_bytes(f"{used_obj.get('value')} {used_obj.get('unit')}")
                elif isinstance(used_obj, str):
                    used_mem_bytes = self._parse_size_string_to_bytes(used_obj)
        
        # Se não encontrou dados na seção Memory, tentar na seção Info
        if total_mem_bytes is None or used_mem_bytes is None:
            info_section = self.raw_inxi_data.get("Info")
            logger.debug(f"Info section: {info_section}")
            if info_section and isinstance(info_section, list):
                for i, item in enumerate(info_section):
                    logger.debug(f"Info item {i}: {item}")
                    if isinstance(item, dict):
                        # Verificar se tem chave "Memory" (pode ser vazia)
                        if "Memory" in item:
                            logger.debug(f"Found Memory key in item {i}: {item}")
                            # Buscar total
                            if total_mem_bytes is None and "total" in item:
                                total_mem_str = item.get("total")
                                logger.debug(f"Found total: {total_mem_str}")
                                total_mem_bytes = self._parse_size_string_to_bytes(total_mem_str)
                                logger.debug(f"Parsed total bytes: {total_mem_bytes}")
                            
                            # Buscar used
                            if used_mem_bytes is None and "used" in item:
                                used_mem_str_full = item.get("used")
                                logger.debug(f"Found used: {used_mem_str_full}")
                                if used_mem_str_full:
                                    used_match = re.match(r"([\d.]+\s*[KMGTPEZY]i?B?)", used_mem_str_full)
                                    if used_match:
                                        used_mem_bytes = self._parse_size_string_to_bytes(used_match.group(1))
                                        logger.debug(f"Parsed used bytes: {used_mem_bytes}")
                            
                            # Se temos total e available mas não used, calcular used
                            if total_mem_bytes is not None and used_mem_bytes is None and "available" in item:
                                available_mem_str = item.get("available")
                                logger.debug(f"Found available: {available_mem_str}")
                                available_mem_bytes = self._parse_size_string_to_bytes(available_mem_str)
                                if available_mem_bytes is not None:
                                    used_mem_bytes = total_mem_bytes - available_mem_bytes
                                    logger.debug(f"Calculated used bytes from available: {used_mem_bytes}")
                            
                            break
                        
                        # Também verificar se as chaves estão diretamente no item (sem chave "Memory")
                        elif any(key in item for key in ["total", "used", "available"]):
                            logger.debug(f"Found memory data directly in item {i}: {item}")
                            # Buscar total
                            if total_mem_bytes is None and "total" in item:
                                total_mem_str = item.get("total")
                                logger.debug(f"Found direct total: {total_mem_str}")
                                total_mem_bytes = self._parse_size_string_to_bytes(total_mem_str)
                                logger.debug(f"Parsed direct total bytes: {total_mem_bytes}")
                            
                            # Buscar used
                            if used_mem_bytes is None and "used" in item:
                                used_mem_str_full = item.get("used")
                                logger.debug(f"Found direct used: {used_mem_str_full}")
                                if used_mem_str_full:
                                    used_match = re.match(r"([\d.]+\s*[KMGTPEZY]i?B?)", used_mem_str_full)
                                    if used_match:
                                        used_mem_bytes = self._parse_size_string_to_bytes(used_match.group(1))
                                        logger.debug(f"Parsed direct used bytes: {used_mem_bytes}")
                            
                            # Se temos total e available mas não used, calcular used
                            if total_mem_bytes is not None and used_mem_bytes is None and "available" in item:
                                available_mem_str = item.get("available")
                                logger.debug(f"Found direct available: {available_mem_str}")
                                available_mem_bytes = self._parse_size_string_to_bytes(available_mem_str)
                                if available_mem_bytes is not None:
                                    used_mem_bytes = total_mem_bytes - available_mem_bytes
                                    logger.debug(f"Calculated direct used bytes from available: {used_mem_bytes}")
                            
                            break
        
        # Fallback: tentar /proc/meminfo se ainda não temos dados
        if total_mem_bytes is None or used_mem_bytes is None:
            logger.debug("Trying /proc/meminfo fallback")
            try:
                with open('/proc/meminfo', 'r') as f:
                    meminfo = f.read()
                    
                for line in meminfo.split('\n'):
                    if line.startswith('MemTotal:') and total_mem_bytes is None:
                        total_kb = int(line.split()[1])
                        total_mem_bytes = total_kb * 1024
                        logger.debug(f"Got total from /proc/meminfo: {total_mem_bytes}")
                    elif line.startswith('MemAvailable:') and used_mem_bytes is None and total_mem_bytes is not None:
                        avail_kb = int(line.split()[1])
                        available_mem_bytes = avail_kb * 1024
                        used_mem_bytes = total_mem_bytes - available_mem_bytes
                        logger.debug(f"Calculated used from /proc/meminfo: {used_mem_bytes}")
                        break
            except Exception as e:
                logger.debug(f"Failed to read /proc/meminfo: {e}")
        
        logger.debug(f"Final memory values - total: {total_mem_bytes}, used: {used_mem_bytes}")
        logger.debug("=== END DEBUG MEMORY PARSING ===")
        
        self._add_usage_bar_row(hardware_group, "Memória RAM", used_mem_bytes, total_mem_bytes, label_override=mem_label_override, icon_name="memory-symbolic")

        # Graphics
        graphics_str = "Desconhecido"
        graphics_section = self.raw_inxi_data.get("Graphics")
        if graphics_section and isinstance(graphics_section, list):
            for device_info in graphics_section:
                if isinstance(device_info, dict) and device_info.get("class-ID") == "0300" and "Device" in device_info:
                    vendor = device_info.get("vendor", "")
                    model_name = device_info.get("Device", "GPU Desconhecido")
                    model_name_cleaned = re.sub(r"^(Advanced Micro Devices \[AMD/ATI\]|NVIDIA|Intel Corporation)\s*", "", model_name).strip()
                    graphics_str = f"{vendor} {model_name_cleaned}".strip()
                    break
        self._add_summary_row(hardware_group, "Placa de Vídeo", graphics_str, "video-display-symbolic")
        
        self.content_box.append(hardware_group)

        # === GRUPO 3: ARMAZENAMENTO (terceira prioridade) ===
        storage_group = Adw.PreferencesGroup()
        storage_group.set_title("Armazenamento")
        storage_group.set_description("Informações sobre discos e partições")
        
        storage_summary = self._get_storage_summary()
        if storage_summary.get('partition_total_bytes') is not None and storage_summary.get('partition_used_bytes') is not None:
            disk_label_override = (f"{storage_summary.get('partition_used_str', 'N/A')} de "
                                   f"{storage_summary.get('partition_total_str', 'N/A')} em "
                                   f"{storage_summary.get('partition_device', 'N/A')} ({storage_summary.get('partition_usage_percent', 'N/A')})")
            self._add_usage_bar_row(storage_group, "Uso do Disco Raiz (/)", storage_summary['partition_used_bytes'], storage_summary['partition_total_bytes'], label_override=disk_label_override, icon_name="drive-harddisk-symbolic")
            self._add_summary_row(storage_group, "Dispositivo da Partição", storage_summary.get('partition_device', 'N/A'), "drive-harddisk-root-symbolic")
            self._add_summary_row(storage_group, "Tamanho Total", storage_summary.get('partition_total_str', 'N/A'), "view-fullscreen-symbolic")
            self._add_summary_row(storage_group, "Espaço Livre", storage_summary.get('partition_free_str', 'N/A'), "folder-open-symbolic")
        else:
            self._add_summary_row(storage_group, "Armazenamento", "Informação indisponível", "drive-harddisk-symbolic")

        self.content_box.append(storage_group)
        
        # Verificar se algum grupo foi criado com sucesso
        if not any(group.get_first_child() for group in [system_group, hardware_group, storage_group]):
            label = Gtk.Label(label="Não foi possível obter informações do sistema.")
            label.set_halign(Gtk.Align.CENTER)
            label.set_valign(Gtk.Align.CENTER)
            label.set_vexpand(True)
            self.content_box.append(label)

    def _get_storage_summary(self) -> Dict[str, Any]:
        # ... (como antes) ...
        storage_info: Dict[str, Any] = {}; partition_section = self.raw_inxi_data.get("Partition"); root_part_data = None
        if partition_section and isinstance(partition_section, list):
            for part_data_item in partition_section:
                if isinstance(part_data_item, dict) and part_data_item.get("ID") == "/":
                    root_part_data = part_data_item; break
        if root_part_data:
            storage_info['partition_device'] = root_part_data.get("dev", "N/A")
            total_str_inxi = root_part_data.get("raw-size"); used_str_full_inxi = root_part_data.get("used")
            total_bytes = self._parse_size_string_to_bytes(total_str_inxi); used_bytes = None; used_str_for_display = "N/A"
            if used_str_full_inxi:
                match = re.match(r"([\d.]+\s*[KMGTPEZY]i?B?)\s*\(?([\d.]+%)?\)?", used_str_full_inxi)
                if match:
                    used_val_unit_part = match.group(1); used_bytes = self._parse_size_string_to_bytes(used_val_unit_part)
                    used_str_for_display = used_val_unit_part 
                    if match.group(2): storage_info['partition_usage_percent'] = match.group(2)
            if total_bytes is not None:
                storage_info['partition_total_bytes'] = total_bytes
                storage_info['partition_total_str'] = GLib.format_size(int(total_bytes))
            if used_bytes is not None:
                storage_info['partition_used_bytes'] = used_bytes
                storage_info['partition_used_str'] = GLib.format_size(int(used_bytes))
            if total_bytes is not None and used_bytes is not None:
                free_bytes = total_bytes - used_bytes; storage_info['partition_free_bytes'] = free_bytes
                storage_info['partition_free_str'] = GLib.format_size(int(free_bytes))
                if 'partition_usage_percent' not in storage_info and total_bytes > 0:
                    storage_info['partition_usage_percent'] = f"{(used_bytes / total_bytes * 100):.1f}%"
        if not all(k in storage_info for k in ['partition_total_bytes', 'partition_used_bytes', 'partition_free_bytes']):
            logger.debug("Inxi storage data incomplete for root, trying df fallback.")
            df_fallback_info = self._get_storage_fallback()
            for key, value in df_fallback_info.items():
                if key not in storage_info or storage_info[key] is None: storage_info[key] = value
        return storage_info


    def _get_storage_fallback(self) -> Dict[str, Any]:
        # ... (como antes) ...
        storage_info_fallback: Dict[str, Any] = {}
        try:
            df_output = subprocess.check_output(['df', '--output=source,size,used,avail', '--block-size=1', '/'], text=True, timeout=5)
            lines = df_output.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    storage_info_fallback['partition_device'] = parts[0]
                    try:
                        total_b = float(parts[1]); used_b = float(parts[2]); avail_b = float(parts[3])
                        storage_info_fallback['partition_total_bytes'] = total_b; storage_info_fallback['partition_used_bytes'] = used_b
                        storage_info_fallback['partition_free_bytes'] = avail_b
                        storage_info_fallback['partition_total_str'] = GLib.format_size(int(total_b))
                        storage_info_fallback['partition_used_str'] = GLib.format_size(int(used_b))
                        storage_info_fallback['partition_free_str'] = GLib.format_size(int(avail_b))
                        if total_b > 0: storage_info_fallback['partition_usage_percent'] = f"{(used_b / total_b * 100):.1f}%"
                    except ValueError: logger.debug("Could not parse df numeric output during fallback.")
        except Exception as e: logger.debug(f"Failed to get storage info from df fallback: {e}")
        return storage_info_fallback


    def _get_installation_date(self) -> Optional[str]:
        # ...existing code...
        
        # Método 1: Verificar /etc/hostname ou /etc/machine-id (mais confiável)
        try:
            # machine-id é criado durante a instalação
            if os.path.exists('/etc/machine-id'):
                stat_info = os.stat('/etc/machine-id')
                install_timestamp = stat_info.st_mtime  # Usar mtime ao invés de ctime
                install_date = subprocess.check_output(['date', '-d', f'@{int(install_timestamp)}', '+%d/%m/%Y'], text=True, timeout=2).strip()
                logger.debug(f"Install date from /etc/machine-id: {install_date}")
                return install_date
        except Exception as e: 
            logger.debug(f"Could not determine installation date from /etc/machine-id: {e}")
        
        # Método 2: Verificar logs de instalação se existirem
        install_log_paths = [
            '/var/log/installer/syslog',
            '/var/log/calamares.log',
            '/var/log/ubiquity/syslog',
            '/var/log/anaconda/anaconda.log'
        ]
        
        for log_path in install_log_paths:
            try:
                if os.path.exists(log_path):
                    stat_info = os.stat(log_path)
                    install_timestamp = stat_info.st_mtime
                    install_date = subprocess.check_output(['date', '-d', f'@{int(install_timestamp)}', '+%d/%m/%Y'], text=True, timeout=2).strip()
                    logger.debug(f"Install date from {log_path}: {install_date}")
                    return install_date
            except Exception as e:
                logger.debug(f"Could not get date from {log_path}: {e}")
                continue
        
        # Método 3: Verificar diretórios do sistema criados na instalação
        system_dirs = [
            '/etc',
            '/var/lib/dpkg',  # Para sistemas Debian/Ubuntu
            '/var/lib/rpm',   # Para sistemas Red Hat/Fedora
            '/usr/share/doc'
        ]
        
        for dir_path in system_dirs:
            try:
                if os.path.exists(dir_path):
                    stat_info = os.stat(dir_path)
                    install_timestamp = stat_info.st_ctime
                    install_date = subprocess.check_output(['date', '-d', f'@{int(install_timestamp)}', '+%d/%m/%Y'], text=True, timeout=2).strip()
                    logger.debug(f"Install date from {dir_path}: {install_date}")
                    return install_date
            except Exception as e:
                logger.debug(f"Could not get date from {dir_path}: {e}")
                continue
        
        # Método 4: Tentar dpkg log (para sistemas Debian/Ubuntu)
        try:
            if os.path.exists('/var/log/dpkg.log'):
                with open('/var/log/dpkg.log', 'r') as f:
                    first_line = f.readline().strip()
                    if first_line:
                        # Formato: 2023-01-15 10:30:25 startup archives ...
                        date_part = first_line.split()[0]
                        if len(date_part) == 10:  # YYYY-MM-DD
                            year, month, day = date_part.split('-')
                            install_date = f"{day}/{month}/{year}"
                            logger.debug(f"Install date from dpkg.log: {install_date}")
                            return install_date
        except Exception as e:
            logger.debug(f"Could not read dpkg.log: {e}")
        
        # Método 5: Verificar filesystem timestamp da partição root (fallback)
        try:
            # Usar tune2fs para ext2/3/4 filesystems
            df_output = subprocess.check_output(['df', '/'], text=True, timeout=2).strip().split('\n')
            if len(df_output) > 1:
                root_device = df_output[1].split()[0]
                logger.debug(f"Root device: {root_device}")
                
                # Tentar tune2fs para filesystems ext*
                try:
                    tune2fs_output = subprocess.check_output(['tune2fs', '-l', root_device], text=True, timeout=5)
                    for line in tune2fs_output.split('\n'):
                        if 'Filesystem created:' in line:
                            # Formato: Filesystem created:       Sun Jan 15 10:30:25 2023
                            date_str = line.split(':', 1)[1].strip()
                            timestamp = subprocess.check_output(['date', '-d', f'{date_str}', '+%d/%m/%Y'], text=True, timeout=2).strip()
                            logger.debug(f"Install date from tune2fs: {timestamp}")
                            return timestamp
                except subprocess.CalledProcessError:
                    logger.debug("tune2fs not available or filesystem not ext*")
                
        except Exception as e:
            logger.debug(f"Could not determine installation date from filesystem: {e}")
        
        # Método 6: Como último recurso, usar stat do diretório raiz
        try:
            stat_info = os.stat('/')
            install_timestamp = stat_info.st_ctime
            install_date = subprocess.check_output(['date', '-d', f'@{int(install_timestamp)}', '+%d/%m/%Y'], text=True, timeout=2).strip()
            logger.debug(f"Install date from root directory (fallback): {install_date}")
            return install_date
        except Exception as e: 
            logger.debug(f"Could not determine installation date from root directory: {e}")
        
        return None

    def _add_summary_row(self, group: Adw.PreferencesGroup, title: str, 
                        value: str, icon_name: Optional[str] = None) -> None:
        # ... (como antes) ...
        row = Adw.ActionRow(); row.set_title(title)
        row.set_subtitle(str(value) if value is not None else "N/A")
        row.set_subtitle_lines(3); row.set_subtitle_selectable(True)
        if icon_name:
            icon_widget = Gtk.Image.new_from_icon_name(icon_name)
            row.add_prefix(icon_widget)
        group.add(row)


    def _fetch_inxi_data(self) -> None:
        # ... (como antes, com a transformação do JSON) ...
        try:
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.json', encoding='utf-8') as temp_file: temp_path = temp_file.name
            logger.debug(f"Writing inxi JSON data to temporary file: {temp_path}")
            inxi_cmd = ["inxi", "-FxxxzamP", "--output", "json", "--output-file", temp_path, "--no-host", "-z"]
            result = subprocess.run(inxi_cmd, capture_output=True, text=True, check=False, timeout=90)
            if result.returncode != 0:
                logger.error(f"inxi command finished with exit code {result.returncode}. Stderr: {result.stderr.strip()}")
                if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                    raise subprocess.SubprocessError(f"inxi failed (code {result.returncode}) and produced no/empty output file. Stderr: {result.stderr.strip()}")
                logger.warning("inxi returned non-zero but an output file was found. Attempting to process.")
            with open(temp_path, 'r', encoding='utf-8') as f: content = f.read()
            content = re.sub(r'\x1b\[[0-9;]*m', '', content) 
            content = re.sub(r'"[^"]*#([^"]*)"', r'"\1"', content)
            try:
                raw_data_list_from_json = json.loads(content)
                transformed_data: Dict[str, List[Dict[str, Any]]] = {}
                if isinstance(raw_data_list_from_json, list):
                    for item_dict_wrapper in raw_data_list_from_json:
                        if isinstance(item_dict_wrapper, dict): transformed_data.update(item_dict_wrapper)
                self.raw_inxi_data = transformed_data 
                self.hardware_data = self._map_raw_to_display_categories(self.raw_inxi_data)
            except json.JSONDecodeError as json_err:
                error_position = json_err.pos; context_start = max(0, error_position - 30)
                context_end = min(len(content), error_position + 30); context_snippet = content[context_start:context_end]
                logger.error(f"JSON parsing error: {json_err.msg} at pos {error_position}. Context: ...'{context_snippet}'...")
                problem_file_path = os.path.join(tempfile.gettempdir(), "inxi_problematic.json")
                with open(problem_file_path, "w", encoding='utf-8') as pf: pf.write(content)
                logger.error(f"Problematic JSON content saved to {problem_file_path}"); raise 
            GLib.idle_add(self._update_ui_with_data)
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, IOError) as e:
            logger.error(f"Error fetching or processing hardware info: {e}", exc_info=True)
            GLib.idle_add(self._show_error_message, f"Erro ao buscar informações de hardware: {str(e)}")
        finally:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try: os.unlink(temp_path); logger.debug(f"Temporary file {temp_path} deleted.")
                except Exception as e_unlink: logger.warning(f"Failed to delete temporary file {temp_path}: {e_unlink}")

    def _map_raw_to_display_categories(self, raw_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        # ... (como antes) ...
        category_mapping_keys = { 
            "System": "System Information", "CPU": "Processor (CPU)", "Graphics": "Graphics / GPU",
            "Audio": "Audio Devices", "Network": "Network Interfaces", "Drives": "Storage Devices",
            "Partition": "Partitions", "Usb": "USB Devices", "Sensors": "Sensors",
            "Memory": "Memory Details", "Machine": "Machine Info", "Info": "Processes & System Load",
            "Battery": "Battery Status", "RAID": "RAID Arrays", "Swap": "Swap Details", # Added Swap
            "Bluetooth": "Bluetooth Devices", "Repos": "Software Repositories",
        }
        processed_data = {}
        for raw_key, raw_value_list in raw_data.items():
            display_name = category_mapping_keys.get(raw_key, raw_key.replace('_', ' ').title())
            processed_data[display_name] = raw_value_list 
        return processed_data

    def _log_data_structure(self, data: Any, level: int = 0, max_level: int = 2, current_path: str = "") -> None:
        # ... (como antes) ...
        indent = '  ' * level
        if level > max_level: logger.debug(f"{indent}{current_path}: [Nesting level too deep, truncating...]"); return
        if isinstance(data, dict):
            logger.debug(f"{indent}{current_path or 'root'}: Dict with {len(data)} items:")
            if level < max_level:
                for key, value in data.items():
                    new_path = f"{current_path}.{key}" if current_path else key; value_type_name = type(value).__name__; value_preview = ""
                    if not isinstance(value, (dict, list)) or not value:
                        value_preview = str(value)[:50]; 
                        if len(str(value)) > 50: value_preview += "..."
                    logger.debug(f"{indent}  - Key: '{key}' (Type: {value_type_name}) {value_preview}")
                    if isinstance(value, (dict,list)) and value: self._log_data_structure(value, level + 1, max_level, new_path)
        elif isinstance(data, list):
            logger.debug(f"{indent}{current_path or 'root'}: List with {len(data)} items:")
            if level < max_level and len(data) > 0:
                first_item_type = type(data[0]).__name__; logger.debug(f"{indent}  - Items type (first): {first_item_type}")
                items_to_log = data[:min(2, len(data))]
                for i, item in enumerate(items_to_log):
                    new_path = f"{current_path}[{i}]"; self._log_data_structure(item, level + 1, max_level, new_path)
                if len(data) > 2: logger.debug(f"{indent}  [... {len(data) - 2} more items ...]")
        else: logger.debug(f"{indent}{current_path}: Value: {str(data)[:100]}")


    def _update_ui_with_data(self) -> None:
        # ...existing code...
        if self.pulse_id > 0:
            GLib.source_remove(self.pulse_id)
            self.pulse_id = 0
        self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_visible(False)
        self.split_view.set_visible(True)
        while child := self.category_list.get_first_child():
            self.category_list.remove(child)
        
        category_icon_mapping = {
            "Resumo do Sistema": "document-properties-symbolic",
            "Informações do Sistema": "computer-symbolic",
            "Processador (CPU)": "cpu-symbolic",
            "Detalhes da Memória": "memory-symbolic",
            "Placa de Vídeo / GPU": "video-display-symbolic",
            "Dispositivos de Áudio": "audio-card-symbolic",
            "Interfaces de Rede": "network-workgroup-symbolic",
            "Dispositivos de Armazenamento": "drive-harddisk-symbolic",
            "Partições": "drive-harddisk-system-symbolic",
            "Dispositivos USB": "drive-removable-media-usb-symbolic",
            "Sensores": "temperature-cold-symbolic",
            "Informações da Máquina": "computer-info-symbolic",
            "Processos e Carga do Sistema": "utilities-system-monitor-symbolic",
            "Status da Bateria": "battery-symbolic",
            "Arrays RAID": "drive-multidisk-symbolic",
            "Detalhes do Swap": "drive-harddisk-symbolic",
            "Dispositivos Bluetooth": "bluetooth-active-symbolic",
            "Repositórios de Software": "folder-download-symbolic",
        }
        default_icon = "dialog-information-symbolic"
        
        # Ordem de importância das categorias
        category_order = {
            "Resumo do Sistema": -10,
            "Informações do Sistema": 0,
            "Processador (CPU)": 10,
            "Detalhes da Memória": 20,
            "Placa de Vídeo / GPU": 30,
            "Dispositivos de Armazenamento": 40,
            "Partições": 45,
            "Detalhes do Swap": 47,
            "Interfaces de Rede": 50,
            "Dispositivos de Áudio": 60,
            "Dispositivos USB": 70,
            "Dispositivos Bluetooth": 75,
            "Informações da Máquina": 80,
            "Status da Bateria": 90,
            "Sensores": 100,
            "Processos e Carga do Sistema": 110,
            "Arrays RAID": 120,
            "Repositórios de Software": 130,
        }
        
        # Adicionar "Resumo do Sistema" primeiro
        all_display_categories_for_sidebar = {"Resumo do Sistema": None}
        
        # Mapear categorias para nomes em português
        translated_categories = {}
        for raw_key, raw_value in self.hardware_data.items():
            translated_key = self._translate_category_name(raw_key)
            translated_categories[translated_key] = raw_value
        
        all_display_categories_for_sidebar.update(translated_categories)
        
        sorted_categories = sorted(all_display_categories_for_sidebar.keys(), 
                                 key=lambda x: (category_order.get(x, 1000), x))
        
        has_selected_row = False
        for category_display_name in sorted_categories:
            if category_display_name == "Resumo do Sistema" or translated_categories.get(category_display_name):
                icon_name = category_icon_mapping.get(category_display_name, default_icon)
                row = CategoryRow(category_display_name, category_display_name, icon_name)
                self.category_list.append(row)
                if not has_selected_row:
                    self.category_list.select_row(row)
                    has_selected_row = True
        
        if not has_selected_row and self.category_list.get_first_child():
            self.category_list.select_row(self.category_list.get_first_child())
        elif not self.category_list.get_first_child():
            self._show_error_message("Nenhuma categoria de hardware pôde ser exibida.")

    def _translate_category_name(self, category: str) -> str:
        """Traduz nomes de categorias para português."""
        translation_map = {
            "System Information": "Informações do Sistema",
            "Processor (CPU)": "Processador (CPU)",
            "Graphics / GPU": "Placa de Vídeo / GPU",
            "Audio Devices": "Dispositivos de Áudio",
            "Network Interfaces": "Interfaces de Rede",
            "Storage Devices": "Dispositivos de Armazenamento",
            "Partitions": "Partições",
            "USB Devices": "Dispositivos USB",
            "Sensors": "Sensores",
            "Memory Details": "Detalhes da Memória",
            "Machine Info": "Informações da Máquina",
            "Processes & System Load": "Processos e Carga do Sistema",
            "Battery Status": "Status da Bateria",
            "RAID Arrays": "Arrays RAID",
            "Swap Details": "Detalhes do Swap",
            "Bluetooth Devices": "Dispositivos Bluetooth",
            "Software Repositories": "Repositórios de Software",
        }
        return translation_map.get(category, category)

    def _on_category_selected(self, listbox: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]) -> None:
        # ...existing code...
        if row is None or not isinstance(row, CategoryRow):
            return
        category_id_display_name = row.category_id
        self.content_view.set_tag(None)
        self.content_view.set_title(category_id_display_name)
        self._display_category_details(category_id_display_name)
    
    def _display_category_details(self, category_id_display_name: str) -> None:
        """Display category details using PreferencesGroup containers."""
        while child := self.content_box.get_first_child():
            self.content_box.remove(child)
        
        if category_id_display_name == "Resumo do Sistema":
            self._create_system_summary()
            return
        
        # Buscar dados da categoria usando o nome traduzido reverso
        reverse_translation_map = {
            "Informações do Sistema": "System Information",
            "Processador (CPU)": "Processor (CPU)",
            "Placa de Vídeo / GPU": "Graphics / GPU",
            "Dispositivos de Áudio": "Audio Devices",
            "Interfaces de Rede": "Network Interfaces",
            "Dispositivos de Armazenamento": "Storage Devices",
            "Partições": "Partitions",
            "Dispositivos USB": "USB Devices",
            "Sensores": "Sensors",
            "Detalhes da Memória": "Memory Details",
            "Informações da Máquina": "Machine Info",
            "Processos e Carga do Sistema": "Processes & System Load",
            "Status da Bateria": "Battery Status",
            "Arrays RAID": "RAID Arrays",
            "Detalhes do Swap": "Swap Details",
            "Dispositivos Bluetooth": "Bluetooth Devices",
            "Repositórios de Software": "Software Repositories",
        }
        
        original_category_name = reverse_translation_map.get(category_id_display_name, category_id_display_name)
        category_data_list = self.hardware_data.get(original_category_name)
        
        if not category_data_list:
            # Create empty state with PreferencesGroup
            empty_group = Adw.PreferencesGroup()
            empty_group.set_title("Informação Indisponível")
            empty_group.set_description(f"Nenhuma informação disponível para {category_id_display_name}")
            
            empty_row = Adw.ActionRow()
            empty_row.set_title("Status")
            empty_row.set_subtitle("Dados não encontrados ou não suportados")
            empty_row.set_sensitive(False)
            empty_group.add(empty_row)
            
            self.content_box.append(empty_group)
            return
        
        self._process_category_data_with_groups(category_data_list, category_id_display_name)

    def _process_category_data_with_groups(self, data_list: List[Dict], category_name: str) -> None:
        """Process category data and organize it into PreferencesGroup containers."""
        if not isinstance(data_list, list):
            # Handle single dict case
            if isinstance(data_list, dict):
                data_list = [data_list]
            else:
                return
        
        # Special handling for different category types
        if category_name == "Processor (CPU)":
            self._create_cpu_groups(data_list)
        elif category_name == "Memory Details":
            self._create_memory_groups(data_list)
        elif category_name == "Graphics / GPU":
            self._create_graphics_groups(data_list)
        elif category_name == "Storage Devices":
            self._create_storage_groups(data_list)
        elif category_name == "Network Interfaces":
            self._create_network_groups(data_list)
        elif category_name == "Partitions":
            self._create_partition_groups(data_list)
        else:
            # Generic handling for other categories
            self._create_generic_groups(data_list, category_name)

    def _create_cpu_groups(self, cpu_data: List[Dict]) -> None:
        """Create specialized groups for CPU information."""
        # CPU Information Group
        cpu_info_group = Adw.PreferencesGroup()
        cpu_info_group.set_title("Processor (CPU) > Info")
        cpu_info_group.set_description("Detalhes técnicos do processador")
        
        # CPU Performance Group
        cpu_perf_group = Adw.PreferencesGroup()
        cpu_perf_group.set_title("Processor (CPU) > Topology")
        cpu_perf_group.set_description("Informações de performance e cache")
        
        # CPU Flags Group
        cpu_flags_group = Adw.PreferencesGroup()
        cpu_flags_group.set_title("CPU Flags")
        cpu_flags_group.set_description("Recursos e instruções suportadas")
        
        # CPU Vulnerabilities Group
        cpu_vulnerabilities_group = Adw.PreferencesGroup()
        cpu_vulnerabilities_group.set_title("Processor (CPU) > Vulnerabilities")
        cpu_vulnerabilities_group.set_description("Vulnerabilidades de segurança e mitigações")
        
        for item in cpu_data:
            if not isinstance(item, dict):
                continue
                
            for key, value in item.items():
                if key in ["model", "vendor", "family", "microcode", "revision"]:
                    self._add_info_row(cpu_info_group, key, value)
                elif key in ["cores", "threads", "cache", "L1", "L2", "L3", "speed", "max", "min"]:
                    self._add_info_row(cpu_perf_group, key, value)
                elif key == "Flags" and isinstance(value, str):
                    # Create flowbox for flags
                    flags_row = Adw.ActionRow()
                    flags_row.set_title("Flags Suportadas")
                    flags_count = len(value.split())
                    flags_row.set_subtitle(f"{flags_count} flags encontradas")
                    
                    flowbox = self._create_flowbox_for_flags(value)
                    flags_row.set_child(flowbox)
                    cpu_flags_group.add(flags_row)
                elif key == "Vulnerabilities" and isinstance(value, list):
                    # Process vulnerabilities
                    for vuln in value:
                        if isinstance(vuln, dict):
                            vuln_type = vuln.get("Type", "Unknown")
                            vuln_status = vuln.get("status", vuln.get("mitigation", "Unknown"))
                            self._add_info_row(cpu_vulnerabilities_group, vuln_type, vuln_status)
                else:
                    # Other CPU data
                    self._add_info_row(cpu_info_group, key, value)
        
        # Add groups to content box
        if cpu_info_group.get_first_child():
            self.content_box.append(cpu_info_group)
        if cpu_perf_group.get_first_child():
            self.content_box.append(cpu_perf_group)
        if cpu_vulnerabilities_group.get_first_child():
            self.content_box.append(cpu_vulnerabilities_group)
        if cpu_flags_group.get_first_child():
            self.content_box.append(cpu_flags_group)

    def _create_memory_groups(self, memory_data: List[Dict]) -> None:
        """Create specialized groups for memory information."""
        # Memory Overview Group
        memory_overview_group = Adw.PreferencesGroup()
        memory_overview_group.set_title("Memory Details > System Ram")
        memory_overview_group.set_description("Informações gerais sobre a memória do sistema")
        
        # Memory Modules Group
        memory_modules_group = Adw.PreferencesGroup()
        memory_modules_group.set_title("Módulos de Memória")
        memory_modules_group.set_description("Detalhes dos módulos de RAM instalados")
        
        for item in memory_data:
            if not isinstance(item, dict):
                continue
                
            if "ram" in item:
                # Memory overview information
                ram_info = item["ram"]
                if isinstance(ram_info, dict):
                    for key, value in ram_info.items():
                        self._add_info_row(memory_overview_group, f"RAM {key}", value)
            
            # Memory module details
            for key, value in item.items():
                if key != "ram":
                    if isinstance(value, dict):
                        # This might be a memory module
                        module_group = Adw.PreferencesGroup()
                        module_group.set_title(f"Módulo {key}")
                        
                        for mod_key, mod_value in value.items():
                            self._add_info_row(module_group, mod_key, mod_value)
                        
                        if module_group.get_first_child():
                            self.content_box.append(module_group)
                    else:
                        self._add_info_row(memory_overview_group, key, value)
        
        if memory_overview_group.get_first_child():
            self.content_box.append(memory_overview_group)
        if memory_modules_group.get_first_child():
            self.content_box.append(memory_modules_group)

    def _create_graphics_groups(self, graphics_data: List[Dict]) -> None:
        """Create specialized groups for graphics information."""
        gpu_count = 0
        
        for item in graphics_data:
            if not isinstance(item, dict):
                continue
            
            # Check if this is a graphics device
            if item.get("class-ID") == "0300" or "Device" in item:
                gpu_count += 1
                
                # GPU Device Group
                gpu_group = Adw.PreferencesGroup()
                if gpu_count == 1:
                    gpu_group.set_title("Placa de Vídeo Principal")
                else:
                    gpu_group.set_title(f"Placa de Vídeo {gpu_count}")
                
                device_name = item.get("Device", f"GPU {gpu_count}")
                gpu_group.set_description(f"Informações sobre {device_name}")
                
                # Add GPU information
                for key, value in item.items():
                    if key in ["vendor", "Device", "driver", "bus-ID", "class-ID"]:
                        display_key = {
                            "Device": "Modelo",
                            "vendor": "Fabricante", 
                            "driver": "Driver",
                            "bus-ID": "Bus ID",
                            "class-ID": "Classe"
                        }.get(key, key)
                        self._add_info_row(gpu_group, display_key, value)
                
                self.content_box.append(gpu_group)
            else:
                # Other graphics-related information
                other_group = Adw.PreferencesGroup()
                other_group.set_title("Informações Gráficas Adicionais")
                
                for key, value in item.items():
                    self._add_info_row(other_group, key, value)
                
                if other_group.get_first_child():
                    self.content_box.append(other_group)

    def _create_storage_groups(self, storage_data: List[Dict]) -> None:
        """Create specialized groups for storage devices."""
        drive_count = 0
        
        for item in storage_data:
            if not isinstance(item, dict):
                continue
                
            drive_count += 1
            
            # Storage Device Group
            storage_group = Adw.PreferencesGroup()
            device_name = item.get("model", item.get("ID", f"Drive {drive_count}"))
            storage_group.set_title(f"Dispositivo de Armazenamento {drive_count}")
            storage_group.set_description(f"Informações sobre {device_name}")
            
            # Add storage information with proper labels
            for key, value in item.items():
                display_key = {
                    "ID": "Identificador",
                    "model": "Modelo",
                    "vendor": "Fabricante",
                    "size": "Tamanho",
                    "tech": "Tecnologia",
                    "type": "Tipo",
                    "serial": "Número de Série"
                }.get(key, key.replace("_", " ").title())
                
                self._add_info_row(storage_group, display_key, value)
            
            self.content_box.append(storage_group)

    def _create_network_groups(self, network_data: List[Dict]) -> None:
        """Create specialized groups for network interfaces."""
        interface_count = 0
        
        for item in network_data:
            if not isinstance(item, dict):
                continue
                
            interface_count += 1
            
            # Network Interface Group
            network_group = Adw.PreferencesGroup()
            interface_name = item.get("IF", item.get("Device", f"Interface {interface_count}"))
            network_group.set_title(f"Interface de Rede {interface_count}")
            network_group.set_description(f"Informações sobre {interface_name}")
            
            # Add network information
            for key, value in item.items():
                display_key = {
                    "IF": "Interface",
                    "Device": "Dispositivo",
                    "vendor": "Fabricante",
                    "driver": "Driver",
                    "state": "Estado",
                    "mac": "Endereço MAC",
                    "speed": "Velocidade"
                }.get(key, key.replace("_", " ").title())
                
                self._add_info_row(network_group, display_key, value)
            
            self.content_box.append(network_group)

    def _create_partition_groups(self, partition_data: List[Dict]) -> None:
        """Create specialized groups for partition information."""
        # System Partitions Group
        system_partitions_group = Adw.PreferencesGroup()
        system_partitions_group.set_title("Partições do Sistema")
        system_partitions_group.set_description("Informações sobre as partições montadas")
        
        # Other Partitions Group
        other_partitions_group = Adw.PreferencesGroup()
        other_partitions_group.set_title("Outras Partições")
        other_partitions_group.set_description("Partições adicionais encontradas")
        
        for item in partition_data:
            if not isinstance(item, dict):
                continue
            
            mount_point = item.get("ID", "Unknown")
            is_system_partition = mount_point in ["/", "/boot", "/boot/efi", "/home", "/var", "/tmp"]
            
            target_group = system_partitions_group if is_system_partition else other_partitions_group
            
            # Create partition entry
            partition_row = Adw.ActionRow()
            partition_row.set_title(f"Partição {mount_point}")
            
            # Build subtitle with key information
            subtitle_parts = []
            if "dev" in item:
                subtitle_parts.append(f"Device: {item['dev']}")
            if "raw-size" in item:
                subtitle_parts.append(f"Tamanho: {item['raw-size']}")
            if "used" in item:
                subtitle_parts.append(f"Usado: {item['used']}")
                
            if subtitle_parts:
                partition_row.set_subtitle(" • ".join(subtitle_parts))
            
            target_group.add(partition_row)
            
            # Add detailed information as sub-rows if needed
            for key, value in item.items():
                if key not in ["ID", "dev", "raw-size", "used"]:  # Already shown in subtitle
                    detail_row = Adw.ActionRow()
                    detail_row.set_title(f"  {key.replace('-', ' ').title()}")
                    detail_row.set_subtitle(str(value))
                    detail_row.set_subtitle_selectable(True)
                    target_group.add(detail_row)
        
        if system_partitions_group.get_first_child():
            self.content_box.append(system_partitions_group)
        if other_partitions_group.get_first_child():
            self.content_box.append(other_partitions_group)

    def _create_generic_groups(self, data_list: List[Dict], category_name: str) -> None:
        """Create generic groups for categories without specialized handling."""
        item_count = 0
        
        for item in data_list:
            if not isinstance(item, dict):
                continue
                
            item_count += 1
            
            # Generic Group
            group = Adw.PreferencesGroup()
            group.set_title(f"{category_name} {item_count}")
            
            # Try to find a meaningful description
            description_keys = ["model", "Device", "name", "ID", "type"]
            description = None
            for key in description_keys:
                if key in item and isinstance(item[key], str):
                    description = item[key]
                    break
            
            if description:
                group.set_description(description)
            
            # Add all item data
            for key, value in item.items():
                self._add_info_row(group, key, value)
            
            if group.get_first_child():
                self.content_box.append(group)

    def _add_info_row(self, group: Adw.PreferencesGroup, key: str, value: Any) -> None:
        """Add an information row to a PreferencesGroup."""
        if value is None:
            return
            
        row = Adw.ActionRow()
        
        # Format the key
        display_key = str(key).replace("_", " ").replace("-", " ").title()
        row.set_title(display_key)
        
        # Format the value
        if isinstance(value, dict):
            if "value" in value and "unit" in value:
                display_value = f"{value['value']} {value['unit']}"
            else:
                display_value = json.dumps(value, indent=2)
        elif isinstance(value, list):
            if len(value) <= 3:
                display_value = ", ".join(str(v) for v in value)
            else:
                display_value = f"{len(value)} items: {', '.join(str(v) for v in value[:2])}..."
        else:
            display_value = str(value)
        
        row.set_subtitle(display_value)
        row.set_subtitle_selectable(True)
        row.set_subtitle_lines(0)  # Allow wrapping
        
        # Add icon based on key name
        icon_name = self._get_icon_for_key(key.lower())
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            row.add_prefix(icon)
        
        group.add(row)

    def _get_icon_for_key(self, key: str) -> str:
        """Get appropriate icon for a given key."""
        # Mapeamento específico de chaves para ícones
        specific_icon_mapping = {
            "info": "info-symbolic",
            "distro": "computer-symbolic",  # Ícone Linux/sistema
            "desktop": "computer-symbolic",
            "monitor": "video-display-symbolic",
            "mode": "view-fullscreen-symbolic",  # Similar a square_foot
            "modelo": "tag-symbolic",  # Similar a sell
            "model": "tag-symbolic",
        }
        
        # Verificar mapeamento específico primeiro
        if key in specific_icon_mapping:
            return specific_icon_mapping[key]
        
        # Mapeamento por categoria/tipo
        category_icon_mapping = {
            # Hardware components
            "cpu": "cpu-symbolic",
            "processor": "cpu-symbolic",
            "cores": "cpu-symbolic",
            "threads": "cpu-symbolic",
            "speed": "speedometer-symbolic",
            "frequency": "speedometer-symbolic",
            "cache": "memory-symbolic",
            "l1": "memory-symbolic",
            "l2": "memory-symbolic", 
            "l3": "memory-symbolic",
            
            # Memory
            "memory": "memory-symbolic",
            "ram": "memory-symbolic",
            "total": "memory-symbolic",
            "used": "memory-symbolic",
            "available": "memory-symbolic",
            "size": "drive-harddisk-symbolic",
            
            # Graphics
            "gpu": "video-display-symbolic",
            "graphics": "video-display-symbolic",
            "display": "video-display-symbolic",
            "resolution": "video-display-symbolic",
            "driver": "applications-development-symbolic",
            
            # Storage
            "disk": "drive-harddisk-symbolic",
            "drive": "drive-harddisk-symbolic",
            "storage": "drive-harddisk-symbolic",
            "partition": "drive-harddisk-system-symbolic",
            
            # Network
            "network": "network-workgroup-symbolic",
            "wifi": "network-wireless-symbolic",
            "ethernet": "network-wired-symbolic",
            "mac": "network-workgroup-symbolic",
            "ip": "network-workgroup-symbolic",
            
            # System
            "kernel": "preferences-system-symbolic",
            "version": "preferences-system-symbolic",
            "architecture": "preferences-system-symbolic",
            "vendor": "distributor-logo-symbolic",
            "manufacturer": "distributor-logo-symbolic",
            "brand": "distributor-logo-symbolic",
            
            # Temperature/Sensors
            "temperature": "temperature-symbolic",
            "temp": "temperature-symbolic",
            "sensor": "temperature-cold-symbolic",
            
            # Power/Battery
            "battery": "battery-symbolic",
            "power": "battery-symbolic",
            "voltage": "battery-symbolic",
            
            # Audio
            "audio": "audio-card-symbolic",
            "sound": "audio-card-symbolic",
            "volume": "audio-volume-high-symbolic",
            
            # USB/Devices
            "usb": "drive-removable-media-usb-symbolic",
            "device": "computer-symbolic",
            "port": "insert-link-symbolic",
            
            # Status/State
            "status": "dialog-information-symbolic",
            "state": "dialog-information-symbolic",
            "enabled": "dialog-information-symbolic",
            "disabled": "dialog-information-symbolic",
            
            # Security
            "vulnerability": "security-medium-symbolic",
            "security": "security-high-symbolic",
            "mitigation": "security-high-symbolic",
        }
        
        # Buscar por palavras-chave parciais
        for keyword, icon in category_icon_mapping.items():
            if keyword in key:
                return icon
        
        # Ícone padrão (arrow_right equivalente)
        return "go-next-symbolic"

    def _process_dict_data_for_expander(self, data_dict: Dict, expander_row: Adw.ExpanderRow, level: int):
        """Popula um Adw.ExpanderRow com os dados de um dicionário."""
        sorted_keys = sorted(data_dict.keys(), key=lambda k: str(k))

        for key in sorted_keys:
            value = data_dict[key]
            formatted_key = str(key).replace('_', ' ').title()

            if isinstance(value, dict) and value: # Dicionário aninhado
                sub_expander = Adw.ExpanderRow(title=formatted_key)
                sub_expander.add_css_class("expander-title-padding")
                expander_row.add_row(sub_expander)
                self._process_dict_data_for_expander(value, sub_expander, level + 1)
            elif isinstance(value, list) and value: # Lista aninhada
                list_expander = Adw.ExpanderRow(title=formatted_key)
                list_expander.add_css_class("expander-title-padding")
                expander_row.add_row(list_expander)
                
                # Processar a lista dentro do novo expander
                if all(isinstance(i, dict) for i in value):
                    for idx, list_item_dict in enumerate(value):
                        item_title = self._generate_item_summary_title(list_item_dict, formatted_key, idx)
                        dict_sub_expander = Adw.ExpanderRow(title=item_title)
                        dict_sub_expander.add_css_class("expander-title-padding")
                        list_expander.add_row(dict_sub_expander)
                        self._process_dict_data_for_expander(list_item_dict, dict_sub_expander, level + 2)
                else: # Lista de strings/valores simples
                    for list_item_val in value:
                        list_item_row = Adw.ActionRow(title=str(list_item_val))
                        list_item_row.set_subtitle_selectable(False)
                        
                        # Adicionar ícone padrão para itens de lista
                        icon = Gtk.Image.new_from_icon_name("go-next-symbolic")
                        list_item_row.add_prefix(icon)
                        
                        list_expander.add_row(list_item_row)

            elif key.lower() == "flags" and isinstance(value, str) and len(value.split()) > 5:
                flags_row = Adw.ActionRow(title=formatted_key)
                flags_row.set_subtitle(value[:100] + "..." if len(value) > 100 else value)
                flags_row.set_tooltip_text(value)
                
                # Ícone para flags
                icon = Gtk.Image.new_from_icon_name("preferences-other-symbolic")
                flags_row.add_prefix(icon)
                
                expander_row.add_row(flags_row)
            else: # Valor simples
                val_str = str(value) if value is not None else "N/A"
                if isinstance(value, dict) and 'value' in value and 'unit' in value:
                    val_str = f"{value['value']} {value['unit']}"
                
                if not val_str.strip() and not formatted_key.strip(): 
                    continue

                action_row = Adw.ActionRow(title=formatted_key)
                action_row.set_subtitle(val_str)
                action_row.set_subtitle_lines(0)
                action_row.set_subtitle_selectable(True)
                
                # Adicionar ícone baseado na chave
                icon_name = self._get_icon_for_key(key.lower())
                if icon_name:
                    icon = Gtk.Image.new_from_icon_name(icon_name)
                    action_row.add_prefix(icon)
                
                expander_row.add_row(action_row)

    def _add_property_to_group(self, group: Adw.PreferencesGroup, key: str, value: str, 
                               container_override: Optional[Gtk.Widget] = None) -> None:
        # ...existing code...
        row_title = str(key).strip()
        row_subtitle = str(value).strip()
        if not row_title and not row_subtitle: 
            return 
        
        row = Adw.ActionRow()
        if not row_subtitle and not row_title.startswith(group.get_title() or "Item"):
            row.set_title(row_title)
            row.set_title_selectable(True)
        else:
            row.set_title(row_title)
            if row_subtitle:
                row.set_subtitle(row_subtitle)
                row.set_subtitle_lines(0)
                row.set_subtitle_selectable(True)
            else: 
                row.set_title_selectable(True)
        
        row.set_activatable(False)
        
        # Adicionar ícone baseado na chave
        icon_name = self._get_icon_for_key(key.lower())
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            row.add_prefix(icon)
        
        if container_override and hasattr(container_override, "append"):
            container_override.append(row)
        else:
            group.add(row)

    def _create_flowbox_for_flags(self, flags_string: str) -> Gtk.Widget:
        flowbox = Gtk.FlowBox()
        flowbox.set_valign(Gtk.Align.START)
        flowbox.set_max_children_per_line(10) # Ajuste conforme necessário
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        
        flags = sorted(list(set(flags_string.split()))) # Ordena e remove duplicados
        for flag in flags:
            if not flag.strip(): continue
            label = Gtk.Label(label=flag)
            label.add_css_class("flowbox-tag")
            label.set_tooltip_text(flag) # Tooltip para acessibilidade
            flowbox.append(label)
        return flowbox

    def _process_category_data(self, data: Any, parent_key: str = "", level: int = 0, container: Optional[Gtk.Box] = None) -> None:
        """
        Process and display category data recursively using Adw.ExpanderRow for lists of dicts.
        'container' is the Gtk.Box where new widgets should be added.
        """
        current_container = container or self.content_box

        if level > 7:
            self._add_property_to_group(self._create_property_group(parent_key), "Data", "[Too deeply nested]", current_container)
            return

        # Caso especial: CPU Flags
        if parent_key.lower() == "cpu" and isinstance(data, list): # Detectando a seção CPU
             cpu_flags_item = next((item for item in data if isinstance(item, dict) and "Flags" in item), None)
             if cpu_flags_item and isinstance(cpu_flags_item["Flags"], str):
                 flags_expander = Adw.ExpanderRow(title="CPU Flags")
                 flags_expander.set_subtitle(f"{len(cpu_flags_item['Flags'].split())} flags found")
                 flags_expander.add_css_class("expander-title-padding")
                 flowbox_flags = self._create_flowbox_for_flags(cpu_flags_item["Flags"])
                 flags_expander.add_row(flowbox_flags) # Adiciona como uma linha, não ActionRow
                 current_container.append(flags_expander)
                 # Remove flags from further processing or handle it specially
                 # For simplicity, let original loop process it again but it won't match this specific condition.

        if isinstance(data, list):
            if not data: return

            if all(isinstance(item, dict) for item in data):
                is_main_category_list = (level == 0) # Se for a lista principal da categoria

                for i, item_dict in enumerate(data):
                    # Título para o ExpanderRow ou PreferencesGroup
                    item_summary_title = self._generate_item_summary_title(item_dict, parent_key, i)
                    
                    # Se for uma lista principal de uma categoria, não crie um PreferencesGroup aqui,
                    # crie um ExpanderRow e popule-o.
                    # Se for uma sub-lista dentro de um Expander, aí sim pode usar PreferencesGroup.
                    
                    expander = Adw.ExpanderRow()
                    expander.set_title(item_summary_title)
                    expander.add_css_class("expander-title-padding")
                    # Adicionar um subtítulo se houver poucos itens no dicionário
                    if len(item_dict) < 4:
                        subtitle_parts = []
                        for k_sub, v_sub in list(item_dict.items())[:2]:
                             if isinstance(v_sub, str) and len(v_sub) < 30:
                                subtitle_parts.append(f"{k_sub.title()}: {v_sub}")
                        if subtitle_parts:
                            expander.set_subtitle(", ".join(subtitle_parts))
                    
                    current_container.append(expander)
                    # Os filhos do expander são adicionados recursivamente
                    self._process_dict_data_for_expander(item_dict, expander, level + 1)

                return

            # Lista de itens simples (não dicionários)
            list_group = self._create_property_group(parent_key)
            for i, item in enumerate(data):
                item_prefix = parent_key.removesuffix('s').removesuffix('es') if parent_key else "Item"
                row_title = f"{item_prefix} {i+1}"
                self._add_property_to_group(list_group, row_title, str(item) if item is not None else "N/A")
            if list_group.get_first_child(): current_container.append(list_group)

        elif isinstance(data, dict):
            # Se data é um dict aqui, geralmente é porque foi chamado de uma lista de dicts com um título já definido.
            # Ou é uma sub-estrutura. Vamos criar um PreferencesGroup para ele.
            dict_group = self._create_property_group(parent_key)
            self._populate_group_with_dict(dict_group, data, level + 1)
            if dict_group.get_first_child(): current_container.append(dict_group)
        
        else: # Valor simples no nível superior (improvável para inxi)
            group = self._create_property_group(parent_key if parent_key else "Value")
            self._add_property_to_group(group, parent_key if parent_key else "Value", str(data) if data is not None else "N/A")
            if group.get_first_child(): current_container.append(group)

    def _generate_item_summary_title(self, item_dict: Dict, category_name: str, index: int) -> str:
        """Gera um título conciso para um item em uma lista (para ExpanderRow)."""
        common_title_keys = ['model', 'Device', 'name', 'ID', 'IF', 'type', 'vendor']
        title = ""
        for key in common_title_keys:
            if key in item_dict and isinstance(item_dict[key], str) and item_dict[key].strip():
                title = item_dict[key].strip()
                # Limpar prefixos comuns de vendor do título se já houver um campo vendor
                if "vendor" in item_dict and isinstance(item_dict["vendor"], str) and item_dict["vendor"]:
                    title = title.replace(item_dict["vendor"], "").strip(" []")
                break
        
        singular_category = category_name.removesuffix('s').removesuffix('es') if category_name.endswith(('s', 'es')) else category_name
        
        if title:
            return f"{singular_category} {index + 1}: {title}"
        return f"{singular_category} {index + 1}"

    def _process_dict_data_for_expander(self, data_dict: Dict, expander_row: Adw.ExpanderRow, level: int):
        """Popula um Adw.ExpanderRow com os dados de um dicionário."""
        sorted_keys = sorted(data_dict.keys(), key=lambda k: str(k))

        for key in sorted_keys:
            value = data_dict[key]
            formatted_key = str(key).replace('_', ' ').title()

            if isinstance(value, dict) and value: # Dicionário aninhado
                sub_expander = Adw.ExpanderRow(title=formatted_key)
                sub_expander.add_css_class("expander-title-padding")
                expander_row.add_row(sub_expander)
                self._process_dict_data_for_expander(value, sub_expander, level + 1)
            elif isinstance(value, list) and value: # Lista aninhada
                list_expander = Adw.ExpanderRow(title=formatted_key)
                list_expander.add_css_class("expander-title-padding")
                expander_row.add_row(list_expander)
                
                # Processar a lista dentro do novo expander
                # Se for lista de dicts, cada dict vira um sub-expander. Se for lista de strings, action rows.
                if all(isinstance(i, dict) for i in value):
                    for idx, list_item_dict in enumerate(value):
                        item_title = self._generate_item_summary_title(list_item_dict, formatted_key, idx)
                        dict_sub_expander = Adw.ExpanderRow(title=item_title)
                        dict_sub_expander.add_css_class("expander-title-padding")
                        list_expander.add_row(dict_sub_expander)
                        self._process_dict_data_for_expander(list_item_dict, dict_sub_expander, level + 2)
                else: # Lista de strings/valores simples
                    for list_item_val in value:
                        list_item_row = Adw.ActionRow(title=str(list_item_val))
                        list_item_row.set_subtitle_selectable(False) # Geralmente não precisa para itens simples
                        list_expander.add_row(list_item_row)

            elif key.lower() == "flags" and isinstance(value, str) and len(value.split()) > 5 : # Caso especial CPU Flags
                 # Este caso já é tratado no início de _process_category_data
                 # Mas se chegar aqui, exibir como texto longo ou truncado
                flags_row = Adw.ActionRow(title=formatted_key)
                flags_row.set_subtitle(value[:100] + "..." if len(value) > 100 else value)
                flags_row.set_tooltip_text(value)
                expander_row.add_row(flags_row)
            else: # Valor simples
                val_str = str(value) if value is not None else "N/A"
                if isinstance(value, dict) and 'value' in value and 'unit' in value:
                    val_str = f"{value['value']} {value['unit']}"
                
                if not val_str.strip() and not formatted_key.strip(): continue

                action_row = Adw.ActionRow(title=formatted_key)
                action_row.set_subtitle(val_str)
                action_row.set_subtitle_lines(0) # Permitir quebra de linha
                action_row.set_subtitle_selectable(True)
                expander_row.add_row(action_row)
                
    def _populate_group_with_dict(self, group: Adw.PreferencesGroup, data_dict: Dict, level: int):
        """Helper para popular um PreferencesGroup com um dicionário (usado por _process_category_data)."""
        # Similar a _process_dict_data_for_expander, mas adiciona a ActionRows ou sub-grupos.
        # Esta função pode ser simplificada ou integrada se a lógica for muito parecida.
        # Por agora, manteremos a estrutura que já funcionava para dicionários simples.
        sorted_keys = sorted(data_dict.keys(), key=lambda k: str(k))
        for key in sorted_keys:
            value = data_dict[key]
            formatted_key = str(key).replace('_', ' ').title()

            if isinstance(value, (dict, list)) and value:
                # Para sub-dicionários/listas, criar um novo grupo (ou expander) e popular recursivamente
                # Esta parte precisa de cuidado para não criar grupos demais.
                # Idealmente, _process_category_data seria chamado novamente.
                # Temporariamente, apenas stringify para evitar complexidade excessiva aqui.
                self._add_property_to_group(group, formatted_key, json.dumps(value, indent=2))

            else:
                val_str = str(value) if value is not None else "N/A"
                if isinstance(value, dict) and 'value' in value and 'unit' in value:
                    val_str = f"{value['value']} {value['unit']}"
                self._add_property_to_group(group, formatted_key, val_str)


    def _create_property_group(self, title: str = "") -> Adw.PreferencesGroup:
        # ... (como antes) ...
        group = Adw.PreferencesGroup(); 
        if title: group.set_title(self._format_category_name(title)) 
        return group
    
    def _add_property_to_group(self, group: Adw.PreferencesGroup, key: str, value: str, 
                               container_override: Optional[Gtk.Widget] = None) -> None:
        # ... (como antes, mas permite container_override) ...
        row_title = str(key).strip(); row_subtitle = str(value).strip()
        if not row_title and not row_subtitle: return 
        row = Adw.ActionRow()
        if not row_subtitle and not row_title.startswith(group.get_title() or "Item"):
            row.set_title(row_title); row.set_title_selectable(True)
        else:
            row.set_title(row_title)
            if row_subtitle:
                row.set_subtitle(row_subtitle); row.set_subtitle_lines(0); row.set_subtitle_selectable(True)
            else: row.set_title_selectable(True)
        row.set_activatable(False) 
        
        if container_override and hasattr(container_override, "append"):
            container_override.append(row) # Adiciona a um container genérico se fornecido
        else:
            group.add(row) # Adiciona ao grupo por padrão
    
    def _show_error_message(self, message: str) -> None:
        # ... (como antes) ...
        if self.pulse_id > 0: GLib.source_remove(self.pulse_id); self.pulse_id = 0
        self.progress_bar.set_fraction(0.0); self.progress_bar.set_visible(False)
        if self.split_view.get_visible():
            self.split_view.set_visible(False)
            while child := self.content_box.get_first_child(): self.content_box.remove(child)
            while child := self.category_list.get_first_child(): self.category_list.remove(child)
        if hasattr(self, 'error_box_container') and self.error_box_container.get_parent(): self.remove(self.error_box_container)
        self.error_box_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True, hexpand=True)
        self.error_box_container.set_halign(Gtk.Align.CENTER); self.error_box_container.set_valign(Gtk.Align.CENTER)
        error_box_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        error_box_content.set_margin_top(24); error_box_content.set_margin_bottom(24); error_box_content.set_margin_start(24); error_box_content.set_margin_end(24)
        error_box_content.set_halign(Gtk.Align.CENTER)
        error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic"); error_icon.set_pixel_size(64); error_box_content.append(error_icon)
        error_label = Gtk.Label(label=message); error_label.set_wrap(True); error_label.set_max_width_chars(60)
        error_label.set_justify(Gtk.Justification.CENTER); error_label.add_css_class("title-3"); error_box_content.append(error_label)
        retry_button = Gtk.Button(label="Tentar Novamente"); retry_button.connect("clicked", self._on_refresh_clicked) 
        retry_button.set_halign(Gtk.Align.CENTER); retry_button.add_css_class("pill"); retry_button.add_css_class("suggested-action")
        error_box_content.append(retry_button); self.error_box_container.append(error_box_content); self.append(self.error_box_container)

    
    def _on_refresh_clicked(self, button: Optional[Gtk.Button]=None) -> None:
        # ... (como antes) ...
        if hasattr(self, 'error_box_container') and self.error_box_container.get_parent(): self.remove(self.error_box_container)
        while child := self.content_box.get_first_child(): self.content_box.remove(child)
        while child := self.category_list.get_first_child(): self.category_list.remove(child)
        self.hardware_data = {}; self.raw_inxi_data = {}
        self._load_hardware_info()

# Exemplo de uso
if __name__ == '__main__':
    # ... (código de teste como antes, com o mock para dummy data) ...
    dummy_json_content = """
    [
      {"System": [{"Kernel": "6.1.0-test", "Distro": "TestOS Linux", "Desktop": "TestDE 5.27"}, {"v": "N/A", "tk": "TestTK"}]},
      {"CPU": [
          {"model": "Test CPU Ultra Zen 5"}, 
          {"cores": 8, "threads": 16, "L1": "512KiB", "L2": "8MiB", "L3":"32MiB"},
          {"Flags": "avx avx2 sse sse2 sse3 sse4_1 sse4_2 ssse3 svm fma much more flags to test wrapping and flowbox display for a cleaner ui experience indeed very long list"},
          {"Vulnerabilities":[{"Type":"meltdown","status":"Not Affected"}, {"Type":"spectre_v1","mitigation":"Mitigated"}]}
      ]},
      {"Graphics": [
          {"class-ID": "0300", "vendor": "TestGPU Inc.", "Device": "Spectra 9000X", "driver": "testdrv", "bus-ID": "01:00.0"},
          {"class-ID": "0300", "vendor": "AnotherGPU Ltd.", "Device": "Vision Pro Max", "driver": "anotherdrv", "bus-ID": "02:00.0"}
      ]},
      {"Info": [{"Memory": "", "total": "16 GiB", "used": "12.5 GiB", "available": "3.5 GiB"}]},
      {"Partition": [
          {"ID": "/boot/efi", "dev": "/dev/sda1", "raw-size": "500MiB", "used": "50MiB (10%)"},
          {"ID": "/", "dev": "/dev/sda2", "raw-size": "200GiB", "used": "180GiB (90%)"}
      ]},
      {"Drives": [
          {"ID": "/dev/sda", "model": "FastSSD 1TB", "vendor": "DriveMaker", "size": "931.51 GiB", "tech": "SSD"},
          {"ID": "/dev/sdb", "model": "ArchiveHDD 4TB", "vendor": "StoreMax", "size": "3.64 TiB", "tech": "HDD"}
      ]}
    ]
    """
    json_file_path = "hardware.json" 
    if not os.path.exists(json_file_path):
        print(f"'{json_file_path}' not found. Using dummy data for testing.")
        original_fetch = HardwareInfoPage._fetch_inxi_data
        def mock_fetch_inxi_data(self_page):
            try:
                logger.info("Using MOCK inxi data for UI test.")
                raw_data_list_from_json = json.loads(dummy_json_content)
                transformed_data: Dict[str, List[Dict[str, Any]]] = {}
                if isinstance(raw_data_list_from_json, list):
                    for item_dict_wrapper in raw_data_list_from_json:
                        if isinstance(item_dict_wrapper, dict): transformed_data.update(item_dict_wrapper)
                self_page.raw_inxi_data = transformed_data
                self_page.hardware_data = self_page._map_raw_to_display_categories(self_page.raw_inxi_data)
                GLib.idle_add(self_page._update_ui_with_data)
            except Exception as e:
                logger.error(f"Error in mock_fetch_inxi_data: {e}", exc_info=True)
                GLib.idle_add(self_page._show_error_message, f"Mock data error: {str(e)}")
        HardwareInfoPage._fetch_inxi_data = mock_fetch_inxi_data

    class MainWindow(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title="Hardware Info Test")
            self.set_default_size(900, 768) # Aumentar um pouco
            page = HardwareInfoPage()
            self.set_child(page)

    class TestApp(Adw.Application):
        def __init__(self):
            super().__init__(application_id="com.example.hardwareinfotest")
            # Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK) # Testar tema escuro
        def do_activate(self):
            win = MainWindow(self)
            win.present()
    app = TestApp()
    app.run(None)
    if 'original_fetch' in globals() and HardwareInfoPage._fetch_inxi_data is mock_fetch_inxi_data : # type: ignore
        HardwareInfoPage._fetch_inxi_data = original_fetch # type: ignore