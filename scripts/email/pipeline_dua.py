"""
Pipeline DUA (tipo 6): código de barras I25 e campos extraídos do PDF.
"""
import io
import logging
import re

from pdfminer.high_level import extract_text

from models.nota_fiscal import CNPJS_MATRIZ_FILIAIS, NotaFiscal

from scripts.email.upload_service import processar_upload


def extrair_dados_dua(pdf_input):
    """Extrai texto e campos de uma DUA a partir de bytes, caminho ou file-like."""
    if isinstance(pdf_input, (bytes, bytearray)):
        texto = extract_text(io.BytesIO(pdf_input))
    else:
        texto = extract_text(pdf_input)

    dados = {}

    data_match = re.search(r"Pagamento\s+(\d{2}/\d{2}/\d{4})", texto)
    if data_match:
        dados["data"] = data_match.group(1)

    valor_match = re.search(r"Receita\s+R\$\s*([\d\.,]+)", texto)
    if valor_match:
        dados["valor"] = valor_match.group(1)

    dacte_match = re.search(r"DACTE\s*N[ºo]\s*(\d+)", texto, re.IGNORECASE)
    if dacte_match:
        dados["dacte"] = dacte_match.group(1)

    nf_match = re.search(r"NF\s*N[ºo]\s*(\d+)", texto, re.IGNORECASE)
    if nf_match:
        dados["nf"] = nf_match.group(1)

    emitente_match = re.search(
        r"DACTE\s*N[ºo]\s*\d+\s*EMITIDO\s*EM\s*\d{2}/\d{2}/\d{4}\s*\n?([A-Z\s]+)",
        texto,
        re.IGNORECASE,
    )
    if emitente_match:
        dados["emitente_dacte"] = emitente_match.group(1).strip()

    return dados


def processar_dua_codigo_i25(dua, payload, filename, dados_adicionais, anexo, tipo):
    """Processa código de barras I25 típico de DUA (858…)."""
    print("processar_dua inicio")
    cod = dua[0].data.decode("utf-8").strip()
    print(f"cod: {cod} int(cod[:3]): {int(cod[:3])}")
    if int(cod[:3]) == 858:
        duan = cod[27:37]
        dados = extrair_dados_dua(payload)
        nf = NotaFiscal.query.filter(
            NotaFiscal.numero_nf == dados["nf"],
            NotaFiscal.cnpj_emitente.in_(CNPJS_MATRIZ_FILIAIS),
        ).first()
        if nf:
            dados["nf_id"] = nf.id
            cte = nf.get_cte()
            dados["cte_id"] = cte.id if cte else None
        else:
            dados["nf_id"] = None

        dados["dua"] = duan
        dados["valor"] = float(cod[9:15]) / 100
        print(f"dados: {dados}")
        dados_adicionais["dua"] = dados
        processar_upload(anexo=anexo, filename=filename, payload=payload, tipo=tipo, dados_adicionais=dados_adicionais)
    return True
