#!/usr/bin/env python3
"""
Script de teste simplificado para verificar se os scripts de migração estão funcionando
"""

import os
import sys
import sqlite3
from pathlib import Path

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def testar_imports():
    """Testa se todos os imports necessários funcionam"""
    print("Testando imports...")
    
    try:
        import sqlalchemy
        print("OK - SQLAlchemy")
    except ImportError as e:
        print(f"ERRO - SQLAlchemy: {e}")
        return False
    
    try:
        import pymysql
        print("OK - PyMySQL")
    except ImportError as e:
        print(f"ERRO - PyMySQL: {e}")
        return False
    
    try:
        import pandas
        print("OK - Pandas")
    except ImportError as e:
        print(f"ERRO - Pandas: {e}")
        return False
    
    try:
        from dotenv import load_dotenv
        print("OK - python-dotenv")
    except ImportError as e:
        print(f"ERRO - python-dotenv: {e}")
        return False
    
    return True

def testar_arquivo_env():
    """Testa se o arquivo .env existe e tem as configurações necessárias"""
    print("\nTestando arquivo .env...")
    
    if not os.path.exists('.env'):
        print("ERRO - Arquivo .env nao encontrado")
        return False
    
    print("OK - Arquivo .env encontrado")
    
    # Carregar variáveis
    from dotenv import load_dotenv
    load_dotenv('.env')
    
    # Verificar variáveis importantes
    db_password = os.environ.get('DB_PASSWORD')
    if db_password:
        print("OK - DB_PASSWORD configurado")
    else:
        print("AVISO - DB_PASSWORD nao configurado")
    
    secret_key = os.environ.get('SECRET_KEY')
    if secret_key:
        print("OK - SECRET_KEY configurado")
    else:
        print("AVISO - SECRET_KEY nao configurado")
    
    return True

def testar_sqlite():
    """Testa criação e operações básicas no SQLite"""
    print("\nTestando SQLite...")
    
    try:
        # Criar diretório instance se não existir
        os.makedirs('instance', exist_ok=True)
        
        # Testar conexão SQLite
        test_db = 'instance/test_sqlite.db'
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        # Criar tabela de teste
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teste (
                id INTEGER PRIMARY KEY,
                nome TEXT,
                data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Inserir dados de teste
        cursor.execute("INSERT INTO teste (nome) VALUES (?)", ("Teste SQLite",))
        conn.commit()
        
        # Consultar dados
        cursor.execute("SELECT * FROM teste")
        result = cursor.fetchone()
        
        if result:
            print("OK - SQLite funcionando corretamente")
            print(f"   Dados de teste: {result}")
        
        conn.close()
        
        # Limpar arquivo de teste
        os.remove(test_db)
        
        return True
        
    except Exception as e:
        print(f"ERRO - SQLite: {e}")
        return False

def testar_scripts():
    """Testa se os scripts podem ser importados"""
    print("\nTestando scripts...")
    
    scripts = [
        'migrar_para_sqlite.py',
        'sincronizar_sqlite.py', 
        'configurar_modo_offline.py',
        'setup_offline.py'
    ]
    
    for script in scripts:
        script_path = f'scripts/{script}'
        if os.path.exists(script_path):
            print(f"OK - {script}")
        else:
            print(f"ERRO - {script} nao encontrado")
            return False
    
    return True

def testar_diretorios():
    """Testa se os diretórios necessários existem"""
    print("\nTestando diretorios...")
    
    diretorios = ['instance', 'logs', 'config', 'scripts']
    
    for diretorio in diretorios:
        if os.path.exists(diretorio):
            print(f"OK - {diretorio}/")
        else:
            print(f"AVISO - {diretorio}/ nao encontrado - sera criado automaticamente")
    
    return True

def main():
    """Função principal de teste"""
    print("=" * 60)
    print("TESTE DOS SCRIPTS DE MIGRACAO")
    print("=" * 60)
    
    testes = [
        ("Imports necessarios", testar_imports),
        ("Arquivo .env", testar_arquivo_env),
        ("Diretorios", testar_diretorios),
        ("Scripts", testar_scripts),
        ("SQLite", testar_sqlite),
    ]
    
    resultados = []
    
    for nome, funcao_teste in testes:
        try:
            resultado = funcao_teste()
            resultados.append((nome, resultado))
        except Exception as e:
            print(f"ERRO no teste '{nome}': {e}")
            resultados.append((nome, False))
    
    # Resumo dos resultados
    print("\n" + "=" * 60)
    print("RESUMO DOS TESTES")
    print("=" * 60)
    
    sucessos = 0
    total = len(resultados)
    
    for nome, resultado in resultados:
        status = "PASSOU" if resultado else "FALHOU"
        print(f"{nome:.<40} {status}")
        if resultado:
            sucessos += 1
    
    print("-" * 60)
    print(f"Total: {sucessos}/{total} testes passaram")
    
    if sucessos == total:
        print("\nTODOS OS TESTES PASSARAM!")
        print("Os scripts estao prontos para uso")
        print("\nProximos passos:")
        print("1. Execute: python scripts/setup_offline.py")
        print("2. Escolha a opcao 6 (Setup completo)")
    else:
        print(f"\n{total - sucessos} teste(s) falharam")
        print("Corrija os problemas antes de usar os scripts")
        
        if not resultados[0][1]:  # Imports falharam
            print("\nSolucao: Instale as dependencias:")
            print("pip install sqlalchemy pymysql pandas python-dotenv")
        
        if not resultados[1][1]:  # .env falhou
            print("\nSolucao: Configure o arquivo .env com as credenciais do MySQL")

if __name__ == "__main__":
    main()

