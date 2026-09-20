# 架构与生产边界

HTTP 层只负责认证、限流边界和 JSON；领域服务执行告警、停机、工单与 OEE 规则；SQLite 通过外键、唯一索引和事务保证单机一致性。企业集群部署可迁移到 PostgreSQL/TimescaleDB，同时把遥测入口接到边缘网关或消息队列。

真实 PLC/传感器采集不在本仓库冒充实现，应通过 `zhuatech-edge-gateway` 或现场协议适配器接入。
