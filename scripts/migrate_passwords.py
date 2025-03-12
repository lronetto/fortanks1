#!/usr/bin/env python3
"""
Script para migração de senhas do formato antigo (base64) para o novo formato seguro (Fernet).

Este script deve ser executado após a atualização do sistema para o novo método de criptografia.
Ele identifica todas as senhas armazenadas no banco de dados e as recriptografa usando o novo método.
"""

from utils.crypto import recrypt_password
from utils.db import execute_query, update_data
import os
import logging
import sys
from pathlib import Path
import argparse

# Adicionar o diretório raiz ao PATH para importar os módulos do sistema
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importar as funções de banco de dados e criptografia

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def migrate_passwords(dry_run=False):
    """
    Migra todas as senhas do formato antigo para o novo formato.

    Args:
        dry_run (bool): Se True, apenas simula a migração sem fazer alterações

    Returns:
        tuple: (total_processado, total_migrado, total_erros)
    """
    logger.info("Iniciando migração de senhas...")

    # Buscar todas as credenciais no banco de dados
    try:
        credenciais = execute_query("""
            SELECT 
                configuracao_id, usuario, senha_encriptada
            FROM 
                erp_credenciais
            WHERE 
                senha_encriptada IS NOT NULL AND senha_encriptada != ''
        """)

        if not credenciais:
            logger.info("Nenhuma credencial encontrada para migração.")
            return (0, 0, 0)

        logger.info(
            f"Encontradas {len(credenciais)} credenciais para processar.")

        total_processado = 0
        total_migrado = 0
        total_erros = 0

        # Processar cada credencial
        for credencial in credenciais:
            total_processado += 1
            config_id = credencial['configuracao_id']
            usuario = credencial['usuario']
            senha_antiga = credencial['senha_encriptada']

            try:
                # Tentar recriptografar a senha
                senha_nova = recrypt_password(senha_antiga)

                # Verificar se a senha foi realmente alterada
                if senha_nova != senha_antiga:
                    logger.info(
                        f"Migração necessária para credencial {config_id} (usuário {usuario})")

                    if not dry_run:
                        # Atualizar a senha no banco de dados
                        update_data(
                            'erp_credenciais',
                            {'senha_encriptada': senha_nova},
                            'configuracao_id',
                            config_id
                        )
                        logger.info(
                            f"✓ Credencial {config_id} migrada com sucesso.")
                    else:
                        logger.info(
                            f"[DRY RUN] A credencial {config_id} seria migrada.")

                    total_migrado += 1
                else:
                    logger.info(
                        f"A credencial {config_id} já está no formato correto.")

            except Exception as e:
                logger.error(
                    f"Erro ao migrar credencial {config_id}: {str(e)}")
                total_erros += 1

        return (total_processado, total_migrado, total_erros)

    except Exception as e:
        logger.error(f"Erro ao buscar credenciais: {str(e)}")
        return (0, 0, 1)


def main():
    """Função principal do script"""
    parser = argparse.ArgumentParser(
        description="Migra senhas do formato antigo para o novo formato seguro")
    parser.add_argument('--dry-run', action='store_true',
                        help="Executa uma simulação sem fazer alterações no banco de dados")

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Executando em modo de simulação (dry run)")

    # Executar a migração
    total_processado, total_migrado, total_erros = migrate_passwords(
        args.dry_run)

    # Mostrar resultados
    print("\n" + "="*60)
    print(" RESULTADO DA MIGRAÇÃO ".center(60, "="))
    print("="*60)
    print(f"Total de credenciais processadas: {total_processado}")
    print(f"Total de credenciais migradas:    {total_migrado}")
    print(f"Total de erros:                   {total_erros}")
    print("="*60)

    if args.dry_run:
        print("\nEste foi apenas um teste. Execute sem a opção --dry-run para aplicar as mudanças.")

    if total_erros > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
