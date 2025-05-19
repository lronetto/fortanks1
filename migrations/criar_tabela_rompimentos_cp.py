"""
Script de migração para criar a tabela de rompimentos de corpo de prova
"""
from models import db
import logging
from sqlalchemy import text

def upgrade():
    """Cria ou altera a tabela de rompimentos de corpos de prova"""
    logging.info('Iniciando migração: criar_tabela_rompimentos_cp')
    
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

        # Verifica se a tabela rompimentos_corpo_prova existe
        result = db.session.execute(text("""
            SELECT TABLE_NAME 
            FROM information_schema.tables 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'rompimentos_corpo_prova'
        """))
        
        if result.fetchone():
            logging.info('Alterando tabela rompimentos_corpo_prova...')
            # Verifica se a coluna quantidade_cps existe
            result = db.session.execute(text("""
                SELECT COLUMN_NAME 
                FROM information_schema.columns 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'rompimentos_corpo_prova' 
                AND COLUMN_NAME = 'quantidade_cps'
            """))
            
            if result.fetchone():
                # Remove a coluna quantidade_cps e adiciona numero_cp
                db.session.execute(text("""
                    ALTER TABLE rompimentos_corpo_prova
                    DROP COLUMN quantidade_cps,
                    ADD COLUMN numero_cp INT NOT NULL AFTER usinagem_id,
                    ADD UNIQUE KEY uk_usinagem_cp (usinagem_id, numero_cp)
                """))
                db.session.commit()
                logging.info('Tabela rompimentos_corpo_prova alterada com sucesso!')
        else:
            logging.info('Criando tabela rompimentos_corpo_prova...')
            db.session.execute(text("""
                CREATE TABLE rompimentos_corpo_prova (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    usinagem_id INT NOT NULL,
                    numero_cp INT NOT NULL,
                    idade_cp INT NOT NULL,
                    data_rompimento TIMESTAMP NOT NULL,
                    resultado DECIMAL(10,2),
                    observacoes TEXT,
                    FOREIGN KEY (usinagem_id) REFERENCES usinagem_concreto (id),
                    UNIQUE KEY uk_usinagem_cp (usinagem_id, numero_cp)
                )
            """))
            db.session.commit()
            logging.info('Tabela rompimentos_corpo_prova criada com sucesso!')
        
        # Registra a migração
        db.session.execute(text(
            "INSERT INTO migracao_historico (descricao) VALUES ('criar_tabela_rompimentos_cp')"
        ))
        db.session.commit()
        
        logging.info('Migração criar_tabela_rompimentos_cp concluída com sucesso!')
        
    except Exception as e:
        logging.error(f'Erro durante a migração: {str(e)}')
        db.session.rollback()
        raise

if __name__ == '__main__':
    upgrade() 