# Exemplo de Implementação do Sistema de Permissões

## Atualizando um Controller Existente

Vamos mostrar como atualizar o `cliente_controller.py` para usar o novo sistema de permissões:

### Antes (Sistema Antigo)

```python
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

cliente_bp = Blueprint('cliente', __name__)

# Middleware para verificar se o usuário tem permissão
@cliente_bp.before_request
@login_required
def verificar_permissao():
    if not current_user.is_gerente_ou_superior:
        flash('Acesso restrito. Você não tem permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard.index'))

@cliente_bp.route('/')
@login_required
def index():
    clientes = Cliente.query.order_by(Cliente.nome).all()
    return render_template('clientes/index.html', clientes=clientes)
```

### Depois (Sistema Novo)

```python
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from utils.permissoes import verificar_permissao

cliente_bp = Blueprint('cliente', __name__)

@cliente_bp.route('/')
@login_required
@verificar_permissao('CLIENTES', 'visualizar')
def index():
    clientes = Cliente.query.order_by(Cliente.nome).all()
    return render_template('clientes/index.html', clientes=clientes)

@cliente_bp.route('/novo', methods=['GET', 'POST'])
@login_required
@verificar_permissao('CLIENTES', 'criar')
def novo():
    if request.method == 'POST':
        # Lógica para criar cliente
        pass
    return render_template('clientes/novo.html')

@cliente_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@verificar_permissao('CLIENTES', 'editar')
def editar(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == 'POST':
        # Lógica para editar cliente
        pass
    return render_template('clientes/editar.html', cliente=cliente)

@cliente_bp.route('/<int:id>/excluir', methods=['POST'])
@login_required
@verificar_permissao('CLIENTES', 'excluir')
def excluir(id):
    cliente = Cliente.query.get_or_404(id)
    # Lógica para excluir cliente
    return redirect(url_for('cliente.index'))
```

## Atualizando Templates

### Menu de Navegação

```html
<!-- Antes -->
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('cliente.index') }}">
        <i class="fas fa-handshake"></i> Clientes
    </a>
</li>

<!-- Depois -->
{% if verificar_permissao_menu('CLIENTES') %}
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('cliente.index') }}">
        <i class="fas fa-handshake"></i> Clientes
    </a>
</li>
{% endif %}
```

### Botões de Ação

```html
<!-- Botão Novo Cliente -->
{% if verificar_permissao('CLIENTES', 'criar') %}
    <a href="{{ url_for('cliente.novo') }}" class="btn btn-primary">
        <i class="fas fa-plus"></i> Novo Cliente
    </a>
{% endif %}

<!-- Botão Editar -->
{% if verificar_permissao('CLIENTES', 'editar') %}
    <a href="{{ url_for('cliente.editar', id=cliente.id) }}" class="btn btn-sm btn-outline-primary">
        <i class="fas fa-edit"></i>
    </a>
{% endif %}

<!-- Botão Excluir -->
{% if verificar_permissao('CLIENTES', 'excluir') %}
    <button type="button" class="btn btn-sm btn-outline-danger" onclick="confirmarExclusao({{ cliente.id }})">
        <i class="fas fa-trash"></i>
    </button>
{% endif %}

<!-- Botão Exportar -->
{% if verificar_permissao('CLIENTES', 'exportar') %}
    <a href="{{ url_for('cliente.exportar') }}" class="btn btn-success">
        <i class="fas fa-download"></i> Exportar
    </a>
{% endif %}
```

## Verificação Programática

```python
# Verificar permissão em uma função
def processar_dados():
    if not current_user.is_permissao('CLIENTES', 'editar'):
        flash('Você não tem permissão para editar clientes', 'error')
        return redirect(url_for('cliente.index'))
    
    # Continuar com a lógica...

# Verificar múltiplas permissões
def operacao_complexa():
    permissoes_necessarias = ['CLIENTES', 'CONTRATOS']
    for modulo in permissoes_necessarias:
        if not current_user.is_permissao(modulo, 'visualizar'):
            flash(f'Sem permissão para acessar {modulo}', 'error')
            return redirect(url_for('dashboard.index'))
    
    # Continuar com a operação...
```

## API com Verificação de Permissões

```python
@cliente_bp.route('/api/clientes')
@login_required
@verificar_permissao('CLIENTES', 'visualizar')
def api_clientes():
    clientes = Cliente.query.all()
    return jsonify([cliente.to_dict() for cliente in clientes])

@cliente_bp.route('/api/clientes', methods=['POST'])
@login_required
@verificar_permissao('CLIENTES', 'criar')
def api_criar_cliente():
    data = request.get_json()
    # Lógica para criar cliente
    return jsonify({'success': True})
```

## Verificação Condicional em Templates

```html
<!-- Mostrar seção apenas se tiver permissão -->
{% if verificar_permissao('CLIENTES', 'editar') %}
<div class="card">
    <div class="card-header">
        <h5>Configurações Avançadas</h5>
    </div>
    <div class="card-body">
        <!-- Conteúdo sensível -->
    </div>
</div>
{% endif %}

<!-- Mostrar informações diferentes baseadas na permissão -->
{% if verificar_permissao('CLIENTES', 'excluir') %}
    <span class="badge badge-danger">Cliente Inativo</span>
{% else %}
    <span class="badge badge-warning">Cliente Inativo</span>
{% endif %}
```

## Migração Gradual

Para migrar gradualmente, você pode:

1. **Manter ambos os sistemas** temporariamente
2. **Usar o novo sistema** em novos controllers
3. **Atualizar controllers existentes** um por vez
4. **Remover o sistema antigo** quando todos estiverem migrados

```python
# Exemplo de migração gradual
@cliente_bp.route('/')
@login_required
def index():
    # Verificação híbrida (temporária)
    if not (current_user.is_gerente_ou_superior or current_user.is_permissao('CLIENTES', 'visualizar')):
        flash('Acesso restrito', 'error')
        return redirect(url_for('dashboard.index'))
    
    clientes = Cliente.query.order_by(Cliente.nome).all()
    return render_template('clientes/index.html', clientes=clientes)
```

## Benefícios da Migração

1. **Controle Granular**: Permissões específicas por ação
2. **Flexibilidade**: Permissões por usuário, departamento ou cargo
3. **Interface Administrativa**: Gerenciamento visual das permissões
4. **Auditoria**: Logs de tentativas de acesso
5. **Escalabilidade**: Fácil adição de novos módulos e permissões
6. **Manutenibilidade**: Código mais limpo e organizado

