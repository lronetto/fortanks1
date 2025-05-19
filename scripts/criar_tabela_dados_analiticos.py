"""
Script para criar a tabela de dados analíticos no banco de dados.
"""
import os
import sys
import logging
from sqlalchemy import inspect

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Adicionar diretório pai ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.database import db
from models.dados_analiticos import DadoAnalitico
from app import app

def criar_tabela_dados_analiticos():
    """
    Cria a tabela dado_analitico no banco de dados.
    """
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Verificar se a tabela já existe
        tabelas_existentes = inspector.get_table_names()
        if 'dado_analitico' in tabelas_existentes:
            logger.info("Tabela 'dado_analitico' já existe no banco de dados.")
            return
        
        # Criar a tabela
        try:
            logger.info("Criando tabela 'dado_analitico'...")
            DadoAnalitico.__table__.create(db.engine)
            logger.info("Tabela 'dado_analitico' criada com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao criar tabela: {str(e)}")
            raise

if __name__ == "__main__":
    criar_tabela_dados_analiticos() 