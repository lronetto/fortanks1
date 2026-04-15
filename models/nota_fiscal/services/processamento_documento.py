"""Processamento de documentos fiscais (CT-e, NF-e, NFSe) após extração do XML."""
import base64
import json
import logging
import xml.etree.ElementTree as ET

from flask_login import current_user

from models.database import db
from models.nota_fiscal.parsing.xml_extracao import (
    extrair_dados_xml_cte,
    extrair_dados_xml_nfe,
    extrair_dados_xml_nfse,
)

logger = logging.getLogger(__name__)


def executar_processamento_cte(nota):
    from models.fornecedor import Fornecedor
    from models.nota_fiscal.entities import NotaFiscal

    logger.debug("processar_cte inicio")
    chave_acesso, dados = extrair_dados_xml_cte(nota.xml_data)
    if not chave_acesso or not dados:
        try:
            root = ET.fromstring(base64.b64decode(nota.xml_data).decode("utf-8"))
            tag = root.tag if hasattr(root, "tag") else ""
            if "nfeProc" in tag or (
                root.find(".//{http://www.portalfiscal.inf.br/nfe}infNFe") is not None
            ) or (root.find(".//infNFe") is not None):
                logger.info("Documento importado como CTe é na verdade NFe; processando como NFe.")
                nota.tipo = "nfe"
                return executar_processamento_nfe(nota)
        except Exception as e:
            logger.debug("Verificação de redirecionamento NFe/CTe: %s", e)
        nota.logs["erro"].append("XML não é um CTe válido (infCte não encontrado).")
        return False
    cnpj_emitente = dados.get("dados_adicionais", {}).get("emitente", {}).get("cnpj", "")
    nome_emitente = dados.get("dados_adicionais", {}).get("emitente", {}).get("nome", "")
    uf = dados.get("dados_adicionais", {}).get("emitente", {}).get("uf", "")
    Fornecedor(nome=nome_emitente, cnpj=cnpj_emitente, estado=uf)
    existente = NotaFiscal.query.filter_by(chave_acesso=chave_acesso).first()
    if existente:
        nota.logs["existente"] += 1
        nota.logs["existentes"].append(
            {
                "numero_nf": existente.numero_nf,
                "tipo": "cte",
                "valor_total": existente.valor_total,
                "cnpj_emitente": existente.cnpj_emitente,
                "nome_emitente": existente.nome_emitente,
                "cnpj_destinatario": existente.cnpj_destinatario,
                "nome_destinatario": existente.nome_destinatario,
                "dados_adicionais": existente.dados_adicionais,
            }
        )
        if not existente.dados_adicionais:
            existente.dados_adicionais = json.dumps(
                dados.get("dados_adicionais") or {}, ensure_ascii=False
            )
            existente.save()
        return existente
    try:
        nota.tipo = 2
        nota.xml_data = nota.data.get("xml", None)
        nota.numero_nf = dados.get("numero_cte")
        nota.chave_acesso = dados.get("chave_acesso")
        nota.data_emissao = dados.get("data_emissao")
        nota.valor_total = dados.get("valor_total")
        nota.cnpj_emitente = dados.get("cnpj_emitente")
        nota.nome_emitente = dados.get("nome_emitente")
        nota.cnpj_destinatario = dados.get("cnpj_destinatario")
        nota.nome_destinatario = dados.get("nome_destinatario")
        nota.status_processamento = "importado"
        nota.dados_adicionais = json.dumps(dados.get("dados_adicionais"), ensure_ascii=False)
        nota.save()
        db.session.refresh(nota)
        db.session.commit()
        nota.logs["inserido"] += 1
        nota.logs["inseridos"].append(nota.to_dict())
    except Exception as e:
        logger.error("Erro ao processar CT-e: %s", str(e))
        nota.logs["erro"] = str(e)
        return False
    return None


def executar_processamento_nfse(nota):
    from models.fornecedor import Fornecedor
    from models.nota_fiscal.entities import NotaFiscal

    logger.debug("processar_nfse inicio")
    chave_acesso, dados = extrair_dados_xml_nfse(nota.xml_data)
    logger.debug("chave_acesso nfse: %s", chave_acesso)
    if not chave_acesso or not dados:
        logger.warning("processar_nfse: extração retornou chave ou dados vazios")
        return False
    cnpj_emitente = dados.get("cnpj_emitente")
    nome_emitente = dados.get("nome_emitente")
    uf = dados.get("dados_adicionais", {}).get("emitente", {}).get("uf", "")
    Fornecedor(nome=nome_emitente, cnpj=cnpj_emitente, estado=uf)
    try:
        existente = NotaFiscal.query.filter_by(chave_acesso=chave_acesso).first()
        if existente:
            if not existente.dados_adicionais:
                existente.dados_adicionais = json.dumps(
                    dados.get("dados_adicionais") or {}, ensure_ascii=False
                )
                existente.save()
            return existente
    except Exception:
        return False

    dados_adicionais = dados.get("dados_adicionais") or {}
    try:
        if dados_adicionais.get("cancelada"):
            nota.status_processamento = "cancelada"
        else:
            nota.status_processamento = "importado"
        nota.tipo = 3
        nota.xml_data = base64.b64encode(nota.xml_data.encode("utf-8")).decode("utf-8")
        nota.numero_nf = dados.get("Numero")
        nota.chave_acesso = chave_acesso
        nota.data_emissao = dados.get("DataEmissao")
        nota.valor_total = (dados.get("valores") or {}).get("ValorLiquidoNfse") or "0"
        nota.cnpj_emitente = dados.get("cnpj_emitente")
        nota.nome_emitente = dados.get("nome_emitente")
        nota.cnpj_destinatario = dados.get("cnpj_destinatario")
        nota.nome_destinatario = dados.get("nome_destinatario")
        nota.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)
    except Exception as e:
        logger.error("processar_nfse [atribuir campos]: %s", e, exc_info=True)
        return False

    try:
        nota.save()
        db.session.commit()
        db.session.refresh(nota)
    except Exception as e:
        logger.error("processar_nfse [save/refresh]: %s", e, exc_info=True)
        return False

    try:
        pass
    except Exception as e:
        logger.error("processar_nfse [to_dict/inserido]: %s", e, exc_info=True)
        return False
    return None


