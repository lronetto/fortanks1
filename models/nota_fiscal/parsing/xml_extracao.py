"""Extração de dados fiscais a partir de XML (CT-e, NF-e, NFS-e).

Gerado a partir da lógica que estava em `entities.NotaFiscal`; mantém o mesmo comportamento.
"""
import base64
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal

import xmltodict

from ..xml_utils import _parse_nfe_data_emissao_xml, get_xml_text

logger = logging.getLogger(__name__)

def _first_not_none(*values):
        for value in values:
            if value is not None:
                return value
        return None

def extrair_dados_xml_cte(xml_data: str):
        root = ET.fromstring(base64.b64decode(xml_data).decode('utf-8'))
        ns = {'cte': 'http://www.portalfiscal.inf.br/cte'}
        infCte = _first_not_none(
            root.find('.//cte:infCte', ns),
            root.find('.//infCte', ns),
        )
        if infCte is None:
            logger.warning("extrair_dados_xml_cte: XML não contém infCte (pode ser NFe ou formato inválido)")
            return None, None
        emit = _first_not_none(infCte.find('.//cte:emit', ns), infCte.find('.//emit', ns))
        dest = _first_not_none(infCte.find('.//cte:dest', ns), infCte.find('.//dest', ns))
        rem = _first_not_none(infCte.find('.//cte:rem', ns), infCte.find('.//rem', ns))
        ide = _first_not_none(infCte.find('.//cte:ide', ns), infCte.find('.//ide', ns))
        vPrest = _first_not_none(infCte.find('.//cte:vPrest', ns), infCte.find('.//vPrest', ns))
        compl = _first_not_none(infCte.find('.//cte:compl', ns), infCte.find('.//compl', ns))
        imp = _first_not_none(infCte.find('.//cte:imp', ns), infCte.find('.//imp', ns))
        infCTeNorm = _first_not_none(
            infCte.find('.//cte:infCTeNorm', ns),
            infCte.find('.//infCTeNorm', ns),
        )
        chave_nf = ''
        if infCTeNorm is not None:
            infDoc = _first_not_none(
                infCTeNorm.find('.//cte:infDoc', ns),
                infCTeNorm.find('.//infDoc', ns),
            )
            if infDoc is not None:
                infNFe = _first_not_none(
                    infDoc.find('.//cte:infNFe', ns),
                    infDoc.find('.//infNFe', ns),
                )
                if infNFe is not None:
                    chave_nf = infNFe.findtext('.//cte:chave', default='', namespaces=ns)
                    
        
        impostos = {}
        if imp is not None:
            ICMSa = _first_not_none(
                imp.find('.//cte:ICMS', ns),
                imp.find('.//ICMS', ns),
                imp.find('.//ICMS00', ns),
            )
            if ICMSa is not None:
                ICMSOutraUF = ICMSa.find('.//cte:ICMSOutraUF', ns)
                if ICMSOutraUF is not None:
                    CSTv = ICMSOutraUF.findtext('.//cte:CST', default='0', namespaces=ns)
                    vBCOutraUF = ICMSOutraUF.findtext('.//cte:vBCOutraUF', default='0', namespaces=ns)
                    pICMSOutraUF = ICMSOutraUF.findtext('.//cte:pICMSOutraUF', default='0', namespaces=ns)
                    vICMSOutraUF = ICMSOutraUF.findtext('.//cte:vICMSOutraUF', default='0', namespaces=ns)
                    impostos = {
                        'CST': CSTv,
                        'vBC': vBCOutraUF,
                        'pICMS': pICMSOutraUF,
                        'vICMS': vICMSOutraUF
                    }
                ICMS00 = _first_not_none(
                    ICMSa.find('.//cte:ICMS00', ns),
                    ICMSa.find('.//ICMS00', ns),
                )
                if ICMS00 is not None:
                    CSTv = ICMS00.findtext('.//cte:CST', default='0', namespaces=ns)
                    vBC = ICMS00.findtext('.//cte:vBC', default='0', namespaces=ns)
                    pICMS = ICMS00.findtext('.//cte:pICMS', default='0', namespaces=ns)
                    vICMS = ICMS00.findtext('.//cte:vICMS', default='0', namespaces=ns)
                    impostos = {
                        'CST': CSTv,
                        'vBC': vBC,
                        'pICMS': pICMS,
                        'vICMS': vICMS
                    }
        infModal = _first_not_none(
            infCte.find('.//cte:infModal', ns),
            infCte.find('.//infModal', ns),
        )
        rodo = infModal.find('.//cte:rodo', ns) if infModal is not None else None

        # Chave de acesso
        chave_acesso = infCte.attrib.get('Id', '') or infCte.attrib.get('id', '')
        if chave_acesso.startswith('CTe'):
            chave_acesso = chave_acesso[3:]

        numero_cte = ide.findtext('cte:nCT', default='', namespaces=ns)

        # Emitente
        cnpj_emitente = emit.findtext('cte:CNPJ', default='', namespaces=ns)
        nome_emitente = emit.findtext('cte:xNome', default='', namespaces=ns)

        # Destinatário
        cnpj_destinatario = dest.findtext('cte:CNPJ', default='', namespaces=ns)
        nome_destinatario = dest.findtext('cte:xNome', default='', namespaces=ns)

        # Valor total
        valor_total = vPrest.findtext('cte:vTPrest', default='0', namespaces=ns)
        valor_total = float(valor_total.replace(',', '.'))

        # Data de emissão
        data_emissao = ide.findtext('cte:dhEmi', default='', namespaces=ns)
        try:
            data_emissao = _parse_nfe_data_emissao_xml(data_emissao)
        except (ValueError, TypeError) as e:
            logger.error("Data de emissão inválida no XML: %r (%s)", data_emissao, e)
            return chave_acesso, None

        # Origem e destino
        municipio_inicio = ide.findtext('cte:xMunIni', default='', namespaces=ns)
        uf_inicio = ide.findtext('cte:UFIni', default='', namespaces=ns)
        municipio_destino = ide.findtext('cte:xMunFim', default='', namespaces=ns)
        uf_destino = ide.findtext('cte:UFFim', default='', namespaces=ns)
        # Placa e motorista
        placa = ''
        motorista = ''
        if compl is not None:
            xObs = compl.findtext('cte:xObs', default='', namespaces=ns)
            if xObs:
                placa_match = re.search(r'PLACA ([A-Z0-9])', xObs)
                if placa_match:
                    placa = placa_match.group(1)
                motorista_match = re.search(r'MOTORISTA ([A-Z .A-Z]+), CPF', xObs)
                if motorista_match:
                    motorista = motorista_match.group(1)
        # fallback para placa no modal rodo
        if not placa and rodo is not None:
            placa = rodo.findtext('cte:placa', default='', namespaces=ns)
        # fallback para motorista (nome pode estar no xObs)
        if not motorista and compl is not None and xObs:
            import re
            motorista_match = re.search(r'MOTORISTA ([A-Z .A-Z]+), CPF', xObs)
            if motorista_match:
                motorista = motorista_match.group(1)
        dados_adicionais = {
            'emitente': {
                'nome': emit.findtext('cte:xNome', default='', namespaces=ns),
                'cnpj': emit.findtext('cte:CNPJ', default='', namespaces=ns),
                'endereco': emit.findtext('cte:xLgr', default='', namespaces=ns),
                'municipio': emit.findtext('cte:xMun', default='', namespaces=ns),
                'uf': emit.findtext('cte:UF', default='', namespaces=ns)
            },
            'remetente': {
                'nome': rem.findtext('cte:xNome', default='', namespaces=ns),
                'cnpj': rem.findtext('cte:CNPJ', default='', namespaces=ns),
                'endereco': rem.findtext('cte:xLgr', default='', namespaces=ns),
                'municipio': rem.findtext('cte:xMun', default='', namespaces=ns),
                'uf': rem.findtext('cte:UF', default='', namespaces=ns)
            },
            'municipio_inicio': municipio_inicio,
            'uf_inicio': uf_inicio,
            'municipio_destino': municipio_destino,
            'uf_destino': uf_destino,
            'placa': placa,
            'motorista': motorista,
            'chave_nf': chave_nf,
            'impostos': impostos
        }
        dados_nf = {
            'chave_acesso': chave_acesso,
            'numero_cte': numero_cte,
            'cnpj_emitente': cnpj_emitente,
            'nome_emitente': nome_emitente,
            'cnpj_destinatario': cnpj_destinatario,
            'nome_destinatario': nome_destinatario,
            'valor_total': valor_total,
            'data_emissao': data_emissao,
            'dados_adicionais': dados_adicionais,
        }
        return chave_acesso, dados_nf     
