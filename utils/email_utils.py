from flask import current_app
from flask_mail import Message
import re
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header, make_header
from email.utils import formataddr
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Você precisará inicializar a extensão Mail no seu app principal (app.py ou similar)
# from flask_mail import Mail
# mail = Mail(app)

def enviar_email(destinatario, assunto, corpo_html, corpo_texto='', anexos=None):
    """
    Envia um e-mail usando a configuração do Flask-Mail.

    Args:
        destinatario (str or list): O endereço de e-mail do destinatário ou uma lista de endereços.
        assunto (str): O assunto do e-mail.
        corpo_html (str): O corpo do e-mail em formato HTML.
        corpo_texto (str, optional): O corpo do e-mail em texto puro (fallback). Defaults to ''.
        anexos (list, optional): Lista de tuplas para anexos. 
                                 Cada tupla deve ser (nome_arquivo, content_type, dados_binarios).
                                 Ex: [('solicitacao.pdf', 'application/pdf', pdf_bytes)]. 
                                 Defaults to None.

    Returns:
        bool: True se o e-mail foi enviado com sucesso (ou enfileirado), False caso contrário.
    """
    mail = current_app.extensions.get('mail')
    if not mail:
        current_app.logger.error("Flask-Mail não inicializado ou configurado.")
        return False
        
    # Garante que temos um corpo de texto, mesmo que básico
    if not corpo_texto:
        corpo_texto = re.sub('<[^<]+?>', '', corpo_html) # Remove tags HTML

    # Garante que destinatario seja uma lista
    if isinstance(destinatario, str):
        recipients = [destinatario]
    elif isinstance(destinatario, list):
        recipients = destinatario
    else:
        current_app.logger.error(f"Tipo inválido para destinatario: {type(destinatario)}")
        return False
        
    msg = Message(
        assunto,
        sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'default@sender.com'), # Usar o remetente padrão configurado
        recipients=recipients
    )
    msg.body = corpo_texto
    msg.html = corpo_html
    
    # Adicionar anexos
    if anexos:
        if not isinstance(anexos, list):
            anexos = [anexos] # Trata caso passe apenas uma tupla
            
        for anexo in anexos:
            try:
                nome_arquivo, content_type, dados = anexo
                msg.attach(nome_arquivo, content_type, dados)
            except Exception as e:
                current_app.logger.error(f"Erro ao anexar arquivo '{nome_arquivo if 'nome_arquivo' in locals() else 'desconhecido'}': {e}")
                # Decide se quer falhar o envio ou apenas logar e continuar
                return False # Falha o envio se não conseguir anexar

    try:
        mail.send(msg)
        current_app.logger.info(f"E-mail enviado para {recipients} com assunto '{assunto}'")
        return True
    except Exception as e:
        current_app.logger.error(f"Falha ao enviar e-mail para {recipients}: {e}")
        return False

# Exemplo de como inicializar no app.py:
# from flask import Flask
# from flask_mail import Mail

# app = Flask(__name__)
# Configurações do Flask-Mail (EXEMPLO - use suas configurações reais!)
# app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
# app.config['MAIL_PORT'] = 587
# app.config['MAIL_USE_TLS'] = True
# app.config['MAIL_USERNAME'] = 'seu_email@gmail.com'  # Ou pegue de variáveis de ambiente
# app.config['MAIL_PASSWORD'] = 'sua_senha_de_app' # Ou pegue de variáveis de ambiente
# app.config['MAIL_DEFAULT_SENDER'] = ('Nome Remetente', 'seu_email@gmail.com')

# mail = Mail(app)


