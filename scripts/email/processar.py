"""
Fluxo principal: leitura IMAP e processamento de caixa de entrada.
"""
import imaplib
import json
import logging
import time
from datetime import datetime

from imbox import Imbox

from models.logs import Logs

from scripts.email.anexos_pipeline import processar_anexos_email
from scripts.email.config import (
    DELAY_ENTRE_EMAILS,
    MARCAR_LIDOS_EM_LOTE,
    MAX_EMAILS_POR_EXECUCAO,
    ORDENAR_EMAILS_POR_ANEXOS,
    TAMANHO_LOTE_MARCAR_LIDOS,
    carregar_variaveis_ambiente,
)
from scripts.email.imap_bodystructure import buscar_uids_ordenados_por_anexos
from scripts.email.imap_fetch import buscar_emails_por_uids
from scripts.email.pipeline_protocolo import montar_mapa_nf_protocolo_id
from scripts.email.texto import determinar_tipo_email


def processar_emails():
    """Processa emails (NFe, protocolo, reembolso, DUA) e anexos."""
    env = carregar_variaveis_ambiente()
    if not env["IMAP_HOST"] or not env["IMAP_USER"] or not env["IMAP_PASS"]:
        logging.error("Credenciais IMAP não configuradas corretamente.")
        return

    logging.info("processar_emails")
    quota_exceeded = False
    imap = None
    try:
        uids_ordenados = []
        contagem_anexos = {}
        if ORDENAR_EMAILS_POR_ANEXOS:
            logging.info("Buscando emails ordenados por quantidade de anexos (usando apenas BODYSTRUCTURE)...")
            uids_ordenados, contagem_anexos = buscar_uids_ordenados_por_anexos(
                env["IMAP_HOST"],
                env["IMAP_USER"],
                env["IMAP_PASS"],
                remetente="leandro.netto@fortanks.ind.br",
                max_emails=MAX_EMAILS_POR_EXECUCAO,
            )
            if not uids_ordenados:
                logging.info("Nenhum email encontrado ou erro ao buscar UIDs ordenados.")
                return

        if uids_ordenados:
            total_emails_ordenados = len(uids_ordenados)
            logging.info(f"Encontrados {total_emails_ordenados} emails ordenados por quantidade de anexos.")
            logging.info(
                f"UIDs ordenados (menos anexos primeiro): {uids_ordenados[:5]}..."
                if len(uids_ordenados) > 5
                else f"UIDs ordenados: {uids_ordenados}"
            )
            logging.info("Buscando emails individualmente do servidor (um por vez na ordem otimizada)...")

            emails_para_processar = buscar_emails_por_uids(env, uids_ordenados, contagem_anexos)
            logging.info(f"{len(emails_para_processar)} emails encontrados e ordenados corretamente (menos anexos primeiro).")
            usar_imaplib_para_marcar = True
        else:
            usar_imaplib_para_marcar = False
            with Imbox(env["IMAP_HOST"], env["IMAP_USER"], env["IMAP_PASS"]) as imap:
                emails = imap.messages(unread=True, sent_from="leandro.netto@fortanks.ind.br", raw="has:attachment")
                emails_lista = list(emails)
                total_emails = len(emails_lista)
                emails_para_processar = emails_lista[:MAX_EMAILS_POR_EXECUCAO]
                if total_emails > MAX_EMAILS_POR_EXECUCAO:
                    logging.info(
                        f"Total de emails: {total_emails}. Processando apenas {MAX_EMAILS_POR_EXECUCAO} por execução para evitar exceder quota."
                    )

        print(f"emails: {len(emails_para_processar)}")

        log_email = {
            "qtd email": len(emails_para_processar),
            "processados": 0,
            "email": [],
        }

        uids_processados = []

        if usar_imaplib_para_marcar:
            mail_marcar = imaplib.IMAP4_SSL(env["IMAP_HOST"])
            mail_marcar.login(env["IMAP_USER"], env["IMAP_PASS"])
            mail_marcar.select("INBOX")
        else:
            mail_marcar = None

        if len(emails_para_processar) > 0:
            for idx, (uid, msg) in enumerate(emails_para_processar):
                if quota_exceeded:
                    logging.warning("Quota de comandos IMAP excedida. Interrompendo processamento.")
                    break
                log_email["processados"] += 1
                num_anexos_email = len(msg.attachments) if msg.attachments else 0
                logging.info(
                    f"[{idx+1}/{len(emails_para_processar)}] Processando e-mail (UID {uid}): {num_anexos_email} anexos - {msg.subject}"
                )

                tipo = determinar_tipo_email(msg.subject)
                logging.info(f"tipo: {tipo}")

                log_email["email"].append(
                    {
                        "subject": msg.subject,
                        "anexos_total": len(msg.attachments),
                        "anexos_processados": 0,
                        "anexos_existentes": {"files": [], "qtd": 0},
                        "tipo": tipo,
                        "anexos": [],
                        "arquivei": [],
                    }
                )
                if tipo > 0:
                    log_email_entry = log_email["email"][-1]
                    protocolo_id = None
                    mapa_nf_protocolo_id: dict[int, int] | None = None
                    if tipo == 2:
                        try:
                            mapa_nf_protocolo_id, numeros_prot, protocolo_id = montar_mapa_nf_protocolo_id(msg)
                            log_email_entry["protocolos_assunto"] = numeros_prot
                            log_email_entry["mapa_nf_protocolo_ids"] = {
                                str(k): v for k, v in (mapa_nf_protocolo_id or {}).items()
                            }
                            if protocolo_id is not None:
                                log_email_entry["protocolo_id_fallback"] = protocolo_id
                            if numeros_prot:
                                log_email_entry["protocolo_numero"] = numeros_prot[0]
                        except Exception as e:
                            logging.error(f"Erro ao montar mapa de protocolos/NFs: {e}")
                            mapa_nf_protocolo_id = {}
                        if not mapa_nf_protocolo_id and protocolo_id is None:
                            logging.warning(
                                "E-mail tipo protocolo: nenhum protocolo no assunto e nenhuma listagem "
                                "reconhecida nos PDFs; uploads usarão protocolo_id nulo se não houver fallback."
                            )

                    anexos_processados, ignorado, total_nao_processados = processar_anexos_email(
                        msg,
                        tipo,
                        log_email_entry,
                        protocolo_id=protocolo_id,
                        mapa_nf_protocolo_id=mapa_nf_protocolo_id,
                    )

                    if len(msg.attachments) > 0:
                        anexos_existentes_qtd = log_email_entry["anexos_existentes"]["qtd"]
                        anexos_restantes = total_nao_processados - anexos_processados
                        logging.info(
                            f"Email processado: {anexos_processados} anexos novos processados, {anexos_existentes_qtd} já existiam, {anexos_restantes} restantes para próxima execução (total: {len(msg.attachments)}, ignorados: {ignorado})"
                        )
                        log_email_entry["anexos_processados"] = anexos_processados
                        log_email_entry["anexos_ignorados"] = ignorado
                        log_email_entry["anexos_restantes"] = anexos_restantes

                uids_processados.append(uid)

                if MARCAR_LIDOS_EM_LOTE:
                    deve_marcar_lote = len(uids_processados) >= TAMANHO_LOTE_MARCAR_LIDOS or idx == len(emails_para_processar) - 1

                    if deve_marcar_lote and not quota_exceeded:
                        try:
                            marcados = 0
                            for uid_lote in uids_processados:
                                try:
                                    if usar_imaplib_para_marcar:
                                        mail_marcar.store(uid_lote, "+FLAGS", "\\Seen")
                                    else:
                                        imap.mark_seen(uid_lote)
                                    marcados += 1
                                except Exception as e_uid:
                                    logging.warning(f"Erro ao marcar UID {uid_lote} como lido: {e_uid}")
                            if marcados > 0:
                                logging.info(f"{marcados} de {len(uids_processados)} emails marcados como lidos em lote")
                            uids_processados = []
                        except imaplib.IMAP4.abort as e:
                            error_msg = str(e)
                            if "OVERQUOTA" in error_msg:
                                quota_exceeded = True
                                logging.error(f"Quota de comandos IMAP excedida ao marcar emails como lidos: {error_msg}")
                                logging.warning(
                                    f"{len(uids_processados)} emails foram processados mas não foram marcados como lidos devido à quota excedida"
                                )
                                uids_processados = []
                            else:
                                logging.error(f"Erro IMAP ao marcar emails como lidos: {error_msg}")
                                uids_processados = []
                        except Exception as e:
                            logging.error(f"Erro não tratado ao marcar emails como lidos: {e}")
                            uids_processados = []
                else:
                    try:
                        if usar_imaplib_para_marcar:
                            mail_marcar.store(str(uid), "+FLAGS", "\\Seen")
                        else:
                            imap.mark_seen(uid)
                        logging.info(f"Email {msg.subject} processado com sucesso")
                    except imaplib.IMAP4.abort as e:
                        error_msg = str(e)
                        if "OVERQUOTA" in error_msg:
                            quota_exceeded = True
                            logging.error(f"Quota de comandos IMAP excedida ao marcar email como lido: {error_msg}")
                            logging.warning(
                                f"Email {msg.subject} foi processado mas não foi marcado como lido devido à quota excedida"
                            )
                        else:
                            logging.error(f"Erro IMAP ao marcar email como lido: {error_msg}")
                            raise
                    except Exception as e:
                        logging.error(f"Erro não tratado ao marcar email como lido: {e}")
                        raise

                if DELAY_ENTRE_EMAILS > 0 and idx < len(emails_para_processar) - 1:
                    time.sleep(DELAY_ENTRE_EMAILS)

                if not quota_exceeded and (
                    not MARCAR_LIDOS_EM_LOTE or len(uids_processados) == 0 or idx == len(emails_para_processar) - 1
                ):
                    try:
                        Logs(local="processar_email", data=datetime.now(), texto=json.dumps(log_email))
                    except Exception as e:
                        logging.error(f"Erro ao salvar log: {e}")

                if quota_exceeded:
                    logging.warning("Interrompendo processamento devido à quota excedida")
                    break

            if MARCAR_LIDOS_EM_LOTE and len(uids_processados) > 0 and not quota_exceeded:
                try:
                    marcados = 0
                    for uid_lote in uids_processados:
                        try:
                            if usar_imaplib_para_marcar:
                                mail_marcar.store(str(uid_lote), "+FLAGS", "\\Seen")
                            else:
                                imap.mark_seen(uid_lote)
                            marcados += 1
                        except Exception as e_uid:
                            logging.warning(f"Erro ao marcar UID {uid_lote} como lido: {e_uid}")
                    if marcados > 0:
                        logging.info(f"{marcados} de {len(uids_processados)} emails restantes marcados como lidos")
                except imaplib.IMAP4.abort as e:
                    error_msg = str(e)
                    if "OVERQUOTA" in error_msg:
                        logging.error(f"Quota de comandos IMAP excedida ao marcar emails restantes: {error_msg}")
                    else:
                        logging.error(f"Erro IMAP ao marcar emails restantes: {error_msg}")
                except Exception as e:
                    logging.error(f"Erro ao marcar emails restantes: {e}")

            if usar_imaplib_para_marcar and mail_marcar:
                try:
                    mail_marcar.close()
                    mail_marcar.logout()
                except Exception:
                    pass
    except imaplib.IMAP4.abort as e:
        error_msg = str(e)
        if "OVERQUOTA" in error_msg:
            logging.error(f"Quota de comandos IMAP excedida durante operação: {error_msg}")
            logging.warning("Processamento interrompido. Aguarde alguns minutos antes de tentar novamente.")
        else:
            logging.error(f"Erro IMAP não tratado: {error_msg}")
            raise
    except Exception as e:
        logging.error(f"Erro não tratado: {e}")
        raise
