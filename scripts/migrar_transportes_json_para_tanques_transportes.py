#!/usr/bin/env python3
"""
Copia registros de transporte que estão apenas em TanquesPecas.qualidade (JSON)
para a tabela TanquesTransportes.

Agrupa peças pela mesma combinação (nota, data_transporte, transportadora, placa_carreta).

Uso:
  python scripts/migrar_transportes_json_para_tanques_transportes.py
  python scripts/migrar_transportes_json_para_tanques_transportes.py --force

Requer migração Alembic `tanques_transportes_001` aplicada e variáveis de ambiente / .env do banco.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Com `python scripts/este_arquivo.py`, o Python coloca `scripts/` no início de
# sys.path; o pacote local `scripts/email/` sombreia o módulo stdlib `email`
# e quebra imports (http.server → email.utils → ImportError em cadeia no Flask).
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))


def _paths_iguais(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


if sys.path and _paths_iguais(sys.path[0], _DIR_SCRIPT):
    sys.path.pop(0)
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from app import app
from models.database import db
from models.tanque import TanquesPecas, TanquesTransportes


def _transporte_de_qualidade(qualidade_raw):
    if not qualidade_raw:
        return None
    try:
        q = json.loads(qualidade_raw) if isinstance(qualidade_raw, str) else qualidade_raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(q, dict):
        return None
    t = q.get("transporte")
    return t if isinstance(t, dict) else None


def main():
    parser = argparse.ArgumentParser(description="Migra transportes do JSON das peças para TanquesTransportes.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Inserir mesmo se já existirem linhas em TanquesTransportes (pode duplicar grupos).",
    )
    args = parser.parse_args()

    with app.app_context():
        existentes = TanquesTransportes.query.count()
        if existentes > 0 and not args.force:
            print(
                f"Já existem {existentes} registro(s) em TanquesTransportes. "
                "Use --force para mesclar novamente (risco de duplicatas). Abortando."
            )
            sys.exit(1)

        grupos = {}
        pecas = TanquesPecas.query.filter(TanquesPecas.qualidade.isnot(None)).all()
        for peca in pecas:
            tr = _transporte_de_qualidade(peca.qualidade)
            if not tr:
                continue
            dt = str(tr.get("data_transporte") or "").strip()
            if not dt or dt.lower() in ("null", "none"):
                continue
            nota_int = TanquesTransportes.parse_nota_int(tr.get("nota"))
            if nota_int is None:
                continue
            transp = str(tr.get("transportadora") or "").strip()
            placa = str(tr.get("placa_carreta") or "").strip()
            chave = (nota_int, dt, transp, placa)
            grupos.setdefault(chave, []).append(peca.id)

        inseridos = 0
        for (nota, dt_s, transp, placa), ids in grupos.items():
            ids_unicos = sorted(set(ids))
            if not ids_unicos:
                continue
            dados_adicionais = json.dumps({"placa_carreta": placa}, ensure_ascii=False)
            row = TanquesTransportes(
                nota=nota,
                cte=None,
                transportadora=transp or None,
                data_transporte=TanquesTransportes.parse_data_transporte(dt_s),
                dados_adicionais=dados_adicionais,
            )
            row.definir_pecas_ids(ids_unicos)
            db.session.add(row)
            inseridos += 1

        db.session.commit()
        print(f"Grupos distintos encontrados: {len(grupos)}")
        print(f"Registros inseridos em TanquesTransportes: {inseridos}")


if __name__ == "__main__":
    main()
