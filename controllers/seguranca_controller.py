from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models.epi import EPI, EntregaEPI
from models.material import Material
from models.colaborador import Colaborador
from models.database import db
from models.estoque import Estoque, MovimentacaoEstoque
from utils.ca_scraper import consultar_ca
from datetime import datetime, timedelta, date
import json
import logging
import pandas as pd
import os
import tempfile
from werkzeug.utils import secure_filename
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from io import BytesIO
try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
except ImportError:
    HTML = None
    CSS = None
    FontConfiguration = None
    # Adicionar um log ou aviso se WeasyPrint não estiver instalado
    print("AVISO: WeasyPrint não está instalado. A geração de PDF não funcionará.")
import zipfile
from sqlalchemy.orm import joinedload

seguranca_bp = Blueprint('seguranca', __name__)

# Middleware para verificar se o usuário tem permissão
#
# @seguranca_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_gerente_ou_superior:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

# Rotas para EPI
@seguranca_bp.route('/epis')
@login_required
def epis_index():
    """
    Lista todos os EPIs cadastrados
    """
    epis = EPI.query.all()
    
    # Classificar por status de estoque e validade
    epis_por_status = {
        "critico": [],
        "atencao": [],
        "normal": []
    }
    
    for epi in epis:
        # Verificar estoque atual usando o método get_estoque_atual
        # que busca a informação do estoque principal
        if epi.status_estoque == "Esgotado" or epi.status_validade == "Vencido":
            epis_por_status["critico"].append(epi)
        elif epi.status_estoque == "Crítico" or epi.status_validade == "Próximo ao vencimento":
            epis_por_status["atencao"].append(epi)
        else:
            epis_por_status["normal"].append(epi)
    
    # Buscar materiais para o formulário do modal
    materiais = Material.query.filter(Material.categoria == 'EPI').all()
    
    # Buscar colaboradores para o modal de entregas
    colaboradores = Colaborador.query.all()
    
    return render_template('seguranca/epis/index.html', 
                           epis=epis, 
                           epis_por_status=epis_por_status,
                           materiais=materiais,
                           colaboradores=colaboradores,
                           now1=datetime.now()) 

@seguranca_bp.route('/epis/novo', methods=['GET', 'POST'])
@login_required
def epi_novo():
    """
    Cadastra um novo EPI
    """
    if request.method == 'POST':
        # Verificar se é uma requisição AJAX
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Implementação da lógica para salvar um novo EPI
        material_id = request.form.get('material_id')
        ca_numero = request.form.get('ca_numero')
        data_validade = request.form.get('data_validade')
        vida_util_meses = request.form.get('vida_util_meses')
        estoque_atual = request.form.get('estoque_atual')
        estoque_minimo = request.form.get('estoque_minimo')

        # Validar os dados
        if not material_id:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Material é obrigatório'})
            flash('Material é obrigatório', 'danger')
            return redirect(url_for('seguranca.epis_index'))

        # Verificar se já existe EPI cadastrado para este material
        epi_existente = EPI.query.filter_by(material_id=material_id).first()
        if epi_existente:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Já existe um EPI cadastrado para o material selecionado'})
            flash('Já existe um EPI cadastrado para o material selecionado', 'danger')
            return render_template('seguranca/epis/novo.html', materiais=materiais, now1=datetime.now())

        # Criar o novo EPI
        epi = EPI()
        epi.material_id = material_id
        epi.ca_numero = ca_numero

        if data_validade:
            epi.data_validade = datetime.strptime(
                data_validade, '%Y-%m-%d').date()

        if vida_util_meses:
            epi.vida_util_meses = int(vida_util_meses)

        # O campo estoque_atual não é mais usado diretamente,
        # mas será atualizado através do estoque principal
        estoque_quantidade = 0
        if estoque_atual:
            estoque_quantidade = int(estoque_atual)

        if estoque_minimo:
            epi.estoque_minimo = int(estoque_minimo)
            
        epi.usuario_id = current_user.id

        # Salvar o EPI (isso também cria registro no estoque principal)
        epi.save()
        
        # Se há estoque inicial, adicionar ao estoque principal
        if estoque_quantidade > 0:
            epi.adicionar_estoque(estoque_quantidade, current_user.id, "Estoque inicial")

        if is_ajax:
            return jsonify({
                'success': True, 
                'message': 'EPI cadastrado com sucesso!',
                'epi': {
                    'id': epi.id,
                    'material_nome': epi.material.nome,
                    'ca_numero': epi.ca_numero or 'Não informado',
                    'estoque_atual': epi.get_estoque_atual(),
                    'estoque_minimo': epi.estoque_minimo,
                    'data_validade': epi.data_validade.strftime('%d/%m/%Y') if epi.data_validade else 'Não aplicável',
                    'status_estoque': epi.status_estoque,
                    'status_validade': epi.status_validade
                }
            })
            
        flash('EPI cadastrado com sucesso!', 'success')
        return redirect(url_for('seguranca.epis_index'))

    # Se for GET, renderiza a página com o formulário
    materiais = Material.query.filter(Material.categoria == 'EPI').all()
    return render_template('seguranca/epis/novo.html', materiais=materiais, now1=datetime.now())


