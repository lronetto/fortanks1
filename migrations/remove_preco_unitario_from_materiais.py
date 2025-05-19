from datetime import datetime
from models.database import db
from sqlalchemy import text

def upgrade():
    """
    Remove a coluna preco_unitario da tabela materiais, pois não é necessária
    """
    start_time = datetime.now()
    print(f"[{start_time}] Iniciando migração para remover coluna preco_unitario da tabela materiais...")
    
    try:
        # Verificar se a coluna existe
        result = db.session.execute(text("SHOW COLUMNS FROM materiais LIKE 'preco_unitario'"))
        if result.rowcount > 0:
            # A coluna existe, então vamos removê-la
            db.session.execute(text("ALTER TABLE materiais DROP COLUMN preco_unitario"))
            db.session.commit()
            print(f"[{datetime.now()}] Coluna preco_unitario removida com sucesso da tabela materiais.")
        else:
            print(f"[{datetime.now()}] A coluna preco_unitario não existe na tabela materiais. Nenhuma alteração necessária.")
    
        end_time = datetime.now()
        duration = end_time - start_time
        print(f"[{end_time}] Migração concluída em {duration.total_seconds():.2f} segundos.")
    except Exception as e:
        db.session.rollback()
        print(f"[{datetime.now()}] Erro durante a migração: {str(e)}")
        raise

def downgrade():
    """
    Readiciona a coluna preco_unitario à tabela materiais (caso seja necessário reverter)
    """
    start_time = datetime.now()
    print(f"[{start_time}] Iniciando migração para adicionar coluna preco_unitario à tabela materiais...")
    
    try:
        # Verificar se a coluna já existe
        result = db.session.execute(text("SHOW COLUMNS FROM materiais LIKE 'preco_unitario'"))
        if result.rowcount == 0:
            # A coluna não existe, então vamos adicioná-la
            db.session.execute(text("ALTER TABLE materiais ADD COLUMN preco_unitario DECIMAL(10,2) DEFAULT 0.00"))
            db.session.commit()
            print(f"[{datetime.now()}] Coluna preco_unitario adicionada com sucesso à tabela materiais.")
        else:
            print(f"[{datetime.now()}] A coluna preco_unitario já existe na tabela materiais. Nenhuma alteração necessária.")
    
        end_time = datetime.now()
        duration = end_time - start_time
        print(f"[{end_time}] Migração concluída em {duration.total_seconds():.2f} segundos.")
    except Exception as e:
        db.session.rollback()
        print(f"[{datetime.now()}] Erro durante a migração: {str(e)}")
        raise 