def extrair_dados_xml_nfe(xml_data: str):
        """
        Extrai os dados de uma nota fiscal a partir do XML
        Retorna a chave de acesso e um dicionário com os dados da nota fiscal
        """
        try:
            # Parse do XML
            root = ET.fromstring(base64.b64decode(xml_data).decode('utf-8'))
            
            # Definir os namespaces
            ns = {
                'nfe': 'http://www.portalfiscal.inf.br/nfe'
            }
            
            # Extrair dados da nota
            inf_nfe = _first_not_none(
                root.find('.//nfe:infNFe', ns),
                root.find('.//infNFe', ns),
            )
            if inf_nfe is None:
                # Tentar com outro namespace
                ns = {'': 'http://www.portalfiscal.inf.br/nfe'}
                inf_nfe = root.find('.//infNFe', ns)
                if inf_nfe is None:
                    logger.error("Não foi possível encontrar os dados da nota fiscal no XML")
                    return None, None
            
            # Extrair a chave de acesso
            chave_acesso = inf_nfe.attrib.get('Id', '')
            if chave_acesso.startswith('NFe'):
                chave_acesso = chave_acesso[3:]  # Remove o prefixo 'NFe'
            
            # Extrair dados essenciais
            ide = _first_not_none(inf_nfe.find('.//nfe:ide', ns), inf_nfe.find('.//ide', ns))
            emit = _first_not_none(inf_nfe.find('.//nfe:emit', ns), inf_nfe.find('.//emit', ns))
            dest = _first_not_none(inf_nfe.find('.//nfe:dest', ns), inf_nfe.find('.//dest', ns))
            total = _first_not_none(
                inf_nfe.find('.//nfe:total/nfe:ICMSTot', ns),
                inf_nfe.find('.//total/ICMSTot', ns),
            )
            itens = inf_nfe.findall('.//nfe:det', ns) or inf_nfe.findall('.//det', ns)
            cobr = _first_not_none(inf_nfe.find('.//nfe:cobr', ns), inf_nfe.find('.//cobr', ns))
            total = _first_not_none(inf_nfe.find('.//nfe:total', ns), inf_nfe.find('.//total', ns))
            if ide is None or emit is None or dest is None or total is None:
                logger.error("Dados essenciais ausentes no XML da NFe")
                return chave_acesso, None
            ICMSTot = _first_not_none(total.find('.//nfe:ICMSTot', ns), total.find('.//ICMSTot', ns))
            if ICMSTot is None:
                logger.error("Totais de impostos ausentes no XML da NFe")
                return chave_acesso, None
            vIPI = ICMSTot.findtext('.//nfe:vIPI', default='0', namespaces=ns) or ICMSTot.findtext('.//vIPI', default='0', namespaces=ns)
            vPIS = ICMSTot.findtext('.//nfe:vPIS', default='0', namespaces=ns) or ICMSTot.findtext('.//vPIS', default='0', namespaces=ns)
            vCOFINS = ICMSTot.findtext('.//nfe:vCOFINS', default='0', namespaces=ns) or ICMSTot.findtext('.//vCOFINS', default='0', namespaces=ns)
            vICMS = ICMSTot.findtext('.//nfe:vICMS', default='0', namespaces=ns) or ICMSTot.findtext('.//vICMS', default='0', namespaces=ns)

            impostos = {
                'vIPI': vIPI,
                'vPIS': vPIS,
                'vCOFINS': vCOFINS,
                'vICMS': vICMS,
            }
            if cobr is not None:
                #print(f'cobr: {cobr}')
                fatura = _first_not_none(cobr.find('.//nfe:fat', ns), cobr.find('.//fat', ns))
                #print(f'fatura: {fatura}')
                dup = _first_not_none(cobr.find('.//nfe:dup', ns), cobr.find('.//dup', ns))
                #print(f'dup: {dup}')
            
            # Extrair número da nota
            numero = get_xml_text(ide, './/nfe:nNF', ns) or get_xml_text(ide, './/nNF', ns)
            tipo = get_xml_text(ide, './/nfe:tpNF', ns) or get_xml_text(ide, './/tpNF', ns)
            # Extrair data de emissão
            data_emissao_text = get_xml_text(ide, './/nfe:dhEmi', ns) or get_xml_text(ide, './/dhEmi', ns) or get_xml_text(ide, './/dEmi', ns)
            if not data_emissao_text:
                logger.error("Data de emissão não encontrada no XML")
                return chave_acesso, None
            try:
                data_emissao = _parse_nfe_data_emissao_xml(data_emissao_text)
            except (ValueError, TypeError) as e:
                logger.error("Data de emissão inválida no XML: %r (%s)", data_emissao_text, e)
                return chave_acesso, None

            # Extrair CNPJ emitente
            cnpj_emitente = get_xml_text(emit, './/nfe:CNPJ', ns) or get_xml_text(emit, './/CNPJ', ns)
            nome_emitente = get_xml_text(emit, './/nfe:xNome', ns) or get_xml_text(emit, './/xNome', ns)
            uf = get_xml_text(emit, './/nfe:UF', ns) or get_xml_text(emit, './/UF', ns) or ''
            # Extrair CNPJ destinatário
            cnpj_destinatario = get_xml_text(dest, './/nfe:CNPJ', ns) or get_xml_text(dest, './/CNPJ', ns) or ''
            if not cnpj_destinatario:
                # Tentar CPF
                cnpj_destinatario = get_xml_text(dest, './/nfe:CPF', ns) or get_xml_text(dest, './/CPF', ns) or ''
                
            nome_destinatario = get_xml_text(dest, './/nfe:xNome', ns) or get_xml_text(dest, './/xNome', ns) or 'Consumidor'
            
            # Extrair valor total
            valor_total_text = get_xml_text(total, './/nfe:vNF', ns) or get_xml_text(total, './/vNF', ns)
            if not valor_total_text:
                logger.error("Valor total não encontrado no XML")
                return chave_acesso, None
                
            valor_total = Decimal(valor_total_text)
            
            dados_adicionais = {
                'emitente': {
                    'nome': nome_emitente,
                    'cnpj': cnpj_emitente,
                    'uf': uf,
                },
                'fatura': {
                    'vencimento': None,
                    'numero_fatura': None,
                    'valor_total': None
                },
                'impostos': impostos
            }
            # Dados básicos da nota
            nfe_data = {
                'numero': numero,
                'tipo': tipo,
                'data_emissao': data_emissao,
                'cnpj_emitente': cnpj_emitente,
                'nome_emitente': nome_emitente,
                'cnpj_destinatario': cnpj_destinatario,
                'nome_destinatario': nome_destinatario,
                'valor_total': valor_total,
                'itens': [],
                'dados_adicionais': dados_adicionais,
            }
            
            if cobr and dup:
                vencimento = get_xml_text(dup, './/nfe:dVenc', ns) or get_xml_text(dup, './/dVenc', ns)
                if vencimento:
                    vencimento = datetime.strptime(vencimento, '%Y-%m-%d')
                    # Converter para string para serialização JSON
                    vencimento_str = vencimento.strftime('%Y-%m-%d')
                else:
                    vencimento = None
                    vencimento_str = None
                #print(f'vencimento: {vencimento}')
                if fatura:
                    #print(f'fatura: {fatura}')
                    numero_fatura = get_xml_text(fatura, './/nfe:nFat', ns) or get_xml_text(fatura, './/nFat', ns)
                    valor_total = get_xml_text(fatura, './/nfe:vOrig', ns) or get_xml_text(fatura, './/vOrig', ns)
                    valor_total = Decimal(valor_total)
                    nfe_data['dados_adicionais']['fatura'] = {
                        'vencimento': vencimento_str,  # Salvar como string para serialização JSON
                        'numero_fatura': numero_fatura,
                        'valor_total': str(valor_total)  # Converter Decimal para string também
                    }

            # Extrair dados dos itens
            for item in itens:
                try:
                    num_item = item.attrib.get('nItem', '0')
                    prod = _first_not_none(item.find('.//nfe:prod', ns), item.find('.//prod', ns))

                    infAdProd = _first_not_none(item.find('.//nfe:infAdProd', ns), item.find('.//infAdProd', ns))

                    
                    if prod is None:
                        logger.warning(f"Produto não encontrado para o item {num_item}")
                        continue
                    
                    codigo = get_xml_text(prod, './/nfe:cProd', ns) or get_xml_text(prod, './/cProd', ns) or ''
                    descricao = get_xml_text(prod, './/nfe:xProd', ns) or get_xml_text(prod, './/xProd', ns) or 'Sem descrição'
                    
                    quantidade_text = get_xml_text(prod, './/nfe:qCom', ns) or get_xml_text(prod, './/qCom', ns) or '0'
                    valor_unitario_text = get_xml_text(prod, './/nfe:vUnCom', ns) or get_xml_text(prod, './/vUnCom', ns) or '0'
                    valor_total_item_text = get_xml_text(prod, './/nfe:vProd', ns) or get_xml_text(prod, './/vProd', ns) or '0'
                    
                    ncm = get_xml_text(prod, './/nfe:NCM', ns) or get_xml_text(prod, './/NCM', ns) or ''
                    cfop = get_xml_text(prod, './/nfe:CFOP', ns) or get_xml_text(prod, './/CFOP', ns) or ''
                    unidade = get_xml_text(prod, './/nfe:uCom', ns) or get_xml_text(prod, './/uCom', ns) or 'UN'
                    xPed = get_xml_text(prod, './/nfe:xPed', ns) or get_xml_text(prod, './/xPed', ns) or ''
                    nItemPed = get_xml_text(prod, './/nfe:nItemPed', ns) or get_xml_text(prod, './/nItemPed', ns) or ''
                    impostos = _first_not_none(item.find('.//nfe:imposto', ns), item.find('.//imposto', ns))
                    ICMS = _first_not_none(impostos.find('.//nfe:ICMS', ns), impostos.find('.//ICMS', ns))
                    if ICMS is not None:
                        ICMS60 = _first_not_none(ICMS.find('.//nfe:ICMS60', ns), ICMS.find('.//ICMS60', ns))
                    else:
                        ICMS60 = None
                    IPI = _first_not_none(impostos.find('.//nfe:IPI', ns), impostos.find('.//IPI', ns))
                    if IPI is not None:
                        IPITrib = _first_not_none(IPI.find('.//nfe:IPITrib', ns), IPI.find('.//IPITrib', ns))
                    else:
                        IPITrib = None
                    PIS = _first_not_none(impostos.find('.//nfe:PIS', ns), impostos.find('.//PIS', ns))
                    if PIS is not None:
                        PISAliq = _first_not_none(PIS.find('.//nfe:PISAliq', ns), PIS.find('.//PISAliq', ns))
                    else:
                        PISAliq = None
                    COFINS = _first_not_none(impostos.find('.//nfe:COFINS', ns), impostos.find('.//COFINS', ns))
                    if COFINS is not None:
                        COFINSAliq = _first_not_none(COFINS.find('.//nfe:COFINSAliq', ns), COFINS.find('.//COFINSAliq', ns))
                    else:
                        COFINSAliq = None
                    
                    impostos = {
                        'ICMS': {
                            'CST': ICMS60.findtext('.//nfe:CST', default='0', namespaces=ns) or ICMS60.findtext('.//CST', default='0', namespaces=ns) if ICMS60 is not None else None,
                            'vBCSTRet': ICMS60.findtext('.//nfe:vBCSTRet', default='0', namespaces=ns) or ICMS60.findtext('.//vBCSTRet', default='0', namespaces=ns) if ICMS60 is not None else None,
                            'pST': ICMS60.findtext('.//nfe:pST', default='0', namespaces=ns) or ICMS60.findtext('.//pST', default='0', namespaces=ns) if ICMS60 is not None else None,
                            'vICMSSTRet': ICMS60.findtext('.//nfe:vICMSSTRet', default='0', namespaces=ns) or ICMS60.findtext('.//vICMSSTRet', default='0', namespaces=ns) if ICMS60 is not None else None,
                            'vICMSSubstituto': ICMS60.findtext('.//nfe:vICMSSubstituto', default='0', namespaces=ns) or ICMS60.findtext('.//vICMSSubstituto', default='0', namespaces=ns) if ICMS60 is not None else None,
                        },
                        'IPI': {
                            'CST': IPITrib.findtext('.//nfe:CST', default='0', namespaces=ns) or IPITrib.findtext('.//CST', default='0', namespaces=ns) if IPITrib is not None else None,
                            'vBC': IPITrib.findtext('.//nfe:vBC', default='0', namespaces=ns) or IPITrib.findtext('.//vBC', default='0', namespaces=ns) if IPITrib is not None else None,
                            'pIPI': IPITrib.findtext('.//nfe:pIPI', default='0', namespaces=ns) or IPITrib.findtext('.//pIPI', default='0', namespaces=ns) if IPITrib is not None else None,
                            'vIPI': IPITrib.findtext('.//nfe:vIPI', default='0', namespaces=ns) or IPITrib.findtext('.//vIPI', default='0', namespaces=ns) if IPITrib is not None else None,
                        },
                        'PIS': {
                            'CST': PISAliq.findtext('.//nfe:CST', default='0', namespaces=ns) or PISAliq.findtext('.//CST', default='0', namespaces=ns) if PISAliq is not None else None,
                            'vBC': PISAliq.findtext('.//nfe:vBC', default='0', namespaces=ns) or PISAliq.findtext('.//vBC', default='0', namespaces=ns) if PISAliq is not None else None,
                            'pPIS': PISAliq.findtext('.//nfe:pPIS', default='0', namespaces=ns) or PISAliq.findtext('.//pPIS', default='0', namespaces=ns) if PISAliq is not None else None,
                            'vPIS': PISAliq.findtext('.//nfe:vPIS', default='0', namespaces=ns) or PISAliq.findtext('.//vPIS', default='0', namespaces=ns) if PISAliq is not None else None,
                        },
                        'COFINS': {
                            'CST': COFINSAliq.findtext('.//nfe:CST', default='0', namespaces=ns) or COFINSAliq.findtext('.//CST', default='0', namespaces=ns) if COFINSAliq is not None else None,
                            'vBC': COFINSAliq.findtext('.//nfe:vBC', default='0', namespaces=ns) or COFINSAliq.findtext('.//vBC', default='0', namespaces=ns) if COFINSAliq is not None else None,
                            'pCOFINS': COFINSAliq.findtext('.//nfe:pCOFINS', default='0', namespaces=ns) or COFINSAliq.findtext('.//pCOFINS', default='0', namespaces=ns) if COFINSAliq is not None else None,
                            'vCOFINS': COFINSAliq.findtext('.//nfe:vCOFINS', default='0', namespaces=ns) or COFINSAliq.findtext('.//vCOFINS', default='0', namespaces=ns) if COFINSAliq is not None else None,
                        },
                    }
                    item_data = {
                        'codigo': codigo,
                        'descricao': descricao,
                        'quantidade': Decimal(quantidade_text),
                        'valor_unitario': Decimal(valor_unitario_text),
                        'valor_total': Decimal(valor_total_item_text),
                        'ncm': ncm,
                        'cfop': cfop,
                        'unidade': unidade,
                        'dados_adicionais':{
                            'xPed': xPed,
                            'nItemPed': nItemPed,
                            'infAdProd': infAdProd,
                            'impostos': impostos
                            }
                        }
                    
                    nfe_data['itens'].append(item_data)
                except Exception as e:
                    logger.error(f"Erro ao processar item {num_item}: {str(e)}")
            
            return chave_acesso, nfe_data
        
        except Exception as e:
            logger.error(f"Erro ao extrair dados do XML: {str(e)}")
            return None, None
