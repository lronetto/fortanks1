"""
Script simples para verificar problemas comuns em arquivos Python:
- Blocos 'try' sem 'except' ou 'finally'
- Funções de rota que terminam sem um 'return'
"""
import re
import sys


def check_file(file_path):
    """
    Verifica problemas comuns em um arquivo Python.
    """
    print(f"Analisando arquivo: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        # Verificar blocos try sem except/finally
        check_try_blocks(lines, file_path)

        # Verificar funções de rota sem return
        check_route_returns(lines, file_path)

    except Exception as e:
        print(f"Erro ao analisar o arquivo: {str(e)}")


def check_try_blocks(lines, file_path):
    """
    Verifica blocos try sem except/finally.
    """
    in_try_block = False
    try_line_num = 0
    try_blocks_without_except = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detecta início de bloco try
        if re.match(r'^try\s*:', stripped):
            in_try_block = True
            try_line_num = i

        # Detecta except ou finally
        elif in_try_block and (re.match(r'^except\s*.*:', stripped) or
                               re.match(r'^finally\s*:', stripped)):
            in_try_block = False

        # Se encontrar outro marcador de bloco depois de try sem except/finally
        elif in_try_block and re.match(r'^(def|class|if|else|elif|while|for|with|try)\s*.*:', stripped):
            try_blocks_without_except.append((try_line_num, i-1))
            in_try_block = False

    if in_try_block:  # Se o arquivo terminar com um bloco try aberto
        try_blocks_without_except.append((try_line_num, len(lines)))

    if try_blocks_without_except:
        print("\nBlocos try sem except/finally encontrados:")
        for start, end in try_blocks_without_except:
            print(f"  - Linhas {start}-{end}")

        # Mostrar conteúdo do primeiro bloco problemático como exemplo
        if try_blocks_without_except:
            start, end = try_blocks_without_except[0]
            print("\nExemplo do primeiro bloco problemático:")
            for i in range(max(0, start-1), min(end+1, len(lines))):
                print(f"{i+1}: {lines[i].rstrip()}")
    else:
        print("\nNenhum bloco try sem except/finally encontrado.")


def check_route_returns(lines, file_path):
    """
    Verifica funções de rota que podem não ter return em todos os caminhos.
    """
    route_funcs = []
    func_start = 0
    in_function = False
    current_func = ""
    indent_level = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detecta decorador de rota
        if "@" in stripped and ".route" in stripped:
            # Próxima linha deve ser a definição da função
            if i+1 < len(lines) and "def " in lines[i+1]:
                func_line = lines[i+1]
                func_match = re.search(r'def\s+(\w+)\s*\(', func_line)
                if func_match:
                    current_func = func_match.group(1)
                    func_start = i
                    in_function = True
                    # Determinar nível de indentação da função
                    indent_match = re.match(r'^(\s*)', func_line)
                    if indent_match:
                        indent_level = len(indent_match.group(1))

        # Detecta final de função atual
        elif in_function:
            # Se a linha não está vazia e tem indentação menor ou igual à função
            if stripped and (len(line) - len(line.lstrip())) <= indent_level:
                # Verificar se a função tem um return
                has_return = False
                for j in range(func_start, i):
                    if "return " in lines[j]:
                        has_return = True
                        break

                if not has_return:
                    route_funcs.append((current_func, func_start+1, i))

                in_function = False

    # Verificar a última função se ainda estivermos processando uma
    if in_function:
        has_return = False
        for j in range(func_start, len(lines)):
            if "return " in lines[j]:
                has_return = True
                break

        if not has_return:
            route_funcs.append((current_func, func_start+1, len(lines)))

    if route_funcs:
        print("\nPossíveis funções de rota sem return explícito:")
        for func, start, end in route_funcs:
            print(f"  - {func} (linhas {start}-{end})")
    else:
        print("\nTodas as funções de rota parecem ter returns adequados.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python find_simple_errors.py <caminho_do_arquivo>")
        sys.exit(1)

    check_file(sys.argv[1])
