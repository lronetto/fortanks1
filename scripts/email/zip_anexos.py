"""
Processamento de anexos ZIP e RAR.
"""
import io
import logging
import os
import shutil
import tempfile
import zipfile

from scripts.email.config import RAR_SUPPORT, rarfile
from scripts.email.pdf_anexos import processar_anexo_pdf


def processar_anexo_zip(
    anexo,
    filename,
    payload,
    tipo,
    log_email_entry,
    lock=None,
    protocolo_id: int | None = None,
    mapa_nf_protocolo_id: dict[int, int] | None = None,
):
    """
    Processa um anexo ZIP ou RAR: extrai arquivos e processa conforme o tipo.
    """
    if "codbarras" not in anexo:
        anexo["codbarras"] = {"qtd": 0, "codigos": [], "erro": []}
    if "erro" not in anexo["codbarras"]:
        anexo["codbarras"]["erro"] = []

    is_rar = filename.lower().endswith(".rar")
    is_zip = filename.lower().endswith(".zip")

    if is_rar and not RAR_SUPPORT:
        logging.error(f"Arquivo RAR {filename} não pode ser processado: biblioteca rarfile não está instalada")
        anexo["codbarras"]["erro"].append("Biblioteca rarfile não está instalada. Instale com: pip install rarfile")
        return False

    try:
        tipo_arquivo = "RAR" if is_rar else "ZIP"
        logging.info(f"Processando arquivo {tipo_arquivo}: {filename}")

        arquivo_buffer = io.BytesIO(payload)

        if is_rar:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".rar") as temp_rar:
                temp_rar.write(payload)
                temp_rar_path = temp_rar.name

            try:
                try:
                    if hasattr(rarfile, "UNRAR_TOOL"):
                        logging.info(f"Tentando abrir RAR usando unrar em: {rarfile.UNRAR_TOOL}")
                    else:
                        unrar_in_path = shutil.which("unrar")
                        if unrar_in_path:
                            rarfile.UNRAR_TOOL = unrar_in_path
                            logging.info(f"unrar encontrado no PATH: {unrar_in_path}")
                        else:
                            logging.warning("unrar não encontrado no PATH. Tentando usar caminhos padrão...")

                    with rarfile.RarFile(temp_rar_path, "r") as rar_ref:
                        arquivos_no_arquivo = rar_ref.namelist()
                        logging.info(f"RAR contém {len(arquivos_no_arquivo)} arquivos: {arquivos_no_arquivo}")

                        resultado = _processar_arquivos_comprimidos(
                            rar_ref,
                            arquivos_no_arquivo,
                            anexo,
                            tipo,
                            log_email_entry,
                            tipo_arquivo,
                            lock=lock,
                            protocolo_id=protocolo_id,
                            mapa_nf_protocolo_id=mapa_nf_protocolo_id,
                        )
                except rarfile.RarCannotExec as e:
                    erro_msg = f"Ferramenta unrar não encontrada ou não pode ser executada. Erro: {str(e)}. Verifique se unrar está instalado e no PATH."
                    logging.error(f"Erro ao abrir RAR {filename}: {erro_msg}")
                    logging.error("Tentando verificar unrar...")
                    unrar_check = shutil.which("unrar")
                    if unrar_check:
                        logging.info(f"unrar encontrado em: {unrar_check}")
                        logging.info(f"Tentando configurar rarfile.UNRAR_TOOL = {unrar_check}")
                        rarfile.UNRAR_TOOL = unrar_check
                    else:
                        logging.error("unrar não encontrado no PATH do sistema")
                    anexo["codbarras"]["erro"].append(erro_msg)
                    resultado = False
            finally:
                try:
                    os.unlink(temp_rar_path)
                except Exception:
                    pass
        else:
            with zipfile.ZipFile(arquivo_buffer, "r") as zip_ref:
                arquivos_no_arquivo = zip_ref.namelist()
                logging.info(f"ZIP contém {len(arquivos_no_arquivo)} arquivos: {arquivos_no_arquivo}")

                resultado = _processar_arquivos_comprimidos(
                    zip_ref,
                    arquivos_no_arquivo,
                    anexo,
                    tipo,
                    log_email_entry,
                    tipo_arquivo,
                    lock=lock,
                    protocolo_id=protocolo_id,
                    mapa_nf_protocolo_id=mapa_nf_protocolo_id,
                )

        return resultado

    except zipfile.BadZipFile as e:
        tipo_erro = "ZIP"
        logging.error(f"Arquivo {filename} não é um {tipo_erro} válido: {e}")
        anexo["codbarras"]["erro"].append(f"Arquivo não é um {tipo_erro} válido")
        return False
    except (rarfile.RarCannotExec, rarfile.RarNoFilesError) as e:
        tipo_erro = "RAR"
        logging.error(f"Arquivo {filename} não é um {tipo_erro} válido ou não pode ser processado: {e}")
        anexo["codbarras"]["erro"].append(f"Arquivo não é um {tipo_erro} válido ou ferramenta unrar não encontrada")
        return False
    except Exception as e:
        tipo_erro = "RAR" if is_rar else "ZIP"
        logging.error(f"Erro ao processar {tipo_erro} {filename}: {e}")
        import traceback

        logging.debug(f"Traceback: {traceback.format_exc()}")
        anexo["codbarras"]["erro"].append(f"Erro ao processar {tipo_erro}: {str(e)}")
        return False