def _nfse_dict_get(obj, *path):
        """Obtém valor aninhado em dict do xmltodict, suportando chaves com namespace e listas de 1 elemento."""
        for key in path:
            if obj is None or not isinstance(obj, dict):
                return None
            val = obj.get(key)
            if val is None and isinstance(obj, dict):
                for k, v in obj.items():
                    if k == key or (k.startswith('{') and k.endswith('}' + key)):
                        val = v
                        break
            if val is not None and isinstance(val, list) and len(val) == 1:
                val = val[0]
            obj = val
        return obj

def _nfse_text(val):
        """Extrai texto de valor do xmltodict (string, dict com #text ou atributo @id)."""
        if val is None:
            return ''
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, dict):
            return (val.get('#text') or val.get('@Id') or '').strip() if isinstance(val.get('#text') or val.get('@Id'), str) else ''
        return str(val).strip() if val else ''

def _nfse_val(d, key):
        """Obtém valor de d por key ou por chave com namespace (ex.: {uri}key)."""
        if not d or not isinstance(d, dict):
            return None
        if d.get(key) is not None:
            return d.get(key)
        for k, v in d.items():
            if isinstance(k, str) and (k == key or k.endswith('}' + key)):
                return v
        return None

def _extrair_nfse_lista_nfse(root):
        """Formato ListaNfse > CompNfse > Nfse > InfNfse ou CompNfse > Nfse > InfNfse (nota única ABRASF)."""
        comp = _nfse_dict_get(root, 'ListaNfse', 'CompNfse') or root
        nfse_el = _nfse_dict_get(comp, 'Nfse') if comp else None
        inf = _nfse_dict_get(nfse_el, 'InfNfse') if nfse_el else None
        if not inf:
            return None, None
        if isinstance(inf, list):
            inf = inf[0] if inf else None
        if not inf or not isinstance(inf, dict):
            return None, None
        chave = (inf.get('@Id') or '').strip()
        if chave.startswith('NFS'):
            chave = chave[3:]
        decl = _nfse_dict_get(inf, 'DeclaracaoPrestacaoServico', 'InfDeclaracaoPrestacaoServico')
        if isinstance(decl, list):
            decl = decl[0] if decl else None
        dados_adicionais = {
            'id': chave,
            'cancelada': _nfse_text(inf.get('Status')) == '2',
            'Rps': {'Numero': None, 'Serie': None, 'DataEmissao': None, 'DataVencimento': None},
            'Servico': {'Valores': {'Aliquota': None, 'ValorConfins': None, 'ValorIss': None, 'ValorPis': None, 'ValorServicos': None}, 'IssRetido': None, 'Discriminacao': None},
        }
        valores_nfse = _nfse_dict_get(inf, 'ValoresNfse')
        valores = None
        if valores_nfse and isinstance(valores_nfse, dict):
            valores = {
                'BaseCalculo': _nfse_text(valores_nfse.get('BaseCalculo')),
                'Aliquota': _nfse_text(valores_nfse.get('Aliquota')),
                'ValorIss': _nfse_text(valores_nfse.get('ValorIss')),
                'ValorLiquidoNfse': _nfse_text(valores_nfse.get('ValorLiquidoNfse')),
            }
        prestador = _nfse_dict_get(inf, 'PrestadorServico')
        cnpj_emitente = None
        nome_emitente = _nfse_text(prestador.get('RazaoSocial')) if prestador else ''
        if decl:
            prest = _nfse_dict_get(decl, 'Prestador')
            if prest:
                cpf_cnpj = _nfse_dict_get(prest, 'CpfCnpj')
                if cpf_cnpj:
                    cnpj_emitente = _nfse_text(cpf_cnpj.get('Cnpj')) or _nfse_text(cpf_cnpj.get('Cpf'))
            if not nome_emitente and prestador:
                nome_emitente = _nfse_text(prestador.get('RazaoSocial'))
        tomador_el = (_nfse_dict_get(decl, 'Tomador') or _nfse_dict_get(decl, 'TomadorServico')) if decl else None
        cnpj_dest = None
        nome_dest = ''
        if tomador_el:
            id_tom = _nfse_dict_get(tomador_el, 'IdentificacaoTomador', 'CpfCnpj')
            if id_tom and isinstance(id_tom, dict):
                cnpj_dest = _nfse_text(id_tom.get('Cnpj')) or _nfse_text(id_tom.get('Cpf'))
            nome_dest = _nfse_text(tomador_el.get('RazaoSocial'))
        if decl:
            serv = _nfse_dict_get(decl, 'Servico')
            if serv:
                vals = _nfse_dict_get(serv, 'Valores')
                if vals and isinstance(vals, dict):
                    dados_adicionais['Servico']['Valores']['Aliquota'] = _nfse_text(vals.get('Aliquota'))
                    dados_adicionais['Servico']['Valores']['ValorConfins'] = _nfse_text(vals.get('ValorCofins'))
                    dados_adicionais['Servico']['Valores']['ValorIss'] = _nfse_text(vals.get('ValorIss'))
                    dados_adicionais['Servico']['Valores']['ValorPis'] = _nfse_text(vals.get('ValorPis'))
                    dados_adicionais['Servico']['Valores']['ValorServicos'] = _nfse_text(vals.get('ValorServicos'))
                dados_adicionais['Servico']['IssRetido'] = _nfse_text(serv.get('IssRetido'))
                dados_adicionais['Servico']['Discriminacao'] = _nfse_text(serv.get('Discriminacao'))
            inf_comp = _nfse_dict_get(decl, 'InformacoesComplementares')
            if inf_comp:
                dados_adicionais['InformacoesComplementares'] = _nfse_text(inf_comp) if isinstance(inf_comp, str) else (inf_comp.get('#text') or '')
        dados_nfse = {
            'Numero': _nfse_text(inf.get('Numero')),
            'cnpj_emitente': cnpj_emitente,
            'nome_emitente': nome_emitente or _nfse_text(prestador.get('RazaoSocial')) if prestador else '',
            'cnpj_destinatario': cnpj_dest,
            'nome_destinatario': nome_dest,
            'DataEmissao': _nfse_text(inf.get('DataEmissao')),
            'valores': valores,
            'dados_adicionais': dados_adicionais,
        }
        return chave, dados_nfse

