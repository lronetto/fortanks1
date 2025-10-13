#!/usr/bin/env python3
"""
Script principal para configurar o sistema Fortanks para funcionamento offline
Orquestra todo o processo de migração e configuração
"""

import os
import sys
import subprocess
from datetime import datetime

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def executar_script(script_path, descricao):
    """Executa um script Python e retorna o resultado"""
    print(f"\n🔄 {descricao}...")
    print("-" * 50)
    
    try:
        result = subprocess.run([sys.executable, script_path], 
                              capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(script_path)))
        
        if result.returncode == 0:
            print(f"✅ {descricao} concluído com sucesso!")
            if result.stdout:
                print("Saída:", result.stdout)
        else:
            print(f"❌ {descricao} falhou!")
            if result.stderr:
                print("Erro:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Erro ao executar {descricao}: {str(e)}")
        return False
    
    return True

def verificar_dependencias():
    """Verifica se as dependências necessárias estão instaladas"""
    print("🔍 Verificando dependências...")
    
    dependencias = [
        'sqlalchemy',
        'pymysql',
        'pandas',
        'python-dotenv'
    ]
    
    dependencias_faltando = []
    
    for dep in dependencias:
        try:
            __import__(dep.replace('-', '_'))
            print(f"✅ {dep}")
        except ImportError:
            print(f"❌ {dep} - NÃO INSTALADO")
            dependencias_faltando.append(dep)
    
    if dependencias_faltando:
        print(f"\n⚠️  Dependências faltando: {', '.join(dependencias_faltando)}")
        print("Execute: pip install " + " ".join(dependencias_faltando))
        return False
    
    print("✅ Todas as dependências estão instaladas!")
    return True

def verificar_arquivo_env():
    """Verifica se o arquivo .env existe"""
    if os.path.exists('.env'):
        print("✅ Arquivo .env encontrado")
        return True
    else:
        print("❌ Arquivo .env não encontrado")
        print("⚠️  Certifique-se de que o arquivo .env está configurado com as credenciais do MySQL")
        return False

def criar_diretorio_logs():
    """Cria o diretório de logs se não existir"""
    if not os.path.exists('logs'):
        os.makedirs('logs')
        print("✅ Diretório de logs criado")
    else:
        print("✅ Diretório de logs já existe")

def main():
    """Função principal"""
    print("=" * 60)
    print("🚀 SETUP OFFLINE - SISTEMA FORTANKS")
    print("=" * 60)
    print("Este script irá configurar o sistema para funcionamento offline")
    print("usando SQLite local em vez do MySQL remoto.")
    print()
    
    # Verificações iniciais
    print("📋 VERIFICAÇÕES INICIAIS")
    print("-" * 30)
    
    if not verificar_dependencias():
        print("\n❌ Instale as dependências faltando antes de continuar.")
        return
    
    if not verificar_arquivo_env():
        print("\n❌ Configure o arquivo .env antes de continuar.")
        return
    
    criar_diretorio_logs()
    
    print("\n✅ Todas as verificações passaram!")
    
    # Menu principal
    while True:
        print("\n" + "=" * 60)
        print("📋 MENU PRINCIPAL")
        print("=" * 60)
        print("1. 🔄 Migração completa (MySQL -> SQLite)")
        print("2. 🔄 Sincronização incremental")
        print("3. ⚙️  Configurar modo offline")
        print("4. ⚙️  Configurar modo online")
        print("5. 📊 Verificar status do banco SQLite")
        print("6. 🚀 Setup completo (migração + configuração offline)")
        print("7. ❌ Sair")
        print()
        
        opcao = input("Digite sua opção (1-7): ").strip()
        
        if opcao == '1':
            print("\n🔄 INICIANDO MIGRAÇÃO COMPLETA")
            print("=" * 40)
            sucesso = executar_script('scripts/migrar_para_sqlite.py', 'Migração MySQL -> SQLite')
            if sucesso:
                print("\n✅ Migração concluída! Agora você pode configurar o modo offline.")
            else:
                print("\n❌ Migração falhou. Verifique os logs para mais detalhes.")
        
        elif opcao == '2':
            print("\n🔄 INICIANDO SINCRONIZAÇÃO INCREMENTAL")
            print("=" * 40)
            sucesso = executar_script('scripts/sincronizar_sqlite.py', 'Sincronização incremental')
            if sucesso:
                print("\n✅ Sincronização concluída!")
            else:
                print("\n❌ Sincronização falhou. Verifique os logs para mais detalhes.")
        
        elif opcao == '3':
            print("\n⚙️  CONFIGURANDO MODO OFFLINE")
            print("=" * 40)
            sucesso = executar_script('scripts/configurar_modo_offline.py', 'Configuração modo offline')
            if sucesso:
                print("\n✅ Sistema configurado para modo offline!")
                print("🔄 Reinicie a aplicação para aplicar as mudanças.")
        
        elif opcao == '4':
            print("\n⚙️  CONFIGURANDO MODO ONLINE")
            print("=" * 40)
            sucesso = executar_script('scripts/configurar_modo_offline.py', 'Configuração modo online')
            if sucesso:
                print("\n✅ Sistema configurado para modo online!")
                print("🔄 Reinicie a aplicação para aplicar as mudanças.")
        
        elif opcao == '5':
            print("\n📊 VERIFICANDO STATUS DO BANCO SQLITE")
            print("=" * 40)
            sqlite_path = 'instance/fortanks_offline.db'
            if os.path.exists(sqlite_path):
                size = os.path.getsize(sqlite_path)
                mod_time = datetime.fromtimestamp(os.path.getmtime(sqlite_path))
                print(f"✅ Banco SQLite encontrado:")
                print(f"   📁 Local: {sqlite_path}")
                print(f"   📏 Tamanho: {size:,} bytes ({size/1024/1024:.2f} MB)")
                print(f"   🕒 Modificado: {mod_time.strftime('%d/%m/%Y %H:%M:%S')}")
            else:
                print(f"❌ Banco SQLite não encontrado: {sqlite_path}")
                print("   Execute primeiro a migração completa (opção 1)")
        
        elif opcao == '6':
            print("\n🚀 INICIANDO SETUP COMPLETO")
            print("=" * 40)
            print("Este processo irá:")
            print("1. Migrar todos os dados do MySQL para SQLite")
            print("2. Configurar o sistema para modo offline")
            print()
            
            confirmacao = input("Deseja continuar? (s/N): ").lower().strip()
            if confirmacao in ['s', 'sim', 'y', 'yes']:
                print("\n🔄 Executando migração completa...")
                if executar_script('scripts/migrar_para_sqlite.py', 'Migração MySQL -> SQLite'):
                    print("\n⚙️  Configurando modo offline...")
                    if executar_script('scripts/configurar_modo_offline.py', 'Configuração modo offline'):
                        print("\n🎉 SETUP COMPLETO CONCLUÍDO!")
                        print("✅ Sistema configurado para funcionamento offline")
                        print("🔄 Reinicie a aplicação para aplicar as mudanças")
                        print("📁 Banco SQLite: instance/fortanks_offline.db")
                    else:
                        print("\n❌ Falha na configuração do modo offline")
                else:
                    print("\n❌ Falha na migração dos dados")
            else:
                print("Setup completo cancelado.")
        
        elif opcao == '7':
            print("\n👋 Saindo...")
            break
        
        else:
            print("\n❌ Opção inválida! Tente novamente.")
        
        input("\nPressione Enter para continuar...")

if __name__ == "__main__":
    main()


