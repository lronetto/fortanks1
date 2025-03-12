"""
Solução para processamento de XMLs em Base64 no módulo de importação NF

Instruções de uso:
1. Copie a função processar_e_salvar_nfe abaixo no arquivo modulos/importacao_nf/app.py
2. Certifique-se de que a importação do módulo base64 esteja presente

Este arquivo contém uma versão completa e revisada das funções para lidar com XMLs em Base64.
"""

import base64
import tempfile
import os
from datetime import datetime
import xml.etree.ElementTree as ET
import re


def processar_e_salvar_nfe(nfe_data):
    """
    Processa e salva uma NFe no banco de dados, com suporte a XML em Base64

    Args:
        nfe_data: Dicionário com dados da NFe da API Arquivei

    Returns:
        bool: True se o processamento foi bem-sucedido, False caso contrário
    """
    from app import get_db_connection, logger, process_xml_file

    connection = get_db_connection()
    if not connection:
        return False

    try:
        cursor = connection.cursor(dictionary=True)

        # Verificar se os dados podem estar em Base64
        xml_base64 = None
        processed_xml = False

        # Verificar em diferentes campos onde o XML pode estar
        if 'xml' in nfe_data and isinstance(nfe_data['xml'], str) and len(nfe_data['xml']) > 100:
            xml_base64 = nfe_data['xml']
        elif 'content' in nfe_data and isinstance(nfe_data['content'], str) and len(nfe_data['content']) > 100:
            xml_base64 = nfe_data['content']
        elif 'data' in nfe_data and isinstance(nfe_data['data'], str) and len(nfe_data['data']) > 100:
            xml_base64 = nfe_data['data']

        # Tentar decodificar Base64
        if xml_base64:
            # Verificar se parece ser Base64 (apenas caracteres válidos de Base64)
            if re.match(r'^[A-Za-z0-9+/=]+$', xml_base64.replace(" ", "").replace("\n", "")):
                try:
                    logger.info(
                        "Detectado conteúdo que parece ser Base64, tentando decodificar")

                    # Limpar a string Base64
                    xml_base64 = xml_base64.replace(
                        " ", "").replace("\n", "").replace("\r", "")

                    # Decodificar Base64
                    xml_bytes = base64.b64decode(xml_base64)

                    # Tentar diferentes codificações
                    xml_content = None
                    for encoding in ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']:
                        try:
                            xml_content = xml_bytes.decode(encoding)
                            logger.info(
                                f"XML decodificado com sucesso usando {encoding}")
                            break
                        except UnicodeDecodeError:
                            continue

                    if xml_content:
                        # Criar arquivo temporário para o XML decodificado
                        temp_file = tempfile.NamedTemporaryFile(
                            mode='w', suffix='.xml', delete=False, encoding='utf-8')
                        temp_file.write(xml_content)
                        temp_file_path = temp_file.name
                        temp_file.close()

                        logger.info(
                            f"XML Base64 salvo em arquivo temporário: {temp_file_path}")

                        # Processar o arquivo XML usando a função existente
                        try:
                            processed_nfe = process_xml_file(temp_file_path)

                            # Remover arquivo temporário
                            os.unlink(temp_file_path)

                            # Se processou com sucesso, usar esses dados
                            if processed_nfe and processed_nfe.get('access_key'):
                                nfe_data = processed_nfe
                                nfe_data['xml'] = xml_content
                                processed_xml = True
                                logger.info(
                                    f"XML Base64 processado com sucesso: {processed_nfe.get('access_key')}")
                        except Exception as e:
                            logger.error(
                                f"Erro ao processar arquivo XML temporário: {str(e)}")
                            # Tentar remover o arquivo temporário, se ainda existir
                            try:
                                if os.path.exists(temp_file_path):
                                    os.unlink(temp_file_path)
                            except:
                                pass
                except Exception as e:
                    logger.error(f"Erro ao decodificar Base64: {str(e)}")

        # Se não conseguimos processar o XML, continuar com os dados originais
        if not processed_xml:
            logger.info("Usando dados originais sem processamento de Base64")

        # Extrair informações relevantes da NFe
        chave_acesso = nfe_data.get('access_key')
        numero_nf = nfe_data.get('number', '')
        data_emissao = nfe_data.get('emission_date')

        # Verificar se data_emissao está presente
        if data_emissao is None:
            # Usar a data atual como fallback
            data_emissao = datetime.now()

        valor_total = nfe_data.get('value', 0)
        cnpj_emitente = nfe_data.get('cnpj_sender', '')
        nome_emitente = nfe_data.get('sender_name', '')
        cnpj_destinatario = nfe_data.get('cnpj_receiver', '')
        nome_destinatario = nfe_data.get('receiver_name', '')
        xml_data = nfe_data.get('xml', '')

        # Verificar se a chave de acesso está presente
        if not chave_acesso:
            logger.error("Chave de acesso ausente, impossível processar NFe")
            return False

        # Registrar informações para debug
        logger.info(
            f"Processando NFe: {chave_acesso}, {numero_nf}, {nome_emitente}")

        # Verificar se a NFe já existe no banco
        cursor.execute(
            "SELECT id FROM nf_notas WHERE chave_acesso = %s", (chave_acesso,))
        resultado = cursor.fetchone()

        if resultado:
            # Atualizar NFe existente
            cursor.execute("""
                UPDATE nf_notas SET 
                numero_nf = %s,
                data_emissao = %s, 
                valor_total = %s, 
                cnpj_emitente = %s, 
                nome_emitente = %s, 
                cnpj_destinatario = %s, 
                nome_destinatario = %s, 
                status_processamento = 'atualizado',
                data_atualizacao = NOW(),
                observacoes = %s
                WHERE chave_acesso = %s
            """, (
                numero_nf,
                data_emissao,
                valor_total,
                cnpj_emitente,
                nome_emitente,
                cnpj_destinatario,
                nome_destinatario,
                f"Atualizado via API Arquivei em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                chave_acesso
            ))

            nfe_id = resultado['id']

            # Remover itens antigos
            cursor.execute("DELETE FROM nf_itens WHERE nf_id = %s", (nfe_id,))

            logger.info(f"NFe {chave_acesso} atualizada no banco")
        else:
            # Inserir nova NFe
            cursor.execute("""
                INSERT INTO nf_notas (
                    chave_acesso, numero_nf, data_emissao, valor_total, cnpj_emitente, 
                    nome_emitente, cnpj_destinatario, nome_destinatario, 
                    xml_data, status_processamento, data_importacao, observacoes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
            """, (
                chave_acesso,
                numero_nf,
                data_emissao,
                valor_total,
                cnpj_emitente,
                nome_emitente,
                cnpj_destinatario,
                nome_destinatario,
                xml_data,
                'importado',
                f"Importado via API Arquivei em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            ))

            # Obter o ID da NFe inserida
            nfe_id = cursor.lastrowid
            logger.info(
                f"Nova NFe {chave_acesso} inserida no banco, ID: {nfe_id}")

        # Processar itens da NFe
        itens = nfe_data.get('items', [])
        logger.info(f"Processando {len(itens)} itens para NFe {chave_acesso}")

        for item in itens:
            codigo = item.get('code', '')
            descricao = item.get('description', '')
            quantidade = item.get('quantity', 0)
            valor_unitario = item.get('unit_value', 0)
            valor_total_item = item.get('total_value', 0)

            cursor.execute("""
                INSERT INTO nf_itens (
                    nf_id, codigo, descricao, quantidade, 
                    valor_unitario, valor_total
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                nfe_id,
                codigo,
                descricao,
                quantidade,
                valor_unitario,
                valor_total_item
            ))

        connection.commit()
        logger.info(
            f"Processamento da NFe {chave_acesso} concluído com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro no processamento da NFe: {str(e)}", exc_info=True)
        if connection:
            connection.rollback()
        return False
    finally:
        if connection and hasattr(connection, 'is_connected') and connection.is_connected():
            cursor.close()
            connection.close()
