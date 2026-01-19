from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_login import login_required, current_user
from models.material import Materiais
from models.unidade import Unidades, UnidadesConversao
from models.colaborador import Colaborador
from models.concreto import ConcretoTracos, ConcretoTracosItens, ConcretoUsinagensMateriais, ConcretoUsinagensRompimentos, ConcretoUsinagens
from models.produto_composto import ProdutoComposto
from models.database import db
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
from sqlalchemy import or_, and_


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



@usinagem_concreto.route('/usinagens')
@login_required
def listar_usinagens():
    """Lista todas as usinagens de concreto cadastradas com filtros opcionais de data."""
    
    # Obter parâmetros de filtro da URL
    data_inicial_str = request.args.get('data_inicial')
    data_final_str = request.args.get('data_final')
    
    query = ConcretoUsinagens.query
    
    data_inicial = None
    data_final = None

    if data_inicial_str:
        try:
            data_inicial = datetime.strptime(data_inicial_str, '%Y-%m-%d')
            query = query.filter(ConcretoUsinagens.data_usinagem >= data_inicial)
        except ValueError:
            flash('Formato de Data Inicial inválido. Use AAAA-MM-DD.', 'warning')
            data_inicial = None

    if data_final_str:
        try:
            data_final_dt_obj = datetime.strptime(data_final_str, '%Y-%m-%d')
            data_final_para_query = datetime.combine(data_final_dt_obj.date(), datetime.max.time())
            query = query.filter(ConcretoUsinagens.data_usinagem <= data_final_para_query)
            data_final = data_final_dt_obj
        except ValueError:
            flash('Formato de Data Final inválido. Use AAAA-MM-DD.', 'warning')
            data_final = None

    usinagens = query.order_by(ConcretoUsinagens.data_usinagem.desc()).all()
    
    # Buscar produtos compostos que são traços (traco=True)
    tracos = ProdutoComposto.query.filter_by(traco=True, status='Ativo').order_by(ProdutoComposto.nome).all()
    tracos_data = [{'id': t.id, 'nome': t.nome} for t in tracos]

    usinagens_data = []
    for usinagem in usinagens:
        idade = (datetime.now() - usinagem.data_usinagem)
        usinagem.idade = idade
        usinagem.idade_hours = idade.total_seconds() / 3600
        usinagem.idade_str = f"{usinagem.idade_hours} horas" if usinagem.idade.days == 0 else f"{usinagem.idade.days} dias"

        usinagem.rompimento = []
        if ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=usinagem.id).count() > 0:   
            for rompimento in ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=usinagem.id).all():
                rompimento.idade = rompimento.data_rompimento - usinagem.data_usinagem
                rompimento.idade_hours = rompimento.idade.total_seconds() / 3600
                rompimento.idade_str = f"{rompimento.idade_hours} horas" if rompimento.idade.days == 0 else f"{rompimento.idade.days} dias"
                usinagem.rompimento.append(rompimento)

        usinagem.rompimento_24h = list(filter(lambda x: x.idade.days <= 3, usinagem.rompimento))
        usinagem.rompimento_28d = list(filter(lambda x: x.idade.days >= 28, usinagem.rompimento))

        usinagens_data.append(usinagem)

    return render_template(
        'usinagem_concreto/usinagens/index.html', 
        now=datetime.now().strftime('%Y-%m-%dT%H:%M'),
        usinagens=usinagens_data, 
        tracos=tracos, 
        tracos_json=Markup(json.dumps(tracos_data)),
        filtro_data_inicial=data_inicial_str if data_inicial else '',
        filtro_data_final=data_final_str if data_final else ''
    )

