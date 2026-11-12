import datetime as dt
import unittest
from crowd_trap_detector import build_crowd_trap_snapshot
UTC=dt.timezone.utc
class CrowdTrapDetectorTests(unittest.TestCase):
 def test_completed_candle_direction_and_partial_exclusion(self):
  now=dt.datetime(2026,11,13,10,31,tzinfo=UTC)
  rows=[{"time":dt.datetime(2026,11,13,10,0,tzinfo=UTC),"open":100,"high":102,"low":99,"close":101,"volume":10},
        {"time":dt.datetime(2026,11,13,10,30,tzinfo=UTC),"open":101,"high":103,"low":100,"close":102,"volume":12}]
  out=build_crowd_trap_snapshot(rows,now)
  self.assertEqual(len(out["completed_30m_bars"]),1)
  self.assertEqual(out["price_dir"],1)
  self.assertEqual(out["last_30m"]["close"],101)
 def test_opening_to_close_session(self):
  now=dt.datetime(2026,11,13,10,31,tzinfo=UTC)
  rows=[{"time":dt.datetime(2026,11,13,3,45,tzinfo=UTC),"open":100,"high":101,"low":99,"close":100.5,"volume":10},
        {"time":dt.datetime(2026,11,13,9,30,tzinfo=UTC),"open":100.5,"high":102,"low":100,"close":101,"volume":12}]
  out=build_crowd_trap_snapshot(rows,now)
  self.assertEqual(out["session_open_close"]["open"],100)
  self.assertEqual(out["session_open_close"]["latest_close"],101)
  self.assertEqual(out["session_open_close"]["status"],"complete")
 def test_invalid_ohlc_rejected(self):
  now=dt.datetime(2026,11,13,10,31,tzinfo=UTC)
  rows=[{"time":dt.datetime(2026,11,13,10,0,tzinfo=UTC),"open":100,"high":98,"low":99,"close":101,"volume":10}]
  self.assertIsNone(build_crowd_trap_snapshot(rows,now))

 def test_after_hours_uses_latest_completed_trading_session(self):
  # 00:31 IST on Nov 13; the latest bars belong to Nov 12.
  now=dt.datetime(2026,11,12,19,1,tzinfo=UTC)
  rows=[{"time":dt.datetime(2026,11,12,3,45,tzinfo=UTC),"open":100,"high":101,"low":99,"close":100.5,"volume":10},
        {"time":dt.datetime(2026,11,12,9,30,tzinfo=UTC),"open":100.5,"high":102,"low":100,"close":101,"volume":12}]
  out=build_crowd_trap_snapshot(rows,now)
  self.assertEqual(out["session_open_close"]["market_date"],"2026-11-12")
  self.assertEqual(out["session_open_close"]["status"],"complete")
  self.assertEqual(out["session_open_close"]["open"],100)
  self.assertEqual(out["session_open_close"]["latest_close"],101)

if __name__=="__main__": unittest.main()