@seguranca_bp.route('/epis/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def epi_editar(id):
    """
    Edita um EPI existente
    """
    epi = EPI.query.get_or_404(id)
    materiais = Material.query.filter_by(categoria='EPI').all()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        try:
            ca_numero = request.form.get('ca_numero')
            data_validade = request.form.get('data_validade')
            vida_util_meses = request.form.get('vida_util_meses')
            estoque_atual = request.form.get('estoque_atual')
            estoque_minimo = request.form.get('estoque_minimo')
            
            # Converter tipos
            if data_validade:
                data_validade = datetime.strptime(data_validade, '%Y-%m-%d').date()
            else:
                data_validade = None
                
            if vida_util_meses:
                vida_util_meses = int(vida_util_meses)
            else:
                vida_util_meses = None
                
            estoque_quantidade = epi.get_estoque_atual()
            if estoque_atual:
                estoque_atual = int(estoque_atual)
                # Se o estoque mudou, registrar a diferença como ajuste
                if estoque_atual != estoque_quantidade:
                    diferenca = estoque_atual - estoque_quantidade
                    if diferenca > 0:
                        epi.adicionar_estoque(diferenca, current_user.id, "Ajuste via edição de EPI")
                    elif diferenca < 0:
                        epi.remover_estoque(-diferenca, current_user.id, "Ajuste via edição de EPI")
                
            if estoque_minimo:
                estoque_minimo = int(estoque_minimo)
            else:
                estoque_minimo = 1
            
            # Atualizar EPI
            epi.ca_numero = ca_numero
            epi.data_validade = data_validade
            epi.vida_util_meses = vida_util_meses
            epi.estoque_minimo = estoque_minimo
            epi.save()
            
            if is_ajax:
                return jsonify({
                    'success': True, 
                    'message': 'EPI atualizado com sucesso!',
                    'epi': {
                        'id': epi.id,
                        'material_nome': epi.material.nome,
                        'ca_numero': epi.ca_numero or 'Não informado',
                        'estoque_atual': epi.get_estoque_atual(),
                        'estoque_minimo': epi.estoque_minimo,
                        'data_validade': epi.data_validade.strftime('%d/%m/%Y') if epi.data_validade else 'Não aplicável',
                        'status_estoque': epi.status_estoque,
                        'status_validade': epi.status_validade
                    }
                })
            
            flash('EPI atualizado com sucesso!', 'success')
            return redirect(url_for('seguranca.epis_index'))
            
        except Exception as e:
            if is_ajax:
                return jsonify({'success': False, 'message': f'Erro ao atualizar EPI: {str(e)}'})
            flash(f'Erro ao atualizar EPI: {str(e)}', 'danger')
    
    # Para requisições AJAX, retorna os dados do EPI em formato JSON
    if is_ajax:
        return jsonify({
            'id': epi.id,
            'material_id': epi.material_id,
            'material_nome': epi.material.nome,
            'ca_numero': epi.ca_numero or '',
            'data_validade': epi.data_validade.strftime('%Y-%m-%d') if epi.data_validade else '',
            'vida_util_meses': epi.vida_util_meses,
            'estoque_atual': epi.get_estoque_atual(),
            'estoque_minimo': epi.estoque_minimo
        })

    return render_template('seguranca/epis/editar.html', epi=epi, materiais=materiais, now1=datetime.now()) 

@seguranca_bp.route('/epis/excluir/<int:id>', methods=['POST', 'GET'])
@login_required
def epi_excluir(id):
    """
    Exclui um EPI
    """
    if request.method == 'GET':
        data = {
            'success': True,
            'epi_nome': EPI.query.get_or_404(id).material.nome,
            'epi_id': id}
        return jsonify(data)
    epi = EPI.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Verificar se há entregas associadas
    entregas = EntregaEPI.query.filter_by(epi_id=id).first()
    if entregas:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Não é possível excluir este EPI pois há entregas associadas.'})
        flash('Não é possível excluir este EPI pois há entregas associadas.', 'danger')
        return redirect(url_for('seguranca.epis_index'))

    try:
        nome = epi.material.nome
        epi.delete()
        
        if is_ajax:
            return jsonify({'success': True, 'message': 'EPI excluído com sucesso!'})
            
        flash(f'EPI "{nome}" excluído com sucesso!', 'success')
        return redirect(url_for('seguranca.epis_index'))
    except Exception as e:
        if is_ajax:
            return jsonify({'success': False, 'message': f'Erro ao excluir EPI: {str(e)}'})
        flash(f'Erro ao excluir EPI: {str(e)}', 'danger')
        return redirect(url_for('seguranca.epis_index'))

@seguranca_bp.route('/epis-json')
@login_required
def epis_json():
    """
    Retorna lista de EPIs em formato JSON para uso em selects
    """
    epis = EPI.query.all()
    resultado = []
    
    for epi in epis:
        resultado.append({
            'id': epi.id,
            'ca_numero': epi.ca_numero or 'N/A',
            'material': {
                'id': epi.material.id,
                'nome': epi.material.nome or '',
                'codigo': epi.material.codigo or ''
            }
        })
    
    return jsonify(resultado)

@seguranca_bp.route('/epis/ajustar-estoque/<int:id>', methods=['POST', 'GET'])
@login_required
def epi_ajustar_estoque(id):
    """
    Ajusta o estoque de um EPI
    """
    if request.method == 'GET':
        data = {
            'success': True,
            'epi_nome': EPI.query.get_or_404(id).material.nome,
            'epi_id': id,
            'estoque_atual': EPI.query.get_or_404(id).getEstoqueAtual()
        }
        return jsonify(data)
    print(request.form)
    epi = EPI.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    quantidade = request.form.get('quantidade')
    operacao = request.form.get('operacao')
    motivo = request.form.get('motivo')
    
    if not quantidade or not operacao:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Quantidade e operação são obrigatórios'})
        flash('Quantidade e operação são obrigatórios', 'danger')
        return redirect(url_for('seguranca.epis_index'))
    
    try:
        quantidade_ajuste = int(quantidade) # Renomeado para clareza

        if operacao == 'definir_estoque_real':
            if quantidade_ajuste < 0:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'A quantidade real em estoque não pode ser negativa.'})
                flash('A quantidade real em estoque não pode ser negativa.', 'danger')
                return redirect(url_for('seguranca.epis_index'))
            
            epi.ajustar_estoque(quantidade_ajuste,current_user.id)
            return jsonify({'success': True, 'message': f'{quantidade_ajuste} item(s) adicionado(s) ao estoque com sucesso!'})

        elif operacao == 'adicionar':
            print(f"Adicionando {quantidade_ajuste} item(s) ao estoque")
            if quantidade_ajuste <= 0:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Para adicionar, a quantidade deve ser maior que zero.'})
                flash('Para adicionar, a quantidade deve ser maior que zero.', 'danger')
                return redirect(url_for('seguranca.epis_index'))
            print(f"Adicionando {quantidade_ajuste} item(s) ao estoque1")
            epi.adicionar_estoque(quantidade_ajuste, current_user.id)
            return jsonify({'success': True, 'message': f'{quantidade_ajuste} item(s) adicionado(s) ao estoque com sucesso!'})
        
        elif operacao == 'subtrair':
            
            epi.remover_estoque(quantidade_ajuste, current_user.id, motivo)
            msg = f'{quantidade_ajuste} item(s) removido(s) do estoque com sucesso!'
        else:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Operação inválida.'})
            flash('Operação inválida.', 'danger')
            return redirect(url_for('seguranca.epis_index'))
        
        if is_ajax:
            return jsonify({
                'success': True, 
                'message': msg,
                'estoque_atual': epi.get_estoque_atual(),
                'status_estoque': epi.status_estoque
            })
        
        flash(msg, 'success')
        return redirect(url_for('seguranca.epis_index'))
    
    except Exception as e:
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)})
        flash(str(e), 'danger')
        return redirect(url_for('seguranca.epis_index'))


