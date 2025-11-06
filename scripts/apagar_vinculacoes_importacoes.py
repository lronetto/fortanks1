"""
Script para apagar vinculações de itens de notas fiscais com materiais
e importações de movimentos de estoque relacionadas a notas fiscais.

Este script:
1. Remove vinculações de materiais dos itens de notas fiscais (material_id)
2. Limpa campos relacionados de vinculação (fator_conversao_aplicado)
3. Remove movimentações de estoque relacionadas a notas fiscais
4. Limpa campos de importação dos itens de notas fiscais
5. Reverte as quantidades no estoque quando remove as movimentações

Uso:
    # Simular apagamento de todas as vinculações
    python scripts/apagar_vinculacoes_importacoes.py
    
    # Apagar todas as vinculações
    python scripts/apagar_vinculacoes_importacoes.py --confirmar
    
    # Simular apagamento de vinculações de um material específico
    python scripts/apagar_vinculacoes_importacoes.py --material-id 123
    
    # Apagar vinculações de um material específico
    python scripts/apagar_vinculacoes_importacoes.py --confirmar --material-id 123

IMPORTANTE: Este script é destrutivo e não pode ser revertido!
Execute apenas se tiver certeza de que deseja apagar as vinculações e importações.
"""

import sys
import os

# Adicionar o diretório raiz ao path para importar os modelos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from models.database import db
from models.nota_fiscal import NotaFiscalItem, NotaFiscal
from models.estoque import MovimentacaoEstoque, Estoque
from models.material import Material
from config.config import Config
from datetime import datetime
from decimal import Decimal
import click


