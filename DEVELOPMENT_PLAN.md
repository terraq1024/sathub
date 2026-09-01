# 内部卫星影像统一接入与管理系统开发方案

## 1. 项目定位

项目名称建议为 **内部卫星影像统一接入与管理系统**，英文名可用 **Ingestion & Imagery Hub**。

系统目标不是建设完整 GIS 平台、遥感处理平台或大数据平台，而是建设一个轻量的内部影像入口：

- 统一接入：URL、压缩包、文件夹打包上传。
- 统一索引：把影像文件解析成可检索元数据。
- 在线浏览：后续通过 COG + TiTiler + Leaflet 预览。
- 可追溯：保留上传人、项目、来源、任务、文件路径、解析日志。

当前仓库 `D:\code\airmap` 已完成从 v1 到 v6 的主体实现；前述早期方案保留为演进背景，当前实施基线以文末 v6、v7 章节为准。

## 2. 技术选型

### 2.1 后端

- 后端框架：Django + Django REST Framework。
- 权限体系：使用 Django 自带 `User`、`Group`、`Permission`、Admin、SessionAuth、CSRF。
- 业务数据库：Django 默认数据库，MVP 可用 SQLite，内网部署建议 PostgreSQL。
- 影像索引库：DuckDB。
- 后台任务：MVP 使用 Django management command 轮询任务，不引入 Celery/Redis。
- 影像解析：GDAL/rasterio 优先；文件名规则作为补充解析。
- STAC 生成与校验：建议引入 `pystac`。

### 2.2 前端

- 前端框架：Vite + React + TypeScript。
- UI 组件：Ant Design v5 原生组件。
- 地图组件：Leaflet。
- 数据请求：React Query + typed fetch。
- 不自造通用 UI 组件库；表格、表单、上传、弹窗、抽屉、进度、标签等全部优先使用 Ant Design 原生组件。

### 2.3 影像服务

- 第一阶段只完成入库和检索。
- 第二阶段引入 COG 转换。
- 第三阶段引入 TiTiler + Leaflet 在线预览。

## 3. 总体架构

```text
frontend/
  React + Ant Design + Leaflet

backend/
  Django + DRF + Django Auth/Admin

data/
  staging/   # 上传暂存
  raw/       # 原始影像
  cog/       # COG 标准影像
  thumb/     # 缩略图
  exports/   # 导出包

duckdb/
  imagery.duckdb

worker/
  Django management command:
  python manage.py run_ingestion_worker
```

核心原则：

- Django 负责用户、权限、项目、任务、任务子项和后台管理。
- DuckDB 负责影像检索索引。
- STAC 负责每景影像的标准化元数据表达。
- 文件系统/NAS 负责真实文件存储。

## 4. STAC 引入方案

### 4.1 STAC 在系统中的角色

STAC 不替代 Django 权限，也不替代 DuckDB 检索。它作为影像元数据的标准表达层：

- 每一景影像生成一个 STAC Item。
- 每个项目或数据集可生成一个 STAC Collection。
- 系统内部保留完整 STAC JSON。
- DuckDB 只抽取高频检索字段。
- 后续可扩展为 STAC API，对外提供标准影像目录服务。

### 4.2 STAC 对象映射

| 系统概念 | STAC 概念 | 说明 |
|---|---|---|
| Project | Collection | 一个项目可对应一个 STAC Collection |
| Imagery | Item | 每景影像对应一个 STAC Item |
| 原始文件 | Asset | key 为 `raw` |
| COG 文件 | Asset | key 为 `cog` |
| 缩略图 | Asset | key 为 `thumbnail` |
| sidecar XML/JSON | Asset | key 为 `metadata` |
| bbox/geometry | Item bbox/geometry | 从 GeoTIFF/GDAL 解析 |
| acquisition_time | properties.datetime | 采集时间，UTC |
| satellite/sensor | properties.platform / instruments | 用 STAC common metadata 表达 |

### 4.3 STAC Item 最小字段

每景影像至少生成：

```json
{
  "type": "Feature",
  "stac_version": "1.0.0",
  "id": "AS05_AR_TD_003485_E117.1_N31.3_20260406020232_L2_HH_05_001",
  "collection": "project-<project_id>",
  "geometry": null,
  "bbox": null,
  "properties": {
    "datetime": "2026-04-05T18:02:32Z",
    "platform": "AS05",
    "sar:polarizations": ["HH"],
    "processing:level": "L2",
    "airmap:source_name": "AS05_AR_TD_003485_E117.1_N31.3_20260406020232_L2_HH_05_001"
  },
  "links": [],
  "assets": {
    "raw": {
      "href": "file:///data/raw/...",
      "type": "image/tiff; application=geotiff",
      "roles": ["data"]
    }
  }
}
```

注意：

- `geometry` 和 `bbox` 最终应优先从影像真实空间参考解析，不能只依赖文件名中心点。
- 如果暂时只有中心点 `E117.1_N31.3`，可先写入自定义属性 `airmap:center_lon`、`airmap:center_lat`，并把影像空间状态标记为 `spatial_pending`。
- 文件名中的时间是北京时间还是 UTC 需要通过数据源规则确认。若不能确认，先按本地项目默认时区 `Asia/Shanghai` 解析，再转换成 UTC，同时保留 `airmap:time_assumption`。