@seguranca_bp.route('/epis/consultar-ca', methods=['GET'])
@login_required
def consultar_ca_endpoint():
    try:
        numero_ca = request.args.get('numero')
        debug = request.args.get('debug', '0') == '1'

        if not numero_ca:
            return jsonify({"erro": "Número de CA não informado"}), 400

        # Cas específicos conhecidos
        casos_especiais = {
            "3890": {
                "equipamento": "LUVA DE SEGURANÇA",
                "fabricante": "VOLK DO BRASIL",
                "situacao": "VÁLIDO",
                "descricao": "Luva de segurança confeccionada em couro tipo vaqueta na palma e dorso, reforço externo entre o polegar e o indicador.",
                "normas": ["Proteção das mãos do usuário contra agentes abrasivos, escoriantes, cortantes e perfurantes"]
            },
            "25089": {
                "equipamento": "CALÇADO",
                "fabricante": "164",
                "situacao": "VENCIDO/Validade:02/06/2014/venceu há 3941 dias",
                "descricao": "Sem descrição disponível",
                "normas": ["PROTEÇÃO DOS PÉS DO USUÁRIO CONTRA RISCOS DE NATUREZA LEVE EM ÁREAS ONDE HAJA RISCO DE CHOQUES ELÉTRICOS"]
            },
            "39878": {
                "equipamento": "PROTETOR AUDITIVO CIRCUMAURICULAR",
                "fabricante": "3M DO BRASIL LTDA",
                "situacao": "VÁLIDO",
                "descricao": "Protetor auditivo do tipo concha (abafador), constituído por duas conchas em plástico, revestidas com almofadas de espuma em suas bordas, fixadas a um arco plástico.",
                "normas": ["Proteção auditiva do usuário contra níveis de pressão sonora superiores ao estabelecido na NR-15"]
            },
            "40293": {
                "equipamento": "CALÇADO FEMININO PROFISSIONAL LADY WORKS",
                "fabricante": "164",
                "situacao": "VENCIDO",
                "descricao": "Calçado feminino profissional Lady Works CA 40293 B895 Pretoç R$ 98"
            }
        }

        # Verificar se é um caso específico
        if numero_ca in casos_especiais:
            logger = logging.getLogger(__name__)
            logger.info(f"Usando dados pré-configurados para CA {numero_ca}")
            resultado = casos_especiais[numero_ca].copy()
            resultado["numero_ca"] = numero_ca
            # Se tem data_validade, converter
            if "data_validade" in resultado and isinstance(resultado["data_validade"], str):
                try:
                    data_obj = datetime.strptime(
                        resultado["data_validade"], "%d/%m/%Y").date()
                    resultado["data_validade"] = data_obj.strftime('%Y-%m-%d')
                except ValueError:
                    pass
        else:
            # Usar o serviço de scraping para consultar o CA
            resultado = consultar_ca(numero_ca)

        # Verificar se houve erro
        if "erro" in resultado:
            return jsonify(resultado), 404 if "não encontrado" in resultado["erro"] else 500

        # Converter objetos date para string antes de serializar para JSON
        for key, value in resultado.items():
            if isinstance(value, (datetime, date)):
                resultado[key] = value.strftime('%Y-%m-%d')

        # Log para depuração
        logger = logging.getLogger(__name__)
        logger.info(f"Consulta CA {numero_ca}: {resultado}")

        # Se modo debug ativado, retornar HTML bruto para análise
        if debug and request.args.get('include_html', '0') == '1':
            import requests
            url = f"https://consultaca.com/{numero_ca}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    resultado["_html"] = response.text
            except Exception as e:
                resultado["_html_error"] = str(e)

        return jsonify(resultado)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(
            f"Erro não tratado na consulta de CA: {str(e)}", exc_info=True)
        return jsonify({"erro": "Erro interno do servidor ao processar a requisição."}), 500 