def executar_processamento_nfe(nota):
    from models.fornecedor import Fornecedor
    from models.nota_fiscal.entities import NotaFiscal, NotaFiscalItem

    logger.debug("processar_nfe inicio")
    try:
        chave_acesso, dados_nf = extrair_dados_xml_nfe(nota.xml_data)
        if not chave_acesso or not dados_nf:
            logger.warning("Não foi possível extrair dados do XML")
            nota.logs["erro"] = "Não foi possível extrair dados do XML"
            return False
        nota.chave_acesso = chave_acesso

        cnpj_emitente = dados_nf.get("cnpj_emitente")
        nome_emitente = dados_nf.get("nome_emitente")
        uf = dados_nf.get("dados_adicionais", {}).get("emitente", {}).get("uf", "")
        Fornecedor(nome=nome_emitente, cnpj=cnpj_emitente, estado=uf)
        nf = NotaFiscal.query.filter_by(chave_acesso=chave_acesso).first()

        if nf:
            nota.logs["existente"] += 1
            nota.logs["existentes"].append(
                {
                    "numero_nf": nf.numero_nf,
                    "tipo": nf.tipo,
                    "valor_total": nf.valor_total,
                    "dados_adicionais": nf.dados_adicionais,
                }
            )
            logger.info("Nota %s já existe no banco de dados", chave_acesso)
            if not nf.dados_adicionais:
                nota.logs["mensagem"] = "Dados adicionais não encontrados adicionando"
                nf.dados_adicionais = json.dumps(
                    dados_nf.get("dados_adicionais"), ensure_ascii=False
                )
                nf.save()
            return nf
        if not nota.xml_data:
            nota.xml_data = nota.data.get("xml", None)
        nota.numero_nf = dados_nf.get("numero")
        nota.tipo = dados_nf.get("tipo")
        nota.chave_acesso = chave_acesso
        nota.data_emissao = dados_nf.get("data_emissao")
        nota.valor_total = dados_nf.get("valor_total")
        nota.cnpj_emitente = dados_nf.get("cnpj_emitente")
        nota.nome_emitente = dados_nf.get("nome_emitente")
        nota.cnpj_destinatario = dados_nf.get("cnpj_destinatario")
        nota.nome_destinatario = dados_nf.get("nome_destinatario")
        nota.status_processamento = "importado"
        nota.dados_adicionais = json.dumps(dados_nf.get("dados_adicionais"), ensure_ascii=False)
        nota.save()
        for item_nf in dados_nf.get("itens", []):
            item_fiscal = NotaFiscalItem(
                nf_id=nota.id,
                codigo=item_nf.get("codigo"),
                descricao=item_nf.get("descricao"),
                quantidade=item_nf.get("quantidade"),
                valor_unitario=item_nf.get("valor_unitario"),
                valor_total=item_nf.get("valor_total"),
                ncm=item_nf.get("ncm"),
                cfop=item_nf.get("cfop"),
                unidade=item_nf.get("unidade"),
                dados_adicionais=json.dumps(item_nf.get("dados_adicionais"), ensure_ascii=False),
            )
            item_fiscal.save()
        nota.vincular_automaticamente()
        db.session.commit()
        db.session.refresh(nota)
        for item in nota.itens:
            try:
                sucesso, mensagem, estatisticas = item.vincular_e_importar_estoque_todos(
                    usuario_id=current_user.id if current_user else None,
                    centro_custo_id=None,
                    observacao=f"Importação da NF {nota.numero_nf if nota else 'N/A'}",
                )
                nota.logs["vinculacao"].append(estatisticas["vinculacao"])
                nota.logs["importacao"].append(estatisticas["importacao"])
            except Exception as e:
                import traceback

                traceback.print_exc()
                logger.error("Erro ao vincular e importar item %s: %s", item.id, str(e))
                nota.logs["erro"].append(
                    f"Erro ao vincular e importar item {item.id}: {str(e)}"
                )

        nota.logs["inserido"] += 1
        nota.logs["inseridos"].append(
            {
                "id": nota.id,
                "numero_nf": nota.numero_nf,
                "tipo": nota.tipo,
                "valor_total": nota.valor_total,
                "dados_adicionais": nota.dados_adicionais,
            }
        )
        logger.debug("processar_nfe finalizado")
    except Exception as e:
        logger.error("Erro ao processar nota fiscal: %s", str(e))
        nota.logs["erro"].append(str(e))
        return False
    return None
