import unittest
from unittest.mock import Mock
from core.media_library import MediaLibrary, upload_name
from core.shop_connection import ConnectionFailure

class MediaLibraryTests(unittest.TestCase):
    def library(self,items):
        return MediaLibrary(Mock(listing=Mock(return_value=items)))

    def test_wordpress_domain_protection_and_long_names(self):
        name='a'*100+'-01__123456789abc-www.example.fr.webp'
        self.assertTrue(upload_name(name).endswith('www.example.fr.webp'))
        lib=self.library([{'id':5,'source_url':'https://example.test/'+name.replace('.fr.','.fr_.')}])
        self.assertEqual(lib.find(name)['id'],5)

    def test_original_image_metadata(self):
        lib=self.library([{'id':6,'source_url':'https://example.test/photo-scaled.jpg','media_details':{'original_image':'photo.jpg'}}])
        self.assertEqual(lib.find('photo.jpg')['id'],6)

    def test_partial_name_is_never_reused(self):
        lib=self.library([{'id':5,'source_url':'https://example.test/photo-blue.webp'}])
        self.assertIsNone(lib.find('photo.webp'))

    def test_confirmed_id_resolves_even_if_filename_changed(self):
        lib=self.library([{'id':6,'source_url':'https://example.test/renamed.webp'}])
        self.assertEqual(lib.find('old.webp',{'state':'uploaded','id':6})['id'],6)

    def test_deleted_confirmed_image_not_reused(self):
        self.assertIsNone(self.library([]).find('old.webp',{'state':'uploaded','id':6}))

    def test_site_suffix_does_not_create_a_second_image(self):
        base='valentino-alexia-noir-01__123456789abc'
        lib=self.library([{'id':9,'source_url':'https://example.test/'+base+'.webp'}])
        self.assertEqual(lib.find(base+'-www.example.fr.webp')['id'],9)
        lib=self.library([{'id':9,'source_url':'https://example.test/'+base+'-www.old.fr_.webp'}])
        self.assertEqual(lib.find(base+'-www.new.fr.webp')['id'],9)

    def test_different_source_identifier_never_matches(self):
        lib=self.library([{'id':9,'source_url':'https://example.test/sac-01__123456789abc.webp'}])
        self.assertIsNone(lib.find('sac-01__abcdefabcdef-www.example.fr.webp'))

    def test_suffix_does_not_hide_existing_duplicates(self):
        base='sac-01__123456789abc'
        lib=self.library([{'id':9,'source_url':'https://example.test/'+base+'.webp'}, {'id':10,'source_url':'https://example.test/'+base+'-www.example.fr.webp'}])
        with self.assertRaisesRegex(ConnectionFailure,'Plusieurs images'):
            lib.find(base+'-www.example.fr.webp')