# Rotas para Entregas de EPIs
@seguranca_bp.route('/epis/entregas', methods=['GET', 'POST'])
@login_required
def entregas_index():
    """
    Lista todas as entregas de EPIs
    """
    """ Listar todas as entregas de EPIs com filtros e paginação """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)

    # Obter parâmetros de filtro
    filtro_colaborador_id = request.args.get('colaborador_id', type=int)
    filtro_epi_id = request.args.get('epi_id', type=int)
    filtro_data_inicio_str = request.args.get('data_inicio', '')
    filtro_data_fim_str = request.args.get('data_fim', '')
    filtro_status = request.args.get('status', '') # 'entregue', 'devolvido'


    print(f"Filtro colaborador_id: {filtro_colaborador_id}")
    print(f"Filtro epi_id: {filtro_epi_id}")
    print(f"Filtro data_inicio: {filtro_data_inicio_str}")
    print(f"Filtro data_fim: {filtro_data_fim_str}")
    print(f"Filtro status: {filtro_status}")
    # Query base com joins para otimizar e permitir filtros
    query = EntregaEPI.query
    

    # Aplicar filtros
    if filtro_colaborador_id:
        query = query.filter(EntregaEPI.colaborador_id == filtro_colaborador_id)
    
    if filtro_epi_id:
        query = query.filter(EntregaEPI.epi_id == filtro_epi_id)

    # Filtro de data (assumindo formato YYYY-MM-DD)
    try:
        if filtro_data_inicio_str:
            data_inicio = datetime.strptime(filtro_data_inicio_str, '%Y-%m-%d').date()
            query = query.filter(EntregaEPI.data_entrega >= data_inicio)
        if filtro_data_fim_str:
            data_fim = datetime.strptime(filtro_data_fim_str, '%Y-%m-%d').date()
            query = query.filter(EntregaEPI.data_entrega <= data_fim)
    except ValueError:
        flash('Formato de data inválido. Use AAAA-MM-DD.', 'warning')
        # Resetar datas inválidas para não quebrar a query
        filtro_data_inicio_str = ''
        filtro_data_fim_str = '' 
        # Poderia redirecionar ou mostrar erro mais proeminente

    if filtro_status == 'entregue':
        query = query.filter(EntregaEPI.data_devolucao.is_(None))
    elif filtro_status == 'devolvido':
        query = query.filter(EntregaEPI.data_devolucao.isnot(None))

    # Ordenar resultados (ex: data de entrega mais recente primeiro)
    query = query.order_by(EntregaEPI.data_entrega.desc(), EntregaEPI.id.desc())
    #print(f"Query: {query}")
    # Aplicar paginação
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    entregas = pagination.items

    # Buscar dados para os filtros
    colaboradores = Colaborador.query.order_by(Colaborador.nome).all()
    epis_disponiveis = EPI.query.join(EPI.material).order_by(Material.nome).all() 
    #print(f"Epis disponíveis: {epis_disponiveis}")
    # Ou buscar apenas materiais com categoria EPI
    # materiais_epi = Material.query.filter(Material.categoria == 'EPI').order_by(Material.nome).all()
    # epis_disponiveis = EPI.query.filter(EPI.material_id.in_([m.id for m in materiais_epi])).all()

    # Manter filtros no contexto para o template
    filtros_ativos = {
        'colaborador_id': filtro_colaborador_id,
        'epi_id': filtro_epi_id,
        'data_inicio': filtro_data_inicio_str,
        'data_fim': filtro_data_fim_str,
        'status': filtro_status
    }

    return render_template('seguranca/entregas/index.html', 
                           pagination=pagination, 
                           entregas=entregas, 
                           colaboradores=colaboradores,
                           epis_disponiveis=epis_disponiveis,
                           filtros_ativos=filtros_ativos,
                           now1=datetime.now().date())



