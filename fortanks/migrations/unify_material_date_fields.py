from datetime import datetime
from models.database import db
from sqlalchemy import text

def upgrade():
    """
    Unifica os campos de data no modelo Material para usar apenas criado_em
    """
    start_time = datetime.now()
    print(f"[{start_time}] Iniciando migração para unificar campos de data em Material...")
    
    try:
        # Verificar se as colunas existem
        data_cadastro_exists = db.session.execute(text("SHOW COLUMNS FROM materiais LIKE 'data_cadastro'")).rowcount > 0
        ultima_atualizacao_exists = db.session.execute(text("SHOW COLUMNS FROM materiais LIKE 'ultima_atualizacao'")).rowcount > 0
        criado_em_exists = db.session.execute(text("SHOW COLUMNS FROM materiais LIKE 'criado_em'")).rowcount > 0
        
        # Se data_cadastro existe mas criado_em não existe, criar criado_em e copiar os dados
        if data_cadastro_exists and not criado_em_exists:
            db.session.execute(text("ALTER TABLE materiais ADD COLUMN criado_em DATETIME"))
            db.session.execute(text("UPDATE materiais SET criado_em = data_cadastro"))
            db.session.commit()
            print(f"[{datetime.now()}] Coluna criado_em criada e dados copiados de data_cadastro.")
        
        # Se data_cadastro existe e criado_em existe, remover data_cadastro
        if data_cadastro_exists and criado_em_exists:
            db.session.execute(text("ALTER TABLE materiais DROP COLUMN data_cadastro"))
            db.session.commit()
            print(f"[{datetime.now()}] Coluna data_cadastro removida com sucesso.")
        
        # Se ultima_atualizacao existe, remover
        if ultima_atualizacao_exists:
            db.session.execute(text("ALTER TABLE materiais DROP COLUMN ultima_atualizacao"))
            db.session.commit()
            print(f"[{datetime.now()}] Coluna ultima_atualizacao removida com sucesso.")
        
        # Se criado_em não existe, criar
        if not criado_em_exists:
            db.session.execute(text("ALTER TABLE materiais ADD COLUMN criado_em DATETIME DEFAULT CURRENT_TIMESTAMP"))
            db.session.commit()
            print(f"[{datetime.now()}] Coluna criado_em criada com sucesso.")
        
        end_time = datetime.now()
        duration = end_time - start_time
        print(f"[{end_time}] Migração concluída em {duration.total_seconds():.2f} segundos.")
    except Exception as e:
        db.session.rollback()
        print(f"[{datetime.now()}] Erro durante a migração: {str(e)}")
        raise

def downgrade():
    """
    Não implementado - esta migração é uma limpeza e não deve ser revertida
    """
    print("Downgrade não implementado para esta migração. Alterações feitas devem ser mantidas.") 