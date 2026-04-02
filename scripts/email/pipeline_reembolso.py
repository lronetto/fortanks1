"""
Pipeline reembolso (tipo 3): PDF com várias páginas separadas por página.
"""
import io
import logging

from PyPDF2 import PdfReader

from utils.utils import separar_pdf_por_paginas


def processar_reembolso_pdf_multiplas_paginas(
    anexo,
    filename,
    payload,
    protocolo_id,
    mapa_nf_protocolo_id,
):
    """
    Se o PDF de reembolso tiver mais de uma página, separa e processa cada página.
    Retorna True se alguma página foi processada com sucesso.
    """
    from scripts.email.pdf_comum import processar_anexo_pdf_pagina

    try:
        pdf_reader = PdfReader(io.BytesIO(payload))
        num_paginas = len(pdf_reader.pages)
        logging.info(f"PDF de reembolso com {num_paginas} páginas detectado. Separando por páginas...")
        if num_paginas > 1:
            logging.info(f"PDF de reembolso com {num_paginas} páginas detectado. Separando por páginas...")
            paginas_separadas = separar_pdf_por_paginas(payload, filename)

            resultados = []
            total_paginas = len(paginas_separadas)
            logging.info(f"Iniciando processamento de {total_paginas} páginas separadas")

            for idx, (payload_pagina, filename_pagina) in enumerate(paginas_separadas):
                try:
                    anexo_pagina = {
                        "filename": filename_pagina,
                        "codbarras": {"qtd": 0, "codigos": [], "erro": []},
                        "db": [],
                        "upload": False,
                        "nao_identificados": 0,
                    }

                    logging.info(f"processando página {idx+1}/{total_paginas}: {filename_pagina}")
                    resultado = processar_anexo_pdf_pagina(
                        anexo_pagina,
                        filename_pagina,
                        payload_pagina,
                        3,
                        mapa_nf_protocolo_id=mapa_nf_protocolo_id,
                    )
                    resultados.append(resultado)

                    if "codbarras" in anexo_pagina and "codbarras" in anexo:
                        anexo["codbarras"]["qtd"] += anexo_pagina["codbarras"].get("qtd", 0)
                        anexo["codbarras"]["codigos"].extend(anexo_pagina["codbarras"].get("codigos", []))
                        anexo["codbarras"]["erro"].extend(anexo_pagina["codbarras"].get("erro", []))
                    if "db" in anexo_pagina:
                        anexo["db"].extend(anexo_pagina.get("db", []))
                    if anexo_pagina.get("upload", False):
                        anexo["upload"] = True
                    anexo["nao_identificados"] += anexo_pagina.get("nao_identificados", 0)

                    logging.info(f"Página {idx+1}/{total_paginas} processada: resultado={resultado}")
                except Exception as e_pagina:
                    logging.error(f"Erro ao processar página {idx+1}/{total_paginas} ({filename_pagina}): {e_pagina}")
                    import traceback

                    logging.debug(f"Traceback: {traceback.format_exc()}")
                    if "codbarras" in anexo and "erro" in anexo["codbarras"]:
                        anexo["codbarras"]["erro"].append(f"Erro ao processar {filename_pagina}: {str(e_pagina)}")
                    resultados.append(False)
                    continue

            paginas_processadas = sum(1 for r in resultados if r)
            logging.info(f"Processamento concluído: {paginas_processadas}/{total_paginas} páginas processadas com sucesso")
            return any(resultados)
    except Exception as e:
        logging.error(f"Erro ao verificar/separar páginas do PDF {filename}: {e}")

    return processar_anexo_pdf_pagina(
        anexo, filename, payload, 3, protocolo_id=protocolo_id, mapa_nf_protocolo_id=mapa_nf_protocolo_id
    )
