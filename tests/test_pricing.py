import unittest
from core.pricing import sale_price

class PricingTests(unittest.TestCase):
    def test_decimal_calculation_and_rounding(self):
        rule={'divide_by':'0.95','multiply_by':'2.5'}
        self.assertEqual(sale_price('152,00',rule),'400.00')
        self.assertEqual(sale_price('49,40',rule),'130.00')
        self.assertEqual(sale_price('1,01',rule),'2.66')
        self.assertEqual(sale_price('1.005',{}),'1.01')
        self.assertEqual(sale_price('',rule),'')
    def test_invalid_values_are_rejected(self):
        for value,rule in [('NaN',{}),('-1',{}),('abc',{}),('12',{'divide_by':'0'}),('12',{'multiply_by':'Infinity'})]:
            with self.subTest(value=value,rule=rule), self.assertRaises(ValueError):
                sale_price(value,rule)
