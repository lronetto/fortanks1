"""
Cliente HTTP para Evolution API — regras de envio de mensagens (texto, mídia, documentos).

Contrato de retorno alinhado ao uso em ``whatsapp_transporte``: dict com ``success``,
``error`` opcional, ``response`` opcional e ``modo`` (``sendText`` / ``sendMedia``).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

from models.evolution.constants import (
    DEFAULT_BASE_URL,
    ENV_BASE_URL,
    ENV_INSTANCE,
    ENV_TOKEN,
    MEDIA_TYPE_DOCUMENT,
    MEDIA_TYPE_IMAGE,
    ROTA_SEND_MEDIA,
    ROTA_SEND_TEXT,
    TIMEOUT_SEGUNDOS_PADRAO,
)
from models.evolution.utils.telefone import normalizar_numero_whatsapp_br

logger = logging.getLogger(__name__)

_cliente_padrao: Optional["EvolutionCliente"] = None


def obter_cliente_evolution() -> "EvolutionCliente":
    """Instância singleton com configuração via variáveis de ambiente."""
    global _cliente_padrao
    if _cliente_padrao is None:
        _cliente_padrao = EvolutionCliente()
    return _cliente_padrao


class EvolutionCliente:
    """
    Centraliza chamadas ``/message/sendText`` e ``/message/sendMedia`` com validação
    de destino e montagem de payload conforme a documentação da Evolution API.
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        instance: Optional[str] = None,
        token: Optional[str] = None,
        timeout_segundos: int = TIMEOUT_SEGUNDOS_PADRAO,
    ) -> None:
        self._base_url = (base_url or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).rstrip(
            "/"
        )
        self._instance = (instance or os.environ.get(ENV_INSTANCE) or "").strip()
        self._token = (token or os.environ.get(ENV_TOKEN) or "").strip()
        self._timeout_segundos = timeout_segundos

    def _config_valida(self) -> Optional[str]:
        if not self._instance or not self._token:
            return "EVOLUTION_API_INSTANCE ou EVOLUTION_API_TOKEN não configurados."
        return None

    def _resolver_numero(self, numero_destino: str) -> tuple[Optional[str], Optional[str]]:
        n = normalizar_numero_whatsapp_br(numero_destino)
        if not n:
            return None, "Número de destino inválido."
        return n, None

    def post_message(
        self, tipo_mensagem: str, payload: Dict[str, Any]
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Chamada HTTP de baixo nível. Útil para fluxos legados que já montam o JSON completo.

        ``tipo_mensagem``: segmento da URL (ex.: ``sendText``, ``sendMedia``).
        """
        err = self._config_valida()
        if err:
            return None, err

        url = f"{self._base_url}/message/{tipo_mensagem}/{self._instance}"
        headers = {
            "apikey": self._token,
            "Content-Type": "application/json",
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=self._timeout_segundos)
            try:
                body = r.json()
            except ValueError:
                body = {"raw": r.text}
            if r.status_code >= 400:
                return body, f"Evolution HTTP {r.status_code}: {body}"
            return body, None
        except requests.RequestException as e:
            logger.exception("Falha ao chamar Evolution API")
            return None, str(e)

    def _resultado_ok(
        self, body: Optional[Dict[str, Any]], modo: str
    ) -> Dict[str, Any]:
        return {"success": True, "response": body, "modo": modo}

    def _resultado_erro(
        self,
        erro: str,
        body: Optional[Dict[str, Any]] = None,
        modo: Optional[str] = None,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {"success": False, "error": erro}
        if body is not None:
            out["response"] = body
        if modo is not None:
            out["modo"] = modo
        return out

    def enviar_texto(self, numero_destino: str, texto: str) -> Dict[str, Any]:
        """Envia apenas texto (rota ``sendText``)."""
        t = (texto or "").strip()
        if not t:
            return self._resultado_erro("Texto da mensagem vazio.")

        numero, err = self._resolver_numero(numero_destino)
        if err:
            return self._resultado_erro(err)

        payload = {"number": numero, "text": t}
        body, err_http = self.post_message(ROTA_SEND_TEXT, payload)
        if err_http:
            return self._resultado_erro(err_http, body, ROTA_SEND_TEXT)
        return self._resultado_ok(body, ROTA_SEND_TEXT)

    def enviar_imagem(
        self,
        numero_destino: str,
        media: str,
        *,
        mimetype: str,
        nome_arquivo: str,
    ) -> Dict[str, Any]:
        """
        Imagem sem legenda. ``media``: URL ou string base64 (como armazenada na aplicação).

        Para legenda, use ``enviar_imagem_com_texto``.
        """
        media = (media or "").strip()
        if not media:
            return self._resultado_erro("Conteúdo da mídia vazio.")

        numero, err = self._resolver_numero(numero_destino)
        if err:
            return self._resultado_erro(err)

        mt = (mimetype or "image/jpeg").strip()
        fn = (nome_arquivo or "imagem.jpg").strip() or "imagem.jpg"
        payload: Dict[str, Any] = {
            "number": numero,
            "mediatype": MEDIA_TYPE_IMAGE,
            "mimetype": mt,
            "media": media,
            "fileName": fn,
        }
        body, err_http = self.post_message(ROTA_SEND_MEDIA, payload)
        if err_http:
            return self._resultado_erro(err_http, body, ROTA_SEND_MEDIA)
        return self._resultado_ok(body, ROTA_SEND_MEDIA)

    def enviar_imagem_com_texto(
        self,
        numero_destino: str,
        media: str,
        *,
        legenda: str,
        mimetype: str,
        nome_arquivo: str,
    ) -> Dict[str, Any]:
        """Imagem com legenda obrigatória (campo ``caption`` no ``sendMedia``)."""
        cap = (legenda or "").strip()
        if not cap:
            return self._resultado_erro("Legenda obrigatória para envio de imagem com texto.")

        media = (media or "").strip()
        if not media:
            return self._resultado_erro("Conteúdo da mídia vazio.")

        numero, err = self._resolver_numero(numero_destino)
        if err:
            return self._resultado_erro(err)

        mt = (mimetype or "image/jpeg").strip()
        fn = (nome_arquivo or "imagem.jpg").strip() or "imagem.jpg"
        payload: Dict[str, Any] = {
            "number": numero,
            "mediatype": MEDIA_TYPE_IMAGE,
            "mimetype": mt,
            "caption": cap,
            "media": media,
            "fileName": fn,
        }
        body, err_http = self.post_message(ROTA_SEND_MEDIA, payload)
        if err_http:
            return self._resultado_erro(err_http, body, ROTA_SEND_MEDIA)
        return self._resultado_ok(body, ROTA_SEND_MEDIA)

    def enviar_documento(
        self,
        numero_destino: str,
        media: str,
        *,
        nome_arquivo: str,
        mimetype: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Documento sem legenda (``mediatype`` = ``document``)."""
        media = (media or "").strip()
        if not media:
            return self._resultado_erro("Conteúdo do documento vazio.")

        numero, err = self._resolver_numero(numero_destino)
        if err:
            return self._resultado_erro(err)

        fn = (nome_arquivo or "documento").strip() or "documento"
        mt = (mimetype or "application/octet-stream").strip()
        payload: Dict[str, Any] = {
            "number": numero,
            "mediatype": MEDIA_TYPE_DOCUMENT,
            "mimetype": mt,
            "media": media,
            "fileName": fn,
        }
        body, err_http = self.post_message(ROTA_SEND_MEDIA, payload)
        if err_http:
            return self._resultado_erro(err_http, body, ROTA_SEND_MEDIA)
        return self._resultado_ok(body, ROTA_SEND_MEDIA)

    def enviar_documento_com_texto(
        self,
        numero_destino: str,
        media: str,
        *,
        legenda: str,
        nome_arquivo: str,
        mimetype: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Documento com legenda obrigatória."""
        cap = (legenda or "").strip()
        if not cap:
            return self._resultado_erro("Legenda obrigatória para envio de documento com texto.")

        media = (media or "").strip()
        if not media:
            return self._resultado_erro("Conteúdo do documento vazio.")

        numero, err = self._resolver_numero(numero_destino)
        if err:
            return self._resultado_erro(err)

        fn = (nome_arquivo or "documento").strip() or "documento"
        mt = (mimetype or "application/octet-stream").strip()
        payload: Dict[str, Any] = {
            "number": numero,
            "mediatype": MEDIA_TYPE_DOCUMENT,
            "mimetype": mt,
            "caption": cap,
            "media": media,
            "fileName": fn,
        }
        body, err_http = self.post_message(ROTA_SEND_MEDIA, payload)
        if err_http:
            return self._resultado_erro(err_http, body, ROTA_SEND_MEDIA)
        return self._resultado_ok(body, ROTA_SEND_MEDIA)
