from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import requests
import re
import json
import traceback

from models.database import db
from models.cliente import Cliente
from models.endereco import Endereco

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
    """
    Lista todos os clientes
    """
    clientes = Cliente.query.order_by(Cliente.nome).all()
    return render_template('clientes/index.html', clientes=clientes)

@cliente_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """
    Cria um novo cliente
    """
    if request.method == 'POST':
        # Dados do cliente
        nome = request.form.get('nome')
        cnpj = request.form.get('cnpj')
        email = request.form.get('email')
        telefone = request.form.get('telefone')
        observacoes = request.form.get('observacoes')
        ativo = True if request.form.get('ativo') == 'on' else False
        
        # Dados do endereço
        logradouro = request.form.get('logradouro')
        numero = request.form.get('numero')
        complemento = request.form.get('complemento')
        bairro = request.form.get('bairro')
        cidade = request.form.get('cidade')
        estado = request.form.get('estado')
        cep = request.form.get('cep')
        
        # Validação básica
        if not nome or not cnpj or not logradouro or not cidade or not estado:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('clientes/novo.html')
        
        # Remover caracteres especiais do CNPJ
        cnpj = "".join(c for c in cnpj if c.isdigit())
        
        # Verificar se o CNPJ já existe
        cliente_existente = Cliente.query.filter_by(cnpj=cnpj).first()
        if cliente_existente:
            flash(f'Um cliente com o CNPJ {cnpj} já existe!', 'danger')
            return render_template('clientes/novo.html')
        
        try:
            # Criar novo cliente
            novo_cliente = Cliente(
                nome=nome,
                cnpj=cnpj,
                email=email,
                telefone=telefone,
                observacoes=observacoes,
                ativo=ativo
            )
            
            # Salvar o cliente para gerar o ID
            db.session.add(novo_cliente)
            db.session.flush()  # Apenas para obter o ID, sem fazer commit ainda
            
            # Criar o endereço principal
            novo_endereco = Endereco(
                logradouro=logradouro,
                numero=numero,
                complemento=complemento,
                bairro=bairro,
                cidade=cidade,
                estado=estado,
                cep=cep,
                tipo='COMERCIAL',
                principal=True,
                cliente_id=novo_cliente.id
            )
            
            # Salvar o endereço
            db.session.add(novo_endereco)
            db.session.commit()
            
            flash('Cliente cadastrado com sucesso!', 'success')
            return redirect(url_for('cliente.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao cadastrar cliente: {str(e)}', 'danger')
            
    return render_template('clientes/novo.html')

@cliente_bp.route('/visualizar/<int:id>')
@login_required
def visualizar(id):
    """
    Visualiza os detalhes de um cliente
    """
    cliente = Cliente.query.get_or_404(id)
    # Buscar endereços do cliente
    enderecos = Endereco.query.filter_by(cliente_id=cliente.id).all()
    
    return render_template('clientes/visualizar.html', cliente=cliente, enderecos=enderecos)

@cliente_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """
    Edita um cliente existente
    """
    cliente = Cliente.query.get_or_404(id)
    endereco_principal = cliente.get_endereco_principal()
    
    if endereco_principal is None:
        # Criar um endereço vazio se não existir
        endereco_principal = Endereco(
            logradouro='',
            cidade='',
            estado='',
            cliente_id=cliente.id,
            principal=True
        )
    
    if request.method == 'POST':
        # Dados do cliente
        nome = request.form.get('nome')
        cnpj = request.form.get('cnpj')
        email = request.form.get('email')
        telefone = request.form.get('telefone')
        observacoes = request.form.get('observacoes')
        ativo = True if request.form.get('ativo') == 'on' else False
        
        # Dados do endereço
        logradouro = request.form.get('logradouro')
        numero = request.form.get('numero')
        complemento = request.form.get('complemento')
        bairro = request.form.get('bairro')
        cidade = request.form.get('cidade')
        estado = request.form.get('estado')
        cep = request.form.get('cep')
        
        # Validação básica
        if not nome or not cnpj or not logradouro or not cidade or not estado:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('clientes/editar.html', cliente=cliente, endereco=endereco_principal)
        
        # Remover caracteres especiais do CNPJ
        cnpj = "".join(c for c in cnpj if c.isdigit())
        
        # Verificar se o CNPJ já existe (exceto para o cliente atual)
        cliente_existente = Cliente.query.filter(
            Cliente.cnpj == cnpj,
            Cliente.id != id
        ).first()
        
        if cliente_existente:
            flash(f'Um cliente com o CNPJ {cnpj} já existe!', 'danger')
            return render_template('clientes/editar.html', cliente=cliente, endereco=endereco_principal)
        
        try:
            # Atualizar o cliente
            cliente.nome = nome
            cliente.cnpj = cnpj
            cliente.email = email
            cliente.telefone = telefone
            cliente.observacoes = observacoes
            cliente.ativo = ativo
            
            # Atualizar o endereço principal
            if endereco_principal.id:  # Se já existe
                endereco_principal.logradouro = logradouro
                endereco_principal.numero = numero
                endereco_principal.complemento = complemento
                endereco_principal.bairro = bairro
                endereco_principal.cidade = cidade
                endereco_principal.estado = estado
                endereco_principal.cep = cep
            else:  # Se não existe, criar novo
                endereco_principal = Endereco(
                    logradouro=logradouro,
                    numero=numero,
                    complemento=complemento,
                    bairro=bairro,
                    cidade=cidade,
                    estado=estado,
                    cep=cep,
                    tipo='COMERCIAL',
                    principal=True,
                    cliente_id=cliente.id
                )
                db.session.add(endereco_principal)
            
            # Salvar as alterações
            db.session.commit()
            
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('cliente.visualizar', id=cliente.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar cliente: {str(e)}', 'danger')
    
    return render_template('clientes/editar.html', cliente=cliente, endereco=endereco_principal)

@cliente_bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """
    Exclui um cliente
    """
    cliente = Cliente.query.get_or_404(id)
    
    try:
        # Os endereços serão excluídos automaticamente devido ao cascade
        nome = cliente.nome
        cliente.delete()
        flash(f'Cliente "{nome}" excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir cliente: {str(e)}', 'danger')
    
    return redirect(url_for('cliente.index'))

@cliente_bp.route('/endereco/novo/<int:cliente_id>', methods=['GET', 'POST'])
@login_required
def novo_endereco(cliente_id):
    """
    Adiciona um novo endereço para o cliente
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    
    if request.method == 'POST':
        # Dados do endereço
        logradouro = request.form.get('logradouro')
        numero = request.form.get('numero')
        complemento = request.form.get('complemento')
        bairro = request.form.get('bairro')
        cidade = request.form.get('cidade')
        estado = request.form.get('estado')
        cep = request.form.get('cep')
        tipo = request.form.get('tipo', 'COMERCIAL')
        principal = True if request.form.get('principal') == 'on' else False
        
        # Validação básica
        if not logradouro or not cidade or not estado:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('clientes/novo_endereco.html', cliente=cliente)
        
        try:
            # Se marcado como principal, desmarcar os outros
            if principal:
                Endereco.query.filter_by(cliente_id=cliente_id, principal=True).update({'principal': False})
            
            # Criar novo endereço
            novo_endereco = Endereco(
                logradouro=logradouro,
                numero=numero,
                complemento=complemento,
                bairro=bairro,
                cidade=cidade,
                estado=estado,
                cep=cep,
                tipo=tipo,
                principal=principal,
                cliente_id=cliente_id
            )
            
            # Salvar o endereço
            db.session.add(novo_endereco)
            db.session.commit()
            
            flash('Endereço adicionado com sucesso!', 'success')
            return redirect(url_for('cliente.visualizar', id=cliente_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao adicionar endereço: {str(e)}', 'danger')
    
    return render_template('clientes/novo_endereco.html', cliente=cliente)

@cliente_bp.route('/endereco/editar/<int:endereco_id>', methods=['GET', 'POST'])
@login_required
def editar_endereco(endereco_id):
    """
    Edita um endereço existente
    """
    endereco = Endereco.query.get_or_404(endereco_id)
    cliente = Cliente.query.get_or_404(endereco.cliente_id)
    
    if request.method == 'POST':
        # Dados do endereço
        logradouro = request.form.get('logradouro')
        numero = request.form.get('numero')
        complemento = request.form.get('complemento')
        bairro = request.form.get('bairro')
        cidade = request.form.get('cidade')
        estado = request.form.get('estado')
        cep = request.form.get('cep')
        tipo = request.form.get('tipo', endereco.tipo)
        principal = True if request.form.get('principal') == 'on' else False
        
        # Validação básica
        if not logradouro or not cidade or not estado:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'danger')
            return render_template('clientes/editar_endereco.html', endereco=endereco, cliente=cliente)
        
        try:
            # Se marcado como principal, desmarcar os outros
            if principal and not endereco.principal:
                Endereco.query.filter_by(cliente_id=endereco.cliente_id, principal=True).update({'principal': False})
            
            # Atualizar o endereço
            endereco.logradouro = logradouro
            endereco.numero = numero
            endereco.complemento = complemento
            endereco.bairro = bairro
            endereco.cidade = cidade
            endereco.estado = estado
            endereco.cep = cep
            endereco.tipo = tipo
            endereco.principal = principal
            
            # Salvar as alterações
            db.session.commit()
            
            flash('Endereço atualizado com sucesso!', 'success')
            return redirect(url_for('cliente.visualizar', id=endereco.cliente_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar endereço: {str(e)}', 'danger')
    
    return render_template('clientes/editar_endereco.html', endereco=endereco, cliente=cliente)

@cliente_bp.route('/endereco/excluir/<int:endereco_id>', methods=['POST'])
@login_required
def excluir_endereco(endereco_id):
    """
    Exclui um endereço
    """
    endereco = Endereco.query.get_or_404(endereco_id)
    cliente_id = endereco.cliente_id
    
    # Verificar se é o único endereço do cliente
    qtd_enderecos = Endereco.query.filter_by(cliente_id=cliente_id).count()
    if qtd_enderecos <= 1:
        flash('Não é possível excluir o único endereço do cliente!', 'danger')
        return redirect(url_for('cliente.visualizar', id=cliente_id))
    
    # Verificar se é o endereço principal
    if endereco.principal:
        # Buscar outro endereço para marcar como principal
        outro_endereco = Endereco.query.filter(
            Endereco.cliente_id == cliente_id,
            Endereco.id != endereco_id
        ).first()
        
        if outro_endereco:
            outro_endereco.principal = True
            db.session.add(outro_endereco)
    
    try:
        # Excluir o endereço
        db.session.delete(endereco)
        db.session.commit()
        
        flash('Endereço excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir endereço: {str(e)}', 'danger')
    
    return redirect(url_for('cliente.visualizar', id=cliente_id))

@cliente_bp.route('/api/clientes')
@login_required
def api_clientes():
    """
    Retorna os clientes em formato JSON (para uso em APIs)
    """
    query = Cliente.query
    
    # Filtragem por status (ativo/inativo)
    status = request.args.get('ativo')
    if status is not None:
        is_active = status.lower() == 'true'
        query = query.filter_by(ativo=is_active)
    
    # Busca por texto
    search = request.args.get('q')
    if search:
        query = query.filter(
            db.or_(
                Cliente.nome.like(f'%{search}%'),
                Cliente.cnpj.like(f'%{search}%'),
                Cliente.email.like(f'%{search}%')
            )
        )
    
    # Ordenação
    sort_by = request.args.get('sort_by', 'nome')
    sort_dir = request.args.get('sort_dir', 'asc')
    
    if sort_dir == 'desc':
        query = query.order_by(db.desc(getattr(Cliente, sort_by)))
    else:
        query = query.order_by(getattr(Cliente, sort_by))
    
    clientes = query.all()
    return jsonify([cliente.to_dict() for cliente in clientes])

@cliente_bp.route('/consultar_cnpj/<cnpj>', methods=['GET'])
@login_required
def consultar_cnpj(cnpj):
    """
    Consulta informações do CNPJ na API pública Brasil API
    """
    try:
        # Log da requisição
        print(f"INÍCIO DA CONSULTA CNPJ: {cnpj}")
        print(f"Path da requisição: {request.path}")
        print(f"Método: {request.method}")
        print(f"User Agent: {request.headers.get('User-Agent')}")
        
        # Remover caracteres especiais do CNPJ
        cnpj_limpo = re.sub(r'[^0-9]', '', cnpj)
        
        if len(cnpj_limpo) != 14:
            print(f"CNPJ inválido: {cnpj_limpo} - deve ter 14 dígitos")
            return jsonify({"success": False, "error": "CNPJ deve conter 14 dígitos"})
        
        # Consultar na API
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        print(f"Fazendo requisição para: {url}")
        
        try:
            # Configurar headers para parecer mais com um navegador
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status da resposta: {response.status_code}")
            print(f"Headers da resposta: {response.headers}")
            
            if response.status_code == 200:
                try:
                    dados = response.json()
                    print(f"Dados recebidos da API: {json.dumps(dados, ensure_ascii=False)}")
                    
                    # Se não tiver razão social, pode ser uma resposta vazia ou inválida
                    if not dados.get("razao_social"):
                        return jsonify({
                            "success": False, 
                            "error": "CNPJ encontrado, mas sem dados completos da empresa"
                        })
                    
                    # Formatar o retorno para o frontend
                    resultado = {
                        "success": True,
                        "dados": {
                            "nome": dados.get("razao_social"),
                            "cnpj": cnpj,  # Mantém o CNPJ formatado
                            "telefone": dados.get("ddd_telefone_1", ""),
                            "logradouro": dados.get("logradouro", ""),
                            "numero": dados.get("numero", ""),
                            "complemento": dados.get("complemento", ""),
                            "bairro": dados.get("bairro", ""),
                            "cidade": dados.get("municipio", ""),
                            "estado": dados.get("uf", ""),
                            "cep": dados.get("cep", "").replace(".", "")
                        }
                    }
                    print(f"Retornando resultado: {json.dumps(resultado, ensure_ascii=False)}")
                    return jsonify(resultado)
                except json.JSONDecodeError as e:
                    print(f"Erro ao decodificar JSON: {str(e)}")
                    print(f"Conteúdo da resposta: {response.text}")
                    return jsonify({
                        "success": False, 
                        "error": "Erro ao processar dados retornados pela API"
                    })
            elif response.status_code == 404:
                print(f"CNPJ não encontrado: {cnpj_limpo}")
                return jsonify({"success": False, "error": "CNPJ não encontrado na base de dados"})
            elif response.status_code == 429:
                print(f"Limite de requisições excedido para CNPJ: {cnpj_limpo}")
                return jsonify({"success": False, "error": "Limite de requisições excedido. Tente novamente em alguns minutos."})
            else:
                print(f"Erro na API para CNPJ {cnpj_limpo}: Status {response.status_code}")
                print(f"Conteúdo da resposta: {response.text}")
                return jsonify({"success": False, "error": f"Erro na consulta à API: Status {response.status_code}"})
        
        except requests.exceptions.Timeout:
            print(f"Timeout na requisição à API Brasil para CNPJ: {cnpj_limpo}")
            return jsonify({"success": False, "error": "Tempo limite excedido na consulta à API. Tente novamente."})
        except requests.exceptions.ConnectionError:
            print(f"Erro de conexão com a API Brasil para CNPJ: {cnpj_limpo}")
            return jsonify({"success": False, "error": "Erro de conexão com o serviço. Verifique sua internet."})
        except requests.exceptions.RequestException as e:
            print(f"Erro na requisição para CNPJ {cnpj_limpo}: {str(e)}")
            return jsonify({"success": False, "error": f"Erro na comunicação com a API: {str(e)}"})
    
    except Exception as e:
        print(f"Erro inesperado na consulta de CNPJ {cnpj}: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Erro inesperado ao processar a consulta: {str(e)}"}) 