@usinagem_concreto.route('/usinagens/nova', methods=['GET', 'POST'])
@login_required
def nova_usinagem():
    """Nova usinagem de concreto - suporta AJAX e formulário tradicional"""
    # Buscar produtos compostos que são traços
    tracos = ProdutoComposto.query.filter_by(traco=True, status='Ativo').order_by(ProdutoComposto.nome).all()
    
    if request.method == 'POST':
        try:
            # Verificar se é requisição AJAX
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            
            # Extrair dados do formulário
            serie = request.form.get('serie', '').strip()
            data_usinagem_str = request.form.get('data_usinagem', '').strip()
            produto_composto_id_str = request.form.get('produto_composto_id', '').strip()
            flow = request.form.get('flow', '').strip()
            volume_str = request.form.get('volume', '').strip()
            nf = request.form.get('nf', '').strip()
            dados_adicionais_str = request.form.get('dados_adicionais', '').strip()

            # Validar campos obrigatórios
            campos_faltando = []
            if not serie:
                campos_faltando.append('Série')
            if not data_usinagem_str:
                campos_faltando.append('Data/Hora')
            if not produto_composto_id_str:
                campos_faltando.append('Traço')
            if not volume_str:
                campos_faltando.append('Volume')
            
            if campos_faltando:
                error_msg = f'Campos obrigatórios não preenchidos: {", ".join(campos_faltando)}'
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': error_msg
                    }), 400
                flash(error_msg, 'error')
                return render_template('usinagem_concreto/usinagens/nova.html', 
                                     tracos=tracos,
                                     now=datetime.now().strftime('%Y-%m-%dT%H:%M'))

            # Verificar se série já existe
            if ConcretoUsinagens.query.filter_by(serie=serie).first():
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Já existe uma usinagem com esta série.'
                    }), 400
                flash('Já existe uma usinagem com esta série.', 'error')
                return render_template('usinagem_concreto/usinagens/nova.html', tracos=tracos)

            # Converter e validar dados
            try:
                data_usinagem = datetime.fromisoformat(data_usinagem_str)
            except ValueError:
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Formato de data/hora inválido. Use o formato: AAAA-MM-DDTHH:MM'
                    }), 400
                flash('Formato de data/hora inválido.', 'error')
                return render_template('usinagem_concreto/usinagens/nova.html', 
                                     tracos=tracos,
                                     now=datetime.now().strftime('%Y-%m-%dT%H:%M'))
            
            try:
                volume = Decimal(volume_str.replace(',', '.'))
                if volume <= 0:
                    raise ValueError("Volume deve ser maior que zero")
            except (ValueError, TypeError):
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Volume inválido. Deve ser um número maior que zero.'
                    }), 400
                flash('Volume inválido.', 'error')
                return render_template('usinagem_concreto/usinagens/nova.html', 
                                     tracos=tracos,
                                     now=datetime.now().strftime('%Y-%m-%dT%H:%M'))
            
            try:
                produto_composto_id = int(produto_composto_id_str)
            except (ValueError, TypeError):
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Traço inválido.'
                    }), 400
                flash('Traço inválido.', 'error')
                return render_template('usinagem_concreto/usinagens/nova.html', 
                                     tracos=tracos,
                                     now=datetime.now().strftime('%Y-%m-%dT%H:%M'))
            
            # Validar produto composto
            produto_composto = ProdutoComposto.query.get_or_404(produto_composto_id)
            if not produto_composto or not produto_composto.traco:
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Produto composto selecionado não é um traço válido.'
                    }), 400
                flash('Produto composto selecionado não é um traço válido.', 'error')
                return render_template('usinagem_concreto/usinagens/nova.html', tracos=tracos)

            # Processar dados_adicionais (JSON)
            dados_adicionais = None
            if dados_adicionais_str:
                try:
                    dados_adicionais = json.loads(dados_adicionais_str)
                except json.JSONDecodeError:
                    if is_ajax:
                        return jsonify({
                            'success': False,
                            'error': 'Dados adicionais inválidos (deve ser JSON válido).'
                        }), 400
                    flash('Dados adicionais inválidos (deve ser JSON válido).', 'warning')

            # Criar nova usinagem
            usinagem = ConcretoUsinagens(
                serie=serie,
                data_usinagem=data_usinagem,
                produtoCompostoId=produto_composto_id,
                flow=flow,
                volume=volume,
                nota=nf,
                dados_adicionais=dados_adicionais
            )
            db.session.add(usinagem)
            db.session.commit()
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Usinagem cadastrada com sucesso!',
                    'usinagem_id': usinagem.id
                })
            
            flash('Usinagem cadastrada com sucesso!', 'success')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro geral ao cadastrar usinagem: {e}")
            import traceback
            traceback.print_exc()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': f'Erro ao cadastrar usinagem: {str(e)}'
                }), 500
            
            flash(f'Erro ao cadastrar usinagem: {str(e)}', 'danger')
            return render_template('usinagem_concreto/usinagens/nova.html', 
                                   tracos=tracos, 
                                 now=datetime.now().strftime('%Y-%m-%dT%H:%M'))
    
    return render_template('usinagem_concreto/usinagens/nova.html', 
                           tracos=tracos, 
                         now=datetime.now().strftime('%Y-%m-%dT%H:%M'))

   

