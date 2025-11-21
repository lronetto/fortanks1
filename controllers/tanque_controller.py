from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime

from models.database import db
from models.tanque import Tanque
from models.contrato import Contrato
from models.peca import Peca
from models.material import Material
from models.material_tanque import MaterialTanque
tanque_bp = Blueprint('tanque', __name__)

# Middleware para verificar se o usuário tem permissão
@tanque_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_gerente_ou_superior:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@tanque_bp.route('/')
def index():
    """
    Lista todos os tanques
    """
    tanques = Tanque.query.order_by(Tanque.contrato_id, Tanque.nome).all()
    tanques_com_pecas = []
    for tanque in tanques:
        pecas = Peca.query.filter_by(tanque_id=tanque.id).count()
        tanque.pecas_cadastradas = pecas
        tanques_com_pecas.append(tanque)
    tanques = tanques_com_pecas
    contratos = Contrato.query.all()
    sistemas = ['SC-10', 'SC-14', 'SR-06']
    return render_template('tanques/index.html', tanques=tanques, contratos=contratos, sistemas=sistemas)

@tanque_bp.route('/contrato/<int:contrato_id>')
def listar_por_contrato(contrato_id):
    """
    Lista tanques de um contrato específico
    """
    contrato = Contrato.query.get_or_404(contrato_id)
    tanques = Tanque.query.filter_by(contrato_id=contrato_id).all()
    return render_template('tanques/listar_por_contrato.html', tanques=tanques, contrato=contrato)

@tanque_bp.route('/novo', methods=['GET', 'POST'])
def novo():
    """
    Cria um novo tanque
    """
    contratos = Contrato.query.all()
    
    # Caso venha da página de contrato
    contrato_id = request.args.get('contrato_id')
    contrato_selecionado = None
    if contrato_id:
        contrato_selecionado = Contrato.query.get(contrato_id)
    
    sistemas = ['SC-10', 'SC-14', 'SR-06']
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        sistema = request.form.get('sistema')
        dimensoes = request.form.get('dimensoes')
        altura_total = request.form.get('altura_total')
        altura_util = request.form.get('altura_util')
        quantidade = request.form.get('quantidade', 1)
        cobertura = True if request.form.get('cobertura') == 'on' else False
        contrato_id = request.form.get('contrato_id')
        quantidade_bainhas = request.form.get('quantidade_bainhas')
        placas_normais = request.form.get('placas_normais')
        placas_fecho = request.form.get('placas_fecho')
        
        # Extrair valores numéricos das dimensões
        diametro = None
        comprimento = None
        largura = None
        
        try:
            # Para tanques circulares, extrair o diâmetro
            if sistema.startswith('SC'):
                # Remover possíveis unidades e converter para float
                valor_str = dimensoes.replace('m', '').replace('M', '').strip()
                # Substituir vírgula por ponto para conversão
                valor_str = valor_str.replace(',', '.')
                diametro = float(valor_str)
            
            # Para tanques retangulares, extrair comprimento e largura
            elif sistema.startswith('SR'):
                # Espera-se formato como "4,0m x 5,0m" ou similar
                partes = dimensoes.lower().replace('m', '').split('x')
                if len(partes) >= 2:
                    # Substituir vírgula por ponto para conversão
                    comp_str = partes[0].strip().replace(',', '.')
                    larg_str = partes[1].strip().replace(',', '.')
                    comprimento = float(comp_str)
                    largura = float(larg_str)
        except (ValueError, IndexError) as e:
            flash(f'Erro ao extrair valores numéricos das dimensões: {str(e)}. Os valores serão salvos como texto.', 'warning')
        
        # Validação básica
        if not nome or not sistema or not dimensoes or not altura_total or not altura_util or not contrato_id:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('tanques/novo.html', 
                                  contratos=contratos, 
                                  contrato_selecionado=contrato_selecionado,
                                  sistemas=sistemas)
        
        try:
            # Converter valores numéricos
            altura_total = float(altura_total)
            altura_util = float(altura_util)
            quantidade = int(quantidade)
            
            # Converter quantidades de placas se fornecidas
            if placas_normais:
                placas_normais = int(placas_normais)
            else:
                placas_normais = None
                
            if placas_fecho:
                placas_fecho = int(placas_fecho)
            else:
                placas_fecho = None
            
            # Converter quantidade de bainhas se fornecida
            if quantidade_bainhas:
                quantidade_bainhas = int(quantidade_bainhas)
            else:
                quantidade_bainhas = 0
            
            # Criar novo tanque
            novo_tanque = Tanque(
                # Definir o UN com base no método gerar_un
                un=Tanque.gerar_un(),
                nome=nome,
                sistema=sistema,
                dimensoes=dimensoes,
                diametro=diametro,
                comprimento=comprimento,
                largura=largura,
                altura_total=altura_total,
                altura_util=altura_util,
                quantidade=quantidade,
                cobertura=cobertura,
                quantidade_bainhas=quantidade_bainhas,
                placas_normais=placas_normais,
                placas_fecho=placas_fecho,
                contrato_id=contrato_id
            )
            
            # Salvar o tanque
            novo_tanque.save()
            
            flash('Tanque cadastrado com sucesso!', 'success')
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': 'Tanque cadastrado com sucesso!',
                    'tanque_id': novo_tanque.id
                })
            
            # Redirecionar para a página de contrato se veio de lá
            if contrato_selecionado:
                return redirect(url_for('tanque.listar_por_contrato', contrato_id=contrato_id))
            else:
                return redirect(url_for('tanque.index'))
            
        except Exception as e:
            error_msg = f'Erro ao cadastrar tanque: {str(e)}'
            flash(error_msg, 'danger')
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
    
    return render_template('tanques/novo.html', 
                          contratos=contratos, 
                          contrato_selecionado=contrato_selecionado,
                          sistemas=sistemas)

