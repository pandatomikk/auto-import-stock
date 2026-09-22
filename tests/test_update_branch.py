import json
from pathlib import Path
import tempfile
import unittest
from core import updater

class UpdateBranchTests(unittest.TestCase):
    def test_dev_distribution_follows_dev_without_changing_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for branch in ('main','dev'):
                (root/updater.STATE).write_text(json.dumps({'managed':True,'repository':updater.REPOSITORY,'revision':'a'*40,'branch':branch}))
                urls=[]
                def fetch(url,limit):
                    urls.append(url)
                    return json.dumps({'sha':'b'*40,'commit':{'message':'test'}}).encode()
                updater.check_update(root,fetch)
                self.assertTrue(urls[0].endswith('/commits/'+branch))
