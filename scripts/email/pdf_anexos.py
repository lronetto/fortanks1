"""
Orquestração de anexos PDF: delega para o pipeline do tipo de e-mail (reembolso vs fluxo comum).
"""
import logging

from scripts.email.pdf_comum import processar_anexo_pdf_pagina
from scripts.email.pipeline_reembolso import processar_reembolso_pdf_multiplas_paginas


def processar_anexo_pdf(
    anexo,
    filename,
    payload,
    tipo,
    protocolo_id: int | None = None,
    mapa_nf_protocolo_id: dict[int, int] | None = None,
):
    """Processa um anexo PDF conforme o tipo de e-mail."""
    logging.info(f"processando anexo pdf tipo: {tipo} filename: {filename}")

    if "codbarras" not in anexo:
        anexo["codbarras"] = {"qtd": 0, "codigos": [], "erro": []}
    if "db" not in anexo:
        anexo["db"] = []
    if "upload" not in anexo:
        anexo["upload"] = False
    if "nao_identificados" not in anexo:
        anexo["nao_identificados"] = 0

    if tipo == 3:
        return processar_reembolso_pdf_multiplas_paginas(
            anexo, filename, payload, protocolo_id, mapa_nf_protocolo_id
        )

    return processar_anexo_pdf_pagina(
        anexo, filename, payload, tipo, protocolo_id=protocolo_id, mapa_nf_protocolo_id=mapa_nf_protocolo_id
    )
