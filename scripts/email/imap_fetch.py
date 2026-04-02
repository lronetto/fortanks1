"""
Download de mensagens RFC822, extração de anexos e marcação como lido.
"""
import email
import imaplib
import io
import logging
import time
from email.header import decode_header

from scripts.email.config import (
    DELAY_ENTRE_BUSCAS_IMAP,
    MAX_EMAILS_POR_EXECUCAO,
)
from scripts.email.texto import decodificar_assunto_email


def extrair_anexos_do_email(msg_obj):
    """Extrai anexos de um objeto email.message.Message."""
    attachments = []
    for part in msg_obj.walk():
        if not isinstance(part, email.message.Message):
            continue

        disposition = part.get_content_disposition()
        filename = part.get_filename()

        is_attachment = (disposition == "attachment") or (filename and disposition != "inline")

        if is_attachment and filename:
            try:
                decoded_parts = decode_header(filename)
                decoded_filename = ""
                for header_part, encoding in decoded_parts:
                    if isinstance(header_part, bytes):
                        decoded_filename += header_part.decode(encoding or "utf-8", errors="ignore")
                    else:
                        decoded_filename += header_part
                filename = decoded_filename
            except Exception as e:
                logging.debug(f"Erro ao decodificar filename: {e}")

            try:
                content_bytes = part.get_payload(decode=True)
                if content_bytes and isinstance(content_bytes, bytes):
                    attachments.append({"filename": filename, "content": io.BytesIO(content_bytes)})
            except Exception as e:
                logging.warning(f"Erro ao extrair conteúdo do anexo {filename}: {e}")

    return attachments


def buscar_emails_por_uids(env, uids_ordenados, contagem_anexos=None):
    """
    Busca emails pelos UIDs usando imaplib.
    Retorna lista de tuplas (uid, msg_wrapper).
    """
    emails_para_processar = []

    limite_emails = MAX_EMAILS_POR_EXECUCAO
    if contagem_anexos and uids_ordenados:
        primeiro_uid = uids_ordenados[0]
        anexos_primeiro = contagem_anexos.get(primeiro_uid, 0)
        if anexos_primeiro > 20:
            limite_emails = 1
            logging.info(
                f"Primeiro email tem {anexos_primeiro} anexos. Processando apenas 1 email por execução para evitar quota."
            )
        elif anexos_primeiro > 10:
            limite_emails = min(2, MAX_EMAILS_POR_EXECUCAO)
            logging.info(
                f"Primeiro email tem {anexos_primeiro} anexos. Limitando a {limite_emails} emails por execução."
            )

    uids_para_buscar = uids_ordenados[:limite_emails] if len(uids_ordenados) > limite_emails else uids_ordenados

    if len(uids_ordenados) > limite_emails:
        logging.info(
            f"Limitando processamento a {limite_emails} emails (de {len(uids_ordenados)} totais) para evitar quota."
        )

    mail_direct = imaplib.IMAP4_SSL(env["IMAP_HOST"])
    mail_direct.login(env["IMAP_USER"], env["IMAP_PASS"])
    mail_direct.select("INBOX")

    try:
        for idx, uid_str in enumerate(uids_para_buscar):
            try:
                if idx > 0 and DELAY_ENTRE_BUSCAS_IMAP > 0:
                    time.sleep(DELAY_ENTRE_BUSCAS_IMAP)

                status, data = mail_direct.fetch(uid_str, "(RFC822)")
                if status == "OK" and data and data[0]:
                    email_body = data[0][1]
                    msg_obj = email.message_from_bytes(email_body)
                    attachments = extrair_anexos_do_email(msg_obj)

                    class MsgWrapper:
                        def __init__(self, msg_obj, attachments, uid):
                            subject_raw = msg_obj.get("Subject", "")
                            self.subject = decodificar_assunto_email(subject_raw)
                            self.attachments = attachments
                            self.uid = uid

                    msg = MsgWrapper(msg_obj, attachments, uid_str)
                    emails_para_processar.append((uid_str, msg))
                    logging.info(
                        f"Email {idx+1}/{len(uids_para_buscar)} (UID {uid_str}): {len(attachments)} anexos - {msg.subject[:60]}..."
                    )
            except Exception as e:
                logging.error(f"Erro ao buscar email UID {uid_str}: {e}")
                continue
    finally:
        mail_direct.close()
        mail_direct.logout()

    return emails_para_processar


def marcar_email_como_lido(uid, usar_imaplib, mail_marcar=None, imap=None):
    """Marca um email como lido usando imaplib ou Imbox."""
    try:
        if usar_imaplib and mail_marcar:
            mail_marcar.store(str(uid), "+FLAGS", "\\Seen")
        elif imap:
            imap.mark_seen(uid)
        return True
    except Exception as e:
        logging.warning(f"Erro ao marcar UID {uid} como lido: {e}")
        return False
