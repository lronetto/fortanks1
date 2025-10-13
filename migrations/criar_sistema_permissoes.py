"""
Script para criar o sistema de permissões e popular com dados iniciais
"""
import sys
import os

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models.database import db
from models.permissoes import Modulo, Permissao
from models.usuario import Usuario
from models.departamento import Departamento
from models.colaborador import Colaborador

def criar_modulos_iniciais():
    """Cria os módulos iniciais do sistema"""
    modulos_iniciais = [
        {
            'nome': 'DASHBOARD',
            'descricao': 'Painel principal com resumos e indicadores',
            'icone': 'fas fa-tachometer-alt',
            'url': '/dashboard',
            'ordem': 1
        },
        {
            'nome': 'USUARIOS',
            'descricao': 'Gerenciamento de usuários do sistema',
            'icone': 'fas fa-users',
            'url': '/usuarios',
            'ordem': 2
        },
        {
            'nome': 'COLABORADORES',
            'descricao': 'Cadastro e gestão de colaboradores',
            'icone': 'fas fa-id-card',
            'url': '/colaboradores',
            'ordem': 3
        },
        {
            'nome': 'DEPARTAMENTOS',
            'descricao': 'Gerenciamento de departamentos',
            'icone': 'fas fa-building',
            'url': '/departamentos',
            'ordem': 4
        },
        {
            'nome': 'CARGOS',
            'descricao': 'Gerenciamento de cargos',
            'icone': 'fas fa-briefcase',
            'url': '/cargos',
            'ordem': 5
        },
        {
            'nome': 'CLIENTES',
            'descricao': 'Cadastro e gestão de clientes',
            'icone': 'fas fa-handshake',
            'url': '/clientes',
            'ordem': 6
        },
        {
            'nome': 'CONTRATOS',
            'descricao': 'Gerenciamento de contratos',
            'icone': 'fas fa-file-contract',
            'url': '/contrato',
            'ordem': 7
        },
        {
            'nome': 'TANQUES',
            'descricao': 'Cadastro e gestão de tanques',
            'icone': 'fas fa-cube',
            'url': '/tanques',
            'ordem': 8
        },
        {
            'nome': 'PECAS',
            'descricao': 'Gerenciamento de peças',
            'icone': 'fas fa-cogs',
            'url': '/pecas',
            'ordem': 9
        },
        {
            'nome': 'CONCRETAGENS',
            'descricao': 'Controle de concretagens',
            'icone': 'fas fa-hammer',
            'url': '/concretagens',
            'ordem': 10
        },
        {
            'nome': 'EQUIPAMENTOS',
            'descricao': 'Gestão de equipamentos',
            'icone': 'fas fa-tools',
            'url': '/equipamentos',
            'ordem': 11
        },
        {
            'nome': 'MATERIAIS',
            'descricao': 'Gerenciamento de materiais',
            'icone': 'fas fa-boxes',
            'url': '/material',
            'ordem': 12
        },
        {
            'nome': 'ESTOQUE',
            'descricao': 'Controle de estoque',
            'icone': 'fas fa-warehouse',
            'url': '/estoque',
            'ordem': 13
        },
        {
            'nome': 'NOTAS_FISCAIS',
            'descricao': 'Gestão de notas fiscais',
            'icone': 'fas fa-file-invoice',
            'url': '/notas-fiscais',
            'ordem': 14
        },
        {
            'nome': 'RELATORIOS',
            'descricao': 'Relatórios do sistema',
            'icone': 'fas fa-chart-bar',
            'url': '/relatorios',
            'ordem': 15
        },
        {
            'nome': 'PERMISSOES',
            'descricao': 'Gerenciamento de permissões',
            'icone': 'fas fa-shield-alt',
            'url': '/permissoes',
            'ordem': 16
        }
    ]
    
    for modulo_data in modulos_iniciais:
        # Verifica se o módulo já existe
        modulo_existente = Modulo.query.filter_by(nome=modulo_data['nome']).first()
        if not modulo_existente:
            modulo = Modulo(**modulo_data)
            db.session.add(modulo)
            print(f"Módulo '{modulo_data['nome']}' criado com sucesso")
        else:
            print(f"Módulo '{modulo_data['nome']}' já existe")
    
    db.session.commit()

