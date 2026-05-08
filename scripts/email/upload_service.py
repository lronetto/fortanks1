"""
Criação de Upload e liberação de nota a partir do processamento de anexos.
"""
import json
import logging
from operator import or_, and_
import time
from datetime import datetime

from models.database import db
from models.upload import Upload


def processar_upload(anexo, nota=None, filename=None, payload=None, tipo=None, dados_adicionais="{}"):
    print("processar_upload inicio")
    tinicia_tempo = time.time()
    up = None
    if nota:
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
            .filter(or_(and_(Upload.pai_id == nota.id, Upload.pai == 'NotaFiscal'), 
                        and_(Upload.filename == filename, Upload.tipo == tipo)))
            .first()
        )
    tempo_fim = time.time()
    logging.info(f"tempo de execucao 1: {tempo_fim - tinicia_tempo} segundos")
    tinicia_tempo = time.time()
    file_name = filename
    if up and tipo in [1,2,3]:
        json_nota = json.loads(nota.dados_adicionais)
        json_nota["liberada"] = True
        json_nota["liberada_em"] = datetime.now().isoformat()
        json_nota["liberada_por"] = "email"
        nota.dados_adicionais = json.dumps(json_nota)
        nota.save()
        return True
        # Protocolo (tipo 2): mantém o nome original do anexo do e-mail
    if tipo != 2:
        file_name = f"{nota.id}_{tipo}_{nota.numero_nf}_{nota.chave_acesso}.pdf"
    tempo_fim = time.time()
    logging.info(f"tempo de execucao 2: {tempo_fim - tinicia_tempo} segundos")
    logging.info(f"fazendo o upload da nota: {nota}")

    dados_json = None
    try:
        if isinstance(dados_adicionais, dict):
            dados_json = json.dumps(dados_adicionais)
        elif isinstance(dados_adicionais, str) and dados_adicionais.strip():
            try:
                json.loads(dados_adicionais)
                dados_json = dados_adicionais
            except Exception:
                dados_json = json.dumps({"info": dados_adicionais})
    except Exception:
        dados_json = None

    if not up:

        if tipo == 6:
            if isinstance(dados_adicionais, str) and dados_adicionais.strip():
                try:
                    dados_dict = json.loads(dados_adicionais)
                except Exception:
                    dados_dict = {"info": dados_adicionais}
            elif isinstance(dados_adicionais, dict):
                dados_dict = dados_adicionais
            else:
                dados_dict = {}

            dua_info = dados_dict.get("dua")
            dua_num = None
            if isinstance(dua_info, dict):
                dua_num = dua_info.get("dua")
            else:
                dua_num = dua_info

            try:
                if dua_num is not None:
                    pai_id_int = int(str(dua_num).strip())
                    pai_id = pai_id_int if pai_id_int <= 2147483647 else 0
            except Exception:
                logging.error(f"Erro ao converter dua_num para int: {dua_num}")
                return False

            dados_json_dua = json.dumps(dados_dict, ensure_ascii=False)
            print(f"dados_adicionais: {dados_json_dua}")
            up = Upload.registrar(
                pai="DUA",
                pai_id=dados_adicionais["dua"]["nf_id"],
                tipo=tipo,
                filename=file_name,
                mimetype="application/pdf",
                blob=payload,
                dados_adicionais=dados_json_dua,
            )
        else:
            up = Upload.registrar(
                "NotaFiscal",
                nota.id,
                tipo,
                file_name,
                "application/pdf",
                payload,
                dados_adicionais=dados_json,
            )
        tempo_fim = time.time()
        logging.info(f"tempo de execucao 3: {tempo_fim - tinicia_tempo} segundos")
    if up.id:
        anexo["upload"] = True
        logging.info(f"upload realizado {nota.numero_nf}")
        return True
    logging.info(f"upload ja existe {nota.numero_nf}")
    return False
    