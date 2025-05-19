from models.database import db
from sqlalchemy import text

def upgrade():
    """
    Esta migração corrige o relacionamento entre ItemTracoConcreto e ConversaoUnidade.
    
    Alterações:
    1. Altera o tipo de campo conversao_unidade_id para INTEGER
    2. Adiciona a chave estrangeira referenciando a tabela conversoes_unidades
    """
    # Obter a conexão do SQLAlchemy
    connection = db.engine.connect()
    
    try:
        print("Iniciando migração para corrigir o relacionamento entre ItemTracoConcreto e ConversaoUnidade...")
        
        # Iniciar uma transação
        transaction = connection.begin()
        
        # Verificar se a coluna existe
        check_column_sql = text("SHOW COLUMNS FROM itens_traco_concreto LIKE 'conversao_unidade_id'")
        
        result = connection.execute(check_column_sql)
        column_info = result.fetchone()
        
        # Se a coluna existe, column_info não será None
        column_exists = column_info is not None
        column_type_correct = False
        
        if column_exists:
            # Verificar se o tipo é INTEGER
            # No MariaDB, a informação do tipo está no segundo elemento (índice 1)
            column_type = column_info[1]
            column_type_correct = 'int' in column_type.lower()
            print(f"Coluna encontrada com tipo: {column_type}")
        
        if not column_exists:
            # Se a coluna não existe, criar como INTEGER
            print("A coluna conversao_unidade_id não existe. Criando...")
            add_column_sql = text("""
            ALTER TABLE itens_traco_concreto 
            ADD COLUMN conversao_unidade_id INTEGER,
            ADD CONSTRAINT fk_conversao_unidade
            FOREIGN KEY (conversao_unidade_id) REFERENCES conversoes_unidades(id)
            """)
            connection.execute(add_column_sql)
        elif not column_type_correct:
            # Se a coluna existe mas é do tipo errado, modificar o tipo
            print("A coluna conversao_unidade_id existe mas tem o tipo errado. Corrigindo...")
            
            # Tentar modificar o tipo da coluna diretamente
            try:
                modify_column_sql = text("""
                ALTER TABLE itens_traco_concreto 
                MODIFY COLUMN conversao_unidade_id INTEGER
                """)
                connection.execute(modify_column_sql)
                
                # Adicionar a chave estrangeira se não existir
                # Verificar se a chave estrangeira existe
                check_fk_sql = text("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
                WHERE TABLE_NAME = 'itens_traco_concreto' 
                AND COLUMN_NAME = 'conversao_unidade_id' 
                AND REFERENCED_TABLE_NAME = 'conversoes_unidades'
                """)
                
                result = connection.execute(check_fk_sql)
                fk_exists = result.scalar() > 0
                
                if not fk_exists:
                    add_fk_sql = text("""
                    ALTER TABLE itens_traco_concreto
                    ADD CONSTRAINT fk_conversao_unidade
                    FOREIGN KEY (conversao_unidade_id) REFERENCES conversoes_unidades(id)
                    """)
                    connection.execute(add_fk_sql)
            except Exception as e:
                print(f"Erro ao modificar a coluna: {str(e)}")
                print("Tentando abordagem alternativa...")
                
                # Se a modificação direta falhar, usar abordagem de criar nova tabela
                # 1. Renomear a tabela atual
                rename_table_sql = text("""
                ALTER TABLE itens_traco_concreto RENAME TO itens_traco_concreto_old
                """)
                connection.execute(rename_table_sql)
                
                # 2. Criar a nova tabela com a estrutura correta
                create_table_sql = text("""
                CREATE TABLE itens_traco_concreto (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    traco_id INTEGER NOT NULL,
                    material_id INTEGER NOT NULL,
                    quantidade DECIMAL(10, 2) NOT NULL,
                    conversao_unidade_id INTEGER,
                    unidade VARCHAR(20) NOT NULL,
                    influenciado_umidade BOOLEAN DEFAULT 0,
                    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (traco_id) REFERENCES tracos_concreto(id) ON DELETE CASCADE,
                    FOREIGN KEY (material_id) REFERENCES materiais(id),
                    FOREIGN KEY (conversao_unidade_id) REFERENCES conversoes_unidades(id)
                )
                """)
                connection.execute(create_table_sql)
                
                # 3. Copiar os dados da tabela antiga para a nova
                copy_data_sql = text("""
                INSERT INTO itens_traco_concreto (
                    id, traco_id, material_id, quantidade, 
                    unidade, influenciado_umidade, criado_em
                )
                SELECT 
                    id, traco_id, material_id, quantidade, 
                    unidade, influenciado_umidade, criado_em
                FROM itens_traco_concreto_old
                """)
                connection.execute(copy_data_sql)
                
                # 4. Remover a tabela antiga
                drop_old_table_sql = text("""
                DROP TABLE itens_traco_concreto_old
                """)
                connection.execute(drop_old_table_sql)
        else:
            print("A coluna conversao_unidade_id já existe com o tipo correto.")
            
            # Verificar se existe a chave estrangeira
            check_fk_sql = text("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
            WHERE TABLE_NAME = 'itens_traco_concreto' 
            AND COLUMN_NAME = 'conversao_unidade_id' 
            AND REFERENCED_TABLE_NAME = 'conversoes_unidades'
            """)
            
            result = connection.execute(check_fk_sql)
            fk_exists = result.scalar() > 0
            
            if not fk_exists:
                print("Adicionando chave estrangeira...")
                add_fk_sql = text("""
                ALTER TABLE itens_traco_concreto
                ADD CONSTRAINT fk_conversao_unidade
                FOREIGN KEY (conversao_unidade_id) REFERENCES conversoes_unidades(id)
                """)
                connection.execute(add_fk_sql)
            else:
                print("A chave estrangeira já existe.")
            
        print("Migração concluída com sucesso!")
        
        # Confirmar a transação
        transaction.commit()
        
    except Exception as e:
        # Em caso de erro, reverter a transação
        if 'transaction' in locals():
            transaction.rollback()
        print(f"Erro durante a migração: {str(e)}")
        raise
    finally:
        # Fechar a conexão
        connection.close()
    
    return True

def downgrade():
    """
    Reverte as alterações feitas no upgrade
    """
    print("Downgrade não implementado para esta migração.")
    return True 