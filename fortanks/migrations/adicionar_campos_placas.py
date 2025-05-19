"""
Migração para adicionar campos de configuração de placas ao modelo Tanque
"""
from app import db
from sqlalchemy import text

def upgrade():
    """Adiciona os campos placas_normais e placas_fecho à tabela tanques"""
    # Usar SQL direto para adicionar as colunas
    try:
        # Verificar se as colunas já existem
        result = db.session.execute(text("SHOW COLUMNS FROM tanques"))
        colunas = [row[0] for row in result]
        
        # Adicionar coluna placas_normais se não existir
        if 'placas_normais' not in colunas:
            db.session.execute(text("ALTER TABLE tanques ADD COLUMN placas_normais INT DEFAULT 0"))
        
        # Adicionar coluna placas_fecho se não existir
        if 'placas_fecho' not in colunas:
            db.session.execute(text("ALTER TABLE tanques ADD COLUMN placas_fecho INT DEFAULT 0"))
        
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao adicionar colunas: {str(e)}")
        return False

def downgrade():
    """Remove os campos placas_normais e placas_fecho da tabela tanques"""
    try:
        # Verificar se as colunas existem
        result = db.session.execute(text("SHOW COLUMNS FROM tanques"))
        colunas = [row[0] for row in result]
        
        # Remover coluna placas_normais se existir
        if 'placas_normais' in colunas:
            db.session.execute(text("ALTER TABLE tanques DROP COLUMN placas_normais"))
        
        # Remover coluna placas_fecho se existir
        if 'placas_fecho' in colunas:
            db.session.execute(text("ALTER TABLE tanques DROP COLUMN placas_fecho"))
        
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao remover colunas: {str(e)}")
        return False 