### 4.4 示例文件名解析

样例路径：

```text
D:\BaiduNetdiskDownload\4-上海铁路合肥工务段遥感监测项目（售前）\1-遥感数据\SAR\AS05_AR_TD_003485_E117.1_N31.3_20260406020232_L2_HH_05_001
```

建议解析对象名：

```text
AS05_AR_TD_003485_E117.1_N31.3_20260406020232_L2_HH_05_001
```

可解析字段：

| 片段 | 字段 | 值 |
|---|---|---|
| `AS05` | satellite/platform | AS05 |
| `AR` | mode 或产品代码 | AR，先保留为 `airmap:mode_code` |
| `TD` | direction/orbit/product code | TD，先保留为 `airmap:direction_code` |
| `003485` | scene/track/order id | 003485 |
| `E117.1` | center_lon | 117.1 |
| `N31.3` | center_lat | 31.3 |
| `20260406020232` | acquisition_time | 2026-04-06 02:02:32 |
| `L2` | processing level | L2 |
| `HH` | SAR polarization | HH |
| `05` | version/batch code | 05 |
| `001` | sequence | 001 |

建议解析正则：

```regex
^(?P<platform>[A-Z0-9]+)_(?P<mode>[A-Z0-9]+)_(?P<direction>[A-Z0-9]+)_(?P<scene_id>\d+)_(?P<lon>[EW]\d+(?:\.\d+)?)_(?P<lat>[NS]\d+(?:\.\d+)?)_(?P<datetime>\d{14})_(?P<level>L\d+)_(?P<polarization>[A-Z]{2})_(?P<version>\d+)_(?P<sequence>\d+)$
```

经纬度转换规则：

- `E117.1` -> `117.1`
- `W117.1` -> `-117.1`
- `N31.3` -> `31.3`
- `S31.3` -> `-31.3`

时间转换规则：

- 文件名时间先解析为 naive datetime：`2026-04-06 02:02:32`。
- 默认按 `Asia/Shanghai` 解释，则 STAC UTC 时间为 `2026-04-05T18:02:32Z`。
- 如果后续确认源文件时间已经是 UTC，则解析规则改为直接 `2026-04-06T02:02:32Z`。

### 4.5 STAC 与 DuckDB 的关系

DuckDB 中不需要把 STAC JSON 拆成所有字段，只保存：

- 高频检索字段。
- 权限过滤字段。
- 文件定位字段。
- 完整 STAC JSON 字符串。

建议 DuckDB 表：

```sql
CREATE TABLE imagery_index (
    image_id VARCHAR PRIMARY KEY,
    stac_id VARCHAR NOT NULL,
    collection_id VARCHAR,
    project_id VARCHAR NOT NULL,
    owner_id VARCHAR NOT NULL,
    job_id VARCHAR,
    item_id VARCHAR,
    source_name VARCHAR,
    file_path VARCHAR NOT NULL,
    raw_path VARCHAR,
    cog_path VARCHAR,
    thumbnail_path VARCHAR,
    platform VARCHAR,
    sensor VARCHAR,
    product_level VARCHAR,
    polarization VARCHAR,
    acquisition_time TIMESTAMP,
    center_lon DOUBLE,
    center_lat DOUBLE,
    min_lon DOUBLE,
    min_lat DOUBLE,
    max_lon DOUBLE,
    max_lat DOUBLE,
    epsg INTEGER,
    spatial_status VARCHAR,
    status VARCHAR NOT NULL,
    stac_json JSON,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

常用查询字段：

- `project_id`
- `owner_id`
- `platform`
- `sensor`
- `product_level`
- `polarization`
- `acquisition_time`
- `min_lon/min_lat/max_lon/max_lat`
- `source_name`

## 5. Django 数据模型

### 5.1 Project

字段：

- `id`
- `name`
- `code`
- `description`
- `created_by`
- `created_at`
- `updated_at`

### 5.2 ProjectMembership

字段：

- `id`
- `project`
- `user`
- `role`: `owner` / `member` / `viewer`
- `created_at`

访问规则：

- 普通用户可访问自己上传的数据。
- 普通用户可访问自己所在项目的数据。
- Django superuser/staff 可访问全部数据。

### 5.3 IngestionJob

字段：

- `id`
- `created_by`
- `project`
- `source_type`: `url_text` / `zip_upload` / `folder_zip`
- `status`: `pending` / `running` / `parsing` / `storing` / `done` / `failed` / `canceled`
- `total_count`
- `success_count`
- `failed_count`
- `source_payload`
- `error_message`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

### 5.4 IngestionItem

字段：

- `id`
- `job`
- `source`
- `source_kind`: `url` / `archive_member` / `file`
- `status`: `pending` / `downloading` / `extracting` / `parsing` / `storing` / `done` / `failed`
- `raw_path`
- `cog_path`
- `stac_id`
- `image_id`
- `error_message`
- `retry_count`
- `created_at`
- `updated_at`

## 6. 后端模块划分

建议 Django app：

```text
backend/
  config/
  apps/
    accounts/
    projects/
    ingestion/
    imagery/
    downloads/