@seguranca_bp.route('/entregas/nova', methods=['GET', 'POST'])
@login_required
def nova_entrega():
    """
    Registra uma nova entrega de EPI
    """
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        colaborador_id = request.form.get('colaborador_id')
        epi_id = request.form.get('epi_id_modal')
        quantidade = request.form.get('quantidade', 1)
        motivo = request.form.get('motivo')
        observacoes = request.form.get('observacoes')
        data_entrega = request.form.get('data_entrega') or datetime.now().date().strftime('%Y-%m-%d')
        assinado = request.form.get('assinado') == 'on'
        devolver_antigo = request.form.get('devolver_antigo') == 'on'
        
        # Novos campos do formulário para o CA
        ca_numero_entrega = request.form.get('ca_numero_entrega')
        update_epi_ca = request.form.get('update_epi_ca') == 'yes' # O valor será 'yes' ou 'no' do JS
        
        # Validações
        if not colaborador_id or not epi_id:
            msg = 'Colaborador e EPI são obrigatórios'
            if is_ajax:
                return jsonify({'success': False, 'message': msg})
            flash(msg, 'danger')
            return redirect(url_for('seguranca.entregas_index'))
        
        # Verificar estoque
        epi = EPI.query.get(epi_id)
        if not epi:
            msg = 'EPI não encontrado'
            if is_ajax:
                return jsonify({'success': False, 'message': msg})
            flash(msg, 'danger')
            return redirect(url_for('seguranca.entregas_index'))
        
        if int(quantidade) > epi.get_estoque_atual():
            msg = f'Estoque insuficiente. Disponível: {epi.get_estoque_atual()}'
            if is_ajax:
                return jsonify({'success': False, 'message': msg})
            flash(msg, 'danger')
            return redirect(url_for('seguranca.entregas_index'))
        
        # --- Atualização do CA do EPI (se solicitado) ---
        if update_epi_ca and ca_numero_entrega:
            try:
                epi.ca_numero = ca_numero_entrega
                db.session.commit() # Salva a alteração no EPI
            except Exception as e:
                db.session.rollback()
                msg = f'Erro ao tentar atualizar o C.A. do EPI: {str(e)}'
                if is_ajax:
                    return jsonify({'success': False, 'message': msg})
                flash(msg, 'warning') # Warning pois a entrega pode prosseguir
                # Não redireciona, permite continuar o fluxo da entrega
        # --- Fim da atualização do CA do EPI ---

        # Verificar se o colaborador já possui este EPI em uso (não devolvido)
        if devolver_antigo:
            entrega_anterior = EntregaEPI.query.filter_by(
                colaborador_id=colaborador_id, 
                epi_id=epi_id, 
                data_devolucao=None
            ).first()
            
            if entrega_anterior:
                # Registrar devolução automática
                data_devolucao = datetime.strptime(data_entrega, '%Y-%m-%d').date()
                observacoes_devolucao = f"Devolução automática devido à nova entrega de EPI. {observacoes if observacoes else ''}"
                entrega_anterior.registrar_devolucao(data_devolucao, observacoes_devolucao)
        
        # Criar a nova entrega
        entrega = EntregaEPI()
        entrega.colaborador_id = colaborador_id
        entrega.epi_id = epi_id
        entrega.quantidade = int(quantidade)
        entrega.motivo = motivo
        entrega.observacoes = observacoes
        entrega.data_entrega = datetime.strptime(data_entrega, '%Y-%m-%d').date()
        entrega.assinado = assinado
        entrega.usuario_id = current_user.id
        entrega.ca = ca_numero_entrega # Salvar o CA informado na entrega
        
        # Salvar a entrega
        try:
            entrega.save()
            msg = 'Entrega de EPI registrada com sucesso!'
            if is_ajax:
                return jsonify({
                    'success': True, 
                    'message': msg,
                    'entrega': {
                        'id': entrega.id,
                        'colaborador_nome': entrega.colaborador.nome,
                        'epi_nome': entrega.epi.material.nome,
                        'data_entrega': entrega.data_entrega.strftime('%d/%m/%Y'),
                        'quantidade': entrega.quantidade,
                        'status': entrega.status
                    }
                })
            flash(msg, 'success')
            return redirect(url_for('seguranca.entregas_index'))
        except Exception as e:
            msg = f'Erro ao registrar entrega: {str(e)}'
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': msg
                })
            flash(msg, 'danger')
            return redirect(url_for('seguranca.entregas_index'))
    
    # Se for GET e não for AJAX, redireciona para o index (pois usaremos modal)
    if not is_ajax:
        return redirect(url_for('seguranca.entregas_index'))
    
    # Para requisições AJAX GET, retorna os dados necessários para o modal
    epis = EPI.query.all()
    colaboradores = Colaborador.query.all()
    
    return jsonify({
        'epis': [{'id': epi.id, 'nome': epi.material.nome, 'estoque': epi.get_estoque_atual()} for epi in epis],
        'colaboradores': [{'id': col.id, 'nome': col.nome} for col in colaboradores]
    })


