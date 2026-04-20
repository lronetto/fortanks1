from models.concreto import (
    ConcretoConcretagens,
    extrair_ids_pecas_concretagem,
    normalizar_chave_peca,
)
from models.tanque.entities.transportes import TanquesTransportes
from models.database import db

from .whatsapp_transporte import enviar_whatsapp_transporte

def registrar_transporte(data_transporte, nota_fiscal, placa_carreta, transportadora,pecas,numero_destino=None,observacao=None,enviar_whatsapp=False,imagem_upload_id=None):
    
    conc = ConcretoConcretagens.query.filter(ConcretoConcretagens.pecas.contains(pecas)).first()
    if not conc:
        raise ValueError('Tem peca que nao foi concretada')
    
    registro = TanquesTransportes(data_transporte, nota_fiscal, placa_carreta, transportadora,pecas,observacao,enviar_whatsapp,imagem_upload_id)
    db.session.add(registro)
    db.session.commit()

    if enviar_whatsapp:
        enviar_whatsapp_transporte(registro.id,numero_destino)
    return registro
