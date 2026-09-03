def is_valid_imei(value: str) -> bool:
    """Validate a 15-digit IMEI using the standard Luhn checksum."""
    if len(value) != 15 or not value.isdigit():
        return False
    total = 0
    for index, char in enumerate(value):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0
