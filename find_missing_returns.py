"""
Script para detectar funções de view do Flask que não retornam valores
em todos os caminhos de execução possíveis.
"""
import re
import sys
import ast


def extract_flask_routes(file_path):
    """Extrai todas as rotas Flask de um arquivo Python."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Encontrar todas as definições de rotas
    route_pattern = r'@\w+\.route\([\'"].*?[\'"](,.*?)?\)\s+def\s+(\w+)\s*\(.*?\):'
    routes = re.finditer(route_pattern, content, re.DOTALL)

    route_info = []
    for match in routes:
        func_name = match.group(2)
        # Encontrar a posição inicial da função
        start_pos = match.start()
        route_info.append((func_name, start_pos))

    return route_info


def check_missing_returns(file_path):
    """
    Verifica funções de view do Flask que podem não retornar 
    valores em todos os caminhos de execução.
    """
    print(f"Analisando arquivo: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            source_code = file.read()

        # Extrair informações sobre as rotas
        route_info = extract_flask_routes(file_path)

        if not route_info:
            print("Nenhuma rota Flask encontrada no arquivo.")
            return

        # Analisar o código para verificar retornos
        tree = ast.parse(source_code)

        problematic_views = []

        # Função para verificar se um nó AST tem um return
        def has_return(node):
            if isinstance(node, ast.Return):
                return True

            # Verificar recursivamente em nós filhos
            for child in ast.iter_child_nodes(node):
                if has_return(child):
                    return True

            return False

        # Verificar cada função de view
        for func_def in ast.walk(tree):
            if isinstance(func_def, ast.FunctionDef):
                # Verificar se é uma função de rota
                if any(func_def.name == name for name, _ in route_info):
                    # Verificar se a função tem um caminho que não retorna valor
                    has_explicit_return = False

                    # Verificar o corpo da função
                    for stmt in func_def.body:
                        if isinstance(stmt, ast.Return) or has_return(stmt):
                            has_explicit_return = True
                            break

                    # Se não tiver um return explícito no nível mais alto
                    if not has_explicit_return:
                        problematic_views.append(func_def.name)

        if problematic_views:
            print("\nPossíveis funções view sem return para todos os caminhos:")
            for view in problematic_views:
                print(f"  - {view}")
        else:
            print("\nTodas as funções view parecem ter retornos adequados.")

    except Exception as e:
        print(f"Erro ao analisar o arquivo: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python find_missing_returns.py <caminho_do_arquivo>")
        sys.exit(1)

    check_missing_returns(sys.argv[1])
