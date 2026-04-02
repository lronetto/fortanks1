"""
Compatibilidade: a implementação foi movida para `scripts.email`.

Prefira: ``from scripts.email import processar_emails, processar_anexo_pdf_pagina``
"""

from scripts.email import processar_anexo_pdf_pagina, processar_emails

__all__ = ["processar_emails", "processar_anexo_pdf_pagina"]