```

### 6.1 accounts

- 使用 Django 内置用户体系。
- 通过 Django Admin 管理用户、用户组、权限。
- API 提供登录、登出、当前用户、CSRF 获取。

### 6.2 projects

- 管理项目。
- 管理用户与项目关系。
- API 返回当前用户可访问项目列表。

### 6.3 ingestion

- 创建 URL 导入任务。
- 创建 zip 上传任务。
- 维护 job/item 状态。
- worker 执行下载、解压、扫描、解析、入库。

### 6.4 imagery

- DuckDB 查询封装。
- 影像列表检索。
- 影像详情。
- STAC Item JSON 查看。

### 6.5 downloads

第二阶段实现：

- 单影像原始文件下载。
- 查询结果 manifest 导出。
- 按 job 批量打包下载。

## 7. API 设计

### 7.1 Auth

```text
GET  /api/auth/csrf
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

### 7.2 Projects

```text
GET /api/projects
```

### 7.3 Ingestion

```text
POST /api/ingestion/jobs/url-import
POST /api/ingestion/jobs/upload-zip
GET  /api/ingestion/jobs
GET  /api/ingestion/jobs/{job_id}
GET  /api/ingestion/jobs/{job_id}/items
POST /api/ingestion/items/{item_id}/retry
```

### 7.4 Imagery

```text
GET /api/imagery
GET /api/imagery/{image_id}
GET /api/imagery/{image_id}/stac
```

影像检索参数：

- `project_id`
- `platform`
- `sensor`
- `product_level`
- `polarization`
- `time_start`
- `time_end`
- `bbox`
- `q`
- `page`
- `page_size`

## 8. Ingestion 流程

### 8.1 URL 文本导入

1. 前端提交 URL 多行文本和 `project_id`。
2. Django 创建 `IngestionJob`。
3. 每个 URL 创建一个 `IngestionItem`。
4. worker 下载文件到 `data/staging/<job_id>/`。
5. 如果是压缩包则解压。
6. 扫描影像文件。
7. 解析空间信息与文件名元数据。
8. 生成 STAC Item。
9. 原始文件移动到 `data/raw/<project_id>/<job_id>/`。
10. 写入 DuckDB。
11. 更新 item/job 状态。

### 8.2 zip 上传

1. 前端使用 AntD `Upload.Dragger` 上传 zip。
2. Django 保存到 staging。
3. 创建 job 和初始 item。
4. worker 解压。
5. 扫描 `.tif`、`.tiff`、`.jp2`、`.vrt` 等文件。
6. 每个影像文件生成子 item 或派生 item 记录。
7. 解析元数据、生成 STAC、写入 DuckDB。

### 8.3 文件夹上传

第一版不直接实现浏览器原生文件夹上传的复杂逻辑。前端提示用户选择文件夹后打包为 zip，后端按 zip 上传处理。

## 9. 前端页面方案

### 9.1 Layout

使用 Ant Design：

- `Layout`
- `Sider`
- `Menu`
- `Breadcrumb`
- `Avatar`
- `Dropdown`

导航：

- 任务中心
- URL 导入
- 压缩包导入
- 影像检索
- 项目选择

### 9.2 登录页

使用：

- `Form`
- `Input`
- `Button`
- `Alert`

### 9.3 任务中心

使用：

- `Table`
- `Tag`
- `Progress`
- `Button`
- `Space`
- `Drawer`
- `Descriptions`

展示：

- job id
- 项目
- 来源类型
- 状态
- 总数/成功/失败
- 创建人
- 创建时间
- 完成时间

### 9.4 URL 导入

使用：

- `Form`
- `Select`
- `Input.TextArea`
- `Button`
- `Alert`

### 9.5 压缩包导入

使用：

- `Upload.Dragger`
- `Form`
- `Select`
- `Progress`
- `Result`

### 9.6 影像检索

使用：

- `Form`
- `DatePicker.RangePicker`
- `Select`
- `Input.Search`
- `Table`
- `Drawer`
- `Descriptions`
- `Tag`

第二阶段加入 Leaflet 地图预览：

- 列表点击影像后地图定位 bbox。
- COG 可用时加载 TiTiler tile layer。

## 10. 开发阶段

### 第一阶段：MVP

必须完成：

- Django 项目初始化。
- Django Auth/Admin 接入。
- Project 和 ProjectMembership。
- IngestionJob 和 IngestionItem。
- URL 导入。
- zip 上传。
- 文件扫描。
- 文件名元数据解析。
- GDAL/rasterio 空间元数据解析。
- STAC Item 生成。
- DuckDB 入库。
- 基础检索 API。
- Ant Design 前端基础页面。

### 第二阶段：影像可视化与下载