def criar_permissoes_iniciais():
    """Cria permissões iniciais baseadas nos cargos existentes"""
    
    # Buscar departamento administrativo
    dept_admin = Departamento.query.filter_by(nome='ADMINISTRATIVO').first()
    
    # Buscar cargos comuns
    cargos_comuns = [
        'ADMINISTRADOR',
        'GERENTE',
        'DIRETOR',
        'TÉCNICO DE EDIFICAÇÕES',
        'GESTOR DE DESENVOLVIMENTO',
        'GESTOR DE FABRICA',
        'ENGENHEIRO CIVIL',
        'OPERADOR CENTRAL DE CONCRETO',
        'ASSISTENTE ADMINISTRATIVO'
    ]
    
    # Permissões para administradores (acesso total)
    for cargo in cargos_comuns:
        if 'ADMIN' in cargo.upper() or 'GERENTE' in cargo.upper() or 'DIRETOR' in cargo.upper():
            for modulo in Modulo.query.filter_by(status='Ativo').all():
                # Verifica se já existe permissão
                permissao_existente = Permissao.query.filter_by(
                    modulo_id=modulo.id,
                    cargo=cargo,
                    tipo_permissao='cargo'
                ).first()
                
                if not permissao_existente:
                    permissao = Permissao(
                        modulo_id=modulo.id,
                        cargo=cargo,
                        tipo_permissao='cargo',
                        pode_visualizar=True,
                        pode_criar=True,
                        pode_editar=True,
                        pode_excluir=True,
                        pode_exportar=True
                    )
                    db.session.add(permissao)
                    print(f"Permissão total criada para cargo '{cargo}' no módulo '{modulo.nome}'")
    
    # Permissões específicas para outros cargos
    permissoes_especificas = {
        'TÉCNICO DE EDIFICAÇÕES': [
            'DASHBOARD', 'CONCRETAGENS', 'EQUIPAMENTOS', 'ESTOQUE', 
            'MATERIAIS', 'PECAS', 'RELATORIOS'
        ],
        'GESTOR DE DESENVOLVIMENTO': [
            'DASHBOARD', 'CLIENTES', 'CONTRATOS', 'TANQUES', 'PECAS',
            'CONCRETAGENS', 'EQUIPAMENTOS', 'ESTOQUE', 'MATERIAIS',
            'NOTAS_FISCAIS', 'RELATORIOS'
        ],
        'GESTOR DE FABRICA': [
            'DASHBOARD', 'CLIENTES', 'CONTRATOS', 'TANQUES', 'PECAS',
            'CONCRETAGENS', 'EQUIPAMENTOS', 'ESTOQUE', 'MATERIAIS',
            'NOTAS_FISCAIS', 'RELATORIOS'
        ],
        'ENGENHEIRO CIVIL': [
            'DASHBOARD', 'CLIENTES', 'CONTRATOS', 'TANQUES', 'PECAS',
            'CONCRETAGENS', 'EQUIPAMENTOS', 'ESTOQUE', 'MATERIAIS',
            'NOTAS_FISCAIS', 'RELATORIOS'
        ],
        'OPERADOR CENTRAL DE CONCRETO': [
            'DASHBOARD', 'CONCRETAGENS', 'EQUIPAMENTOS', 'RELATORIOS'
        ],
        'ASSISTENTE ADMINISTRATIVO': [
            'DASHBOARD', 'COLABORADORES', 'CLIENTES', 'NOTAS_FISCAIS', 'RELATORIOS'
        ]
    }
    
    for cargo, modulos in permissoes_especificas.items():
        for nome_modulo in modulos:
            modulo = Modulo.query.filter_by(nome=nome_modulo).first()
            if modulo:
                # Verifica se já existe permissão
                permissao_existente = Permissao.query.filter_by(
                    modulo_id=modulo.id,
                    cargo=cargo,
                    tipo_permissao='cargo'
                ).first()
                
                if not permissao_existente:
                    permissao = Permissao(
                        modulo_id=modulo.id,
                        cargo=cargo,
                        tipo_permissao='cargo',
                        pode_visualizar=True,
                        pode_criar=True,
                        pode_editar=True,
                        pode_excluir=False,
                        pode_exportar=True
                    )
                    db.session.add(permissao)
                    print(f"Permissão específica criada para cargo '{cargo}' no módulo '{modulo.nome}'")
    
    db.session.commit()

def main():
    """Função principal para executar a migração"""
    with app.app_context():
        print("Iniciando criação do sistema de permissões...")
        
        try:
            # Criar tabelas se não existirem
            db.create_all()
            print("Tabelas criadas/verificadas com sucesso")
            
            # Criar módulos iniciais
            print("\nCriando módulos iniciais...")
            criar_modulos_iniciais()
            
            # Criar permissões iniciais
            print("\nCriando permissões iniciais...")
            criar_permissoes_iniciais()
            
            print("\nSistema de permissões criado com sucesso!")
            
        except Exception as e:
            print(f"Erro ao criar sistema de permissões: {str(e)}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    main()


