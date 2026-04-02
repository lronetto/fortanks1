"""
Processamento de anexos XML (NFe/CTe via Arquivei).
"""
import base64
import logging

from models.arquivei import Arquivei
from models.nota_fiscal import NotaFiscal


def processar_anexo_xml(filename, payload, log_email_entry, lock=None):
    """
    Processa um anexo XML: cria NotaFiscal e Arquivei.
    Se lock for passado, usa-o ao atualizar log_email_entry (thread-safe).
    """
    try:
        chave_acesso = filename.split(".")[0]
        tipo = None
        if len(chave_acesso) == 44:
            tipo = "cte" if chave_acesso[20:22] == "57" else "nfe" if chave_acesso[20:22] == "55" else None

        nf = NotaFiscal(xml_data=base64.b64encode(payload).decode("utf-8"), tipo=tipo)
        if nf.inserido:
            try:
                resp = Arquivei(xml_data=base64.b64encode(payload).decode("utf-8"))
                entry = {
                    "arquivei": resp.json(),
                    "chave_acesso": chave_acesso,
                    "tipo": tipo,
                }
                if lock:
                    with lock:
                        log_email_entry.setdefault("arquivei", []).append(entry)
                else:
                    log_email_entry.setdefault("arquivei", []).append(entry)
                return True
            except Exception as e:
                logging.error(f"Erro ao processar arquivo xml {filename}: {e}")
                return False
        logging.info(f"nota fiscal nao inserida {filename}")
        return False
    except Exception as e:
        logging.error(f"Erro ao processar XML {filename}: {e}")
        return False
