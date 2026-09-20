# API 摘要

- `GET /api/dashboard`
- `POST /api/assets`
- `POST /api/signals`
- `POST /api/telemetry`
- `POST /api/work-orders`
- `POST /api/work-orders/{id}/complete`
- `POST /api/alarms/{id}/acknowledge`
- `POST /api/alarms/{id}/clear`
- `POST /api/downtime`
- `POST /api/downtime/{id}/end`
- `POST /api/production`

领域服务还提供告警确认/清除、停机开始/结束、工单完成和生产班次记录，可按企业权限模型暴露为 REST API。