@seguranca_bp.route('/epis/entregas/visualizar/<int:id>')
@login_required
def entrega_visualizar(id):
    """
    Visualiza os detalhes de uma entrega
    """
    entrega = EntregaEPI.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if is_ajax:
        return jsonify({
            'id': entrega.id,
            'colaborador': {
                'id': entrega.colaborador_id,
                'nome': entrega.colaborador.nome
            },
            'epi': {
                'id': entrega.epi_id,
                'nome': entrega.epi.material.nome,
                'ca_numero': entrega.epi.ca_numero
            },
            'data_entrega': entrega.data_entrega.strftime('%Y-%m-%d'),
            'data_devolucao': entrega.data_devolucao.strftime('%Y-%m-%d') if entrega.data_devolucao else None,
            'quantidade': entrega.quantidade,
            'motivo': entrega.motivo,
            'observacoes': entrega.observacoes,
            'status': entrega.status,
            'assinado': entrega.assinado,
            'dias_em_uso': entrega.dias_em_uso
        })
    
    return render_template('seguranca/entregas/visualizar.html', entrega=entrega, now1=datetime.now())


@seguranca_bp.route('/entregas/devolver/<int:id>', methods=['POST'])
@login_required
def devolver_entrega(id):
    """
    Registra a devolução de um EPI
    """
    entrega = EntregaEPI.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if entrega.data_devolucao:
        msg = 'Este EPI já foi devolvido'
        if is_ajax:
            return jsonify({'success': False, 'message': msg})
        flash(msg, 'warning')
        return redirect(url_for('seguranca.entregas_index'))
    
    data_devolucao = request.form.get('data_devolucao')
    observacoes = request.form.get('observacoes_devolucao')
    
    if data_devolucao:
        data_devolucao = datetime.strptime(data_devolucao, '%Y-%m-%d').date()
    
    # Registrar a devolução
    resultado = entrega.registrar_devolucao(data_devolucao, observacoes)
    
    if resultado:
        msg = 'Devolução registrada com sucesso!'
        if is_ajax:
            return jsonify({
                'success': True, 
                'message': msg,
                'entrega': {
                    'id': entrega.id,
                    'data_devolucao': entrega.data_devolucao.strftime('%d/%m/%Y'),
                    'status': 'Devolvido',
                    'dias_em_uso': entrega.dias_em_uso
                }
            })
        flash(msg, 'success')
    else:
        msg = 'Não foi possível registrar a devolução'
        if is_ajax:
            return jsonify({'success': False, 'message': msg})
        flash(msg, 'danger')
    
    return redirect(url_for('seguranca.entrega_visualizar', id=id))


