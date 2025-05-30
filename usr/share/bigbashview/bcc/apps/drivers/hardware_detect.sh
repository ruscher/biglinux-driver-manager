#!/bin/bash

# Script para detectar hardware e mostrar apenas os dispositivos compatíveis encontrados
# Saída no formato JSON específico

# Função para formatar a saída no formato JSON
format_output() {
    echo "{"
    echo "  \"name\": \"$1\","
    echo "  \"device\": \"$2\","
    echo "  \"driver\": \"$3\","
    echo "  \"id\": \"$4\","
    echo "  \"open\": $5,"
    echo "  \"compatible\": $6,"
    echo "  \"installed\": $7,"
    echo "  \"module\": \"$8\","
    echo "  \"package\": \"$9\","
    echo "  \"source\": \"${10:-device-ids}\"" # Default to device-ids if not provided
    echo "},"
}

# Diretório base para os device-ids
DEVICE_IDS_DIR="/usr/share/bigbashview/bcc/apps/drivers/device-ids"

# Variável para armazenar a saída JSON
OUTPUT_FILE="$(mktemp)"
echo "[" > "$OUTPUT_FILE" # Início do array JSON

# 1. Detecção de módulos (PCI, USB, SDIO)
OIFS=$IFS
IFS=$'\n'

# PCI
PCI_LIST="$(grep -Ri : "$DEVICE_IDS_DIR" 2>/dev/null | grep -i 'pci.ids' 2>/dev/null)"

for i in $(lspci -nn); do
    ID="$(echo "$i" | rev | cut -f1 -d[ | cut -f2 -d] | rev)"
    TYPE="$(echo "$i" | cut -f1 -d[ | cut -f1 -d: | xargs)"
    NAME="$(echo "$i" | cut -f2- -d: | rev | cut -f2- -d[ | rev | xargs)"

    if [ -n "$PCI_LIST" ] && [ "$(echo "$PCI_LIST" | grep -i "$ID")" != "" ]; then
        ADDR="$(grep -i -m1 -R "$ID" "$DEVICE_IDS_DIR" 2>/dev/null)"
        MODULE="$(echo "$ADDR" | cut -f2 -d/)"

        # Verifica se o módulo está carregado
        if lsmod | grep -q "^${MODULE}\s"; then
            INSTALLED="true"
        else
            INSTALLED="false"
        fi

        # Verifica se é open (assume que todos os módulos são open)
        OPEN="true"

        # Compatible é true pois foi encontrado na lista
        COMPATIBLE="true"

        format_output \
            "$NAME" \
            "$TYPE" \
            "$MODULE" \
            "$ID" \
            "$OPEN" \
            "$COMPATIBLE" \
            "$INSTALLED" \
            "$MODULE" \
            "$MODULE" \
            "device-ids" >> "$OUTPUT_FILE" # Explicitly set source
    fi
done

# USB
USB_LIST="$(grep -Ri : "$DEVICE_IDS_DIR" 2>/dev/null | grep -i 'usb.ids' 2>/dev/null)"

for i in $(lsusb); do
    ID="$(echo "$i" | cut -f6 -d" ")"
    NAME="$(echo "$i" | cut -f7- -d" " | xargs)"
    TYPE="USB"

    if [ -n "$USB_LIST" ] && [ "$(echo "$USB_LIST" | grep -i "$ID")" != "" ]; then
        ADDR="$(grep -i -m1 -R "$ID" "$DEVICE_IDS_DIR" 2>/dev/null)"
        MODULE="$(echo "$ADDR" | cut -f2 -d/)"

        # Verifica se o módulo está carregado
        if lsmod | grep -q "^${MODULE}\s"; then
            INSTALLED="true"
        else
            INSTALLED="false"
        fi

        # Verifica se é open (assume que todos os módulos são open)
        OPEN="true"

        # Compatible é true pois foi encontrado na lista
        COMPATIBLE="true"

        format_output \
            "$NAME" \
            "$TYPE" \
            "$MODULE" \
            "$ID" \
            "$OPEN" \
            "$COMPATIBLE" \
            "$INSTALLED" \
            "$MODULE" \
            "$MODULE" \
            "device-ids" >> "$OUTPUT_FILE" # Explicitly set source
    fi
done

# SDIO
SDIO_LIST="$(grep -Ri : "$DEVICE_IDS_DIR" 2>/dev/null | grep -i 'sdio.ids' 2>/dev/null)"

