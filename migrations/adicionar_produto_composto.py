"""
Script de migração para adicionar as tabelas de produto composto e produção de peças
"""

from flask import current_app
from models.database import db
import logging
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger(__name__)

def upgrade():
    """
    Cria as tabelas de produto composto e produção de peças
    """
    # SQLAlchemy não tem suporte para criar tabelas específicas,
    # então vamos executar SQL diretamente
    logger.info("Iniciando migração para criar tabelas de produto composto e produção de peças...")
    
    conn = db.engine.connect()
    
    # Tabela produtos_compostos
    logger.info("Criando tabela produtos_compostos...")
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS produtos_compostos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(50) UNIQUE,
        nome VARCHAR(100) NOT NULL,
        descricao TEXT,
        tipo_peca VARCHAR(50) NOT NULL,
        tempo_producao DECIMAL(10, 2),
        status VARCHAR(20) DEFAULT 'Ativo',
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """))
    
    # Tabela componentes_produto
    logger.info("Criando tabela componentes_produto...")
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS componentes_produto (
        id INT AUTO_INCREMENT PRIMARY KEY,
        produto_id INT NOT NULL,
        material_id INT NOT NULL,
        quantidade DECIMAL(10, 2) NOT NULL,
        unidade VARCHAR(20) NOT NULL,
        observacao TEXT,
        FOREIGN KEY (produto_id) REFERENCES produtos_compostos(id) ON DELETE CASCADE,
        FOREIGN KEY (material_id) REFERENCES materiais(id)
    )
    """))
    
    # Tabela producoes_peca
    logger.info("Criando tabela producoes_peca...")
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS producoes_peca (
        id INT AUTO_INCREMENT PRIMARY KEY,
        peca_id INT NOT NULL,
        produto_composto_id INT NOT NULL,
        data_producao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        quantidade INT NOT NULL DEFAULT 1,
        status VARCHAR(20) DEFAULT 'Concluída',
        observacoes TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (peca_id) REFERENCES pecas(id),
        FOREIGN KEY (produto_composto_id) REFERENCES produtos_compostos(id)
    )
    """))
    
    # Tabela producao_peca_materiais
    logger.info("Criando tabela producao_peca_materiais...")
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS producao_peca_materiais (
        id INT AUTO_INCREMENT PRIMARY KEY,
        producao_id INT NOT NULL,
        material_id INT NOT NULL,
        quantidade_utilizada DECIMAL(10, 2) NOT NULL,
        unidade VARCHAR(20) NOT NULL,
        FOREIGN KEY (producao_id) REFERENCES producoes_peca(id) ON DELETE CASCADE,
        FOREIGN KEY (material_id) REFERENCES materiais(id)
    )
    """))
    
    conn.close()
    logger.info("Migração concluída com sucesso!")

def downgrade():
    """
    Remove as tabelas criadas
    """
    logger.info("Desfazendo migração de produto composto e produção de peças...")
    
    conn = db.engine.connect()
    
    # Remover na ordem inversa para respeitar as chaves estrangeiras
    logger.info("Removendo tabela producao_peca_materiais...")
    conn.execute(text("DROP TABLE IF EXISTS producao_peca_materiais"))
    
    logger.info("Removendo tabela producoes_peca...")
    conn.execute(text("DROP TABLE IF EXISTS producoes_peca"))
    
    logger.info("Removendo tabela componentes_produto...")
    conn.execute(text("DROP TABLE IF EXISTS componentes_produto"))
    
    logger.info("Removendo tabela produtos_compostos...")
    conn.execute(text("DROP TABLE IF EXISTS produtos_compostos"))
    
    conn.close()
    logger.info("Downgrade concluído com sucesso!") 