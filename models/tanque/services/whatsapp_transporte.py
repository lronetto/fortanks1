"""
Envio de resumo de transporte pelo WhatsApp via Evolution API (imagem + legenda).

Variáveis de ambiente (mesmo padrão de ``scripts/email/mensagens.py``):
``EVOLUTION_API_INSTANCE``, ``EVOLUTION_API_TOKEN`` e opcionalmente ``EVOLUTION_API_BASE_URL``
(padrão ``http://192.168.8.150:8081``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models.evolution import EvolutionCliente, obter_cliente_evolution
from models.tanque.constants import TIPO_UPLOAD_FOTO_TRANSPORTE
from models.tanque.entities.pecas import TanquesPecas
from models.tanque.entities.transportes import TanquesTransportes
from models.upload import Upload

logger = logging.getLogger(__name__)


def _carregar_pecas_transporte(registro: TanquesTransportes) -> List[TanquesPecas]:
    ids = registro.pecas_ids()
    if not ids:
        return []
    return (
        TanquesPecas.query.filter(TanquesPecas.id.in_(ids))
        .order_by(TanquesPecas.nome.asc())
        .all()
    )


def montar_texto_whatsapp_transporte(registro: TanquesTransportes) -> str:
    """
    Texto da legenda: NF, tanques, nomes das peças (chapas/peças transportadas), observação e placa se houver.
    """
    pecas = _carregar_pecas_transporte(registro)
    dados = registro.dados_adicionais_dict()

    linhas: List[str] = []
    nf = registro.nota
    linhas.append(f"*NF:* {nf if nf is not None else '—'}")

    tanques_nomes = sorted(
        {p.tanque.nome.strip() for p in pecas if p.tanque and (p.tanque.nome or '').strip()}
    )
    if tanques_nomes:
        linhas.append(f"*Tanque(s):* {', '.join(tanques_nomes)}")
    else:
        linhas.append("*Tanque(s):* —")

    nomes_pecas = [(p.nome or "").strip() for p in pecas if (p.nome or "").strip()]
    if nomes_pecas:
        linhas.append("*Peças transportadas:*")
        linhas.extend(f"• {n}" for n in nomes_pecas)
    else:
        linhas.append("*Peças transportadas:* —")

    placa = (dados.get("placa_carreta") or "").strip()
    if placa:
        linhas.append(f"*Placa carreta:* {placa}")

    obs = (dados.get("observacao") or "").strip()
    if obs:
        linhas.append(f"*Observação:* {obs}")

    transportadora = (registro.transportadora or "").strip()
    if transportadora:
        linhas.append(f"*Transportadora:* {transportadora}")

    return "\n".join(linhas)


def _resolver_upload_foto(transportes_id: int, registro: TanquesTransportes) -> Optional[Upload]:
    dados = registro.dados_adicionais_dict()
    uid = dados.get("foto_upload_id")
    try:
        uid_int = int(uid) if uid is not None and str(uid).strip() != "" else None
    except (TypeError, ValueError):
        uid_int = None
    if not uid_int:
        return None
    up = Upload.query.get(uid_int)
    if not up:
        return None
    if up.pai != "TanquesTransportes" or up.pai_id != transportes_id or up.tipo != TIPO_UPLOAD_FOTO_TRANSPORTE:
        logger.warning(
            "Upload %s não corresponde ao transporte %s (pai/tipo/pai_id).",
            uid_int,
            transportes_id,
        )
        return None
    if not up.blob:
        return None
    return up


def enviar_whatsapp_transporte(
    transportes_id: int,
    numero_destino: str,
    *,
    apenas_texto_sem_foto: bool = False,
    cliente: EvolutionCliente | None = None,
) -> Dict[str, Any]:
    """
    Envia foto (se existir em ``dados_adicionais.foto_upload_id``) + legenda via ``sendMedia``,
    ou só texto via ``sendText`` se não houver imagem ou ``apenas_texto_sem_foto=True``.

    :param numero_destino: número com DDI (ex.: 5548999999999) ou 11 dígitos BR (prefixa 55).
    :return: dict com ``success``, opcionalmente ``response`` ou ``error``.
    """
    evo = cliente or obter_cliente_evolution()

    registro = TanquesTransportes.query.get(transportes_id)
    if not registro:
        return {"success": False, "error": "Registro de transporte não encontrado."}

    caption = montar_texto_whatsapp_transporte(registro)

    upload = None if apenas_texto_sem_foto else _resolver_upload_foto(transportes_id, registro)

    if upload:
        blob = (upload.blob or "").strip()
        if not blob:
            return {"success": False, "error": "Arquivo da foto vazio no upload."}
        return evo.enviar_imagem_com_texto(
            numero_destino,
            blob,
            legenda=caption,
            mimetype=(upload.mimetype or "image/jpeg").strip(),
            nome_arquivo=(upload.filename or "transporte.jpg").strip() or "transporte.jpg",
        )

    return evo.enviar_texto(numero_destino, caption)
