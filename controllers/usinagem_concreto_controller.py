from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_login import login_required, current_user
from models.material import Materiais
from models.unidade import Unidades, UnidadesConversao
from models.concreto import ConcretoTracos, ConcretoTracosItens, ConcretoUsinagensMateriais, ConcretoUsinagensRompimentos, ConcretoUsinagens
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
from markupsafe import Markup
import pandas as pd
import io
import xlsxwriter
import os
import tempfile
from werkzeug.utils import secure_filename


# Criação do blueprint
usinagem_concreto = Blueprint('usinagem_concreto', __name__)

#
# Rotas para API
#

@usinagem_concreto.route('/api/materiais-para-traco')
@login_required
def api_materiais_para_traco():
    """API para obter materiais que podem ser usados em traços de concreto"""
    try:
        # Busca todos os materiais ordenados por nome
        materiais = Materiais.query.order_by(Materiais.nome).all()
        
        # Transforma em JSON
        result = []
        for m in materiais:
            result.append({
                'id': m.id,
                'codigo': m.codigo,
                'nome': m.nome,
                'unidade_id': m.unidade_id
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@usinagem_concreto.route('/api/conversoes-unidade', methods=['GET'])
@login_required
def api_conversoes_unidade():
    """Retorna todas as conversões de unidade cadastradas"""
    try:
        conversoes = UnidadesConversao.query.all()
        resultado = []
        
        for conversao in conversoes:
            resultado.append({
                'id': conversao.id,
                'descricao': conversao.nome,
                'unidade_origem': conversao.unidade_entrada,
                'unidade_destino': conversao.unidade_saida,
                'fator': float(conversao.fator)
            })
        
        return jsonify(resultado)
    except Exception as e:
        print(f"Erro ao buscar conversões: {str(e)}")
        return jsonify([])

#
# Rotas para Traço de Concreto
#

@usinagem_concreto.route('/tracos')
@login_required
def listar_tracos():
    """Lista todos os traços de concreto cadastrados"""
    tracos = ConcretoTracos.query.order_by(ConcretoTracos.nome).all()
    visualizar_id = request.args.get('visualizar_id')
    
    return render_template('usinagem_concreto/tracos/index.html', 
                          tracos=tracos, 
                          visualizar_id=visualizar_id)

@usinagem_concreto.route('/tracos/novo', methods=['GET', 'POST'])
@login_required
def novo_traco():
    """Cria um novo traço de concreto"""
    materiais = Materiais.query.order_by(Materiais.nome).all()
    conversoes = UnidadesConversao.query.all()
    
    # Verificar se a submissão veio do modal
    via_modal = request.args.get('via_modal') or request.form.get('via_modal')
    
    if request.method == 'POST':
        try:
            print("======== INÍCIO DO PROCESSO DE NOVO TRAÇO ========")
            
            # Obter dados do formulário
            codigo = request.form.get('codigo')
            nome = request.form.get('nome')
            descricao = request.form.get('descricao', '')
            resistencia = request.form.get('resistencia')
            tipo_abatimento = request.form.get('tipo_abatimento')
            valor_abatimento = request.form.get('valor_abatimento')
            relacao_agua_cimento = request.form.get('relacao_agua_cimento')
            status = request.form.get('status', 'Ativo')
            
            print(f"Dados básicos do traço: Código={codigo}, Nome={nome}, Resistência={resistencia}")
            
            # Validar dados
            if not codigo or not nome or not resistencia:
                print("ERRO: Campos obrigatórios não preenchidos")
                flash('Todos os campos obrigatórios devem ser preenchidos', 'danger')
                if via_modal:
                    return redirect(url_for('usinagem_concreto.listar_tracos') + '?erro=campos_obrigatorios')
                return render_template('usinagem_concreto/tracos/novo.html', materiais=materiais, conversoes=conversoes)
            
            # Verificar se já existe traço com o mesmo código
            if ConcretoTracos.query.filter_by(codigo=codigo).first():
                print(f"ERRO: Já existe um traço com o código {codigo}")
                flash('Já existe um traço de concreto com este código', 'danger')
                if via_modal:
                    return redirect(url_for('usinagem_concreto.listar_tracos') + '?erro=codigo_existente')
                return render_template('usinagem_concreto/tracos/novo.html', materiais=materiais, conversoes=conversoes)
            
            # Converter relação água/cimento para decimal
            if relacao_agua_cimento:
                try:
                    relacao_agua_cimento = Decimal(relacao_agua_cimento.replace(',', '.'))
                    print(f"Relação água/cimento convertida: {relacao_agua_cimento}")
                except:
                    print("ERRO: Valor inválido para relação água/cimento")
                    flash('Valor inválido para relação água/cimento', 'danger')
                    if via_modal:
                        return redirect(url_for('usinagem_concreto.listar_tracos') + '?erro=relacao_agua_cimento')
                    return render_template('usinagem_concreto/tracos/novo.html', materiais=materiais, conversoes=conversoes)
            
            # Criar novo traço
            traco = ConcretoTracos(
                codigo=codigo,
                nome=nome,
                descricao=descricao,
                resistencia=resistencia,
                tipo_abatimento=tipo_abatimento,
                valor_abatimento=valor_abatimento,
                relacao_agua_cimento=relacao_agua_cimento,
                status=status
            )
            
            # Obter materiais e quantidades
            material_ids = request.form.getlist('material_ids')
            quantidades = request.form.getlist('quantidades')
            unidade_ids = request.form.getlist('unidade_ids') # <--- MUDANÇA AQUI
            influenciado_umidade = request.form.getlist('influenciado_umidade[]')
            conversao_unidade_ids = request.form.getlist('conversao_unidade_ids')
            
            # Novos campos para o agrupamento de materiais
            material_agrupado_idss = request.form.getlist('material_agrupado_ids')
            material_agrupado_ids = []
            for item in material_agrupado_idss:
                material_agrupado_ids.append(int(item))

            ordem_pesagem = request.form.getlist('ordem_pesagem')
            grupo_ids = request.form.getlist('grupo_id')
            
            print(f"Dados de materiais recebidos:")
            print(f"  - Material IDs: {material_ids}")
            print(f"  - Quantidades: {quantidades}")
            print(f"  - Unidade IDs: {unidade_ids}") # <--- MUDANÇA AQUI (Log)
            print(f"  - Influenciado por umidade: {influenciado_umidade}")
            print(f"  - Conversão unidade IDs: {conversao_unidade_ids}")
            print(f"  - Agrupamento de materiais: {material_agrupado_ids}")
            print(f"  - Ordem de pesagem: {ordem_pesagem}")
            print(f"  - IDs de grupo: {grupo_ids}")
            
            # Verificar se há materiais preenchidos
            if not material_ids or not quantidades:
                print("ERRO: Nenhum material ou quantidade fornecida")
                flash('Adicione pelo menos um material ao traço', 'danger')
                if via_modal:
                    return redirect(url_for('usinagem_concreto.listar_tracos') + '?erro=sem_materiais')
                return render_template('usinagem_concreto/tracos/novo.html', materiais=materiais, conversoes=conversoes)
            
            # Criar dicionário para mapear índices de materiais para seus IDs no banco
            indices_para_ids = {}
            
            # Adicionar materiais ao traço (PRIMEIRA PASSAGEM: Cria todos os itens sem agrupamento)
            for i, material_id in enumerate(material_ids):
                print(f"Processando material {i+1}/{len(material_ids)}: ID={material_id}")
                
                # Ignorar materiais sem ID ou quantidade
                if not material_id or material_id == "" or i >= len(quantidades) or not quantidades[i] or quantidades[i] == "":
                    print(f"  - Material {i+1}: ID ou Quantidade vazios, pulando")
                    continue
                    
                material = Materiais.query.get(material_id)
                if not material:
                    print(f"  - Material {i+1}: Material ID={material_id} não encontrado, pulando")
                    continue
                
                # Converter quantidade
                try:
                    quantidade = Decimal(str(quantidades[i]).replace(',', '.'))
                except Exception as qe:
                    print(f"  - Material {i+1}: Erro ao converter quantidade '{quantidades[i]}': {str(qe)}")
                    flash(f'Quantidade inválida para o material {material.nome}', 'danger')
                    if via_modal:
                        return redirect(url_for('usinagem_concreto.listar_tracos') + '?erro=quantidade_invalida')
                    return render_template('usinagem_concreto/tracos/novo.html', materiais=materiais, conversoes=conversoes)
                
                # Obter unidade_id
                unidade_id = unidade_ids[i] if i < len(unidade_ids) and unidade_ids[i] else None # <--- MUDANÇA AQUI
                if not unidade_id: # Se não veio, tenta pegar do material
                    unidade_obj = Unidade.query.get(material.unidade_id) if material.unidade_id else None
                    if unidade_obj:
                        unidade_id = unidade_obj.id
                    else: # Se nem o material tem, erro
                        raise ValueError(f"Unidade não definida para material {material.nome} e não fornecida no formulário.")
                else:
                     unidade_id = int(unidade_id) # Converte para int se veio do form
                
                # Verificar se é influenciado por umidade (usando o índice 'i' que veio no value do checkbox)
                e_influenciado = str(i) in influenciado_umidade # O value do checkbox é o índice da linha
                print(f"  - Material {i+1} (Índice {i}): Influenciado por umidade={e_influenciado}")

                # Adicionar material ao traço (ainda sem agrupamento)
                try:
                    # Criar o item SEMPRE sem material_agrupado_id e ordem_pesagem aqui
                    item_traco = ItemTracoConcreto(
                        traco=traco, # Associar ao traço já
                        material=material,
                        quantidade=quantidade,
                        unidade_id=unidade_id, # <--- MUDANÇA AQUI
                        influenciado_umidade=e_influenciado,
                        material_agrupado_id=None, # Definido na segunda passagem
                        ordem_pesagem=0,           # Definido na segunda passagem
                        conversao_unidade_id=None  # Definido abaixo se houver
                    )
                    
                    # Adicionar conversão se existir
                    if i < len(conversao_unidade_ids) and conversao_unidade_ids[i]:
                        item_traco.conversao_unidade_id = conversao_unidade_ids[i]
                        print(f"  - Material {i+1}: Conversão de unidade configurada, ID={conversao_unidade_ids[i]}")
                    
                    db.session.add(item_traco)
                    db.session.flush()  # Garantir que o item tenha um ID

                    indices_para_ids[i] = item_traco.id # Mapeia ÍNDICE da linha do form para ID do item no banco
                    print(f"  - Material {i+1} (Índice {i}): Adicionado/Atualizado com sucesso, ID={item_traco.id}")

                except Exception as me:
                    print(f"  - Material {i+1}: Erro ao adicionar material: {str(me)}")
                    flash(f'Erro ao adicionar material {material.nome}: {str(me)}', 'danger')
                    if via_modal:
                        return redirect(url_for('usinagem_concreto.listar_tracos') + '?erro=erro_material')
                    return render_template('usinagem_concreto/tracos/novo.html', materiais=materiais, conversoes=conversoes)
            
            # Processar agrupamentos de materiais (SEGUNDA PASSAGEM: Atualiza itens recém-criados)
            print("\nProcessando agrupamentos de materiais:")
            
            # Identificar todos os grupos e seus materiais (usando grupo_id e índice i)
            grupos = {} # { 'grupo_xyz': [0, 2, 5], 'grupo_abc': [1, 3] }
            for i, grupo_id_form in enumerate(grupo_ids):
                # Só processa se o índice 'i' corresponde a um material válido que foi criado (tem ID)
                if grupo_id_form and i in indices_para_ids:
                    if grupo_id_form not in grupos:
                        grupos[grupo_id_form] = []
                    grupos[grupo_id_form].append(i) # Adiciona o ÍNDICE do item ao grupo
            
            print(f"Grupos identificados (por índice): {grupos}")
            
            # Processar cada grupo
            for grupo_id_form, indices_do_grupo in grupos.items():
                print(f"Processando grupo {grupo_id_form} com índices {indices_do_grupo}")
                
                if len(indices_do_grupo) < 2:
                    print(f"Ignorando grupo {grupo_id_form} com menos de 2 materiais")
                    continue
                
                # Encontrar o índice do pai (aquele cujo material_agrupado_ids[indice] está vazio)
                indice_pai = None
                print(f"Indices do grupo: {indices_do_grupo}")
                print(f"Material_agrupado_ids: {material_agrupado_ids}")
                for idx in indices_do_grupo:
                    # Verifica se o índice existe na lista material_agrupado_ids e se o valor está vazio
                    if idx < len(material_agrupado_ids) and not material_agrupado_ids[idx]:
                        indice_pai = idx
                        break
                
                if indice_pai is None:
                    print(f"ERRO: Não foi possível identificar o material pai no grupo {grupo_id_form} (nenhum item com material_agrupado_ids vazio)")
                    continue # Pula este grupo se não achar o pai
                
                print(f"Material pai identificado no índice {indice_pai}")
                
                # Garantir que o pai tenha um ID real no banco
                if indice_pai not in indices_para_ids:
                    print(f"ERRO Crítico: Material pai (índice {indice_pai}) não possui ID no banco (não foi criado na primeira passagem?)")
                    continue # Pula este grupo
                
                id_pai_real = indices_para_ids[indice_pai]
                print(f"ID real do pai: {id_pai_real}")
                
                # Processar os materiais filhos
                for idx_filho in indices_do_grupo:
                    # Pular o pai
                    if idx_filho == indice_pai:
                        continue
                    
                    # Verificar se este índice filho tem um ID no banco
                    if idx_filho not in indices_para_ids:
                        print(f"ERRO: Material filho (índice {idx_filho}) não possui ID no banco")
                        continue # Pula este filho
                    
                    try:
                        # Obter o item filho do banco usando seu ID real
                        id_filho_real = indices_para_ids[idx_filho]
                        item_filho = ItemTracoConcreto.query.get(id_filho_real)
                        
                        if item_filho is None:
                            print(f"ERRO Crítico: Item filho não encontrado no banco (ID {id_filho_real})")
                            continue # Pula este filho
                        
                        # --- CORREÇÃO APLICADA AQUI ---
                        # Usamos o id_pai_real que já encontramos para este grupo.
                        item_filho.material_agrupado_id = ItemTracoConcreto.query.get(id_pai_real).material_id
                        # --- FIM DA CORREÇÃO ---
                        
                        # Definir a ordem de pesagem vinda do form
                        ordem_do_form = 0
                        if idx_filho < len(ordem_pesagem) and ordem_pesagem[idx_filho]:
                            try:
                                ordem_do_form = int(ordem_pesagem[idx_filho])
                            except ValueError:
                                ordem_do_form = 1 # Default se valor inválido
                        else:
                             ordem_do_form = 1 # Default se não veio ou vazio
                        
                        item_filho.ordem_pesagem = ordem_do_form

                        # Adicionar à sessão para salvar as mudanças no filho
                        db.session.add(item_filho) # Adiciona para garantir que a atualização seja commitada
                        
                        print(f"  - Material Filho (Índice {idx_filho}, ID {id_filho_real}) agrupado com pai ID {id_pai_real}, ordem {item_filho.ordem_pesagem}")
                    except Exception as e:
                        import traceback
                        print(f"Erro ao processar agrupamento para filho (índice {idx_filho}): {e}")
                        traceback.print_exc()
            
            db.session.commit()
            
            print("======== FIM DO PROCESSO DE NOVO TRAÇO ========")
            
            flash('Traço de concreto cadastrado com sucesso!', 'success')
            # Redirecionar para a lista, talvez destacando o novo traço?
            if via_modal:
                return redirect(url_for('usinagem_concreto.listar_tracos', visualizar_id=traco.id))
            return redirect(url_for('usinagem_concreto.listar_tracos'))
            
        except Exception as e:
            db.session.rollback()
            import traceback
            print(f"ERRO GERAL NO CADASTRO DO TRAÇO: {e}")
            traceback.print_exc()
            flash(f'Erro ao cadastrar traço: {str(e)}', 'danger')
            if via_modal:
                 # Tenta retornar para a lista em caso de erro no modal
                 return redirect(url_for('usinagem_concreto.listar_tracos') + '?erro=geral')
            return render_template('usinagem_concreto/tracos/novo.html', materiais=materiais, conversoes=conversoes)
    
    # Se GET, renderizar o template (para o caso de não ser via modal)
    return render_template('usinagem_concreto/tracos/novo.html', materiais=materiais, conversoes=conversoes)

@usinagem_concreto.route('/tracos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_traco(id):
    # Verificar se é uma requisição via modal
    modo = request.args.get('modo', '')
    via_modal = request.form.get('via_modal') == '1'
    
    # Buscar o traço existente
    traco = TracoConcreto.query.get_or_404(id)

    # Buscar todos os materiais disponíveis para dropdowns (caso GET)
    materiais_disponiveis = Material.query.order_by(Material.nome).all()
    # Buscar todas as conversões para dropdowns (caso GET)
    conversoes_disponiveis = ConversaoUnidade.query.order_by(ConversaoUnidade.nome).all()
    
    if request.method == 'POST':
        try:
            print(f"Iniciando edição do traço ID {id}, via_modal={via_modal}")
            print(f"Dados do formulário: {request.form}")
            
            # --- 1. Atualizar dados do Traço ---            
            codigo = request.form.get('codigo')
            nome = request.form.get('nome')
            resistencia = request.form.get('resistencia')
            status = request.form.get('status', 'Ativo')
            descricao = request.form.get('descricao')
            tipo_abatimento = request.form.get('tipo_abatimento')
            valor_abatimento = request.form.get('valor_abatimento')
            relacao_agua_cimento_str = request.form.get('relacao_agua_cimento', '')

            # Validações básicas do traço
            if not nome or not resistencia:
                msg = 'Nome e Resistência do traço são obrigatórios.'
                print(f"Erro de validação: {msg}")
                if via_modal:
                    return jsonify({'success': False, 'message': msg})
                flash(msg, 'danger')
                # Retornar com os dados atuais para o formulário GET
                return render_template('usinagem_concreto/tracos/editar.html', traço=traco, materiais=materiais_disponiveis, conversoes=conversoes_disponiveis)

            traco.codigo = codigo
            traco.nome = nome
            traco.resistencia = resistencia
            traco.status = status
            traco.descricao = descricao
            traco.tipo_abatimento = tipo_abatimento
            traco.valor_abatimento = valor_abatimento
            try:
                traco.relacao_agua_cimento = Decimal(relacao_agua_cimento_str.replace(',', '.')) if relacao_agua_cimento_str else None
            except Exception as e:
                msg = f'Valor inválido para Relação Água/Cimento: {relacao_agua_cimento_str}'
                print(f"Erro de validação: {msg} - {e}")
                if via_modal:
                    return jsonify({'success': False, 'message': msg})
                flash(msg, 'danger')
                return render_template('usinagem_concreto/tracos/editar.html', traço=traco, materiais=materiais_disponiveis, conversoes=conversoes_disponiveis)

            traco.data_atualizacao = datetime.now().astimezone(timezone('America/Sao_Paulo'))
            
            # --- 2. Processar Itens do Traço (Materiais) ---            
            item_ids = request.form.getlist('item_ids')
            material_ids = request.form.getlist('material_ids')
            quantidades_str = request.form.getlist('quantidades')
            unidades = request.form.getlist('unidades')
            conversao_unidade_ids_str = request.form.getlist('conversao_unidade_ids')
            umidade_item_ids = request.form.getlist('umidade_item_ids[]') # Nova lista de IDs marcados
            
            # Dados de agrupamento
            material_agrupado_indices = request.form.getlist('material_agrupado_ids') # Vem o ÍNDICE do pai
            ordem_pesagem_str = request.form.getlist('ordem_pesagem')
            
            print(f"Dados dos itens recebidos:")
            print(f"  - Item IDs: {item_ids}")
            print(f"  - Material IDs: {material_ids}")
            print(f"  - Quantidades: {quantidades_str}")
            print(f"  - Unidades: {unidades}")
            print(f"  - Conversão IDs: {conversao_unidade_ids_str}")
            print(f"  - Umidade Marcada (Item IDs): {umidade_item_ids}")
            print(f"  - Agrupado com (Índice Pai): {material_agrupado_indices}")
            print(f"  - Ordem Pesagem: {ordem_pesagem_str}")

            # Verificar se pelo menos um material válido foi enviado
            if not any(mid for mid in material_ids):
                msg = 'Adicione pelo menos um material ao traço.'
                print(f"Erro de validação: {msg}")
                if via_modal:
                    return jsonify({'success': False, 'message': msg})
                flash(msg, 'danger')
                return render_template('usinagem_concreto/tracos/editar.html', traço=traco, materiais=materiais_disponiveis, conversoes=conversoes_disponiveis)

            # Obter IDs dos itens existentes ANTES de modificar
            itens_existentes = ItemTracoConcreto.query.filter_by(traco_id=traco.id).all()
            mapa_itens_existentes = {item.id: item for item in itens_existentes}
            ids_existentes = set(mapa_itens_existentes.keys())
            print(f"Itens existentes no banco para traço {id}: {ids_existentes}") # Log Adicionado
            ids_processados = set() # IDs que foram atualizados ou criados nesta requisição
            
            # Dicionário para mapear o índice da linha do form para o ID do ItemTracoConcreto (novo ou existente)
            # Necessário para processar o agrupamento depois
            mapa_indice_form_para_item_id = {}

            # --- 3. Primeira Passagem: Atualizar/Criar Itens ---            
            print("\n--- Iniciando Primeira Passagem: Atualizar/Criar Itens ---")
            for i, material_id_str in enumerate(material_ids):
                
                # Ignorar linhas sem material ID ou quantidade
                if not material_id_str or i >= len(quantidades_str) or not quantidades_str[i]:
                    print(f"Linha {i}: Material ID ou Quantidade vazios, pulando.")
                    continue

                # Validar e obter dados da linha
                try:
                    material_id = int(material_id_str)
                    quantidade = Decimal(quantidades_str[i].replace(',', '.'))
                    unidade = unidades[i] if i < len(unidades) and unidades[i] else None
                    conversao_unidade_id = int(conversao_unidade_ids_str[i]) if i < len(conversao_unidade_ids_str) and conversao_unidade_ids_str[i] else None
                    item_id_str = item_ids[i] if i < len(item_ids) else None
                    
                    print(f"Processando linha {i}: item_id='{item_id_str}', material_id={material_id}, qtd={quantidade}, unid={unidade}, conv_id={conversao_unidade_id}")

                    # Buscar material base
                    material = Material.query.get(material_id)
                    if not material:
                        raise ValueError(f"Material com ID {material_id} não encontrado.")
                    if not unidade: # Usar unidade padrão do material se não foi enviada
                            unidade = material.unidade_id

                    # Verificar se é atualização ou criação
                    item_traco = None
                    item_id = None
                    is_update = False # Flag para log
                    if item_id_str:
                        try:
                            item_id = int(item_id_str)
                            print(f"  Linha {i}: Tentando converter item_id_str '{item_id_str}' para int: {item_id}") # Log Adicionado
                            if item_id in mapa_itens_existentes:
                                is_update = True # Marcar que é atualização
                                item_traco = mapa_itens_existentes[item_id]
                                print(f"  -> OK: item_id {item_id} encontrado em mapa_itens_existentes. ATUALIZANDO.") # Log Adicionado
                                ids_processados.add(item_id) # Marcar como visto
                            else:
                                # ID veio mas não existe no banco para este traço? Estranho, tratar como novo.
                                print(f"  -> AVISO: Item ID {item_id} (da linha {i}) NÃO encontrado no mapa de itens existentes {ids_existentes}. Tratando como NOVO.") # Log Adicionado
                                item_id = None # Forçar criação
                        except ValueError:
                            print(f"  -> AVISO: Item ID '{item_id_str}' (da linha {i}) inválido (não é int). Tratando como NOVO.") # Log Adicionado
                            item_id = None # Forçar criação
                    else:
                         print(f"  Linha {i}: item_id_str está vazio. Tratando como NOVO.") # Log Adicionado

                    if item_traco is None: # Criar novo item
                        print(f"  -> Criando novo item para linha {i}") # Log Adicionado
                        item_traco = ItemTracoConcreto(traco_id=traco.id)
                        db.session.add(item_traco)
                        # Precisamos do ID logo, então fazemos flush aqui ou após preencher dados
                        # Vamos preencher primeiro para evitar flush desnecessário se der erro depois
                    
                    # Preencher/Atualizar dados do item
                    item_traco.material_id = material_id
                    item_traco.quantidade = quantidade
                    item_traco.unidade_id = unidade # <--- MUDANÇA AQUI
                    item_traco.conversao_unidade_id = conversao_unidade_id
                    # Resetar agrupamento e ordem, serão definidos na segunda passagem
                    item_traco.material_agrupado_id = None 
                    item_traco.ordem_pesagem = 0 
                    # Definir umidade baseado na lista umidade_item_ids (será feito após ter ID)
                    item_traco.influenciado_umidade = False # Default, ajustado depois
                    
                    # Se for novo (e não atualização), fazer flush para obter ID
                    if not is_update:
                       db.session.flush()
                       item_id = item_traco.id # Pega o ID recém-criado
                       print(f"  -> Novo item criado com ID: {item_id}")
                       ids_processados.add(item_id) # Marcar como visto/processado
                       
                    # Mapear índice do form para o ID real do item (novo ou existente)
                    mapa_indice_form_para_item_id[i] = item_id
                    print(f"  Linha {i}: Mapeado índice do form para Item ID: {item_id}") # Log Adicionado

                except Exception as e:
                    msg = f"Erro ao processar material na linha {i+1}: {e}"
                    print(f"Erro: {msg}")
                    db.session.rollback() # Desfazer qualquer adição parcial
                    if via_modal:
                        return jsonify({'success': False, 'message': msg})
                    flash(msg, 'danger')
                    return render_template('usinagem_concreto/tracos/editar.html', traço=traco, materiais=materiais_disponiveis, conversoes=conversoes_disponiveis)
            
            # --- 4. Segunda Passagem: Definir Umidade ---            
            print("\n--- Iniciando Segunda Passagem: Definir Umidade ---")
            mapa_umidade_item_ids = set(int(uid) for uid in umidade_item_ids if uid.isdigit()) # Converter IDs de umidade para inteiros
            
            # Iterar sobre os itens que acabamos de processar (novos ou atualizados)
            for item_id_processado in ids_processados:
                 item = ItemTracoConcreto.query.get(item_id_processado) # Buscar o item (pode ser novo ou antigo)
                 if item:
                    item.influenciado_umidade = item.id in mapa_umidade_item_ids
                    print(f"Item ID {item.id}: Influenciado Umidade = {item.influenciado_umidade}")

            # --- 5. Terceira Passagem: Processar Agrupamentos ---            
            print("\n--- Iniciando Terceira Passagem: Processar Agrupamentos ---")
            # Precisamos iterar usando os ÍNDICES do form que foram mapeados para IDs reais
            for i, indice_pai_str in enumerate(material_agrupado_indices):
                # Verificar se esta linha do form foi processada e tem um ID de item associado
                if i not in mapa_indice_form_para_item_id:
                    print(f"Linha {i} (Agrupamento): Não corresponde a um item processado, pulando.")
                    continue
                
                id_item_atual = mapa_indice_form_para_item_id[i]
                item_atual = ItemTracoConcreto.query.get(id_item_atual)
                if not item_atual:
                    print(f"ERRO CRÍTICO: Item ID {id_item_atual} (da linha {i}) não encontrado para definir agrupamento.")
                    continue
                
                # Resetar agrupamento e ordem (caso tenha sido definido antes ou venha lixo)
                item_atual.material_agrupado_id = None
                item_atual.ordem_pesagem = 0
                
                # Se indice_pai_str não for vazio, significa que este item é um filho
                if indice_pai_str:
                    try:
                        indice_pai = int(indice_pai_str)
                        # Verificar se o índice do pai também foi processado e mapeado
                        if indice_pai in mapa_indice_form_para_item_id:
                            id_item_pai = mapa_indice_form_para_item_id[indice_pai]
                            
                            # --- CORREÇÃO DO BUG DE AGRUPAMENTO --- 
                            # Devemos armazenar o ID do ItemTracoConcreto pai
                            item_pai_obj = ItemTracoConcreto.query.get(id_item_pai) # Busca o objeto pai
                            if item_pai_obj:
                                item_atual.material_agrupado_id = item_pai_obj.id # CORRIGIDO: Atribui o ID do item pai
                                print(f"  Item ID {item_atual.id} (linha {i}) definido como filho do Item ID {id_item_pai} (linha {indice_pai})")
                            else:
                                print(f"  ERRO CRÍTICO: Item Pai ID {id_item_pai} não encontrado ao definir agrupamento para Item ID {item_atual.id}.")
                                continue # Pula este agrupamento se o pai não foi encontrado
                            # --- FIM DA CORREÇÃO --- 
                            
                            # Definir ordem de pesagem
                            if i < len(ordem_pesagem_str) and ordem_pesagem_str[i]:
                                try:
                                    item_atual.ordem_pesagem = int(ordem_pesagem_str[i])
                                    print(f"    Ordem de pesagem definida para {item_atual.ordem_pesagem}")
                                except ValueError:
                                     print(f"    AVISO: Ordem de pesagem inválida ('{ordem_pesagem_str[i]}') para linha {i}. Usando 0.")
                                     item_atual.ordem_pesagem = 0
                        else:
                            print(f"  AVISO: Índice do pai ({indice_pai}) da linha {i} não corresponde a um item processado. Agrupamento ignorado.")
                    except ValueError:
                         print(f"  AVISO: Índice do pai inválido ('{indice_pai_str}') para linha {i}. Agrupamento ignorado.")
                else:
                    print(f"  Item ID {item_atual.id} (linha {i}) não é filho (material_agrupado_ids vazio).")

            # --- 6. Excluir Itens Órfãos ---            
            print("\n--- Iniciando Quarta Passagem: Excluir Itens Órfãos ---")
            ids_para_excluir = ids_existentes - ids_processados
            if ids_para_excluir:
                print(f"Itens para excluir (existiam antes, não vieram no form): {ids_para_excluir}")
                for item_id_excluir in ids_para_excluir:
                    item_excluir = mapa_itens_existentes[item_id_excluir]
                    print(f"  Excluindo Item ID {item_id_excluir} (Material: {item_excluir.material_id})")
                    # Verificar se este item era pai de alguém que ainda existe
                    # (Embora a lógica anterior deva ter resetado os filhos)
                    filhos_orfos = ItemTracoConcreto.query.filter_by(material_agrupado_id=item_id_excluir).all()
                    for filho in filhos_orfos:
                        print(f"    AVISO: Resetando agrupamento do filho órfão ID {filho.id}")
                        filho.material_agrupado_id = None
                        filho.ordem_pesagem = 0
                        db.session.add(filho)
                    
                    db.session.delete(item_excluir)
            else:
                print("Nenhum item para excluir.")

            # --- 7. Commit e Resposta ---            
            db.session.commit()
            print("Alterações salvas com sucesso.")
            
            if via_modal:
                return jsonify({'success': True, 'message': 'Traço atualizado com sucesso!'})
            
            flash('Traço atualizado com sucesso!', 'success')
            return redirect(url_for('usinagem_concreto.listar_tracos'))
            
        except Exception as e:
            db.session.rollback()
            error_message = f"Erro ao atualizar traço: {e}"
            print(f"ERRO GERAL: {error_message}")
            import traceback
            traceback.print_exc()
            
            if via_modal:
                # Tentar obter uma mensagem mais específica se for erro de conversão
                # (O erro original invalid literal for int() acontece aqui se item_id for vazio e não tratado)
                 if isinstance(e, ValueError) and "invalid literal for int()" in str(e):
                     error_message = "Erro interno ao processar IDs dos itens. Verifique os dados enviados."
                 return jsonify({'success': False, 'message': error_message})
            
            flash(error_message, 'danger')
            # Retornar para o formulário GET em caso de erro não modal
            return render_template('usinagem_concreto/tracos/editar.html', traço=traco, materiais=materiais_disponiveis, conversoes=conversoes_disponiveis)

    # Método GET: Exibir o formulário de edição
    return render_template('usinagem_concreto/tracos/editar.html', 
                           traço=traco, 
                           materiais=materiais_disponiveis, 
                           conversoes=conversoes_disponiveis)

@usinagem_concreto.route('/tracos/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_traco(id):
    """Exclui um traço de concreto"""
    traco = TracoConcreto.query.get_or_404(id)
    
    try:
        # Verificar se há usinagens usando este traço
        if UsinagemConcreto.query.filter_by(traco_id=traco.id).first():
            flash('Não é possível excluir este traço pois há usinagens vinculadas a ele', 'danger')
            return redirect(url_for('usinagem_concreto.listar_tracos'))
        
        traco.delete()
        flash('Traço de concreto excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir traço de concreto: {str(e)}', 'danger')
    
    return redirect(url_for('usinagem_concreto.listar_tracos'))

@usinagem_concreto.route('/tracos/<int:id>/visualizar')
@login_required
def visualizar_traco(id):
    """Visualiza detalhes de um traço de concreto"""
    # Verificar se o traço existe
    traco = TracoConcreto.query.get_or_404(id)
    
    # Redirecionar para a listagem com parâmetro para abrir modal
    return redirect(url_for('usinagem_concreto.listar_tracos', visualizar_id=str(id)))

#
# Rotas para Usinagem de Concreto
#

@usinagem_concreto.route('/usinagens')
@login_required
def listar_usinagens():
    """Lista todas as usinagens de concreto cadastradas com filtros opcionais de data."""
    
    # Obter parâmetros de filtro da URL
    data_inicial_str = request.args.get('data_inicial')
    data_final_str = request.args.get('data_final')
    
    query = UsinagemConcreto.query
    
    data_inicial = None
    data_final = None

    if data_inicial_str:
        try:
            data_inicial = datetime.strptime(data_inicial_str, '%Y-%m-%d')
            # Para o filtro, queremos incluir o dia inteiro, então ajustamos para o início do dia
            query = query.filter(UsinagemConcreto.data_usinagem >= data_inicial)
        except ValueError:
            flash('Formato de Data Inicial inválido. Use AAAA-MM-DD.', 'warning')
            data_inicial = None # Reseta se inválido

    if data_final_str:
        try:
            data_final_dt_obj = datetime.strptime(data_final_str, '%Y-%m-%d')
            # Para o filtro, queremos incluir o dia inteiro, então ajustamos para o final do dia
            # Adicionando 23 horas, 59 minutos, 59 segundos
            data_final_para_query = datetime.combine(data_final_dt_obj.date(), datetime.max.time())
            query = query.filter(UsinagemConcreto.data_usinagem <= data_final_para_query)
            data_final = data_final_dt_obj # Mantemos o objeto data original para repopular o campo
        except ValueError:
            flash('Formato de Data Final inválido. Use AAAA-MM-DD.', 'warning')
            data_final = None # Reseta se inválido

    usinagens = query.order_by(UsinagemConcreto.data_usinagem.desc()).all()
    
    # Preparar dados para JSON (para modais, etc.)
    tracos = TracoConcreto.query.filter_by(status='Ativo').order_by(TracoConcreto.nome).all()
    tracos_data = [{'id': t.id, 'codigo': t.codigo, 'nome': t.nome} for t in tracos]
    
    colaboradores = Colaborador.query.filter_by(status='Ativo').order_by(Colaborador.nome).all()
    colaboradores_data = [{'id': c.id, 'nome': c.nome} for c in colaboradores]
        
    equipamentos = Equipamento.query.filter_by(status='Ativo').order_by(Equipamento.nome).all()
    equipamentos_data = [{'id': e.id, 'nome': e.nome, 'tipo': e.tipo} for e in equipamentos]

    usinagens_data = []
    for usinagem in usinagens:
        idade = (datetime.now() - usinagem.data_usinagem)
        usinagem.idade = idade
        usinagem.idade_hours = idade.total_seconds() / 3600
        usinagem.idade_str = f"{usinagem.idade_hours} horas" if usinagem.idade.days == 0  else f"{usinagem.idade.days} dias"

        usinagem.rompimento = []
        if ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=usinagem.id).count() > 0:   
            for rompimento in ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=usinagem.id).all():
                rompimento.idade = rompimento.data_rompimento - usinagem.data_usinagem
                rompimento.idade_hours = rompimento.idade.total_seconds() / 3600
                rompimento.idade_str = f"{rompimento.idade_hours} horas" if rompimento.idade.days == 0  else f"{rompimento.idade.days} dias"
                usinagem.rompimento.append(rompimento)


        usinagem.rompimento_24h = list(filter(lambda x: x.idade.days <= 3,usinagem.rompimento))
        usinagem.rompimento_28d = list(filter(lambda x: x.idade.days >= 28,usinagem.rompimento))

        if usinagem.status == 'Concluído':
            usinagem.status_badge = 'success'
        elif usinagem.status == 'Em andamento':
            usinagem.status_badge = 'warning'
        else:
            usinagem.status_badge = 'danger'

        usinagens_data.append(usinagem)

    # Passar dados serializados como JSON para o template
    return render_template(
        'usinagem_concreto/usinagens/index.html', 
        now=datetime.now().strftime('%Y-%m-%dT%H:%M'),
        usinagens=usinagens_data, 
        tracos=tracos, 
        colaboradores=colaboradores, 
        equipamentos=equipamentos, 
        tracos_json=Markup(json.dumps(tracos_data)),
        colaboradores_json=Markup(json.dumps(colaboradores_data)),
        equipamentos_json=Markup(json.dumps(equipamentos_data)),
        # Passar as datas do filtro de volta para o template
        filtro_data_inicial=data_inicial_str if data_inicial else '', # Passa a string original se válida
        filtro_data_final=data_final_str if data_final else ''      # Passa a string original se válida
    )
def e_filho(traco_id, material_id):
    """Verifica se um material é filho de um traço"""
    item = ItemTracoConcreto.query.filter_by(traco_id=traco_id, material_id=material_id).first()
    return item is not None

@usinagem_concreto.route('/usinagens/nova', methods=['GET', 'POST'])
@login_required
def nova_usinagem():
    """Nova usinagem de concreto"""
    tracos = TracoConcreto.query.filter_by(status='Ativo').order_by(TracoConcreto.nome).all()
    colaboradores = Colaborador.query.filter_by(status='Ativo').order_by(Colaborador.nome).all()
    equipamentos = Equipamento.query.filter_by(status='Ativo').order_by(Equipamento.nome).all()
    
    if request.method == 'POST':
       
        try:
            # Extrair dados do formulário
            data_usinagem_str = request.form.get('data_usinagem')
            volume_produzido_str = request.form.get('volume_produzido')
            traco_id_str = request.form.get('traco_id')
            responsavel_id_str = request.form.get('responsavel_id')
            umidade_str = request.form.get('umidade', '0')
            status_usinagem = request.form.get('status') # Renomeado para evitar conflito
            fluidez = request.form.get('fluidez') # Novo campo
            nota_id_str = request.form.get('nota_id')
            nbt_str = request.form.get('nbt')
            quantidade_cps_str = request.form.get('quantidade_cps', '0')
            baixar_estoque_automaticamente = request.form.get('baixar_estoque_automaticamente') == 'on' # Captura do checkbox

            # Validar campos obrigatórios
            if not all([data_usinagem_str, volume_produzido_str, traco_id_str, responsavel_id_str, status_usinagem]):
                flash('Todos os campos obrigatórios devem ser preenchidos.', 'error')
                return render_template('usinagem_concreto/usinagens/nova.html',
                                       tracos=tracos,
                                       colaboradores=colaboradores,
                                       equipamentos=equipamentos)

            # Converter e validar dados
            data_usinagem = datetime.fromisoformat(data_usinagem_str)
            volume_produzido = Decimal(volume_produzido_str.replace(',', '.'))
            traco_id = int(traco_id_str)
            responsavel_id = int(responsavel_id_str)
            umidade = Decimal(umidade_str.replace(',', '.'))
            quantidade_cps = int(quantidade_cps_str)

            # Determinar o status inicial da baixa de estoque
            status_baixa_inicial = 'PENDENTE' if baixar_estoque_automaticamente else 'NAO_EXECUTAR'

            # Criar nova usinagem
            usinagem = UsinagemConcreto(
                data_usinagem=data_usinagem,
                volume_produzido=volume_produzido,
                traco_id=traco_id,
                responsavel_id=responsavel_id,
                umidade=umidade,
                status=status_usinagem, # Usando a variável renomeada
                fluidez=fluidez, # Novo campo
                quantidade_cps=quantidade_cps,
                nota=nota_id_str,
                nbt=nbt_str
              #  status_baixa_estoque=status_baixa_inicial # Novo campo
            )
            db.session.add(usinagem) # Adiciona antes para obter o ID se necessário para baixa

            # Adicionar equipamentos
            equipamento_ids = request.form.getlist('equipamento_ids')
            for equipamento_id_str in equipamento_ids:
                if equipamento_id_str:
                    equipamento = Equipamento.query.get(int(equipamento_id_str))
                    if equipamento:
                        usinagem.adicionar_equipamento(equipamento)
            
            # Processar materiais e suas quantidades (conforme lógica anterior)
            itens_do_traco_base = ItemTracoConcreto.query.filter_by(traco_id=traco_id).all()
            mapa_item_traco_por_material_id = {item.material_id: item for item in itens_do_traco_base}
            mapa_item_traco_por_id = {item.id: item for item in itens_do_traco_base}

            quantidades_executadas_do_form = {}
            material_ids_form_str = request.form.getlist('material_ids')
            quantidades_str_form = request.form.getlist('quantidades_executadas')

            for idx, mat_id_str in enumerate(material_ids_form_str):
                if mat_id_str and idx < len(quantidades_str_form) and quantidades_str_form[idx]:
                    try:
                        mat_id_int = int(mat_id_str)
                        qtd_decimal = Decimal(quantidades_str_form[idx].replace(',', '.'))
                        quantidades_executadas_do_form[mat_id_int] = qtd_decimal
                    except ValueError:
                        flash(f"Valor inválido para material ID '{mat_id_str}' ou quantidade '{quantidades_str_form[idx]}'.", 'danger')
                        return render_template('usinagem_concreto/usinagens/nova.html', tracos=tracos, colaboradores=colaboradores, equipamentos=equipamentos)
            
            for material_id_int_atual, qtd_atual_do_form in quantidades_executadas_do_form.items():
                material_obj = Material.query.get(material_id_int_atual)
                if not material_obj:
                    print(f"AVISO: Material com ID {material_id_int_atual} não encontrado no banco. Pulando.")
                    continue

                quantidade_final_a_salvar = qtd_atual_do_form
                item_traco_corrente = mapa_item_traco_por_material_id.get(material_id_int_atual)

                if item_traco_corrente and item_traco_corrente.material_agrupado_id:
                    id_do_item_pai = item_traco_corrente.material_agrupado_id
                    item_traco_pai = mapa_item_traco_por_id.get(id_do_item_pai)

                    if item_traco_pai:
                        material_id_do_pai = item_traco_pai.material_id
                        qtd_pai_do_form = quantidades_executadas_do_form.get(material_id_do_pai)
                        if qtd_pai_do_form is not None:
                            quantidade_final_a_salvar = qtd_atual_do_form - qtd_pai_do_form
                
                try:
                    # Obter o nome da unidade do objeto material para passar explicitamente
                    nome_unidade_material = None
                    if material_obj and material_obj.unidade and hasattr(material_obj.unidade, 'nome'):
                        nome_unidade_material = material_obj.unidade.nome
                    elif material_obj and isinstance(material_obj.unidade, str):
                         nome_unidade_material = material_obj.unidade # Caso raro onde já é string
                    
                    usinagem.adicionar_material(material_obj, quantidade_final_a_salvar, unidade=nome_unidade_material)
                except Exception as e_add:
                    print(f"Erro ao adicionar material {material_obj.nome} (ID: {material_obj.id}) com qtd {quantidade_final_a_salvar} à usinagem: {e_add}")
            
            db.session.commit() # Salva a usinagem e seus materiais/equipamentos
            flash('Usinagem cadastrada com sucesso!', 'success')

            # Baixar estoque automaticamente se o checkbox foi marcado e usinagem status 'Concluído'
            if baixar_estoque_automaticamente and usinagem.status == 'Concluído':
                print(f"Tentando baixar estoque automaticamente para usinagem ID {usinagem.id}")
                from flask_login import current_user
                usuario_id = current_user.id if current_user.is_authenticated else None
                try:
                    resultados_baixa = usinagem.baixar_materiais_estoque(usuario_id=usuario_id)
                    # Verificar se houve erros na baixa
                    erros_na_baixa = [msg for status_op, msg, _ in resultados_baixa if status_op is False]
                    if erros_na_baixa:
                        usinagem.status_baixa_estoque = 'ERRO'
                        for erro_msg in erros_na_baixa:
                            flash(f'Erro na baixa automática de estoque: {erro_msg}', 'warning')
                    elif any(status_op for status_op, _, _ in resultados_baixa): # Se houve pelo menos um sucesso
                        usinagem.status_baixa_estoque = 'REALIZADA'
                        flash('Baixa de estoque automática realizada com sucesso!', 'info')
                    else: # Nenhum sucesso e nenhum erro (ex: nenhum material para baixar)
                        usinagem.status_baixa_estoque = 'NAO_EXECUTAR' # Ou um status tipo 'NADA_A_BAIXAR'
                        flash('Nenhum material aplicável para baixa automática de estoque.', 'info')
                    db.session.commit() # Salva o novo status da baixa
                except Exception as e_baixa:
                    usinagem.status_baixa_estoque = 'ERRO'
                    db.session.commit()
                    print(f"Erro na baixa automática de estoque para usinagem ID {usinagem.id}: {e_baixa}")
                    flash(f'Erro crítico na baixa automática de estoque: {str(e_baixa)}', 'danger')
            elif baixar_estoque_automaticamente and usinagem.status != 'Concluído':
                # Se marcado para baixar, mas usinagem não está 'Concluído', fica 'PENDENTE'
                flash('Baixa de estoque programada, será executada quando a usinagem for marcada como "Concluído" e a baixa manual for acionada ou se a usinagem for editada para "Concluído" com a opção de baixa marcada.', 'info')
                # O status_baixa_estoque já foi setado para PENDENTE no início

            return redirect(url_for('usinagem_concreto.listar_usinagens'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro geral ao cadastrar usinagem: {e}")
            import traceback
            traceback.print_exc()
            flash(f'Erro ao cadastrar usinagem: {str(e)}', 'danger')
            return render_template('usinagem_concreto/usinagens/nova.html', 
                                   tracos=tracos, 
                                   colaboradores=colaboradores, 
                                   equipamentos=equipamentos)
    
    return render_template('usinagem_concreto/usinagens/nova.html', 
                           tracos=tracos, 
                           colaboradores=colaboradores, 
                           equipamentos=equipamentos)

@usinagem_concreto.route('/usinagens/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_usinagem(id):
    """Edita uma usinagem existente"""
    usinagem = UsinagemConcreto.query.get_or_404(id)
    usinagens = UsinagemConcreto.query.order_by(UsinagemConcreto.data_usinagem.desc()).all()
    tracos = TracoConcreto.query.filter_by(status='Ativo').order_by(TracoConcreto.nome).all()
    colaboradores = Colaborador.query.filter_by(status='Ativo').order_by(Colaborador.nome).all()
    equipamentos = Equipamento.query.filter_by(status='Ativo').order_by(Equipamento.nome).all()
    
    if request.method == 'POST':
        try:
            # Extrair dados do formulário
            data_usinagem_str = request.form.get('data_usinagem')
            volume_produzido = request.form.get('volume_produzido').replace(',', '.')
            traco_id = request.form.get('traco_id')
            responsavel_id = request.form.get('responsavel_id')
            umidade = request.form.get('umidade', '0').replace(',', '.')
            status = request.form.get('status')
            observacoes = request.form.get('observacoes')
            quantidade_cps = request.form.get('quantidade_cps', '0')
            
            # Validar campos obrigatórios
            if not data_usinagem_str or not volume_produzido or not traco_id or not responsavel_id or not status:
                flash('Todos os campos obrigatórios devem ser preenchidos.', 'error')
                return redirect(url_for('usinagem_concreto.editar_usinagem', id=id))
            
            # Converter data e hora
            data_usinagem = datetime.fromisoformat(data_usinagem_str)
            
            # Atualizar usinagem
            usinagem.data_usinagem = data_usinagem
            usinagem.volume_produzido = volume_produzido
            usinagem.traco_id = traco_id
            usinagem.responsavel_id = responsavel_id
            usinagem.umidade = umidade
            usinagem.status = status
            usinagem.observacoes = observacoes
            usinagem.quantidade_cps = int(quantidade_cps)
            
            # Remover todos os equipamentos existentes e adicionar o novo
            for equip in usinagem.equipamentos[:]:
                db.session.delete(equip)
            
            # Adicionar equipamento se informado
            equipamento_ids = request.form.getlist('equipamento_ids')
            for equipamento_id in equipamento_ids:
                equipamento = Equipamento.query.get(equipamento_id)
                if equipamento:
                    usinagem.adicionar_equipamento(equipamento)
            
            # Remover todos os materiais existentes e adicionar os novos
            for mat in usinagem.materiais[:]:
                db.session.delete(mat)
            
            # Adicionar materiais executados
            material_ids = request.form.getlist('material_ids')
            quantidades_executadas = request.form.getlist('quantidades_executadas')
            
            for i, material_id in enumerate(material_ids):
                if material_id and i < len(quantidades_executadas) and quantidades_executadas[i]:
                    material = Material.query.get(material_id)
                    if material:
                        try:
                            quantidade = Decimal(quantidades_executadas[i].replace(',', '.'))
                            usinagem.adicionar_material(material, quantidade)
                        except:
                            # Se houver erro na conversão, ignorar este material
                            pass
            
            db.session.commit()
            flash('Usinagem atualizada com sucesso!', 'success')
            return redirect(url_for('usinagem_concreto.visualizar_usinagem', id=usinagem.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar usinagem: {str(e)}', 'danger')
            return render_template('usinagem_concreto/usinagens/editar.html', 
                                  usinagem=usinagem,
                                  tracos=tracos, 
                                  equipamentos=equipamentos)
    else:
        return render_template('usinagem_concreto/usinagens/index.html', 
                           usinagens=usinagens,
                           tracos=tracos,
                           colaboradores=colaboradores,
                           equipamentos=equipamentos)
   

@usinagem_concreto.route('/usinagens/<int:id>/visualizar')
@login_required
def visualizar_usinagem(id):
    """Visualiza detalhes de uma usinagem de concreto"""
    usinagem = UsinagemConcreto.query.get_or_404(id)
    materiais_calculados = usinagem.calcular_materiais()
    
    # Se for uma requisição AJAX, retorna apenas o conteúdo do modal
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':

        idade = (datetime.now() - usinagem.data_usinagem)
        usinagem.idade = idade
        usinagem.idade_hours = idade.total_seconds() / 3600
        usinagem.idade_str = f"{usinagem.idade_hours} horas" if usinagem.idade.days == 0  else f"{usinagem.idade.days} dias"

        usinagem.rompimentos = []
        if ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=usinagem.id).count() > 0:   
            for rompimento in ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=usinagem.id).all():
                rompimento.idade = rompimento.data_rompimento - usinagem.data_usinagem
                rompimento.idade_hours = rompimento.idade.total_seconds() / 3600
                rompimento.idade_str = f"{rompimento.idade_hours} horas" if rompimento.idade.days == 0  else f"{rompimento.idade.days} dias"
                usinagem.rompimentos.append(rompimento)
        return render_template('usinagem_concreto/usinagens/partials/visualizar_usinagem_content.html',
                             usinagem=usinagem,
                             materiais_calculados=materiais_calculados)
    
    # Se não for AJAX, retorna a página completa
    return render_template('usinagem_concreto/usinagens/visualizar.html',
                          usinagem=usinagem,
                          materiais_calculados=materiais_calculados)

@usinagem_concreto.route('/usinagens/<int:id>/baixar-estoque', methods=['POST'])
@login_required
def baixar_estoque_usinagem(id):
    """Baixa os materiais utilizados na usinagem do estoque"""
    # ... (imports de traceback e sys podem ser mantidos ou removidos se não usados aqui diretamente) ...
    
    usinagem = UsinagemConcreto.query.get_or_404(id)
    
    try:
        print(f"\n\n===== INICIANDO BAIXA DE ESTOQUE MANUAL PARA USINAGEM #{id} =====")
        
        if usinagem.status != 'Concluído':
            print(f"Usinagem não concluída - Status: {usinagem.status}")
            flash('Só é possível baixar do estoque usinagens concluídas.', 'warning')
            usinagem.status_baixa_estoque = 'PENDENTE' # Continua pendente
            db.session.commit()
            return redirect(url_for('usinagem_concreto.visualizar_usinagem', id=id))
        
        if not usinagem.materiais or len(usinagem.materiais) == 0:
            print("Sem materiais executados")
            flash('Não há materiais executados registrados nesta usinagem para baixar.', 'warning')
            usinagem.status_baixa_estoque = 'NAO_EXECUTAR' # Ou um status tipo NADA_A_BAIXAR
            db.session.commit()
            return redirect(url_for('usinagem_concreto.visualizar_usinagem', id=id))
        
        from flask_login import current_user
        usuario_id = current_user.id if current_user.is_authenticated else None
        
        try:
            resultados = usinagem.baixar_materiais_estoque(usuario_id=usuario_id)
            print(f"Resultado da baixa manual: {resultados}")

            erros = [msg for status_op, msg, _ in resultados if status_op is False]
            sucessos = [msg for status_op, msg, _ in resultados if status_op is True]
            
            if erros:
                usinagem.status_baixa_estoque = 'ERRO'
                print(f"Erros na baixa de estoque manual: {erros}")
                for erro in erros:
                    flash(erro, 'danger')
            elif sucessos: # Se houve sucessos e nenhum erro grave que impediu tudo
                usinagem.status_baixa_estoque = 'REALIZADA'
                print(f"Sucessos na baixa de estoque manual: {sucessos}")
                for sucesso in sucessos:
                    flash(sucesso, 'success')
                flash('Baixa de materiais (manual) realizada com sucesso!', 'success')
            else: # Nenhum sucesso e nenhum erro (ex: nada a baixar, já baixado)
                # Poderia verificar se já estava REALIZADA antes, para não mudar o status
                if usinagem.status_baixa_estoque != 'REALIZADA':
                    usinagem.status_baixa_estoque = 'NAO_EXECUTAR' # Ou um status específico
                flash('Nenhum material foi baixado do estoque (manual) ou já havia sido baixado.', 'info')
                
            db.session.commit() # Salva o status_baixa_estoque
            
        except Exception as baixa_ex:
            print(f"Exceção capturada ao baixar materiais (manual): {str(baixa_ex)}")
            # import traceback # Descomente se precisar de traceback detalhado aqui
            # traceback.print_exc()
            db.session.rollback() # Rollback em caso de exceção na chamada de baixar_materiais_estoque
            usinagem.status_baixa_estoque = 'ERRO'
            db.session.add(usinagem) # Re-adiciona para salvar o status de ERRO
            db.session.commit()
            flash(f'Erro ao baixar materiais (manual): {str(baixa_ex)}', 'danger')
            
    except Exception as e:
        # Este é um erro mais geral na rota, não diretamente na lógica de baixa.
        # O rollback aqui pode ser desnecessário se o commit principal da baixa já ocorreu ou falhou.
        # db.session.rollback() # Avaliar necessidade
        print(f"Erro não tratado na baixa de estoque (manual): {str(e)}")
        flash(f'Erro crítico ao processar baixa de materiais do estoque (manual): {str(e)}', 'danger')
        # O status da baixa pode não ser atualizado aqui se o erro for antes da lógica principal.
        
    print(f"===== FIM DA BAIXA DE ESTOQUE (MANUAL) PARA USINAGEM #{id} =====\n\n")
    return redirect(url_for('usinagem_concreto.visualizar_usinagem', id=id))

@usinagem_concreto.route('/usinagens/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_usinagem(id):
    """Exclui uma usinagem de concreto"""
    usinagem = UsinagemConcreto.query.get_or_404(id)
    
    try:
        usinagem.delete()
        flash('Usinagem de concreto excluída com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir usinagem de concreto: {str(e)}', 'danger')
    
    return redirect(url_for('usinagem_concreto.listar_usinagens'))

@usinagem_concreto.route('/tracos/<int:id>/materiais', endpoint='get_materiais_traco')
@login_required
def get_materiais_traco(id):
    """Retorna os materiais de um traço de concreto em formato JSON"""
    traco = TracoConcreto.query.get_or_404(id)
    materiais = []
    
    for item in traco.itens:
        materiais.append({
            'id': item.id,
            'material_id': item.material_id,
            'material_nome': item.material.nome,
            'material_codigo': item.material.codigo,
            'quantidade': float(item.quantidade),
            'unidade_id': item.unidade_id, # <--- MUDANÇA AQUI
            'unidade_nome': item.unidade.nome if item.unidade else 'N/A', # <-- MUDANÇA AQUI (Nome da Unidade)
            'influenciado_umidade': item.influenciado_umidade,
            'conversao_unidade_id': item.conversao_unidade_id,
            'material_agrupado_id': item.material_agrupado_id,
            'ordem_pesagem': item.ordem_pesagem
        })
    
    return jsonify(materiais)

@usinagem_concreto.route('/tracos/<int:id>/calcular/<string:volume>', endpoint='calcular_materiais')
@login_required
def calcular_materiais(id, volume):
    """Calcula a quantidade de materiais necessários para o volume de concreto informado"""
    traco = TracoConcreto.query.get_or_404(id)
    umidade = request.args.get('umidade', '0')
    
    try:
        umidade = Decimal(umidade)
    except ValueError:
        umidade = 0
    try:
        volume = Decimal(volume)
    except ValueError:
        volume = 0
        
    # Criar uma usinagem temporária para fazer o cálculo
    usinagem_temp = UsinagemConcreto(
        traco=traco,
        volume_produzido=volume,
        umidade=umidade
    )
    
    # Calcular os materiais necessários
    materiais = usinagem_temp.calcular_materiais()
    
    # Formatar o resultado para retornar como JSON
    resultado = []
    for item in materiais:
        quantidade_formatada = float(item['quantidade'])
        resultado.append({
            'material_id': item['material'].codigo,
            'nome': item['material'].nome,
            'quantidade': quantidade_formatada,
            'unidade_id': item['unidade_id'],
            'unidade_nome': item['unidade'].nome if item['unidade'] else 'N/A',
            'influenciado_umidade': item['influenciado_umidade'],
            'conversao_unidade_id': item['conversao_unidade_id'],
            'material_agrupado_id': item['material_agrupado_id'],
            'ordem_pesagem': item['ordem_pesagem']
        })
    
    return jsonify(resultado)

@usinagem_concreto.route('/tracos/<int:id>/detalhes', methods=['GET'])
@login_required
def detalhes_traco(id):
    """Retorna os detalhes de um traço de concreto em formato JSON"""
    traco = TracoConcreto.query.get_or_404(id)
    
    # Obter materiais do traço
    materiais_traco = ItemTracoConcreto.query.filter_by(traco_id=id).options(
        db.joinedload(ItemTracoConcreto.material), # Carrega o material relacionado
        db.joinedload(ItemTracoConcreto.unidade)   # Carrega a unidade relacionada
    ).all()
    
    # Identificar materiais que são pais (têm materiais agrupados a eles)
    materiais_pais = {}
    for mt in materiais_traco:
        if mt.material_agrupado_id:
            if mt.material_agrupado_id not in materiais_pais:
                materiais_pais[mt.material_agrupado_id] = []
            materiais_pais[mt.material_agrupado_id].append(mt.id)
    
    # Formatar materiais
    materiais_formatados = []
    for mt in materiais_traco:
        material = Material.query.get(mt.material_id)
        if material:
            # Verificar se este material é um pai (tem materiais agrupados a ele)
            eh_material_pai = mt.id in materiais_pais
            
            materiais_formatados.append({
                'id': mt.id,
                'material_id': mt.material_id,
                'material_codigo': material.codigo,
                'material_nome': material.nome,
                'nome': f"{material.codigo} - {material.nome}",
                'quantidade': str(mt.quantidade),
                'unidade_id': mt.unidade_id, # <--- MUDANÇA AQUI
                'unidade_nome': mt.unidade.nome if mt.unidade else 'N/A', # <-- MUDANÇA AQUI (Nome da Unidade)
                'influenciado_umidade': mt.influenciado_umidade,
                'conversao_unidade_id': mt.conversao_unidade_id,
                'material_agrupado_id': mt.material_agrupado_id,
                'ordem_pesagem': mt.ordem_pesagem,
                'eh_material_pai': eh_material_pai,
                'materiais_agrupados': materiais_pais.get(mt.id, [])
            })
    
    # Retornar dados como JSON
    return jsonify({
        'id': traco.id,
        'codigo': traco.codigo,
        'nome': traco.nome,
        'descricao': traco.descricao,
        'resistencia': traco.resistencia,
        'tipo_abatimento': traco.tipo_abatimento,
        'valor_abatimento': traco.valor_abatimento,
        'relacao_agua_cimento': str(traco.relacao_agua_cimento) if traco.relacao_agua_cimento else '',
        'status': traco.status,
        'criado_em': traco.criado_em.strftime('%d/%m/%Y %H:%M') if traco.criado_em else None,
        'atualizado_em': traco.atualizado_em.strftime('%d/%m/%Y %H:%M') if traco.atualizado_em else None,
        'materiais': materiais_formatados,
        'traco': {
            'id': traco.id,
            'codigo': traco.codigo,
            'nome': traco.nome,
            'descricao': traco.descricao,
            'resistencia': traco.resistencia,
            'tipo_abatimento': traco.tipo_abatimento,
            'valor_abatimento': traco.valor_abatimento,
            'relacao_agua_cimento': str(traco.relacao_agua_cimento) if traco.relacao_agua_cimento else '',
            'status': traco.status,
            'criado_em': traco.criado_em.strftime('%d/%m/%Y %H:%M') if traco.criado_em else None,
            'atualizado_em': traco.atualizado_em.strftime('%d/%m/%Y %H:%M') if traco.atualizado_em else None
        }
    })

@usinagem_concreto.route('/usinagens/calcular-materiais', methods=['POST'])
@login_required
def calcular_materiais_usinagem():
    traco_id = request.form.get('traco_id')
    volume_str = request.form.get('volume')
    umidade_str = request.form.get('umidade', '0')
    
    if not traco_id or not volume_str:
        return jsonify({'error': 'ID do traço e volume são obrigatórios'}), 400
    
    try:
        traco_id = int(traco_id)
        volume = Decimal(volume_str.replace(',', '.'))
        umidade = Decimal(umidade_str.replace(',', '.')) if umidade_str else Decimal('0')
        if volume <= 0:
            raise ValueError("Volume deve ser positivo")
    except (ValueError, TypeError):
        return jsonify({'error': 'Valores de ID, volume ou umidade inválidos'}), 400
    
    traco = TracoConcreto.query.get(traco_id)
    if not traco:
        return jsonify({'error': 'Traço não encontrado'}), 404
    
    itens_traco = ItemTracoConcreto.query.filter_by(traco_id=traco_id).join(Material, Material.id == ItemTracoConcreto.material_id).join(Unidade, Unidade.id == ItemTracoConcreto.unidade_id).all()
    print(itens_traco)
    # Dicionário para mapear ID do item para o próprio item (facilita encontrar o pai)
    mapa_itens = {item.id: item for item in itens_traco}
    
    # Dicionário para armazenar quantidades INDIVIDUAIS calculadas
    # Estrutura: { item_id: {'quantidade': Decimal, 'unidade_id': int|None, 'unidade_nome': str|None, 'material': Material} }
    quantidades_calculadas = {}

    print(f"\nCalculando para Traco ID: {traco_id}, Volume: {volume}, Umidade: {umidade}%")

    # Primeira passagem: Calcular e armazenar quantidades individuais para TODOS os itens
    for item in itens_traco:
        if not item.material: # Pular se o material não foi carregado corretamente
            print(f"AVISO: Item ID {item.id} sem material associado.")
            continue

        quantidade_base = item.quantidade * volume
        
        # Aplicar correção de umidade
        if item.influenciado_umidade and umidade > 0:
            fator_correcao = Decimal('1') + (umidade / Decimal('100')) # Ajuste: Usar fator de correção padrão
            quantidade_calculada = quantidade_base * fator_correcao # Ajuste: Aplicar fator
            print(f"  Item ID {item.id} ({item.material.codigo}): Qtd Base={quantidade_base:.2f}, Umidade={umidade}%, Fator={fator_correcao:.4f}, Qtd Corrigida={quantidade_calculada:.2f}")
        else:
            quantidade_calculada = quantidade_base
            print(f"  Item ID {item.id} ({item.material.codigo}): Qtd Base={quantidade_base:.2f}, Sem correção de umidade.")
        
        # Aplicar conversão de unidade, se houver, e determinar unidade final
        unidade_final_obj = item.unidade # Começa com o objeto Unidade original
        unidade_final_nome_str = item.unidade.nome if item.unidade else None # Nome da unidade original
        #if item.conversao_unidade:
        if False:
            try:
                fator_conversao = Decimal(item.conversao_unidade.fator)
                quantidade_calculada *= fator_conversao
                unidade_final_nome_str = item.conversao_unidade.unidade_saida # Pega a string da unidade de saída
                # Tenta encontrar o objeto Unidade correspondente à string de saída
                unidade_final_obj = Unidade.query.filter(Unidade.nome.ilike(unidade_final_nome_str)).first()
                if not unidade_final_obj:
                     print(f"    AVISO: Unidade de saída '{unidade_final_nome_str}' da conversão ID {item.conversao_unidade.id} não encontrada como objeto Unidade no banco.")
                print(f"    Aplicada Conversão ID {item.conversao_unidade.id}: Fator={fator_conversao}, Qtd Final={quantidade_calculada:.2f}, Unidade Saída='{unidade_final_nome_str}'")
            except (ValueError, TypeError, AttributeError) as conv_err:
                 print(f"    ERRO ao aplicar conversão ID {item.conversao_unidade_id} para item ID {item.id}: {conv_err}")
                 # Mantém a unidade original se a conversão falhar
                 unidade_final_obj = item.unidade
                 unidade_final_nome_str = item.unidade.nome if item.unidade else None

        # Determinar ID e Nome final para armazenar
        unidade_id_final = unidade_final_obj.id if unidade_final_obj else None
        unidade_nome_final = unidade_final_nome_str # Usa a string (original ou da conversão)

        # Armazenar resultado individual
        item.material.unidade_id = unidade_id_final
        item.material.unidade_nome = unidade_nome_final
        quantidades_calculadas[item.id] = {
            'quantidade': quantidade_calculada,
            'unidade_id': unidade_id_final,      # Armazena o ID (ou None)
            'unidade_nome': unidade_nome_final,  # Armazena o Nome (string)
            'material': item.material
        }
        print(f"    -> Individual Calculado para Item ID {item.id}: Qtd={quantidade_calculada:.2f}, Unidade ID={unidade_id_final}, Unidade Nome='{unidade_nome_final}'")

    # Montar resultado final: Iterar sobre itens, construir estrutura aninhada,
    # somando quantidade do pai na quantidade do filho.
    resultado_final = []
    
    for item in itens_traco:
        # Processar apenas itens que são pais ou normais (não são filhos de outros)
        if item.material_agrupado_id is None:
            
            # Obter dados individuais calculados para o pai/normal
            dados_pai = quantidades_calculadas.get(item.id)
            if not dados_pai:
                print(f"AVISO: Dados individuais não encontrados para item pai/normal ID {item.id}. Pulando.")
                continue
            
            mat_pai = dados_pai['material']
            qtd_pai_individual = dados_pai['quantidade']
            unidade_id_pai = dados_pai['unidade_id'] # Pega o ID
            unidade_nome_pai = dados_pai['unidade_nome'] # Pega o nome

            entry = {
                'id': mat_pai.id,
                'nome': f"{mat_pai.nome}",
                'quantidade': round(float(qtd_pai_individual), 2), # Quantidade INDIVIDUAL do pai
                'unidade_id': unidade_id_pai, # Usa o ID diretamente
                'unidade_nome': unidade_nome_pai, # Adiciona o nome para referência no JSON
                'eh_agrupamento': False, # Será True se encontrar filhos
                'conversao_unidade_id': item.conversao_unidade_id, # Conversão original do item pai
                'materiais_agrupados': []
            }

            # Encontrar filhos deste pai
            filhos_deste_pai = []
            for filho_item in itens_traco:
                if filho_item.material_agrupado_id == item.id:
                    filhos_deste_pai.append(filho_item)

            if filhos_deste_pai:
                entry['eh_agrupamento'] = True
                # Ordenar filhos por ordem de pesagem
                filhos_deste_pai.sort(key=lambda x: x.ordem_pesagem or 0)

                for filho in filhos_deste_pai:
                    dados_filho = quantidades_calculadas.get(filho.id)
                    if not dados_filho:
                        print(f"AVISO: Dados individuais não encontrados para item filho ID {filho.id}. Pulando filho.")
                        continue # Corrigido: continue em vez de break

                    mat_filho = dados_filho['material']
                    qtd_filho_individual = dados_filho['quantidade']
                    unidade_id_filho = dados_filho['unidade_id']
                    unidade_nome_filho = dados_filho['unidade_nome']

                    # Calcular quantidade somada (Pai + Filho)
                    # Comparar unidades para soma (usar ID se ambos disponíveis, senão usar nome)
                    pode_somar = False
                    if unidade_id_pai is not None and unidade_id_filho is not None:
                        pode_somar = (unidade_id_pai == unidade_id_filho)
                    elif unidade_nome_pai is not None and unidade_nome_filho is not None:
                        # Fallback para comparar nomes (case-insensitive) se IDs não estiverem disponíveis ou divergirem
                        pode_somar = (unidade_nome_pai.lower() == unidade_nome_filho.lower())

                    quantidade_somada = qtd_filho_individual # Começa com a do filho
                    if pode_somar:
                        quantidade_somada += qtd_pai_individual
                        print(f"    -> Somando Pai ({qtd_pai_individual:.2f} {unidade_nome_pai}) ao Filho {filho.id} ({qtd_filho_individual:.2f} {unidade_nome_filho}). Total={quantidade_somada:.2f}")
                    else:
                        print(f"    AVISO: Unidade do Pai ({unidade_nome_pai} ID:{unidade_id_pai}) difere da unidade do Filho ({unidade_nome_filho} ID:{unidade_id_filho}) ID {filho.id}. Usando apenas quantidade do filho.")

                    entry['materiais_agrupados'].append({
                        'id': mat_filho.id,
                        'nome': f"{mat_filho.nome}",
                        'quantidade': round(float(quantidade_somada), 2), # Quantidade SOMADA
                        'unidade_id': unidade_id_filho, # Usa o ID do filho
                        'unidade_nome': unidade_nome_filho, # Adiciona nome do filho
                        'conversao_unidade_id': filho.conversao_unidade_id,
                        'ordem_pesagem': filho.ordem_pesagem or 0
                    })

            resultado_final.append(entry)
            print(f"Resultado Final para Material Pai/Normal ID {item.material_id}: Qtd={entry['quantidade']}, Unidade ID={entry['unidade_id']}, Agrupados={len(entry['materiais_agrupados'])}")

    return jsonify({'materiais': resultado_final})

@usinagem_concreto.route('/rompimentos/api')
@login_required
def listar_rompimentos_api():
    """API para listar rompimentos com filtros"""
    from models.database import db
    
    # Verificar se há filtro para séries sem rompimento de 28 dias
    filtrar_sem_28dias = request.args.get('sem_28dias', 'false') == 'true'
    
    if filtrar_sem_28dias:
        # Buscar todas as séries
        todas_series = db.session.query(ConcretoUsinagensRompimentos.numero_serie).distinct().all()
        series_sem_28dias = []
        
        for serie_tuple in todas_series:
            serie = serie_tuple[0]
            # Buscar todos os rompimentos desta série
            rompimentos_serie = ConcretoUsinagensRompimentos.query.filter_by(numero_serie=serie).all()
            
            # Verificar se tem rompimento de 28 dias
            tem_28dias = False
            for romp in rompimentos_serie:
                if romp.data_moldagem and romp.data_rompimento:
                    diff_days = (romp.data_rompimento - romp.data_moldagem).total_seconds() / 3600 / 24
                    # Considerar 27-29 dias como rompimento de 28 dias (pode cair em domingo e ser 29)
                    if 27 <= diff_days <= 29:
                        tem_28dias = True
                        break
            
            if not tem_28dias:
                series_sem_28dias.append(serie)
        
        # Buscar rompimentos apenas das séries sem 28 dias
        if series_sem_28dias:
            rompimentos = ConcretoUsinagensRompimentos.query.filter(
                ConcretoUsinagensRompimentos.numero_serie.in_(series_sem_28dias)
            ).order_by(ConcretoUsinagensRompimentos.numero_serie.asc()).all()
        else:
            rompimentos = []
    else:
        rompimentos = ConcretoUsinagensRompimentos.query.order_by(ConcretoUsinagensRompimentos.numero_serie.asc()).all()
    
    # Converter para JSON
    rompimentos_data = []
    for rompimento in rompimentos:
        # Calcular idade
        idade_calculada = None
        diff_hours = None
        if rompimento.data_moldagem and rompimento.data_rompimento:
            diff_hours = (rompimento.data_rompimento - rompimento.data_moldagem).total_seconds() / 3600
            if diff_hours < 24:
                idade_calculada = f"{int(diff_hours)}h"
            else:
                idade_calculada = f"{int(diff_hours / 24)}d"
        elif rompimento.usinagem and rompimento.usinagem.data_usinagem and rompimento.data_rompimento:
            diff_hours = (rompimento.data_rompimento - rompimento.usinagem.data_usinagem).total_seconds() / 3600
            if diff_hours < 24:
                idade_calculada = f"{int(diff_hours)}h"
            else:
                idade_calculada = f"{int(diff_hours / 24)}d"
        elif rompimento.idade_cp is not None:
            if rompimento.idade_cp < 24:
                idade_calculada = f"{rompimento.idade_cp}h"
            else:
                idade_calculada = f"{rompimento.idade_cp}d"
        
        rompimentos_data.append({
            'id': rompimento.id,
            'numero_serie': rompimento.numero_serie,
            'usinagem_id': rompimento.usinagem_id,
            'usinagem_traco': rompimento.usinagem.traco.nome if rompimento.usinagem and rompimento.usinagem.traco else None,
            'data_moldagem': rompimento.data_moldagem.strftime('%d/%m/%Y %H:%M') if rompimento.data_moldagem else None,
            'data_rompimento': rompimento.data_rompimento.strftime('%d/%m/%Y %H:%M'),
            'idade': idade_calculada or 'N/A',
            'resultado': float(rompimento.resultado) if rompimento.resultado else None,
            'tipo_rompimento': rompimento.tipo_rompimento,
            'observacoes': rompimento.observacoes,
            'fator_conversao': float(rompimento.fator_conversao) if rompimento.fator_conversao else 1.2
        })
    
    return jsonify({
        'success': True,
        'rompimentos': rompimentos_data
    })

@usinagem_concreto.route('/rompimentos')
@login_required
def listar_rompimentos():
    """Lista todos os rompimentos de corpo de prova cadastrados"""
    usinagens = ConcretoUsinagens.query.order_by(ConcretoUsinagens.data_usinagem.desc()).all()
    
    return render_template('usinagem_concreto/rompimentos/index.html',
                          usinagens=usinagens)

@usinagem_concreto.route('/rompimentos/novo', methods=['POST'])
@login_required
def criar_rompimento():
    try:
        from models.database import db
        
        usinagem_id = request.form.get('usinagem_id')
        numero_serie = request.form.get('numero_serie')
        data_moldagem = request.form.get('data_moldagem')
        data_rompimento = request.form.get('data_rompimento')
        resultados_kg = request.form.getlist('resultados_kg[]')  # Array de resultados em kg
        tipos_rompimento = request.form.getlist('tipos_rompimento[]')  # Array de tipos de rompimento
        fator_conversao = request.form.get('fator_conversao')
        observacoes = request.form.get('observacoes')
        idade_cp = request.form.get('idade_cp')

        # Validações
        if not numero_serie or not data_rompimento:
            flash('Número de série e data de rompimento são obrigatórios.', 'error')
            return redirect(url_for('usinagem_concreto.listar_rompimentos'))
        
        # Validar se há pelo menos um resultado
        resultados_validos = [r for r in resultados_kg if r and r.strip()]
        if not resultados_validos:
            flash('É necessário informar pelo menos um resultado.', 'error')
            return redirect(url_for('usinagem_concreto.listar_rompimentos'))

        # Converter valores
        data_rompimento_dt = datetime.fromisoformat(data_rompimento)
        data_moldagem_dt = None
        if data_moldagem:
            try:
                data_moldagem_dt = datetime.fromisoformat(data_moldagem)
            except ValueError:
                pass
        
        # Processar fator de conversão (padrão: 1.2)
        fator_conversao_float = Decimal('1.2')
        if fator_conversao:
            try:
                fator_conversao_float = Decimal(str(fator_conversao).replace(',', '.'))
            except (ValueError, TypeError):
                pass

        # Processar cálculo de idade
        usinagem_id_int = None
        idade_cp_int = None
        
        # Prioridade: 1) Data de moldagem, 2) Data de usinagem, 3) Idade informada manualmente
        if data_moldagem_dt:
            # Calcular idade baseado na data de moldagem
            diff_hours = (data_rompimento_dt - data_moldagem_dt).total_seconds() / 3600
            idade_cp_int = int(diff_hours / 24) if diff_hours >= 24 else int(diff_hours)
        elif usinagem_id:
            try:
                usinagem_id_int = int(usinagem_id)
                usinagem = ConcretoUsinagens.query.get(usinagem_id_int)
                
                if usinagem:
                    # Calcular idade do CP baseado na data de usinagem
                    diff_hours = (data_rompimento_dt - usinagem.data_usinagem).total_seconds() / 3600
                    idade_cp_int = int(diff_hours / 24) if diff_hours >= 24 else int(diff_hours)
            except (ValueError, AttributeError):
                pass
        
        # Se idade foi informada manualmente e não calculada, usar a informada
        if idade_cp and not idade_cp_int:
            try:
                # Processar idade no formato "12h" ou "5d"
                idade_str = str(idade_cp).strip()
                if idade_str.endswith('h'):
                    # Idade em horas: converter para dias (salvar como horas no campo)
                    idade_cp_int = int(idade_str[:-1])
                elif idade_str.endswith('d'):
                    # Idade em dias: converter para dias
                    idade_cp_int = int(idade_str[:-1]) * 24
                else:
                    # Tentar converter como número inteiro (assumir dias)
                    idade_cp_int = int(idade_str)
            except ValueError:
                pass

        # Criar um rompimento para cada resultado informado
        rompimentos_criados = 0
        for i, resultado_kg in enumerate(resultados_kg):
            if not resultado_kg or not resultado_kg.strip():
                continue  # Pular resultados vazios
            
            # Processar resultado: converter de kg para MPa
            resultado_mpa = None
            try:
                resultado_kg_float = Decimal(str(resultado_kg).replace(',', '.'))
                # Calcular resultado em MPa: kg × fator de conversão
                resultado_mpa = resultado_kg_float * fator_conversao_float
            except (ValueError, TypeError):
                continue  # Pular se não conseguir converter
            
            # Obter tipo de rompimento correspondente (se houver)
            tipo_rompimento = None
            if i < len(tipos_rompimento):
                tipo_rompimento = tipos_rompimento[i].strip() if tipos_rompimento[i] else None

            # Criar novo rompimento
            rompimento = ConcretoUsinagensRompimentos(
                usinagem_id=usinagem_id_int,
                numero_serie=numero_serie,
                data_moldagem=data_moldagem_dt,
                idade_cp=idade_cp_int,
                data_rompimento=data_rompimento_dt,
                resultado=float(resultado_mpa) if resultado_mpa else None,  # Salvar resultado em MPa
                fator_conversao=fator_conversao_float,
                tipo_rompimento=tipo_rompimento,
                observacoes=observacoes if observacoes else None
            )

            db.session.add(rompimento)
            rompimentos_criados += 1

        db.session.commit()

        if rompimentos_criados > 0:
            flash(f'{rompimentos_criados} rompimento(s) registrado(s) com sucesso!', 'success')
        else:
            flash('Nenhum rompimento foi registrado. Verifique os dados informados.', 'warning')
        
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))

    except ValueError as e:
        flash('Erro ao processar os dados. Verifique se os valores estão corretos.', 'error')
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao registrar o rompimento: {str(e)}', 'error')
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))

@usinagem_concreto.route('/rompimentos/<int:id>/editar', methods=['POST'])
@login_required
def editar_rompimento(id):
    try:
        from models.database import db
        
        numero_serie = request.form.get('numero_serie')
        data_moldagem = request.form.get('data_moldagem')
        idade_cp = request.form.get('idade_cp')
        data_rompimento = request.form.get('data_rompimento')
        resultados_kg = request.form.getlist('resultados_kg[]')  # Array de resultados em kg
        tipos_rompimento = request.form.getlist('tipos_rompimento[]')  # Array de tipos de rompimento
        fator_conversao = request.form.get('fator_conversao')
        observacoes = request.form.get('observacoes')
        usinagem_id = request.form.get('usinagem_id')

        rompimento = ConcretoUsinagensRompimentos.query.get_or_404(id)

        # Validações
        if not numero_serie or not data_rompimento:
            flash('Número de série e data de rompimento são obrigatórios.', 'error')
            return redirect(url_for('usinagem_concreto.listar_rompimentos'))
        
        # Validar se há pelo menos um resultado
        resultados_validos = [r for r in resultados_kg if r and r.strip()]
        if not resultados_validos:
            flash('É necessário informar pelo menos um resultado.', 'error')
            return redirect(url_for('usinagem_concreto.listar_rompimentos'))

        # Converter valores
        data_rompimento_dt = datetime.fromisoformat(data_rompimento)
        data_moldagem_dt = None
        if data_moldagem:
            try:
                data_moldagem_dt = datetime.fromisoformat(data_moldagem)
            except ValueError:
                pass
        
        # Processar fator de conversão (padrão: 1.2 ou usar o valor atual se não informado)
        fator_conversao_float = rompimento.fator_conversao if rompimento.fator_conversao else Decimal('1.2')
        if fator_conversao:
            try:
                fator_conversao_float = Decimal(str(fator_conversao).replace(',', '.'))
            except (ValueError, TypeError):
                pass

        # Processar cálculo de idade
        usinagem_id_int = None
        idade_cp_int = None
        
        # Prioridade: 1) Data de moldagem, 2) Data de usinagem, 3) Idade informada manualmente
        if data_moldagem_dt:
            # Calcular idade baseado na data de moldagem
            diff_hours = (data_rompimento_dt - data_moldagem_dt).total_seconds() / 3600
            idade_cp_int = int(diff_hours / 24) if diff_hours >= 24 else int(diff_hours)
        elif usinagem_id:
            try:
                usinagem_id_int = int(usinagem_id)
                usinagem = ConcretoUsinagens.query.get(usinagem_id_int)
                
                if usinagem:
                    # Calcular idade do CP baseado na data de usinagem
                    diff_hours = (data_rompimento_dt - usinagem.data_usinagem).total_seconds() / 3600
                    idade_cp_int = int(diff_hours / 24) if diff_hours >= 24 else int(diff_hours)
            except (ValueError, AttributeError):
                pass
        
        # Se idade foi informada manualmente e não calculada, usar a informada
        if idade_cp and not idade_cp_int:
            try:
                # Processar idade no formato "12h" ou "5d"
                idade_str = str(idade_cp).strip()
                if idade_str.endswith('h'):
                    # Idade em horas: converter para dias (salvar como horas no campo)
                    idade_cp_int = int(idade_str[:-1])
                elif idade_str.endswith('d'):
                    # Idade em dias: converter para dias
                    idade_cp_int = int(idade_str[:-1]) * 24
                else:
                    # Tentar converter como número inteiro (assumir dias)
                    idade_cp_int = int(idade_str)
            except ValueError:
                pass
        
        # Atualizar o rompimento existente com o primeiro resultado
        primeiro_resultado_kg = resultados_kg[0] if resultados_kg else None
        primeiro_tipo_rompimento = tipos_rompimento[0] if tipos_rompimento else None
        
        resultado_mpa = None
        if primeiro_resultado_kg:
            try:
                resultado_kg_float = Decimal(str(primeiro_resultado_kg).replace(',', '.'))
                resultado_mpa = resultado_kg_float * fator_conversao_float
            except (ValueError, TypeError):
                pass

        # Atualizar rompimento existente com o primeiro resultado
        rompimento.numero_serie = numero_serie
        rompimento.usinagem_id = usinagem_id_int
        rompimento.data_moldagem = data_moldagem_dt
        rompimento.idade_cp = idade_cp_int
        rompimento.data_rompimento = data_rompimento_dt
        rompimento.resultado = float(resultado_mpa) if resultado_mpa else None  # Salvar resultado em MPa
        rompimento.fator_conversao = fator_conversao_float
        rompimento.tipo_rompimento = primeiro_tipo_rompimento if primeiro_tipo_rompimento else None
        rompimento.observacoes = observacoes if observacoes else None

        # Criar novos rompimentos para os resultados adicionais (a partir do segundo)
        rompimentos_criados = 0
        for i in range(1, len(resultados_kg)):
            resultado_kg = resultados_kg[i]
            if not resultado_kg or not resultado_kg.strip():
                continue  # Pular resultados vazios
            
            # Processar resultado: converter de kg para MPa
            resultado_mpa_adicional = None
            try:
                resultado_kg_float = Decimal(str(resultado_kg).replace(',', '.'))
                resultado_mpa_adicional = resultado_kg_float * fator_conversao_float
            except (ValueError, TypeError):
                continue  # Pular se não conseguir converter
            
            # Obter tipo de rompimento correspondente (se houver)
            tipo_rompimento_adicional = None
            if i < len(tipos_rompimento):
                tipo_rompimento_adicional = tipos_rompimento[i].strip() if tipos_rompimento[i] else None

            # Criar novo rompimento
            novo_rompimento = ConcretoUsinagensRompimentos(
                usinagem_id=usinagem_id_int,
                numero_serie=numero_serie,
                data_moldagem=data_moldagem_dt,
                idade_cp=idade_cp_int,
                data_rompimento=data_rompimento_dt,
                resultado=float(resultado_mpa_adicional) if resultado_mpa_adicional else None,
                fator_conversao=fator_conversao_float,
                tipo_rompimento=tipo_rompimento_adicional,
                observacoes=observacoes if observacoes else None
            )

            db.session.add(novo_rompimento)
            rompimentos_criados += 1

        db.session.commit()
        
        if rompimentos_criados > 0:
            flash(f'Rompimento atualizado e {rompimentos_criados} novo(s) rompimento(s) criado(s) com sucesso!', 'success')
        else:
            flash('Rompimento atualizado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar rompimento: {str(e)}', 'error')

    return redirect(url_for('usinagem_concreto.listar_rompimentos'))

@usinagem_concreto.route('/rompimentos/series-pendentes-28d')
@login_required
def listar_series_pendentes_28d():
    """Lista séries que completaram 28 dias mas não foram rompidas"""
    try:
        from models.database import db
        from datetime import datetime, timedelta
        
        # Buscar todas as séries com data de moldagem
        todas_series = db.session.query(ConcretoUsinagensRompimentos.numero_serie).filter(
            ConcretoUsinagensRompimentos.data_moldagem.isnot(None)
        ).distinct().all()
        
        series_pendentes = []
        hoje = datetime.now()
        
        for serie_tuple in todas_series:
            serie = serie_tuple[0]
            
            # Buscar o rompimento mais antigo desta série (para pegar a data de moldagem)
            primeiro_rompimento = ConcretoUsinagensRompimentos.query.filter_by(
                numero_serie=serie
            ).filter(
                ConcretoUsinagensRompimentos.data_moldagem.isnot(None)
            ).order_by(ConcretoUsinagensRompimentos.data_moldagem.asc()).first()
            
            if not primeiro_rompimento or not primeiro_rompimento.data_moldagem:
                continue
            
            data_moldagem = primeiro_rompimento.data_moldagem
            
            # Calcular data prevista de rompimento 28 dias
            data_prevista_28d = data_moldagem + timedelta(days=28)
            # Se cair em domingo, adiciona 1 dia
            if data_prevista_28d.weekday() == 6:  # Domingo
                data_prevista_28d += timedelta(days=1)
            
            # Verificar se já passou a data prevista
            if hoje < data_prevista_28d:
                continue  # Ainda não completou 28 dias
            
            # Verificar se já tem rompimento de 28 dias
            tem_rompimento_28d = False
            rompimentos_serie = ConcretoUsinagensRompimentos.query.filter_by(numero_serie=serie).all()
            
            for romp in rompimentos_serie:
                if romp.data_moldagem and romp.data_rompimento:
                    diff_days = (romp.data_rompimento - romp.data_moldagem).total_seconds() / 3600 / 24
                    # Considerar 27-29 dias como rompimento de 28 dias
                    if 27 <= diff_days <= 29:
                        tem_rompimento_28d = True
                        break
            
            # Se não tem rompimento de 28 dias e já passou a data prevista
            if not tem_rompimento_28d:
                dias_atrasados = (hoje - data_prevista_28d).days
                quantidade_rompimentos = len(rompimentos_serie)
                
                series_pendentes.append({
                    'numero_serie': serie,
                    'data_moldagem': data_moldagem.strftime('%d/%m/%Y %H:%M'),
                    'data_prevista_28d': data_prevista_28d.strftime('%d/%m/%Y'),
                    'dias_atrasados': dias_atrasados,
                    'quantidade_rompimentos': quantidade_rompimentos
                })
        
        # Ordenar por dias atrasados (mais atrasadas primeiro)
        series_pendentes.sort(key=lambda x: x['dias_atrasados'], reverse=True)
        
        return jsonify({
            'success': True,
            'series': series_pendentes
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@usinagem_concreto.route('/rompimentos/por-serie/<serie>')
@login_required
def listar_rompimentos_por_serie(serie):
    """Lista todos os rompimentos de uma série específica"""
    try:
        # Ordenar por data de moldagem (descendente), depois por data de rompimento se não tiver data de moldagem
        from sqlalchemy import desc
        rompimentos = ConcretoUsinagensRompimentos.query.filter_by(numero_serie=serie).order_by(
            ConcretoUsinagensRompimentos.data_moldagem.asc(),
            desc(ConcretoUsinagensRompimentos.data_rompimento)
        ).all()
        
        # Reordenar manualmente para colocar NULLs por último
        rompimentos_com_data = [r for r in rompimentos if r.data_moldagem is not None]
        rompimentos_sem_data = [r for r in rompimentos if r.data_moldagem is None]
        rompimentos = rompimentos_com_data + rompimentos_sem_data
        
        rompimentos_data = []
        for rompimento in rompimentos:
            # Calcular idade
            idade_calculada = None
            if rompimento.data_moldagem and rompimento.data_rompimento:
                diff_hours = (rompimento.data_rompimento - rompimento.data_moldagem).total_seconds() / 3600
                if diff_hours < 24:
                    idade_calculada = f"{int(diff_hours)}h"
                else:
                    idade_calculada = f"{int(diff_hours / 24)}d"
            elif rompimento.usinagem and rompimento.usinagem.data_usinagem and rompimento.data_rompimento:
                diff_hours = (rompimento.data_rompimento - rompimento.usinagem.data_usinagem).total_seconds() / 3600
                if diff_hours < 24:
                    idade_calculada = f"{int(diff_hours)}h"
                else:
                    idade_calculada = f"{int(diff_hours / 24)}d"
            elif rompimento.idade_cp is not None:
                if rompimento.idade_cp < 24:
                    idade_calculada = f"{rompimento.idade_cp}h"
                else:
                    idade_calculada = f"{rompimento.idade_cp}d"
            
            # Verificar se é rompimento de 28 dias
            is_28dias = False
            if rompimento.data_moldagem and rompimento.data_rompimento:
                diff_days = (rompimento.data_rompimento - rompimento.data_moldagem).total_seconds() / 3600/24
                # Considerar 27-29 dias como rompimento de 28 dias (pode cair em domingo e ser 29)
                if 27 <= diff_days <= 29:
                    is_28dias = True
            
            rompimentos_data.append({
                'id': rompimento.id,
                'numero_serie': rompimento.numero_serie,
                'usinagem_id': rompimento.usinagem_id,
                'usinagem_traco': rompimento.usinagem.traco.nome if rompimento.usinagem and rompimento.usinagem.traco else None,
                'data_moldagem': rompimento.data_moldagem.strftime('%d/%m/%Y %H:%M') if rompimento.data_moldagem else None,
                'data_rompimento': rompimento.data_rompimento.strftime('%d/%m/%Y %H:%M'),
                'idade': idade_calculada or 'N/A',
                'resultado': float(rompimento.resultado) if rompimento.resultado else None,
                'tipo_rompimento': rompimento.tipo_rompimento,
                'observacoes': rompimento.observacoes,
                'is_28dias': is_28dias
            })
        
        return jsonify({
            'success': True,
            'serie': serie,
            'rompimentos': rompimentos_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@usinagem_concreto.route('/rompimentos/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_rompimento(id):
    try:
        from models.database import db
        
        rompimento = ConcretoUsinagensRompimentos.query.get_or_404(id)
        
        db.session.delete(rompimento)
        db.session.commit()
        
        flash('Rompimento excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir rompimento: {str(e)}', 'error')
        
    return redirect(url_for('usinagem_concreto.listar_rompimentos'))

@usinagem_concreto.route('/usinagens/<int:id>/rompimentos')
@login_required
def listar_rompimentos_usinagem(id):
    """Lista todos os rompimentos de corpo de prova de uma usinagem específica"""
    usinagem = UsinagemConcreto.query.get_or_404(id)

    return render_template('usinagem_concreto/rompimentos/por_usinagem.html',
                          usinagem=usinagem)

@usinagem_concreto.route('/usinagens/<int:id>/data-usinagem')
@login_required
def get_data_usinagem(id):
    """Retorna a data de usinagem de uma usinagem específica"""
    usinagem = UsinagemConcreto.query.get_or_404(id)
    return jsonify({
        'data_usinagem': usinagem.data_usinagem.isoformat()
    }) 
@usinagem_concreto.route('/usinagens/download-modelo-excel', methods=['GET'])
@login_required
def download_excel_modelo_usinagem():
    traco_id_str = request.args.get('traco_id')
    if not traco_id_str:
        flash('ID do Traço é obrigatório para gerar o modelo.', 'danger')
        return redirect(url_for('usinagem_concreto.listar_usinagens'))

    try:
        traco_id = int(traco_id_str)
    except ValueError:
        flash('ID do Traço inválido.', 'danger')
        return redirect(url_for('usinagem_concreto.listar_usinagens'))

    traco = TracoConcreto.query.get_or_404(traco_id)
    
    # Itens do traço (principais e filhos diretos de agrupamentos)
    # Vamos pegar todos os itens e identificar os pais e filhos na lógica
    itens_do_traco = ItemTracoConcreto.query.filter_by(traco_id=traco_id).join(Material).join(Unidade).order_by(ItemTracoConcreto.id).all()

    if not itens_do_traco:
        flash(f'O traço "{traco.nome}" não possui materiais cadastrados. Não é possível gerar o modelo.', 'warning')
        return redirect(url_for('usinagem_concreto.listar_usinagens'))

    output = io.BytesIO()
    # Especificar explicitamente o writer para evitar UserWarning sobre zip64
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        colunas_fixas = [
            'Data Usinagem (AAAA-MM-DD HH:MM)', 
            'Volume Produzido (m³)',
            'Umidade (%)',
            'Nota',
            'Quantidade de CPs'
        ]
        
        colunas_materiais_excel = []
        referencia_materiais_data = []

        # Mapear itens por ID para fácil acesso aos pais
        map_itens_traco = {item.id: item for item in itens_do_traco}

        for item_traco in itens_do_traco:
            # Apenas materiais que são "raízes" (não são filhos de outros no traço)
            # ou materiais que são "pais" de um agrupamento devem gerar colunas diretas.
            # Materiais que SÃO filhos (material_agrupado_id não é None) não geram sua própria coluna principal,
            # eles são considerados parte do material pai.
            
            # A lógica aqui é que o Excel deve refletir o que o usuário precisa preencher.
            # Se um material é sempre parte de um grupo (e sua quantidade é derivada ou somada),
            # ele não deve ter uma coluna separada para "quantidade executada" individualmente,
            # a menos que o agrupamento seja apenas uma forma de visualização e cada parte precise ser informada.
            # Baseado no plano anterior, o usuário informará a Qtd. Executada para *cada* material do traço.

            nome_coluna = f'Qtd. Executada - {item_traco.material.nome} ({item_traco.unidade.nome if item_traco.unidade else "N/A"})'
            
            colunas_materiais_excel.append(nome_coluna)
            referencia_materiais_data.append({
                'Nome Coluna Excel': nome_coluna,
                'ID Material': item_traco.material_id,
                'ID Unidade': item_traco.unidade_id,
                'ID ItemTracoConcreto': item_traco.id # Útil para referenciar o item específico do traço
            })

        df_modelo = pd.DataFrame(columns=colunas_fixas + colunas_materiais_excel)
        df_modelo.to_excel(writer, sheet_name='Modelo_Importacao_Usinagens', index=False)
        
        df_meta = pd.DataFrame(referencia_materiais_data)
        df_meta.to_excel(writer, sheet_name='_Referencia_Materiais', index=False)

    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'modelo_usinagem_traco_{traco.codigo or traco.id}.xlsx'
    )


@usinagem_concreto.route('/usinagens/importar-excel', methods=['POST'])
@login_required
def importar_usinagens_excel():
    if 'arquivo_excel' not in request.files:
        return jsonify({'success': False, 'errors': ['Nenhum arquivo enviado.']}), 400
    
    arquivo = request.files['arquivo_excel']
    traco_id_str = request.form.get('traco_id')
    responsavel_id_str = request.form.get('responsavel_id')

    if not arquivo or arquivo.filename == '':
        return jsonify({'success': False, 'errors': ['Nome de arquivo inválido.']}), 400
    
    if not traco_id_str or not responsavel_id_str:
        return jsonify({'success': False, 'errors': ['Traço e Responsável são obrigatórios.']}), 400

    try:
        traco_id = int(traco_id_str)
        responsavel_id = int(responsavel_id_str)
    except ValueError:
        return jsonify({'success': False, 'errors': ['IDs de Traço ou Responsável inválidos.']}), 400

    traco = TracoConcreto.query.get(traco_id)
    responsavel = Colaborador.query.get(responsavel_id)

    if not traco:
        return jsonify({'success': False, 'errors': [f'Traço com ID {traco_id} não encontrado.']}), 404
    if not responsavel:
        return jsonify({'success': False, 'errors': [f'Responsável com ID {responsavel_id} não encontrado.']}), 404

    map_coluna_material_info = {}
    try:
        # Ler a aba de referência primeiro para saber quais colunas de material esperar
        df_referencia_materiais = pd.read_excel(arquivo, sheet_name='_Referencia_Materiais')
        for _, row_ref in df_referencia_materiais.iterrows():
            map_coluna_material_info[row_ref['Nome Coluna Excel']] = {
                'material_id': row_ref['ID Material'],
                'unidade_id': row_ref['ID Unidade'],
                'item_traco_id': row_ref['ID ItemTracoConcreto']
            }
        
        df = pd.read_excel(arquivo, sheet_name='Modelo_Importacao_Usinagens')

    except Exception as e:
        # Captura erros como aba não encontrada ou problema de parsing geral do Excel
        if '_Referencia_Materiais' not in pd.ExcelFile(arquivo).sheet_names:
             return jsonify({'success': False, 'errors': ['Aba de referência "_Referencia_Materiais" não encontrada no arquivo. Por favor, use o modelo gerado pelo sistema.']}), 400
        if 'Modelo_Importacao_Usinagens' not in pd.ExcelFile(arquivo).sheet_names:
             return jsonify({'success': False, 'errors': ['Aba principal "Modelo_Importacao_Usinagens" não encontrada no arquivo.']}), 400
        return jsonify({'success': False, 'errors': [f'Erro ao ler o arquivo Excel: {str(e)}.']}), 400

    feedback_erros = []
    usinagens_importadas_count = 0
    
    colunas_fixas_rename_map = {
        'Data Usinagem (AAAA-MM-DD HH:MM)': 'data_usinagem_raw',
        'Volume Produzido (m³)': 'volume_produzido_raw',
        'Umidade (%)': 'umidade_raw',
        'Nota': 'nota_raw',
        'Quantidade de CPs': 'quantidade_cps_raw',
        
    }
    # Renomeia apenas as colunas que existem no DF para evitar erros se o usuário remover alguma
    df.rename(columns={k: v for k, v in colunas_fixas_rename_map.items() if k in df.columns}, inplace=True)


    for index, row in df.iterrows():
        linha_excel = index + 2  # Para feedback ao usuário (1-indexed + cabeçalho)
        try:
            data_usinagem_str = row.get('data_usinagem_raw')
            volume_produzido_str = row.get('volume_produzido_raw')
            umidade_str = row.get('umidade_raw')
            quantidade_cps_str = row.get('quantidade_cps_raw')
            nota_str = row.get('nota_raw')

            # Validações
            if pd.isna(data_usinagem_str):
                feedback_erros.append(f"Linha {linha_excel}: Data de Usinagem não informada.")
                continue
            try:
                if isinstance(data_usinagem_str, datetime): # Pandas já converteu
                    data_usinagem = data_usinagem_str
                else: # Tenta converter de string
                    data_usinagem = datetime.strptime(str(data_usinagem_str).split('.')[0].split(' ')[0], '%Y-%m-%d') # Pega só a data
                    # Adicionar hora se vier na string:
                    if ' ' in str(data_usinagem_str):
                        time_part_str = str(data_usinagem_str).split(' ')[1].split('.')[0]
                        time_part = datetime.strptime(time_part_str, '%H:%M:%S' if ':' in time_part_str and time_part_str.count(':') == 2 else '%H:%M').time()
                        data_usinagem = datetime.combine(data_usinagem.date(), time_part)
            except ValueError:
                feedback_erros.append(f"Linha {linha_excel}: Data de Usinagem ('{data_usinagem_str}') em formato inválido. Use AAAA-MM-DD ou AAAA-MM-DD HH:MM.")
                continue
            
            if pd.isna(volume_produzido_str):
                feedback_erros.append(f"Linha {linha_excel}: Volume Produzido não informado.")
                continue
            try:
                volume_produzido = Decimal(str(volume_produzido_str).replace(',', '.'))
                if volume_produzido <= 0: raise ValueError("Volume deve ser positivo")
            except:
                feedback_erros.append(f"Linha {linha_excel}: Volume Produzido ('{volume_produzido_str}') inválido.")
                continue

            umidade = Decimal('0')
            if not pd.isna(umidade_str) and str(umidade_str).strip() != '':
                try: umidade = Decimal(str(umidade_str).replace(',', '.'))
                except: feedback_erros.append(f"Linha {linha_excel}: Umidade ('{umidade_str}') inválida."); continue
            
            quantidade_cps = 0
            if not pd.isna(quantidade_cps_str) and str(quantidade_cps_str).strip() != '':
                try: quantidade_cps = int(float(str(quantidade_cps_str)))
                except: feedback_erros.append(f"Linha {linha_excel}: Quantidade de CPs ('{quantidade_cps_str}') inválida."); continue

            nova_usinagem = UsinagemConcreto(
                data_usinagem=data_usinagem, 
                volume_produzido=volume_produzido, 
                umidade=umidade,
                traco_id=traco_id, 
                responsavel_id=responsavel_id, 
                status="Concluído",
                quantidade_cps=quantidade_cps, 
                criado_em=datetime.utcnow(), 
                atualizado_em=datetime.utcnow(),
                nota=nota_str
            )
            db.session.add(nova_usinagem)
            db.session.flush() 

            materiais_para_salvar = []
            algum_material_informado = False
            for nome_coluna_excel, info_material in map_coluna_material_info.items():
                if nome_coluna_excel in df.columns: # Verifica se a coluna do material existe no arquivo do usuário
                    quantidade_executada_str = row.get(nome_coluna_excel)
                    if not pd.isna(quantidade_executada_str) and str(quantidade_executada_str).strip() != '':
                        algum_material_informado = True
                        try:
                            quantidade_executada = Decimal(str(quantidade_executada_str).replace(',', '.'))
                            if quantidade_executada < 0: raise ValueError("Quantidade não pode ser negativa.")
                        except:
                            feedback_erros.append(f"Linha {linha_excel}, Material '{nome_coluna_excel}': Quantidade ('{quantidade_executada_str}') inválida.")
                            # Decide se quer pular este material ou a linha inteira.
                            # Por enquanto, vamos pular este material específico e continuar com outros.
                            continue 
                        
                        # Garantir que o ItemTracoConcreto existe (deve existir se o modelo foi gerado corretamente)
                        item_traco = ItemTracoConcreto.query.get(info_material['item_traco_id'])
                        if not item_traco:
                             feedback_erros.append(f"Linha {linha_excel}: Material '{nome_coluna_excel}' (ItemTracoID: {info_material['item_traco_id']}) não encontrado no traço. Inconsistência no modelo ou modelo desatualizado.")
                             continue

                        usinagem_material = UsinagemMaterial(
                            usinagem_id=nova_usinagem.id,
                            material_id=info_material['material_id'],
                            quantidade_executada=quantidade_executada,
                            unidade=Unidade.query.filter_by(id=info_material['unidade_id']).first().nome
                        )
                        materiais_para_salvar.append(usinagem_material)
            
            if not algum_material_informado and map_coluna_material_info:
                 # Se o modelo define materiais, mas nenhum foi preenchido
                 feedback_erros.append(f"Linha {linha_excel}: Nenhuma quantidade de material foi informada para esta usinagem, embora o traço selecionado possua materiais.")
                 # Considerar se deve dar rollback na usinagem principal ou permitir usinagem sem materiais.
                 # Por ora, permite, mas avisa.
            
            if materiais_para_salvar:
                db.session.add_all(materiais_para_salvar)
                db.session.flush()
                nova_usinagem.baixar_materiais_estoque(usuario_id=current_user.id)
            
            db.session.commit()
            usinagens_importadas_count += 1

        except Exception as e_row:
            db.session.rollback()
            feedback_erros.append(f"Linha {linha_excel}: Erro inesperado ao processar - {str(e_row)}")
            import traceback
            traceback.print_exc() 

    if usinagens_importadas_count > 0 and not feedback_erros:
        flash(f'{usinagens_importadas_count} usinagem(ns) importada(s) com sucesso!', 'success')
        return jsonify({'success': True, 'message': f'{usinagens_importadas_count} usinagem(ns) importada(s) com sucesso!', 'errors': []})
    elif usinagens_importadas_count > 0 and feedback_erros:
        flash(f'{usinagens_importadas_count} usinagem(ns) importada(s). Alguns erros ocorreram (ver detalhes abaixo).', 'warning')
        return jsonify({'success': True, 'message': f'{usinagens_importadas_count} usinagem(ns) importada(s). Erros em {len(feedback_erros)} linha(s).', 'errors': feedback_erros})
    else:
        flash('Nenhuma usinagem foi importada. Verifique os erros.', 'danger')
        return jsonify({'success': False, 'message': 'Nenhuma usinagem importada.', 'errors': feedback_erros if feedback_erros else ['Nenhuma usinagem válida encontrada no arquivo ou nenhum dado fornecido.']})

@usinagem_concreto.route('/tracos/<int:traco_id>/materiais-para-redozagem')
@login_required
def get_materiais_para_redozagem(traco_id):
    """Retorna os materiais de um traço para o modal de redozagem."""
    traco = TracoConcreto.query.get_or_404(traco_id)
    materiais_formatados = []
    # Considerar apenas itens que não são filhos de outros (material_agrupado_id is None)
    # Pois a redozagem normalmente é feita em "componentes" principais do traço.
    # Se precisar permitir redozagem em sub-componentes, a lógica de busca e exibição no modal precisaria mudar.
    itens_traco = ItemTracoConcreto.query.filter_by(traco_id=traco.id).join(Unidade).join(Material).all()

    for item in itens_traco:
        materiais_formatados.append({
            'material_id': item.material_id,
            'material_nome': item.material.nome,
            'unidade_nome': item.unidade.nome if item.unidade else 'N/A'
        })
    return jsonify(materiais_formatados)

@usinagem_concreto.route('/usinagens/registrar-redozagem', methods=['POST'])
@login_required
def registrar_redozagem():
    """Registra materiais de redozagem para uma usinagem existente."""
    data = request.get_json()
    usinagem_id = data.get('usinagem_id')
    materiais_redozados = data.get('materiais') # Lista de {'material_id': x, 'quantidade': y}

    if not usinagem_id or not materiais_redozados:
        return jsonify({'success': False, 'errors': ['ID da Usinagem e lista de materiais são obrigatórios.']}), 400

    usinagem = UsinagemConcreto.query.join(TracoConcreto).filter(UsinagemConcreto.id == usinagem_id).first()
    if not usinagem:
        return jsonify({'success': False, 'errors': [f'Usinagem com ID {usinagem_id} não encontrada.']}), 404

    try:
        materiais_para_baixa = []
        novos_materiais_usinagem = []

        for mat_data in materiais_redozados:
            material_id = mat_data.get('material_id')
            quantidade_str = mat_data.get('quantidade')

            if not material_id or quantidade_str is None:
                # Pular este material se dados incompletos
                continue 
            
            try:
                quantidade = Decimal(str(quantidade_str))
                if quantidade <= 0:
                    # Pular se quantidade não for positiva
                    continue
            except:
                # Pular se quantidade inválida
                continue

            material_obj = Material.query.get(material_id)

            if not material_obj:
                # Pular se o material base não for encontrado (improvável se veio da lista do traço)
                continue
        

            novo_material_redozagem = UsinagemMaterial(
                usinagem_id=usinagem.id,
                material_id=material_obj.id,
                quantidade_executada=quantidade,
                redozagem=True # Marcar como redozagem
            )
            
            novos_materiais_usinagem.append(novo_material_redozagem)
            

        if not novos_materiais_usinagem:
            return jsonify({'success': False, 'message': 'Nenhum material válido para redozagem foi processado.', 'errors':['Verifique as quantidades.']}), 400

        db.session.add_all(novos_materiais_usinagem)
        db.session.commit()
        usinagem=UsinagemConcreto.query.get(usinagem.id)
        usinagem.baixar_materiais_estoque(usuario_id=current_user.id)

        return jsonify({'success': True, 'message': 'Redozagem registrada com sucesso.'})
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'errors': [f'Erro interno ao registrar redozagem: {str(e)}']}), 500

@usinagem_concreto.route('/usinagens/numeros-betoneira')
@login_required
def get_numeros_betoneira():
    """Retorna todos os números de betoneira únicos já cadastrados"""
    try:
        # Busca todos os números de betoneira únicos, ordenados
        numeros = db.session.query(UsinagemConcreto.nbt).distinct().filter(UsinagemConcreto.nbt.isnot(None)).order_by(UsinagemConcreto.nbt).all()
        
        # Transforma em lista simples
        resultado = [numero[0] for numero in numeros if numero[0]]
        
        return jsonify(resultado)
    except Exception as e:
        print(f"Erro ao buscar números de betoneira: {str(e)}")
        return jsonify([])
@usinagem_concreto.route('/usinagens/ultima-nota')
@login_required
def get_ultima_nota():
    """Retorna a última nota de usinagem"""
    try:
        # Busca a última nota de usinagem
        nota = db.session.query(UsinagemConcreto.nota).order_by(UsinagemConcreto.nota.desc()).first()
        
        # Transforma em lista simples
        resultado = nota[0] if nota else None
        
        return jsonify(resultado)
    except Exception as e:
        print(f"Erro ao buscar última nota: {str(e)}")
        return jsonify(None)

@usinagem_concreto.route('/rompimentos/buscar-por-serie/<numero_serie>')
@login_required
def buscar_rompimento_por_serie(numero_serie):
    """Busca um rompimento pelo número de série e retorna a data de moldagem"""
    try:
        # Tentar converter para inteiro se possível, caso contrário usar como string
        try:
            numero_serie_int = int(numero_serie)
            # Busca o último rompimento com este número de série (mais recente)
            rompimento = ConcretoUsinagensRompimentos.query.filter_by(
                numero_serie=numero_serie_int
            ).order_by(ConcretoUsinagensRompimentos.data_rompimento.desc()).first()
        except ValueError:
            # Se não for número, tentar buscar como string (caso o campo seja alterado para String no futuro)
            # Por enquanto, retornar que não encontrou
            return jsonify({
                'success': True,
                'data_moldagem': None,
                'existe': False
            })
        
        if rompimento and rompimento.data_moldagem:
            # Formatar data para o formato datetime-local (YYYY-MM-DDTHH:mm)
            data_moldagem_formatada = rompimento.data_moldagem.strftime('%Y-%m-%dT%H:%M')
            return jsonify({
                'success': True,
                'data_moldagem': data_moldagem_formatada,
                'existe': True
            })
        else:
            return jsonify({
                'success': True,
                'data_moldagem': None,
                'existe': False
            })
    except Exception as e:
        print(f"Erro ao buscar rompimento por série: {str(e)}")
        return jsonify({
            'success': False,
            'data_moldagem': None,
            'existe': False,
            'error': str(e)
        }), 500

@usinagem_concreto.route('/rompimentos/<int:id>')
@login_required
def get_rompimentos_usinagem(id):
    """Retorna os rompimentos de uma usinagem específica"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
    rompimentos = ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=id).all()
    if not rompimentos:
        return jsonify({
            'success': False,
            'rompimentos': []
        })
    rompimentos_data = []
    for rompimento in rompimentos:
        romp = {}
        if usinagem:
            idade = rompimento.data_rompimento - usinagem.data_usinagem
            romp['idade_hours'] = idade.total_seconds() / 3600
            romp['idade_days'] = idade.days
            romp['idade_str'] = f"{romp['idade_hours']} horas" if idade.days == 0  else f"{idade.days} dias"
        else:
            romp['idade_hours'] = None
            romp['idade_days'] = rompimento.idade_cp if rompimento.idade_cp else None
            romp['idade_str'] = f"{romp['idade_days']} dias" if romp['idade_days'] else 'N/A'
        romp['numero_serie'] = rompimento.numero_serie
        romp['resistencia'] = float(rompimento.resultado) if rompimento.resultado else None
        romp['resistencia_str'] = f"{romp['resistencia']} MPa" if romp['resistencia'] else None
        rompimentos_data.append(romp)
    
    return jsonify({
        'success': True,
        'rompimentos': rompimentos_data
    })
def normalizar_data_str(s):
            """Normaliza string de data removendo espaços extras"""
            # Remover múltiplos espaços e normalizar
            import re
            s = re.sub(r'\s+', ' ', s.strip())
            return s
def get_value_datetime(row, col_index,index):
    """Converte valor do Excel para datetime, preservando horas"""
    if index < 10:
        print(f'col_index: {col_index}')
        print(f'index: {index}')
        print(f'valor: {row.iloc[col_index]}')
    try:
        valor = row.iloc[col_index]
        if pd.isna(valor) or valor == '' or valor is None:
            return None
        
        # Se já for datetime do pandas, converter diretamente (preserva horas)
        if isinstance(valor, pd.Timestamp):
            # Converter preservando horas, minutos e segundos
            # Usar replace para evitar aviso de nanossegundos
            py_dt = valor.to_pydatetime()
            if index < 10:
                print(f'py_dt1: {py_dt}')
            return py_dt
        
        # Se for datetime do Python, retornar como está
        if isinstance(valor, datetime):
            if index < 10:
                print(f'valor: {valor}')
            return valor
        
        # Se for número (serial do Excel), converter usando cálculo manual
        # O Excel armazena datas como números seriais desde 1899-12-30
        # A parte decimal representa as horas (0.5 = meio-dia, 0.25 = 6h, etc)
        if isinstance(valor, (int, float)) and not pd.isna(valor):
            try:
                # Primeiro tentar usar openpyxl que já faz a conversão correta
                try:
                    from openpyxl.utils.datetime import from_excel
                    dt = from_excel(valor)
                    if isinstance(dt, datetime):
                        if index < 10:
                            print(f'dt2: {dt}')
                        return dt
                    elif isinstance(dt, pd.Timestamp):
                        if index < 10:
                            print(f'dt3: {dt.to_pydatetime()}')
                        return dt.to_pydatetime()
                except (ImportError, Exception):
                    pass
                
                # Método alternativo: calcular manualmente a partir do número serial
                # Excel: base é 1899-12-30 (dia 0), então dia 1 = 1899-12-31
                base_date = datetime(1899, 12, 30)
                days = int(valor)
                fraction = valor - days
                
                # Adicionar dias
                dt = base_date + timedelta(days=days)
                
                # Adicionar fração do dia (horas, minutos, segundos)
                if fraction > 0:
                    total_seconds = int(fraction * 86400)  # 86400 segundos em um dia
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    dt = dt.replace(hour=hours, minute=minutes, second=seconds)
                
                if index < 10:
                    print(f'dt4: {dt}')
                return dt
            except Exception as e:
                # Última tentativa: usar pd.to_datetime (pode perder precisão de horas)
                try:
                    dt = pd.to_datetime(valor, unit='d', origin='1899-12-30')
                    if pd.notna(dt):
                        if index < 10:
                            print(f'dt5: {dt.to_pydatetime()}')
                        return dt.to_pydatetime()
                except:
                    pass
        
        # Converter para string para processar
        valor_str = str(valor).strip()
        if not valor_str or valor_str.lower() == 'nan' or valor_str.lower() == 'nat':
            return None
        
        # Função auxiliar para normalizar string de data (remove espaços extras)
        
        
        valor_str = normalizar_data_str(valor_str)
        
        # Tentar diferentes formatos de data/hora, priorizando os que têm hora
        # Incluir formatos com ano de 2 dígitos (formato comum do Excel)
        date_formats = [
            '%d/%m/%y %H:%M',         # 26/6/25 7:50 (formato do Excel mostrado)
            '%d/%m/%y %H:%M:%S',      # 26/6/25 7:50:00
            '%d/%m/%Y %H:%M',         # 26/06/2025 7:50
            '%d/%m/%Y %H:%M:%S',      # 26/06/2025 7:50:00
            '%Y-%m-%d %H:%M:%S',      # 2025-06-26 17:00:00
            '%Y-%m-%d %H:%M',         # 2025-06-26 17:00
            '%Y-%m-%dT%H:%M:%S',      # ISO format com hora
            '%Y-%m-%dT%H:%M',         # ISO format com hora (sem segundos)
            '%d/%m/%y',                # 26/6/25 (apenas data)
            '%Y-%m-%d',                # Apenas data (sem hora)
            '%d/%m/%Y',                # Apenas data (sem hora)
        ]
        
        # Tentar formatos com hora primeiro
        for fmt in date_formats[:8]:  # Primeiros 8 formatos têm hora
            try:
                dt = datetime.strptime(valor_str, fmt)
                if index < 10:
                    print(f'dt6: {dt}')
                return dt
            except ValueError:
                continue
        
        # Se nenhum formato com hora funcionou, tentar formatos sem hora
        for fmt in date_formats[8:]:
            try:
                dt = datetime.strptime(valor_str, fmt)
                if index < 10:
                    print(f'dt7: {dt}')
                # Se não tinha hora, manter como está (meia-noite)
                return dt
            except ValueError:
                continue
        
        # Última tentativa: usar pd.to_datetime com dayfirst=True para datas DD/MM
        # Isso é mais flexível e pode detectar formatos variados
        try:
            dt = pd.to_datetime(valor_str, errors='coerce', dayfirst=True)
            if pd.notna(dt):
                # Converter para datetime do Python, preservando horas e minutos
                py_dt = dt.to_pydatetime()
                if index < 10:
                    print(f'py_dt8: {py_dt}')
                return py_dt
        except:
            pass
        
        return None
    except (IndexError, KeyError, Exception) as e:
        print(f'Erro ao converter datetime col_index {col_index}: {str(e)}, valor: {valor}')
        return None

# Função auxiliar para validar se é uma data (não deve ser usado como numero_serie)
def is_date_string(valor_str):
    """Verifica se a string parece ser uma data"""
    if not valor_str:
        return False
    # Se for Timestamp do pandas, é uma data
    if isinstance(valor_str, pd.Timestamp) or isinstance(valor_str, datetime):
        return True
    # Verificar padrões comuns de data
    date_patterns = ['%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M']
    for pattern in date_patterns:
        try:
            datetime.strptime(str(valor_str), pattern)
            return True
        except:
            continue
def get_value_str(row, col_index):
        """Converte valor do Excel para string, retornando None se for NaN ou vazio"""
        try:
            valor = row.iloc[col_index]
            if pd.isna(valor) or valor == '' or valor is None:
                return None
            return str(valor).strip()
        except (IndexError, KeyError):
            return None
def calcular_data_rompimento_28_dias(data_moldagem_dt):
    """Calcula data de rompimento 28 dias após a moldagem. Se cair em domingo, adiciona 1 dia."""
    data_rompimento = data_moldagem_dt + timedelta(days=28)
    # Verificar se é domingo (weekday() retorna 6 para domingo)
    if data_rompimento.weekday() == 6:  # Domingo
        data_rompimento += timedelta(days=1)  # Adiciona 1 dia (vira segunda-feira)
    return data_rompimento
@usinagem_concreto.route('/rompimentos/importar-excel', methods=['POST'])
@login_required
def importar_rompimentos_excel():
    """
    Importa rompimentos de corpo de prova a partir de um arquivo Excel
    """
    from models.database import db
    
    if 'arquivo_excel' not in request.files:
        flash('Nenhum arquivo enviado.', 'error')
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))
    
    arquivo = request.files['arquivo_excel']
    
    if arquivo.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))
    
    if not arquivo.filename.endswith(('.xlsx', '.xls')):
        flash('Formato de arquivo inválido. Use arquivos Excel (.xlsx ou .xls).', 'error')
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))
    
    nome_planilha = request.form.get('nome_planilha', '').strip()
    primeira_linha_cabecalho = request.form.get('primeira_linha_cabecalho') == 'on'
    
    temp_file = None
    try:
        # Salvar arquivo temporariamente
        filename = secure_filename(arquivo.filename)
        temp_file = os.path.join(tempfile.gettempdir(), f"rompimentos_{filename}")
        arquivo.save(temp_file)
        
        # Ler arquivo Excel sem converter datas automaticamente para preservar horas
        try:
            if nome_planilha:
                df = pd.read_excel(temp_file, sheet_name=nome_planilha, parse_dates=False, header=0 if primeira_linha_cabecalho else None)
            else:
                df = pd.read_excel(temp_file, parse_dates=False, header=0 if primeira_linha_cabecalho else None)
        except Exception as e:
            flash(f'Erro ao ler o arquivo Excel: {str(e)}', 'error')
            return redirect(url_for('usinagem_concreto.listar_rompimentos'))
        
        if df.empty:
            flash('O arquivo Excel está vazio ou não contém dados.', 'error')
            return redirect(url_for('usinagem_concreto.listar_rompimentos'))
        
        # Pular as primeiras 4 linhas (começar a partir da linha 5, índice 4)
        df = df.iloc[4:504].reset_index(drop=True)

        # Função auxiliar para converter valor para datetime preservando horas

        
        for index, row in df.iterrows():
            rompimentos = []
           
            # Função auxiliar para converter valores do Excel para string ou None
           
            # Tentar obter numero_serie - pode estar em diferentes colunas
            numero_serie = None
            # Tentar coluna 0 primeiro (primeira coluna de dados)
            valor_col0 = get_value_str(row, 0)
            if valor_col0 and not is_date_string(valor_col0):
                numero_serie = valor_col0
           
            
            data_moldagem_dt = None
            rompimento5_dt = None
            rompimento8_dt = None
            rompimento9_dt = None
            
            data_moldagem_dt = get_value_datetime(row, 1,index)
            rompimento5_dt = get_value_datetime(row, 4,index)
            rompimento8_dt = get_value_datetime(row, 7,index)
            rompimento9_dt = get_value_datetime(row, 8,index)
            
            resultado10 = get_value_str(row, 9)
            resultado11 = get_value_str(row, 10)
            resultado13 = get_value_str(row, 12)
            resultado17 = get_value_str(row, 16)
            resultado21 = get_value_str(row, 20)
            resultado25 = get_value_str(row, 24)
            tipo15 = get_value_str(row, 14)
            tipo19 = get_value_str(row, 18)
            tipo23 = get_value_str(row, 22)
            tipo27 = get_value_str(row, 26)
            # Validar numero_serie antes de processar - não pode ser uma data
            if not numero_serie:
                print(f'Linha {index+1}: Número de série não encontrado')
                continue
            
            if is_date_string(numero_serie):
                print(f'Linha {index+1}: Número de série inválido (é uma data): {numero_serie}')
                continue
            
            # Limitar tamanho do numero_serie (o modelo pode ter limitação)
            if len(str(numero_serie)) > 50:
                numero_serie = str(numero_serie)[:50]
            #print(f'linha {index+1}: numero_serie: {numero_serie} data_moldagem_str: {row.iloc[1]} data_moldagem_dt: {data_moldagem_dt} ')
            #print(f'resultado13: {resultado13} resultado17: {resultado17} resultado21: {resultado21} resultado25: {resultado25}')
            #print(f'rompimento5_dt: {rompimento5_dt} rompimento8_dt: {rompimento8_dt} rompimento9_dt: {rompimento9_dt}')
            #print(f'tipo15: {tipo15} tipo19: {tipo19} tipo23: {tipo23} tipo27: {tipo27}')
            if numero_serie and data_moldagem_dt:
                if rompimento5_dt:
                    if not rompimento8_dt:
                        try:
                            
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento5_dt,
                                resultado=resultado13,
                                tipo_rompimento=tipo15
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento5_dt,
                                resultado=resultado17,
                                tipo_rompimento=tipo19
                            ))
                        except (ValueError, TypeError) as e:
                            print(f'Erro ao processar linha {index+2}, primeiro caso: {str(e)}')
                            continue
                    elif not rompimento9_dt:
                        try:
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento5_dt,
                                resultado=resultado10,
                                tipo_rompimento=4
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento8_dt,
                                resultado=resultado13,
                                tipo_rompimento=tipo15
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento8_dt,
                                resultado=resultado17,
                                tipo_rompimento=tipo19
                            ))
                        except (ValueError, TypeError) as e:
                            print(f'Erro ao processar linha {index+2}, segundo caso: {str(e)}')
                            continue
                    elif rompimento9_dt:
                        try:                        
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento5_dt,
                                resultado=resultado10,
                                tipo_rompimento=4
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento8_dt,
                                resultado=resultado11,
                                tipo_rompimento=4
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento9_dt,
                                resultado=resultado13,
                                tipo_rompimento=tipo15
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento9_dt,
                                resultado=resultado17,
                                tipo_rompimento=tipo19
                            ))
                        except (ValueError, TypeError) as e:
                            print(f'Erro ao processar linha {index+2}, terceiro caso: {str(e)}')
                            continue
                    
                    if resultado21:
                        try:
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=calcular_data_rompimento_28_dias(data_moldagem_dt),
                                resultado=resultado21,
                                tipo_rompimento=tipo23
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=calcular_data_rompimento_28_dias(data_moldagem_dt),
                                resultado=resultado25,
                                tipo_rompimento=tipo27
                            ))
                        except (ValueError, TypeError) as e:
                            print(f'Erro ao processar linha {index+2}, quarto caso: {str(e)}')
                            continue
            else:
                print(f'Erro ao processar linha {index+6}, dados incompletos: {numero_serie} e {data_moldagem_dt}')

            # Salvar rompimentos no banco de dados
            if rompimentos:
                try:
                    db.session.add_all(rompimentos)
                    db.session.commit()
                    print(f'linha {index+6}: serie {numero_serie} importado(s) com sucesso!')
                    #print(f'linha {index+1}: {len(rompimentos)} rompimento(s) importado(s) com sucesso!')
                except (ValueError, TypeError) as e:
                    print(f'Erro ao processar linha {index+8}, salvar rompimentos: {str(e)}')
                    continue
        
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))
                    
    except Exception as e:
        #flash(f'Erro ao processar o arquivo Excel: {str(e)}', 'error')
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
