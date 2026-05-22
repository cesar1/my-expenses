import pytest
from app import validate_expense_form


VALID = {
    "description": "Lunch",
    "amount": "12.50",
    "category": "Food",
    "date": "2024-03-01",
}


def form(**overrides):
    return {**VALID, **overrides}


def test_valid_input():
    data, error = validate_expense_form(form())
    assert error is None
    assert data == {"description": "Lunch", "amount": 12.50, "category": "Food", "date": "2024-03-01"}


@pytest.mark.parametrize("field", ["description", "amount", "category", "date"])
def test_missing_field(field):
    _, error = validate_expense_form(form(**{field: ""}))
    assert error == "All fields are required."


def test_amount_not_a_number():
    _, error = validate_expense_form(form(amount="abc"))
    assert error == "Amount must be a positive number."


def test_amount_zero():
    _, error = validate_expense_form(form(amount="0"))
    assert error == "Amount must be a positive number."


def test_amount_negative():
    _, error = validate_expense_form(form(amount="-5"))
    assert error == "Amount must be a positive number."


def test_invalid_category():
    _, error = validate_expense_form(form(category="Vacation"))
    assert error == "Invalid category."


def test_invalid_date_format():
    _, error = validate_expense_form(form(date="03/01/2024"))
    assert error == "Date must be in YYYY-MM-DD format."


def test_description_is_stripped():
    data, error = validate_expense_form(form(description="  Lunch  "))
    assert error is None
    assert data["description"] == "Lunch"
