#!/usr/bin/env python3
"""
Script para auxiliar na centralização das funções do sistema.

Este script exemplifica como converter funções repetidas para usar o sistema centralizado.
Pode ser usado como guia para continuar a refatoração dos outros módulos.
"""

import os
import logging
import re
import argparse
from pathlib import Path


def configure_logger():
    """Configura o logger para exibir informações sobre o processo"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def scan_module(module_path, logger):
    """Escaneia um módulo para encontrar padrões que precisam ser centralizados"""
    logger.info(f"Escaneando o módulo: {module_path}")

    patterns = {
        'db_connection': r'connection\s*=\s*(?:mysql\.connector\.)?connect\(',
        'cursor_usage': r'cursor\s*=\s*connection\.cursor\(',
        'login_check': r'if\s+[\'"](?:usuario_id|logado)[\'"](?:\s+not)?\s+in\s+session',
        'file_upload': r'(?:secure_filename|werkzeug\.utils\.secure_filename)',
        'permission_check': r'(?:verificar_permissao|verificar_acesso)\s*\([\'"]([^\'"]+)[\'"]\)',
    }

    results = {name: [] for name in patterns}
    files_to_check = []

    # Encontrar todos os arquivos Python
    for root, _, files in os.walk(module_path):
        for file in files:
            if file.endswith('.py'):
                files_to_check.append(os.path.join(root, file))

    # Procurar padrões em cada arquivo
    for file_path in files_to_check:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

                for pattern_name, pattern in patterns.items():
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        line_number = content[:match.start()].count('\n') + 1
                        line = content.splitlines()[line_number - 1]
                        results[pattern_name].append({
                            'file': file_path,
                            'line': line_number,
                            'code': line.strip(),
                            'match': match.group(0)
                        })
        except Exception as e:
            logger.error(f"Erro ao processar o arquivo {file_path}: {str(e)}")

    return results


def suggest_changes(results, logger):
    """Sugere mudanças com base nos resultados do escaneamento"""
    logger.info("Analisando resultados e sugerindo mudanças...")

    suggestions = []

    # Sugestões para conexões de banco de dados
    if results['db_connection']:
        suggestions.append({
            'type': 'database',
            'title': 'Substituir conexões de banco de dados',
            'message': 'Substitua as conexões diretas por funções centralizadas',
            'examples': [
                {
                    'before': 'connection = mysql.connector.connect(\n    host=os.environ.get("DB_HOST"),\n    database=os.environ.get("DB_NAME"),\n    user=os.environ.get("DB_USER"),\n    password=os.environ.get("DB_PASSWORD")\n)',
                    'after': 'from utils.db import get_db_connection\n\n# ...\n\nconnection = get_db_connection()'
                }
            ],
            'files': [item['file'] for item in results['db_connection']]
        })

    # Sugestões para uso de cursores
    if results['cursor_usage']:
        suggestions.append({
            'type': 'database',
            'title': 'Substituir uso direto de cursores',
            'message': 'Use execute_query ou o context manager db_cursor para operações de banco',
            'examples': [
                {
                    'before': 'cursor = connection.cursor(dictionary=True)\ncursor.execute("SELECT * FROM tabela")\nresultados = cursor.fetchall()\ncursor.close()',
                    'after': 'from utils.db import execute_query\n\n# ...\n\nresultados = execute_query("SELECT * FROM tabela")'
                },
                {
                    'before': 'cursor = connection.cursor()\ncursor.execute("UPDATE tabela SET campo = %s WHERE id = %s", (valor, id))\nconnection.commit()',
                    'after': 'from utils.db import update_data\n\n# ...\n\nupdate_data("tabela", {"campo": valor}, "id", id)'
                }
            ],
            'files': [item['file'] for item in results['cursor_usage']]
        })

    # Sugestões para verificações de login
    if results['login_check']:
        suggestions.append({
            'type': 'authentication',
            'title': 'Substituir verificações manuais de login',
            'message': 'Use o decorador login_obrigatorio para proteger rotas',
            'examples': [
                {
                    'before': '@app.route("/rota")\ndef funcao():\n    if "usuario_id" not in session:\n        flash("Faça login para acessar", "warning")\n        return redirect(url_for("login"))\n    # resto da função',
                    'after': 'from utils.auth import login_obrigatorio\n\n# ...\n\n@app.route("/rota")\n@login_obrigatorio\ndef funcao():\n    # resto da função'
                }
            ],
            'files': [item['file'] for item in results['login_check']]
        })

    # Sugestões para uploads de arquivos
    if results['file_upload']:
        suggestions.append({
            'type': 'file_handling',
            'title': 'Centralizar manipulação de uploads',
            'message': 'Use as funções centralizadas para manipular uploads',
            'examples': [
                {
                    'before': 'filename = secure_filename(file.filename)\nfile_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)\nfile.save(file_path)',
                    'after': 'from utils.file_handlers import salvar_arquivo_upload\n\n# ...\n\nfile_path = salvar_arquivo_upload(file, "categoria_arquivo")'
                }
            ],
            'files': [item['file'] for item in results['file_upload']]
        })

    # Sugestões para verificações de permissão
    if results['permission_check']:
        suggestions.append({
            'type': 'permission',
            'title': 'Padronizar verificações de permissão',
            'message': 'Certifique-se de que todas as verificações de permissão usam o mesmo formato',
            'examples': [
                {
                    'before': 'if verificar_permissao("modulo.acao.permissao")',
                    'after': 'from utils.auth import verificar_permissao\n\n# ...\n\nif not verificar_permissao("permissao")'
                }
            ],
            'files': [item['file'] for item in results['permission_check']]
        })

    return suggestions


def print_suggestions(suggestions, logger):
    """Imprime as sugestões em um formato legível"""
    if not suggestions:
        logger.info("Nenhuma sugestão de mudança encontrada.")
        return

    print("\n" + "="*80)
    print(" SUGESTÕES DE CENTRALIZAÇÃO ".center(80, "="))
    print("="*80)

    for i, suggestion in enumerate(suggestions, 1):
        print(f"\n{i}. {suggestion['title']} [{suggestion['type']}]")
        print("-" * 80)
        print(f"{suggestion['message']}")
        print("\nExemplos:")

        for j, example in enumerate(suggestion['examples'], 1):
            print(f"\nExemplo {j}:")
            print("\nAntes:")
            print("```python")
            print(example['before'])
            print("```")

            print("\nDepois:")
            print("```python")
            print(example['after'])
            print("```")

        print("\nArquivos afetados:")
        # Limitar a 5 arquivos para não sobrecarregar
        for file in suggestion['files'][:5]:
            print(f"- {file}")

        if len(suggestion['files']) > 5:
            print(f"... e mais {len(suggestion['files']) - 5} arquivo(s)")

    print("\n" + "="*80)
    print(" PASSO A PASSO PARA CENTRALIZAÇÃO ".center(80, "="))
    print("="*80)
    print("""
