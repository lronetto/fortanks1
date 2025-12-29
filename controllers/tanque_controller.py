from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime
import pandas as pd
import io
from sqlalchemy import or_

from models.database import db
from models.tanque import Tanques, TanquesPecas, TanquesGrupos
from models.contrato import Contrato
from models.material import Materiais
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
    tanques = Tanques.query.order_by(Tanques.contrato_id, Tanques.nome).all()
    tanques_com_pecas = []
    for tanque in tanques:
        pecas = TanquesPecas.query.filter_by(tanque_id=tanque.id).count()
        tanque.pecas_cadastradas = pecas
        tanques_com_pecas.append(tanque)
    tanques = tanques_com_pecas
    contratos = Contrato.query.all()
    sistemas = ['SC-10', 'SC-14', 'SR-06']
    grupos = TanquesGrupos.get_all()
    return render_template('tanques/index.html', tanques=tanques, contratos=contratos, sistemas=sistemas, grupos=grupos)

@tanque_bp.route('/contrato/<int:contrato_id>')
def listar_por_contrato(contrato_id):
    """
    Lista tanques de um contrato específico
    """
    contrato = Contrato.query.get_or_404(contrato_id)
    tanques = Tanques.query.filter_by(contrato_id=contrato_id).all()
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
            novo_tanque = Tanques(
                # Definir o UN com base no método gerar_un
                un=Tanques.gerar_un(),
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
    tanque = Tanques.query.get_or_404(id)
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
    tanque = Tanques.query.get_or_404(id)
    return render_template('tanques/visualizar.html', tanque=tanque)

@tanque_bp.route('/duplicar/<int:id>', methods=['POST'])
def duplicar(id):
    """
    Duplica um tanque existente (pode duplicar múltiplas vezes)
    """
    tanque_original = Tanques.query.get_or_404(id)
    
    try:
        # Obter parâmetros do formulário
        quantidade = int(request.form.get('quantidade', 1))
        formato_nome = request.form.get('formato_nome', 'copia')
        numero_inicial = int(request.form.get('numero_inicial', 1))
        renomear_original = request.form.get('renomear_original') == '1'
        
        # Validar quantidade
        if quantidade < 1:
            quantidade = 1
        if quantidade > 100:
            quantidade = 100
        
        # Validar número inicial
        if numero_inicial < 1:
            numero_inicial = 1
        
        tanques_criados = []
        
        # Guardar nome original antes de qualquer modificação
        nome_base_original = tanque_original.nome
        
        # Função auxiliar para gerar nome baseado no formato
        def gerar_nome(numero, nome_base, formato, qtd_total=1):
            if formato == 'sequencial':
                return f"{numero} - {nome_base}"
            elif formato == 'nome_zero':
                numero_formatado = f"{numero:02d}"
                return f"{nome_base} {numero_formatado}"
            elif formato == 'apenas_numero':
                numero_formatado = f"{numero:02d}"
                return numero_formatado
            elif formato == 'copia':
                if qtd_total == 1:
                    return f"{nome_base} (Cópia)"
                else:
                    return f"{nome_base} (Cópia {numero})"
            elif formato == 'sequencial_copia':
                return f"{numero} - {nome_base} (Cópia)"
            else:
                return f"{nome_base} (Cópia {numero})"
        
        # Se renomear original, renomear primeiro usando o nome base original
        if renomear_original:
            nome_original_renomeado = gerar_nome(numero_inicial, nome_base_original, formato_nome, quantidade)
            tanque_original.nome = nome_original_renomeado
            db.session.commit()
        
        # Criar múltiplas cópias
        # Se renomear original, as cópias começam em numero_inicial + 1
        inicio_copias = numero_inicial + 1 if renomear_original else numero_inicial
        
        for i in range(quantidade):
            # Gerar nome baseado no formato escolhido
            numero_atual = inicio_copias + i
            
            # Usar nome base original para as cópias
            novo_nome = gerar_nome(numero_atual, nome_base_original, formato_nome, quantidade)
            
            # Criar novo tanque com dados do original
            novo_tanque = Tanques(
                un=Tanques.gerar_un(),  # Gerar novo UN
                nome=novo_nome,
                sistema=tanque_original.sistema,
                dimensoes=tanque_original.dimensoes,
                diametro=tanque_original.diametro,
                comprimento=tanque_original.comprimento,
                largura=tanque_original.largura,
                altura_total=tanque_original.altura_total,
                altura_util=tanque_original.altura_util,
                quantidade=tanque_original.quantidade,
                cobertura=tanque_original.cobertura,
                ncabospn=tanque_original.ncabospn,
                ncabospf=tanque_original.ncabospf,
                quantidade_bainhas=tanque_original.quantidade_bainhas,
                placas_normais=tanque_original.placas_normais,
                placas_fecho=tanque_original.placas_fecho,
                valorUnitario=tanque_original.valorUnitario,
                contrato_id=tanque_original.contrato_id,
                item_nf=tanque_original.item_nf
            )
            
            # Salvar o novo tanque
            novo_tanque.save()
            tanques_criados.append(novo_tanque.id)
        
        mensagem = f'{quantidade} cópia(s) do tanque "{tanque_original.nome}" criada(s) com sucesso!'
        flash(mensagem, 'success')
        
        # Verificar se é requisição AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': mensagem,
                'tanques_criados': tanques_criados,
                'quantidade': quantidade
            })
        
        # Redirecionar para a página de tanques
        return redirect(url_for('tanque.index'))
        
    except Exception as e:
        db.session.rollback()
        error_msg = f'Erro ao duplicar tanque: {str(e)}'
        flash(error_msg, 'danger')
        
        # Verificar se é requisição AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        return redirect(url_for('tanque.index'))

