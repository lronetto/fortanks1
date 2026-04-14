"""
Script para envio de relatório Excel de tanques por projeto via email

Uso:
    # Enviar para um projeto específico
    python -c "from controllers.relatorios.script_email import enviar_relatorio_por_email; import sys; sys.path.insert(0, '.'); from app import app; app.app_context().push(); enviar_relatorio_por_email(contrato_id=1, destinatarios=['email@example.com'])"
    
    # Ou usar diretamente no código Python com contexto da aplicação
    with app.app_context():
        enviar_relatorio_por_email(contrato_id=1, destinatarios=['email@example.com'])
"""

import sys
import os
from datetime import datetime
import pandas as pd
import io

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from flask import current_app
from models.tanque import TanquesPecas, Tanques
from models.contrato import Contrato
from models.database import db
from models.logs import Logs
from utils.email_utils import enviar_email, enviar_email_gmail
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill


def gerar_relatorio_excel_bytes(contrato_id):
    """
    Gera o relatório Excel em bytes para um projeto específico.
    Retorna uma tupla (bytes_do_excel, nome_arquivo, nome_projeto)
    """
    try:
        # Buscar o contrato
        contrato = Contrato.query.get(contrato_id)
        if not contrato:
            raise ValueError(f'Contrato com ID {contrato_id} não encontrado.')
        
        # Buscar todos os tanques do contrato
        tanques = Tanques.query.filter_by(contrato_id=contrato_id).order_by(Tanques.nome).all()
        
        if not tanques:
            raise ValueError(f'Nenhum tanque encontrado para o projeto "{contrato.nome}".')
        
        # Preparar dados para o relatório
        dados_relatorio = []
        
        for tanque in tanques:
            # Calcular quantidade prevista: (placas_normais + placas_fecho) * quantidade
            placas_normais = tanque.placas_normais or 0
            placas_fecho = tanque.placas_fecho or 0
            quantidade_tanques = tanque.quantidade or 1
            quantidade_prevista = (placas_normais + placas_fecho) * quantidade_tanques
            
            # Buscar peças concretadas (com data_concretagem não nula)
            pecas_concretadas = TanquesPecas.query.filter(
                TanquesPecas.tanque_id == tanque.id,
                TanquesPecas.data_concretagem.isnot(None),
            ).count()
            
            percentual_concluido = (pecas_concretadas/quantidade_prevista)*100 if quantidade_prevista > 0 else 0
            dados_relatorio.append({
                'ID': tanque.id,
                'Tanque': tanque.nome,
                'Placas': quantidade_prevista,
                'Quantidade Realizada (Concretadas)': pecas_concretadas,
                'Concluido': percentual_concluido / 100,  # Dividir por 100 para formato de porcentagem
            })
        
        # Criar DataFrame
        df = pd.DataFrame(dados_relatorio)
        
        if df.empty:
            raise ValueError('Nenhum dado encontrado para gerar o relatório.')
        
        # Adicionar linha de totais
        percentual_total = (df['Quantidade Realizada (Concretadas)'].sum()/df['Placas'].sum()*100) if df['Placas'].sum() > 0 else 0
        totais = {
            'ID': '',
            'Tanque': 'TOTAL',
            'Placas': df['Placas'].sum(),
            'Quantidade Realizada (Concretadas)': df['Quantidade Realizada (Concretadas)'].sum(),
            'Concluido': percentual_total / 100  # Dividir por 100 para formato de porcentagem
        }
        
        # Adicionar linha de totais ao DataFrame
        df_totais = pd.DataFrame([totais])
        df = pd.concat([df, df_totais], ignore_index=True)
        
        # Criar Excel na memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Relatório de Tanques')
            
            # Ajustar largura das colunas
            worksheet = writer.sheets['Relatório de Tanques']
            for idx, col in enumerate(df.columns):
                max_length = max(
                    df[col].astype(str).apply(len).max(),
                    len(col)
                )
                # Limitar largura máxima
                adjusted_width = min(max_length + 2, 50)
                col_letter = get_column_letter(idx + 1)
                worksheet.column_dimensions[col_letter].width = adjusted_width
            
            # Formatar coluna de "Concluido" como porcentagem
            col_concluido_idx = list(df.columns).index('Concluido')
            col_concluido_letter = get_column_letter(col_concluido_idx + 1)
            
            # Aplicar formatação de porcentagem em todas as linhas (exceto cabeçalho)
            for row_idx in range(2, len(df) + 2):  # Começa na linha 2 (após cabeçalho)
                cell = worksheet[f'{col_concluido_letter}{row_idx}']
                cell.number_format = '0.00%'  # Formato: 85.50%
            
            # Formatar linha de totais (última linha)
            last_row = len(df) + 1  # +1 porque o Excel começa em 1 e tem cabeçalho
            for col_idx, col in enumerate(df.columns):
                col_letter = get_column_letter(col_idx + 1)
                cell = worksheet[f'{col_letter}{last_row}']
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color='D3D3D3', end_color='D3D3D3', fill_type='solid')
                # Se for a coluna "Concluido", aplicar formatação de porcentagem também
                if col == 'Concluido':
                    cell.number_format = '0.00%'
        
        output.seek(0)
        excel_bytes = output.read()
        
        # Nome do arquivo
        nome_arquivo = f"relatorio_tanques_{contrato.nome.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return excel_bytes, nome_arquivo, contrato.nome
        
    except Exception as e:
        current_app.logger.error(f'Erro ao gerar relatório Excel: {str(e)}')
        raise