def _processar_arquivos_comprimidos(
    arquivo_ref,
    arquivos_lista,
    anexo,
    tipo,
    log_email_entry,
    tipo_arquivo,
    lock=None,
    protocolo_id: int | None = None,
    mapa_nf_protocolo_id: dict[int, int] | None = None,
):
    """Processa arquivos dentro de ZIP ou RAR."""
    if "codbarras" not in anexo:
        anexo["codbarras"] = {"qtd": 0, "codigos": [], "erro": []}
    if "erro" not in anexo["codbarras"]:
        anexo["codbarras"]["erro"] = []
    if "db" not in anexo:
        anexo["db"] = []
    if "upload" not in anexo:
        anexo["upload"] = False
    if "nao_identificados" not in anexo:
        anexo["nao_identificados"] = 0

    if tipo == 3:
        pdfs_processados = 0
        for arquivo_nome in arquivos_lista:
            if arquivo_nome.lower().endswith(".pdf"):
                try:
                    arquivo_conteudo = arquivo_ref.read(arquivo_nome)

                    anexo_pdf = {
                        "filename": arquivo_nome,
                        "codbarras": {"qtd": 0, "codigos": [], "erro": []},
                        "db": [],
                        "upload": False,
                        "nao_identificados": 0,
                    }

                    resultado = processar_anexo_pdf(
                        anexo_pdf,
                        arquivo_nome,
                        arquivo_conteudo,
                        tipo,
                        protocolo_id=protocolo_id,
                        mapa_nf_protocolo_id=mapa_nf_protocolo_id,
                    )

                    if resultado:
                        pdfs_processados += 1
                        anexo["codbarras"]["qtd"] += anexo_pdf["codbarras"].get("qtd", 0)
                        anexo["codbarras"]["codigos"].extend(anexo_pdf["codbarras"].get("codigos", []))
                        anexo["codbarras"]["erro"].extend(anexo_pdf["codbarras"].get("erro", []))
                        anexo["db"].extend(anexo_pdf.get("db", []))
                        if anexo_pdf.get("upload", False):
                            anexo["upload"] = True
                        anexo["nao_identificados"] += anexo_pdf.get("nao_identificados", 0)

                        if lock is not None:
                            with lock:
                                log_email_entry["anexos"].append(anexo_pdf)
                        else:
                            log_email_entry["anexos"].append(anexo_pdf)
                        logging.info(f"PDF {arquivo_nome} extraído do {tipo_arquivo} e processado com sucesso")
                    else:
                        logging.warning(f"Falha ao processar PDF {arquivo_nome} extraído do {tipo_arquivo}")
                except rarfile.RarCannotExec:
                    erro_msg = "Ferramenta unrar não encontrada no sistema. Instale unrar: sudo apt-get install unrar (Ubuntu/Debian) ou sudo yum install unrar (CentOS/RHEL)"
                    logging.error(f"Erro ao extrair {arquivo_nome} do {tipo_arquivo}: {erro_msg}")
                    anexo["codbarras"]["erro"].append(f"Erro ao extrair {arquivo_nome}: {erro_msg}")
                    break
                except Exception as e:
                    erro_msg = str(e)
                    if "Cannot find working tool" in erro_msg or "RarCannotExec" in str(type(e).__name__):
                        erro_msg = "Ferramenta unrar não encontrada no sistema. Instale unrar: sudo apt-get install unrar (Ubuntu/Debian) ou sudo yum install unrar (CentOS/RHEL)"
                        logging.error(f"Erro ao processar PDF {arquivo_nome} do {tipo_arquivo}: {erro_msg}")
                        anexo["codbarras"]["erro"].append(f"Erro ao processar {arquivo_nome}: {erro_msg}")
                        break
                    logging.error(f"Erro ao processar PDF {arquivo_nome} do {tipo_arquivo}: {e}")
                    import traceback

                    logging.debug(f"Traceback: {traceback.format_exc()}")
                    anexo["codbarras"]["erro"].append(f"Erro ao processar {arquivo_nome}: {str(e)}")

        if pdfs_processados > 0:
            total_pdfs = len([a for a in arquivos_lista if a.lower().endswith(".pdf")])
            logging.info(f"{tipo_arquivo} processado: {pdfs_processados} PDFs processados de {total_pdfs} PDFs encontrados")
            return True
        logging.warning(f"{tipo_arquivo} não contém PDFs válidos ou nenhum PDF foi processado com sucesso")
        return False

    logging.info(f"{tipo_arquivo} encontrado para tipo {tipo}, mas processamento específico não implementado")
    return False
