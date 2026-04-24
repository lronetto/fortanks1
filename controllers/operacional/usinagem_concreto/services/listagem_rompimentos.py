"""Consultas e montagem de payloads para listagens de rompimentos (sem Flask request)."""

from collections import defaultdict

from models.concreto import ConcretoUsinagensRompimentos
from models.database import db


def montar_resposta_listar_rompimentos_api(filtrar_sem_28dias: bool, agrupar: bool) -> dict:
    """Monta o dict JSON para GET /rompimentos/api."""
    if filtrar_sem_28dias:
        todas_series = db.session.query(ConcretoUsinagensRompimentos.numero_serie).distinct().all()
        series_sem_28dias = []

        for serie_tuple in todas_series:
            serie = serie_tuple[0]
            rompimentos_serie = ConcretoUsinagensRompimentos.query.filter_by(numero_serie=serie).all()

            tem_28dias = False
            for romp in rompimentos_serie:
                if romp.data_moldagem and romp.data_rompimento:
                    diff_days = (romp.data_rompimento - romp.data_moldagem).total_seconds() / 3600 / 24
                    if 27 <= diff_days <= 29:
                        tem_28dias = True
                        break

            if not tem_28dias:
                series_sem_28dias.append(serie)

        if series_sem_28dias:
            query = ConcretoUsinagensRompimentos.query.filter(
                ConcretoUsinagensRompimentos.numero_serie.in_(series_sem_28dias)
            )
        else:
            query = ConcretoUsinagensRompimentos.query.filter(False)
    else:
        query = ConcretoUsinagensRompimentos.query

    rompimentos = query.all()

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

    def rompimento_to_dict(rompimento):
        return {
            'id': rompimento.id,
            'numero_serie': rompimento.numero_serie,
            'data_moldagem': rompimento.data_moldagem.strftime('%d/%m/%Y %H:%M') if rompimento.data_moldagem else None,
            'data_rompimento': rompimento.data_rompimento.strftime('%d/%m/%Y %H:%M'),
            'idade': calcular_idade(rompimento),
            'resultado': float(rompimento.resultado) if rompimento.resultado else None,
            'tipo_rompimento': rompimento.tipo_rompimento,
            'observacoes': rompimento.observacoes,
            'fator_conversao': float(rompimento.fator_conversao) if rompimento.fator_conversao else 1.2
        }

    if agrupar:
        grupos_dict = defaultdict(list)
        for rompimento in rompimentos:
            grupos_dict[rompimento.numero_serie].append(rompimento)

        grupos_data = []
        for serie, rompimentos_serie in grupos_dict.items():
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

        return {
            'success': True,
            'agrupado': True,
            'grupos': grupos_data
        }

    rompimentos_data = [rompimento_to_dict(r) for r in rompimentos]

    return {
        'success': True,
        'agrupado': False,
        'rompimentos': rompimentos_data
    }
