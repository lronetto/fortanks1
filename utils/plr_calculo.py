"""
Cálculo de PLR: tempo de casa, salário base e multiplicador.
Regra: salário base para PLR = salário do cargo no período × multiplicador;
       se tempo de casa (meses) > 18 então multiplicador = 2, senão 1.
"""
from datetime import date
from dateutil.relativedelta import relativedelta


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
    meses = (fim.year - data_admissao.year) * 12
    meses += (fim.month - data_admissao.month)
    if data_admissao.day <=15: 
        meses+=1   
    return max(0, meses)
    meses = (fim.year - data_admissao.year) * 12
    meses = relativedelta(fim, data_admissao).months
    if data_admissao.day <=15: 
        meses+=1   
   # meses = (fim.year - data_admissao.year) * 12 + (fim.month - data_admissao.month)
    
    return max(0, meses)


def assiduidade_pct_por_faltas(faltas):
    """
    Converte quantidade de faltas no mês em percentual de assiduidade (0-100).
    Regra: 1 falta = 90%, 2 = 80%, 3 = 70%, 4 ou mais = 0%.
    """
    if faltas is None:
        return None
    try:
        n = int(faltas)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return 100.0
    if n >= 4:
        return 0.0
    return 100.0 - (n * 10.0)


def multiplicador_tempo_casa(tempo_mes):
    """
    Multiplicador do salário base para PLR conforme tempo de casa.
    Por padrão: mais de 18 meses → 2; até 18 meses → 1.
    """
    if tempo_mes > 18:
        return 1.2
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

    if colaborador.cargo_id in [1, 2, 7]:
        cargo_salario = CargoSalario.query.filter(
            CargoSalario.cargo_id == 1,
            CargoSalario.data <= data_fechamento,
        ).order_by(CargoSalario.data.desc()).first()
    else:
        cargo_salario = CargoSalario.query.filter(
            CargoSalario.cargo_id == 3,
            CargoSalario.data <= data_fechamento,
        ).order_by(CargoSalario.data.desc()).first()

    salario_base = cargo_salario.salario if cargo_salario else None
    salario_base_plr = (float(salario_base) * mult) if salario_base is not None else None
    return {
        'tempo_casa_meses': tempo_meses,
        'salario_base': salario_base,
        'multiplicador': mult,
        'salario_base_plr': salario_base_plr,
    }
