import tempfile
import unittest
from app.service import IndustrialService


class IndustrialServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.NamedTemporaryFile(suffix=".db")
        self.service = IndustrialService(self.temp.name)
        self.asset = self.service.create_asset("M-01", "包装机", "包装一线")
        self.signal = self.service.create_signal(self.asset["id"], "m01.temperature", "电机温度", "℃", high=80)

    def test_alarm_ack_clear_and_work_order(self):
        alarm = self.service.ingest(self.signal["code"], 92)
        self.assertIsNotNone(alarm)
        acknowledged = self.service.acknowledge_alarm(alarm["id"], "张工")
        self.assertEqual("acknowledged", acknowledged["status"])
        order = self.service.create_work_order(self.asset["id"], "检查电机散热", "李工", "high", alarm["id"])
        self.service.complete_work_order(order["id"], "清理风道并复测正常", "李工")
        self.service.clear_alarm(alarm["id"], "李工")
        self.assertEqual(0, self.service.dashboard()["metrics"]["alarms"])

    def test_downtime_and_oee(self):
        down = self.service.start_downtime(self.asset["id"], "换模")
        with self.assertRaises(ValueError): self.service.start_downtime(self.asset["id"], "重复")
        self.service.end_downtime(down["id"])
        result = self.service.record_production(self.asset["id"], 480, 420, 4, 6000, 5880)
        self.assertGreater(result["oee"], 0)
        self.assertLessEqual(result["oee"], 1)

    def test_bad_quality_does_not_raise_alarm(self):
        self.assertIsNone(self.service.ingest(self.signal["code"], 999, "bad"))


if __name__ == "__main__": unittest.main()
