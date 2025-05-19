from datetime import datetime
from models.database import db

def upgrade():
    """
    Script de migração para adicionar a coluna 'unidade' à tabela 'materiais'
    Executar com: python -m migrations.add_unidade_to_materiais
    """
    # Obtém uma conexão com o banco de dados
    conn = db.engine.connect()
    
    # Verifica se a coluna já existe para evitar erros
    resultado = conn.execute("SHOW COLUMNS FROM materiais LIKE 'unidade'")
    if not resultado.fetchone():
        # Adiciona a coluna 'unidade' à tabela 'materiais'
        conn.execute("ALTER TABLE materiais ADD COLUMN unidade VARCHAR(20)")
        print("Coluna 'unidade' adicionada com sucesso à tabela 'materiais'.")
    else:
        print("A coluna 'unidade' já existe na tabela 'materiais'.")
    
    # Fecha a conexão
    conn.close()

def downgrade():
    """
    Script para remover a coluna 'unidade' caso seja necessário reverter a migração
    """
    # Obtém uma conexão com o banco de dados
    conn = db.engine.connect()
    
    # Verifica se a coluna existe antes de tentar removê-la
    resultado = conn.execute("SHOW COLUMNS FROM materiais LIKE 'unidade'")
    if resultado.fetchone():
        # Remove a coluna 'unidade' da tabela 'materiais'
        conn.execute("ALTER TABLE materiais DROP COLUMN unidade")
        print("Coluna 'unidade' removida com sucesso da tabela 'materiais'.")
    else:
        print("A coluna 'unidade' não existe na tabela 'materiais'.")
    
    # Fecha a conexão
    conn.close()

if __name__ == '__main__':
    # Registra execução da migração
    print(f"Executando migração em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Executa a migração
    upgrade()
    
    print("Migração concluída.") 