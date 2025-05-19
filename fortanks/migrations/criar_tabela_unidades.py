"""
Script para criar a tabela de unidades e adicionar as unidades padrão
"""
from models.database import db
from models.unidade import Unidade
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

def run():
    """
    Executa a migração para criar a tabela de unidades
    """
    try:
        # Verifica se a tabela já existe
        result = db.session.execute(text("SHOW TABLES LIKE 'unidades'"))
        if result.rowcount > 0:
            logger.info("A tabela 'unidades' já existe. Pulando criação.")
        else:
            # Cria a tabela unidades
            sql_criar_tabela = """
            CREATE TABLE IF NOT EXISTS unidades (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                nome VARCHAR(10) NOT NULL UNIQUE,
                descricao VARCHAR(100),
                ativo BOOLEAN DEFAULT TRUE,
                padrao BOOLEAN DEFAULT FALSE,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            );
            """
            db.session.execute(text(sql_criar_tabela))
            logger.info("Tabela 'unidades' criada com sucesso.")
            
        # Adiciona coluna unidade_id à tabela materiais
        try:
            db.session.execute(text("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS unidade_id INTEGER REFERENCES unidades(id)"))
            logger.info("Coluna 'unidade_id' adicionada à tabela 'materiais' com sucesso.")
        except Exception as e:
            logger.warning(f"Erro ao adicionar coluna 'unidade_id': {str(e)}")
            
        # Adiciona colunas à tabela conversoes_unidades
        try:
            db.session.execute(text("ALTER TABLE conversoes_unidades ADD COLUMN IF NOT EXISTS unidade_origem_id INTEGER REFERENCES unidades(id)"))
            db.session.execute(text("ALTER TABLE conversoes_unidades ADD COLUMN IF NOT EXISTS unidade_destino_id INTEGER REFERENCES unidades(id)"))
            db.session.execute(text("ALTER TABLE conversoes_unidades ADD COLUMN IF NOT EXISTS material_id INTEGER REFERENCES materiais(id)"))
            logger.info("Colunas adicionadas à tabela 'conversoes_unidades' com sucesso.")
        except Exception as e:
            logger.warning(f"Erro ao adicionar colunas à tabela 'conversoes_unidades': {str(e)}")
            
        # Cria as unidades padrão
        try:
            Unidade.criar_unidades_padrao()
            logger.info("Unidades padrão criadas com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao criar unidades padrão: {str(e)}")
            
        # Mapeia as unidades existentes nos materiais para as novas unidades
        try:
            sql_mapear_unidades = """
            UPDATE materiais m
            JOIN unidades u ON UPPER(TRIM(m.unidade)) = UPPER(TRIM(u.nome))
            SET m.unidade_id = u.id
            WHERE m.unidade IS NOT NULL AND m.unidade != '';
            """
            db.session.execute(text(sql_mapear_unidades))
            logger.info("Unidades mapeadas para os materiais com sucesso.")
        except Exception as e:
            logger.warning(f"Erro ao mapear unidades: {str(e)}")
            
        # Confirma as alterações
        db.session.commit()
        logger.info("Migração concluída com sucesso.")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao executar migração: {str(e)}")
        raise e 