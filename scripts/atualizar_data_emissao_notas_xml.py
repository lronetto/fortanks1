#!/usr/bin/env python3
"""
Recalcula e grava apenas o campo data_emissao de cada NotaFiscal a partir do XML bruto:
coluna `xml_data` (legado) ou `Upload` referenciado em `dados_adicionais.xml_upload_id`.

Ordem de leitura no XML: primeiro valor em dhEmi; se não houver, DataEmissao; se não houver, dEmi.
Usa o mesmo parser ISO (_parse_nfe_data_emissao_xml) da importação de NF-e.

Com --atualizar-movimentacoes-estoque, roda um segundo loop (após o das datas no XML): apenas
notas que tenham ao menos um item com material vinculado (material_id preenchido); em cada uma,
alinha data_movimento das EstoqueMovimentacoes à data_emissao atual da NF
(ver models.estoque.EstoqueMovimentacoes.atualizar_data_movimentacoes_por_nota_fiscal).

Uso (na raiz do projeto, com venv ativo):
  python scripts/atualizar_data_emissao_notas_xml.py --dry-run
  python scripts/atualizar_data_emissao_notas_xml.py
  python scripts/atualizar_data_emissao_notas_xml.py --limit 100 --tipo 1
  python scripts/atualizar_data_emissao_notas_xml.py --atualizar-movimentacoes-estoque
"""

from __future__ import annotations

import argparse
import base64
import logging
import os
import sys
import traceback
import xml.etree.ElementTree as ET

# Ao rodar `python scripts/este_arquivo.py`, o Python coloca `scripts/` no sys.path e
# o pacote `scripts/email` sombreia o módulo stdlib `email` (quebra o Flask).
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_script_dir, ".."))
sys.path = [p for p in sys.path if os.path.abspath(p) != _script_dir]
if _root not in sys.path:
    sys.path.insert(0, _root)

from sqlalchemy import or_

