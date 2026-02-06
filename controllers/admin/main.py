from flask import render_template, request
from flask_login import login_required
from datetime import datetime
import logging
from sqlalchemy import text, inspect

from controllers.admin import admin_bp, PERMISSOES_DISPONIVEL
from models.database import db
from models.logs import Logs
from scripts.processar_email1 import processar_emails

logger = logging.getLogger(__name__)

@admin_bp.route('/')
def index():
    """
    Página inicial da área administrativa com resumo das tabelas do banco de dados
    """
    try:
        # Obter todas as tabelas do banco de dados
        inspector = inspect(db.engine)
        tabelas = inspector.get_table_names()
        
        tabelas_info = []
        uploads_por_tipo = {}
        
        # Mapeamento de tipos de upload
        tipos_upload = {
            0: 'Não definido',
            1: 'Arquivei',
            2: 'Protocolo',
            3: 'Reembolso',
            4: 'Avulso',
            5: 'Certificado'
        }
        
        # Para cada tabela, obter informações
        for tabela in sorted(tabelas):
            try:
                # Contar registros
                count_query = text(f"SELECT COUNT(*) as total FROM `{tabela}`")
                result = db.session.execute(count_query)
                total_registros = result.scalar() or 0
                
                # Obter tamanho da tabela (MySQL)
                size_query = text("""
                    SELECT 
                        ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
                    FROM information_schema.TABLES 
                    WHERE table_schema = DATABASE()
                    AND table_name = :table_name
                """)
                size_result = db.session.execute(size_query, {'table_name': tabela})
                size_row = size_result.fetchone()
                tamanho_mb = float(size_row[0]) if size_row and size_row[0] else 0.0
                
                tabelas_info.append({
                    'nome': tabela,
                    'total_registros': total_registros,
                    'tamanho_mb': tamanho_mb
                })
                
                # Se for a tabela Uploads, obter informações por tipo
                if tabela == 'Uploads':
                    tipo_query = text("""
                        SELECT 
                            tipo,
                            COUNT(*) as total,
                            ROUND(SUM(LENGTH(`blob`)) / 1024 / 1024, 2) as tamanho_mb
                        FROM Uploads
                        GROUP BY tipo
                        ORDER BY tipo
                    """)
                    tipo_result = db.session.execute(tipo_query)
                    for row in tipo_result:
                        tipo = row[0] if row[0] is not None else 0
                        total = row[1]
                        tamanho = float(row[2]) if row[2] else 0.0
                        tipo_nome = tipos_upload.get(tipo, f'Tipo {tipo}')
                        uploads_por_tipo[tipo_nome] = {
                            'total': total,
                            'tamanho_mb': tamanho
                        }
                    
                    # Adicionar total de registros sem tipo
                    sem_tipo_query = text("""
                        SELECT 
                            COUNT(*) as total,
                            ROUND(SUM(LENGTH(`blob`)) / 1024 / 1024, 2) as tamanho_mb
                        FROM Uploads 
                        WHERE tipo IS NULL
                    """)
                    sem_tipo_result = db.session.execute(sem_tipo_query)
                    sem_tipo_row = sem_tipo_result.fetchone()
                    if sem_tipo_row and sem_tipo_row[0] and sem_tipo_row[0] > 0:
                        uploads_por_tipo['Sem tipo'] = {
                            'total': sem_tipo_row[0],
                            'tamanho_mb': float(sem_tipo_row[1]) if sem_tipo_row[1] else 0.0
                        }
                
            except Exception as e:
                logger.warning(f"Erro ao obter informações da tabela {tabela}: {str(e)}")
                tabelas_info.append({
                    'nome': tabela,
                    'total_registros': 0,
                    'tamanho_mb': 0.0,
                    'erro': str(e)
                })
        
        # Calcular totais gerais
        total_registros_geral = sum(t['total_registros'] for t in tabelas_info)
        total_tamanho_geral = sum(t['tamanho_mb'] for t in tabelas_info)
        
        # Ordenar tabelas por tamanho (maior primeiro)
        tabelas_info.sort(key=lambda x: x['tamanho_mb'], reverse=True)
        
        return render_template('admin/index.html',
                            tabelas_info=tabelas_info,
                            uploads_por_tipo=uploads_por_tipo,
                            total_registros_geral=total_registros_geral,
                            total_tamanho_geral=total_tamanho_geral,
                            total_tabelas=len(tabelas_info))
    
    except Exception as e:
        logger.error(f"Erro ao carregar página de admin: {str(e)}")
        from flask import flash
        flash(f'Erro ao carregar informações do banco de dados: {str(e)}', 'error')
        return render_template('admin/index.html',
                            tabelas_info=[],
                            uploads_por_tipo={},
                            total_registros_geral=0,
                            total_tamanho_geral=0.0,
                            total_tabelas=0)

@admin_bp.route('/configuracoes')
def configuracoes():
    """
    Página de configurações do sistema
    """
    return render_template('admin/configuracoes.html')

@admin_bp.route('/logs')
def logs():
    """
    Página de logs do sistema
    """
    # Parâmetros de paginação
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Parâmetros de filtro
    local_filtro = request.args.get('local', '').strip()
    data_inicial = request.args.get('data_inicial', '')
    data_final = request.args.get('data_final', '')
    
    # Construir query base
    query = Logs.query
    
    # Aplicar filtros
    if local_filtro:
        query = query.filter(Logs.local.ilike(f'%{local_filtro}%'))
    
    if data_inicial:
        try:
            data_inicial_obj = datetime.strptime(data_inicial, '%Y-%m-%d')
            query = query.filter(Logs.data >= data_inicial_obj)
        except ValueError:
            pass
    
    if data_final:
        try:
            data_final_obj = datetime.strptime(data_final, '%Y-%m-%d')
            # Adicionar 23:59:59 para incluir o dia inteiro
            data_final_obj = data_final_obj.replace(hour=23, minute=59, second=59)
            query = query.filter(Logs.data <= data_final_obj)
        except ValueError:
            pass
    
    # Ordenar por data (mais recente primeiro)
    query = query.order_by(Logs.data.desc())
    
    # Aplicar paginação
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    logs = pagination.items
    
    return render_template('admin/logs.html', 
                         logs=logs, 
                         pagination=pagination)

@admin_bp.route('/backup')
def backup():
    """
    Página de backup do sistema
    """
    # Aqui você pode implementar a lógica para realizar backups do banco de dados
    return render_template('admin/backup.html')
@admin_bp.route('/teste1')
def teste1():
    """
    Teste 1
    """
    processar_emails()
    return 'Teste 1'