@usinagem_concreto.route('/usinagens/<int:id>/visualizar')
@login_required
def visualizar_usinagem(id):
    """Visualiza detalhes de uma usinagem de concreto"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
    materiais_calculados = usinagem.calcular_materiais()
    
    # Se for uma requisição AJAX, retorna apenas o conteúdo do modal
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        idade = (datetime.now() - usinagem.data_usinagem)
        usinagem.idade = idade
        usinagem.idade_hours = idade.total_seconds() / 3600
        usinagem.idade_str = f"{usinagem.idade_hours} horas" if usinagem.idade.days == 0 else f"{usinagem.idade.days} dias"

        usinagem.rompimentos = []
        if ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=usinagem.id).count() > 0:   
            for rompimento in ConcretoUsinagensRompimentos.query.filter_by(usinagem_id=usinagem.id).all():
                rompimento.idade = rompimento.data_rompimento - usinagem.data_usinagem
                rompimento.idade_hours = rompimento.idade.total_seconds() / 3600
                rompimento.idade_str = f"{rompimento.idade_hours} horas" if rompimento.idade.days == 0 else f"{rompimento.idade.days} dias"
                usinagem.rompimentos.append(rompimento)
        return render_template('usinagem_concreto/usinagens/partials/visualizar_usinagem_content.html',
                             usinagem=usinagem,
                             materiais_calculados=materiais_calculados)
    
    # Se não for AJAX, retorna a página completa
    return render_template('usinagem_concreto/usinagens/visualizar.html',
                          usinagem=usinagem,
                          materiais_calculados=materiais_calculados)


@usinagem_concreto.route('/usinagens/<int:id>/editar', methods=['POST'])
@login_required
def editar_usinagem(id):
    """Edita uma usinagem de concreto - suporta AJAX e formulário tradicional"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
    
    try:
        # Verificar se é requisição AJAX
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Extrair dados do formulário
        serie = request.form.get('serie', '').strip()
        data_usinagem_str = request.form.get('data_usinagem', '').strip()
        produto_composto_id_str = request.form.get('produto_composto_id', '').strip()
        flow = request.form.get('flow', '').strip()
        volume_str = request.form.get('volume', '').strip()
        nf = request.form.get('nf', '').strip()
        dados_adicionais_str = request.form.get('dados_adicionais', '').strip()

        # Validar campos obrigatórios
        campos_faltando = []
        if not serie:
            campos_faltando.append('Série')
        if not data_usinagem_str:
            campos_faltando.append('Data/Hora')
        if not produto_composto_id_str:
            campos_faltando.append('Traço')
        if not volume_str:
            campos_faltando.append('Volume')
        
        if campos_faltando:
            error_msg = f'Campos obrigatórios não preenchidos: {", ".join(campos_faltando)}'
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
            flash(error_msg, 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))

        # Verificar se série já existe (exceto para a própria usinagem)
        if serie != usinagem.serie:
            if ConcretoUsinagens.query.filter_by(serie=serie).first():
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Já existe uma usinagem com esta série.'
                    }), 400
                flash('Já existe uma usinagem com esta série.', 'error')
                return redirect(url_for('usinagem_concreto.listar_usinagens'))

        # Converter e validar dados
        try:
            data_usinagem = datetime.fromisoformat(data_usinagem_str)
        except ValueError:
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': 'Formato de data/hora inválido. Use o formato: AAAA-MM-DDTHH:MM'
                }), 400
            flash('Formato de data/hora inválido.', 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))
        
        try:
            volume = Decimal(volume_str.replace(',', '.'))
            if volume <= 0:
                raise ValueError("Volume deve ser maior que zero")
        except (ValueError, TypeError):
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': 'Volume inválido. Deve ser um número maior que zero.'
                }), 400
            flash('Volume inválido.', 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))
        
        try:
            produto_composto_id = int(produto_composto_id_str)
        except (ValueError, TypeError):
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': 'Traço inválido.'
                }), 400
            flash('Traço inválido.', 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))
        
        # Validar produto composto
        produto_composto = ProdutoComposto.query.get_or_404(produto_composto_id)
        if not produto_composto or not produto_composto.traco:
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': 'Produto composto selecionado não é um traço válido.'
                }), 400
            flash('Produto composto selecionado não é um traço válido.', 'error')
            return redirect(url_for('usinagem_concreto.listar_usinagens'))

        # Processar dados_adicionais (JSON)
        dados_adicionais = None
        if dados_adicionais_str:
            try:
                dados_adicionais = json.loads(dados_adicionais_str)
            except json.JSONDecodeError:
                if is_ajax:
                    return jsonify({
                        'success': False,
                        'error': 'Dados adicionais inválidos (deve ser JSON válido).'
                    }), 400
                flash('Dados adicionais inválidos (deve ser JSON válido).', 'warning')

        # Atualizar usinagem
        usinagem.serie = serie
        usinagem.data_usinagem = data_usinagem
        usinagem.produtoCompostoId = produto_composto_id
        usinagem.flow = flow if flow else None
        usinagem.volume = volume
        usinagem.nota = nf if nf else None
        usinagem.dados_adicionais = dados_adicionais
        
        db.session.commit()
        
        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Usinagem atualizada com sucesso!',
                'usinagem_id': usinagem.id
            })
        
        flash('Usinagem atualizada com sucesso!', 'success')
        return redirect(url_for('usinagem_concreto.listar_usinagens'))
        
    except Exception as e:
        db.session.rollback()
        print(f"Erro geral ao atualizar usinagem: {e}")
        import traceback
        traceback.print_exc()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': f'Erro ao atualizar usinagem: {str(e)}'
            }), 500
        
        flash(f'Erro ao atualizar usinagem: {str(e)}', 'danger')
        return redirect(url_for('usinagem_concreto.listar_usinagens'))