@tanque_bp.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    """
    Exclui um tanque
    """
    tanque = Tanques.query.get_or_404(id)
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
@tanque_bp.route('/relatorio-projeto-excel/<int:contrato_id>', methods=['GET'])
def relatorio_projeto_excel(contrato_id):
    """
    Gera relatório em Excel com tanques do projeto, quantidade prevista (PN+PF) e realizada (concretadas)
    """
    try:
        # Buscar o contrato
        contrato = Contrato.query.get_or_404(contrato_id)
        
        # Buscar todos os tanques do contrato
        tanques = Tanques.query.filter_by(contrato_id=contrato_id).order_by(Tanques.nome).all()
        
        if not tanques:
            flash('Nenhum tanque encontrado para este projeto.', 'warning')
            return redirect(url_for('tanque.index'))
        
        # Preparar dados para o relatório
        dados_relatorio = []
        
        for tanque in tanques:
            # Calcular quantidade prevista: (placas_normais + placas_fecho) * quantidade
            placas_normais = tanque.placas_normais or 0
            placas_fecho = tanque.placas_fecho or 0
            quantidade_tanques = tanque.quantidade or 1
            quantidade_prevista = (placas_normais + placas_fecho) * quantidade_tanques
            
            # Buscar peças concretadas (com data_concretagem não nula)
            # Considerar peças do tipo "Placa Normal", "Placa Fecho", "PN" ou "PF"
            # Também considerar variações como peças que começam com "Placa"
            pecas_concretadas = TanquesPecas.query.filter(
                TanquesPecas.tanque_id == tanque.id,
                TanquesPecas.data_concretagem.isnot(None),
            ).count()
            
            dados_relatorio.append({
                'ID': tanque.id,
                'Tanque': tanque.nome,
                'Placas': quantidade_prevista,
                'Quantidade Realizada (Concretadas)': pecas_concretadas,
                'Concluido': (pecas_concretadas/quantidade_prevista)*100,
            })
        
        # Criar DataFrame
        df = pd.DataFrame(dados_relatorio)
        
        # Adicionar linha de totais
        totais = {
            'ID': '',
            'Tanque': 'TOTAL',
            'Placas': df['Placas'].sum(),
            'Quantidade Realizada (Concretadas)': df['Quantidade Realizada (Concretadas)'].sum(),
            'Concluido': (df['Quantidade Realizada (Concretadas)'].sum()/df['Placas'].sum())*100
        }
        
        # Adicionar linha de totais ao DataFrame
        df_totais = pd.DataFrame([totais])
        df = pd.concat([df, df_totais], ignore_index=True)
        
        # Criar Excel na memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Relatório de Tanques')
            
            # Ajustar largura das colunas
            from openpyxl.utils import get_column_letter
            from openpyxl.styles import Font, PatternFill
            
            worksheet = writer.sheets['Relatório de Tanques']
            for idx, col in enumerate(df.columns):
                max_length = max(
                    df[col].astype(str).apply(len).max(),
                    len(col)
                )
                # Limitar largura máxima
                adjusted_width = min(max_length + 2, 50)
                col_letter = get_column_letter(idx + 1)
                worksheet.column_dimensions[col_letter].width = adjusted_width
            
            # Formatar linha de totais (última linha)
            last_row = len(df) + 1  # +1 porque o Excel começa em 1 e tem cabeçalho
            for col_idx, col in enumerate(df.columns):
                col_letter = get_column_letter(col_idx + 1)
                cell = worksheet[f'{col_letter}{last_row}']
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color='D3D3D3', end_color='D3D3D3', fill_type='solid')
        
        output.seek(0)
        
        # Nome do arquivo
        nome_arquivo = f"relatorio_tanques_{contrato.nome.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=nome_arquivo
        )
        
    except Exception as e:
        flash(f'Erro ao gerar relatório: {str(e)}', 'danger')
        return redirect(url_for('tanque.index'))

