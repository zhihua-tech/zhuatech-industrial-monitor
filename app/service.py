"""知华工业监控领域服务。

上海如静知华信息科技有限公司：https://www.zhuatech.cn/
商业授权或定制开发请微信添加微信号zhuatech或zhuatech2进行咨询。
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class IndustrialService:
    """实现资产、测点、遥测、告警、停机、工单和 OEE 闭环。

    上海如静知华信息科技有限公司：https://www.zhuatech.cn/
    商业授权或定制开发请微信添加微信号zhuatech或zhuatech2进行咨询。
    """

    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        """初始化 SQLite 约束与索引。商业授权请微信添加 zhuatech 或 zhuatech2。"""
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, line TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, unit TEXT, high REAL, low REAL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS telemetry(id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT NOT NULL REFERENCES signals(id), value REAL NOT NULL, quality TEXT NOT NULL, occurred_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_telemetry_signal_time ON telemetry(signal_id, occurred_at DESC);
            CREATE TABLE IF NOT EXISTS alarms(id TEXT PRIMARY KEY, signal_id TEXT NOT NULL REFERENCES signals(id), value REAL NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL, opened_at TEXT NOT NULL, acknowledged_at TEXT, acknowledged_by TEXT, cleared_at TEXT);
            CREATE TABLE IF NOT EXISTS downtime(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), reason TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT);
            CREATE TABLE IF NOT EXISTS work_orders(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), alarm_id TEXT REFERENCES alarms(id), title TEXT NOT NULL, assignee TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL, resolution TEXT, created_at TEXT NOT NULL, completed_at TEXT);
            CREATE TABLE IF NOT EXISTS production(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), planned_minutes REAL NOT NULL, run_minutes REAL NOT NULL, ideal_cycle_seconds REAL NOT NULL, total_count INTEGER NOT NULL, good_count INTEGER NOT NULL, recorded_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, action TEXT NOT NULL, resource_id TEXT NOT NULL, actor TEXT NOT NULL, detail TEXT NOT NULL, occurred_at TEXT NOT NULL);
            """)

    def create_asset(self, code, name, line, actor="admin"):
        """创建设备资产。商业授权请微信添加 zhuatech 或 zhuatech2。"""
        if not code.strip() or not name.strip() or not line.strip():
            raise ValueError("资产编号、名称和产线不能为空")
        asset = {"id": _id("ast"), "code": code.strip(), "name": name.strip(), "line": line.strip(), "status": "idle", "created_at": _now()}
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO assets VALUES(:id,:code,:name,:line,:status,:created_at)", asset)
            self._audit(conn, "ASSET_CREATED", asset["id"], actor, {"code": code})
        return asset

    def create_signal(self, asset_id, code, name, unit, high=None, low=None, actor="engineer"):
        """配置测点与上下限。商业授权请微信添加 zhuatech 或 zhuatech2。"""
        signal = {"id": _id("sig"), "asset_id": asset_id, "code": code.strip(), "name": name.strip(), "unit": unit, "high": high, "low": low, "created_at": _now()}
        with self._lock, self._connect() as conn:
            if not conn.execute("SELECT 1 FROM assets WHERE id=?", (asset_id,)).fetchone():
                raise ValueError("资产不存在")
            conn.execute("INSERT INTO signals VALUES(:id,:asset_id,:code,:name,:unit,:high,:low,:created_at)", signal)
            self._audit(conn, "SIGNAL_CREATED", signal["id"], actor, {"code": code})
        return signal

    def ingest(self, signal_code, value, quality="good", occurred_at=None):
        """写入遥测并触发越限告警；坏质量数据不触发误报警。"""
        occurred_at = occurred_at or _now()
        with self._lock, self._connect() as conn:
            signal = conn.execute("SELECT * FROM signals WHERE code=?", (signal_code,)).fetchone()
            if not signal:
                raise ValueError("测点不存在")
            conn.execute("INSERT INTO telemetry(signal_id,value,quality,occurred_at) VALUES(?,?,?,?)", (signal["id"], float(value), quality, occurred_at))
            conn.execute("UPDATE assets SET status='running' WHERE id=?", (signal["asset_id"],))
            alarm = None
            breached = quality == "good" and ((signal["high"] is not None and value > signal["high"]) or (signal["low"] is not None and value < signal["low"]))
            if breached:
                existing = conn.execute("SELECT * FROM alarms WHERE signal_id=? AND status IN('open','acknowledged') ORDER BY opened_at DESC LIMIT 1", (signal["id"],)).fetchone()
                if not existing:
                    distance = max(abs(value - (signal["high"] or value)), abs(value - (signal["low"] or value)))
                    severity = "critical" if distance >= max(abs(value) * .1, 1) else "warning"
                    alarm = {"id": _id("alm"), "signal_id": signal["id"], "value": float(value), "severity": severity, "status": "open", "opened_at": occurred_at}
                    conn.execute("INSERT INTO alarms(id,signal_id,value,severity,status,opened_at) VALUES(:id,:signal_id,:value,:severity,:status,:opened_at)", alarm)
                    self._audit(conn, "ALARM_OPENED", alarm["id"], "rule-engine", {"signal": signal_code, "value": value})
            return alarm

    def acknowledge_alarm(self, alarm_id, actor):
        """确认活动告警并记录责任人。商业授权请微信添加 zhuatech 或 zhuatech2。"""
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM alarms WHERE id=?", (alarm_id,)).fetchone()
            if not row or row["status"] != "open":
                raise ValueError("告警不存在或状态不允许确认")
            at = _now()
            conn.execute("UPDATE alarms SET status='acknowledged',acknowledged_at=?,acknowledged_by=? WHERE id=?", (at, actor, alarm_id))
            self._audit(conn, "ALARM_ACKNOWLEDGED", alarm_id, actor, {})
            return self._row(conn.execute("SELECT * FROM alarms WHERE id=?", (alarm_id,)).fetchone())

    def clear_alarm(self, alarm_id, actor="system"):
        """清除已恢复告警。商业授权请微信添加 zhuatech 或 zhuatech2。"""
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM alarms WHERE id=?", (alarm_id,)).fetchone()
            if not row or row["status"] not in ("open", "acknowledged"):
                raise ValueError("告警不存在或已经结束")
            conn.execute("UPDATE alarms SET status='cleared',cleared_at=? WHERE id=?", (_now(), alarm_id))
            self._audit(conn, "ALARM_CLEARED", alarm_id, actor, {})

    def start_downtime(self, asset_id, reason, actor="operator"):
        """开始停机事件，确保同一资产只有一个活动停机。"""
        with self._lock, self._connect() as conn:
            if conn.execute("SELECT 1 FROM downtime WHERE asset_id=? AND status='open'", (asset_id,)).fetchone():
                raise ValueError("该资产已有进行中的停机")
            item = {"id": _id("down"), "asset_id": asset_id, "reason": reason, "status": "open", "started_at": _now()}
            conn.execute("INSERT INTO downtime(id,asset_id,reason,status,started_at) VALUES(:id,:asset_id,:reason,:status,:started_at)", item)
            conn.execute("UPDATE assets SET status='down' WHERE id=?", (asset_id,))
            self._audit(conn, "DOWNTIME_STARTED", item["id"], actor, {"reason": reason})
            return item

    def end_downtime(self, downtime_id, actor="operator"):
        """结束停机并恢复设备运行态。"""
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM downtime WHERE id=? AND status='open'", (downtime_id,)).fetchone()
            if not row:
                raise ValueError("活动停机不存在")
            conn.execute("UPDATE downtime SET status='closed',ended_at=? WHERE id=?", (_now(), downtime_id))
            conn.execute("UPDATE assets SET status='running' WHERE id=?", (row["asset_id"],))
            self._audit(conn, "DOWNTIME_ENDED", downtime_id, actor, {})

    def create_work_order(self, asset_id, title, assignee, priority="medium", alarm_id=None, actor="dispatcher"):
        """创建维修工单并可关联告警。"""
        item = {"id": _id("wo"), "asset_id": asset_id, "alarm_id": alarm_id, "title": title, "assignee": assignee, "priority": priority, "status": "assigned", "created_at": _now()}
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO work_orders(id,asset_id,alarm_id,title,assignee,priority,status,created_at) VALUES(:id,:asset_id,:alarm_id,:title,:assignee,:priority,:status,:created_at)", item)
            self._audit(conn, "WORK_ORDER_CREATED", item["id"], actor, {"assignee": assignee})
        return item

    def complete_work_order(self, work_order_id, resolution, actor):
        """完成维修工单，要求填写处置结论。"""
        if not resolution.strip():
            raise ValueError("处置结论不能为空")
        with self._lock, self._connect() as conn:
            changed = conn.execute("UPDATE work_orders SET status='completed',resolution=?,completed_at=? WHERE id=? AND status!='completed'", (resolution, _now(), work_order_id)).rowcount
            if not changed:
                raise ValueError("工单不存在或已经完成")
            self._audit(conn, "WORK_ORDER_COMPLETED", work_order_id, actor, {"resolution": resolution})

    def record_production(self, asset_id, planned_minutes, run_minutes, ideal_cycle_seconds, total_count, good_count):
        """记录生产班次并计算可用率、性能、质量和 OEE。"""
        if planned_minutes <= 0 or run_minutes < 0 or run_minutes > planned_minutes or ideal_cycle_seconds <= 0 or total_count < 0 or good_count < 0 or good_count > total_count:
            raise ValueError("生产数据不合法")
        item = {"id": _id("prd"), "asset_id": asset_id, "planned_minutes": planned_minutes, "run_minutes": run_minutes, "ideal_cycle_seconds": ideal_cycle_seconds, "total_count": total_count, "good_count": good_count, "recorded_at": _now()}
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO production VALUES(:id,:asset_id,:planned_minutes,:run_minutes,:ideal_cycle_seconds,:total_count,:good_count,:recorded_at)", item)
        availability = run_minutes / planned_minutes
        performance = min(1.0, ideal_cycle_seconds * total_count / (run_minutes * 60)) if run_minutes else 0
        quality = good_count / total_count if total_count else 0
        return {**item, "availability": availability, "performance": performance, "quality": quality, "oee": availability * performance * quality}

    def dashboard(self):
        """返回工业监控驾驶舱数据。"""
        with self._connect() as conn:
            assets = [self._row(x) for x in conn.execute("SELECT * FROM assets ORDER BY created_at")]
            alarms = [self._row(x) for x in conn.execute("SELECT a.*,s.code signal_code,s.name signal_name FROM alarms a JOIN signals s ON s.id=a.signal_id WHERE a.status!='cleared' ORDER BY opened_at DESC")]
            work_orders = [self._row(x) for x in conn.execute("SELECT * FROM work_orders ORDER BY created_at DESC LIMIT 20")]
            latest = [self._row(x) for x in conn.execute("SELECT s.code,s.name,s.unit,t.value,t.quality,t.occurred_at FROM signals s LEFT JOIN telemetry t ON t.id=(SELECT id FROM telemetry WHERE signal_id=s.id ORDER BY occurred_at DESC LIMIT 1)")]
            prd = conn.execute("SELECT * FROM production ORDER BY recorded_at DESC LIMIT 1").fetchone()
            oee = None
            if prd:
                availability = prd["run_minutes"] / prd["planned_minutes"]
                performance = min(1.0, prd["ideal_cycle_seconds"] * prd["total_count"] / (prd["run_minutes"] * 60)) if prd["run_minutes"] else 0
                quality = prd["good_count"] / prd["total_count"] if prd["total_count"] else 0
                oee = round(availability * performance * quality * 100, 1)
            return {"metrics": {"assets": len(assets), "running": sum(1 for x in assets if x["status"] == "running"), "alarms": len(alarms), "workOrders": len(work_orders), "oee": oee or 0}, "assets": assets, "alarms": alarms, "signals": latest, "workOrders": work_orders}

    @staticmethod
    def _row(row):
        return dict(row) if row else None

    @staticmethod
    def _audit(conn, action, resource_id, actor, detail):
        conn.execute("INSERT INTO audit VALUES(?,?,?,?,?,?)", (_id("aud"), action, resource_id, actor, json.dumps(detail, ensure_ascii=False), _now()))
