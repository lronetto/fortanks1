"""
Constantes e configuração de ambiente do processamento de e-mail IMAP.
"""
import logging
import os
import shutil

from dotenv import load_dotenv

try:
    import rarfile

    RAR_SUPPORT = True
    unrar_paths = ["/usr/bin/unrar", "/usr/local/bin/unrar", "/bin/unrar", "unrar"]
    unrar_found = None
    for path in unrar_paths:
        if shutil.which(path) or (os.path.exists(path) and os.access(path, os.X_OK)):
            unrar_found = path
            rarfile.UNRAR_TOOL = path
            logging.info(f"Ferramenta unrar encontrada em: {path}")
            break

    if not unrar_found:
        unrar_in_path = shutil.which("unrar")
        if unrar_in_path:
            rarfile.UNRAR_TOOL = unrar_in_path
            logging.info(f"Ferramenta unrar encontrada no PATH: {unrar_in_path}")
        else:
            logging.warning(
                "Ferramenta unrar não encontrada. Arquivos RAR podem não funcionar corretamente."
            )
except ImportError:

    class _RarStub:
        """Evita NameError em handlers que referenciam rarfile.* quando o pacote não está instalado."""

        class RarCannotExec(Exception):
            pass

        class RarNoFilesError(Exception):
            pass

    rarfile = _RarStub()  # type: ignore
    RAR_SUPPORT = False
    logging.warning(
        "Biblioteca rarfile não encontrada. Arquivos .rar não serão processados. Instale com: pip install rarfile"
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def carregar_variaveis_ambiente():
    """Carrega as variáveis de ambiente do arquivo .env."""
    load_dotenv(override=True)
    return {
        "IMAP_HOST": os.getenv("IMAP_HOST"),
        "IMAP_USER": os.getenv("IMAP_USER"),
        "IMAP_PASS": os.getenv("IMAP_PASS"),
        "EVOLUTION_API_INSTANCE": os.getenv("EVOLUTION_API_INSTANCE"),
        "EVOLUTION_API_TOKEN": os.getenv("EVOLUTION_API_TOKEN"),
        "ARQUIVEI_API_KEY": os.getenv("ARQUIVEI_API_KEY"),
        "ARQUIVEI_API_ID": os.getenv("ARQUIVEI_API_ID"),
    }


IMAP_FOLDER = "Inbox"
ASSUNTO_PADRAO_NFE = ["Envio de Nota Fiscal Eletrônica"]
ASSUNTO_PADRAO_CTE = ["Envio de Nota Fiscal Eletrônica - DUA"]
ASSUNTO_PADRAO_DUA = ["CTE, NF Fortanks e DUA", "CTE, NF Fortanks"]
ASSUNTO_PADRAO_PROTOCOLO = [
    "ENC: NF´S PROTOCOLOS",
    "ENC: NF PROTOCOLO",
    "NF PROTOCOLO",
    "Protocolo",
    "ENC: PROTOCOLO",
]
ASSUNTO_PADRAO_REEMBOLSO = ["REEMBOLSO", "REEBOLSO", "ENC: REEBOLSO", "ENC: reembolso"]
EMAIL_DESTINO = "leandro.netto@fortanks.ind.br"
IMAGEM_MARCA_DAGUA = "static/img/carimbo_0014-00.png"
NUMBER_WHATSAPP = "5527996440664-1630085280@g.us"

MAX_EMAILS_POR_EXECUCAO = 20
DELAY_ENTRE_EMAILS = float(os.getenv("DELAY_ENTRE_EMAILS", "1.0"))
DELAY_ENTRE_BUSCAS_IMAP = float(os.getenv("DELAY_ENTRE_BUSCAS_IMAP", "0.5"))
MARCAR_LIDOS_EM_LOTE = os.getenv("MARCAR_LIDOS_EM_LOTE", "true").lower() == "true"
TAMANHO_LOTE_MARCAR_LIDOS = int(os.getenv("TAMANHO_LOTE_MARCAR_LIDOS", "10"))

MAX_ANEXOS_POR_EMAIL = int(os.getenv("MAX_ANEXOS_POR_EMAIL", "50"))
MAX_ANEXOS_POR_EMAIL_PROCESSAR = int(os.getenv("MAX_ANEXOS_POR_EMAIL_PROCESSAR", "50"))
TAMANHO_MAX_ANEXO_MB = float(os.getenv("TAMANHO_MAX_ANEXO_MB", "10.0"))
PROCESSAR_APENAS_PDF_XML = os.getenv("PROCESSAR_APENAS_PDF_XML", "true").lower() == "true"
PRIORIZAR_XML = os.getenv("PRIORIZAR_XML", "true").lower() == "true"
ORDENAR_EMAILS_POR_ANEXOS = os.getenv("ORDENAR_EMAILS_POR_ANEXOS", "true").lower() == "true"
MAX_WORKERS_ANEXOS = int(os.getenv("MAX_WORKERS_ANEXOS", "1"))
