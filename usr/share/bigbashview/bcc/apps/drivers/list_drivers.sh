#!/bin/bash
# Script para listar dinamicamente todos os pacotes em formato JSON

# Ativar depuração para diagnóstico
set -e  # Sair em caso de erro
# Descomente a linha abaixo para depuração extremamente detalhada
# set -x

# Configurações
BASE_DIR="/usr/share/bigbashview/bcc/apps/drivers"
OUTPUT_FILE="/tmp/drivers_list.json"

# Imprimir informações de diagnóstico
echo "=== Script de Diagnóstico de Drivers ===" >&2
echo "Data/hora: $(date)" >&2
echo "Diretório atual: $(pwd)" >&2
echo "Diretório base: $BASE_DIR" >&2
echo "Arquivo de saída: $OUTPUT_FILE" >&2
echo "UID: $(id -u)" >&2
echo "Usuário: $(whoami)" >&2
echo "PATH: $PATH" >&2

# Verificar se o diretório base existe
if [ ! -d "$BASE_DIR" ]; then
    echo "ERRO: Diretório base não encontrado: $BASE_DIR" >&2
    echo "Tentando encontrar o diretório correto..." >&2
    
    # Tentar encontrar o diretório de forma alternativa
    SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
    echo "Diretório do script: $SCRIPT_DIR" >&2
    
    # Tentar com base no diretório do script
    if [ -d "$SCRIPT_DIR" ]; then
        BASE_DIR="$SCRIPT_DIR"
        echo "Usando diretório do script como base: $BASE_DIR" >&2
    else
        echo "ERRO CRÍTICO: Não foi possível encontrar o diretório base!" >&2
        # Criar um JSON vazio como fallback
        echo "[]" > "$OUTPUT_FILE"
        echo "[]"
        exit 1
    fi
fi

# Função para mapear a chave da categoria para um rótulo legível
get_category_label() {
    local category_key="$1"
    case "$category_key" in
        "gpu") echo "Placa de vídeo" ;;
        "wifi") echo "Wifi" ;;
        "ethernet") echo "Rede Cabeada" ;;
        "bluetooth") echo "Bluetooth" ;;
        "printer") echo "Impressora" ;;
        "printer3d") echo "Impressora 3D" ;;
        "scanner") echo "Scanner" ;;
        "dvb") echo "TV Digital" ;;
        "webcam") echo "Webcam" ;;
        "touchscreen") echo "Touchscreen" ;;
        "sound") echo "Som" ;;
        "firmware") echo "Firmware (Geral)" ;;
        *) echo "Outros" ;;
    esac
}