- COG 转换。
- 缩略图生成。
- TiTiler 服务接入。
- Leaflet 地图预览。
- 单影像下载。
- job 批量导出。

### 第三阶段：增强管理能力

- 失败任务重试优化。
- 批量导入性能优化。
- STAC Catalog/Collection 静态导出。
- 可选 STAC API。
- 更完整的项目权限管理 UI。
- 操作审计日志。

## 11. 测试计划

### 11.1 后端测试

- 登录/登出/当前用户。
- 项目权限过滤。
- URL 导入创建 job 和 items。
- zip 上传创建 job。
- worker 成功处理影像。
- worker 处理坏文件并记录失败。
- 文件名解析样例：
  - `AS05_AR_TD_003485_E117.1_N31.3_20260406020232_L2_HH_05_001`
- STAC Item 生成字段完整性。
- DuckDB 按项目、时间、平台、极化方式检索。

### 11.2 前端测试

- 登录态展示。
- 任务中心状态展示。
- URL 导入表单校验。
- zip 上传进度和错误提示。
- 影像检索参数构造。
- 影像详情抽屉展示 STAC 摘要。

### 11.3 验收标准

- 用户可以登录系统。
- 所有登录用户可看到全量影像；项目仅作为可选标签。
- 用户可以提交 URL 文本任务。
- 用户可以上传 zip、7z、解压文件夹并提交下载链接任务。
- worker 能解析至少一种 SAR 文件名规则。
- 入库后能在影像检索页查到数据。
- 每景影像能查看对应 STAC JSON。

## 12. 关键约束与默认假设

- 第一阶段不做复杂 GIS 分析。
- 第一阶段不做完整 STAC API，只生成和保存 STAC Item JSON。
- 第一阶段不强制 COG，COG 在第二阶段实现。
- 若文件名与真实影像元数据冲突，以 GDAL/rasterio 读取结果优先。
- 文件名解析结果需要标记 `metadata_source=filename`。
- 真实空间 bbox 需要标记 `metadata_source=gdal`。
- 时间默认按 `Asia/Shanghai` 解析并转换 UTC，后续可按数据源配置修正。

## 13. 参考规范

- STAC Item 是 GeoJSON Feature 的扩展，核心字段包括 `id`、`geometry`、`bbox`、`properties`、`links`、`assets`。
- STAC Item 的 `properties.datetime` 是可检索时间，要求使用 UTC。
- STAC Item 的 assets 用于描述可下载或可流式访问的数据文件，建议包含 data 和 thumbnail。
- STAC Collection 用于表达一组 Items 的集合信息，适合映射系统中的项目或数据集。

## 14. v2 实施更新

v2 将项目标签与影像访问权限解耦。影像由 `ImageryRecord` 全局唯一管理，项目通过 `ImageryProjectTag` 作为可选分类标签；所有登录用户可以检索、预览和下载影像，任务仍按创建人限制普通用户查看。

接入方式包括 HTTP/HTTPS 下载链接、ZIP、7Z 和浏览器目录上传。7Z 使用 `py7zr`，ZIP 使用 Python `zipfile`，所有输入先进入 staging，再扫描同名产品组。产品组以 TIFF/JP2 为主数据，配套识别同名 JPG、thumb JPG、meta XML、incidence XML、result XML 和 log。

元数据以 AIRSAT `meta.xml` 为最高优先级，解析卫星代码与名称、传感器、成像模式、极化串、产品级别、采集时间、轨道方向、侧视方向、分辨率、像元间距、影像尺寸和四角坐标。四角坐标生成 WGS84 GeoJSON footprint；没有 footprint 时回退到栅格边界或文件名中心点并标记空间质量状态。无时区时间按 `Asia/Shanghai` 解析后转 UTC。

STAC 使用单一 `airmap-imagery` Collection，每一景生成一个 Item，项目标签写入 `airmap:project_ids`。Item 资产包括 `data`、`preview`、`thumbnail`、`metadata`、`incidence` 和 `log`。DuckDB 仅作为检索投影，Django 数据库负责唯一性、资产关系和权限。

去重优先使用 XML `Productid`，否则使用规范化产品主名，并通过 SHA-256 identity hash 建唯一约束。重复上传标记为 `skipped`，复用已有文件和 STAC；指定新项目时只增加项目标签，不复制文件。

地图不依赖 TiTiler。地图接口返回 GeoJSON footprint，详情页和地图叠加层通过安全资产接口加载同名 JPG；没有 JPG 时展示缺失状态。

## 15. v3 前端信息架构与影像管理工作台

### 15.1 一级入口

平台一级导航收敛为两个业务入口：

- `影像管理`：统一承载影像目录、影像导入和接入任务。
- `影像一张图`：全屏地图检索、footprint 定位、JPG 预览和单景详情。

原 `Task Center`、`URL Import`、`ZIP / 7Z Upload`、`Folder Upload` 不再作为一级菜单出现，功能和现有接口保持兼容。

### 15.2 影像管理页面

使用 Ant Design 原生 `Tabs` 组织三个工作区：

