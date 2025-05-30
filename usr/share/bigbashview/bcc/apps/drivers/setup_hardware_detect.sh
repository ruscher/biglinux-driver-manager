#!/bin/bash

# Script para preparar o hardware_detect.sh no diretório /tmp
# Este script copia o hardware_detect.sh para /tmp e o modifica conforme necessário

# Caminho para o script original
ORIGINAL_SCRIPT="/usr/share/bigbashview/bcc/apps/drivers/hardware_detect.sh"
TARGET_SCRIPT="/tmp/biglinux_hardware_detect.sh"

# Verifica se o script original existe
if [ ! -f "$ORIGINAL_SCRIPT" ]; then
    echo "Script original não encontrado: $ORIGINAL_SCRIPT"
    exit 1
fi

# Copia o script para /tmp
cp "$ORIGINAL_SCRIPT" "$TARGET_SCRIPT"

# Dá permissão de execução
chmod +x "$TARGET_SCRIPT"

# Modifica o script para garantir saída formatada corretamente
# Adiciona contagem de drivers no final do arquivo para depuração
sed -i '/^# Exibe o resultado/i\\n# Conta quantos drivers foram encontrados\nNUM_DRIVERS=$(grep -c "\\\"name\\\":" "$OUTPUT_FILE")\necho "Detected $NUM_DRIVERS compatible drivers" >&2\n' "$TARGET_SCRIPT"

echo "Script hardware_detect.sh preparado em $TARGET_SCRIPT"