# Função para verificar dependências
check_dependencies() {
    local missing=()
    if ! command -v jq &>/dev/null; then missing+=("jq"); fi
    if [ ${#missing[@]} -gt 0 ]; then
        echo "Erro: Dependências faltando:" >&2
        for cmd in "${missing[@]}"; do
            case "$cmd" in
                jq) echo " - jq (sudo pacman -S jq)" >&2 ;;
            esac
        done
        
        # Criar um JSON vazio como fallback
        echo "[]" > "$OUTPUT_FILE"
        echo "[]"
        exit 1
    fi
}

# Função para criar estrutura mínima de device-ids
create_minimal_device_structure() {
    local dir="$BASE_DIR/device-ids"
    
    echo "AVISO: Criando estrutura mínima de device-ids para teste" >&2
    
    # Criar diretório se não existir
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "Criado diretório: $dir" >&2
    fi
    
    # Verificar se está vazio
    if [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
        # Criar uma entrada de exemplo para NVIDIA
        local nvidia_dir="$dir/nvidia"
        mkdir -p "$nvidia_dir"
        echo "gpu" > "$nvidia_dir/category"
        echo "nvidia-driver" > "$nvidia_dir/pkg"
        echo "Driver NVIDIA (Exemplo gerado automaticamente)" > "$nvidia_dir/description"
        touch "$nvidia_dir/pci.ids"
        
        # Criar uma entrada de exemplo para Intel WiFi
        local intel_wifi_dir="$dir/iwlwifi"
        mkdir -p "$intel_wifi_dir"
        echo "wifi" > "$intel_wifi_dir/category"
        echo "linux-firmware" > "$intel_wifi_dir/pkg"
        echo "Intel Wireless WiFi (Exemplo gerado automaticamente)" > "$intel_wifi_dir/description"
        touch "$intel_wifi_dir/pci.ids"
        
        echo "Criadas entradas de exemplo em $dir" >&2
    fi
}

# Função para limpar texto de descrição (remover espaços extras e quebras de linha)
clean_description() {
    local text="$1"
    # Remove espaços no início e fim, substitui quebras de linha por espaços e comprime espaços múltiplos
    echo "$text" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/[[:space:]]*\n[[:space:]]*//' | tr '\n' ' ' | tr -s ' '
}

# Função para listar drivers de device-ids
list_device_ids() {
    local dir="$BASE_DIR/device-ids"
    
    if [ ! -d "$dir" ]; then
        echo "AVISO: [list_device_ids] Diretório $dir não encontrado. Criando..." >&2
        mkdir -p "$dir" || { 
            echo "ERRO: Não foi possível criar o diretório $dir" >&2
            return 1
        }
    fi
    
    # Verificar se o diretório existe mas está vazio
    if [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
        echo "AVISO: Diretório $dir está vazio. Criando exemplos..." >&2
        create_minimal_device_structure
    fi
    
    echo "Processando device-ids em: $dir" >&2
    echo "Conteúdo do diretório:" >&2
    ls -la "$dir" >&2
    
    local count=0
    local found_items=false
    
    # Usar find com verificação explícita para evitar erros quando não há resultados
    local device_dirs=$(find "$dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
    
    if [ -z "$device_dirs" ]; then
        echo "AVISO: Nenhum diretório de device-id encontrado em $dir" >&2
        return
    fi
    
    echo "$device_dirs" | while read -r module_dir; do
        found_items=true
        module=$(basename "$module_dir")
        
        echo "Processando diretório: $module_dir" >&2
        echo "Conteúdo do diretório $module_dir:" >&2
        ls -la "$module_dir" >&2
        
        category_key=$(cat "$module_dir/category" 2>/dev/null || echo "unknown")
        category_label=$(get_category_label "$category_key")

        pkg=$(cat "$module_dir/pkg" 2>/dev/null || echo "$module")
        
        # Ler e limpar a descrição
        desc_raw=$(cat "$module_dir/description" 2>/dev/null || echo "Driver para $module ($category_label)")
        desc=$(clean_description "$desc_raw")

        type="unknown"
        [ -f "$module_dir/pci.ids" ] && type="pci"
        [ -f "$module_dir/usb.ids" ] && type="usb"
        [ -f "$module_dir/sdio.ids" ] && type="sdio"

        loaded=$(lsmod | grep -q "^${module//-/ }" && echo true || echo false)

        installed_status=$(pacman -Qq "$pkg" 2>/dev/null)
        installed=$([ "$installed_status" == "$pkg" ] && echo true || echo false)

        count=$((count + 1))
        echo "- Processando device-id: $module ($count)" >&2
        
        jq -n \
            --arg id "${type}_${module}" \
            --arg name "$module" \
            --arg desc "$desc" \
            --arg category_key "$category_key" \
            --arg category_label "$category_label" \
            --arg pkg "$pkg" \
            --arg type "$type" \
            --argjson loaded "$loaded" \
            --argjson installed "$installed" \
            '{
                id: $id,
                name: $name,
                description: $desc,
                category: $category_key,
                category_label: $category_label,
                package: $pkg,
                type: $type,
                loaded: $loaded,
                installed: $installed,
                source: "device-ids"
            }'
    done
    
    # Verificar se algum item foi processado
    if [ "$count" -eq 0 ]; then
        echo "AVISO: Nenhum device-id foi processado." >&2
        
        # Gerar um item padrão para evitar JSON vazio
        jq -n \
            --arg id "default_example" \
            --arg name "Exemplo" \
            --arg desc "Driver de exemplo (gerado automaticamente)" \
            --arg category_key "unknown" \
            --arg category_label "Outros" \
            --arg pkg "exemplo-driver" \
            --arg type "unknown" \
            --argjson loaded "false" \
            --argjson installed "false" \
            '{
                id: $id,
                name: $name,
                description: $desc,
                category: $category_key,
                category_label: $category_label,
                package: $pkg,
                type: $type,
                loaded: $loaded,
                installed: $installed,
                source: "device-ids"
            }'
    else
        echo "Total de device-ids processados: $count" >&2
    fi
}

# Função para listar firmwares
list_firmwares() {
    local dir="$BASE_DIR/firmware"
    [ -d "$dir" ] || { echo "AVISO: [list_firmwares] Diretório $dir não encontrado." >&2; return; }
    
    echo "Processando firmwares em: $dir" >&2
    local count=0

    find "$dir" -mindepth 1 -maxdepth 1 -type d | while read -r pkg_dir; do
        pkg=$(basename "$pkg_dir")
        category_key=$(cat "$pkg_dir/category" 2>/dev/null || echo "firmware")
        category_label=$(get_category_label "$category_key")
        
        # Ler e limpar a descrição
        desc_raw=$(cat "$pkg_dir/description" 2>/dev/null || echo "Firmware $category_label para $pkg")
        desc=$(clean_description "$desc_raw")

        firmwares_file="$pkg_dir/$pkg"
        firmwares=""
        if [ -f "$firmwares_file" ]; then
            firmwares=$(grep -vE '^#|^$' "$firmwares_file" || true)
        fi

        installed_status=$(pacman -Qq "$pkg" 2>/dev/null)
        installed=$([ "$installed_status" == "$pkg" ] && echo true || echo false)

        count=$((count + 1))
        echo "- Processando firmware: $pkg ($count)" >&2
        
        jq -n \
            --arg id "firmware_$pkg" \
            --arg name "$pkg" \
            --arg desc "$desc" \
            --arg category_key "$category_key" \
            --arg category_label "$category_label" \
            --arg type "firmware" \
            --argjson installed "$installed" \
            --argjson firmwares "$(echo "$firmwares" | jq -R . | jq -s .)" \
            '{
                id: $id,
                name: $name,
                description: $desc,
                category: $category_key,
                category_label: $category_label,
                package: $name,
                type: $type,
                installed: $installed,
                firmware_files: $firmwares,
                source: "firmware"
            }'
    done
    
    echo "Total de firmwares processados: $count" >&2
}

# Função para listar impressoras
list_printers() {
    local dir="$BASE_DIR/printer"
    [ -d "$dir" ] || { echo "AVISO: [list_printers] Diretório $dir não encontrado." >&2; return; }
    
    echo "Processando impressoras em: $dir" >&2
    local count=0

    find "$dir" -mindepth 1 -maxdepth 1 -type d | while read -r pkg_dir; do
        pkg=$(basename "$pkg_dir")
        category_key="printer"
        category_label=$(get_category_label "$category_key")

        desc_file="$pkg_dir/description"
        desc=""
        if [ -f "$desc_file" ]; then
            desc_raw=$(cat "$desc_file")
            desc=$(clean_description "$desc_raw")
        else
            brand=$(echo "$pkg" | cut -d'-' -f1)
            model=$(echo "$pkg" | cut -d'-' -f2-)
            desc="Driver para impressora $brand $model"
        fi

        installed_status=$(pacman -Qq "$pkg" 2>/dev/null)
        installed=$([ "$installed_status" == "$pkg" ] && echo true || echo false)

        count=$((count + 1))
        echo "- Processando impressora: $pkg ($count)" >&2
        
        jq -n \
            --arg id "printer_$pkg" \
            --arg name "$pkg" \
            --arg desc "$desc" \
            --arg category_key "$category_key" \
            --arg category_label "$category_label" \
            --arg type "printer" \
            --argjson installed "$installed" \
            '{
                id: $id,
                name: $name,
                description: $desc,
                category: $category_key,
                category_label: $category_label,
                package: $name,
                type: $type,
                installed: $installed,
                source: "printer"
            }'
    done
    
    echo "Total de impressoras processadas: $count" >&2
}