1. `影像目录`
   - 表格浏览已入库影像。
   - 表格首列展示稳定尺寸的缩略图。
   - 支持列表和缩略图卡片两种视图，共用筛选、分页和详情状态。
   - 详情侧栏内使用 Leaflet 按 footprint 定位，并叠加 preview JPG；preview 缺失时回退 thumbnail。
   - 支持关键词、平台、产品级别、极化方式和项目标签筛选。
   - 支持查看单景结构化信息和下载已有资产。
   - 后续补充编辑标签、修复元数据、软删除及审计记录；在后端具备相应事务和引用清理能力前不提供破坏性删除按钮。
2. `导入影像`
   - 使用 `Segmented` 切换 `URL`、`压缩包`、`文件夹` 三种接入方式。
   - 复用现有 URL、ZIP/7Z 和目录上传流程、校验、进度与反馈。
3. `接入任务`
   - 复用任务列表、状态轮询、任务明细和失败项重试。

Tab 状态保留在页面内；完成导入后用户可直接切换到接入任务查看处理进度，不再跨一级页面跳转。

### 15.3 影像一张图

- 保持 Leaflet 占满业务内容区。
- 检索与结果列表继续作为地图左侧浮层。
- 点击 footprint 后才加载 JPG，并在地图右侧显示窄幅单列详情栏。
- STAC JSON 暂不在业务页面展示，但仍保留后端 STAC 接口和文件。

### 15.4 实施范围与验收

- 一级菜单只显示 `影像管理`、`影像一张图`。
- 影像管理默认进入影像目录。
- 三种导入方式均可在同一页面切换和提交。
- 接入任务在同一页面可查看、刷新、展开明细和重试失败项。
- 现有后端 URL 和数据模型保持兼容。
- `npm run type-check`、`npm run build` 和 Ant Design lint 通过。

## 16. v4 影像服务发布与生命周期管理

### 16.1 信息架构

新增一级入口 `影像服务`。影像目录提供单景影像的 `发布服务` 快捷动作，发布后的状态、配置、访问地址、上下线和失败重试统一在影像服务页面管理。影像数据与服务记录分离，允许后续支持一景多服务、多景镶嵌和不同渲染方案。

### 16.2 服务模型

- `ImageryService`
  - 服务名称、稳定 `service_key`、服务类型、可见性。
  - 状态：`draft / validating / preparing / publishing / online / degraded / offline / failed / archived`。
  - TiTiler 基础地址、COG 路径、渲染配置、错误信息和发布时间。
- `ImageryServiceAsset`
  - 关联服务与影像，保存资产角色、波段映射和顺序。
- `ServicePublishJob`
  - 保存发布动作、状态、当前步骤、进度、错误和起止时间。

### 16.3 发布流程

1. 影像目录创建服务草稿和发布任务。
2. `run_service_worker` 异步检查单景或数据集成员的主数据和地理参考。
3. 使用 Rasterio/GDAL COG 驱动生成或复用 `data/cog/<image_id>.tif`；数据集服务再生成稳定 MosaicJSON。
4. 重新打开 COG，校验 CRS、范围、尺寸和 overview。
5. 调用配置的 TiTiler `/cog/info` 或 `/mosaicjson/info` 探测可读性。
6. 探测成功后服务进入 `online`，失败进入 `failed` 并保留错误，可重新发布。

Web 请求不执行大文件转换，避免阻塞 Django 进程。

### 16.4 稳定服务 API

```text
GET  /api/services
POST /api/services
GET  /api/services/{service_key}
PATCH /api/services/{service_key}
POST /api/services/{service_key}/publish
POST /api/services/{service_key}/offline
GET  /api/services/{service_key}/jobs
GET  /api/services/{service_key}/tilejson
GET  /api/services/{service_key}/tiles/{z}/{x}/{y}.png
```

Django 负责用户权限、服务状态和稳定 URL，并代理内部 TiTiler 请求。外部客户端不能提交本地文件路径；TiTiler 的 `url` 参数只由服务端根据已登记 COG 构造。

### 16.5 第一阶段边界

- 支持单景 GeoTIFF/COG 的 XYZ 和 TileJSON 发布。
- 支持服务列表、发布进度、上线、下线和失败重试。
- 服务列表提供 Leaflet 在线预览，直接加载对外 XYZ 地址并按服务 bbox 定位，用于验证服务端代理、权限和瓦片渲染链路。
- 默认渲染配置支持 `rescale`、`colormap_name`、`bidx` 和 `expression`。
- 未指定 `rescale` 时，发布 worker 使用 TiTiler statistics 的 2%/98% 分位数生成默认拉伸，避免高位深影像显示为黑图。
- footprint 外的瓦片返回 HTTP 204；QGIS XYZ 不读取数据范围，用户需根据 TileJSON `bounds` 定位影像。
- 后续扩展服务 Token、调用统计、WMTS/OGC API Tiles 和预设光学/SAR 样式。

## 17. v5 凝练版影像闭环

### 17.1 产品对象与信息架构