def enviar_relatorio_por_email(contrato_id, destinatarios=None, assunto=None, mensagem_adicional=''):
    """
    Gera o relatório Excel de tanques por projeto e envia por email.
    
    Args:
        contrato_id (int): ID do contrato/projeto
        destinatarios (list, optional): Lista de emails destinatários. 
                                       Se None, usa EMAILS_RELATORIO_TANQUES do config.
        assunto (str, optional): Assunto do email. Se None, usa assunto padrão.
        mensagem_adicional (str, optional): Mensagem adicional a incluir no corpo do email.
    
    Returns:
        bool: True se enviado com sucesso, False caso contrário.
    """
    try:
        # Verificar se há contexto da aplicação
        if not current_app:
            raise RuntimeError('Este script precisa ser executado dentro do contexto da aplicação Flask. Use: with app.app_context():')
        
        # Buscar o contrato para obter o nome
        contrato = Contrato.query.get(contrato_id)
        if not contrato:
            current_app.logger.error(f'Contrato com ID {contrato_id} não encontrado.')
            return False
        
        # Obter destinatários
        if not destinatarios:
            # Tentar obter do config
            emails_config = current_app.config.get('EMAILS_RELATORIO_TANQUES', '')
            if emails_config:
                # Separar emails por vírgula ou ponto e vírgula
                destinatarios = [email.strip() for email in emails_config.replace(';', ',').split(',') if email.strip()]
            else:
                current_app.logger.error('Nenhum destinatário configurado. Configure EMAILS_RELATORIO_TANQUES no .env ou passe destinatarios como parâmetro.')
                return False
        
        # Garantir que destinatarios seja uma lista
        if isinstance(destinatarios, str):
            destinatarios = [destinatarios]
        
        # Filtrar emails vazios
        destinatarios = [email for email in destinatarios if email and email.strip()]
        
        if not destinatarios:
            current_app.logger.error('Nenhum destinatário válido encontrado.')
            return False
        
        # Gerar relatório Excel
        current_app.logger.info(f'Gerando relatório Excel para o projeto "{contrato.nome}" (ID: {contrato_id})...')
        excel_bytes, nome_arquivo, nome_projeto = gerar_relatorio_excel_bytes(contrato_id)
        
        # Preparar assunto do email
        if not assunto:
            assunto = f'Relatório de Tanques - {nome_projeto}'
        
        # Preparar corpo do email
        data_geracao = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        corpo_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <p>Prezados,</p>
            <p>Segue em anexo o relatório Excel de tanques do projeto <strong>{nome_projeto}</strong>.</p>
            <p><strong>Data de geração:</strong> {data_geracao}</p>
        """
        
        if mensagem_adicional:
            corpo_html += f"<p><strong>Mensagem adicional:</strong><br>{mensagem_adicional}</p>"
        
        corpo_html += """
            <p>Atenciosamente,<br>Sistema Fortanks</p>
        </body>
        </html>
        """
        
        corpo_texto = f"""
