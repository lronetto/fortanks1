"""
Rotas relacionadas a rompimentos de corpo de prova
"""
from flask import render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required
from models.concreto import ConcretoUsinagensRompimentos, ConcretoUsinagens
from models.database import db
from datetime import datetime
from decimal import Decimal
from collections import defaultdict
from sqlalchemy import func, case, and_, exists, select, text, desc
from urllib.parse import unquote
import pandas as pd
import os
import tempfile
from werkzeug.utils import secure_filename
from . import usinagem_concreto
from controllers.utils import (
    get_value_datetime,
    get_value_str,
    is_date_string,
    calcular_data_rompimento_28_dias
)


@usinagem_concreto.route('/rompimentos/api')
@login_required
def listar_rompimentos_api():
    """API para listar rompimentos com filtros e agrupamento"""
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
        rompimento = ConcretoUsinagensRompimentos.query.get_or_404(id)
        
        db.session.delete(rompimento)
        db.session.commit()
        
        flash('Rompimento excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir rompimento: {str(e)}', 'error')
        
    return redirect(url_for('usinagem_concreto.listar_rompimentos'))


@usinagem_concreto.route('/rompimentos/buscar-por-serie/<numero_serie>')
@login_required
def buscar_rompimento_por_serie(numero_serie):
    """Busca um rompimento pelo número de série e retorna a data de moldagem"""
    try:
        # Decodificar URL e limpar espaços
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


@usinagem_concreto.route('/rompimentos/importar-excel', methods=['POST'])
@login_required
def importar_rompimentos_excel():
    """
    Importa rompimentos de corpo de prova a partir de um arquivo Excel
    """
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
        
        for index, row in df.iterrows():
            rompimentos = []
            
            # Tentar obter numero_serie - pode estar em diferentes colunas
            numero_serie = None
            # Tentar coluna 0 primeiro (primeira coluna de dados)
            valor_col0 = get_value_str(row, 0)
            if valor_col0 and not is_date_string(valor_col0):
                numero_serie = valor_col0
           
            print(f'linha: {index+1} - numero_serie: {numero_serie}')
            data_moldagem_dt = None
            rompimento5_dt = None
            rompimento8_dt = None
            rompimento9_dt = None
            
            data_moldagem_dt = get_value_datetime(row, 1, index)
            rompimento5_dt = get_value_datetime(row, 4, index)
            rompimento8_dt = get_value_datetime(row, 7, index)
            rompimento9_dt = get_value_datetime(row, 8, index)
            
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
                    for rompimento in rompimentos:
                        if not rompimento.is_exist():
                            db.session.add(rompimento)
                        else:
                            print(f'linha {index+6}: serie {numero_serie} já existe!')
                            continue
                    db.session.commit()
                    print(f'linha {index+6}: serie {numero_serie} importado(s) com sucesso!')
                except (ValueError, TypeError) as e:
                    print(f'Erro ao processar linha {index+8}, salvar rompimentos: {str(e)}')
                    continue
        
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))
                    
    except Exception as e:
        return redirect(url_for('usinagem_concreto.listar_rompimentos'))
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