@tanque_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """
    Edita um tanque existente
    """
    tanque = Tanque.query.get_or_404(id)
    contratos = Contrato.query.all()
    sistemas = ['SC-10', 'SC-14', 'SR-06']
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        sistema = request.form.get('sistema')
        dimensoes = request.form.get('dimensoes')
        altura_total = request.form.get('altura_total')
        altura_util = request.form.get('altura_util')
        quantidade = request.form.get('quantidade', 1)
        cobertura = True if request.form.get('cobertura') == 'on' else False
        contrato_id = request.form.get('contrato_id')
        quantidade_bainhas = request.form.get('quantidade_bainhas')
        placas_normais = request.form.get('placas_normais')
        placas_fecho = request.form.get('placas_fecho')
        item_nf = request.form.get('item_nf')
        
        # Extrair valores numéricos das dimensões
        diametro = None
        comprimento = None
        largura = None
        
        try:
            # Para tanques circulares, extrair o diâmetro
            if sistema.startswith('SC'):
                # Remover possíveis unidades e converter para float
                valor_str = dimensoes.replace('m', '').replace('M', '').strip()
                # Substituir vírgula por ponto para conversão
                valor_str = valor_str.replace(',', '.')
                diametro = float(valor_str)
            
            # Para tanques retangulares, extrair comprimento e largura
            elif sistema.startswith('SR'):
                # Espera-se formato como "4,0m x 5,0m" ou similar
                partes = dimensoes.lower().replace('m', '').split('x')
                if len(partes) >= 2:
                    # Substituir vírgula por ponto para conversão
                    comp_str = partes[0].strip().replace(',', '.')
                    larg_str = partes[1].strip().replace(',', '.')
                    comprimento = float(comp_str)
                    largura = float(larg_str)
        except (ValueError, IndexError) as e:
            flash(f'Erro ao extrair valores numéricos das dimensões: {str(e)}. Os valores serão salvos como texto.', 'warning')
        
        # Validação básica
        if not nome or not sistema or not dimensoes or not altura_total or not altura_util or not contrato_id:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('tanques/editar.html', 
                                 tanque=tanque, 
                                 contratos=contratos, 
                                 sistemas=sistemas)
        
        try:
            # Converter valores numéricos
            altura_total = float(altura_total)
            altura_util = float(altura_util)
            quantidade = int(quantidade)
            
            # Converter quantidades de placas se fornecidas
            if placas_normais:
                placas_normais = int(placas_normais)
            else:
                placas_normais = None
                
            if placas_fecho:
                placas_fecho = int(placas_fecho)
            else:
                placas_fecho = None
            
            # Converter quantidade de bainhas se fornecida
            if quantidade_bainhas:
                quantidade_bainhas = int(quantidade_bainhas)
            else:
                quantidade_bainhas = 0
            
            # Converter item_nf se fornecida
            if item_nf:
                item_nf = int(item_nf)
            else:
                item_nf = None
            
            # Atualizar o tanque
            tanque.nome = nome
            tanque.sistema = sistema
            tanque.dimensoes = dimensoes
            tanque.diametro = diametro
            tanque.comprimento = comprimento
            tanque.largura = largura
            tanque.altura_total = altura_total
            tanque.altura_util = altura_util
            tanque.quantidade = quantidade
            tanque.cobertura = cobertura
            tanque.quantidade_bainhas = quantidade_bainhas
            tanque.placas_normais = placas_normais
            tanque.placas_fecho = placas_fecho
            tanque.contrato_id = contrato_id
            tanque.item_nf = item_nf
            
            # Salvar as alterações
            db.session.commit()
            
            flash('Tanque atualizado com sucesso!', 'success')
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': 'Tanque atualizado com sucesso!',
                    'tanque_id': tanque.id
                })
            
            return redirect(url_for('tanque.visualizar', id=tanque.id))
            
        except Exception as e:
            db.session.rollback()
            error_msg = f'Erro ao atualizar tanque: {str(e)}'
            flash(error_msg, 'danger')
            
            # Verificar se é requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
    
    return render_template('tanques/editar.html', 
                         tanque=tanque, 
                         contratos=contratos, 
                         sistemas=sistemas)

