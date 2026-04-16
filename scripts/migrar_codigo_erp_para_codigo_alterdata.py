#!/usr/bin/env python3
"""
Normaliza `dados_adicionais['codigo_alterdata']` (Materiais) para inteiro.

Contexto:
- A coluna `codigo_erp` foi removida do modelo/tabela `Materiais`.
- O código Alterdata agora fica em `dados_adicionais` (JSON em TEXT) na chave `codigo_alterdata`.
"""

import json
import logging
import os
import sys

# IMPORTANTE:
# Ao executar um script dentro de `scripts/`, o Python coloca essa pasta no sys.path[0].
# Como existe `scripts/email/`, isso pode sombrear o módulo padrão `email` da stdlib
# e quebrar imports indiretos (ex: requests/urllib3).
script_dir = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
if sys.path:
    path0 = os.path.abspath(sys.path[0]) if sys.path[0] else sys.path[0]
    if path0 and os.path.normcase(path0) == os.path.normcase(script_dir):
        sys.path.pop(0)
sys.path.insert(0, project_root)

from models.database import db  # noqa: E402
from app import app  # noqa: E402
from models.material import Materiais  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def migrar(batch_size: int = 200) -> dict:
    """
    Retorna um dicionário com estatísticas da migração.
    """
    total_encontrados = 0
    total_atualizados = 0
    total_ignorado = 0
    total_erros = 0

    with app.app_context():
        query = Materiais.query.options().yield_per(batch_size)

        atualizado_no_lote = 0

        for material in query:
            total_encontrados += 1

            try:
                dados_adicionais = {}
                if material.dados_adicionais and str(material.dados_adicionais).strip():
                    try:
                        dados_adicionais = json.loads(material.dados_adicionais)
                        if not isinstance(dados_adicionais, dict):
                            dados_adicionais = {}
                    except json.JSONDecodeError:
                        dados_adicionais = {}

                valor = dados_adicionais.get("codigo_alterdata")
                if valor is None or str(valor).strip() == "":
                    total_ignorado += 1
                    continue

                # Converte para inteiro (aceita "12.0" e similares)
                try:
                    codigo_alterdata_int = int(float(str(valor).strip()))
                except (ValueError, TypeError):
                    total_ignorado += 1
                    continue

                dados_adicionais["codigo_alterdata"] = codigo_alterdata_int
                material.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)

                db.session.add(material)
                atualizado_no_lote += 1
                total_atualizados += 1

                if atualizado_no_lote >= batch_size:
                    db.session.commit()
                    atualizado_no_lote = 0

            except Exception:
                total_erros += 1
                logger.exception(
                    "Erro ao normalizar Material id=%s codigo_alterdata=%r",
                    getattr(material, "id", None),
                    getattr(material, "dados_adicionais", None),
                )
                db.session.rollback()

        if atualizado_no_lote > 0:
            db.session.commit()

    return {
        "total_encontrados": total_encontrados,
        "total_atualizados": total_atualizados,
        "total_ignorado": total_ignorado,
        "total_erros": total_erros,
    }


def main() -> None:
    logger.info("Iniciando migração de `codigo_erp` -> `dados_adicionais['codigo_alterdata']`")
    stats = migrar()
    logger.info("Migração concluída. Estatísticas: %s", stats)


if __name__ == "__main__":
    main()

