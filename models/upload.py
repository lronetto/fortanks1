from datetime import datetime
from models.database import db
import base64
from sqlalchemy import Text


class Upload(db.Model):
    __tablename__ = 'Uploads'
    id = db.Column(db.Integer, primary_key=True)
    pai_id = db.Column(db.Integer, nullable=True)
    pai = db.Column(db.String(255), nullable=True)
    tipo = db.Column(db.Integer, nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    blob = db.Column(Text(length=4294967295), nullable=False)  # LONGTEXT
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Upload {self.id} - {self.filename}>'
    
    def __init__(self, pai=None, pai_id=None, tipo=None, filename=None, mimetype=None, blob=None):
        if not pai and not pai_id and not tipo and not filename and not mimetype and not blob:
            return self
        if not blob:
            #print('pai: ',pai)
            #print('pai_id: ',pai_id)
            #print('tipo: ',tipo)
            self = Upload.query.filter_by(pai=pai, pai_id=pai_id, tipo=tipo, filename=filename, mimetype=mimetype).first()
            #print('upload: ',self)
            return self
        else:
            self.pai = pai
            self.pai_id = pai_id
            self.tipo = tipo
            self.filename = filename
            self.mimetype = mimetype
            # Codifica o blob em base64 antes de salvar
            if isinstance(blob, bytes):
                self.blob = base64.b64encode(blob).decode('utf-8')
            else:
                self.blob = blob
            up = Upload.query.filter_by(pai=pai, pai_id=pai_id, tipo=tipo).first()
            if not up:
                self.save()
            else:
                self.id = up.id
                self.uploaded_at = up.uploaded_at
                return self

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            print('upload error: ',e)
            db.session.rollback()
            raise e

    def get_blob(self):
        """
        Retorna o blob decodificado do base64
        """
        if self.blob:
            return base64.b64decode(self.blob)
        return None

    def get(self, pai, pai_id, tipo=None):
        if tipo:
            return Upload.query.filter_by(pai=pai, pai_id=pai_id, tipo=tipo).all()
        else:
            return Upload.query.filter_by(pai=pai, pai_id=pai_id).all()
    
    def delete(self):
        try:
            db.session.delete(self)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e