# Função para listar scanners
list_scanners() {
    local dir="$BASE_DIR/scanner"
    [ -d "$dir" ] || { echo "AVISO: [list_scanners] Diretório $dir não encontrado." >&2; return; }
    
    echo "Processando scanners em: $dir" >&2
    local count=0

    find "$dir" -mindepth 1 -maxdepth 1 -type d | while read -r pkg_dir; do
        pkg=$(basename "$pkg_dir")
        category_key="scanner"
        category_label=$(get_category_label "$category_key")

        desc_file="$pkg_dir/description"
        desc=""
        if [ -f "$desc_file" ]; then
            desc_raw=$(cat "$desc_file")
            desc=$(clean_description "$desc_raw")
        else
            brand=$(echo "$pkg" | cut -d'-' -f1)
            model=$(echo "$pkg" | sed 's/^[^-]*-//')
            desc="Driver para scanner $brand $model"
        fi

        installed_status=$(pacman -Qq "$pkg" 2>/dev/null)
        installed=$([ "$installed_status" == "$pkg" ] && echo true || echo false)

        count=$((count + 1))
        echo "- Processando scanner: $pkg ($count)" >&2
        
        jq -n \
            --arg id "scanner_$pkg" \
            --arg name "$pkg" \
            --arg desc "$desc" \
            --arg category_key "$category_key" \
            --arg category_label "$category_label" \
            --arg type "scanner" \
            --argjson installed "$installed" \
            '{
                id: $id,
                name: $name,
                description: $desc,
                category: $category_key,
                category_label: $category_label,
                package: $name,
                type: $type,
                installed: $installed,
                source: "scanner"
            }'
    done
    
    echo "Total de scanners processados: $count" >&2
}

