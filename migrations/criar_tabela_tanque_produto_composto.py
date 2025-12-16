"""
Script de migração para criar a tabela de vinculação entre tanques e produtos compostos
"""

from flask import current_app
from models.database import db
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

def upgrade():
    """
    Cria a tabela de vinculação entre tanques e produtos compostos
    Executar com: python -m migrations.criar_tabela_tanque_produto_composto
    """
    logger.info("Iniciando migração para criar tabela tanques_produtos_compostos...")
    
    try:
        conn = db.engine.connect()
        
        # Verificar se a tabela já existe
        result = conn.execute(text("SHOW TABLES LIKE 'tanques_produtos_compostos'"))
        if result.rowcount > 0:
            logger.info("A tabela 'tanques_produtos_compostos' já existe. Pulando criação.")
            conn.close()
            return
        
        # Criar tabela de vinculação
        logger.info("Criando tabela tanques_produtos_compostos...")
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tanques_produtos_compostos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tanque_id INT NOT NULL,
            produto_composto_id INT NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (tanque_id) REFERENCES tanques(id) ON DELETE CASCADE,
            FOREIGN KEY (produto_composto_id) REFERENCES ProdComp(id) ON DELETE CASCADE,
            UNIQUE KEY uq_tanque_produto_composto (tanque_id, produto_composto_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        
        conn.commit()
        conn.close()
        logger.info("Tabela 'tanques_produtos_compostos' criada com sucesso.")
        print("✅ Tabela 'tanques_produtos_compostos' criada com sucesso.")
        
    except Exception as e:
        logger.error(f"Erro ao criar tabela tanques_produtos_compostos: {str(e)}")
        db.session.rollback()
        if 'conn' in locals():
            conn.close()
        raise

def downgrade():
    """
    Remove a tabela de vinculação entre tanques e produtos compostos
    """
    logger.info("Iniciando downgrade para remover tabela tanques_produtos_compostos...")
    
    try:
        conn = db.engine.connect()
        
        logger.info("Removendo tabela tanques_produtos_compostos...")
        conn.execute(text("DROP TABLE IF EXISTS tanques_produtos_compostos"))
        
        conn.commit()
        conn.close()
        logger.info("Tabela 'tanques_produtos_compostos' removida com sucesso.")
        print("✅ Tabela 'tanques_produtos_compostos' removida com sucesso.")
        
    except Exception as e:
        logger.error(f"Erro ao remover tabela tanques_produtos_compostos: {str(e)}")
        db.session.rollback()
        if 'conn' in locals():
            conn.close()
        raise

if __name__ == '__main__':
    from datetime import datetime
    print(f"Executando migração em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        upgrade()
        print("=" * 60)
        print("✅ Migração concluída com sucesso!")
    except Exception as e:
        print("=" * 60)
        print(f"❌ Erro ao executar migração: {str(e)}")
        raise

