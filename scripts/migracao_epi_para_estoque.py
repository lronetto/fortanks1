#!/usr/bin/env python
"""
Script para migrar os dados de estoque dos EPIs existentes para o sistema de estoque principal.
Este script deve ser executado uma única vez após a atualização do código.
"""
from datetime import datetime
from decimal import Decimal
import sys
import os

# Adicionar o diretório pai ao path para poder importar os módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import db
from models.epi import EPI
from models.estoque import Estoque, MovimentacaoEstoque
from app import create_app

def migrar_epi_para_estoque():
    """
    Migra os dados de estoque dos EPIs existentes para o sistema de estoque principal.
    """
    print("Iniciando migração de EPIs para o sistema de estoque principal...")
    
    # Buscar todos os EPIs
    epis = EPI.query.all()
    print(f"Encontrados {len(epis)} EPIs para migração.")
    
    for epi in epis:
        # Verificar se já existe um registro no estoque para este EPI
        estoque = Estoque.query.filter_by(epi_id=epi.id, tipo_item='epi').first()
        
        if estoque:
            print(f"EPI #{epi.id} ({epi.material.nome}) já tem registro no estoque principal. Atualizando...")
            
            # Verificar se a quantidade atual está correta
            quantidade_atual = float(estoque.quantidade)
            if quantidade_atual != epi.estoque_atual:
                # Criar movimentação de ajuste
                mov = MovimentacaoEstoque(
                    estoque_id=estoque.id,
                    tipo_movimento='ajuste',
                    quantidade=epi.estoque_atual,
                    observacao='Migração do estoque de EPI para estoque principal',
                    origem_tipo='EPI',
                    origem_id=epi.id,
                    usuario_id=epi.usuario_id or 1  # Usar o ID do usuário do EPI ou 1 como padrão
                )
                db.session.add(mov)
                
                # Atualizar quantidade
                estoque.quantidade = Decimal(epi.estoque_atual)
                print(f"   - Ajustado estoque de {quantidade_atual} para {epi.estoque_atual}")
            
            # Atualizar estoque mínimo
            estoque.quantidade_minima = epi.estoque_minimo
            
        else:
            print(f"Criando novo registro de estoque para EPI #{epi.id} ({epi.material.nome})...")
            
            # Criar novo registro no estoque
            estoque = Estoque(
                epi_id=epi.id,
                tipo_item='epi',
                quantidade=epi.estoque_atual,
                quantidade_minima=epi.estoque_minimo,
                localizacao='Estoque EPI',
                usuario_id=epi.usuario_id or 1,  # Usar o ID do usuário do EPI ou 1 como padrão
                criado_em=datetime.now(),
                atualizado_em=datetime.now()
            )
            db.session.add(estoque)
            
            # Criar movimentação para registrar o estoque inicial
            if epi.estoque_atual > 0:
                mov = MovimentacaoEstoque(
                    estoque_id=estoque.id,
                    tipo_movimento='entrada',
                    quantidade=epi.estoque_atual,
                    observacao='Migração do estoque de EPI para estoque principal',
                    origem_tipo='EPI',
                    origem_id=epi.id,
                    usuario_id=epi.usuario_id or 1,  # Usar o ID do usuário do EPI ou 1 como padrão
                    data_movimento=datetime.now()
                )
                db.session.add(mov)
    
    # Salvar as alterações
    db.session.commit()
    print("Migração concluída com sucesso!")

if __name__ == '__main__':
    # Criar aplicação
    app = create_app()
    
    # Executar migração dentro do contexto da aplicação
    with app.app_context():
        migrar_epi_para_estoque() 