@tanque_bp.route('/visualizar/<int:id>')
def visualizar(id):
    """
    Visualiza os detalhes de um tanque
    """
    tanque = Tanque.query.get_or_404(id)
    return render_template('tanques/visualizar.html', tanque=tanque)

@tanque_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """
    Exclui um tanque
    """
    tanque = Tanque.query.get_or_404(id)
    contrato_id = tanque.contrato_id
    
    try:
        # Excluir o tanque
        tanque.delete()
        flash('Tanque excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir tanque: {str(e)}', 'danger')
    
    # Verificar se veio da página de contrato
    referrer = request.referrer
    if referrer and f'/contrato/{contrato_id}' in referrer:
        return redirect(url_for('tanque.listar_por_contrato', contrato_id=contrato_id))
    else:
        return redirect(url_for('tanque.index'))

@tanque_bp.route('/relatorio-materiais', methods=['GET', 'POST'])
def relatorio_materiais():
    """
    Gera relatório de materiais básicos necessários para os tanques selecionados
    """
    if request.method == 'GET':
        # Se for GET, redireciona para a página de tanques
        return redirect(url_for('tanque.index'))
    
    # Obter IDs dos tanques selecionados
    tanque_ids = request.form.getlist('tanque_ids')
    
    if not tanque_ids:
        flash('Por favor, selecione pelo menos um tanque para gerar o relatório.', 'warning')
        return redirect(url_for('tanque.index'))
    
    # Converter para inteiros
    try:
        tanque_ids = [int(id) for id in tanque_ids]
    except ValueError:
        flash('IDs de tanques inválidos.', 'danger')
        return redirect(url_for('tanque.index'))
    
    # Buscar os tanques selecionados
    tanques = Tanque.query.filter(Tanque.id.in_(tanque_ids)).all()
    
    if not tanques:
        flash('Nenhum tanque encontrado com os IDs fornecidos.', 'warning')
        return redirect(url_for('tanque.index'))
    
    # Buscar todos os materiais cadastrados
    materiais = Material.query.filter_by(ativo=True).order_by(Material.nome).all()
    
    # Buscar materiais com fórmula válida
    materiais_com_formula = [m for m in materiais if m.formula_calculo and m.formula_calculo.strip()]
    
    # Buscar relacionamentos existentes entre materiais e tanques
    materiais_tanques = MaterialTanque.query.filter(
        MaterialTanque.tanque_id.in_(tanque_ids)
    ).all()
    
    # Criar um dicionário para agrupar materiais por tanque
    materiais_por_tanque = {}
    for mt in materiais_tanques:
        if mt.tanque_id not in materiais_por_tanque:
            materiais_por_tanque[mt.tanque_id] = []
        materiais_por_tanque[mt.tanque_id].append(mt)
    
    # Preparar dados para o relatório
    dados_relatorio = []
    for tanque in tanques:
        dados_tanque = {
            'tanque': tanque,
            'materiais': materiais_por_tanque.get(tanque.id, []),
            'dados_basicos': {
                'quantidade_total': tanque.quantidade,
                'placas_normais': tanque.placas_normais or 0,
                'placas_fecho': tanque.placas_fecho or 0,
                'quantidade_bainhas': tanque.quantidade_bainhas or 0,
                'altura_total': tanque.altura_total,
                'sistema': tanque.sistema
            }
        }
        dados_relatorio.append(dados_tanque)
    
    # Preparar tabela de materiais com fórmula para todos os tanques
    tabela_materiais = []
    totais_por_tanque = {tanque.id: 0 for tanque in tanques}
    total_geral_tabela = 0
    
    for material in materiais_com_formula:
        linha_material = {
            'material': material,
            'quantidades_por_tanque': {},
            'total_geral': 0
        }
        
        # Calcular quantidade para cada tanque
        for tanque in tanques:
            quantidade = material.calcular_quantidade(
                tanque.quantidade,
                tanque.placas_normais or 0,
                tanque.placas_fecho or 0,
                tanque.quantidade_bainhas or 0,
                tanque.altura_total,
                tanque.sistema
            )
            linha_material['quantidades_por_tanque'][tanque.id] = quantidade
            linha_material['total_geral'] += quantidade
            totais_por_tanque[tanque.id] += quantidade
        
        total_geral_tabela += linha_material['total_geral']
        tabela_materiais.append(linha_material)
    
    # Calcular totais gerais
    totais_gerais = {
        'total_tanques': len(tanques),
        'total_quantidade': sum(t.quantidade for t in tanques),
        'total_placas_normais': sum((t.placas_normais or 0) * t.quantidade for t in tanques),
        'total_placas_fecho': sum((t.placas_fecho or 0) * t.quantidade for t in tanques),
        'total_bainhas': sum((t.quantidade_bainhas or 0) * t.quantidade for t in tanques)
    }
    
    return render_template('tanques/relatorio_materiais.html',
                         tanques=tanques,
                         dados_relatorio=dados_relatorio,
                         materiais=materiais,
                         materiais_com_formula=materiais_com_formula,
                         tabela_materiais=tabela_materiais,
                         totais_por_tanque=totais_por_tanque,
                         total_geral_tabela=total_geral_tabela,
                         totais_gerais=totais_gerais,
                         data_geracao=datetime.now())

