"""
WhatsApp / Evolution API e consultas auxiliares (centro de custo).
"""
import logging

import requests

from models.database import db

from scripts.email.config import carregar_variaveis_ambiente


def enviar_mensagem(payload, tipo="sendText"):
    env = carregar_variaveis_ambiente()
    url = f"http://192.168.8.150:8081/message/{tipo}/{env['EVOLUTION_API_INSTANCE']}"
    headers = {
        "apikey": env["EVOLUTION_API_TOKEN"],
        "Content-Type": "application/json",
    }

    try:
        response = requests.request("POST", url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        logging.error(f"Erro ao enviar mensagem: {e}")
        return None


def get_CC(nnf):
    from models.centro_custo import CentroCusto
    from models.contrato import Contrato
    from models.nota_fiscal import NotaFiscal, NotaFiscalItem
    from models.tanque import Tanque

    try:
        cc = (
            db.session.query(CentroCusto)
            .join(Contrato)
            .join(Tanque)
            .join(NotaFiscalItem, NotaFiscalItem.codigo == Tanque.item_nf)
            .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
            .filter(
                NotaFiscal.numero_nf == nnf,
                NotaFiscal.cnpj_emitente.like("%27126997000187%"),
            )
            .first()
        )
        if cc:
            return cc.codigo
        return None
    except Exception as e:
        logging.error(f"Erro ao buscar centro de custo: {e}")
        return None
