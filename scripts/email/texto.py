"""
Normalização de texto, assunto de e-mail e extração de dados do nome de arquivo.
"""
import logging
import re
import unicodedata
from email.header import decode_header

from scripts.email.config import (
    ASSUNTO_PADRAO_DUA,
    ASSUNTO_PADRAO_NFE,
    ASSUNTO_PADRAO_PROTOCOLO,
    ASSUNTO_PADRAO_REEMBOLSO,
)


def normalizar_texto(texto):
    """
    Remove acentos e caracteres especiais do texto.
    """
    if not texto:
        return texto

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))

    substituicoes = {
        "ç": "c",
        "Ç": "C",
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "ä": "a",
        "Á": "A",
        "À": "A",
        "Ã": "A",
        "Â": "A",
        "Ä": "A",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "É": "E",
        "È": "E",
        "Ê": "E",
        "Ë": "E",
        "í": "i",
        "ì": "i",
        "î": "i",
        "ï": "i",
        "Í": "I",
        "Ì": "I",
        "Î": "I",
        "Ï": "I",
        "ó": "o",
        "ò": "o",
        "õ": "o",
        "ô": "o",
        "ö": "o",
        "Ó": "O",
        "Ò": "O",
        "Õ": "O",
        "Ô": "O",
        "Ö": "O",
        "ú": "u",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "Ú": "U",
        "Ù": "U",
        "Û": "U",
        "Ü": "U",
        "ý": "y",
        "ÿ": "y",
        "Ý": "Y",
        "Ÿ": "Y",
        "ñ": "n",
        "Ñ": "N",
        "/": ".",
        "\\": ".",
        "&": "E",
        "E.": "E",
        " S.A": " SA",
        " S/A": " SA",
        " LTDA": " LTDA",
        "LTDA.": "LTDA",
        " ME": " ME",
        " EPP": " EPP",
        ".": "",
        "DADALTO LUCAS E UNIFORMES ME": "DADALTO LUVAS E UNIFORMES ME",
        "DADALTO LUVAS E UNIFORMES - ME": "DADALTO LUVAS E UNIFORMES ME",
        "MIRANDA RESTAURANTE LTDA": "MIRANDA RESTAURANTES LTDA",
        "BRASITALIA AGREGADOS LTDA": "BRASITALIA AGREGADOS PARA CONSTRUCAO LTDA",
        "NEOBETEL EQUIP DE PROTEÇÃO INDIVIDUAL LTDA": "NEOBETEL EPI, EQUIPAMENTOS DE PROTECAO INDIVIDUAL LTDA",
        "ES PRODUTOS SIDERGÚRGICOS LTDA": "ES PRODUTOS SIDERURGICOS LTDA",
        "FERRARI MAQ E FERRAMENTAS LTDA": "FERRARI MAQUINAS E FERRAMENTAS LTDA EPP",
        "TECNOSIL IND E COM DE PRODUTOS QUIMICOS": "Tecnosil Industria e Comercio de Produtos Quimicos Ltda.",
    }

    for char, replacement in substituicoes.items():
        texto = texto.replace(char, replacement)

    texto = " ".join(texto.split())
    return texto