def _extrair_nfse_tc_lista(root):
        """Formato tcListaNFse (EL) com namespace - ex.: NF 35 - VALE."""
        for key in list(root.keys()):
            if key == 'tcListaNFse' or (isinstance(key, str) and key.endswith('}tcListaNFse')):
                tc = root[key]
                break
        else:
            return None, None
        nfse_el = _nfse_dict_get(tc, 'Nfse')
        if not nfse_el or not isinstance(nfse_el, dict):
            return None, None
        chave = _nfse_text(_nfse_val(nfse_el, 'Id'))
        ident = _nfse_dict_get(nfse_el, 'IdentificacaoNfse')
        numero = _nfse_text(_nfse_val(ident, 'Numero')) if ident else _nfse_text(_nfse_val(nfse_el, 'Numero'))
        data_emissao = _nfse_text(_nfse_val(nfse_el, 'DataEmissao'))
        if data_emissao and 'T' in data_emissao:
            data_emissao = data_emissao[:10]
        dados_adicionais = {
            'id': chave,
            'cancelada': _nfse_text(_nfse_val(nfse_el, 'Status')) == '2',
            'Rps': {'Numero': _nfse_text(_nfse_val(ident, 'NumeroRps')) if ident else None, 'Serie': _nfse_text(_nfse_val(ident, 'Serie')) if ident else None, 'DataEmissao': None, 'DataVencimento': None},
            'Servico': {'Valores': {'Aliquota': None, 'ValorConfins': None, 'ValorIss': None, 'ValorPis': None, 'ValorServicos': None}, 'IssRetido': None, 'Discriminacao': None},
        }
        valores_el = _nfse_dict_get(nfse_el, 'Valores')
        valores = None
        if valores_el and isinstance(valores_el, dict):
            valores = {
                'BaseCalculo': '',
                'Aliquota': _nfse_text(_nfse_val(valores_el, 'Aliquota')),
                'ValorIss': _nfse_text(_nfse_val(valores_el, 'ValorIss')),
                'ValorLiquidoNfse': _nfse_text(_nfse_val(valores_el, 'ValorLiquidoNfse')),
            }
        servicos_el = _nfse_dict_get(nfse_el, 'Servicos')
        if servicos_el and isinstance(servicos_el, dict):
            dados_adicionais['Servico']['Valores']['Aliquota'] = _nfse_text(_nfse_val(servicos_el, 'Aliquota'))
            dados_adicionais['Servico']['Valores']['ValorServicos'] = _nfse_text(_nfse_val(servicos_el, 'ValorServico') or _nfse_val(valores_el, 'ValorServicos') if valores_el else None)
            dados_adicionais['Servico']['Discriminacao'] = _nfse_text(_nfse_val(servicos_el, 'Descricao'))
        if valores_el and isinstance(valores_el, dict) and not dados_adicionais['Servico']['Valores']['ValorServicos']:
            dados_adicionais['Servico']['Valores']['ValorServicos'] = _nfse_text(_nfse_val(valores_el, 'ValorServicos'))
        dados_adicionais['Servico']['IssRetido'] = _nfse_text(_nfse_val(nfse_el, 'IssRetido'))
        obs = _nfse_text(_nfse_val(nfse_el, 'Observacao'))
        if obs:
            dados_adicionais['InformacoesComplementares'] = obs
        prest = _nfse_dict_get(nfse_el, 'DadosPrestador', 'IdentificacaoPrestador')
        cnpj_emitente = _nfse_text(_nfse_val(prest, 'CpfCnpj')) if prest and isinstance(prest, dict) else ''
        if not cnpj_emitente:
            prest_root = _nfse_dict_get(nfse_el, 'DadosPrestador')
            cnpj_emitente = _nfse_text(_nfse_val(prest_root, 'CpfCnpj')) if prest_root and isinstance(prest_root, dict) else ''
        dados_prest = _nfse_dict_get(nfse_el, 'DadosPrestador')
        nome_emitente = _nfse_text(_nfse_val(dados_prest, 'RazaoSocial')) if dados_prest else ''
        tomador = _nfse_dict_get(nfse_el, 'DadosTomador')
        id_tom = _nfse_dict_get(tomador, 'IdentificacaoTomador') if tomador else None
        cnpj_dest = _nfse_text(_nfse_val(id_tom, 'CpfCnpj')) if id_tom and isinstance(id_tom, dict) else ''
        if not cnpj_dest and tomador:
            cnpj_dest = _nfse_text(_nfse_val(tomador, 'CpfCnpj'))
        nome_dest = _nfse_text(_nfse_val(tomador, 'RazaoSocial')) if tomador and isinstance(tomador, dict) else ''
        dados_nfse = {
            'Numero': numero,
            'cnpj_emitente': cnpj_emitente,
            'nome_emitente': nome_emitente,
            'cnpj_destinatario': cnpj_dest,
            'nome_destinatario': nome_dest,
            'DataEmissao': data_emissao,
            'valores': valores,
            'dados_adicionais': dados_adicionais,
        }
        return chave, dados_nfse

