"""Constantes fiscais, de CNPJ e de API compartilhadas pelo domínio de Nota Fiscal."""
import os
from dotenv import load_dotenv

load_dotenv()

# Referência ao `Upload` do XML principal da nota (`Upload.tipo == TIPO_UPLOAD_XML_NOTA_FISCAL`).
DA_XML_UPLOAD_ID = "xml_upload_id"

# ── Credenciais Arquivei ────────────────────────────────────────────────────
# Fonte única: todos os módulos devem importar daqui, não reler os envvars.
ARQUIVEI_API_ID  = os.getenv('ARQUIVEI_API_ID')
ARQUIVEI_API_KEY = os.getenv('ARQUIVEI_API_KEY')

# ── CNPJs da empresa ────────────────────────────────────────────────────────
CNPJS_FILIAIS = ["27126997000349", "27126997000268", "27126997000420"]
CNPJS_MATRIZ = ["27126997000187"]
CNPJS_MATRIZ_FILIAIS = CNPJS_MATRIZ + CNPJS_FILIAIS
CFOPS_COMPRA = ["6101", "5101", "5405", "6105", "6401"]
CFOPS_VENDA = ["6101", "5101", "6107"]
CFOPS_TRANSFERENCIA = ["5949", "6949"]
