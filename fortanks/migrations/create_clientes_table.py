from datetime import datetime
from models.database import db

def upgrade():
    """
    Cria as tabelas de clientes e endereços no banco de dados
    """
    print(f"[{datetime.now()}] Iniciando criação das tabelas para clientes...")
    
    try:
        # Verificar se a tabela de clientes já existe
        resultado = db.engine.execute("SHOW TABLES LIKE 'clientes'")
        if resultado.rowcount > 0:
            print(f"[{datetime.now()}] Tabela clientes já existe. Pulando criação.")
        else:
            # Criar a tabela de clientes
            db.engine.execute("""
                CREATE TABLE clientes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nome VARCHAR(100) NOT NULL,
                    cnpj VARCHAR(20) NOT NULL UNIQUE,
                    email VARCHAR(100),
                    telefone VARCHAR(20),
                    observacoes TEXT,
                    ativo BOOLEAN DEFAULT TRUE,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX (nome),
                    INDEX (cnpj)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """)
            print(f"[{datetime.now()}] Tabela clientes criada com sucesso!")
        
        # Verificar se a tabela de endereços já existe
        resultado = db.engine.execute("SHOW TABLES LIKE 'enderecos'")
        if resultado.rowcount > 0:
            print(f"[{datetime.now()}] Tabela enderecos já existe. Pulando criação.")
        else:
            # Criar a tabela de endereços
            db.engine.execute("""
                CREATE TABLE enderecos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    logradouro VARCHAR(150) NOT NULL,
                    numero VARCHAR(20),
                    complemento VARCHAR(100),
                    bairro VARCHAR(100),
                    cidade VARCHAR(100) NOT NULL,
                    estado VARCHAR(2) NOT NULL,
                    cep VARCHAR(10),
                    tipo VARCHAR(20) DEFAULT 'COMERCIAL',
                    principal BOOLEAN DEFAULT TRUE,
                    cliente_id INT NOT NULL,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX (cliente_id),
                    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """)
            print(f"[{datetime.now()}] Tabela enderecos criada com sucesso!")
            
        print(f"[{datetime.now()}] Criação das tabelas finalizada com sucesso!")
    except Exception as e:
        print(f"[{datetime.now()}] Erro ao criar tabelas: {str(e)}")
        raise

def downgrade():
    """
    Remove as tabelas de endereços e clientes do banco de dados
    """
    print(f"[{datetime.now()}] Iniciando remoção das tabelas...")
    
    try:
        # Remover primeiro a tabela de endereços (devido à chave estrangeira)
        resultado = db.engine.execute("SHOW TABLES LIKE 'enderecos'")
        if resultado.rowcount == 0:
            print(f"[{datetime.now()}] Tabela enderecos não existe. Pulando remoção.")
        else:
            db.engine.execute("DROP TABLE IF EXISTS enderecos")
            print(f"[{datetime.now()}] Tabela enderecos removida com sucesso!")
        
        # Depois remover a tabela de clientes
        resultado = db.engine.execute("SHOW TABLES LIKE 'clientes'")
        if resultado.rowcount == 0:
            print(f"[{datetime.now()}] Tabela clientes não existe. Pulando remoção.")
        else:
            db.engine.execute("DROP TABLE IF EXISTS clientes")
            print(f"[{datetime.now()}] Tabela clientes removida com sucesso!")
            
        print(f"[{datetime.now()}] Remoção das tabelas finalizada com sucesso!")
    except Exception as e:
        print(f"[{datetime.now()}] Erro ao remover tabelas: {str(e)}")
        raise 