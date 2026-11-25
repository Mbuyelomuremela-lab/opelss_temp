import re
from datetime import date

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Regexp

from app.utils import sast_today

SA_MOBILE_RE = re.compile(r"^(?:0|\+27)[6-8]\d{8}$")


def normalize_cellphone(value):
    """Strip spaces, dashes and brackets so '082 123 4567' is accepted."""
    return re.sub(r"[\s\-()]", "", value or "")


def is_valid_sa_mobile(value):
    return bool(SA_MOBILE_RE.match(normalize_cellphone(value)))


def _luhn_ok(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _birth_date_ok(yymmdd):
    """True if YYMMDD is a real, non-future date in either the 1900s or 2000s."""
    yy, mm, dd = int(yymmdd[0:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    today = sast_today()
    for century in (2000, 1900):
        try:
            if date(century + yy, mm, dd) <= today:
                return True
        except ValueError:
            continue
    return False


def sa_id_error(value):
    """Return an error message for an invalid SA ID number, or None if valid."""
    value = (value or "").strip()
    if not re.fullmatch(r"\d{13}", value):
        return "ID number must be exactly 13 digits."
    if not _birth_date_ok(value[0:6]):
        return "ID number does not contain a valid birth date (YYMMDD)."
    if value[10] not in "01":
        return "ID number citizenship digit (11th digit) must be 0 or 1."
    if not _luhn_ok(value):
        return "ID number check digit is incorrect."
    return None


class VisitorForm(FlaskForm):
    visitor_name = StringField("Visitor Name", validators=[DataRequired(), Length(max=120)])
    category = SelectField(
        "Category",
        choices=[
            ("UNISA Student", "UNISA Student"),
            ("Educator", "Educator"),
            ("Learner", "Learner"),
            ("Other", "Other"),
        ],
        validators=[DataRequired(), Length(max=100)],
    )
    student_number = StringField(
        "Student Number",
        validators=[
            Optional(),
            Regexp(r"^\d{8}$", message="Student number must be exactly 8 digits."),
        ],
    )
    sace_number = StringField(
        "SACE Number",
        validators=[
            Optional(),
            Regexp(r"^\d{8}$", message="SACE number must be exactly 8 digits."),
        ],
    )
    id_number = StringField("SA ID Number", validators=[Optional(), Length(max=13)])
    cellphone_number = StringField(
        "Cellphone Number",
        validators=[Optional(), Length(max=20)],
    )
    purpose = TextAreaField("Purpose", validators=[DataRequired(), Length(max=400)])
    visit_date = DateField("Visit Date", validators=[DataRequired()])
    lab_id = SelectField("Lab", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Log Visitor")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        ok = True
        category = self.category.data

        if category == "UNISA Student" and not self.student_number.data:
            self.student_number.errors.append("Student number is required for UNISA students.")
            ok = False

        if category == "Educator":
            if not self.sace_number.data:
                self.sace_number.errors.append("SACE number is required for educators.")
                ok = False
        else:
            if not self.id_number.data:
                self.id_number.errors.append("ID number is required.")
                ok = False
            else:
                error = sa_id_error(self.id_number.data)
                if error:
                    self.id_number.errors.append(error)
                    ok = False

        cell = self.cellphone_number.data
        if cell:
            if not is_valid_sa_mobile(cell):
                self.cellphone_number.errors.append(
                    "Enter a valid SA cellphone number, e.g. 0821234567 or +27821234567."
                )
                ok = False
        elif category != "Learner":
            self.cellphone_number.errors.append("Cellphone number is required.")
            ok = False

        return ok
