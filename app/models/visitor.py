import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from app.extensions import db
from app.utils import sast_today


def _id_cipher() -> Fernet:
    # The encryption key is derived from SECRET_KEY. If SECRET_KEY changes,
    # ID numbers stored under the old value can no longer be decrypted.
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    key = hashlib.sha256(b"opelss-visitor-id-number:" + secret).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class Visitor(db.Model):
    __tablename__ = "visitors"

    id = db.Column(db.Integer, primary_key=True)
    visitor_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    student_number = db.Column(db.String(8))
    cellphone_number = db.Column(db.String(20))
    sace_number = db.Column(db.String(8))
    id_number_encrypted = db.Column(db.String(255))
    purpose = db.Column(db.Text, nullable=False)
    visit_date = db.Column(db.Date, nullable=False, default=sast_today)
    lab_id = db.Column(db.Integer, db.ForeignKey("labs.id"), nullable=False)

    lab = db.relationship("Lab", back_populates="visitors")

    @property
    def id_number(self):
        """Decrypted SA ID number, or None if not captured / unreadable."""
        if not self.id_number_encrypted:
            return None
        try:
            return _id_cipher().decrypt(self.id_number_encrypted.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return None

    @id_number.setter
    def id_number(self, value):
        if not value:
            self.id_number_encrypted = None
            return
        self.id_number_encrypted = _id_cipher().encrypt(value.encode("utf-8")).decode("ascii")

    def __repr__(self):
        return f"<Visitor {self.visitor_name} on {self.visit_date}>"
