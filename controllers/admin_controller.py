from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime

from models.database import db
from models.usuario import Usuario
from models.centro_custo import CentroCusto
from models.contrato import Contrato
from models.material import Material
from models.plano_conta import PlanoConta
from models.cliente import Cliente
from models.endereco import Endereco

admin_bp = Blueprint('admin', __name__)

# Middleware para verificar se o usuário é administrador
@admin_bp.before_request
@login_required
def verificar_admin():
    if not current_user.is_admin:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@admin_bp.route('/')
def index():
    """
    Página inicial da área administrativa
    """
    # Estatísticas gerais
    total_usuarios = Usuario.query.count()
    total_centros_custo = CentroCusto.query.count()
    total_contratos = Contrato.query.count()
    total_materiais = Material.query.count()
    total_clientes = Cliente.query.count()
    
    # Usuários recentes
    usuarios_recentes = Usuario.query.order_by(Usuario.criado_em.desc()).limit(5).all()
    
    # Clientes recentes
    clientes_recentes = Cliente.query.order_by(Cliente.criado_em.desc()).limit(5).all()
    
    return render_template('admin/index.html',
                          total_usuarios=total_usuarios,
                          total_centros_custo=total_centros_custo,
                          total_contratos=total_contratos,
                          total_materiais=total_materiais,
                          total_clientes=total_clientes,
                          usuarios_recentes=usuarios_recentes,
                          clientes_recentes=clientes_recentes)

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
    # Aqui você pode implementar a lógica para exibir logs do sistema
    return render_template('admin/logs.html')

@admin_bp.route('/backup')
def backup():
    """
    Página de backup do sistema
    """
    # Aqui você pode implementar a lógica para realizar backups do banco de dados
    return render_template('admin/backup.html') 