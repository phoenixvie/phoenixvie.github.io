import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import source_archive as archive
import run_step

class SourceArchiveTests(unittest.TestCase):
    def fixture(self):
        return {'weekStart':'2026-11-16','restaurants':[{'id':'mensa','status':'ai_checked','days':{'2026-11-16':[{'name':'Gericht','price':6.4}]}}]}

    def test_exact_bytes_are_immutable_deduplicated_and_bound_to_menu_version(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.multiple(archive,STAGING=root/'staging',ARCHIVE=root/'archive'),patch.dict(os.environ,{'WU_SOURCE_CAPTURE':'1','WU_SOURCE_STAGE':'mensa_ai'}):
                raw=b'%PDF-original'
                archive.capture('https://www.wumensa.at/menuplan-deutsch/',raw)
                data=self.fixture();entries=archive.finalize(data,{})
                path=root/'archive'/entries[0]['manifest'];first=path.read_bytes()
                record=json.loads(first)
                blob=root/'archive/blobs'/record['sources'][0]['blob']
                self.assertEqual(blob.read_bytes(),raw)
                self.assertTrue(record['training_review_required'])
                self.assertFalse(record['publication_time_confirmed'])
                self.assertEqual(archive.finalize(data,{}),[])
                data['restaurants'][0]['days']['2026-11-16'][0]['price']=6.5
                self.assertEqual(len(archive.finalize(data,{})),1)
                self.assertEqual(path.read_bytes(),first)
                self.assertEqual(len(list((root/'archive/blobs').iterdir())),1)

    def test_observation_alone_is_not_extraction_evidence_and_capture_is_opt_in(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.multiple(archive,STAGING=root/'staging',ARCHIVE=root/'archive'),patch.dict(os.environ,{'WU_SOURCE_CAPTURE':'0'}):
                archive.capture('https://www.wumensa.at/menuplan-deutsch/',b'%PDF-test')
                self.assertFalse((root/'staging').exists())
                os.environ['WU_SOURCE_CAPTURE']='1';os.environ['WU_SOURCE_STAGE']='observe'
                archive.capture('https://www.wumensa.at/menuplan-deutsch/',b'%PDF-test')
                self.assertEqual(archive.finalize(self.fixture(),{}),[])
                archive.capture('https://user:secret@www.wumensa.at/',b'secret','mensa')
                self.assertEqual(len(archive.requests()),1)

    def test_tampered_staged_bytes_cannot_be_archived(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.multiple(archive,STAGING=root/'staging',ARCHIVE=root/'archive'),patch.dict(os.environ,{'WU_SOURCE_CAPTURE':'1','WU_SOURCE_STAGE':'parser'}):
                archive.capture('https://www.wumensa.at/menuplan-deutsch/',b'%PDF-original')
                row=archive.requests()[0]
                (root/'staging/blobs'/row['blob']).write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'hash mismatch'):
                    archive.finalize(self.fixture(),{})

    def test_run_facts_do_not_invent_a_fetch_or_first_menu_update(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir();(root/'data/menus.json').write_text(json.dumps(self.fixture()),encoding='utf-8')
            with patch.multiple(run_step,ROOT=root,PATH=root/'data/update-status.json'),patch.object(archive,'STAGING',root/'stage'),patch.object(run_step.subprocess,'run') as command:
                command.return_value.returncode=2
                run_step.start();self.assertEqual(run_step.run('parser',['fake']),2);run_step.finish()
                facts=json.loads((root/'data/update-status.json').read_text())
                self.assertEqual(facts['run']['steps'][0]['exit_code'],2)
                self.assertIsNone(facts['last_source_fetch'])
                self.assertIsNone(facts['menus_updated_at'])
                data=self.fixture();data['restaurants'][0]['days']['2026-11-16'][0]['name']='Neu'
                (root/'data/menus.json').write_text(json.dumps(data),encoding='utf-8');run_step.finish()
                self.assertIsNotNone(json.loads((root/'data/update-status.json').read_text())['menus_updated_at'])