@tanque_bp.route('/adicionar-material-tanque', methods=['POST'])
def adicionar_material_tanque():
    """
    Adiciona um material relacionado a um tanque com os dados básicos do tanque
    """
    try:
        # Obter dados do formulário
        material_id = request.form.get('material_id')
        tanque_id = request.form.get('tanque_id')
        quantidade_material = request.form.get('quantidade_material', 1.0)
        observacoes = request.form.get('observacoes')
        
        # Dados básicos do tanque
        quantidade_total = request.form.get('quantidade_total', 1)
        placas_normais = request.form.get('placas_normais', 0)
        placas_fecho = request.form.get('placas_fecho', 0)
        quantidade_bainhas = request.form.get('quantidade_bainhas', 0)
        altura_total = request.form.get('altura_total', 0)
        sistema = request.form.get('sistema', '')
        
        # Validações
        if not material_id or not tanque_id:
            flash('Material e tanque são obrigatórios.', 'danger')
            return redirect(request.referrer or url_for('tanque.index'))
        
        # Verificar se o material existe
        material = Material.query.get(material_id)
        if not material:
            flash('Material não encontrado.', 'danger')
            return redirect(request.referrer or url_for('tanque.index'))
        
        # Verificar se o tanque existe
        tanque = Tanque.query.get(tanque_id)
        if not tanque:
            flash('Tanque não encontrado.', 'danger')
            return redirect(request.referrer or url_for('tanque.index'))
        
        # Verificar se já existe relacionamento
        material_tanque_existente = MaterialTanque.query.filter_by(
            material_id=material_id,
            tanque_id=tanque_id
        ).first()
        
        if material_tanque_existente:
            flash('Este material já está relacionado a este tanque.', 'warning')
            return redirect(request.referrer or url_for('tanque.index'))
        
        # Converter valores
        try:
            quantidade_total = int(quantidade_total)
            placas_normais = int(placas_normais) if placas_normais else 0
            placas_fecho = int(placas_fecho) if placas_fecho else 0
            quantidade_bainhas = int(quantidade_bainhas) if quantidade_bainhas else 0
            altura_total = float(altura_total)
            # Se o material tiver fórmula universal, calcular automaticamente
            if material.formula_calculo:
                quantidade_material = material.calcular_quantidade(
                    quantidade_total, placas_normais, placas_fecho, 
                    quantidade_bainhas, altura_total, sistema
                )
            else:
                quantidade_material = float(quantidade_material) if quantidade_material else 1.0
        except ValueError as e:
            flash(f'Erro ao converter valores numéricos: {str(e)}', 'danger')
            return redirect(request.referrer or url_for('tanque.index'))
        
        # Criar novo relacionamento (calcular_automatico=True se material tiver fórmula universal)
        material_tanque = MaterialTanque(
            material_id=material_id,
            tanque_id=tanque_id,
            quantidade_total=quantidade_total,
            placas_normais=placas_normais,
            placas_fecho=placas_fecho,
            quantidade_bainhas=quantidade_bainhas,
            altura_total=altura_total,
            sistema=sistema,
            quantidade_material=quantidade_material,
            observacoes=observacoes,
            calcular_automatico=bool(material.formula_calculo),  # Calcular automaticamente se material tiver fórmula
            material_obj=material  # Passar o objeto material para evitar query extra
        )
        
        material_tanque.save()
        
        flash(f'Material "{material.nome}" adicionado ao tanque "{tanque.nome}" com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao adicionar material ao tanque: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('tanque.index')) 