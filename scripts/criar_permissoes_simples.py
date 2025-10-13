"""
Script simples para criar o sistema de permissões
"""
import sqlite3
import os

def criar_tabelas_permissoes():
    """Cria as tabelas de permissões no banco SQLite"""
    
    # Caminho para o banco de dados
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'fortanks.db')
    
    if not os.path.exists(db_path):
        print(f"Banco de dados não encontrado em: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Criar tabela de módulos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS modulos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome VARCHAR(100) NOT NULL UNIQUE,
                descricao TEXT,
                icone VARCHAR(50),
                url VARCHAR(200),
                ordem INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'Ativo',
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Criar tabela de permissões
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS permissoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                modulo_id INTEGER NOT NULL,
                usuario_id INTEGER,
                departamento_id INTEGER,
                cargo VARCHAR(50),
                tipo_permissao VARCHAR(20) NOT NULL,
                pode_visualizar BOOLEAN DEFAULT 1,
                pode_criar BOOLEAN DEFAULT 0,
                pode_editar BOOLEAN DEFAULT 0,
                pode_excluir BOOLEAN DEFAULT 0,
                pode_exportar BOOLEAN DEFAULT 0,
                status VARCHAR(20) DEFAULT 'Ativo',
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (modulo_id) REFERENCES modulos (id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
                FOREIGN KEY (departamento_id) REFERENCES departamentos (id)
            )
        ''')
        
        print("Tabelas criadas com sucesso!")
        return True
        
    except Exception as e:
        print(f"Erro ao criar tabelas: {str(e)}")
        return False
    finally:
        conn.close()

def inserir_modulos_iniciais():
    """Insere os módulos iniciais"""
    
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'fortanks.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    modulos_iniciais = [
        ('DASHBOARD', 'Painel principal com resumos e indicadores', 'fas fa-tachometer-alt', '/dashboard', 1),
        ('USUARIOS', 'Gerenciamento de usuários do sistema', 'fas fa-users', '/usuarios', 2),
        ('COLABORADORES', 'Cadastro e gestão de colaboradores', 'fas fa-id-card', '/colaboradores', 3),
        ('DEPARTAMENTOS', 'Gerenciamento de departamentos', 'fas fa-building', '/departamentos', 4),
        ('CARGOS', 'Gerenciamento de cargos', 'fas fa-briefcase', '/cargos', 5),
        ('CLIENTES', 'Cadastro e gestão de clientes', 'fas fa-handshake', '/clientes', 6),
        ('CONTRATOS', 'Gerenciamento de contratos', 'fas fa-file-contract', '/contrato', 7),
        ('TANQUES', 'Cadastro e gestão de tanques', 'fas fa-cube', '/tanques', 8),
        ('PECAS', 'Gerenciamento de peças', 'fas fa-cogs', '/pecas', 9),
        ('CONCRETAGENS', 'Controle de concretagens', 'fas fa-hammer', '/concretagens', 10),
        ('EQUIPAMENTOS', 'Gestão de equipamentos', 'fas fa-tools', '/equipamentos', 11),
        ('MATERIAIS', 'Gerenciamento de materiais', 'fas fa-boxes', '/material', 12),
        ('ESTOQUE', 'Controle de estoque', 'fas fa-warehouse', '/estoque', 13),
        ('NOTAS_FISCAIS', 'Gestão de notas fiscais', 'fas fa-file-invoice', '/notas-fiscais', 14),
        ('RELATORIOS', 'Relatórios do sistema', 'fas fa-chart-bar', '/relatorios', 15),
        ('PERMISSOES', 'Gerenciamento de permissões', 'fas fa-shield-alt', '/permissoes', 16)
    ]
    
    try:
        for modulo in modulos_iniciais:
            # Verifica se já existe
            cursor.execute('SELECT id FROM modulos WHERE nome = ?', (modulo[0],))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO modulos (nome, descricao, icone, url, ordem)
                    VALUES (?, ?, ?, ?, ?)
                ''', modulo)
                print(f"Módulo '{modulo[0]}' inserido com sucesso")
            else:
                print(f"Módulo '{modulo[0]}' já existe")
        
        conn.commit()
        print("Módulos iniciais inseridos com sucesso!")
        return True
        
    except Exception as e:
        print(f"Erro ao inserir módulos: {str(e)}")
        return False
    finally:
        conn.close()

