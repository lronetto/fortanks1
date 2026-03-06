"""
Cálculo de PLR: tempo de casa, salário base e multiplicador.
Regra: salário base para PLR = salário do cargo no período × multiplicador;
       se tempo de casa (meses) > 18 então multiplicador = 2, senão 1.
"""
from datetime import date


def tempo_de_casa_meses(data_admissao, data_fechamento):
    """
    Retorna o tempo de casa em meses (inteiro).
    data_fechamento: data de demissão ou data de fechamento do período.
    """
    if not data_admissao:
        return 0
    fim = data_fechamento if data_fechamento else date.today()
    if data_admissao > fim:
        return 0
    meses = (fim.year - data_admissao.year) * 12 + (fim.month - data_admissao.month)
    if fim.day < data_admissao.day:
        meses -= 1
    return max(0, meses)


def multiplicador_tempo_casa(tempo_meses, limite_meses=18, multiplicador_acima=2):
    """
    Multiplicador do salário base para PLR conforme tempo de casa.
    Por padrão: mais de 18 meses → 2; até 18 meses → 1.
    """
    if tempo_meses > limite_meses:
        return multiplicador_acima
    return 1


def salario_base_plr(colaborador, mes_ref, ano_ref, data_fechamento, db_session):
    """
    Retorna salário base para PLR do colaborador no mês/ano de referência,
    aplicando o multiplicador por tempo de casa.

    Retorno: dict com tempo_casa_meses, salario_base (do cargo), multiplicador, salario_base_plr.
    Se não houver CargoSalario para o cargo no mês/ano, salario_base e salario_base_plr ficam None.
    """
    from models.cargo_salario import CargoSalario

    data_admissao = colaborador.data_admissao
    data_fim = data_fechamento or colaborador.data_demissao or date.today()
    tempo_meses = tempo_de_casa_meses(data_admissao, data_fim)
    mult = multiplicador_tempo_casa(tempo_meses)

    cargo_salario = (
        db_session.query(CargoSalario)
        .filter(
            CargoSalario.cargo_id == colaborador.cargo_id,
            CargoSalario.mes == mes_ref,
            CargoSalario.ano == ano_ref,
        )
        .first()
    )
    if not cargo_salario or cargo_salario.salario is None:
        return {
            'tempo_casa_meses': tempo_meses,
            'salario_base': None,
            'multiplicador': mult,
            'salario_base_plr': None,
        }
    salario_base = float(cargo_salario.salario)
    salario_base_plr = salario_base * mult
    return {
        'tempo_casa_meses': tempo_meses,
        'salario_base': salario_base,
        'multiplicador': mult,
        'salario_base_plr': salario_base_plr,
    }
