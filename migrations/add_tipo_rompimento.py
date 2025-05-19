"""
Migração para adicionar a coluna tipo_rompimento à tabela RompCorpProva
"""
import logging
import sqlite3
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def upgrade():
    """
    Executa a migração para adicionar a coluna tipo_rompimento à tabela RompCorpProva
    """
    logger.info("Iniciando migração: Adicionar coluna tipo_rompimento à tabela RompCorpProva")
    
    # Caminho para o banco de dados
    db_path = Path(__file__).parents[1] / "fortanks.db"
    if not db_path.exists():
        logger.error(f"Arquivo de banco de dados não encontrado: {db_path}")
        return False
    
    # Conectar ao banco de dados
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Verificar se a tabela RompCorpProva existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='RompCorpProva'")
        if not cursor.fetchone():
            logger.error("Tabela RompCorpProva não encontrada no banco de dados")
            conn.close()
            return False
        
        # Verificar se a coluna já existe
        cursor.execute("PRAGMA table_info(RompCorpProva)")
        colunas = cursor.fetchall()
        if any(coluna[1] == 'tipo_rompimento' for coluna in colunas):
            logger.info("Coluna tipo_rompimento já existe. Pulando migração.")
            conn.close()
            return True
        
        # Adicionar a coluna
        logger.info("Adicionando coluna tipo_rompimento à tabela RompCorpProva")
        cursor.execute("ALTER TABLE RompCorpProva ADD COLUMN tipo_rompimento TEXT")
        
        # Commit e fechar conexão
        conn.commit()
        conn.close()
        
        logger.info("Migração concluída com sucesso!")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Erro ao executar migração: {e}")
        if 'conn' in locals():
            conn.close()
        return False

def downgrade():
    """
    Reverte a migração (remove a coluna tipo_rompimento da tabela RompCorpProva)
    """
    # SQLite não suporta remover colunas diretamente, então uma downgrade 
    # requereria recriar a tabela sem a coluna, o que não está implementado aqui.
    logger.warning("Downgrade não implementado para esta migração devido a limitações do SQLite")
    return False

if __name__ == "__main__":
    upgrade() 