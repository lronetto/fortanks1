"""Testes unitários para models.nota_fiscal.movimentacao_estoque (Fase C)."""
from types import SimpleNamespace

from models.nota_fiscal.constants import CNPJS_FILIAIS, CNPJS_MATRIZ
from models.nota_fiscal.movimentacao_estoque import determinar_movimentacoes_estoque

# CNPJ de terceiro (não matriz nem filiais cadastradas)
CNPJ_TERCEIRO = "00000000000000"
CNPJ_MATRIZ = CNPJS_MATRIZ[0]
CNPJ_FILIAL_A = CNPJS_FILIAIS[0]


def _nf(emitente, destinatario, tipo=1):
    return SimpleNamespace(
        cnpj_emitente=emitente,
        cnpj_destinatario=destinatario,
        tipo=tipo,
    )


class TestDeterminarMovimentacoesEstoque:
    def test_tipo_maior_que_um_retorna_vazio(self):
        assert determinar_movimentacoes_estoque(_nf(CNPJ_TERCEIRO, CNPJ_MATRIZ, tipo=2)) == []
        assert determinar_movimentacoes_estoque(_nf(CNPJ_TERCEIRO, CNPJ_MATRIZ, tipo=3)) == []

    def test_compra_externa_para_matriz(self):
        movs = determinar_movimentacoes_estoque(_nf(CNPJ_TERCEIRO, CNPJ_MATRIZ, tipo=1))
        assert movs == [("Estoque Matriz", "entrada")]

    def test_compra_externa_para_filial(self):
        movs = determinar_movimentacoes_estoque(_nf(CNPJ_TERCEIRO, CNPJ_FILIAL_A, tipo=1))
        assert movs == [(f"Estoque Filial {CNPJ_FILIAL_A}", "entrada")]

    def test_transferencia_matriz_para_filial(self):
        movs = determinar_movimentacoes_estoque(_nf(CNPJ_MATRIZ, CNPJ_FILIAL_A, tipo=1))
        assert movs == [
            ("Estoque Matriz", "saida"),
            (f"Estoque Filial {CNPJ_FILIAL_A}", "entrada"),
        ]

    def test_transferencia_filial_para_matriz(self):
        movs = determinar_movimentacoes_estoque(_nf(CNPJ_FILIAL_A, CNPJ_MATRIZ, tipo=1))
        assert movs == [
            (f"Estoque Filial {CNPJ_FILIAL_A}", "saida"),
            ("Estoque Matriz", "entrada"),
        ]
