"""
Este arquivo contém o código para resolver o processamento de XML em Base64 da API Arquivei.
Instruções:

1. Remova qualquer import do xml_utils de modulos/importacao_nf/app.py 
2. Adicione as funções abaixo no início do arquivo modulos/importacao_nf/app.py
3. Substitua a função original processar_e_salvar_nfe pela versão abaixo
"""

import base64
import tempfile
import os


def decodificar_base64_xml(xml_base64):
    """Decodifica um XML em Base64 para um arquivo temporário"""
    # Remover espaços e quebras de linha
    xml_base64 = xml_base64.replace(
        " ", "").replace("\n", "").replace("\r", "")

    # Decodificar o Base64 para bytes
    xml_bytes = base64.b64decode(xml_base64)

    # Tentar diferentes codificações
    xml_content = None
    for encoding in ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']:
        try:
            xml_content = xml_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if not xml_content:
        return None

    # Salvar em arquivo temporário
    temp_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.xml', delete=False, encoding='utf-8')
    temp_file.write(xml_content)
    temp_file_path = temp_file.name
    temp_file.close()

    return {
        'xml_content': xml_content,
        'temp_file_path': temp_file_path
    }


def identificar_xml_base64(nfe_data):
    """Identifica se um dicionário contém dados XML em Base64"""
    if 'xml' in nfe_data and isinstance(nfe_data['xml'], str) and len(nfe_data['xml']) > 100:
        return nfe_data['xml']
    elif 'xml_content' in nfe_data and isinstance(nfe_data['xml_content'], str) and len(nfe_data['xml_content']) > 100:
        return nfe_data['xml_content']
    elif 'content' in nfe_data and isinstance(nfe_data['content'], str) and len(nfe_data['content']) > 100:
        return nfe_data['content']
    elif 'data' in nfe_data and isinstance(nfe_data['data'], str) and len(nfe_data['data']) > 100:
        return nfe_data['data']
    return None


def processar_e_salvar_nfe(nfe_data):
    connection = get_db_connection()
    if not connection:
        return False

    try:
        logger.info("Iniciando processamento de NFe da API Arquivei")
        cursor = connection.cursor(dictionary=True)

        # Verificar se os dados contêm XML em Base64
        xml_base64 = identificar_xml_base64(nfe_data)

        # Se identificamos um possível XML em Base64, tentar decodificar e processar
        if xml_base64:
            logger.info(
                "Detectado possível XML em Base64, tentando decodificar")
            try:
                # Decodificar o XML Base64
                decoded_data = decodificar_base64_xml(xml_base64)

                if decoded_data:
                    # Processar o XML usando a função existente
                    temp_file_path = decoded_data['temp_file_path']
                    processed_nfe = process_xml_file(temp_file_path)

                    # Remover o arquivo temporário
                    os.unlink(temp_file_path)

                    # Se o processamento foi bem-sucedido, usar esses dados
                    if processed_nfe and processed_nfe.get('access_key'):
                        logger.info(
                            f"XML Base64 processado com sucesso: {processed_nfe.get('access_key')}")
                        nfe_data = processed_nfe

                        # Guardar o XML decodificado
                        nfe_data['xml'] = decoded_data['xml_content']
            except Exception as e:
                logger.warning(f"Erro ao processar XML Base64: {str(e)}")

        # Extrair informações relevantes da NFe
        chave_acesso = nfe_data.get('access_key')
        numero_nf = nfe_data.get('number', '')
        data_emissao = nfe_data.get('emission_date')

        # Verificar se data_emissao está presente
        if data_emissao is None:
            # Usar a data atual como fallback
            data_emissao = datetime.now()
            logger.warning(
                f"Data de emissão ausente para NFe {chave_acesso}, usando data atual como fallback")

        valor_total = nfe_data.get('value', 0)
        cnpj_emitente = nfe_data.get('cnpj_sender', '')
        nome_emitente = nfe_data.get('sender_name', '')
        cnpj_destinatario = nfe_data.get('cnpj_receiver', '')
        nome_destinatario = nfe_data.get('receiver_name', '')
        xml_data = nfe_data.get('xml', '')

        # Verificar se a chave de acesso está presente
        if not chave_acesso:
            logger.error("Chave de acesso ausente, impossível importar NFe")
            return False

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
                'Atualizado via API Arquivei em ' + datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                chave_acesso
            ))

            nfe_id = resultado['id']

            # Remover itens antigos
            cursor.execute("DELETE FROM nf_itens WHERE nf_id = %s", (nfe_id,))
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
                'Importado via API Arquivei em ' + datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            ))

            # Obter o ID da NFe inserida
            nfe_id = cursor.lastrowid

        # Processar itens da NFe
        itens = nfe_data.get('items', [])
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
            """, (nfe_id, codigo, descricao, quantidade,
                  valor_unitario, valor_total_item))

        connection.commit()
        logger.info(f"NFe {chave_acesso} salva com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro ao processar NFe: {str(e)}", exc_info=True)
        if connection:
            connection.rollback()
        return False
    finally:
        if connection and hasattr(connection, 'is_connected') and connection.is_connected():
            cursor.close()
            connection.close()
