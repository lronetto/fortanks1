"""
Orquestração de anexos (paralelismo e filtros).
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.upload import Upload

from scripts.email.config import (
    MAX_ANEXOS_POR_EMAIL,
    MAX_ANEXOS_POR_EMAIL_PROCESSAR,
    MAX_WORKERS_ANEXOS,
    PRIORIZAR_XML,
    PROCESSAR_APENAS_PDF_XML,
    TAMANHO_MAX_ANEXO_MB,
)
from scripts.email.pdf_anexos import processar_anexo_pdf
from scripts.email.xml_anexos import processar_anexo_xml
from scripts.email.zip_anexos import processar_anexo_zip


def _processar_um_anexo(
    att,
    tipo,
    log_email_entry,
    lock,
    protocolo_id: int | None = None,
    mapa_nf_protocolo_id: dict[int, int] | None = None,
):
    """Processa um único anexo (worker para execução paralela)."""
    filename = att["filename"]
    try:
        payload = att["content"].getvalue()
        tamanho_mb = len(payload) / (1024 * 1024)
        if tamanho_mb > TAMANHO_MAX_ANEXO_MB:
            logging.warning(
                f"Anexo {filename} muito grande ({tamanho_mb:.2f} MB). Limite: {TAMANHO_MAX_ANEXO_MB} MB. Pulando."
            )
            return (0, 1)
    except Exception as e:
        logging.error(f"Erro ao verificar tamanho do anexo {filename}: {e}")
        return (0, 0)

    from app import app

    with app.app_context():
        anexo = {
            "filename": filename,
            "tamanho_mb": round(tamanho_mb, 2),
            "codbarras": {"qtd": 0, "codigos": []},
            "db": [],
            "upload": False,
            "nao_identificados": 0,
        }

        if filename.lower().endswith(".pdf"):
            processar_anexo_pdf(
                anexo, filename, payload, tipo, protocolo_id=protocolo_id, mapa_nf_protocolo_id=mapa_nf_protocolo_id
            )
            with lock:
                log_email_entry["anexos"].append(anexo)
            return (1, 0)
        if filename.lower().endswith(".xml"):
            processar_anexo_xml(filename, payload, log_email_entry, lock=lock)
            return (1, 0)
        if filename.lower().endswith(".zip") or filename.lower().endswith(".rar"):
            processar_anexo_zip(
                anexo,
                filename,
                payload,
                tipo,
                log_email_entry,
                lock=lock,
                protocolo_id=protocolo_id,
                mapa_nf_protocolo_id=mapa_nf_protocolo_id,
            )
            if tipo != 3:
                with lock:
                    log_email_entry["anexos"].append(anexo)
            return (1, 0)
    return (0, 0)


def processar_anexos_email(
    msg,
    tipo,
    log_email_entry,
    protocolo_id: int | None = None,
    mapa_nf_protocolo_id: dict[int, int] | None = None,
):
    """Processa todos os anexos de um email em paralelo."""
    if not msg.attachments or len(msg.attachments) == 0:
        return 0, 0, 0

    log_email_entry.setdefault("arquivei", [])

    anexos_filtrados = msg.attachments
    if PROCESSAR_APENAS_PDF_XML:
        anexos_filtrados = [
            att
            for att in msg.attachments
            if att["filename"].lower().endswith((".pdf", ".xml", ".zip", ".rar"))
        ]
        if len(anexos_filtrados) < len(msg.attachments):
            logging.info(
                f"Filtrados {len(msg.attachments) - len(anexos_filtrados)} anexos não-PDF/XML/ZIP de {len(msg.attachments)} totais"
            )

    if PRIORIZAR_XML:
        anexos_ordenados = sorted(
            anexos_filtrados,
            key=lambda att: (
                0 if att["filename"].lower().endswith(".xml") else 1
                if att["filename"].lower().endswith(".pdf")
                else 2 if att["filename"].lower().endswith(".zip") else 3 if att["filename"].lower().endswith(".rar") else 4
            ),
        )
    else:
        anexos_ordenados = sorted(
            anexos_filtrados,
            key=lambda att: (
                0 if att["filename"].lower().endswith(".pdf") else 1
                if att["filename"].lower().endswith(".xml")
                else 2 if att["filename"].lower().endswith(".zip") else 3 if att["filename"].lower().endswith(".rar") else 4
            ),
        )

    anexos_nao_processados = []
    for att in anexos_ordenados:
        filename = att["filename"]
        if tipo != 3:
            up = Upload.query.filter(Upload.filename == filename).first()
            if up:
                if not up.dados_adicionais and up.pai_id == 0:
                    anexos_nao_processados.append(att)
                    continue
                logging.info(f"arquivo {filename} ja existe no db")
                log_email_entry["anexos_existentes"]["files"].append(filename)
                log_email_entry["anexos_existentes"]["qtd"] += 1
                continue
        anexos_nao_processados.append(att)

    total_anexos = len(anexos_ordenados)
    total_nao_processados = len(anexos_nao_processados)

    if total_anexos > MAX_ANEXOS_POR_EMAIL:
        logging.warning(f"Email tem {total_anexos} anexos. Limite máximo por email: {MAX_ANEXOS_POR_EMAIL}.")

    anexos_para_processar = anexos_nao_processados[:MAX_ANEXOS_POR_EMAIL_PROCESSAR]

    if total_nao_processados > MAX_ANEXOS_POR_EMAIL_PROCESSAR:
        logging.info(
            f"Email tem {total_nao_processados} anexos não processados. Processando apenas {MAX_ANEXOS_POR_EMAIL_PROCESSAR} nesta execução."
        )

    if not anexos_para_processar:
        return 0, 0, total_nao_processados

    lock = threading.Lock()
    workers = min(MAX_WORKERS_ANEXOS, len(anexos_para_processar))
    anexos_processados = 0
    ignorado = 0

    logging.info(f"Processando {len(anexos_para_processar)} anexos em paralelo (até {workers} workers).")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _processar_um_anexo, att, tipo, log_email_entry, lock, protocolo_id, mapa_nf_protocolo_id
            ): att
            for att in anexos_para_processar
        }
        for future in as_completed(futures):
            try:
                p, i = future.result()
                anexos_processados += p
                ignorado += i
            except Exception as e:
                att = futures[future]
                logging.error(f"Erro ao processar anexo {att.get('filename', '?')}: {e}")

    return anexos_processados, ignorado, total_nao_processados
