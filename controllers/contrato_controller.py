from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime

from models.database import db
from models.contrato import Contrato
from models.centro_custo import CentroCusto
from models.cliente import Cliente

contrato_bp = Blueprint('contrato', __name__)

# Middleware para verificar se o usuário tem permissão
@contrato_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_gerente_ou_superior:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@contrato_bp.route('/')
def index():
    """
    Lista todos os contratos
    """
    contratos = Contrato.query.all()
    return render_template('contratos/index.html', contratos=contratos)

@contrato_bp.route('/novo', methods=['GET', 'POST'])
def novo():
    """
    Cria um novo contrato
    """
    # Busca todos os centros de custo ativos para o formulário
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    
    # Busca todos os clientes ativos para o formulário
    clientes = Cliente.query.filter_by(ativo=True).all()
    
    if request.method == 'POST':
        centro_custo_id = request.form.get('centro_custo_id')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        estado = request.form.get('estado')
        cidade = request.form.get('cidade')
        cliente_direto_id = request.form.get('cliente_direto_id')
        cliente_final_id = request.form.get('cliente_final_id')
        valor_material = request.form.get('venda_material', '0')
        valor_servico = request.form.get('venda_servico', '0')
        data_base = request.form.get('data_base', '0')
        
        # Validação básica
        if not centro_custo_id or not nome:
            flash('Por favor, preencha todos os campos obrigatórios.', 'danger')
            return render_template('contratos/novo.html', centros_custo=centros_custo, clientes=clientes)
        
        # Criar o novo contrato
        try:
            contrato = Contrato()
            contrato.centro_custo_id = centro_custo_id
            contrato.nome = nome
            contrato.descricao = descricao
            contrato.estado = estado
            contrato.cidade = cidade
            contrato.cliente_direto_id = cliente_direto_id if cliente_direto_id else None
            contrato.cliente_final_id = cliente_final_id if cliente_final_id else None
            contrato.data_base = data_base
            
            # Converter valores de string para números
            valor_material = valor_material.replace('R$', '').replace('.', '').replace(',', '.').strip() if valor_material else '0'
            valor_servico = valor_servico.replace('R$', '').replace('.', '').replace(',', '.').strip() if valor_servico else '0'
            
            valor_material_float = float(valor_material)
            valor_servico_float = float(valor_servico)
            
            contrato.valor_mat = valor_material_float
            contrato.valor_ser = valor_servico_float
            # Calcular o valor total somando os valores de material e serviço
            contrato.valor_total = valor_material_float + valor_servico_float
            
            # Manter compatibilidade com o campo cliente (legado)
            cliente_direto_nome = None
            if cliente_direto_id:
                cliente_direto = Cliente.query.get(cliente_direto_id)
                if cliente_direto:
                    cliente_direto_nome = cliente_direto.nome
            
            contrato.cliente = cliente_direto_nome or "Não especificado"
            
            # Outros campos aqui...
            
            db.session.add(contrato)
            db.session.commit()
            
            flash('Contrato criado com sucesso!', 'success')
            return redirect(url_for('contrato.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar contrato: {str(e)}', 'danger')
    
    return render_template('contratos/novo.html', centros_custo=centros_custo, clientes=clientes)

@contrato_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    """
    Edita um contrato existente
    """
    contrato = Contrato.query.get_or_404(id)
    centros_custo = CentroCusto.query.filter_by(ativo=True).all()
    clientes = Cliente.query.filter_by(ativo=True).all()
    
    if request.method == 'POST':
        centro_custo_id = request.form.get('centro_custo_id')
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        cliente_direto_id = request.form.get('cliente_direto_id')
        cliente_final_id = request.form.get('cliente_final_id')
        
        # Validação básica
        if not centro_custo_id or not nome:
            flash('Por favor, preencha todos os campos obrigatórios.', 'danger')
            return render_template('contratos/editar.html', contrato=contrato, centros_custo=centros_custo, clientes=clientes)
        
        try:
            contrato.centro_custo_id = centro_custo_id
            contrato.nome = nome
            contrato.descricao = descricao
            contrato.cliente_direto_id = cliente_direto_id if cliente_direto_id else None
            contrato.cliente_final_id = cliente_final_id if cliente_final_id else None
            
            # Obter e processar os valores monetários
            valor_material = request.form.get('venda_material', '0')
            valor_servico = request.form.get('venda_servico', '0')
            
            # Converter valores de string para números
            valor_material = valor_material.replace('R$', '').replace('.', '').replace(',', '.').strip() if valor_material else '0'
            valor_servico = valor_servico.replace('R$', '').replace('.', '').replace(',', '.').strip() if valor_servico else '0'
            
            valor_material_float = float(valor_material)
            valor_servico_float = float(valor_servico)
            
            contrato.valor_mat = valor_material_float
            contrato.valor_ser = valor_servico_float
            # Calcular o valor total somando os valores de material e serviço
            contrato.valor_total = valor_material_float + valor_servico_float
            
            # Manter compatibilidade com o campo cliente (legado)
            cliente_direto_nome = None
            if cliente_direto_id:
                cliente_direto = Cliente.query.get(cliente_direto_id)
                if cliente_direto:
                    cliente_direto_nome = cliente_direto.nome
            
            contrato.cliente = cliente_direto_nome or "Não especificado"
            
            # Outros campos aqui...
            
            db.session.commit()
            flash('Contrato atualizado com sucesso!', 'success')
            return redirect(url_for('contrato.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar contrato: {str(e)}', 'danger')
    
    return render_template('contratos/editar.html', contrato=contrato, centros_custo=centros_custo, clientes=clientes)

@contrato_bp.route('/visualizar/<int:id>')
def visualizar(id):
    """
    Visualiza os detalhes de um contrato
    """
    contrato = Contrato.query.get_or_404(id)
    return render_template('contratos/visualizar.html', contrato=contrato)

@contrato_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """
    Exclui um contrato
    """
    contrato = Contrato.query.get_or_404(id)
    
    # Aqui você pode adicionar verificações adicionais antes de excluir
    
    db.session.delete(contrato)
    db.session.commit()
    
    flash('Contrato excluído com sucesso.', 'success')
    return redirect(url_for('contrato.index')) 