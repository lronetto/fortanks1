"""
Migração para alterar o tipo do campo numero_tanque na tabela pecas de String para Integer

Data de Criação: 2025-03-16
"""

from datetime import datetime
from models.database import db
from sqlalchemy import text, exc

def upgrade():
    """
    Executa a migração para converter numero_tanque para Integer
    """
    try:
        # Primeiro verifica se a coluna existe
        try:
            check_query = text("SHOW COLUMNS FROM pecas LIKE 'numero_tanque'")
            result = db.session.execute(check_query).fetchone()
            
            if result:
                # A coluna existe, então altera o tipo
                query = text("""
                ALTER TABLE pecas
                MODIFY COLUMN numero_tanque INTEGER NULL;
                """)
                db.session.execute(query)
                print("Migração concluída com sucesso: Alterado tipo do campo numero_tanque para INTEGER")
            else:
                # A coluna não existe, então adiciona
                query = text("""
                ALTER TABLE pecas
                ADD COLUMN numero_tanque INTEGER NULL;
                """)
                db.session.execute(query)
                print("Migração concluída com sucesso: Adicionado campo numero_tanque como INTEGER")
        except exc.SQLAlchemyError as e:
            # Se ocorrer erro ao verificar, tenta adicionar a coluna diretamente
            try:
                query = text("""
                ALTER TABLE pecas
                ADD COLUMN numero_tanque INTEGER NULL;
                """)
                db.session.execute(query)
                print("Migração concluída com sucesso: Adicionado campo numero_tanque como INTEGER")
            except exc.SQLAlchemyError as add_error:
                # Se ocorrer erro ao adicionar, tenta modificar
                query = text("""
                ALTER TABLE pecas
                MODIFY COLUMN numero_tanque INTEGER NULL;
                """)
                db.session.execute(query)
                print("Migração concluída com sucesso: Alterado tipo do campo numero_tanque para INTEGER")
                
        db.session.commit()
        
        # Registra a migração
        registrar_migracao()
        
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Erro durante a migração: {str(e)}")
        return False

def downgrade():
    """
    Reverte a migração, voltando numero_tanque para VARCHAR
    """
    try:
        # Verifica se a coluna existe
        check_query = text("SHOW COLUMNS FROM pecas LIKE 'numero_tanque'")
        result = db.session.execute(check_query).fetchone()
        
        if result:
            # A coluna existe, então altera o tipo
            query = text("""
            ALTER TABLE pecas
            MODIFY COLUMN numero_tanque VARCHAR(50) NULL;
            """)
            db.session.execute(query)
            print("Downgrade concluído com sucesso: Alterado tipo do campo numero_tanque para VARCHAR(50)")
            db.session.commit()
        else:
            print("A coluna numero_tanque não existe, nada a fazer.")
        
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Erro durante o downgrade: {str(e)}")
        return False

def registrar_migracao():
    """
    Registra a migração na tabela de controle de migrações, se existir
    """
    try:
        # Verifica se a tabela de migrações existe
        query = text("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            data_execucao DATETIME NOT NULL,
            descricao TEXT NULL
        );
        """)
        db.session.execute(query)
        
        # Insere o registro da migração
        query = text("""
        INSERT INTO migrations (nome, data_execucao, descricao)
        VALUES (:nome, :data, :descricao);
        """)
        db.session.execute(
            query,
            {
                'nome': 'alterar_tipo_numero_tanque',
                'data': datetime.now(),
                'descricao': 'Alteração do tipo do campo numero_tanque na tabela pecas de VARCHAR(50) para INTEGER'
            }
        )
        db.session.commit()
    except Exception as e:
        print(f"Aviso: Não foi possível registrar a migração: {str(e)}")
        # Não interrompemos o processo se o registro falhar

if __name__ == "__main__":
    # Se executado diretamente, rodar o upgrade
    upgrade() 