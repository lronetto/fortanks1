"""
Contagem de anexos via BODYSTRUCTURE e ordenação de UIDs IMAP.
"""
import imaplib
import logging


def contar_anexos_por_header(imap_conn, uid):
    """
    Conta anexos de um email usando apenas o BODYSTRUCTURE, sem baixar o conteúdo.
    """
    try:
        status, data = imap_conn.fetch(str(uid), "(BODYSTRUCTURE)")
        if status != "OK" or not data or not data[0]:
            return 0

        body_data = data[0]
        estrutura = None
        if isinstance(body_data, tuple):
            if len(body_data) >= 2:
                estrutura = body_data[1]
            elif len(body_data) == 1:
                estrutura = body_data[0]
        else:
            estrutura = body_data

        if estrutura is None:
            return 0

        estrutura_str = str(estrutura).lower()
        estrutura_original = str(estrutura)

        count_attachment = estrutura_str.count("attachment")
        tem_filename = (
            "filename" in estrutura_str
            or "name" in estrutura_str
            or "filename" in estrutura_original
            or "name" in estrutura_original
        )

        tipos_anexo = [
            "application/pdf",
            "application/zip",
            "application/x-zip",
            "application/octet-stream",
            "image/",
            "video/",
            "audio/",
            "application/msword",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats",
        ]
        tem_tipo_anexo = any(tipo in estrutura_str for tipo in tipos_anexo)
        multipart_count = estrutura_str.count("multipart")

        if count_attachment > 0:
            return count_attachment

        if tem_filename:
            if multipart_count > 0:
                partes_nao_texto = (
                    estrutura_str.count("application/")
                    + estrutura_str.count("image/")
                    + estrutura_str.count("video/")
                    + estrutura_str.count("audio/")
                )
                if partes_nao_texto > 0:
                    return partes_nao_texto
                return 1
            return 1

        if tem_tipo_anexo:
            count_tipos = sum(1 for tipo in tipos_anexo if tipo in estrutura_str)
            if count_tipos > 0:
                return count_tipos

        if multipart_count > 1:
            return multipart_count - 1

        return 0

    except Exception as e:
        logging.warning(f"Erro ao contar anexos do email UID {uid}: {e}")
        import traceback

        logging.debug(f"Traceback: {traceback.format_exc()}")
        return 0


def buscar_uids_ordenados_por_anexos(
    imap_host, imap_user, imap_pass, remetente=None, max_emails=None
):
    """
    Busca UIDs de emails não lidos e ordena por quantidade de anexos (menos primeiro).
    """
    try:
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(imap_user, imap_pass)
        mail.select("INBOX")

        if remetente:
            criterio = f'UNSEEN FROM "{remetente}"'
        else:
            criterio = "UNSEEN"

        status, messages = mail.search(None, criterio)
        if status != "OK" or not messages[0]:
            mail.close()
            mail.logout()
            logging.info("Nenhum email não lido encontrado com os critérios especificados.")
            return [], {}

        uids = messages[0].split()
        total_uids = len(uids)

        logging.info(f"Encontrados {total_uids} emails não lidos. Contando anexos para ordenação...")

        emails_com_contagem = []
        for idx, uid in enumerate(uids):
            try:
                uid_str = uid.decode()
                num_anexos = contar_anexos_por_header(mail, uid_str)

                if idx < 2:
                    status, data = mail.fetch(uid_str, "(BODYSTRUCTURE)")
                    if status == "OK" and data and data[0]:
                        estrutura_str = str(
                            data[0][1] if len(data[0]) > 1 else data[0]
                        ).lower()
                        logging.info(
                            f"UID {uid_str}: num_anexos={num_anexos}, estrutura (primeiros 500 chars): {estrutura_str[:500]}"
                        )

                emails_com_contagem.append((uid_str, num_anexos))

                if num_anexos == 0 and idx < 5:
                    logging.info(
                        f"UID {uid_str}: Nenhum anexo detectado (será processado com prioridade menor)"
                    )

                if (idx + 1) % 10 == 0:
                    logging.info(
                        f"Verificados {idx + 1}/{total_uids} emails... ({len(emails_com_contagem)} com anexos encontrados)"
                    )
            except Exception as e:
                logging.warning(f"Erro ao processar UID {uid}: {e}")
                import traceback

                logging.debug(f"Traceback: {traceback.format_exc()}")
                continue

        emails_com_anexos = [e for e in emails_com_contagem if e[1] > 0]
        logging.info(
            f"Total de {len(emails_com_contagem)} emails processados. {len(emails_com_anexos)} com anexos detectados, {len(emails_com_contagem) - len(emails_com_anexos)} sem anexos detectados (serão processados com prioridade menor)."
        )

        emails_com_contagem.sort(key=lambda x: x[1])

        if len(emails_com_contagem) > 0:
            primeiro = emails_com_contagem[0]
            ultimo = emails_com_contagem[-1]
            logging.info(
                f"Ordenação: Primeiro email (UID {primeiro[0]}) tem {primeiro[1]} anexos, último (UID {ultimo[0]}) tem {ultimo[1]} anexos."
            )
            if len(emails_com_contagem) <= 10:
                logging.info(
                    f"Lista completa ordenada: {[(uid, count) for uid, count in emails_com_contagem]}"
                )

        contagem_anexos_dict = {uid: count for uid, count in emails_com_contagem}

        if max_emails and len(emails_com_contagem) > max_emails:
            uids_ordenados = [uid for uid, _ in emails_com_contagem[:max_emails]]
            logging.info(
                f"Selecionados {len(uids_ordenados)} emails com menos anexos para processar (de {len(emails_com_contagem)} totais)."
            )
        else:
            uids_ordenados = [uid for uid, _ in emails_com_contagem]
            logging.info(
                f"Todos os {len(uids_ordenados)} emails serão processados (ordenados por anexos - menos primeiro)."
            )

        mail.close()
        mail.logout()

        return uids_ordenados, contagem_anexos_dict

    except Exception as e:
        logging.error(f"Erro ao buscar UIDs ordenados: {e}")
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass
        return [], {}
