"""
BuscadorXMLs — modelo de fachada do Distribuição DF-e (NFe/CTe) e ADN (NFSe).

Sem acesso ao banco. Recebe certificado A1 + parâmetros, devolve um
`LoteDownload` com listas por tipo (`nfe`, `cte`, `nfse`), cada item
com `nsu`, `chave`, `xml`, `data_emissao`, etc.

Uso típico (chamador é responsável por persistir o resultado onde quiser):

    from datetime import date
    from models.sefaz_distribuicao import BuscadorXMLs, CertificadoA1

    cert = CertificadoA1("/etc/certs/empresa.pfx", "senhaA1")
    bus = BuscadorXMLs(cert, cnpj="12345678000199", uf_autor=35)

    lote = bus.buscar(
        ultimo_nsu_nfe="000000000000345",
        ultimo_nsu_cte="0",
        data_inicial=date(2026, 4, 1),
        data_final=date(2026, 4, 30),
    )
    for xml in lote:
        print(xml.tipo, xml.nsu, xml.chave)

    print("Próximo cursor NFe:", lote.ultimo_nsu_nfe)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from ..entities import LoteDownload, TipoDocumento, XmlBaixado
from ..utils.cert_utils import CertificadoA1
from . import cliente_cte, cliente_nfe, cliente_nfse
from .cliente_nfe import DocumentoXML, filtrar_por_data

log = logging.getLogger(__name__)


def _doc_para_xml_baixado(doc: DocumentoXML, tipo: TipoDocumento) -> XmlBaixado:
    return XmlBaixado(
        tipo=tipo,
        nsu=doc.nsu,
        xml=doc.xml,
        schema=doc.schema,
        chave=doc.chave,
        data_emissao=doc.data_emissao,
        cnpj_emitente=doc.cnpj_emitente,
        cnpj_destinatario=doc.cnpj_destinatario,
    )


class BuscadorXMLs:
    """
    Fachada que orquestra os clientes NFe/CTe/NFSe e devolve XMLs por tipo.

    Não acessa banco; quem usa decide o que fazer com o `LoteDownload`.
    """

    def __init__(
        self,
        certificado: CertificadoA1,
        cnpj: str,
        *,
        uf_autor: int = 35,
        ambiente: int = 1,
    ) -> None:
        self.certificado = certificado
        self.cnpj = "".join(filter(str.isdigit, cnpj)).zfill(14)
        self.uf_autor = uf_autor
        self.ambiente = ambiente

    # -- API pública -----------------------------------------------------

    def buscar(
        self,
        *,
        ultimo_nsu_nfe: str = "0",
        ultimo_nsu_cte: str = "0",
        data_inicial: Optional[date] = None,
        data_final: Optional[date] = None,
        incluir_nfse: bool = True,
        max_documentos: int = 0,
        timeout: int = 60,
    ) -> LoteDownload:
        """
        Faz as três consultas e devolve o lote consolidado.

        Args:
            ultimo_nsu_nfe / ultimo_nsu_cte: NSU a partir do qual buscar
                (use o `lote.ultimo_nsu_*` da execução anterior).
            data_inicial / data_final: filtra documentos por `dhEmi`
                após o download (a SEFAZ não filtra por data). Se None,
                não filtra.
            incluir_nfse: se False, pula o ADN (útil quando o município
                não é aderente).
            max_documentos: corta cada tipo após N documentos. 0 = sem limite.
        """
        lote = LoteDownload()
        lote.nfe = self._buscar_nfe(
            ultimo_nsu_nfe, data_inicial, data_final, max_documentos, timeout, lote
        )
        lote.cte = self._buscar_cte(
            ultimo_nsu_cte, data_inicial, data_final, max_documentos, timeout, lote
        )
        if incluir_nfse and data_inicial and data_final:
            lote.nfse = self._buscar_nfse(data_inicial, data_final, max_documentos, timeout)
        return lote

    # -- Implementação ---------------------------------------------------

    def _buscar_nfe(
        self,
        ultimo_nsu: str,
        data_inicial: Optional[date],
        data_final: Optional[date],
        max_documentos: int,
        timeout: int,
        lote: LoteDownload,
    ) -> List[XmlBaixado]:
        log.info("BuscadorXMLs.NFe ultNSU=%s", ultimo_nsu)
        documentos: List[DocumentoXML] = []
        for pagina in cliente_nfe.consultar(
            self.certificado,
            self.cnpj,
            uf_autor=self.uf_autor,
            ambiente=self.ambiente,
            nsu_inicial=ultimo_nsu,
            timeout=timeout,
        ):
            documentos.extend(pagina.documentos)
            if pagina.ultimo_nsu and pagina.ultimo_nsu != "0":
                lote.ultimo_nsu_nfe = pagina.ultimo_nsu
            if pagina.max_nsu and pagina.max_nsu != "0":
                lote.max_nsu_nfe = pagina.max_nsu
            if max_documentos and len(documentos) >= max_documentos:
                log.info("NFe: limite de %d atingido.", max_documentos)
                break
        if data_inicial and data_final:
            documentos = filtrar_por_data(documentos, data_inicial, data_final)
        if max_documentos:
            documentos = documentos[:max_documentos]
        return [_doc_para_xml_baixado(d, "nfe") for d in documentos]

    def _buscar_cte(
        self,
        ultimo_nsu: str,
        data_inicial: Optional[date],
        data_final: Optional[date],
        max_documentos: int,
        timeout: int,
        lote: LoteDownload,
    ) -> List[XmlBaixado]:
        log.info("BuscadorXMLs.CTe ultNSU=%s", ultimo_nsu)
        documentos: List[DocumentoXML] = []
        for pagina in cliente_cte.consultar(
            self.certificado,
            self.cnpj,
            uf_autor=self.uf_autor,
            ambiente=self.ambiente,
            nsu_inicial=ultimo_nsu,
            timeout=timeout,
        ):
            documentos.extend(pagina.documentos)
            if pagina.ultimo_nsu and pagina.ultimo_nsu != "0":
                lote.ultimo_nsu_cte = pagina.ultimo_nsu
            if pagina.max_nsu and pagina.max_nsu != "0":
                lote.max_nsu_cte = pagina.max_nsu
            if max_documentos and len(documentos) >= max_documentos:
                log.info("CTe: limite de %d atingido.", max_documentos)
                break
        if data_inicial and data_final:
            documentos = filtrar_por_data(documentos, data_inicial, data_final)
        if max_documentos:
            documentos = documentos[:max_documentos]
        return [_doc_para_xml_baixado(d, "cte") for d in documentos]

    def _buscar_nfse(
        self,
        data_inicial: date,
        data_final: date,
        max_documentos: int,
        timeout: int,
    ) -> List[XmlBaixado]:
        log.info(
            "BuscadorXMLs.NFSe periodo=[%s..%s]",
            data_inicial.isoformat(),
            data_final.isoformat(),
        )
        try:
            nfses = cliente_nfse.baixar_periodo(
                self.certificado,
                self.cnpj,
                data_inicial,
                data_final,
                ambiente=self.ambiente,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "ADN indisponível ou município não aderente ao Sistema Nacional NFS-e: %s",
                exc,
            )
            return []
        if max_documentos:
            nfses = nfses[:max_documentos]
        return [
            XmlBaixado(
                tipo="nfse",
                nsu="",  # ADN não devolve NSU; cursor é pela data
                xml=n.xml,
                chave=n.chave_acesso,
            )
            for n in nfses
        ]
