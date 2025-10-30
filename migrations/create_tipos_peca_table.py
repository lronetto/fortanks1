from datetime import datetime
from models.database import db

def upgrade():
    """
    Cria a tabela de tipos de peça no banco de dados
    """
    print(f"[{datetime.now()}] Iniciando criação da tabela tipos_peca...")
    
    try:
        # Verificar se a tabela já existe
        resultado = db.engine.execute("SHOW TABLES LIKE 'tipos_peca'")
        if resultado.rowcount > 0:
            print(f"[{datetime.now()}] Tabela tipos_peca já existe. Pulando criação.")
        else:
            # Criar a tabela de tipos de peça
            db.engine.execute("""
                CREATE TABLE tipos_peca (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nome VARCHAR(100) NOT NULL,
                    volume DECIMAL(10, 2),
                    abertura TEXT,
                    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX (nome)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """)
            print(f"[{datetime.now()}] Tabela tipos_peca criada com sucesso!")
            
        print(f"[{datetime.now()}] Criação da tabela finalizada com sucesso!")
    except Exception as e:
        print(f"[{datetime.now()}] Erro ao criar tabela: {str(e)}")
        raise

def downgrade():
    """
    Remove a tabela tipos_peca do banco de dados
    """
    print(f"[{datetime.now()}] Iniciando remoção da tabela tipos_peca...")
    
    try:
        # Verificar se a tabela existe
        resultado = db.engine.execute("SHOW TABLES LIKE 'tipos_peca'")
        if resultado.rowcount == 0:
            print(f"[{datetime.now()}] Tabela tipos_peca não existe. Pulando remoção.")
        else:
            db.engine.execute("DROP TABLE IF EXISTS tipos_peca")
            print(f"[{datetime.now()}] Tabela tipos_peca removida com sucesso!")
            
        print(f"[{datetime.now()}] Remoção da tabela finalizada com sucesso!")
    except Exception as e:
        print(f"[{datetime.now()}] Erro ao remover tabela: {str(e)}")
        raise

