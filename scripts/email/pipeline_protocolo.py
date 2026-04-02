"""
Pipeline de e-mails tipo protocolo (tipo 2): mapa NF→protocolo, listagens em PDF.
"""
import logging
import re

from scripts.email.protocolo_db import obter_ou_criar_protocolo_por_numero


def protocolo_id_resolvido(
    tipo: int,
    numero_nf: int | None,
    nota,
    protocolo_id: int | None,
    mapa_nf_protocolo_id: dict[int, int] | None,
) -> int | None:
    """Usa mapa NF→protocolo (listagens) com fallback ao protocolo único."""
    if tipo != 2:
        return None
    if mapa_nf_protocolo_id and numero_nf is not None:
        r = mapa_nf_protocolo_id.get(int(numero_nf))
        if r is not None:
            return r
    if mapa_nf_protocolo_id and nota is not None and getattr(nota, "numero_nf", None) is not None:
        try:
            nf_int = int(nota.numero_nf)
        except (TypeError, ValueError):
            nf_int = None
        if nf_int is not None:
            r = mapa_nf_protocolo_id.get(nf_int)
            if r is not None:
                return r
    return protocolo_id


def _extrair_numero_protocolo_do_texto_pdf(texto: str) -> str | None:
    """
    Localiza o número do protocolo no texto do PDF.

    Espaços opcionais entre o 'nº' e os dígitos também cobrem quebra de linha (pdfminer
    pode colocar o número só na linha seguinte a 'Protocolo nº').
    """
    m = re.search(r"(?i)Protocolo\s+n[ºo\u00ba]?\s*(\d{5,12})\b", texto)
    if m:
        return m.group(1)
    m = re.search(r"(?i)Protocolo\s+(\d{5,12})\b", texto)
    if m:
        return m.group(1)
    return None


def _numero_protocolo_do_nome_arquivo_pdf(fn: str) -> str | None:
    """Ex.: ``Protocolo 264231943.pdf`` ou ``protocolo264231943.pdf``."""
    m = re.search(r"(?i)protocolo\s*(\d{5,12})\s*\.pdf", fn.strip())
    return m.group(1) if m else None


def _nf_da_linha_listagem(line: str) -> int | None:
    """
    Extrai número da NF de uma linha da tabela.

    Aceita ``4453 CEDISA``, ``524448RDG ACOS`` (NF colada em sufixo) e ignora valores monetários.
    """
    line = line.strip()
    if not line or line in ("X", "T", "x"):
        return None
    if re.match(r"^\d{1,3}[.,]\d{3}", line):
        return None
    m = re.match(r"^(\d{3,9})(?=\s|[A-Za-zÀ-ÿ\u00c0-\u017f])", line)
    if not m:
        return None
    v = int(m.group(1))
    if v < 100:
        return None
    return v


def extrair_listagem_nfs_pdf_protocolo(payload: bytes) -> tuple[str | None, set[int]]:
    """
    Lê PDF tipo "RELAÇÃO DE NOTAS FISCAIS" e retorna o número do protocolo no cabeçalho
    e o conjunto de números de N.F. da tabela.
    """
    try:
        import io

        from pdfminer.high_level import extract_text

        texto = extract_text(io.BytesIO(payload))
    except Exception as e:
        logging.warning(f"Erro ao extrair texto do PDF de listagem de protocolo: {e}")
        return None, set()

    num_proto = _extrair_numero_protocolo_do_texto_pdf(texto)

    nfs: set[int] = set()
    for line in texto.splitlines():
        nf = _nf_da_linha_listagem(line)
        if nf is not None:
            nfs.add(nf)
    return num_proto, nfs


def montar_mapa_nf_protocolo_id(msg) -> tuple[dict[int, int], list[str], int | None]:
    """
    Monta mapa número da NF -> protocolo_id usando assunto (vários PROTOCOLO …)
    e PDFs de listagem (``Protocolo … .pdf``).
    """
    from scripts.email.texto import extrair_todos_protocolos_do_texto

    subject = getattr(msg, "subject", "") or ""
    numeros_assunto = extrair_todos_protocolos_do_texto(subject)
    ids_por_numero: dict[str, int] = {}

    for num in numeros_assunto:
        try:
            p = obter_ou_criar_protocolo_por_numero(num)
            ids_por_numero[num] = p.id
        except Exception as e:
            logging.error(f"Erro ao obter/criar protocolo {num}: {e}")

    mapa_nf: dict[int, int] = {}
    attachments = getattr(msg, "attachments", None) or []

    for att in attachments:
        fn = (att.get("filename") or "").lower()
        if not fn.endswith(".pdf") or "protocolo" not in fn:
            continue
        try:
            payload = att["content"].getvalue()
        except Exception as e:
            logging.warning(f"Anexo {fn}: não foi possível ler bytes: {e}")
            continue

        num_pdf, nfs = extrair_listagem_nfs_pdf_protocolo(payload)
        if not num_pdf:
            num_pdf = _numero_protocolo_do_nome_arquivo_pdf(fn)
        if not num_pdf or not nfs:
            continue

        pid = ids_por_numero.get(num_pdf)
        if pid is None:
            try:
                p = obter_ou_criar_protocolo_por_numero(num_pdf)
                pid = p.id
                ids_por_numero[num_pdf] = pid
            except Exception as e:
                logging.error(f"Erro ao criar protocolo {num_pdf} a partir do PDF de listagem: {e}")
                continue

        for nf in nfs:
            if nf in mapa_nf and mapa_nf[nf] != pid:
                logging.warning(
                    f"NF {nf} associada a mais de um protocolo no mesmo e-mail; mantendo o último vínculo."
                )
            mapa_nf[nf] = pid

        logging.info(
            f"Listagem protocolo {num_pdf} ({fn}): {len(nfs)} NF(s) mapeada(s) para protocolo_id={pid}"
        )

    fallback: int | None = None
    if numeros_assunto:
        fallback = ids_por_numero.get(numeros_assunto[0])
    if fallback is None and mapa_nf:
        fallback = next(iter(set(mapa_nf.values())))
    if fallback is None and ids_por_numero:
        fallback = next(iter(ids_por_numero.values()))

    return mapa_nf, numeros_assunto, fallback


def upload_pdf_listagem_protocolo(anexo, filename: str, payload: bytes, tipo: int) -> bool:
    """
    Se for ``Protocolo123456.pdf`` em e-mail tipo protocolo, faz upload da listagem e retorna True.
    Chamar apenas quando o anexo ainda não existir no banco (checagem comum já feita).
    """
    import json

    from models.upload import Upload

    if tipo != 2:
        return False
    mlist = re.match(r"(?i)^protocolo\s*(\d+)\.pdf$", (filename or "").strip())
    if not mlist:
        return False
    try:
        prot = obter_ou_criar_protocolo_por_numero(mlist.group(1))
    except Exception as e:
        logging.error(f"Erro ao vincular PDF de listagem ao protocolo: {e}")
        return False
    dados = json.dumps({"protocolo_id": prot.id})
    # Uma única chamada com blob: o modelo Upload ignora segunda inserção com o mesmo
    # (pai, pai_id, tipo, filename, mimetype), então gravar só metadados primeiro deixa o PDF vazio.
    Upload("NotaFiscal", 0, tipo, filename, "application/pdf", payload, dados_adicionais=dados)
    logging.info(f"Upload de PDF de listagem do protocolo {mlist.group(1)}")
    anexo["upload"] = True
    return True
