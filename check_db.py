import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
config = {
    'host': '192.168.8.150',  # IP fixo do servidor
    'user': 'remote',
    'password': '8225Le@28',
    'database': 'sistema_solicitacoes'
}

try:
    # Conectar ao banco de dados
    print("Tentando conectar ao banco de dados...")
    connection = mysql.connector.connect(**config)
    cursor = connection.cursor(dictionary=True)
    print("Conexão estabelecida com sucesso!")

    # Verificar se a tabela usuarios existe
    print("\nVerificando tabela usuarios...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE,
            senha VARCHAR(255) NOT NULL,
            cargo VARCHAR(50) NOT NULL,
            departamento VARCHAR(50)
        )
    """)
    print("Tabela usuarios verificada/criada!")

    # Verificar se a tabela centros_custo existe
    print("\nVerificando tabela centros_custo...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS centros_custo (
            id INT AUTO_INCREMENT PRIMARY KEY,
            codigo VARCHAR(20) NOT NULL UNIQUE,
            nome VARCHAR(100) NOT NULL,
            descricao TEXT,
            ativo BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("Tabela centros_custo verificada/criada!")

    # Verificar se a tabela materiais existe
    print("\nVerificando tabela materiais...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materiais (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            descricao TEXT,
            categoria VARCHAR(50),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("Tabela materiais verificada/criada!")

    # Verificar se a tabela solicitacoes existe
    print("\nVerificando tabela solicitacoes...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS solicitacoes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            justificativa TEXT NOT NULL,
            solicitante_id INT NOT NULL,
            aprovador_id INT,
            centro_custo_id INT NOT NULL,
            status ENUM('pendente', 'aprovada', 'rejeitada') DEFAULT 'pendente',
            data_solicitacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_aprovacao TIMESTAMP NULL,
            observacao TEXT,
            FOREIGN KEY (solicitante_id) REFERENCES usuarios(id),
            FOREIGN KEY (aprovador_id) REFERENCES usuarios(id),
            FOREIGN KEY (centro_custo_id) REFERENCES centros_custo(id)
        )
    """)
    print("Tabela solicitacoes verificada/criada!")

    # Verificar se a tabela itens_solicitacao existe
    print("\nVerificando tabela itens_solicitacao...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS itens_solicitacao (
            id INT AUTO_INCREMENT PRIMARY KEY,
            solicitacao_id INT NOT NULL,
            material_id INT NOT NULL,
            quantidade INT NOT NULL,
            valor_unitario DECIMAL(15,2) DEFAULT 0,
            observacao TEXT,
            FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes(id),
            FOREIGN KEY (material_id) REFERENCES materiais(id)
        )
    """)
    print("Tabela itens_solicitacao verificada/criada!")

    # Verificar se já existem usuários
    cursor.execute("SELECT * FROM usuarios LIMIT 1")
    usuario = cursor.fetchone()

    if not usuario:
        # Criar usuário admin
        print("\nCriando usuário admin...")
        cursor.execute("""
            INSERT INTO usuarios (nome, email, senha, cargo, departamento)
            VALUES ('Administrador', 'admin@empresa.com', 'admin123', 'admin', 'TI')
        """)
        connection.commit()
        print("Usuário admin criado com sucesso!")
    else:
        print("\nJá existe pelo menos um usuário no sistema.")

    # Verificar estrutura atual da tabela
    cursor.execute("DESCRIBE usuarios")
    colunas = cursor.fetchall()
    print("\nEstrutura atual da tabela usuarios:")
    for coluna in colunas:
        print(f"Coluna: {coluna['Field']}, Tipo: {coluna['Type']}")

except Error as e:
    print(f"Erro ao conectar ao MySQL: {e}")
except Exception as e:
    print(f"Erro inesperado: {e}")
finally:
    try:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("\nConexão com MySQL fechada.")
    except Exception as e:
        print(f"Erro ao fechar conexão: {e}")
