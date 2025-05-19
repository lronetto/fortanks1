from datetime import datetime
from models.database import db

def upgrade():
    """
    Adiciona os campos cliente_direto_id e cliente_final_id à tabela contratos
    """
    print(f"[{datetime.now()}] Iniciando atualização da tabela contratos...")
    
    try:
        # Verificar se as colunas já existem
        resultado_direto = db.engine.execute("SHOW COLUMNS FROM contratos LIKE 'cliente_direto_id'")
        resultado_final = db.engine.execute("SHOW COLUMNS FROM contratos LIKE 'cliente_final_id'")
        
        if resultado_direto.rowcount == 0:
            # Adicionar a coluna cliente_direto_id
            db.engine.execute("""
                ALTER TABLE contratos 
                ADD COLUMN cliente_direto_id INT NULL,
                ADD CONSTRAINT fk_contratos_cliente_direto
                FOREIGN KEY (cliente_direto_id) REFERENCES clientes(id)
                ON DELETE SET NULL;
            """)
            print(f"[{datetime.now()}] Coluna cliente_direto_id adicionada com sucesso!")
        else:
            print(f"[{datetime.now()}] Coluna cliente_direto_id já existe. Pulando criação.")
        
        if resultado_final.rowcount == 0:
            # Adicionar a coluna cliente_final_id
            db.engine.execute("""
                ALTER TABLE contratos 
                ADD COLUMN cliente_final_id INT NULL,
                ADD CONSTRAINT fk_contratos_cliente_final
                FOREIGN KEY (cliente_final_id) REFERENCES clientes(id)
                ON DELETE SET NULL;
            """)
            print(f"[{datetime.now()}] Coluna cliente_final_id adicionada com sucesso!")
        else:
            print(f"[{datetime.now()}] Coluna cliente_final_id já existe. Pulando criação.")
            
        print(f"[{datetime.now()}] Atualização da tabela contratos finalizada com sucesso!")
    except Exception as e:
        print(f"[{datetime.now()}] Erro ao atualizar tabela contratos: {str(e)}")
        raise

def downgrade():
    """
    Remove os campos cliente_direto_id e cliente_final_id da tabela contratos
    """
    print(f"[{datetime.now()}] Iniciando remoção das colunas da tabela contratos...")
    
    try:
        # Verificar se as colunas existem
        resultado_direto = db.engine.execute("SHOW COLUMNS FROM contratos LIKE 'cliente_direto_id'")
        resultado_final = db.engine.execute("SHOW COLUMNS FROM contratos LIKE 'cliente_final_id'")
        
        # Remover primeiro as chaves estrangeiras antes de remover as colunas
        db.engine.execute("ALTER TABLE contratos DROP FOREIGN KEY IF EXISTS fk_contratos_cliente_direto;")
        db.engine.execute("ALTER TABLE contratos DROP FOREIGN KEY IF EXISTS fk_contratos_cliente_final;")
        
        if resultado_direto.rowcount > 0:
            # Remover a coluna cliente_direto_id
            db.engine.execute("ALTER TABLE contratos DROP COLUMN cliente_direto_id;")
            print(f"[{datetime.now()}] Coluna cliente_direto_id removida com sucesso!")
        else:
            print(f"[{datetime.now()}] Coluna cliente_direto_id não existe. Pulando remoção.")
        
        if resultado_final.rowcount > 0:
            # Remover a coluna cliente_final_id
            db.engine.execute("ALTER TABLE contratos DROP COLUMN cliente_final_id;")
            print(f"[{datetime.now()}] Coluna cliente_final_id removida com sucesso!")
        else:
            print(f"[{datetime.now()}] Coluna cliente_final_id não existe. Pulando remoção.")
            
        print(f"[{datetime.now()}] Remoção das colunas da tabela contratos finalizada com sucesso!")
    except Exception as e:
        print(f"[{datetime.now()}] Erro ao remover colunas da tabela contratos: {str(e)}")
        raise 