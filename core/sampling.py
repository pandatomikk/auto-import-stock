"""Product-count sampling and separate output names for demonstration batches."""
from pathlib import Path


def validate_limit(limit):
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError('La limite de produits doit être un entier positif.')


def catalogue_output(source, product_limit=None):
    validate_limit(product_limit)
    source = Path(source)
    suffix = f'_test_{product_limit}_produits' if product_limit is not None else ''
    return source.with_name(source.stem + suffix + '_woocommerce.csv')
