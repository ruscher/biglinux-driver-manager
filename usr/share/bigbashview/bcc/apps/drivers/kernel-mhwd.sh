#!/bin/bash

# Script para listar apenas kernels principais no BigLinux

# Cores
RED='\033[1;31m'
GREEN='\033[1;32m'
BLUE='\033[1;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Obter kernel atual
current_kernel=$(uname -r)
echo -e "\n${GREEN}Kernel em uso: ${current_kernel}${NC}\n"

# Listar todos os kernels e filtrar apenas os principais
main_kernels=$(mhwd-kernel -l | grep -vi "kernels:" | sed 's|.* ||g' | grep -E '^linux[0-9]+(-lts|-rt|-xanmod)?$' | sort -Vr)

# Listar kernels instalados (apenas principais)
installed_kernels=$(mhwd-kernel -li | grep -vi "running" | grep -vi "kernels" | sed 's|.* ||g' | grep -E '^linux[0-9]+(-lts|-rt|-xanmod)?$')

# Mostrar kernels principais
echo -e "${BLUE}Kernels principais disponíveis:${NC}"
for kernel in $main_kernels; do
    # Verificar status
    if echo "$installed_kernels" | grep -q "^$kernel$"; then
        if [[ "$current_kernel" == *"${kernel//-/}"* ]]; then
            status="${GREEN}[EM USO]${NC}"
        else
            status="${BLUE}[INSTALADO]${NC}"
        fi
    else
        status="${YELLOW}[DISPONÍVEL]${NC}"
    fi

    # Obter versão
    version=$(pacman -Si "$kernel" 2>/dev/null | grep "^Version" | cut -f2 -d: | xargs)

    echo -e "• ${kernel} ${version} ${status}"
done

# Comandos úteis
echo -e "\n${GREEN}Comandos úteis:${NC}"
echo "Instalar: sudo mhwd-kernel -i linux[versão]"
echo "Remover: sudo mhwd-kernel -r linux[versão]"
echo "Exemplo: sudo mhwd-kernel -i linux61"
