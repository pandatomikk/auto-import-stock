"""Optional profile-driven sale price calculation with decimal rounding."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def sale_price(value, rule):
    if value is None or str(value).strip() == '':
        return ''
    try:
        price = Decimal(str(value).strip().replace('\xa0', '').replace(' ', '').replace('€', '').replace(',', '.'))
        divisor = Decimal(str(rule.get('divide_by', '1')))
        multiplier = Decimal(str(rule.get('multiply_by', '1')))
        if not all(x.is_finite() for x in (price, divisor, multiplier)) or price < 0 or divisor <= 0 or multiplier <= 0:
            raise ValueError('Prix ou coefficient invalide')
        return format((price / divisor * multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Calcul du prix de vente impossible : vérifiez le prix source et les coefficients.') from exc