1. Inicie pelos módulos mais simples e com menos dependências
2. Para cada arquivo:
   a. Atualize os imports para incluir as funções centralizadas
   b. Substitua as conexões de banco por chamadas a get_db_connection()
   c. Substitua queries SQL diretas por execute_query(), get_single_result(), etc.
   d. Adicione os decoradores @login_obrigatorio e @admin_obrigatorio nas rotas
   e. Substitua verificações manuais de login/permissão pelas funções centralizadas
   f. Substitua manipulação direta de arquivos pelas funções centralizadas
3. Teste cada módulo após as alterações para garantir que tudo funcione corretamente
4. Documente as mudanças feitas e qualquer problema encontrado
""")


def main():
    parser = argparse.ArgumentParser(
        description="Auxiliar na centralização de funções do sistema")
    parser.add_argument('--module', '-m', type=str, required=True,
                        help="Caminho para o módulo a ser analisado (ex: modulos/solicitacoes)")

    args = parser.parse_args()

    logger = configure_logger()

    if not os.path.exists(args.module):
        logger.error(f"Módulo não encontrado: {args.module}")
        return 1

    results = scan_module(args.module, logger)
    suggestions = suggest_changes(results, logger)
    print_suggestions(suggestions, logger)

    return 0


if __name__ == "__main__":
    exit(main())