def enviar_email_gmail(destinatario, assunto, corpo_html, corpo_texto='', anexos=None, remetente_nome=None):
    """
    Envia um e-mail usando SMTP do Gmail diretamente, sem depender do Flask-Mail.
    Esta função é útil para scripts que não têm contexto da aplicação Flask.
    
    Configurações necessárias no .env:
        IMAP_HOST: Servidor SMTP (padrão: smtp.gmail.com)
        IMAP_USER: Email do Gmail (ex: seu_email@gmail.com)
        IMAP_PASS: Senha de app do Gmail (não a senha normal, mas uma senha de app)
    
    Args:
        destinatario (str or list): O endereço de e-mail do destinatário ou uma lista de endereços.
        assunto (str): O assunto do e-mail.
        corpo_html (str): O corpo do e-mail em formato HTML.
        corpo_texto (str, optional): O corpo do e-mail em texto puro (fallback). Defaults to ''.
        anexos (list, optional): Lista de tuplas para anexos. 
                                 Cada tupla deve ser (nome_arquivo, content_type, dados_binarios).
                                 Ex: [('solicitacao.pdf', 'application/pdf', pdf_bytes)]. 
                                 Defaults to None.
        remetente_nome (str, optional): Nome do remetente. Se None, usa apenas o email.
    
    Returns:
        bool: True se o e-mail foi enviado com sucesso, False caso contrário.
    """
    try:
        # Obter configurações do .env
        smtp_host = os.environ.get('IMAP_HOST', 'smtp.gmail.com')
        smtp_user = os.environ.get('IMAP_USER', '')
        smtp_pass = os.environ.get('IMAP_PASS', '')
        
        if not smtp_user or not smtp_pass:
            print("ERRO: IMAP_USER e IMAP_PASS devem estar configurados no arquivo .env")
            return False
        
        # Garantir que destinatario seja uma lista
        if isinstance(destinatario, str):
            recipients = [destinatario]
        elif isinstance(destinatario, list):
            recipients = destinatario
        else:
            print(f"ERRO: Tipo inválido para destinatario: {type(destinatario)}")
            return False
        
        # Filtrar emails vazios
        recipients = [email for email in recipients if email and email.strip()]
        
        if not recipients:
            print("ERRO: Nenhum destinatário válido encontrado.")
            return False
        
        # Garantir que temos um corpo de texto
        if not corpo_texto:
            corpo_texto = re.sub('<[^<]+?>', '', corpo_html)  # Remove tags HTML
        
        # Criar mensagem
        msg = MIMEMultipart('alternative')
        # Codificar assunto com UTF-8
        msg['Subject'] = Header(assunto, 'utf-8')
        # Codificar remetente com UTF-8 se tiver nome
        if remetente_nome:
            msg['From'] = formataddr((Header(remetente_nome, 'utf-8').encode(), smtp_user))
        else:
            msg['From'] = smtp_user
        msg['To'] = ', '.join(recipients)
        
        # Adicionar corpo do email
        part_texto = MIMEText(corpo_texto, 'plain', 'utf-8')
        part_html = MIMEText(corpo_html, 'html', 'utf-8')
        
        msg.attach(part_texto)
        msg.attach(part_html)
        
        # Adicionar anexos
        if anexos:
            if not isinstance(anexos, list):
                anexos = [anexos]  # Trata caso passe apenas uma tupla
            
            for anexo in anexos:
                try:
                    nome_arquivo, content_type, dados = anexo
                    
                    # Criar parte do anexo
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(dados)
                    encoders.encode_base64(part)
                    # Codificar nome do arquivo com UTF-8 para suportar caracteres especiais
                    # Usar Header para codificar corretamente
                    try:
                        # Tentar codificar o nome do arquivo
                        if any(ord(c) > 127 for c in nome_arquivo):
                            # Tem caracteres especiais, usar codificação UTF-8
                            encoded_filename = str(Header(nome_arquivo, 'utf-8'))
                        else:
                            # Apenas ASCII, usar diretamente
                            encoded_filename = nome_arquivo
                        part.add_header(
                            'Content-Disposition',
                            'attachment',
                            filename=encoded_filename
                        )
                    except Exception as e:
                        # Fallback: usar nome simples se houver erro
                        print(f"AVISO: Erro ao codificar nome do arquivo '{nome_arquivo}', usando nome simples: {e}")
                        part.add_header(
                            'Content-Disposition',
                            'attachment',
                            filename='anexo'
                        )
                    msg.attach(part)
                except Exception as e:
                    print(f"ERRO: Erro ao anexar arquivo '{nome_arquivo if 'nome_arquivo' in locals() else 'desconhecido'}': {e}")
                    return False
        
        # Conectar ao servidor SMTP e enviar
        try:
            # Determinar porta baseada no host
            if 'gmail.com' in smtp_host.lower():
                smtp_port = 587
                use_tls = True
            else:
                smtp_port = int(os.environ.get('IMAP_PORT', '587'))
                use_tls = True
            
            # Conectar ao servidor
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()  # Habilitar TLS
            
            # Fazer login
            server.login(smtp_user, smtp_pass)
            
            # Enviar email - usar as_bytes() para garantir encoding UTF-8 correto
            server.sendmail(smtp_user, recipients, msg.as_bytes())
            server.quit()
            
            print(f"✅ E-mail enviado com sucesso para {', '.join(recipients)} com assunto '{assunto}'")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"ERRO: Falha na autenticação SMTP. Verifique IMAP_USER e IMAP_PASS no .env. Erro: {e}")
            return False
        except smtplib.SMTPException as e:
            print(f"ERRO: Falha ao enviar e-mail via SMTP: {e}")
            return False
        except Exception as e:
            print(f"ERRO: Erro inesperado ao enviar e-mail: {e}")
            return False
            
    except Exception as e:
        print(f"ERRO: Erro ao preparar e-mail: {e}")
        return False 