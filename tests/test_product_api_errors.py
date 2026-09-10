import io
import json
import unittest
from urllib.error import HTTPError
from core.shop_connection import Credentials
from core.shop_products import api_error


class ApiErrorTests(unittest.TestCase):
    def test_validation_details_and_secret_redaction(self):
        c=Credentials(consumer_key='ck_private',consumer_secret='cs_private')
        body={'code':'rest_invalid_param','message':'Champ invalide cs_private','data':{'params':{'stock_quantity':'Entier attendu ck_private'}}}
        error=api_error(HTTPError('https://shop.example',400,'Bad request',{},io.BytesIO(json.dumps(body).encode())),c,True)
        self.assertTrue(error.rejected)
        self.assertIn('stock_quantity',str(error))
        self.assertNotIn('cs_private',str(error));self.assertNotIn('ck_private',str(error))

    def test_generic_400_is_still_unconfirmed(self):
        error=api_error(HTTPError('https://shop.example',400,'Bad request',{},io.BytesIO(b'<html>Error</html>')),Credentials(),True)
        self.assertFalse(error.rejected)
        self.assertIn('non confirmée',str(error))
