#!/usr/bin/env python3
"""
Script para verificar a consistência do sistema após a centralização.

Este script analisa todos os módulos do sistema e identifica quais ainda
não foram atualizados para usar as funções centralizadas.
"""

import os
import sys
import logging
import argparse
import re
from pathlib import Path
from tabulate import tabulate
from termcolor import colored


# Configuração do logger
def setup_logger():
    """Configura o logger para o script"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


# Padrões a serem procurados em arquivos
PATTERNS = {
    'database': {
        'old': [
            r'connection\s*=\s*(?:mysql\.connector\.)?connect\(',
            r'cursor\s*=\s*connection\.cursor\(',
            r'connection\.commit\(\)',
            r'cursor\.execute\(.*\)',
            r'cursor\.fetchall\(\)',
            r'cursor\.fetchone\(\)',
        ],
        'new': [
            r'from\s+utils\.db\s+import',
            r'get_db_connection\(\)',
            r'execute_query\(',
            r'get_single_result\(',
            r'insert_data\(',
            r'update_data\(',
        ],
    },
    'authentication': {
        'old': [
            r'if\s+[\'"](?:usuario_id|logado)[\'"](?:\s+not)?\s+in\s+session',
            r'session\[[\'"]id_usuario[\'"]\]',
            r'redirect\(url_for\([\'"]login[\'"]\)\)',
        ],
        'new': [
            r'from\s+utils\.auth\s+import',
            r'@login_obrigatorio',
            r'@admin_obrigatorio',
            r'verificar_permissao\(',
            r'get_user_id\(\)',
        ],
    },
    'file_handling': {
        'old': [
            r'(?:secure_filename|werkzeug\.utils\.secure_filename)',
            r'os\.path\.join\([^,]+,\s*[\'"][^\'"]+[\'"]\)',
            r'file\.save\(',
        ],
        'new': [
            r'from\s+utils\.file_handlers\s+import',
            r'salvar_arquivo_upload\(',
            r'processar_arquivo_excel\(',
        ],
    },
}


def scan_directory(directory, logger):
    """
    Escaneia todos os arquivos Python em um diretório para identificar padrões de código
    """
    logger.info(f"Analisando diretório: {directory}")

    results = {
        'modules': {},
        'summary': {
            'total_files': 0,
            'updated_files': 0,
            'partially_updated_files': 0,
            'non_updated_files': 0,
        }
    }

    # Encontrar todos os módulos (subdiretórios)
    modules = [d for d in os.listdir(directory) if os.path.isdir(
        os.path.join(directory, d)) and not d.startswith('.') and d != '__pycache__']

    for module in modules:
        module_path = os.path.join(directory, module)
        logger.info(f"Processando módulo: {module}")

        module_results = {
            'files': {},
            'summary': {
                'total_files': 0,
                'updated_files': 0,
                'partially_updated_files': 0,
                'non_updated_files': 0,
                'update_percentage': 0,
            }
        }

        # Encontrar todos os arquivos Python no módulo
        python_files = []
        for root, _, files in os.walk(module_path):
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))

        module_results['summary']['total_files'] = len(python_files)
        results['summary']['total_files'] += len(python_files)

        # Analisar cada arquivo Python
        for file_path in python_files:
            file_rel_path = os.path.relpath(file_path, directory)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                file_results = {
                    'categories': {},
                    'status': 'unknown',
                }

                # Verificar cada categoria de padrões
                for category, patterns in PATTERNS.items():
                    old_patterns_found = []
                    new_patterns_found = []

                    # Verificar padrões antigos
                    for pattern in patterns['old']:
                        if re.search(pattern, content):
                            old_patterns_found.append(pattern)

                    # Verificar padrões novos
                    for pattern in patterns['new']:
                        if re.search(pattern, content):
                            new_patterns_found.append(pattern)

                    # Determinar status para esta categoria
                    if old_patterns_found and not new_patterns_found:
                        category_status = 'not_updated'
                    elif not old_patterns_found and new_patterns_found:
                        category_status = 'updated'
                    elif old_patterns_found and new_patterns_found:
                        category_status = 'partially_updated'
                    else:
                        category_status = 'not_applicable'

                    file_results['categories'][category] = {
                        'status': category_status,
                        'old_patterns': old_patterns_found,
                        'new_patterns': new_patterns_found,
                    }

                # Determinar status geral do arquivo
                statuses = [info['status'] for info in file_results['categories'].values()
                            if info['status'] != 'not_applicable']

                if not statuses:
                    file_results['status'] = 'not_applicable'
                elif all(status == 'updated' for status in statuses):
                    file_results['status'] = 'updated'
                    module_results['summary']['updated_files'] += 1
                    results['summary']['updated_files'] += 1
                elif all(status == 'not_updated' for status in statuses):
                    file_results['status'] = 'not_updated'
                    module_results['summary']['non_updated_files'] += 1
                    results['summary']['non_updated_files'] += 1
                else:
                    file_results['status'] = 'partially_updated'
                    module_results['summary']['partially_updated_files'] += 1
                    results['summary']['partially_updated_files'] += 1

                module_results['files'][file_rel_path] = file_results

            except Exception as e:
                logger.error(
                    f"Erro ao processar o arquivo {file_path}: {str(e)}")

        # Calcular percentual de atualização
        if module_results['summary']['total_files'] > 0:
            updated = module_results['summary']['updated_files']
            partially = module_results['summary']['partially_updated_files'] * 0.5
            total = module_results['summary']['total_files']

            module_results['summary']['update_percentage'] = (
                updated + partially) / total * 100

        results['modules'][module] = module_results

    return results


def print_report(results, verbose=False):
    """
    Imprime um relatório com os resultados da análise
    """
    print("\n" + "="*80)
    print(" RELATÓRIO DE CONSISTÊNCIA DO SISTEMA ".center(80, "="))
    print("="*80 + "\n")

    # Tabela de resumo dos módulos
    module_data = []
    for module_name, module_info in results['modules'].items():
        summary = module_info['summary']
        percentage = summary['update_percentage']

        # Colorir com base no percentual
        if percentage >= 90:
            status = colored("Bom", "green")
        elif percentage >= 50:
            status = colored("Parcial", "yellow")
        else:
            status = colored("Pendente", "red")

        module_data.append([
            module_name,
            summary['total_files'],
            summary['updated_files'],
            summary['partially_updated_files'],
            summary['non_updated_files'],
            f"{percentage:.1f}%",
            status
        ])

    # Ordenar por percentual de conclusão (decrescente)
    module_data.sort(key=lambda x: float(x[5].rstrip('%')), reverse=True)

    print(tabulate(
        module_data,
        headers=["Módulo", "Total", "Atualizados",
                 "Parcial", "Pendentes", "Progresso", "Status"],
        tablefmt="grid"
    ))

    # Resumo geral
    total = results['summary']['total_files']
    updated = results['summary']['updated_files']
    partially = results['summary']['partially_updated_files']
    non_updated = results['summary']['non_updated_files']

    if total > 0:
        overall_percentage = (updated + partially * 0.5) / total * 100
    else:
        overall_percentage = 0

    print("\n" + "-"*80)
    print(" RESUMO GERAL ".center(80, "-"))
    print("-"*80)
    print(f"Total de arquivos: {total}")
    print(
        f"Arquivos atualizados: {updated} ({updated/total*100:.1f}% se aplicável)")
    print(
        f"Arquivos parcialmente atualizados: {partially} ({partially/total*100:.1f}% se aplicável)")
    print(
        f"Arquivos pendentes: {non_updated} ({non_updated/total*100:.1f}% se aplicável)")
    print(f"Progresso geral: {overall_percentage:.1f}%")

    # Status geral
    if overall_percentage >= 90:
        print(
            colored("\nStatus geral: BOM - A maioria dos arquivos foi atualizada", "green"))
    elif overall_percentage >= 50:
        print(colored(
            "\nStatus geral: PARCIAL - Muitos arquivos ainda precisam ser atualizados", "yellow"))
    else:
        print(colored(
            "\nStatus geral: PENDENTE - A maioria dos arquivos precisa ser atualizada", "red"))

    # Detalhes por arquivo, se requisitado
    if verbose:
        print("\n" + "="*80)
        print(" DETALHES POR ARQUIVO ".center(80, "="))
        print("="*80 + "\n")

        for module_name, module_info in results['modules'].items():
            print(f"\nMódulo: {module_name}")
            print("-" * 80)

            # Arquivos não atualizados
            non_updated_files = [f for f, info in module_info['files'].items()
                                 if info['status'] == 'not_updated']
            if non_updated_files:
                print(
                    colored(f"\nArquivos pendentes ({len(non_updated_files)}):", "red"))
                for file in non_updated_files:
                    print(f"  - {file}")

            # Arquivos parcialmente atualizados
            partially_files = [f for f, info in module_info['files'].items()
                               if info['status'] == 'partially_updated']
            if partially_files:
                print(colored(
                    f"\nArquivos parcialmente atualizados ({len(partially_files)}):", "yellow"))
                for file in partially_files:
                    file_info = module_info['files'][file]
                    print(f"  - {file}")

                    # Mostrar categorias com problemas
                    for category, cat_info in file_info['categories'].items():
                        if cat_info['status'] == 'not_updated':
                            print(f"    * {category}: Não atualizado")
                        elif cat_info['status'] == 'partially_updated':
                            print(f"    * {category}: Parcialmente atualizado")

            # Arquivos atualizados (opcional, pode ficar muito extenso)
            if verbose > 1:
                updated_files = [f for f, info in module_info['files'].items()
                                 if info['status'] == 'updated']
                if updated_files:
                    print(
                        colored(f"\nArquivos atualizados ({len(updated_files)}):", "green"))
                    for file in updated_files:
                        print(f"  - {file}")


def main():
    parser = argparse.ArgumentParser(
        description="Verificar a consistência do sistema após a centralização")
    parser.add_argument('--directory', '-d', type=str, default='modulos',
                        help="Diretório base para análise (padrão: 'modulos')")
    parser.add_argument('--verbose', '-v', action='count', default=0,
                        help="Exibir informações detalhadas (-v para detalhes básicos, -vv para todos os detalhes)")

    try:
        import tabulate
        import termcolor
    except ImportError:
        print("Este script requer os pacotes 'tabulate' e 'termcolor'.")
        print("Instale-os com: pip install tabulate termcolor")
        return 1

    args = parser.parse_args()
    logger = setup_logger()

    # Verificar se o diretório existe
    if not os.path.isdir(args.directory):
        logger.error(f"O diretório {args.directory} não existe.")
        return 1

    # Escanear os módulos
    results = scan_directory(args.directory, logger)

    # Imprimir relatório
    print_report(results, args.verbose)

    return 0


if __name__ == "__main__":
    sys.exit(main())