def inserir_permissoes_iniciais():
    """Insere permissões iniciais baseadas em cargos"""
    
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'fortanks.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Buscar todos os módulos
        cursor.execute('SELECT id, nome FROM modulos WHERE status = "Ativo"')
        modulos = cursor.fetchall()
        
        # Cargos com acesso total
        cargos_admin = ['ADMINISTRADOR', 'GERENTE', 'DIRETOR']
        
        # Cargos com permissões específicas
        permissoes_especificas = {
            'TÉCNICO DE EDIFICAÇÕES': ['DASHBOARD', 'CONCRETAGENS', 'EQUIPAMENTOS', 'ESTOQUE', 'MATERIAIS', 'PECAS', 'RELATORIOS'],
            'GESTOR DE DESENVOLVIMENTO': ['DASHBOARD', 'CLIENTES', 'CONTRATOS', 'TANQUES', 'PECAS', 'CONCRETAGENS', 'EQUIPAMENTOS', 'ESTOQUE', 'MATERIAIS', 'NOTAS_FISCAIS', 'RELATORIOS'],
            'GESTOR DE FABRICA': ['DASHBOARD', 'CLIENTES', 'CONTRATOS', 'TANQUES', 'PECAS', 'CONCRETAGENS', 'EQUIPAMENTOS', 'ESTOQUE', 'MATERIAIS', 'NOTAS_FISCAIS', 'RELATORIOS'],
            'ENGENHEIRO CIVIL': ['DASHBOARD', 'CLIENTES', 'CONTRATOS', 'TANQUES', 'PECAS', 'CONCRETAGENS', 'EQUIPAMENTOS', 'ESTOQUE', 'MATERIAIS', 'NOTAS_FISCAIS', 'RELATORIOS'],
            'OPERADOR CENTRAL DE CONCRETO': ['DASHBOARD', 'CONCRETAGENS', 'EQUIPAMENTOS', 'RELATORIOS'],
            'ASSISTENTE ADMINISTRATIVO': ['DASHBOARD', 'COLABORADORES', 'CLIENTES', 'NOTAS_FISCAIS', 'RELATORIOS']
        }
        
        # Inserir permissões para cargos administrativos (acesso total)
        for cargo in cargos_admin:
            for modulo_id, modulo_nome in modulos:
                # Verifica se já existe
                cursor.execute('''
                    SELECT id FROM permissoes 
                    WHERE cargo = ? AND modulo_id = ? AND tipo_permissao = 'cargo'
                ''', (cargo, modulo_id))
                
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO permissoes (modulo_id, cargo, tipo_permissao, pode_visualizar, pode_criar, pode_editar, pode_excluir, pode_exportar)
                        VALUES (?, ?, 'cargo', 1, 1, 1, 1, 1)
                    ''', (modulo_id, cargo))
                    print(f"Permissão total criada para cargo '{cargo}' no módulo '{modulo_nome}'")
        
        # Inserir permissões específicas
        for cargo, modulos_permitidos in permissoes_especificas.items():
            for modulo_id, modulo_nome in modulos:
                if modulo_nome in modulos_permitidos:
                    # Verifica se já existe
                    cursor.execute('''
                        SELECT id FROM permissoes 
                        WHERE cargo = ? AND modulo_id = ? AND tipo_permissao = 'cargo'
                    ''', (cargo, modulo_id))
                    
                    if not cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO permissoes (modulo_id, cargo, tipo_permissao, pode_visualizar, pode_criar, pode_editar, pode_excluir, pode_exportar)
                            VALUES (?, ?, 'cargo', 1, 1, 1, 0, 1)
                        ''', (modulo_id, cargo))
                        print(f"Permissão específica criada para cargo '{cargo}' no módulo '{modulo_nome}'")
        
        conn.commit()
        print("Permissões iniciais inseridas com sucesso!")
        return True
        
    except Exception as e:
        print(f"Erro ao inserir permissões: {str(e)}")
        return False
    finally:
        conn.close()

def main():
    """Função principal"""
    print("Iniciando criação do sistema de permissões...")
    
    # Criar tabelas
    if not criar_tabelas_permissoes():
        return
    
    # Inserir módulos iniciais
    if not inserir_modulos_iniciais():
        return
    
    # Inserir permissões iniciais
    if not inserir_permissoes_iniciais():
        return
    
    print("\nSistema de permissões criado com sucesso!")
    print("Agora você pode acessar /permissoes para gerenciar as permissões do sistema.")

if __name__ == '__main__':
    main()