def _extrair_nfse_sped(root):
        """Formato NFSe SPED (namespace sped.fazenda.gov.br/nfse) - ex.: 27126...8.xml."""
        for key in list(root.keys()):
            if key == 'NFSe' or (isinstance(key, str) and key.endswith('}NFSe')):
                nfse_root = root[key]
                break
        else:
            return None, None
        inf_nfse = _nfse_dict_get(nfse_root, 'infNFSe')
        if not inf_nfse or not isinstance(inf_nfse, dict):
            return None, None
        chave = _nfse_text(inf_nfse.get('@Id') or '')
        if chave.startswith('NFS'):
            chave = chave[3:]
        numero = _nfse_text(_nfse_val(inf_nfse, 'nNFSe'))
        data_emissao = ''
        emit = _nfse_dict_get(inf_nfse, 'emit')
        cnpj_emitente = _nfse_text(_nfse_val(emit, 'CNPJ')) if emit and isinstance(emit, dict) else ''
        nome_emitente = _nfse_text(_nfse_val(emit, 'xNome')) if emit and isinstance(emit, dict) else ''
        valores_raiz = _nfse_dict_get(inf_nfse, 'valores')
        v_liq = _nfse_text(_nfse_val(valores_raiz, 'vLiq')) if valores_raiz and isinstance(valores_raiz, dict) else ''
        dps = _nfse_dict_get(inf_nfse, 'DPS', 'infDPS')
        if isinstance(dps, list):
            dps = dps[0] if dps else None
        if dps and isinstance(dps, dict):
            data_emissao = _nfse_text(_nfse_val(dps, 'dhEmi'))
            if data_emissao and 'T' in data_emissao:
                data_emissao = data_emissao[:10]
            toma = _nfse_dict_get(dps, 'toma')
            cnpj_dest = _nfse_text(_nfse_val(toma, 'CNPJ')) if toma and isinstance(toma, dict) else ''
            nome_dest = _nfse_text(_nfse_val(toma, 'xNome')) if toma and isinstance(toma, dict) else ''
        else:
            cnpj_dest = ''
            nome_dest = ''
        v_serv = ''
        if dps and isinstance(dps, dict):
            v_serv_prest = _nfse_dict_get(dps, 'valores', 'vServPrest')
            if v_serv_prest and isinstance(v_serv_prest, dict):
                v_serv = _nfse_text(_nfse_val(v_serv_prest, 'vServ'))
        valores = {
            'BaseCalculo': '',
            'Aliquota': '',
            'ValorIss': '',
            'ValorLiquidoNfse': v_liq or '',
        }
        dados_adicionais = {
            'id': chave,
            'cancelada': False,
            'Rps': {'Numero': None, 'Serie': None, 'DataEmissao': None, 'DataVencimento': None},
            'Servico': {'Valores': {'Aliquota': None, 'ValorConfins': None, 'ValorIss': None, 'ValorPis': None, 'ValorServicos': v_serv or None}, 'IssRetido': None, 'Discriminacao': None},
        }
        dados_nfse = {
            'Numero': numero,
            'cnpj_emitente': cnpj_emitente,
            'nome_emitente': nome_emitente,
            'cnpj_destinatario': cnpj_dest,
            'nome_destinatario': nome_dest,
            'DataEmissao': data_emissao,
            'valores': valores,
            'dados_adicionais': dados_adicionais,
        }
        return chave, dados_nfse

