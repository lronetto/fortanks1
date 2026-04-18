"""Constantes da integração Evolution API (WhatsApp)."""

# Variáveis de ambiente (mesmo padrão de scripts/email e serviços legados)
ENV_BASE_URL = "EVOLUTION_API_BASE_URL"
ENV_INSTANCE = "EVOLUTION_API_SFORTANKS_INSTANCE"
ENV_TOKEN = "EVOLUTION_API_SFORTANKS_TOKEN"

DEFAULT_BASE_URL = "http://192.168.8.5:8080"
TIMEOUT_SEGUNDOS_PADRAO = 90

# Segmento de rota após ``/message/`` (ex.: POST /message/sendText/{instance})
ROTA_SEND_TEXT = "sendText"
ROTA_SEND_MEDIA = "sendMedia"

# Campo ``mediatype`` do corpo em ``sendMedia``
MEDIA_TYPE_IMAGE = "image"
MEDIA_TYPE_DOCUMENT = "document"
