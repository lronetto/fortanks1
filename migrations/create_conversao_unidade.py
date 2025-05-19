"""
Script de migração para criar a tabela de conversões de unidades.
"""
from datetime import datetime
import sqlite3
import os

# Caminho do arquivo do banco de dados
DB_PATH = os.path.join('fortanks', 'fortanks.db')

def up():
    """
    Cria a tabela de conversões de unidades.
    """
    print("Iniciando migração para criar tabela de conversões de unidades...")
    
    try:
        # Conecta ao banco de dados
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Cria a tabela
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversoes_unidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            unidade_entrada TEXT NOT NULL,
            unidade_saida TEXT NOT NULL,
            fator REAL NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Insere alguns dados iniciais
        dados_iniciais = [
            ('Quilograma para Grama', 'kg', 'g', 1000.0),
            ('Grama para Quilograma', 'g', 'kg', 0.001),
            ('Tonelada para Quilograma', 't', 'kg', 1000.0),
            ('Quilograma para Tonelada', 'kg', 't', 0.001),
            ('Metro cúbico para Litro', 'm³', 'l', 1000.0),
            ('Litro para Metro cúbico', 'l', 'm³', 0.001),
            ('Litro para Mililitro', 'l', 'ml', 1000.0),
            ('Mililitro para Litro', 'ml', 'l', 0.001)
        ]
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for nome, entrada, saida, fator in dados_iniciais:
            cursor.execute('''
            INSERT INTO conversoes_unidades (nome, unidade_entrada, unidade_saida, fator, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (nome, entrada, saida, fator, now, now))
        
        # Commit das alterações
        conn.commit()
        print("Tabela de conversões de unidades criada com sucesso!")
        
    except Exception as e:
        print(f"Erro ao criar tabela de conversões de unidades: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def down():
    """
    Remove a tabela de conversões de unidades.
    """
    print("Revertendo migração de tabela de conversões de unidades...")
    
    try:
        # Conecta ao banco de dados
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Remove a tabela
        cursor.execute('DROP TABLE IF EXISTS conversoes_unidades')
        
        # Commit das alterações
        conn.commit()
        print("Tabela de conversões de unidades removida com sucesso!")
        
    except Exception as e:
        print(f"Erro ao remover tabela de conversões de unidades: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    # Execute a migração
    up() 