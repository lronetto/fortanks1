"""Utilitários do domínio PLR (cálculos e importação de planilhas)."""

from .calculo import (
    assiduidade_pct_por_faltas,
    multiplicador_tempo_casa,
    nota_media_com_assiduidade,
    salario_base_plr,
    tempo_de_casa_meses,
)
from .importacao_planilha import ler_avaliacoes_planilha, ler_avaliacoes_planilha_xls

__all__ = [
    "assiduidade_pct_por_faltas",
    "multiplicador_tempo_casa",
    "nota_media_com_assiduidade",
    "salario_base_plr",
    "tempo_de_casa_meses",
    "ler_avaliacoes_planilha",
    "ler_avaliacoes_planilha_xls",
]