平台只向用户暴露三个核心对象：`影像`、`数据集`、`服务`。一级入口统一为：

- `数据`：影像目录、静态数据集、导入 Drawer 和任务 Drawer。
- `地图`：按当前视口检索、选择、预览影像并形成数据集。
- `服务`：管理单景和数据集服务的发布、更新、上下线和预览。

影像导入后立即进入检索；任意多景选择可创建静态数据集；单景或数据集均可发布稳定 XYZ/TileJSON 服务。

### 17.2 影像轻量管理

- 影像增加显示名称、业务备注和软归档字段，解析元数据保持只读。
- 首次上传人和管理员可以编辑、归档和恢复；其他登录用户可查看全部未归档影像。
- 列表、缩略图卡片和地图共享筛选条件与跨分页选择模型。
- 修改筛选条件清空选择，避免对不可见结果误操作。
- DuckDB 默认排除归档影像，STAC 和 DuckDB 投影由统一同步函数维护。

### 17.3 静态数据集

- `ImageryDataset` 保存名称、描述、状态、修订号、创建人和时间。
- `ImageryDatasetMember` 保存成员、启停状态和发布优先顺序。
- 数据集默认最多 200 景；添加、移除、启停和排序均使修订号递增。
- 数据集创建人和管理员可修改；归档仅从普通列表隐藏，不删除成员和影像。
- 数据集包含归档影像时禁止重新发布，已有在线服务继续使用最后一次成功快照。

### 17.4 多景服务

- 服务类型支持 `single_scene` 和 `dataset_mosaic`。
- 数据集发布任务冻结启用成员顺序，逐景复用或生成 COG，并校验波段数和数据类型兼容。
- 使用 `titiler.mosaic` 与 `cogeo-mosaic` 生成并读取本地 MosaicJSON，成员顺序决定 `pixel_selection=first` 的重叠优先级。
- 正式 MosaicJSON 写入 `data/mosaics/<service_key>.json`，临时文件校验成功后原子替换。
- 首次失败进入 `failed`；在线服务更新失败进入 `degraded` 并继续提供旧版本。
- 数据集修订号变化只显示“有更新”，由用户主动重新发布。

### 17.5 一致性与验收

- SQLite 保存业务权威数据，DuckDB 只承担检索投影，STAC 负责标准交换表达。
- 提供 `rebuild_imagery_index` 命令，可从 Django 数据库完整重建 DuckDB 和 STAC。
- 保持现有接入接口、单景 TileJSON/XYZ 地址和历史单景服务兼容。
- 发布验收必须覆盖两景真实 AIRSAT 数据集、MosaicJSON 瓦片预览、QGIS XYZ 访问、成员排序后重发以及旧单景服务回归。

## 18. v6 标准访问与交付版实施结果

本轮沿用“数据 / 地图 / 服务”三个一级入口，补齐影像数据的标准访问和交付闭环，不引入矢量、DEM、PostGIS 或复杂组织权限。

### 18.1 已实现

- 最小 STAC API：目录、Collection、Item、Collection Items 和 `/search`。
- STAC 支持 `bbox`、RFC3339 `datetime`、`ids`、`limit` 及平台/卫星/传感器/模式/极化/级别等 `query.eq`。
- STAC 只返回未归档影像；Bearer Token 需要 `catalog/read` scope。
- API Token 只存 SHA-256 哈希，原始 token 仅在创建时返回一次。
- 签名资产 URL、过期校验、资产角色校验和单段 HTTP Range，支持 `200/206/416` 与 `HEAD`。
- 用户独立数据篮，支持去重加入、移除和清空。
- Manifest、STAC ItemCollection 和 ZIP 异步导出，下载权限、过期和失败状态管理。
- 动态数据集 `static/query`、手动刷新、刷新模式和查询定义。
- 保存检索 CRUD。
- Polygon/MultiPolygon 的 `intersects/within/contains` 空间检索，DuckDB bbox 预筛选后进行纯 GeoJSON 精确判断。
- 现有影像目录、地图、服务页面接入数据篮、动态数据集、STAC 和 Token 入口。
- 导出任务失败原因在数据篮中展示，导出任务在 pending/running 状态自动轮询。
- `on_ingestion` 动态数据集在接入任务成功后自动刷新，成员结果变化时递增 revision。
- 归档影像不能新建或重新发布单景服务；已在线服务仍按旧版本策略继续提供访问。
- 签名外链优先使用固定 `PUBLIC_SERVICE_BASE_URL`，单次 Range 默认限制为 64 MiB。

### 18.2 当前边界

