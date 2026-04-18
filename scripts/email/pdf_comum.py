"""
PDF compartilhado: checagem de duplicata, imagem/código de barras, NFe por chave/nome.
Usado por vários tipos de e-mail (NFe, protocolo, reembolso, DUA).
"""
import json
import logging
import re
import sys

from pdf2image import convert_from_bytes
from pyzbar.pyzbar import decode

from models.arquivei import Arquivei
from models.database import db
from models.nota_fiscal import NotaFiscal
from models.upload import Upload
from utils.utils import validar_chave_acesso

from scripts.email.pipeline_dua import processar_dua_codigo_i25
from scripts.email.pipeline_protocolo import protocolo_id_resolvido, upload_pdf_listagem_protocolo
from scripts.email.texto import extrair_numero_fornecedor_do_nome, normalizar_texto
from scripts.email.upload_service import processar_upload


def processar_anexo_pdf_pagina(
    anexo,
    filename,
    payload,
    tipo,
    protocolo_id: int | None = None,
    mapa_nf_protocolo_id: dict[int, int] | None = None,
):
    """Processa uma página de PDF (código de barras, DUA, vínculo a nota, protocolo)."""
    print("processar_anexo_pdf_pagina inicio")
    dados_adicionais = {"codbarras": None}
    anexo["codbarras"] = {"qtd": 0, "codigos": [], "erro": []}

    if "protocolo" in filename.lower() and tipo != 2:
        logging.info(f"Ignorando arquivo de protocolo (tipo != 2): {filename}")
        return False

    up = (
        db.session.query(
            Upload.id,
            Upload.pai,
            Upload.pai_id,
            Upload.tipo,
            Upload.filename,
            Upload.mimetype,
            Upload.dados_adicionais,
        )
        .filter(Upload.filename == filename)
        .first()
    )
    if up:
        logging.info(f"upload filename {filename} existe")
        return True
    logging.info(f"upload filename {filename} nao existe")

    if upload_pdf_listagem_protocolo(anexo, filename, payload, tipo):
        return True

    logging.info(f"tentando a chave por codigo de barras do arquivo {filename}")

    poppler_path = "/usr/bin" if sys.platform == "linux" else None
    try:
        img = convert_from_bytes(payload, 500, poppler_path=poppler_path)[0]
    except Exception as e:
        logging.error(f"Erro ao converter o arquivo {filename} para imagem: {e}")
        anexo["codbarras"]["erro"].append(str(e))
        img = convert_from_bytes(payload, 500, poppler_path=poppler_path)[0]

    decs = []
    try:
        print("decodando imagem")
        decs = decode(img)
        anexo["codbarras"]["qtd"] = len(decs)
    except Exception as e:
        logging.error(f"Erro ao decodificar o arquivo {filename}: {e}")
        anexo["codbarras"]["erro"].append(str(e))

    dec1 = None
    tiponf = None

    if decs:
        for dec in decs:
            anexo["codbarras"]["codigos"].append(
                {"decodificado": dec.data.decode("utf-8"), "tiponf": dec.type}
            )
        dados_adicionais["codbarras"] = anexo["codbarras"]["codigos"]
        dec = [d for d in decs if d.type == "CODE128"]
        dua = [d for d in decs if d.type == "I25"]
        if dua:
            processar_dua_codigo_i25(dua, payload, filename, dados_adicionais, anexo, tipo)
            return True
        if dec:
            dec1 = dec[0].data.decode("utf-8") if dec[0].data else None
            tiponf = dec1[20:22] if dec1 and len(dec1) > 22 else None
        else:
            dec = [d for d in decs if d.type == "QRCODE"]
            if dec:
                dec1 = dec[0].data.decode("utf-8") if dec[0].data else None
                if "https://nfe.fazenda.sp.gov.br/CTeConsulta" in dec1:
                    dec1 = dec1.split("=")[1]
                    dec1 = dec1.split("&")[0]
                    tiponf = "57"
                elif "https://www.nfse.gov.br/ConsultaPublica" in dec1:
                    dec1 = dec1.split("&")[1]
                    dec1 = dec1.split("=")[1]
                    tiponf = "nfse"

    if dec1:
        if not validar_chave_acesso(dec1):
            logging.warning(
                f"Código de barras/QR code decodificado não é uma chave de acesso válida: {dec1} (tamanho: {len(dec1) if dec1 else 0})"
            )
            anexo["nao_identificados"] += 1
            dec1 = None
        else:
            logging.info(f"com codigo de barras /qrcode tipo: {tiponf} dec1: {dec1}")
            nota = NotaFiscal.query.filter(NotaFiscal.chave_acesso == dec1).first()
            anexo["db"].append({"chave_acesso": dec1, "nota": nota.id if nota else None})

            if nota:
                logging.info(f"nota encontrada {nota.id} {nota.numero_nf}")
                pid = protocolo_id_resolvido(tipo, None, nota, protocolo_id, mapa_nf_protocolo_id)
                if pid and tipo == 2:
                    dados_adicionais["protocolo_id"] = pid
                processar_upload(anexo, nota, filename, payload, tipo, dados_adicionais)
                return True
            tiponfc = (
                "nfe"
                if tiponf == "55"
                else "cte"
                if tiponf == "57"
                else "nfse"
                if tiponf == "nfse"
                else None
            )
            if tiponfc:
                try:
                    arquivei = Arquivei(chave_acesso=dec1, tipo=tiponfc)
                    if arquivei.xml_data:
                        nota = NotaFiscal(xml_data=arquivei.xml_data, tipo=tiponfc)
                        if nota:
                            pid = protocolo_id_resolvido(tipo, None, nota, protocolo_id, mapa_nf_protocolo_id)
                            if pid and tipo == 2:
                                dados_adicionais["protocolo_id"] = pid
                            processar_upload(anexo, nota, filename, payload, tipo, dados_adicionais)
                        return True
                except Exception as e:
                    logging.error(f"Erro ao buscar no Arquivei com chave {dec1}: {e}")
                    dec1 = None
            else:
                logging.info(f"codBarras nao identificado {dec1}")
                anexo["nao_identificados"] += 1
                dec1 = None

    else:
        logging.info(f"tentando pelo numero e fornecedor {filename}")
        numero_nf, fornecedor = extrair_numero_fornecedor_do_nome(filename)
        if not numero_nf or not fornecedor:
            logging.error(f"Não foi possível extrair número da NF ou fornecedor do arquivo: {filename}")
            return False

        numero_nf = int(numero_nf.strip())
        notas = NotaFiscal.query.filter(NotaFiscal.numero_nf == numero_nf).all()

        fornecedor_normalizado = normalizar_texto(fornecedor)
        if not notas:
            logging.info(f"numero nf {numero_nf} nao encontrado no db")
            dados = None
            pid = protocolo_id_resolvido(tipo, numero_nf, None, protocolo_id, mapa_nf_protocolo_id)
            if pid and tipo == 2:
                dados = json.dumps({"protocolo_id": pid})
            Upload.registrar("NotaFiscal", 0, tipo, filename, "application/pdf", payload, dados_adicionais=dados)
            logging.info(f"upload realizado sem nota {numero_nf}")
            return True

        nota = None
        for n in notas:
            emitente_normalizado = normalizar_texto(n.nome_emitente)
            if fornecedor_normalizado in emitente_normalizado:
                nota = n
                break

        if nota:
            logging.info(f"nota encontrada {nota.id} {nota.numero_nf}")
            try:
                dados = None
                pid = protocolo_id_resolvido(tipo, numero_nf, nota, protocolo_id, mapa_nf_protocolo_id)
                if pid and tipo == 2:
                    dados = json.dumps({"protocolo_id": pid})
                Upload.registrar(
                    pai="NotaFiscal",
                    pai_id=nota.id,
                    tipo=tipo,
                    filename=filename,
                    mimetype="application/pdf",
                    blob=payload,
                    dados_adicionais=dados,
                )
                logging.info(f"upload realizado {numero_nf}")
                return True
            except Exception as e:
                logging.error(f"Erro ao fazer upload do PDF protocolo para NF {numero_nf}: {e}")
                return False

        logging.info(f"fornecedor nao encontrado {numero_nf}")
        dados = None
        pid = protocolo_id_resolvido(tipo, numero_nf, None, protocolo_id, mapa_nf_protocolo_id)
        if pid and tipo == 2:
            dados = json.dumps({"protocolo_id": pid})
        Upload.registrar(
            pai="NotaFiscal",
            pai_id=0,
            tipo=tipo,
            filename=filename,
            mimetype="application/pdf",
            blob=payload,
            dados_adicionais=dados,
        )
        logging.info(f"upload realizado sem nota {numero_nf}")
        return True
