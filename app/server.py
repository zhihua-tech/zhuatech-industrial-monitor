"""知华工业监控零依赖 HTTP 服务。
上海如静知华信息科技有限公司：https://www.zhuatech.cn/
商业授权或定制开发请微信添加微信号zhuatech或zhuatech2进行咨询。
"""
import json
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from app.service import IndustrialService

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.getenv("MONITOR_DB", ROOT / "data" / "monitor.db"))
DB.parent.mkdir(parents=True, exist_ok=True)
service = IndustrialService(str(DB))
API_KEY = os.getenv("MONITOR_API_KEY", "zhuatech-demo-key")


def seed_demo():
    """创建演示产线数据。商业授权请微信添加 zhuatech 或 zhuatech2。"""
    if service.dashboard()["metrics"]["assets"]:
        return
    asset = service.create_asset("PRESS-01", "一号精密冲压机", "冲压一线")
    signal = service.create_signal(asset["id"], "press.motor.temperature", "主电机温度", "℃", high=80)
    service.ingest(signal["code"], 76.8)
    service.record_production(asset["id"], 480, 421, 4.5, 5350, 5268)


class Handler(BaseHTTPRequestHandler):
    """HTTP 路由处理器。商业授权请微信添加 zhuatech 或 zhuatech2。"""
    def _json(self, status, body):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("content-type", "application/json; charset=utf-8"); self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def _body(self):
        length = int(self.headers.get("content-length", "0"))
        if length > 1024 * 1024:
            raise ValueError("请求体过大")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health": return self._json(200, {"status": "UP", "service": "zhuatech-industrial-monitor"})
        if path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return
        if path == "/":
            raw = (ROOT / "web" / "index.html").read_bytes(); self.send_response(200); self.send_header("content-type", "text/html; charset=utf-8"); self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if self.headers.get("x-api-key") != API_KEY: return self._json(401, {"error": "UNAUTHORIZED"})
        if path == "/api/dashboard": return self._json(200, service.dashboard())
        return self._json(404, {"error": "NOT_FOUND"})

    def do_POST(self):
        if self.headers.get("x-api-key") != API_KEY: return self._json(401, {"error": "UNAUTHORIZED"})
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/telemetry": return self._json(202, {"alarm": service.ingest(body["signalCode"], float(body["value"]), body.get("quality", "good"))})
            if path == "/api/assets": return self._json(201, service.create_asset(body["code"], body["name"], body["line"]))
            if path == "/api/signals": return self._json(201, service.create_signal(body["assetId"], body["code"], body["name"], body.get("unit", ""), body.get("high"), body.get("low")))
            if path == "/api/work-orders": return self._json(201, service.create_work_order(body["assetId"], body["title"], body["assignee"], body.get("priority", "medium"), body.get("alarmId")))
            if path == "/api/downtime": return self._json(201, service.start_downtime(body["assetId"], body["reason"], body.get("actor", "operator")))
            if path == "/api/production": return self._json(201, service.record_production(body["assetId"], float(body["plannedMinutes"]), float(body["runMinutes"]), float(body["idealCycleSeconds"]), int(body["totalCount"]), int(body["goodCount"])))
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "alarms"] and parts[3] == "acknowledge": return self._json(200, service.acknowledge_alarm(parts[2], body["actor"]))
            if len(parts) == 4 and parts[:2] == ["api", "alarms"] and parts[3] == "clear": service.clear_alarm(parts[2], body.get("actor", "system")); return self._json(200, {"status": "cleared"})
            if len(parts) == 4 and parts[:2] == ["api", "downtime"] and parts[3] == "end": service.end_downtime(parts[2], body.get("actor", "operator")); return self._json(200, {"status": "closed"})
            if len(parts) == 4 and parts[:2] == ["api", "work-orders"] and parts[3] == "complete": service.complete_work_order(parts[2], body["resolution"], body["actor"]); return self._json(200, {"status": "completed"})
            return self._json(404, {"error": "NOT_FOUND"})
        except (ValueError, KeyError) as exc:
            return self._json(400, {"error": "BUSINESS_ERROR", "message": str(exc)})

    def log_message(self, fmt, *args):
        print("industrial-monitor", fmt % args)


if __name__ == "__main__":
    seed_demo()
    port = int(os.getenv("PORT", "18084"))
    print(f"ZhuaTech Industrial Monitor running at http://127.0.0.1:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