from app import app
from models.database import db
from models.estoque import EstoqueMovimentacoes
from models.nota_fiscal import NotaFiscal, NotaFiscalItem, _parse_nfe_data_emissao_xml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def data_emissao_do_xml_bruto(xml_data_b64):
    """
    Extrai data/hora de emissão do XML armazenado em base64.
    Retorna datetime ou None se não for possível obter.
    """
    if not xml_data_b64 or not str(xml_data_b64).strip():
        return None
    try:
        raw = base64.b64decode(xml_data_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as e:
        logger.debug("Falha ao decodificar xml_data: %s", e)
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        logger.debug("XML inválido: %s", e)
        return None

    dh_emi: list[str] = []
    data_emissao_tags: list[str] = []
    demi: list[str] = []

    for el in root.iter():
        tag = el.tag.split("}")[-1]
        tx = (el.text or "").strip()
        if not tx:
            continue
        if tag == "dhEmi":
            dh_emi.append(tx)
        elif tag == "DataEmissao":
            data_emissao_tags.append(tx)
        elif tag == "dEmi":
            demi.append(tx)

    for candidato in (
        dh_emi[0] if dh_emi else None,
        data_emissao_tags[0] if data_emissao_tags else None,
        demi[0] if demi else None,
    ):
        if not candidato:
            continue
        try:
            return _parse_nfe_data_emissao_xml(candidato)
        except (ValueError, TypeError):
            continue
    return None


def _mesmo_instante(a, b) -> bool:
    if a is None or b is None:
        return False
    return a.replace(microsecond=0) == b.replace(microsecond=0)


def contar_movimentacoes_estoque_por_nf(nota_fiscal_id: int) -> int:
    """Quantidade de movimentações de estoque ligadas a itens da nota (para dry-run / log)."""
    return (
        db.session.query(EstoqueMovimentacoes.id)
        .join(NotaFiscalItem, EstoqueMovimentacoes.nota_fiscal_item_id == NotaFiscalItem.id)
        .filter(NotaFiscalItem.nf_id == nota_fiscal_id)
        .count()
    )


def nota_fiscal_ids_com_item_material_vinculado(tipo: int | None, limit: int | None) -> list[int]:
    """
    IDs de NotaFiscal que possuem ao menos um NotaFiscalItem com material vinculado.
    Mesmos filtros opcionais --tipo e --limit do script principal.
    """
    q = (
        db.session.query(NotaFiscal.id)
        .join(NotaFiscalItem, NotaFiscalItem.nf_id == NotaFiscal.id)
        .filter(NotaFiscalItem.material_id.isnot(None))
    )
    if tipo is not None:
        q = q.filter(NotaFiscal.tipo == tipo)
    q = q.distinct().order_by(NotaFiscal.id.asc())
    if limit is not None:
        q = q.limit(limit)
    return [row[0] for row in q.all()]


def main():
    parser = argparse.ArgumentParser(description="Atualiza data_emissao a partir do XML bruto.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas simula: não grava no banco.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Processa no máximo N notas (ordem por id).",
    )
    parser.add_argument(
        "--tipo",
        type=int,
        default=None,
        choices=(0, 1, 2, 3),
        help="Filtra por tipo de nota (0/1=NFe, 2=CTe, 3=NFSe).",
    )
    parser.add_argument(
        "--commit-cada",
        type=int,
        default=100,
        help="Confirma transação a cada N atualizações (padrão 100).",
    )
    parser.add_argument(
        "--atualizar-movimentacoes-estoque",
        action="store_true",
        help=(
            "Segundo passo: loop exclusivo só para notas com ao menos um item com material "
            "vinculado; alinha data_movimento das movimentações a NotaFiscal.data_emissao."
        ),
    )
    args = parser.parse_args()

    stats = {
        "processadas": 0,
        "atualizadas": 0,
        "iguais": 0,
        "sem_data_xml": 0,
        "erros": 0,
        "movimentacoes_nfs": 0,
        "movimentacoes_alteradas": 0,
        "movimentacoes_erros": 0,
    }

    with app.app_context():
        q = NotaFiscal.query.filter(
            or_(
                NotaFiscal.xml_data.isnot(None),
                NotaFiscal.dados_adicionais.contains('"xml_upload_id"'),
            )
        )
        if args.tipo is not None:
            q = q.filter(NotaFiscal.tipo == args.tipo)
        q = q.order_by(NotaFiscal.id.asc())
        if args.limit:
            q = q.limit(args.limit)

        pendentes_commit = 0
        for nf in q:
            stats["processadas"] += 1
            try:
                novo = data_emissao_do_xml_bruto(nf.get_xml_data())
                if novo is None:
                    stats["sem_data_xml"] += 1
                    logger.warning(
                        "id=%s chave=%s: não foi possível obter data do XML",
                        nf.id,
                        nf.chave_acesso,
                    )
                    continue

                emissao_mudou = not _mesmo_instante(nf.data_emissao, novo)

                if args.dry_run:
                    if emissao_mudou:
                        logger.info(
                            "[dry-run] id=%s chave=%s: data_emissao %s -> %s",
                            nf.id,
                            nf.chave_acesso,
                            nf.data_emissao,
                            novo,
                        )
                    continue

                alterou = False
                if emissao_mudou:
                    antigo = nf.data_emissao
                    nf.data_emissao = novo
                    stats["atualizadas"] += 1
                    alterou = True
                    logger.info(
                        "id=%s chave=%s: data_emissao %s -> %s",
                        nf.id,
                        nf.chave_acesso,
                        antigo,
                        novo,
                    )
                else:
                    stats["iguais"] += 1

                if alterou:
                    pendentes_commit += 1
                    if pendentes_commit >= args.commit_cada:
                        try:
                            db.session.commit()
                        except Exception as e:
                            print(
                                f"ERRO ao confirmar lote (última nota id={nf.id}): {e}",
                                file=sys.stderr,
                            )
                            traceback.print_exc(file=sys.stderr)
                            logger.error("commit em lote: %s", e)
                            db.session.rollback()
                            raise
                        pendentes_commit = 0
            except Exception as e:
                stats["erros"] += 1
                msg = f"ERRO nota id={nf.id} chave={nf.chave_acesso}: {e}"
                print(msg, file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                logger.error("%s", msg)

        if not args.dry_run and pendentes_commit:
            try:
                db.session.commit()
            except Exception as e:
                print(f"ERRO ao confirmar transação final no banco: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                logger.error("commit final: %s", e)
                db.session.rollback()
                raise

        # Segundo passo: só movimentações; apenas NFs com item com material vinculado
        if args.atualizar_movimentacoes_estoque:
            movs = EstoqueMovimentacoes.query\
                .join(NotaFiscal, NotaFiscal.id == EstoqueMovimentacoes.origem_id)\
                .filter(EstoqueMovimentacoes.origem_tipo == 'NotaFiscal')\
                .filter(EstoqueMovimentacoes.origem_id.isnot(None))\
                .all()
            logger.info(
                "Movimentações (material vinculado): %s nota(s) a processar",
                len(movs),
            )
            pendentes_commit_mov = 0
            for mov in movs:
                stats["movimentacoes_nfs"] += 1
                try:
                    print(f"data_movimento: {mov.data_movimento} data_emissao: {mov.nota_fiscal_item.nota_fiscal.data_emissao}")

                    if mov.data_movimento == mov.nota_fiscal_item.nota_fiscal.data_emissao:
                        continue
                    mov.data_movimento = mov.nota_fiscal_item.nota_fiscal.data_emissao
                    stats["movimentacoes_alteradas"] += 1
                    db.session.add(mov)
                    pendentes_commit_mov += 1
                except Exception as e:
                    stats["movimentacoes_erros"] += 1
                    msg = f"ERRO movimentações nf id={mov.id}: {e}"
                    print(msg, file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    logger.error("%s", msg)

            if not args.dry_run and pendentes_commit_mov:
                try:
                    db.session.commit()
                except Exception as e:
                    print(
                        f"ERRO ao confirmar transação final (movimentações): {e}",
                        file=sys.stderr,
                    )
                    traceback.print_exc(file=sys.stderr)
                    logger.error("commit final movimentações: %s", e)
                    db.session.rollback()
                    raise

    logger.info(
        "Resumo: processadas=%(processadas)s atualizadas=%(atualizadas)s iguais=%(iguais)s "
        "sem_data_no_xml=%(sem_data_xml)s erros=%(erros)s | "
        "mov.: nfs=%(movimentacoes_nfs)s alteradas=%(movimentacoes_alteradas)s "
        "erros_mov=%(movimentacoes_erros)s | dry_run=%(dry_run)s",
        {**stats, "dry_run": args.dry_run},
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Falha ao executar o script: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