for i in $(ls /sys/bus/sdio/devices/ 2>/dev/null); do
    Vendor="$(cat /sys/bus/sdio/devices/$i/vendor 2>/dev/null | cut -f2 -dx)"
    Device="$(cat /sys/bus/sdio/devices/$i/device 2>/dev/null | cut -f2 -dx)"

    ID="$Vendor:$Device"
    NAME="SDIO Device $ID"
    TYPE="SDIO"

    if [ -n "$SDIO_LIST" ] && [ "$(echo "$SDIO_LIST" | grep -i "$ID")" != "" ]; then
        ADDR="$(grep -i -m1 -R "$ID" "$DEVICE_IDS_DIR" 2>/dev/null)"
        MODULE="$(echo "$ADDR" | cut -f2 -d/)"

        # Verifica se o módulo está carregado
        if lsmod | grep -q "^${MODULE}\s"; then
            INSTALLED="true"
        else
            INSTALLED="false"
        fi

        # Verifica se é open (assume que todos os módulos são open)
        OPEN="true"

        # Compatible é true pois foi encontrado na lista
        COMPATIBLE="true"

        format_output \
            "$NAME" \
            "$TYPE" \
            "$MODULE" \
            "$ID" \
            "$OPEN" \
            "$COMPATIBLE" \
            "$INSTALLED" \
            "$MODULE" \
            "$MODULE" \
            "device-ids" >> "$OUTPUT_FILE" # Explicitly set source
    fi
done

# 2. Detecção de drivers MHWD (apenas os compatíveis)
if command -v mhwd >/dev/null 2>&1; then
    # Get list of installed drivers once to improve performance
    INSTALLED_DRIVERS=$(mhwd -li | awk '{print $1}')
    
    # Processa a saída do mhwd -l linha por linha
    mhwd -l | while IFS= read -r line; do
        # Detecta início de bloco de dispositivo
        if [[ $line =~ \(([0-9a-f]{4}:[0-9a-f]{4}:[0-9a-f]{4})\) ]]; then
            # Remove os primeiros 5 caracteres (0300: → fica só vendor:device)
            FULL_ID="${BASH_REMATCH[1]}"
            ID="${FULL_ID:5}"

            NAME=""

            # Extrai nome se existir
            if [[ $line =~ \)\ (.+): ]]; then
                NAME="${BASH_REMATCH[1]}"
            fi

            # Determina o tipo
            TYPE_CODE="${FULL_ID:0:4}"
            case "$TYPE_CODE" in
                "0300") TYPE="Graphics" ;;
                "0200") TYPE="Network" ;;
                *) TYPE="Other" ;;
            esac

            # Variáveis para processar drivers
            PROCESSING_DRIVERS=false
            DRIVERS=()
            continue
        fi

        # Marca início da seção de drivers
        if [[ $line =~ ^[[:space:]]*(TYPE|[[:space:]]*NAME[[:space:]]+VERSION[[:space:]]+FREEDRIVER[[:space:]]+TYPE)[[:space:]]*$ ]]; then
            PROCESSING_DRIVERS=true
            continue
        fi

        # Ignora linhas de separador
        [[ $line =~ ^-+$ ]] && continue

        # Coleta drivers durante o processamento
        if [[ $PROCESSING_DRIVERS == true && $line =~ ^[[:space:]]*([a-zA-Z0-9_.-]+) ]]; then
            DRIVER="${BASH_REMATCH[1]}"

            # Filtra drivers relevantes (video-* ou network-*, exceto os básicos)
            if [[ $DRIVER =~ ^(video|network)- ]] && [[ ! $DRIVER =~ ^(video-linux|video-modesetting|video-vesa)$ ]]; then
                DRIVERS+=("$DRIVER")
            fi
        fi

        # Quando encontra linha vazia, processa todos os drivers coletados
        if [[ -z "$line" && -n "$ID" && ${#DRIVERS[@]} -gt 0 ]]; then
            for MODULE in "${DRIVERS[@]}"; do
                # Verifica se está instalado usando o resultado do mhwd -li
                if echo "$INSTALLED_DRIVERS" | grep -q "^${MODULE}$"; then
                    INSTALLED="true"
                else
                    INSTALLED="false"
                fi

                # Verifica se é free
                if mhwd -la | grep "^$MODULE " | awk '{print $3}' | grep -q "free"; then
                    OPEN="true"
                else
                    OPEN="false"
                fi

                COMPATIBLE="true"

                # Adiciona descrição específica para o driver
                DESCRIPTION=""
                case "$MODULE" in
                    video-nvidia)
                        DESCRIPTION="Driver proprietário NVIDIA mais recente" ;;
                    video-nvidia-390xx)
                        DESCRIPTION="Driver proprietário NVIDIA legado (série 390xx)" ;;
                    video-nvidia-470xx)
                        DESCRIPTION="Driver proprietário NVIDIA legado (série 470xx)" ;;
                    video-hybrid-*)
                        DESCRIPTION="Driver híbrido para sistemas com GPU integrada e dedicada" ;;
                    network-*)
                        DESCRIPTION="Driver para dispositivo de rede" ;;
                    *)
                        DESCRIPTION="Driver para $NAME" ;;
                esac

                # Adiciona informação adicional ao JSON para melhor identificação
                echo "{" >> "$OUTPUT_FILE"
                echo "  \"name\": \"$NAME\"," >> "$OUTPUT_FILE"
                echo "  \"device\": \"$TYPE\"," >> "$OUTPUT_FILE"
                echo "  \"driver\": \"$MODULE\"," >> "$OUTPUT_FILE"
                echo "  \"id\": \"$ID\"," >> "$OUTPUT_FILE"
                echo "  \"open\": $OPEN," >> "$OUTPUT_FILE"
                echo "  \"compatible\": $COMPATIBLE," >> "$OUTPUT_FILE"
                echo "  \"installed\": $INSTALLED," >> "$OUTPUT_FILE"
                echo "  \"module\": \"$MODULE\"," >> "$OUTPUT_FILE"
                echo "  \"package\": \"$MODULE\"," >> "$OUTPUT_FILE"
                echo "  \"description\": \"$DESCRIPTION\"," >> "$OUTPUT_FILE"
                echo "  \"source\": \"mhwd\"" >> "$OUTPUT_FILE" # Add source for MHWD
                echo "}," >> "$OUTPUT_FILE"
            done

            # Reseta variáveis para o próximo dispositivo
            ID=""
            NAME=""
            TYPE=""
            DRIVERS=()
            PROCESSING_DRIVERS=false
        fi
    done
