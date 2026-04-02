"""
Processamento de e-mail IMAP (NFe, protocolos, reembolsos, DUA).

Uso:
    from scripts.email import processar_emails, processar_anexo_pdf_pagina
"""

from scripts.email.pdf_comum import processar_anexo_pdf_pagina
from scripts.email.processar import processar_emails

__all__ = ["processar_emails", "processar_anexo_pdf_pagina"]