def extrair_numero_fornecedor_do_nome(nome_arquivo):
    """
    Extrai o número da nota fiscal e o nome do fornecedor do nome do arquivo.
    """
    try:
        logging.info(f"Processando arquivo: {nome_arquivo}")
        numero_nf = None
        fornecedor = None
        nome_sem_ext = nome_arquivo.replace(".pdf", "")
        nome_sem_ext = re.sub(r"_pagina_\d+$", "", nome_sem_ext)

        if nome_sem_ext.startswith("Protocolo"):
            numero_protocolo = nome_sem_ext.replace("Protocolo", "").strip()
            return numero_protocolo, "PROTOCOLO"

        qtd_hifens = nome_sem_ext.count("-")
        if qtd_hifens == 1:
            if "- NF" in nome_sem_ext:
                partes = nome_sem_ext.split(" - NF")
                print(f"Partes do nome (reembolso): {partes}")
                if len(partes) == 2:
                    fornecedor = partes[0].strip()
                    numero_nf = partes[1].replace(".", "").strip()
                    print(f"Reembolso encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
        else:
            partes = nome_sem_ext.split(" - ")
            if len(partes) == 3:
                fornecedor = partes[2].strip()
                partes[1] = partes[1].replace(".", "")
                delimitador = re.sub(r"\d", "", partes[1])
                numero_nf = partes[1].split(delimitador)[1].strip().replace(".", "")
            elif len(partes) > 3:
                fornecedor = (partes[2] + " - " + partes[3]).strip()
                numero_nf = partes[1].split("NF")[1].strip().replace(".", "")
            else:
                print("Formato inválido")

        if numero_nf and fornecedor:
            fornecedor = normalizar_texto(fornecedor)
            return numero_nf, fornecedor
        print("Formato de protocolo inválido")
        return None, None
    except Exception as e:
        print(f"Erro ao extrair número e fornecedor do nome do arquivo: {e}")
        return None, None


def decodificar_assunto_email(subject_raw):
    """Decodifica o assunto do email que pode vir codificado."""
    if not subject_raw:
        return ""

    if isinstance(subject_raw, bytes):
        try:
            subject_raw = subject_raw.decode("utf-8", errors="ignore")
        except Exception:
            subject_raw = str(subject_raw)

    if isinstance(subject_raw, str) and not subject_raw.strip().startswith("=?"):
        return subject_raw.strip()

    try:
        decoded_parts = decode_header(subject_raw)
        decoded_subject = ""

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    if encoding:
                        decoded_subject += part.decode(encoding, errors="ignore")
                    else:
                        try:
                            decoded_subject += part.decode("utf-8", errors="ignore")
                        except Exception:
                            decoded_subject += part.decode("latin-1", errors="ignore")
                except Exception:
                    try:
                        decoded_subject += part.decode("utf-8", errors="ignore")
                    except Exception:
                        decoded_subject += part.decode("latin-1", errors="ignore")
            else:
                decoded_subject += str(part)

        return decoded_subject.strip()
    except Exception as e:
        logging.warning(f"Erro ao decodificar assunto do email: {e}")
        return str(subject_raw).strip()


def determinar_tipo_email(subject):
    """
    Determina o tipo de email baseado no assunto.
    Retorna: 0=desconhecido, 1=NFE, 2=Protocolo, 3=Reembolso, 4=DUA (6 no fluxo legado para DUA).
    """
    subject_decodificado = decodificar_assunto_email(subject)

    if any(p in subject_decodificado for p in ASSUNTO_PADRAO_PROTOCOLO):
        return 2
    if any(p in subject_decodificado for p in ASSUNTO_PADRAO_REEMBOLSO):
        return 3
    if any(p in subject_decodificado for p in ASSUNTO_PADRAO_NFE):
        return 1
    if any(p in subject_decodificado for p in ASSUNTO_PADRAO_DUA):
        return 6
    return 0


def _normalizar_numero_protocolo(valor: str | None) -> str | None:
    if not valor:
        return None
    v = str(valor).strip()
    v = re.sub(r"\s+", " ", v)
    return v or None


def extrair_todos_protocolos_do_texto(texto: str | None) -> list[str]:
    """
    Extrai todos os números de protocolo do texto (ex.: assunto com
    ``ENC: PROTOCOLO 264231942 / PROTOCOLO 264231943``).
    Retorna lista única na ordem de aparição.
    """
    if not texto:
        return []
    t = decodificar_assunto_email(texto) if not isinstance(texto, str) else texto
    t = " ".join(t.split())

    encontrados = re.findall(
        r"(?i)\bPROTOCOLO\s+([0-9]{5,12}(?:/[0-9]{2,4})?)\b",
        t,
    )
    if not encontrados:
        m = re.search(
            r"(?i)\bprotocolo\b\s*(?:n[ºo]\.?\s*)?[:\-]?\s*([0-9]{3,12}(?:/[0-9]{2,4})?)\b",
            t,
        )
        if m:
            n = _normalizar_numero_protocolo(m.group(1))
            return [n] if n else []
        m2 = re.search(r"\b([0-9]{5,12})\b", t)
        if m2:
            n = _normalizar_numero_protocolo(m2.group(1))
            return [n] if n else []
        return []

    vistos: set[str] = set()
    ordem: list[str] = []
    for raw in encontrados:
        n = _normalizar_numero_protocolo(raw)
        if n and n not in vistos:
            vistos.add(n)
            ordem.append(n)
    return ordem


def extrair_numero_protocolo_do_texto(texto: str | None) -> str | None:
    """Extrai o primeiro número de protocolo a partir de texto (assunto ou PDF)."""
    todos = extrair_todos_protocolos_do_texto(texto)
    return todos[0] if todos else None
