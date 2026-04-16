"""
Extensões Flask centralizadas.
Evita imports circulares ao criar instâncias sem app e inicializar depois.

PRODUÇÃO: Configure RATELIMIT_STORAGE_URI=redis://localhost:6379/0 no .env
para que os contadores de rate limit sobrevivam a restarts e funcionem
em múltiplas instâncias. Sem isso, o storage é em memória e zera a cada
reinicialização do processo.
"""
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

_storage_uri = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri=_storage_uri,
)
