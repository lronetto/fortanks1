#!/usr/bin/env python3
"""
Teste manual de envio WhatsApp via Evolution API (models.evolution).

Carrega variáveis de ``.env`` na raiz do projeto: EVOLUTION_API_BASE_URL,
EVOLUTION_API_INSTANCE, EVOLUTION_API_TOKEN.

Exemplos::

    python scripts/testar_envio_evolution_whatsapp.py 48999999999 --tipo texto --texto "Olá"
    python scripts/testar_envio_evolution_whatsapp.py 5548999999999 --tipo imagem --media ./foto.jpg
    python scripts/testar_envio_evolution_whatsapp.py 48999999999 --tipo imagem-texto --media ./foto.jpg --legenda "Teste"
    python scripts/testar_envio_evolution_whatsapp.py 48999999999 --tipo documento --media ./arq.pdf
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path


def _raiz_projeto() -> Path:
    return Path(__file__).resolve().parent.parent


def _configurar_path_e_env() -> None:
    raiz = _raiz_projeto()
    script_dir = Path(__file__).resolve().parent
    # O interpretador prefixa sys.path com o diretório deste arquivo (`.../scripts/`).
    # Existe `scripts/email/`, que sombreia o pacote stdlib `email` e quebra
    # urllib3/requests/sqlalchemy ao importar `models`.
    sys.path[:] = [
        p for p in sys.path if Path(p).resolve() != script_dir
    ]
    raiz_str = str(raiz.resolve())
    if raiz_str not in sys.path:
        sys.path.insert(0, raiz_str)


def _arquivo_para_data_uri(caminho: Path) -> tuple[str, str, str]:
    """Lê arquivo e devolve (data_uri, mimetype, nome_arquivo)."""
    dados = caminho.read_bytes()
    mime, _ = mimetypes.guess_type(str(caminho))
    mime = mime or "application/octet-stream"
    b64 = base64.standard_b64encode(dados).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"
    return data_uri, mime, caminho.name


def _resolver_media(media: str) -> tuple[str, str | None, str | None]:
    """
    ``media`` pode ser URL/data URI ou caminho de arquivo local.

    Retorna (string_media, mimetype_opcional, nome_arquivo_opcional).
    """
    s = (media or "").strip()
    if not s:
        raise SystemExit("Parâmetro --media vazio.")

    if s.startswith(("http://", "https://", "data:")):
        return s, None, None

    p = Path(s)
    if not p.is_file():
        raise SystemExit(f"Arquivo não encontrado: {p}")
    data_uri, mime, nome = _arquivo_para_data_uri(p)
    return data_uri, mime, nome


def main() -> int:
    _configurar_path_e_env()

    parser = argparse.ArgumentParser(
        description="Envia uma mensagem de teste pela Evolution API."
    )
    parser.add_argument(
        "numero",
        help="Número de destino (ex.: 48999999999 ou 5548999999999)",
    )
    parser.add_argument(
        "--tipo",
        choices=("texto", "imagem", "imagem-texto", "documento", "documento-texto"),
        default="texto",
        help="Tipo de envio (padrão: texto)",
    )
    parser.add_argument(
        "--texto",
        "-t",
        default="",
        help="Texto para envio tipo texto (sendText)",
    )
    parser.add_argument(
        "--media",
        "-m",
        default="",
        help="URL, data URI ou caminho de arquivo local (imagem/documento)",
    )
    parser.add_argument(
        "--legenda",
        "-c",
        default="",
        help="Legenda obrigatória para imagem-texto e documento-texto",
    )
    parser.add_argument(
        "--mimetype",
        default="",
        help="MIME type (opcional; inferido para arquivos locais)",
    )
    parser.add_argument(
        "--nome-arquivo",
        default="",
        help="Nome do arquivo exibido no WhatsApp (opcional)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Mostra também variáveis de ambiente usadas (sem segredos)",
    )

    args = parser.parse_args()

    from models.evolution import EvolutionCliente, obter_cliente_evolution

    cliente = obter_cliente_evolution()

    if args.verbose:
        base = os.environ.get("EVOLUTION_API_BASE_URL") or "(padrão interno)"
        inst = os.environ.get("EVOLUTION_API_INSTANCE") or "(vazio)"
        tok = os.environ.get("EVOLUTION_API_TOKEN")
        print(f"EVOLUTION_API_BASE_URL={base}", file=sys.stderr)
        print(f"EVOLUTION_API_INSTANCE={inst}", file=sys.stderr)
        print(
            "EVOLUTION_API_TOKEN="
            + ("(definido)" if tok else "(ausente)"),
            file=sys.stderr,
        )

    texto_padrao = (
        args.texto.strip()
        if args.texto.strip()
        else "Mensagem de teste — Fortanks / Evolution API."
    )

    resultado: dict

    if args.tipo == "texto":
        resultado = cliente.enviar_texto(args.numero, texto_padrao)

    elif args.tipo == "imagem":
        if not args.media:
            parser.error("--tipo imagem exige --media (arquivo, URL ou data URI)")
        media_str, mime_arq, nome_arq = _resolver_media(args.media)
        mt = (args.mimetype or mime_arq or "image/jpeg").strip()
        fn = (args.nome_arquivo or nome_arq or "teste.jpg").strip() or "teste.jpg"
        resultado = cliente.enviar_imagem(
            args.numero, media_str, mimetype=mt, nome_arquivo=fn
        )

    elif args.tipo == "imagem-texto":
        if not args.media:
            parser.error("--tipo imagem-texto exige --media")
        legenda = (args.legenda or texto_padrao).strip()
        media_str, mime_arq, nome_arq = _resolver_media(args.media)
        mt = (args.mimetype or mime_arq or "image/jpeg").strip()
        fn = (args.nome_arquivo or nome_arq or "teste.jpg").strip() or "teste.jpg"
        resultado = cliente.enviar_imagem_com_texto(
            args.numero,
            media_str,
            legenda=legenda,
            mimetype=mt,
            nome_arquivo=fn,
        )

    elif args.tipo == "documento":
        if not args.media:
            parser.error("--tipo documento exige --media")
        media_str, mime_arq, nome_arq = _resolver_media(args.media)
        mt = (args.mimetype or mime_arq or None)
        fn = (args.nome_arquivo or nome_arq or "documento.bin").strip() or "documento.bin"
        resultado = cliente.enviar_documento(
            args.numero,
            media_str,
            nome_arquivo=fn,
            mimetype=mt,
        )

    else:  # documento-texto
        if not args.media:
            parser.error("--tipo documento-texto exige --media")
        legenda = (args.legenda or texto_padrao).strip()
        media_str, mime_arq, nome_arq = _resolver_media(args.media)
        mt = (args.mimetype or mime_arq or None)
        fn = (args.nome_arquivo or nome_arq or "documento.bin").strip() or "documento.bin"
        resultado = cliente.enviar_documento_com_texto(
            args.numero,
            media_str,
            legenda=legenda,
            nome_arquivo=fn,
            mimetype=mt,
        )

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