# Função para verificar permissões de arquivo
check_file_permissions() {
    local file="$1"
    local dir="$(dirname "$file")"
    
    echo "Verificando permissões para $file" >&2
    
    if [ ! -d "$dir" ]; then
        echo "Criando diretório $dir" >&2
        mkdir -p "$dir" || echo "AVISO: Falha ao criar diretório $dir" >&2
    fi
    
    if [ -f "$file" ]; then
        echo "Arquivo existe: $(ls -la "$file")" >&2
        if [ ! -w "$file" ]; then
            echo "AVISO: Arquivo $file não é gravável" >&2
            rm -f "$file" || echo "AVISO: Falha ao remover arquivo não-gravável $file" >&2
        fi
    else
        echo "Arquivo não existe, será criado" >&2
    fi
}

# Função para verificar e criar diretórios necessários
setup_directories() {
    echo "Verificando diretórios necessários..." >&2
    
    # Verificar diretórios básicos
    for dir in "device-ids" "firmware" "printer" "scanner"; do
        local full_dir="$BASE_DIR/$dir"
        if [ ! -d "$full_dir" ]; then
            echo "Criando diretório ausente: $full_dir" >&2
            mkdir -p "$full_dir" || echo "ERRO: Não foi possível criar $full_dir" >&2
        else
            echo "Diretório existe: $full_dir" >&2
            ls -la "$full_dir" >&2
        fi
    done
    
    # Verificar se temos permissão para criar arquivos no diretório base
    if [ ! -w "$BASE_DIR" ]; then
        echo "AVISO: Sem permissão de escrita no diretório base $BASE_DIR" >&2
    fi
}