Prezados,

Segue em anexo o relatório Excel de tanques do projeto {nome_projeto}.

Data de geração: {data_geracao}
"""
        if mensagem_adicional:
            corpo_texto += f"\nMensagem adicional:\n{mensagem_adicional}\n"
        
        corpo_texto += "\nAtenciosamente,\nSistema Fortanks"
        
        # Preparar anexo
        anexos = [
            (nome_arquivo, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', excel_bytes)
        ]
        
        # Enviar email
        current_app.logger.info(f'Enviando relatório para: {", ".join(destinatarios)}')
        sucesso = enviar_email_gmail(
            destinatario=destinatarios,
            assunto=assunto,
            corpo_html=corpo_html,
            corpo_texto=corpo_texto,
            anexos=anexos
        )
        
        if sucesso:
            current_app.logger.info(f'Relatório enviado com sucesso para {", ".join(destinatarios)}')
        else:
            current_app.logger.error(f'Falha ao enviar relatório para {", ".join(destinatarios)}')
        
        return sucesso
        
    except Exception as e:
        current_app.logger.error(f'Erro ao enviar relatório por email: {str(e)}', exc_info=True)
        return False


def enviar_relatorios_multiplos_projetos(contrato_ids, destinatarios=None, assunto_padrao=None):
    """
    Envia relatórios para múltiplos projetos.
    
    Args:
        contrato_ids (list): Lista de IDs de cadastros/contratos/projetos
        destinatarios (list, optional): Lista de emails destinatários
        assunto_padrao (str, optional): Assunto padrão (será complementado com nome do projeto)
    
    Returns:
        dict: Dicionário com resultados {contrato_id: sucesso (bool)}
    """
    resultados = {}
    
    for contrato_id in contrato_ids:
        try:
            contrato = Contrato.query.get(contrato_id)
            if not contrato:
                resultados[contrato_id] = False
                continue
            
            assunto = f'{assunto_padrao} - {contrato.nome}' if assunto_padrao else None
            sucesso = enviar_relatorio_por_email(
                contrato_id=contrato_id,
                destinatarios=destinatarios,
                assunto=assunto
            )
            resultados[contrato_id] = sucesso
        except Exception as e:
            current_app.logger.error(f'Erro ao enviar relatório para projeto {contrato_id}: {str(e)}')
            resultados[contrato_id] = False
    
    return resultados


def relatorio_semanal():
    """
    Envia relatórios semanais.
    """
    "Relatorios de tanques por projeto"
    contrato_id = 3
    destinatarios = []
    destinatarios = ['leandro.netto@fortanks.ind.br', 
                    'gean.junior@fortanks.ind.br', 
                   'bruno.lacerda@fortanks.ind.br', 
                   'marcelo.porto@fortanks.ind.br']
    destinatarios += ['arthur.witzel@fortes.ind.br','joao.faria@fortes.ind.br','joao.carvalho@fortes.ind.br']
    try:
        enviar_relatorio_por_email(contrato_id=contrato_id, destinatarios=destinatarios)
        Logs(local='relatorio_semanal', data=datetime.now(), texto='Relatório de tanques por projeto enviado com sucesso enviado para: ' + ', '.join(destinatarios))
        return True
    except Exception as e:
        Logs(local='relatorio_semanal', data=datetime.now(), texto='Erro ao enviar relatório de tanques por projeto: ' + str(e))
        raise e