- STAC API 仍由 Django/SQLite 提供，适用于当前单机和内网规模；未引入 pgSTAC。
- COG 原始数据通过签名 Range URL 供客户端按需读取，服务渲染仍使用 TiTiler。
- 动态数据集支持手动刷新和 `on_ingestion` 接入成功后自动刷新；大规模部署仍建议改为独立异步队列。
- Manifest/STAC 异步导出中的资产链接为带过期时间的签名 URL；ZIP 已在 v7 扩展为主数据与现有辅助资产的完整交付，并提供 SHA-256 校验清单。
- STAC 搜索为轻量 offset 分页，响应已提供 `rel=next` 链接；它不是游标分页，也不适合作为大规模生产 STAC API。
- 空间检索已支持 GeoJSON 文本输入，并在 v7 增加 Leaflet 矩形/多边形绘制、空间关系选择和保存查询；行政区检索仍未实现。
- v7 增加轻量 OGC API Tiles 兼容路径，但不声明完整 OGC conformance；WMS/WMTS、矢量/DEM、组织权限、订阅通知、调用计量和运营监控仍未实现。

### 18.3 运行要求

除 Django、接入 worker、发布 worker、TiTiler 和前端外，需启动交付 worker：

```powershell
cd backend
python manage.py run_delivery_worker
```

数据库迁移后继续执行：

```powershell
python manage.py migrate
python manage.py rebuild_imagery_index
```

## 19. v7 轻量交付、标准瓦片与在线处理

v7 在 v6 的标准访问与交付能力上继续补齐四个高频工作流：完整资产打包、标准化瓦片发现、单景在线裁剪处理和地图绘制检索。目标是让现有影像更容易交付、接入第三方 GIS 客户端和完成轻量派生处理，不扩展为通用遥感算法平台。

### 19.1 实施状态

| 能力 | 状态 | 说明 |
|---|---|---|
| ZIP 全资产交付 | 已实现 | 打包当前景已登记的 data、preview、thumbnail、metadata、incidence、log 资产 |
| SHA-256 交付清单 | 已实现 | ZIP 包含 `checksums.sha256`，Manifest 增加 `asset_details` |
| 轻量 OGC API Tiles | 已实现 | 为已发布服务提供发现、tileset 元数据和 WebMercatorQuad tile 路径 |
| Leaflet 空间绘制检索 | 已实现 | 支持矩形、多边形、空间关系和保存查询 |
| ProcessingJob 单景处理 | 已实现 | bbox/Polygon、波段或表达式、GeoTIFF/PNG、独立 worker 和结果下载 |

### 19.2 ZIP 全资产交付

数据篮仍通过异步 `ExportJob` 生成 ZIP。每景使用独立且经过清洗的目录名，避免跨景同名文件覆盖，并按资产角色组织：

```text
<scene>/data/
<scene>/preview/
<scene>/thumbnail/
<scene>/metadata/
<scene>/incidence/
<scene>/log/
manifest.json
checksums.sha256
```

ZIP 只打包数据库已登记且实际存在的资产。主数据缺失时任务失败；某个辅助资产缺失时跳过该资产，不伪造文件。归档路径必须经过安全文件名处理，不接受绝对路径、`..` 或由客户端指定的服务器路径。

Manifest 保留 v6 的兼容字段：

```json
{
  "assets": {
    "data": "<signed-url>"
  }
}
```

同时新增每个资产的结构化 `asset_details`：

```json
{
  "role": "data",
  "name": "scene.tiff",
  "media_type": "image/tiff",
  "size_bytes": 123456,
  "checksum_sha256": "...",
  "url": "<signed-url>"
}
```

`checksums.sha256` 覆盖 `manifest.json` 和全部已打包资产，可用于离线完整性校验。原有数据篮和交付接口保持不变：

```text
GET    /api/delivery/basket
POST   /api/delivery/basket
DELETE /api/delivery/basket/clear
DELETE /api/delivery/basket/items/{image_id}
GET    /api/delivery/exports
POST   /api/delivery/exports
GET    /api/delivery/exports/{job_id}
GET    /api/delivery/downloads/{job_id}
```

### 19.3 轻量 OGC API Tiles

单景和数据集服务在原有 XYZ、TileJSON 地址之外增加以下兼容路径：

```text
GET /api/services/{service_key}/ogcapi
GET /api/services/{service_key}/ogcapi/tiles
GET /api/services/{service_key}/ogcapi/tiles/WebMercatorQuad
GET /api/services/{service_key}/ogcapi/tiles/WebMercatorQuad/{tileMatrix}/{tileRow}/{tileCol}
GET /api/services/{service_key}/ogcapi/tiles/WebMercatorQuad/{tileMatrix}/{tileRow}/{tileCol}.png
```

OGC tile 路径把 `tileMatrix/tileRow/tileCol` 映射到现有 TiTiler XYZ 代理，继续使用服务的公开/登录可见性规则，只允许 `online` 和 `degraded` 服务访问。原有接口保持兼容：

```text
GET /api/services/{service_key}/tilejson
GET /api/services/{service_key}/tiles/{z}/{x}/{y}.png
```

本实现仅提供面向当前影像服务的轻量发现文档、tileset 描述和 `WebMercatorQuad` PNG 瓦片，不声明通过完整 OGC API Tiles conformance suite，也不等同于 WMS、WMTS 或完整 OGC API 平台。

### 19.4 ProcessingJob 在线单景处理

ProcessingJob 面向已入库的一景影像创建异步派生任务，支持：

