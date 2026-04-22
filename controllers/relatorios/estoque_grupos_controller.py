from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, send_file
from flask_login import login_required
from models.estoque import Estoque
from models.material import MateriaisGrupos
from models.database import db
from datetime import datetime
from decimal import Decimal
import logging
import io
import pandas as pd
from weasyprint import HTML, CSS
import os
from utils.utils import parse_dados_json

# Configuração do logger
logger = logging.getLogger(__name__)

# Criar blueprint
estoque_grupos_bp = Blueprint('relatorios_estoque_grupos', __name__, url_prefix='/relatorios/estoque-grupos')

@estoque_grupos_bp.route('/api/filtros')
@login_required
def api_filtros():
    """
    API para retornar grupos e localizações para o modal
    """
    try:
        grupos = MateriaisGrupos.query.filter_by(ativo=True).order_by(MateriaisGrupos.nome).all()
        localizacoes = db.session.query(Estoque.localizacao).filter(
            Estoque.localizacao != None,
            Estoque.localizacao != ''
        ).distinct().order_by(Estoque.localizacao).all()
        
        return jsonify({
            'success': True,
            'grupos': [{'id': g.id, 'nome': g.nome} for g in grupos],
            'localizacoes': [loc[0] for loc in localizacoes]
        })
    except Exception as e:
        logger.error(f"Erro ao buscar filtros do relatório: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@estoque_grupos_bp.route('/')
@login_required
def index():
    """
    Relatório de estoque agrupado por grupo de material
    """
    try:
        # Parâmetros de filtro
        data_filtro = request.args.get('data_filtro', '')
        grupo_id = request.args.get('grupo_id', type=int)
        localizacao_filtro = request.args.get('localizacao_filtro', '').strip()
        
        # Converter data se fornecida
        data_filtro_dt = None
        if data_filtro:
            try:
                data_filtro_dt = datetime.strptime(data_filtro, '%Y-%m-%d')
            except ValueError:
                data_filtro_dt = None
        
        # Buscar todos os grupos de materiais
        grupos = MateriaisGrupos.query.filter_by(ativo=True).order_by(MateriaisGrupos.nome).all()
        
        # Obter lista de localizações únicas para o filtro
        localizacoes = db.session.query(Estoque.localizacao).filter(
            Estoque.localizacao != None,
            Estoque.localizacao != ''
        ).distinct().order_by(Estoque.localizacao).all()
        
        # Dados do relatório
        dados_relatorio = []
        
        # Se um grupo específico foi selecionado, filtrar
        grupos_filtrados = [g for g in grupos if not grupo_id or g.id == grupo_id]
        
        for grupo in grupos_filtrados:
            # Buscar materiais do grupo ordenados pelo nome
            materiais_grupo = sorted(grupo.materiais, key=lambda m: m.nome or '')
            
            itens_grupo = []
            quantidade_total_grupo = Decimal('0.0')
            
            for material in materiais_grupo:
                # Buscar estoques do material
                query_estoques = Estoque.query.filter_by(
                    material_id=material.id,
                    tipo_item='material'
                )
                
                # Aplicar filtro de localização se fornecido
                if localizacao_filtro:
                    query_estoques = query_estoques.filter(Estoque.localizacao == localizacao_filtro)
                
                estoques = query_estoques.all()
                
                quantidade_total_material = Decimal('0.0')
                localizacoes_material = []
                
                for estoque in estoques:
                    # Calcular saldo até a data filtro
                    if data_filtro_dt:
                        saldo = estoque.get_saldo_ate_data(data_fim=data_filtro_dt)
                    else:
                        saldo = estoque.get_saldo_real()
                    
                    quantidade_total_material += saldo
                    
                    if estoque.localizacao:
                        localizacoes_material.append(estoque.localizacao)
                
               
                itens_grupo.append({
                    'material_id': material.id,
                    'codigo': str(parse_dados_json(material.dados_adicionais).get("codigo_alterdata") or ''),
                    'nome': material.nome,
                    'categoria': material.categoria or '',
                    'unidade': material.get_unidade_nome() or '',
                    'quantidade': float(quantidade_total_material),
                    'localizacoes': ', '.join(set(localizacoes_material)) if localizacoes_material else 'Não especificado'
                })
                quantidade_total_grupo += quantidade_total_material
            
            if itens_grupo or not grupo_id:
                dados_relatorio.append({
                    'grupo_id': grupo.id,
                    'grupo_nome': grupo.nome,
                    'grupo_codigo': grupo.codigo or '',
                    'grupo_cor': grupo.cor or '#6c757d',
                    'grupo_icone': grupo.icone or 'fas fa-boxes',
                    'quantidade_total': float(quantidade_total_grupo),
                    'total_itens': len(itens_grupo),
                    'itens': itens_grupo
                })
        
        # Verificar se é uma requisição AJAX (para carregar no modal)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if is_ajax:
            # Retornar apenas o conteúdo do relatório para inserir no modal
            return render_template('relatorios/estoque/conteudo.html',
                                 dados_relatorio=dados_relatorio,
                                 data_filtro=data_filtro)
        
        return render_template('relatorios/estoque/index.html',
                             dados_relatorio=dados_relatorio,
                             grupos=grupos,
                             localizacoes=localizacoes,
                             data_filtro=data_filtro,
                             grupo_id=grupo_id,
                             localizacao_filtro=localizacao_filtro)
    
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de grupos: {str(e)}")
        flash('Erro ao gerar relatório.', 'error')
        return redirect(url_for('estoque.index'))

@estoque_grupos_bp.route('/exportar-excel')
@login_required
def exportar_excel():
    """
    Exporta relatório de estoque por grupo de material para Excel
    """
    try:
        data_filtro = request.args.get('data_filtro', '')
        grupo_id = request.args.get('grupo_id', type=int)
        localizacao_filtro = request.args.get('localizacao_filtro', '').strip()
        
        # Converter data se fornecida
        data_filtro_dt = None
        if data_filtro:
            try:
                data_filtro_dt = datetime.strptime(data_filtro, '%Y-%m-%d')
            except ValueError:
                data_filtro_dt = None
        
        # Buscar grupos
        grupos = MateriaisGrupos.query.filter_by(ativo=True).order_by(MateriaisGrupos.nome).all()
        grupos_filtrados = [g for g in grupos if not grupo_id or g.id == grupo_id]
        
        # Preparar dados para Excel
        dados_excel = []
        
        for grupo in grupos_filtrados:
            for material in grupo.materiais:
                if not material.ativo:
                    continue
                
                query_estoques = Estoque.query.filter_by(
                    material_id=material.id,
                    tipo_item='material'
                )
                
                # Aplicar filtro de localização se fornecido
                if localizacao_filtro:
                    query_estoques = query_estoques.filter(Estoque.localizacao == localizacao_filtro)
                
                estoques = query_estoques.all()
                
                quantidade_total = Decimal('0.0')
                localizacoes = []
                
                for estoque in estoques:
                    if data_filtro_dt:
                        saldo = estoque.get_saldo_ate_data(data_fim=data_filtro_dt)
                    else:
                        saldo = estoque.get_saldo_real()
                    
                    quantidade_total += saldo
                    if estoque.localizacao:
                        localizacoes.append(estoque.localizacao)
                
                # Só adicionar se tiver quantidade ou se não tiver filtro de localização
                extras = parse_dados_json(material.dados_adicionais)
                dados_excel.append({
                    'codigo_alterdata': str(extras.get("codigo_alterdata") or '').replace(".0", ""),
                    'nome': material.nome,
                    'unidade': material.get_unidade_nome() or '',
                    'estoque': float(quantidade_total),
                })
        
        # Criar DataFrame
        df = pd.DataFrame(dados_excel)
        
        # Criar buffer Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Estoque por Grupo')
        
        excel_buffer.seek(0)
        
        # Nome do arquivo
        nome_arquivo = 'relatorio_estoque_grupos'
        if data_filtro:
            nome_arquivo += f'_{data_filtro}'
        nome_arquivo += '.xlsx'
        
        return send_file(
            excel_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=nome_arquivo
        )
    
    except Exception as e:
        logger.error(f"Erro ao exportar relatório Excel: {str(e)}")
        flash('Erro ao exportar relatório para Excel.', 'error')
        return redirect(url_for('relatorios_estoque_grupos.index'))

@estoque_grupos_bp.route('/exportar-pdf')
@login_required
def exportar_pdf():
    """
    Exporta relatório de estoque por grupo de material para PDF
    """
    try:
        data_filtro = request.args.get('data_filtro', '')
        grupo_id = request.args.get('grupo_id', type=int)
        localizacao_filtro = request.args.get('localizacao_filtro', '').strip()
        
        # Converter data se fornecida
        data_filtro_dt = None
        if data_filtro:
            try:
                data_filtro_dt = datetime.strptime(data_filtro, '%Y-%m-%d')
            except ValueError:
                data_filtro_dt = None
        
        # Buscar grupos
        grupos = MateriaisGrupos.query.filter_by(ativo=True).order_by(MateriaisGrupos.nome).all()
        grupos_filtrados = [g for g in grupos if not grupo_id or g.id == grupo_id]
        
        # Preparar dados do relatório
        dados_relatorio = []
        
        for grupo in grupos_filtrados:
            materiais_grupo = grupo.materiais
            
            itens_grupo = []
            quantidade_total_grupo = Decimal('0.0')
            
            for material in materiais_grupo:
                if not material.ativo:
                    continue
                
                query_estoques = Estoque.query.filter_by(
                    material_id=material.id,
                    tipo_item='material'
                )
                
                # Aplicar filtro de localização se fornecido
                if localizacao_filtro:
                    query_estoques = query_estoques.filter(Estoque.localizacao == localizacao_filtro)
                
                estoques = query_estoques.all()
                
                quantidade_total_material = Decimal('0.0')
                localizacoes = []
                
                for estoque in estoques:
                    if data_filtro_dt:
                        saldo = estoque.get_saldo_ate_data(data_fim=data_filtro_dt)
                    else:
                        saldo = estoque.get_saldo_real()
                    
                    quantidade_total_material += saldo
                    if estoque.localizacao:
                        localizacoes.append(estoque.localizacao)
                
                # Só adicionar se tiver quantidade ou se não tiver filtro de localização
                if quantidade_total_material > 0 or not localizacao_filtro:
                    itens_grupo.append({
                        'material_id': material.id,
                        'codigo': str(parse_dados_json(material.dados_adicionais).get("codigo_sox") or ''),
                        'nome': material.nome,
                        'categoria': material.categoria or '',
                        'unidade': material.get_unidade_nome() or '',
                        'quantidade': float(quantidade_total_material),
                        'localizacoes': ', '.join(set(localizacoes)) if localizacoes else 'Não especificado'
                    })
                    quantidade_total_grupo += quantidade_total_material
            
            if itens_grupo or not grupo_id:
                dados_relatorio.append({
                    'grupo_id': grupo.id,
                    'grupo_nome': grupo.nome,
                    'grupo_codigo': grupo.codigo or '',
                    'grupo_cor': grupo.cor or '#6c757d',
                    'quantidade_total': float(quantidade_total_grupo),
                    'total_itens': len(itens_grupo),
                    'itens': itens_grupo
                })
        
        # Caminho da logo
        logo_path = os.path.abspath(os.path.join('static', 'img', 'logo.png'))
        logo_path_uri = 'file:///' + logo_path.replace('\\', '/')
        
        # Renderizar template PDF
        html = render_template('relatorios/estoque/pdf.html',
                             dados_relatorio=dados_relatorio,
                             data_filtro=data_filtro,
                             data_filtro_formatada=datetime.strptime(data_filtro, '%Y-%m-%d').strftime('%d/%m/%Y') if data_filtro else 'Atual',
                             now=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                             logo_path=logo_path_uri)
        
        # Gerar PDF
        pdf_bytes = HTML(string=html).write_pdf(
            stylesheets=[CSS(string='body { font-family: Arial, sans-serif; }')]
        )
        
        pdf_io = io.BytesIO(pdf_bytes)
        pdf_io.seek(0)
        
        # Nome do arquivo
        nome_arquivo = 'relatorio_estoque_grupos'
        if data_filtro:
            nome_arquivo += f'_{data_filtro}'
        nome_arquivo += '.pdf'
        
        return send_file(
            pdf_io,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=nome_arquivo
        )
    
    except Exception as e:
        logger.error(f"Erro ao exportar relatório PDF: {str(e)}")
        flash('Erro ao exportar relatório para PDF.', 'error')
        return redirect(url_for('relatorios_estoque_grupos.index'))

