"""
Retrocompatibilidade: re-exporta as funções de senha agora definidas em Usuario.
Prefira usar Usuario.hash_password(), Usuario.check_password() e Usuario.is_argon2_hash().
"""
from models.usuario import Usuario

hash_password = Usuario.hash_password
check_password = Usuario.check_password
is_argon2_hash = Usuario.is_argon2_hash