@usinagem_concreto.route('/usinagens/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_usinagem(id):
    """Exclui uma usinagem de concreto"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
    
    try:
        usinagem.delete()
        flash('Usinagem de concreto excluída com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir usinagem de concreto: {str(e)}', 'danger')
    
    return redirect(url_for('usinagem_concreto.listar_usinagens'))



@usinagem_concreto.route('/rompimentos/api')
@login_required
def listar_rompimentos_api():
    """API para listar rompimentos com filtros e agrupamento"""
    from models.database import db
    from collections import defaultdict
    
    # Verificar parâmetros
    filtrar_sem_28dias = request.args.get('sem_28dias', 'false') == 'true'
    agrupar = request.args.get('agrupar', 'false') == 'true'
    
    # Buscar rompimentos baseado nos filtros (sem ordenação/paginação - será feito no frontend)
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
            query = ConcretoUsinagensRompimentos.query.filter(
                ConcretoUsinagensRompimentos.numero_serie.in_(series_sem_28dias)
            )
        else:
            query = ConcretoUsinagensRompimentos.query.filter(False)  # Query vazia
    else:
        query = ConcretoUsinagensRompimentos.query
    
    # Buscar todos os rompimentos (sem ordenação/paginação - será feito no frontend)
    rompimentos = query.all()
    
    # Função auxiliar para calcular idade
    def calcular_idade(rompimento):
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
        return idade_calculada or 'N/A'
    
    # Função auxiliar para converter rompimento para dict
    def rompimento_to_dict(rompimento):
        return {
            'id': rompimento.id,
            'numero_serie': rompimento.numero_serie,
            'usinagem_id': rompimento.usinagem_id,
            'usinagem_traco': rompimento.usinagem.traco.nome if rompimento.usinagem and rompimento.usinagem.traco else None,
            'data_moldagem': rompimento.data_moldagem.strftime('%d/%m/%Y %H:%M') if rompimento.data_moldagem else None,
            'data_rompimento': rompimento.data_rompimento.strftime('%d/%m/%Y %H:%M'),
            'idade': calcular_idade(rompimento),
            'resultado': float(rompimento.resultado) if rompimento.resultado else None,
            'tipo_rompimento': rompimento.tipo_rompimento,
            'observacoes': rompimento.observacoes,
            'fator_conversao': float(rompimento.fator_conversao) if rompimento.fator_conversao else 1.2
        }
    
    if agrupar:
        # Agrupar por série
        grupos_dict = defaultdict(list)
        for rompimento in rompimentos:
            grupos_dict[rompimento.numero_serie].append(rompimento)
        
        # Criar lista de grupos (sem ordenação - será feito no frontend)
        grupos_data = []
        for serie, rompimentos_serie in grupos_dict.items():
            # Buscar primeira data de moldagem
            primeira_data_moldagem = None
            for romp in rompimentos_serie:
                if romp.data_moldagem:
                    primeira_data_moldagem = romp.data_moldagem.strftime('%d/%m/%Y %H:%M')
                    break
            
            grupos_data.append({
                'numero_serie': serie,
                'quantidade': len(rompimentos_serie),
                'data_moldagem': primeira_data_moldagem or 'N/A',
                'rompimentos': [rompimento_to_dict(r) for r in rompimentos_serie]
            })
        
        # Retornar todos os grupos (sem paginação - será feito no frontend)
        return jsonify({
            'success': True,
            'agrupado': True,
            'grupos': grupos_data
        })
    else:
        # Retornar todos os rompimentos individuais (sem paginação - será feito no frontend)
        rompimentos_data = [rompimento_to_dict(r) for r in rompimentos]
        
        return jsonify({
            'success': True,
            'agrupado': False,
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
        from sqlalchemy import func, case, and_, exists, select, text
        
        hoje = datetime.now()
        
        # Subquery para pegar a primeira data de moldagem por série
        primeira_moldagem_subq = db.session.query(
            ConcretoUsinagensRompimentos.numero_serie,
            func.min(ConcretoUsinagensRompimentos.data_moldagem).label('primeira_data_moldagem')
            ).filter(
                ConcretoUsinagensRompimentos.data_moldagem.isnot(None)
        ).group_by(
            ConcretoUsinagensRompimentos.numero_serie
        ).subquery()
        
        # Subquery para contar quantidade de rompimentos por série
        quantidade_subq = db.session.query(
            ConcretoUsinagensRompimentos.numero_serie,
            func.count(ConcretoUsinagensRompimentos.id).label('quantidade')
        ).group_by(
            ConcretoUsinagensRompimentos.numero_serie
        ).subquery()
        
        # Calcular data prevista de 28 dias (ajustando domingo)
        # Se WEEKDAY(data_moldagem + 28 dias) = 6 (domingo), adiciona 1 dia
        # Usando text() para SQL puro quando necessário
        data_prevista_28d_base = func.date_add(
            primeira_moldagem_subq.c.primeira_data_moldagem,
            text('INTERVAL 28 DAY')
        )
        data_prevista_28d = case(
            (func.weekday(data_prevista_28d_base) == 6,
             func.date_add(
                 primeira_moldagem_subq.c.primeira_data_moldagem,
                 text('INTERVAL 29 DAY')
             )),
            else_=data_prevista_28d_base
        )
        
        # Subquery correlacionada para verificar se existe rompimento de 28 dias (27-29 dias)
        # Esta será usada com EXISTS na query principal
        rompimento_28d_exists = exists(
            select(1).where(
                and_(
                    ConcretoUsinagensRompimentos.numero_serie == primeira_moldagem_subq.c.numero_serie,
                    ConcretoUsinagensRompimentos.data_moldagem.isnot(None),
                    ConcretoUsinagensRompimentos.data_rompimento.isnot(None),
                    func.datediff(
                        ConcretoUsinagensRompimentos.data_rompimento,
                        ConcretoUsinagensRompimentos.data_moldagem
                    ) >= 27
                )
            )
        )
        
        # Query principal: buscar séries pendentes
        query = db.session.query(
            primeira_moldagem_subq.c.numero_serie,
            primeira_moldagem_subq.c.primeira_data_moldagem,
            data_prevista_28d.label('data_prevista_28d'),
            func.datediff(
                func.curdate(),
                func.date(data_prevista_28d)
            ).label('dias_atrasados'),
            func.coalesce(quantidade_subq.c.quantidade, 0).label('quantidade_rompimentos')
        ).outerjoin(
            quantidade_subq,
            primeira_moldagem_subq.c.numero_serie == quantidade_subq.c.numero_serie
        ).filter(
            # Já passou a data prevista
            func.date(data_prevista_28d) <= func.curdate(),
            # Não tem rompimento de 28 dias
            ~rompimento_28d_exists
        ).order_by(
            func.datediff(
                func.curdate(),
                func.date(data_prevista_28d)
            ).desc()
        )
        
        resultados = query.all()
        
        # Formatar resultados
        series_pendentes = []
        for resultado in resultados:
            data_moldagem = resultado.primeira_data_moldagem
            data_prevista_28d = resultado.data_prevista_28d
                
            series_pendentes.append({
                'numero_serie': resultado.numero_serie,
                'data_moldagem': data_moldagem.strftime('%d/%m/%Y %H:%M') if data_moldagem else '',
                'data_prevista_28d': data_prevista_28d.strftime('%d/%m/%Y') if data_prevista_28d else '',
                'dias_atrasados': resultado.dias_atrasados or 0,
                'quantidade_rompimentos': resultado.quantidade_rompimentos or 0
            })
        
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
    usinagem = ConcretoUsinagens.query.get_or_404(id)

    return render_template('usinagem_concreto/rompimentos/por_usinagem.html',
                          usinagem=usinagem)

@usinagem_concreto.route('/usinagens/<int:id>/data-usinagem')
@login_required
def get_data_usinagem(id):
    """Retorna a data de usinagem de uma usinagem específica"""
    usinagem = ConcretoUsinagens.query.get_or_404(id)
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
    """Retorna os materiais de um traço para o modal de redozagem, convertendo todas as unidades para KG."""
    try:
        traco = ConcretoTracos.query.get_or_404(traco_id)
        materiais_formatados = []
        
        # Buscar a unidade KG (tentar diferentes variações)
        unidade_kg = Unidades.query.filter(
            or_(
                Unidades.nome.ilike('KG'),
                Unidades.nome.ilike('KILO'),
                Unidades.nome.ilike('KILOS'),
                Unidades.nome == 'KG',
                Unidades.nome == 'KILO',
                Unidades.nome == 'KILOS'
            )
        ).first()
        
        if not unidade_kg:
            # Tentar buscar por nome exato
            unidade_kg = Unidades.query.filter_by(nome='KG').first()
            if not unidade_kg:
                return jsonify({'error': 'Unidade KG não encontrada no sistema. Por favor, cadastre a unidade KG.'}), 500
        
        print(f"Unidade KG encontrada: ID={unidade_kg.id}, Nome={unidade_kg.nome}")
        
        # Buscar todos os itens do traço (incluindo agrupados, se necessário)
        itens_traco = ConcretoTracosItens.query.filter_by(traco_id=traco.id).all()
        
        print(f"Total de itens encontrados no traço: {len(itens_traco)}")

        for item in itens_traco:
            if not item.material:
                print(f"Item {item.id} sem material, pulando...")
                continue
                
            material = item.material
            unidade_original = item.unidade if item.unidade else (material.unidade_obj if material.unidade_obj else None)
            
            if not unidade_original:
                print(f"Material {material.nome} (ID: {material.id}) sem unidade, pulando...")
                continue
            
            # Quantidade original do item (por m³)
            quantidade_original = float(item.quantidade) if item.quantidade else 0.0
            
            # Converter quantidade para KG
            quantidade_em_kg = quantidade_original
            foi_convertido = False
            fator_usado = 1.0
            
            # Se a unidade original não for KG, fazer a conversão
            if unidade_original.id != unidade_kg.id:
                print(f"Convertendo {material.nome}: {quantidade_original} {unidade_original.nome} (ID: {unidade_original.id}) para KG (ID: {unidade_kg.id})")
                
                # Obter fator de conversão da unidade original para KG
                fator_conversao = UnidadesConversao.obter_fator_conversao(
                    unidade_origem_id=unidade_original.id,
                    unidade_destino_id=unidade_kg.id,
                    material_id=material.id  # Tentar conversão específica para o material primeiro
                )
                
                if fator_conversao is not None and fator_conversao > 0:
                    quantidade_em_kg = quantidade_original * fator_conversao
                    foi_convertido = True
                    fator_usado = fator_conversao
                    print(f"  ✓ Conversão encontrada: {quantidade_original} × {fator_conversao} = {quantidade_em_kg} KG")
                else:
                    # Tentar buscar conversão usando nomes das unidades (fallback)
                    conversao_por_nome = UnidadesConversao.query.filter(
                        or_(
                            and_(
                                UnidadesConversao.unidade_origem_id == unidade_original.id,
                                UnidadesConversao.unidade_destino_id == unidade_kg.id
                            ),
                            and_(
                                UnidadesConversao.unidade_origem_id == unidade_kg.id,
                                UnidadesConversao.unidade_destino_id == unidade_original.id
                            )
                        )
                    ).first()
                    
                    if conversao_por_nome:
                        if conversao_por_nome.unidade_origem_id == unidade_original.id:
                            fator_conversao = conversao_por_nome.fator
                        else:
                            fator_conversao = 1.0 / conversao_por_nome.fator if conversao_por_nome.fator > 0 else None
                        
                        if fator_conversao and fator_conversao > 0:
                            quantidade_em_kg = quantidade_original * fator_conversao
                            foi_convertido = True
                            fator_usado = fator_conversao
                            print(f"  ✓ Conversão encontrada (por nome): {quantidade_original} × {fator_conversao} = {quantidade_em_kg} KG")
                        else:
                            print(f"  ✗ Não foi possível converter {unidade_original.nome} para KG para o material {material.nome} (ID: {material.id})")
                    else:
                        print(f"  ✗ Conversão não encontrada: {unidade_original.nome} (ID: {unidade_original.id}) para KG (ID: {unidade_kg.id})")
                        print(f"     Material: {material.nome} (ID: {material.id})")
                        # Mesmo sem conversão, retornar em KG (assumindo que a quantidade já está em KG ou será tratada manualmente)
            
            materiais_formatados.append({
                'material_id': material.id,
                'material_nome': material.nome,
                'unidade_nome': 'KG',  # Sempre KG
                'quantidade_por_m3_kg': round(quantidade_em_kg, 4),  # Quantidade já convertida para KG
                'quantidade_original': round(quantidade_original, 4),  # Quantidade original (para referência)
                'unidade_original_id': unidade_original.id,
                'unidade_original_nome': unidade_original.nome,
                'unidade_kg_id': unidade_kg.id,
                'convertido': foi_convertido,  # Indica se foi necessário converter
                'fator_conversao': round(fator_usado, 6) if foi_convertido else None
            })
        
        print(f"Total de materiais formatados: {len(materiais_formatados)}")
        return jsonify(materiais_formatados)
    
    except Exception as e:
        import traceback
        print(f"ERRO ao buscar materiais para redozagem: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'Erro ao buscar materiais: {str(e)}'}), 500

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
        # Decodificar URL e limpar espaços
        from urllib.parse import unquote
        numero_serie = unquote(numero_serie).strip()
        
        # Validar entrada
        if not numero_serie or len(numero_serie) == 0:
            return jsonify({
                'success': True,
                'data_moldagem': None,
                'existe': False
            })
        
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
        import traceback
        print(f"Erro ao buscar rompimento por série '{numero_serie}': {str(e)}")
        print(traceback.format_exc())
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
            resultado14 = get_value_str(row, 13)
            resultado18 = get_value_str(row, 17)
            resultado22 = get_value_str(row, 21)
            resultado26 = get_value_str(row, 25)
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
                                resultado=resultado14,
                                tipo_rompimento=tipo15
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento5_dt,
                                resultado=resultado18,
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
                                resultado=resultado14,
                                tipo_rompimento=tipo15
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento8_dt,
                                resultado=resultado18,
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
                                resultado=resultado14,
                                tipo_rompimento=tipo15
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=rompimento9_dt,
                                resultado=resultado18,
                                tipo_rompimento=tipo19
                            ))
                        except (ValueError, TypeError) as e:
                            print(f'Erro ao processar linha {index+2}, terceiro caso: {str(e)}')
                            continue
                    
                    if resultado22:
                        try:
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=calcular_data_rompimento_28_dias(data_moldagem_dt),
                                resultado=resultado22,
                                tipo_rompimento=tipo23
                            ))
                            rompimentos.append(ConcretoUsinagensRompimentos(
                                numero_serie=numero_serie,
                                data_moldagem=data_moldagem_dt,
                                data_rompimento=calcular_data_rompimento_28_dias(data_moldagem_dt),
                                resultado=resultado26,
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
