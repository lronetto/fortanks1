"""
Script para encontrar blocos try sem except ou finally em um arquivo Python
"""
import re
import sys


def find_try_without_except(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    line_number = 0
    in_try_block = False
    try_line = 0
    try_blocks = []
    indent_level = 0

    for line in lines:
        line_number += 1
        stripped = line.strip()

        # Ignorar comentários e linhas vazias
        if not stripped or stripped.startswith('#'):
            continue

        # Detectar nível de indentação
        current_indent = len(line) - len(line.lstrip())

        # Encontrar início de try
        if stripped == 'try:':
            in_try_block = True
            try_line = line_number
            indent_level = current_indent
            continue

        # Se estamos em um bloco try, procure por except ou finally
        if in_try_block:
            # Se encontrarmos uma linha com menor indentação que o try,
            # significa que o bloco terminou sem except ou finally
            if current_indent <= indent_level and stripped and not stripped.startswith('except') and not stripped.startswith('finally'):
                try_blocks.append((try_line, line_number - 1))
                in_try_block = False

            # Se encontrarmos except ou finally, o bloco try está completo
            elif stripped.startswith('except') or stripped.startswith('finally'):
                in_try_block = False

    # Se ainda estivermos em um bloco try no final do arquivo
    if in_try_block:
        try_blocks.append((try_line, line_number))

    return try_blocks


def show_context(filename, try_blocks, context_lines=2):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    results = []
    for start, end in try_blocks:
        # Definir o intervalo de linhas para mostrar
        context_start = max(1, start - context_lines)
        context_end = min(len(lines), end + context_lines)

        # Coletar linhas do contexto
        context = []
        for i in range(context_start - 1, context_end):
            line_num = i + 1
            prefix = '>>> ' if line_num == start else '    '
            context.append(f"{prefix}{line_num}: {lines[i].rstrip()}")

        results.append((start, end, '\n'.join(context)))

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python find_try_errors.py <arquivo>")
        sys.exit(1)

    filename = sys.argv[1]
    try_blocks = find_try_without_except(filename)

    if try_blocks:
        print(f"Encontrados {len(try_blocks)} blocos try sem except/finally:")
        contexts = show_context(filename, try_blocks)

        for i, (start, end, context) in enumerate(contexts, 1):
            print(f"\nProblema #{i} - Linhas {start}-{end}:")
            print(context)
            print("-" * 50)
    else:
        print("Nenhum bloco try sem except/finally encontrado.")
