# SatHub — 影像数据管理平台（开源版）

轻量级、可私有部署的卫星影像数据管理平台：把散落在个人电脑、硬盘和服务器里的影像汇聚到一处，自动解析编目，秒级检索，浏览器里直接在地图上看图。

开源版覆盖影像工作流中的"数据之家"环节：

```
接入 -> 编目（STAC） -> 检索 -> 地图预览 -> 组织（数据集）
```

完整文档请阅读 [README.md](README.md)。

## 功能

- **多方式接入**：URL 链接导入、ZIP/7Z 压缩包上传、浏览器整目录上传；每次接入都是异步任务，逐条可见、失败可重试。
- **自动解析编目**：读取栅格元数据（GDAL/rasterio）、STAC Item 与厂商 JSON 配套文件（Capella、Umbra、ICEYE），自动提取 footprint、分辨率、采集时间；每景生成一个 STAC Item 并写入 DuckDB 检索索引。
- **自动去重**：基于 SHA-256 指纹跨用户去重，同一景数据只存一份，重复上传自动复用并补打项目标签。
- **检索**：关键词、卫星、传感器、级别、极化、时间范围与分面自由组合；地图框选、多边形绘制（相交/包含/被包含）；保存查询一键复用。
- **一张图**：全部 footprint 上图，点选即叠加预览图，透明度可调；厂商 TIFF 快视自动转码为浏览器可显示的 JPEG。
- **预览图生成**：无配套预览的影像在入库时自动生成降采样缓存预览，保证每一景都能在地图上看到。
- **数据集**：静态数据集（手工挑选、排序）与动态数据集（按查询条件自动圈定、入库自动刷新）。
- **STAC API**：只读 STAC API（`/api/stac/`），支持 bbox / datetime / query 检索，第三方工具可直接消费。
- **轻量治理**：账号登录、项目标签、软归档、显示名称编辑、索引重建。

## 开源版不包含的内容

以下能力属于商业版，本仓库有意不包含：

- 瓦片服务发布（XYZ / TileJSON / OGC API Tiles，单景与镶嵌）
- 在线处理（裁剪、波段选择、波段运算）
- 交付（数据篮、带校验的 ZIP 清单、交付版本冻结）
- 存储端点扫描（NAS/S3 登记、定时扫描、对账）
- 可配置元数据解析模板、分类/标签/行政区治理、审计日志、API 令牌鉴权

开源版只在自己的地图内渲染影像，不对外提供瓦片服务端点。

## 快速开始

```bash
# Docker Compose
docker compose up --build
# 后端 http://localhost:8000 ，前端 http://localhost:8080
docker compose exec backend python manage.py seed_sample_data

# 或手动部署
cd backend && pip install -r requirements.txt
python manage.py migrate
python manage.py seed_sample_data
python manage.py run_ingestion_worker   # 独立终端
python manage.py runserver 127.0.0.1:8000

cd frontend && npm ci && npm run dev -- --host 127.0.0.1
```

使用演示账号登录（`demo` / `demo1234`），打开地图即可看到三景示例影像与预览图。底图使用天地图时，在 `frontend/.env` 配置自己的 `VITE_TIANDITU_TOKEN`。

## 许可证

[Apache-2.0](LICENSE)