fi

IFS=$OIFS

# Adiciona drivers adicionais baseados em outros métodos

# Exemplo para RTL8168 se detectado
if lspci | grep -i "Realtek RTL8111/8168/8411" > /dev/null; then
    # Check if network-r8168 is already listed by mhwd to avoid duplicates
    # This assumes network-r8168 is an mhwd package.
    # A more robust check would be to see if mhwd -l lists it for the device.
    if ! grep -q "\"package\": \"network-r8168\"" "$OUTPUT_FILE"; then
        R8168_INSTALLED="false"
        if mhwd -li | grep -q "network-r8168"; then
            R8168_INSTALLED="true"
        fi

        echo "{" >> "$OUTPUT_FILE"
        echo "  \"name\": \"Network controller Realtek RTL8111/8168/8411\"," >> "$OUTPUT_FILE"
        echo "  \"device\": \"Network\"," >> "$OUTPUT_FILE"
        echo "  \"driver\": \"r8168\"," >> "$OUTPUT_FILE" # Kernel module name
        echo "  \"id\": \"10ec:8168\"," >> "$OUTPUT_FILE"
        echo "  \"open\": true," >> "$OUTPUT_FILE"
        echo "  \"compatible\": true," >> "$OUTPUT_FILE"
        echo "  \"installed\": $R8168_INSTALLED," >> "$OUTPUT_FILE"
        echo "  \"module\": \"r8168\"," >> "$OUTPUT_FILE" # Kernel module name
        echo "  \"package\": \"network-r8168\"," >> "$OUTPUT_FILE" # MHWD package name
        echo "  \"description\": \"Driver alternativo para placas de rede Realtek 8168/8111/8411 (MHWD)\"," >> "$OUTPUT_FILE"
        echo "  \"source\": \"mhwd\"" >> "$OUTPUT_FILE" # Add source for MHWD
        echo "}," >> "$OUTPUT_FILE"
    fi
fi

# Remove a última vírgula para validar o JSON
sed -i '$ s/,$//' "$OUTPUT_FILE" 2>/dev/null
echo "]" >> "$OUTPUT_FILE" # Fim do array JSON

# Conta quantos drivers foram encontrados
NUM_DRIVERS=$(grep -c "\"name\":" "$OUTPUT_FILE")
echo "Detected $NUM_DRIVERS compatible drivers" >&2

# Exibe o resultado
cat "$OUTPUT_FILE"
rm -f "$OUTPUT_FILE"