def criar_app():
    """Cria e configura a aplicação Flask"""
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def apagar_vinculacoes_importacoes(confirmar=False, material_id=None):
    """
    Apaga vinculações de itens de notas fiscais e importações de movimentos de estoque.
    
    Args:
        confirmar: Se True, executa a operação. Se False, apenas mostra estatísticas.
        material_id: ID do material específico. Se None, apaga todas as vinculações.
    
    Returns:
        dict: Estatísticas da operação
    """
    app = criar_app()
    
    with app.app_context():
        stats = {
            'itens_vinculados': 0,
            'movimentacoes_removidas': 0,
            'estoques_atualizados': 0,
            'erros': [],
            'material': None
        }
        
        try:
            # Verificar se o material existe se foi especificado
            material = None
            if material_id:
                material = Material.query.get(material_id)
                if not material:
                    raise ValueError(f"Material com ID {material_id} não encontrado")
                stats['material'] = {
                    'id': material.id,
                    'nome': material.nome,
                    'codigo': material.codigo or 'Sem código'
                }
                print(f"📦 Material selecionado: {material.codigo or 'Sem código'} - {material.nome}")
                print()
            
            # 1. Contar e remover vinculações de materiais nos itens de notas fiscais
            if material_id:
                print("📊 Analisando vinculações do material em itens de notas fiscais...")
            else:
                print("📊 Analisando vinculações de materiais em itens de notas fiscais...")
            
            query_itens = NotaFiscalItem.query.filter(
                NotaFiscalItem.material_id.isnot(None)
            )
            
            if material_id:
                query_itens = query_itens.filter(NotaFiscalItem.material_id == material_id)
            
            itens_vinculados = query_itens.all()
            
            stats['itens_vinculados'] = len(itens_vinculados)
            print(f"   Encontrados {len(itens_vinculados)} itens com material vinculado")
            
            if confirmar:
                print("   Removendo vinculações...")
                for item in itens_vinculados:
                    item.material_id = None
                    item.fator_conversao_aplicado = None
                    item.importado_estoque = False
                    item.data_importacao_estoque = None
                    item.usuario_importacao_id = None
                    item.movimentacao_estoque_id = None
                    item.status_importacao = 'Pendente'
                    item.tentativas_importacao = 0
                    item.ultima_tentativa_importacao = None
                    db.session.add(item)
                
                db.session.commit()
                print("   ✅ Vinculações removidas com sucesso!")
            else:
                print("   ⚠️  Modo simulação - nenhuma alteração foi feita")
            
            # 2. Contar e remover movimentações de estoque relacionadas a notas fiscais
            if material_id:
                print("\n📊 Analisando movimentações de estoque relacionadas ao material...")
            else:
                print("\n📊 Analisando movimentações de estoque relacionadas a notas fiscais...")
            
            # Buscar movimentações que têm nota_fiscal_item_id OU origem_tipo='NotaFiscal'
            query_mov = MovimentacaoEstoque.query.filter(
                db.or_(
                    MovimentacaoEstoque.nota_fiscal_item_id.isnot(None),
                    MovimentacaoEstoque.origem_tipo == 'NotaFiscal'
                )
            )
            
            # Se foi especificado um material, filtrar apenas movimentações dos itens desse material
            if material_id:
                # Buscar IDs dos itens de nota fiscal vinculados a esse material
                ids_itens_material = [item.id for item in itens_vinculados]
                
                if ids_itens_material:
                    query_mov = query_mov.filter(
                        MovimentacaoEstoque.nota_fiscal_item_id.in_(ids_itens_material)
                    )
                else:
                    # Se não há itens vinculados, não há movimentações para remover
                    query_mov = query_mov.filter(False)  # Query que não retorna nada
            
            movimentacoes_nf = query_mov.all()
            
            stats['movimentacoes_removidas'] = len(movimentacoes_nf)
            print(f"   Encontradas {len(movimentacoes_nf)} movimentações relacionadas a notas fiscais")
            
            if confirmar:
                print("   Removendo movimentações e revertendo estoques...")
                
                # Agrupar por estoque_id para atualizar quantidades corretamente
                estoques_afetados = set()
                
                # Processar em lotes para evitar problemas de memória
                batch_size = 100
                total_processadas = 0
                
                for i in range(0, len(movimentacoes_nf), batch_size):
                    batch = movimentacoes_nf[i:i+batch_size]
                    
                    for mov in batch:
                        estoque_id = mov.estoque_id
                        estoques_afetados.add(estoque_id)
                        
                        # Reverter a movimentação no estoque antes de deletar
                        estoque = mov.estoque
                        if estoque:
                            # Converter quantidade para Decimal se necessário
                            qtd_mov = Decimal(str(mov.quantidade)) if mov.quantidade else Decimal('0')
                            qtd_estoque = Decimal(str(estoque.quantidade)) if estoque.quantidade else Decimal('0')
                            
                            # Reverter a movimentação no estoque
                            if mov.tipo_movimento == 'entrada':
                                qtd_estoque -= qtd_mov
                                if qtd_estoque < 0:
                                    qtd_estoque = Decimal('0')
                            elif mov.tipo_movimento == 'saida':
                                qtd_estoque += qtd_mov
                            # Para ajuste, não fazemos nada pois não temos a quantidade anterior
                            
                            estoque.quantidade = qtd_estoque
                            db.session.add(estoque)
                        
                        db.session.delete(mov)
                        total_processadas += 1
                    
                    # Commit em lotes
                    db.session.commit()
                    print(f"   Processadas {total_processadas}/{len(movimentacoes_nf)} movimentações...")
                
                stats['estoques_atualizados'] = len(estoques_afetados)
                print(f"   ✅ {len(movimentacoes_nf)} movimentações removidas")
                print(f"   ✅ {len(estoques_afetados)} estoques atualizados")
            else:
                print("   ⚠️  Modo simulação - nenhuma alteração foi feita")
            
            # 3. Verificar se há itens com campos de importação ainda preenchidos
            print("\n📊 Verificando campos de importação restantes...")
            query_importacao = NotaFiscalItem.query.filter(
                db.or_(
                    NotaFiscalItem.importado_estoque == True,
                    NotaFiscalItem.movimentacao_estoque_id.isnot(None),
                    NotaFiscalItem.data_importacao_estoque.isnot(None)
                )
            )
            
            # Se foi especificado um material, filtrar pelos IDs dos itens (mesmo após remover vinculações)
            if material_id:
                ids_itens_material = [item.id for item in itens_vinculados]
                if ids_itens_material:
                    query_importacao = query_importacao.filter(NotaFiscalItem.id.in_(ids_itens_material))
                else:
                    # Se não há itens vinculados, não há campos de importação para limpar
                    query_importacao = query_importacao.filter(False)  # Query que não retorna nada
            
            itens_com_importacao = query_importacao.count()
            
            if itens_com_importacao > 0:
                if material_id:
                    print(f"   ⚠️  Ainda há {itens_com_importacao} itens deste material com campos de importação preenchidos")
                else:
                    print(f"   ⚠️  Ainda há {itens_com_importacao} itens com campos de importação preenchidos")
                if confirmar:
                    print("   Limpando campos de importação restantes...")
                    itens_para_limpar = query_importacao.all()
                    
                    for item in itens_para_limpar:
                        item.importado_estoque = False
                        item.data_importacao_estoque = None
                        item.usuario_importacao_id = None
                        item.movimentacao_estoque_id = None
                        item.status_importacao = 'Pendente'
                        item.tentativas_importacao = 0
                        item.ultima_tentativa_importacao = None
                        db.session.add(item)
                    
                    db.session.commit()
                    print("   ✅ Campos de importação limpos!")
            else:
                print("   ✅ Nenhum campo de importação encontrado")
            
            if confirmar:
                print("\n" + "="*60)
                print("✅ OPERAÇÃO CONCLUÍDA COM SUCESSO!")
                print("="*60)
                if material_id:
                    print(f"📦 Material: {stats['material']['codigo']} - {stats['material']['nome']}")
                print(f"📋 Estatísticas:")
                print(f"   - Itens desvinculados: {stats['itens_vinculados']}")
                print(f"   - Movimentações removidas: {stats['movimentacoes_removidas']}")
                print(f"   - Estoques atualizados: {stats['estoques_atualizados']}")
            else:
                print("\n" + "="*60)
                print("📊 SIMULAÇÃO CONCLUÍDA")
                print("="*60)
                if material_id:
                    print(f"📦 Material: {stats['material']['codigo']} - {stats['material']['nome']}")
                print(f"📋 Estatísticas (se executado):")
                print(f"   - Itens que seriam desvinculados: {stats['itens_vinculados']}")
                print(f"   - Movimentações que seriam removidas: {stats['movimentacoes_removidas']}")
                print(f"   - Estoques que seriam atualizados: {stats['estoques_atualizados']}")
                print("\n⚠️  Para executar a operação, use: --confirmar")
            
            return stats
            
        except Exception as e:
            error_msg = f"Erro ao apagar vinculações e importações: {str(e)}"
            stats['erros'].append(error_msg)
            print(f"\n❌ ERRO: {error_msg}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            raise


@click.command()
@click.option('--confirmar', is_flag=True, help='Confirma e executa a operação (sem isso, apenas simula)')
@click.option('--material-id', type=int, help='ID do material específico. Se não fornecido, apaga todas as vinculações.')
def main(confirmar, material_id):
    """
    Script para apagar vinculações de itens de notas fiscais e importações de movimentos de estoque.
    
    Este script é DESTRUTIVO e não pode ser revertido!
    
    Use --confirmar para executar a operação, ou sem essa flag para apenas simular.
    Use --material-id para apagar vinculações de um material específico, ou omita para apagar todas.
    """
    print("="*60)
    if material_id:
        print("🗑️  APAGAR VINCULAÇÕES DE MATERIAL ESPECÍFICO")
    else:
        print("🗑️  APAGAR VINCULAÇÕES E IMPORTAÇÕES DE NOTAS FISCAIS")
    print("="*60)
    print()
    
    if not confirmar:
        print("⚠️  MODO SIMULAÇÃO - Nenhuma alteração será feita")
        print("   Use --confirmar para executar a operação")
        print()
    else:
        print("⚠️  ATENÇÃO: Esta operação é DESTRUTIVA e IRREVERSÍVEL!")
        print("   Você está prestes a apagar:")
        if material_id:
            print(f"   - Todas as vinculações do material ID {material_id} nos itens de notas fiscais")
            print(f"   - Todas as movimentações de estoque relacionadas a esse material")
            print(f"   - Todos os campos de importação dos itens desse material")
        else:
            print("   - Todas as vinculações de materiais nos itens de notas fiscais")
            print("   - Todas as movimentações de estoque relacionadas a notas fiscais")
            print("   - Todos os campos de importação dos itens de notas fiscais")
        print()
        
        resposta = input("   Digite 'SIM' para confirmar: ")
        if resposta != 'SIM':
            print("   ❌ Operação cancelada pelo usuário")
            return
    
    try:
        stats = apagar_vinculacoes_importacoes(confirmar=confirmar, material_id=material_id)
        
        if confirmar:
            print("\n✅ Operação concluída com sucesso!")
        else:
            if material_id:
                print(f"\n💡 Para executar a operação, use: python scripts/apagar_vinculacoes_importacoes.py --confirmar --material-id {material_id}")
            else:
                print("\n💡 Para executar a operação, use: python scripts/apagar_vinculacoes_importacoes.py --confirmar")
            
    except Exception as e:
        print(f"\n❌ Erro ao executar script: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()

