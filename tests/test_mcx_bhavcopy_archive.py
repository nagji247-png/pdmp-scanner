import json
import tempfile
import unittest
from pathlib import Path
from mcx_bhavcopy_archive import append_session,default_trade_date,filter_contract_rows,write_archive_atomic

def sample(date="06 Nov 2026"):
 return [
  {"InstrumentName":"FUTCOM","Symbol":"GOLD","DateDisplay":date,"ExpiryDate":"04DEC2026","OptionType":"-","OpenInterest":"15771","Close":"142364"},
  {"InstrumentName":"FUTCOM","Symbol":"GOLD","DateDisplay":date,"ExpiryDate":"05FEB2027","OptionType":"-","OpenInterest":"120","Close":"145000"},
  {"InstrumentName":"FUTCOM","Symbol":"SILVER","DateDisplay":date,"ExpiryDate":"05DEC2026","OptionType":"-","OpenInterest":"23000","Close":"180000"},
  {"InstrumentName":"FUTIDX","Symbol":"NIFTY","DateDisplay":date,"ExpiryDate":"10NOV2026","OptionType":"-","OpenInterest":"1","Close":"25000"},
 ]
class MCXBhavcopyArchiveTests(unittest.TestCase):
 def test_default_trade_date_handles_delayed_overnight_run(self):
  delayed=dt.datetime(2026,11,12,4,58,tzinfo=dt.timezone(dt.timedelta(hours=5,minutes=30)))
  self.assertEqual(default_trade_date(delayed).isoformat(),"2026-11-11")
 def test_default_trade_date_uses_current_date_after_eod_window(self):
  after_eod=dt.datetime(2026,11,11,22,50,tzinfo=dt.timezone(dt.timedelta(hours=5,minutes=30)))
  self.assertEqual(default_trade_date(after_eod).isoformat(),"2026-11-11")
 def test_default_trade_date_skips_weekends(self):
  monday_morning=dt.datetime(2026,11,16,4,0,tzinfo=dt.timezone(dt.timedelta(hours=5,minutes=30)))
  self.assertEqual(default_trade_date(monday_morning).isoformat(),"2026-11-13")

 def test_filters_commodity_futcom_and_preserves_expiries(self):
  got=filter_contract_rows(sample(),"2026-11-06")
  self.assertEqual(len(got),3); self.assertEqual([x["Symbol"] for x in got],["GOLD","GOLD","SILVER"])
  self.assertEqual(got[0]["OpenInterest"],15771); self.assertEqual(got[0]["ExpiryDate"],"04DEC2026")
 def test_rejects_wrong_date(self):
  with self.assertRaisesRegex(ValueError,"date mismatch"): filter_contract_rows(sample("05 Nov 2026"),"2026-11-06")
 def test_rejects_duplicate_contract(self):
  x=sample(); x.append(dict(x[0]))
  with self.assertRaisesRegex(ValueError,"Duplicate"): filter_contract_rows(x,"2026-11-06")
 def test_rejects_bad_oi_and_missing_commodity(self):
  x=sample(); x[0]["OpenInterest"]=""
  with self.assertRaisesRegex(ValueError,"Malformed"): filter_contract_rows(x,"2026-11-06")
  with self.assertRaisesRegex(ValueError,"lacks required"): filter_contract_rows([sample()[0]],"2026-11-06")
 def test_appends_once_without_overwriting(self):
  a,ok=append_session({"records":[]},"2026-11-06",sample(),"2026-11-06T17:20:00Z")
  self.assertTrue(ok)
  b,ok2=append_session(a,"2026-11-06",sample(),"2026-11-06T18:20:00Z")
  self.assertFalse(ok2); self.assertEqual(b["records"][0]["captured_at_utc"],"2026-11-06T17:20:00Z")
 def test_atomic_write_produces_complete_json_and_cleans_temp_file(self):
  payload={"schema_version":1,"records":[{"date":"2026-11-06","rows":[1,2,3]}]}
  with tempfile.TemporaryDirectory() as directory:
   target=Path(directory)/"archive.json"
   write_archive_atomic(target,payload)
   self.assertEqual(json.loads(target.read_text(encoding="utf-8")),payload)
   self.assertFalse(target.with_suffix(".json.tmp").exists())
 def test_atomic_write_replaces_previous_complete_snapshot(self):
  with tempfile.TemporaryDirectory() as directory:
   target=Path(directory)/"archive.json"
   target.write_text('{"old":true}',encoding="utf-8")
   payload={"schema_version":1,"records":[{"date":"2026-11-06"}]}
   write_archive_atomic(target,payload)
   self.assertEqual(json.loads(target.read_text(encoding="utf-8")),payload)

 def test_archive_record_includes_deterministic_source_hash(self):
  a,added=append_session({"records":[]},"2026-11-06",sample(),"2026-11-06T17:20:00Z")
  self.assertTrue(added)
  digest=a["records"][0]["normalized_rows_sha256"]
  self.assertEqual(len(digest),64)
  b,added2=append_session({"records":[]},"2026-11-06",sample(),"2026-11-06T18:20:00Z")
  self.assertEqual(b["records"][0]["normalized_rows_sha256"],digest)
 def test_workflow_stages_first_run_archive_before_cached_diff(self):
  workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mcx-eod-archive.yml"
  source = workflow.read_text(encoding="utf-8")
  stage = "git add -f -- mcx_bhavcopy_archive.json"
  diff = "git diff --cached --quiet -- mcx_bhavcopy_archive.json"
  self.assertIn(stage, source)
  self.assertIn(diff, source)
  self.assertLess(source.index(stage), source.index(diff))
  self.assertNotIn("git diff --quiet -- mcx_bhavcopy_archive.json", source)

if __name__=="__main__": unittest.main()