def extrair_dados_xml_nfse(xml_data: str):
        """
        Extrai os dados de uma nota fiscal de serviço (NFSe) a partir do XML.
        Suporta três formatos: ListaNfse (padrão ABRASF), tcListaNFse (EL) e NFSe SPED.
        Retorna a chave de acesso e um dicionário com os dados da nota fiscal.
        """
        try:
            root = xmltodict.parse(base64.b64decode(xml_data).decode('utf-8'))
            if not root or not isinstance(root, dict):
                logger.warning("extrair_dados_xml_nfse: XML inválido ou vazio")
                return None, None

            def _tem_chave(d, *keys):
                for k in keys:
                    if d.get(k) is not None:
                        return True
                    for key in d:
                        if isinstance(key, str) and (key == k or key.endswith('}' + k)):
                            return True
                return False
            if _tem_chave(root, 'CompNfse'):
                root = _nfse_dict_get(root, 'CompNfse') or root
            if _tem_chave(root, 'ListaNfse'):
                chave, dados = _extrair_nfse_lista_nfse(root)
            elif _tem_chave(root, 'tcListaNFse'):
                chave, dados = _extrair_nfse_tc_lista(root)
            elif _tem_chave(root, 'Nfse'):
                nfse_inner = _nfse_dict_get(root, 'Nfse')
                if nfse_inner and isinstance(nfse_inner, dict) and _nfse_dict_get(nfse_inner, 'InfNfse'):
                    chave, dados = _extrair_nfse_lista_nfse(root)
                else:
                    chave, dados = _extrair_nfse_sped(root)
            else:
                logger.warning("extrair_dados_xml_nfse: Formato de XML NFSe não reconhecido")
                return None, None

            if not chave or not dados:
                return None, None
            if not dados.get('valores') or not _nfse_text(dados['valores'].get('ValorLiquidoNfse')):
                if dados.get('valores') is None:
                    dados['valores'] = {'BaseCalculo': '', 'Aliquota': '', 'ValorIss': '', 'ValorLiquidoNfse': '0'}
                elif not dados['valores'].get('ValorLiquidoNfse'):
                    dados['valores']['ValorLiquidoNfse'] = '0'
            return chave, dados
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Erro ao extrair dados do XML NFSe: {str(e)}")
            return None, None
