"""
Script de migração para adicionar o campo quantidade_cps na tabela usinagens_concreto
"""
from models import db
import logging
from sqlalchemy import text

def upgrade():
    """Adiciona o campo quantidade_cps na tabela usinagens_concreto"""
    logging.info('Iniciando migração: adicionar_quantidade_cps')
    
    try:
        # Verifica se a tabela migracao_historico existe
        result = db.session.execute(text("""
            SELECT TABLE_NAME 
            FROM information_schema.tables 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'migracao_historico'
        """))
        if not result.fetchone():
            logging.info('Criando tabela migracao_historico...')
            db.session.execute(text("""
                CREATE TABLE migracao_historico (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    descricao VARCHAR(255) NOT NULL,
                    aplicado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.session.commit()
            logging.info('Tabela migracao_historico criada com sucesso!')

        # Verifica se a tabela usinagens_concreto existe
        result = db.session.execute(text("""
            SELECT TABLE_NAME 
            FROM information_schema.tables 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'usinagens_concreto'
        """))
        
        if result.fetchone():
            logging.info('Verificando se o campo quantidade_cps já existe...')
            # Verifica se a coluna quantidade_cps existe
            result = db.session.execute(text("""
                SELECT COLUMN_NAME 
                FROM information_schema.columns 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'usinagens_concreto' 
                AND COLUMN_NAME = 'quantidade_cps'
            """))
            
            if not result.fetchone():
                logging.info('Adicionando campo quantidade_cps...')
                # Adiciona a coluna quantidade_cps
                db.session.execute(text("""
                    ALTER TABLE usinagens_concreto
                    ADD COLUMN quantidade_cps INT DEFAULT 0 AFTER observacoes
                """))
                db.session.commit()
                logging.info('Campo quantidade_cps adicionado com sucesso!')
            else:
                logging.info('Campo quantidade_cps já existe. Nenhuma alteração necessária.')
        else:
            logging.error('Tabela usinagens_concreto não encontrada!')
            raise Exception('Tabela usinagens_concreto não encontrada!')
        
        # Registra a migração
        db.session.execute(text(
            "INSERT INTO migracao_historico (descricao) VALUES ('adicionar_quantidade_cps')"
        ))
        db.session.commit()
        
        logging.info('Migração adicionar_quantidade_cps concluída com sucesso!')
        
    except Exception as e:
        logging.error(f'Erro durante a migração: {str(e)}')
        db.session.rollback()
        raise

if __name__ == '__main__':
    upgrade() 