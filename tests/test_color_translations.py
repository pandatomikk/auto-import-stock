import unittest
from core.color_translations import translate_color


class ColorTranslationTests(unittest.TestCase):
    def test_languages_and_compounds(self):
        for source, expected in [('NERO/ANTRACITE','Noir / Anthracite'), ('BLACK AND GOLD','Noir / Doré'), ('NAVY-BLUE','Bleu marine'), ('white-black','Blanc / Noir'), ('blanco/rojo','Blanc / Rouge'), ('DUNKELGRÜN/SCHWARZ','Vert foncé / Noir'), ('caffè','Café'), ('gris clair','Gris clair'), ('ROSA ANTICO','Vieux rose')]:
            with self.subTest(source=source): self.assertEqual(translate_color(source),expected)

    def test_user_translation_has_priority(self):
        self.assertEqual(translate_color('black/gold',{'BLACK':'Ébène'}),'Ébène / Doré')
        self.assertEqual(translate_color('nero/argento',{'NERO/ARGENTO':'Noir métallisé'}),'Noir métallisé')

    def test_unknown_colour_is_not_guessed(self):
        self.assertIsNone(translate_color('Summer Dream'))
        self.assertIsNone(translate_color('BLACK/SECRET SHADE'))
