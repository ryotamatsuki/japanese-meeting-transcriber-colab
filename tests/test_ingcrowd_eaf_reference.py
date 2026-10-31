import unittest
import xml.etree.ElementTree as ET
from scripts.ingcrowd_eaf_reference import (
    ALLOWED_IDS, load_ingcrowd_eaf, clean_annotation)

def mock_eaf():
    root=ET.Element("ANNOTATION_DOCUMENT")
    ET.SubElement(root,"HEADER",TIME_UNITS="milliseconds")
    order=ET.SubElement(root,"TIME_ORDER")
    for i in range(100):
        ET.SubElement(order,"TIME_SLOT",TIME_SLOT_ID=f"ts{i}",
                      TIME_VALUE=str(i*2500))
    for sp in (1,2):
        tier=ET.SubElement(root,"TIER",TIER_ID=f"speaker_{sp}")
        for i in range(sp-1,90,4):
            a=ET.SubElement(ET.SubElement(tier,"ANNOTATION"),
                "ALIGNABLE_ANNOTATION",TIME_SLOT_REF1=f"ts{i}",
                TIME_SLOT_REF2=f"ts{i+1}")
            ET.SubElement(a,"ANNOTATION_VALUE").text="会議ではない自然会話"
    return ET.tostring(root,encoding="utf-8")

class IngcrowdReferenceLoaderTests(unittest.TestCase):
    def test_strict_two_speakers_and_bounded_timing(self):
        raw=mock_eaf()
        rows,meta=load_ingcrowd_eaf(raw,duration=250)
        self.assertGreaterEqual(len(rows),40)
        self.assertEqual(meta["speakers"],2)
        self.assertEqual(len(meta["reference_sha256"]),64)
        self.assertLess(meta["reference_last_end"],250)
        self.assertEqual({r["speaker_id"] for r in rows},
                         {"speaker_1","speaker_2"})
    def test_reject_entity_expansion_and_non_xml(self):
        with self.assertRaises(ValueError):
            load_ingcrowd_eaf(b"<!DOCTYPE a><ANNOTATION_DOCUMENT/>",duration=200)
        with self.assertRaises(ET.ParseError):
            load_ingcrowd_eaf(b"bad xml over the length bound"*10,duration=200)
    def test_reject_no_timeline_and_time_range(self):
        with self.assertRaises(ValueError):
            load_ingcrowd_eaf(mock_eaf(),duration=100)
    def test_clean_tags_without_changing_filler(self):
        self.assertEqual(clean_annotation("(F あの)そうですね"),"あのそうですね")
        self.assertEqual(clean_annotation("(D その) その話"),"その その話")
    def test_dataset_cohort_preregistered(self):
        self.assertEqual(ALLOWED_IDS,("japanese-themed-dialogue01",
            "japanese-themed-dialogue04","japanese-themed-dialogue07"))

if __name__=="__main__":unittest.main()