@seguranca_bp.route('/entregas/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_entrega(id):
    """
    Exclui uma entrega de EPI
    """
    entrega = EntregaEPI.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        entrega.delete()
        msg = 'Registro de entrega excluído com sucesso!'
        if is_ajax:
            return jsonify({'success': True, 'message': msg})
        flash(msg, 'success')
    except Exception as e:
        msg = f'Erro ao excluir o registro: {str(e)}'
        if is_ajax:
            return jsonify({'success': False, 'message': msg})
        flash(msg, 'danger')
    
    return redirect(url_for('seguranca.entregas_index'))


@seguranca_bp.route('/relatorios')
@login_required
def relatorios():
    """
    Página de relatórios de segurança
    """
    # Calcular estatísticas
    with app.app_context():
        total_epis = EPI.query.count()
        # Usar filter_by para verificar quais EPIs têm estoque zero no sistema principal
        epis_criticos = []
        for epi in EPI.query.all():
            if epi.get_estoque_atual() <= 0:
                epis_criticos.append(epi.id)
        epis_criticos_count = len(epis_criticos)
        
        # Colaboradores com equipamentos
        total_colaboradores = Colaborador.query.count()
        colaboradores_com_epi = db.session.query(EntregaEPI.colaborador_id).filter(EntregaEPI.data_devolucao.is_(None)).distinct().count()
    
    # Estatísticas de entregas
    total_entregas = EntregaEPI.query.count()
    entregas_sem_devolucao = EntregaEPI.query.filter(EntregaEPI.data_devolucao.is_(None)).count()
    
    # Estatísticas por colaborador
    colaboradores = Colaborador.query.filter_by(status='Ativo').all()
    dados_colaboradores = []
    
    for colaborador in colaboradores:
        entregas = EntregaEPI.query.filter_by(colaborador_id=colaborador.id).all()
        entregas_ativas = EntregaEPI.query.filter_by(colaborador_id=colaborador.id, data_devolucao=None).count()
        
        dados_colaboradores.append({
            'id': colaborador.id,
            'nome': colaborador.nome,
            'cargo': colaborador.cargo,
            'total_entregas': len(entregas),
            'entregas_ativas': entregas_ativas
        })
    
    # Estatísticas por mês
    meses = []
    for i in range(12):
        data = datetime.now() - timedelta(days=30*i)
        mes = data.strftime('%Y-%m')
        
        entregas = EntregaEPI.query.filter(
            db.func.strftime('%Y-%m', EntregaEPI.data_entrega) == mes
        ).count()
        
        devolucoes = EntregaEPI.query.filter(
            db.func.strftime('%Y-%m', EntregaEPI.data_devolucao) == mes
        ).count()
        
        meses.append({
            'mes': data.strftime('%b/%Y'),
            'entregas': entregas,
            'devolucoes': devolucoes
        })
    
    return render_template('seguranca/relatorios.html',
                          total_epis=total_epis,
                          epis_criticos=epis_criticos_count,
                          total_entregas=total_entregas,
                          entregas_sem_devolucao=entregas_sem_devolucao,
                          dados_colaboradores=dados_colaboradores,
                          dados_meses=json.dumps(meses),
                          now1=datetime.now())


@seguranca_bp.route('/colaborador/<int:id>')
@login_required
def colaborador_epis(id):
    """
    Mostra os EPIs entregues a um colaborador específico
    """
    colaborador = Colaborador.query.get_or_404(id)
    entregas = EntregaEPI.query.filter_by(colaborador_id=id).order_by(EntregaEPI.data_entrega.desc()).all()
    
    return render_template('seguranca/colaborador.html',
                          colaborador=colaborador,
                          entregas=entregas,
                          now1=datetime.now())


# Definir o blueprint do EPI como alias para o blueprint de segurança
# Isso é necessário para manter compatibilidade com as URLs existentes
from flask import current_app

def register_blueprints(app):
    """
    Registra os blueprints no aplicativo Flask
    """
    app.register_blueprint(seguranca_bp)
    
    # Registrar as rotas do EPI como alias para as rotas de segurança
    epi_bp = Blueprint('epi', __name__)
    
    @epi_bp.route('/')
    @login_required
    def index():
        return redirect(url_for('seguranca.epis_index'))
        
    @epi_bp.route('/novo', methods=['GET', 'POST'])
    @login_required
    def novo():
        return redirect(url_for('seguranca.epi_novo'))
        
    @epi_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
    @login_required
    def editar(id):
        return redirect(url_for('seguranca.epi_editar', id=id))
        
    @epi_bp.route('/excluir/<int:id>', methods=['POST'])
    @login_required
    def excluir(id):
        return redirect(url_for('seguranca.epi_excluir', id=id))
        
    @epi_bp.route('/entregas')
    @login_required
    def entregas_index():
        return redirect(url_for('seguranca.entregas_index'))
        
    @epi_bp.route('/entregas/nova', methods=['GET', 'POST'])
    @login_required
    def nova_entrega():
        return redirect(url_for('seguranca.nova_entrega'))
        
    @epi_bp.route('/entregas/visualizar/<int:id>')
    @login_required
    def visualizar_entrega(id):
        return redirect(url_for('seguranca.entrega_visualizar', id=id))
        
    @epi_bp.route('/entregas/devolver/<int:id>', methods=['POST'])
    @login_required
    def devolver_entrega(id):
        return redirect(url_for('seguranca.devolver_entrega', id=id))
        
    @epi_bp.route('/entregas/excluir/<int:id>', methods=['POST'])
    @login_required
    def excluir_entrega(id):
        return redirect(url_for('seguranca.excluir_entrega', id=id))
        
    @epi_bp.route('/colaborador/<int:id>')
    @login_required
    def epis_colaborador(id):
        return redirect(url_for('seguranca.colaborador_epis', id=id))
        
    @epi_bp.route('/consultar-ca', methods=['GET'])
    @login_required
    def consultar_ca_endpoint():
        return redirect(url_for('seguranca.consultar_ca_endpoint', **request.args))
    
    app.register_blueprint(epi_bp) 

@seguranca_bp.route('/<int:id>/ficha_epi_modal')
@login_required
def ficha_epi_modal(id):
    """
    Retorna o conteúdo HTML da ficha de EPI para ser carregado em um modal.
    """
    colaborador = Colaborador.query.options(joinedload(Colaborador.entregas_epi).joinedload(EntregaEPI.epi).joinedload(EPI.material)).get_or_404(id)
    
    # Ordenar entregas, por exemplo, por data de entrega descendente
    entregas_ordenadas = sorted(colaborador.entregas_epi, key=lambda e: e.data_entrega, reverse=True)
    
    return render_template('colaboradores/_ficha_epi_conteudo.html', 
                           colaborador=colaborador,
                           entregas=entregas_ordenadas)

@seguranca_bp.route('/<int:id>/ficha_epi_pdf')
@login_required
def ficha_epi_pdf(id):
    """
    Gera e retorna a ficha de EPI em formato PDF para um colaborador.
    """
    if not HTML:
        flash('Funcionalidade de PDF indisponível. WeasyPrint não instalado.', 'danger')
        # Redirecionar ou retornar erro apropriado
        return redirect(url_for('colaborador.index')) 

    colaborador = Colaborador.query.options(joinedload(Colaborador.entregas_epi).joinedload(EntregaEPI.epi).joinedload(EPI.material)).get_or_404(id)
    entregas_ordenadas = sorted(colaborador.entregas_epi, key=lambda e: e.data_entrega, reverse=True)
    
    # Renderizar o template HTML
    html_content = render_template('colaboradores/_ficha_epi_conteudo.html', 
                                   colaborador=colaborador,
                                   entregas=entregas_ordenadas)

    # Gerar PDF usando WeasyPrint
    try:
        font_config = FontConfiguration()
        html = HTML(string=html_content, base_url=request.base_url)
        # Adicionar CSS se necessário: css = CSS(string='@page { size: A4; margin: 1cm; }', font_config=font_config)
        # pdf_bytes = html.write_pdf(stylesheets=[css], font_config=font_config)
        pdf_bytes = html.write_pdf(font_config=font_config)
        
        # Criar resposta
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=ficha_epi_{colaborador.nome.replace(" ", "_").lower()}_{id}.pdf'
        return response
        
    except Exception as e:
        flash(f'Erro ao gerar PDF: {e}', 'danger')
        # Adicionar log do erro
        print(f"Erro WeasyPrint: {e}") 
        return redirect(url_for('colaborador.index'))

@seguranca_bp.route('/fichas_epi_pdf_massa', methods=['POST'])
@login_required
def fichas_epi_pdf_massa():
    """
    Gera um arquivo ZIP contendo as fichas de EPI em PDF para os colaboradores selecionados.
    """
    if not HTML:
        flash('Funcionalidade de PDF indisponível. WeasyPrint não instalado.', 'danger')
        return jsonify({'success': False, 'message': 'WeasyPrint não instalado.'}), 500

    colaborador_ids = request.json.get('colaborador_ids')

    if not colaborador_ids:
        return jsonify({'success': False, 'message': 'Nenhum colaborador selecionado.'}), 400

    try:
        # Usar BytesIO para criar o ZIP em memória
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            font_config = FontConfiguration() # Reutilizar configuração de fonte

            for col_id in colaborador_ids:
                colaborador = Colaborador.query.options(joinedload(Colaborador.entregas_epi).joinedload(EntregaEPI.epi).joinedload(EPI.material)).get(col_id)
                if colaborador:
                    entregas_ordenadas = sorted(colaborador.entregas_epi, key=lambda e: e.data_entrega, reverse=True)
                    html_content = render_template('colaboradores/_ficha_epi_conteudo.html', 
                                                   colaborador=colaborador,
                                                   entregas=entregas_ordenadas)
                    
                    html = HTML(string=html_content, base_url=request.base_url)
                    pdf_bytes = html.write_pdf(font_config=font_config)
                    
                    # Nome do arquivo dentro do ZIP
                    pdf_filename = f'ficha_epi_{colaborador.nome.replace(" ", "_").lower()}_{col_id}.pdf'
                    zip_file.writestr(pdf_filename, pdf_bytes)

        # Preparar o buffer para envio
        zip_buffer.seek(0)

        # Nome do arquivo ZIP para download
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f'fichas_epi_{timestamp}.zip'

        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )

    except Exception as e:
        flash(f'Erro ao gerar ZIP de PDFs: {e}', 'danger')
        # Adicionar log do erro
        print(f"Erro Geração ZIP: {e}")
        # Retornar um erro JSON para a requisição AJAX
        return jsonify({'success': False, 'message': f'Erro ao gerar ZIP: {e}'}), 500 