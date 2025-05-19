from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime

from models.database import db
from models.tanque import Tanque
from models.contrato import Contrato

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
    tanques = Tanque.query.all()
    return render_template('tanques/index.html', tanques=tanques)

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
                placas_normais=placas_normais,
                placas_fecho=placas_fecho,
                contrato_id=contrato_id
            )
            
            # Salvar o tanque
            novo_tanque.save()
            
            flash('Tanque cadastrado com sucesso!', 'success')
            
            # Redirecionar para a página de contrato se veio de lá
            if contrato_selecionado:
                return redirect(url_for('tanque.listar_por_contrato', contrato_id=contrato_id))
            else:
                return redirect(url_for('tanque.index'))
            
        except Exception as e:
            flash(f'Erro ao cadastrar tanque: {str(e)}', 'danger')
    
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
            tanque.placas_normais = placas_normais
            tanque.placas_fecho = placas_fecho
            tanque.contrato_id = contrato_id
            
            # Salvar as alterações
            db.session.commit()
            
            flash('Tanque atualizado com sucesso!', 'success')
            return redirect(url_for('tanque.visualizar', id=tanque.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar tanque: {str(e)}', 'danger')
    
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