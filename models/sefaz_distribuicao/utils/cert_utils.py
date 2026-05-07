"""
Utilitários para uso do certificado digital A1 (.pfx / .p12).

O mesmo certificado é usado:
  - para autenticação TLS mútua com a SEFAZ / ADN (mTLS);
  - opcionalmente para assinar XMLs em alguns serviços.

Como o `requests` não consome PKCS#12 diretamente, extraímos chave e
certificado para arquivos PEM temporários (criados com permissão 0600 e
removidos ao final via context manager).
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


@dataclass(frozen=True)
class CertificadoA1:
    """Caminho para o arquivo .pfx/.p12 e a senha de acesso."""

    caminho_pfx: str
    senha: str

    def carregar(self) -> Tuple[bytes, bytes, bytes]:
        """Retorna (chave_privada_pem, certificado_pem, cadeia_pem)."""
        with open(self.caminho_pfx, "rb") as fp:
            pfx_bytes = fp.read()

        chave, cert, cadeia = pkcs12.load_key_and_certificates(
            pfx_bytes, self.senha.encode("utf-8")
        )
        if chave is None or cert is None:
            raise ValueError("PFX inválido: chave ou certificado ausente")

        chave_pem = chave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        cadeia_pem = b"".join(
            c.public_bytes(serialization.Encoding.PEM) for c in (cadeia or [])
        )
        return chave_pem, cert_pem, cadeia_pem

    def cnpj_titular(self) -> str | None:
        """Lê o CNPJ embutido no Subject Alternative Name (otherName 2.16.76.1.3.3)."""
        with open(self.caminho_pfx, "rb") as fp:
            _, cert, _ = pkcs12.load_key_and_certificates(
                fp.read(), self.senha.encode("utf-8")
            )
        if cert is None:
            return None
        try:
            from cryptography.x509.oid import ExtensionOID

            ext = cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )
            for name in ext.value:
                valor = getattr(name, "value", "")
                if isinstance(valor, bytes) and len(valor) >= 14:
                    candidato = valor[-14:].decode("ascii", errors="ignore")
                    if candidato.isdigit():
                        return candidato
        except Exception:
            pass
        return None


@contextmanager
def materializar_pem(cert: CertificadoA1) -> Iterator[Tuple[str, str]]:
    """
    Gera arquivos PEM temporários (chave + cert) e devolve os caminhos.
    Os arquivos são apagados ao sair do `with`.

    Uso:
        with materializar_pem(cert) as (cert_path, key_path):
            requests.post(url, ..., cert=(cert_path, key_path))
    """
    chave_pem, cert_pem, _ = cert.carregar()

    fd_cert, cert_path = tempfile.mkstemp(suffix=".pem", prefix="cert_")
    fd_key, key_path = tempfile.mkstemp(suffix=".pem", prefix="key_")
    try:
        os.write(fd_cert, cert_pem)
        os.write(fd_key, chave_pem)
        os.close(fd_cert)
        os.close(fd_key)
        os.chmod(cert_path, 0o600)
        os.chmod(key_path, 0o600)
        yield cert_path, key_path
    finally:
        for caminho in (cert_path, key_path):
            try:
                os.remove(caminho)
            except OSError:
                pass