@tanque_bp.route('/grupos', methods=['GET', 'POST'])
def grupos():
    """
    Lista e gerencia grupos de tanques
    """
    if request.method == 'POST':
        # Criar novo grupo
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        cor = request.form.get('cor', '#007bff')
        icone = request.form.get('icone', 'fas fa-water')
        
        if not nome:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'O nome do grupo é obrigatório!'}), 400
            flash('O nome do grupo é obrigatório!', 'danger')
            return redirect(url_for('tanque.grupos'))
        
        try:
            grupo = TanquesGrupos(
                nome=nome,
                descricao=descricao,
                cor=cor,
                icone=icone
            )
            grupo.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': f'Grupo "{nome}" criado com sucesso!',
                    'grupo': {
                        'id': grupo.id,
                        'nome': grupo.nome,
                        'total_tanques': grupo.total_tanques
                    }
                })
            
            flash(f'Grupo "{nome}" criado com sucesso!', 'success')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': str(e)}), 400
            flash(f'Erro ao criar grupo: {str(e)}', 'danger')
        
        return redirect(url_for('tanque.grupos'))
    
    grupos = TanquesGrupos.get_all()
    return render_template('tanques/grupos.html', grupos=grupos)

@tanque_bp.route('/grupos/<int:id>/editar', methods=['POST'])
def editar_grupo(id):
    """
    Edita um grupo de tanques
    """
    grupo = TanquesGrupos.query.get_or_404(id)
    
    nome = request.form.get('nome')
    descricao = request.form.get('descricao')
    cor = request.form.get('cor', '#007bff')
    icone = request.form.get('icone', 'fas fa-water')
    
    if not nome:
        flash('O nome do grupo é obrigatório!', 'danger')
        return redirect(url_for('tanque.grupos'))
    
    try:
        grupo.nome = nome
        grupo.descricao = descricao
        grupo.cor = cor
        grupo.icone = icone
        grupo.save()
        flash(f'Grupo "{nome}" atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar grupo: {str(e)}', 'danger')
    
    return redirect(url_for('tanque.grupos'))

@tanque_bp.route('/grupos/<int:id>/excluir', methods=['POST'])
def excluir_grupo(id):
    """
    Exclui um grupo de tanques
    """
    grupo = TanquesGrupos.query.get_or_404(id)
    
    try:
        nome = grupo.nome
        grupo.delete()
        flash(f'Grupo "{nome}" excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir grupo: {str(e)}', 'danger')
    
    return redirect(url_for('tanque.grupos'))

@tanque_bp.route('/grupos/adicionar-tanques', methods=['POST'])
def adicionar_tanques_grupo():
    """
    Adiciona tanques selecionados a um grupo
    """
    grupo_id = request.form.get('grupo_id')
    tanque_ids = request.form.getlist('tanque_ids')
    
    if not grupo_id or not tanque_ids:
        flash('Selecione um grupo e pelo menos um tanque.', 'warning')
        return redirect(url_for('tanque.index'))
    
    grupo = TanquesGrupos.query.get_or_404(grupo_id)
    
    try:
        tanques_adicionados = 0
        tanques_ja_no_grupo = 0
        
        for tanque_id in tanque_ids:
            try:
                tanque_id_int = int(tanque_id)
                tanque = Tanques.query.get(tanque_id_int)
                if tanque:
                    if tanque not in grupo.tanques:
                        grupo.tanques.append(tanque)
                        tanques_adicionados += 1
                    else:
                        tanques_ja_no_grupo += 1
            except (ValueError, TypeError) as e:
                continue
        
        # Fazer commit de uma vez só
        if tanques_adicionados > 0:
            db.session.commit()
        
        mensagem = f'{tanques_adicionados} tanque(s) adicionado(s) ao grupo "{grupo.nome}"!'
        if tanques_ja_no_grupo > 0:
            mensagem += f' {tanques_ja_no_grupo} tanque(s) já estavam no grupo.'
        
        flash(mensagem, 'success' if tanques_adicionados > 0 else 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao adicionar tanques ao grupo: {str(e)}', 'danger')
    
    return redirect(url_for('tanque.index'))

@tanque_bp.route('/grupos/<int:grupo_id>/remover-tanque/<int:tanque_id>', methods=['POST'])
def remover_tanque_grupo(grupo_id, tanque_id):
    """
    Remove um tanque de um grupo
    """
    grupo = TanquesGrupos.query.get_or_404(grupo_id)
    tanque = Tanques.query.get_or_404(tanque_id)
    
    try:
        grupo.remover_tanque(tanque)
        flash(f'Tanque "{tanque.nome}" removido do grupo "{grupo.nome}"!', 'success')
    except Exception as e:
        flash(f'Erro ao remover tanque do grupo: {str(e)}', 'danger')
    
    return redirect(url_for('tanque.grupos')) 