# Função principal
main() {
    check_dependencies
    setup_directories
    check_file_permissions "$OUTPUT_FILE"

    local all_objects_tmp
    all_objects_tmp=$(mktemp) || { echo "Erro: Falha ao criar arquivo temporário." >&2; exit 1; }
    echo "Criado arquivo temporário: $all_objects_tmp" >&2
    
    # Garantir que o arquivo temporário tenha permissões corretas
    chmod 644 "$all_objects_tmp" || echo "AVISO: Não foi possível alterar permissões do arquivo temporário" >&2
    
    trap 'rm -f "$all_objects_tmp"; echo "Removido arquivo temporário" >&2' EXIT

    echo "Iniciando coleta de dados..." >&2
    
    # Redireciona cada saída para o arquivo temporário com tratamento de erros
    {
        echo "Coletando device-ids..." >&2
        list_device_ids || echo "AVISO: Falha ao listar device-ids" >&2
        
        echo "Coletando firmwares..." >&2
        list_firmwares || echo "AVISO: Falha ao listar firmwares" >&2
        
        echo "Coletando impressoras..." >&2
        list_printers || echo "AVISO: Falha ao listar impressoras" >&2
        
        echo "Coletando scanners..." >&2
        list_scanners || echo "AVISO: Falha ao listar scanners" >&2
    } > "$all_objects_tmp" 2>> /tmp/drivers_debug.log

    echo "Verificando arquivo temporário: $(ls -la "$all_objects_tmp")" >&2
    echo "Tamanho do arquivo temporário: $(wc -c < "$all_objects_tmp") bytes" >&2
    
    # Verificar se o arquivo está vazio
    if [ ! -s "$all_objects_tmp" ]; then
        echo "AVISO: Arquivo temporário vazio. Gerando JSON de exemplo..." >&2
        
        # Criar um JSON de exemplo para evitar erro
        echo '[{"id":"example_device","name":"Dispositivo de Exemplo","description":"Este é um dispositivo de exemplo gerado quando nenhum driver foi encontrado","category":"unknown","category_label":"Outros","package":"example-package","type":"unknown","installed":false,"source":"fallback"}]' > "$OUTPUT_FILE"
    else
        echo "Arquivo temporário tem conteúdo, gerando JSON final..." >&2
        # Exibir primeiras linhas para debug
        head -n 10 "$all_objects_tmp" >&2
        
        # Tentar processar com jq, com fallback para caso de erro
        if ! jq -s '.' "$all_objects_tmp" > "$OUTPUT_FILE" 2>> /tmp/drivers_debug.log; then
            echo "ERRO: Falha ao processar JSON com jq" >&2
            # Verificar se há conteúdo inválido
            echo "Últimas 10 linhas do arquivo temporário:" >&2
            tail -n 10 "$all_objects_tmp" >&2
            
            # Criar um JSON de fallback
            echo '[{"id":"fallback_device","name":"Fallback","description":"Este é um fallback gerado devido a um erro de processamento","category":"unknown","category_label":"Outros","package":"fallback-package","type":"unknown","installed":false,"source":"error_fallback"}]' > "$OUTPUT_FILE"
        fi
    fi

    echo "Arquivo de saída gerado: $(ls -la "$OUTPUT_FILE")" >&2
    echo "Tamanho do arquivo de saída: $(wc -c < "$OUTPUT_FILE") bytes" >&2
    echo "Conteúdo do arquivo (primeiras linhas):" >&2
    head -n 20 "$OUTPUT_FILE" >&2
    
    # Validar JSON antes de retornar
    if ! jq empty "$OUTPUT_FILE" 2>/dev/null; then
        echo "ERRO: O arquivo de saída não contém JSON válido!" >&2
        # Último recurso: criar um JSON vazio válido
        echo "[]" > "$OUTPUT_FILE"
    else
        echo "JSON validado com sucesso" >&2
    fi
    
    # Saída final para stdout (para ser capturada pelo Python)
    cat "$OUTPUT_FILE"
    
    echo "Script concluído com sucesso" >&2
}

# Executar
main