- 使用 WGS84 bbox 或 GeoJSON Polygon 裁剪。
- 指定一个或多个从 1 开始的波段编号。
- 使用 `b1`、`b2` 等波段变量执行受限的加减乘除表达式。
- 输出 GeoTIFF 或 PNG。
- 仅任务创建人和管理员查看、重试、删除及下载结果。

接口契约如下；下载接口随 ProcessingJob 集成一并验收：

```text
GET    /api/processing/jobs
POST   /api/processing/jobs
GET    /api/processing/jobs/{job_id}
PATCH  /api/processing/jobs/{job_id}
DELETE /api/processing/jobs/{job_id}
POST   /api/processing/jobs/{job_id}/retry
GET    /api/processing/jobs/{job_id}/download
```

创建任务请求示例：

```json
{
  "imagery_id": "23ba3e02b44c42e19127eb33aaddf8d5",
  "crop_geometry_type": "bbox",
  "bbox": [117.0, 31.1, 117.3, 31.5],
  "bands": [1],
  "expression": "",
  "output_format": "geotiff"
}
```

`bands` 与 `expression` 互斥。Django worker 负责领取任务、校验影像资产和记录状态；实际 Rasterio 读写通过 `TITILER_PYTHON` 指向的隔离 Python 运行时启动受控子进程。客户端不能提交本地源路径、输出路径或任意 Python 代码。

当前处理边界：

- 只支持单景栅格，不支持数据集镶嵌处理或跨景分析。
- 只支持 bbox/Polygon 裁剪、波段选择和简单算术表达式。
- 不包含大气校正、正射校正、云检测、SAR 专业处理、AI 算法或工作流编排。
- 结果写入本地 `data/processing`，使用单机轮询 worker；没有分布式队列、对象存储、配额和计量。
- 对波段数量、表达式长度、输出宽高和像素数设置上限，超限任务失败并记录原因。
- 该能力不等同于 Microsoft Planetary Computer 的分布式数据目录、计算与对象存储体系。

### 19.5 Leaflet 绘制与空间检索

地图页继续使用原生 Leaflet/react-leaflet 与 Ant Design，不增加绘图库依赖：

- 矩形模式依次点击两个对角点后完成。
- 多边形模式连续点击顶点，双击闭合。
- 绘制结果转换为 GeoJSON Polygon，并写入现有 `geometry` 检索参数。
- 空间关系支持 `intersects`、`contains` 和 `within`。
- 清除范围时同步清除空间条件和当前选择集。
- 可将当前空间范围和其他筛选条件保存为 Saved Search 记录；当前不提供从保存记录快捷重新应用到地图的能力。
- 地图仍按当前视口 bbox 查询，最多加载 200 景；绘制 geometry 是附加业务筛选条件。

### 19.6 运行与升级顺序

升级后先执行迁移和系统检查：

```powershell
cd D:\code\airmap\backend
python manage.py migrate
python manage.py check
python manage.py rebuild_imagery_index
```

长期运行进程按以下顺序启动：

```powershell
# 1. 内部 TiTiler/Rasterio Python 环境
..\.venv-titiler\Scripts\python.exe -m uvicorn titiler_app:app --host 127.0.0.1 --port 8081

# 2. Django API
python manage.py runserver 127.0.0.1:8000 --noreload

# 3. 接入、发布、交付和处理 worker
python manage.py run_ingestion_worker
python manage.py run_service_worker
python manage.py run_delivery_worker
python manage.py run_processing_worker

# 4. 前端，需在单独终端执行
cd ..\frontend
npm run dev -- --host 127.0.0.1
```

每个长驻命令应使用独立终端或进程管理器。`run_processing_worker` 依赖 `TITILER_PYTHON` 所指向的 Python 运行时已安装 Rasterio 和 NumPy，但它不要求 TiTiler HTTP 服务参与每次裁剪。

### 19.7 v7 验收标准

- 数据篮 ZIP 对一景真实 AIRSAT 数据打包所有现有资产，并能通过 `checksums.sha256` 校验。
- Manifest 同时保留旧 `assets` 字段并返回完整 `asset_details`；非法归档文件名不能产生路径穿越。
- 已上线公开服务可通过 OGC landing、tilesets、WebMercatorQuad 元数据和 tile 路径访问；私有服务仍要求登录。
- OGC tile 与原 XYZ 地址返回相同空间位置的数据，离线服务和不支持的 TileMatrixSet 被拒绝。
- ProcessingJob 能完成 bbox 和 Polygon 裁剪，正确处理 bands/expression 互斥、GeoTIFF/PNG 输出、失败状态和属主下载权限。
- 非属主用户不能查看或下载他人的处理结果，客户端不能注入任意文件路径或表达式代码。
- 地图绘制结果能实际进入 `/api/imagery/map` 的 `geometry` 与 `spatial_relation` 查询，并可保存为查询记录；重新应用保存记录不属于当前验收范围。
- 后端迁移、`manage.py check` 和全量测试通过；前端 `npm run type-check`、`npm run build` 与 Ant Design lint 通过。
