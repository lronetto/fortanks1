"""
Shim de compatibilidade para Materiais.

O controller original era muito grande e misturava páginas + APIs.
Agora:
- páginas ficam em `controllers/material/routes/*`
- APIs ficam em `controllers/api/material_api.py`

Este arquivo existe para manter compatibilidade com `app.py`:
`from controllers.material_controller import material_bp`
"""

from controllers.material import material_bp  # noqa: F401


