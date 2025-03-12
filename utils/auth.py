from flask import session


def verificar_permissao(nivel_permissao):
    """
    Verifica se o usuário logado tem o nível de permissão necessário.

    Args:
        nivel_permissao (str): Nível de permissão necessário para a operação.
            Pode ser 'visualizar', 'editar', 'admin', entre outros.

    Returns:
        bool: True se o usuário tem permissão, False caso contrário.
    """
    # Verificar se o usuário está logado
    if 'logado' not in session or 'cargo' not in session:
        return False

    cargo = session.get('cargo', '')

    # Permissões baseadas no cargo
    if cargo == 'admin':
        # Administradores têm todas as permissões
        return True

    elif cargo == 'gerente':
        # Gerentes podem visualizar e editar, mas não têm acesso admin
        if nivel_permissao in ['visualizar', 'editar']:
            return True

    elif cargo == 'supervisor':
        # Supervisores podem visualizar e editar em certas condições
        if nivel_permissao in ['visualizar', 'editar']:
            return True

    elif cargo == 'técnico':
        # Técnicos podem apenas visualizar
        if nivel_permissao == 'visualizar':
            return True

    # Qualquer outro usuário só tem permissão de visualização básica
    elif nivel_permissao == 'visualizar':
        return True

    return False
