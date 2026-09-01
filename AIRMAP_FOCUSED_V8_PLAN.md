# Airmap v8 收缩版平台开发方案

> 更新日期：2026-08-25  
> 定位：内部海量遥感数据统一汇聚、治理、检索、使用与项目交付底座

## 1. 产品边界

Airmap 不继续扩展为综合 GIS、算法平台、网盘、商业订单系统或通用数据中台。

平台服务三类内部角色：

- 研发：快速发现数据、预览、下载、裁剪、组合数据集和发布服务。
- 售前：按区域、时间和产品条件找数据，完成多时相判读、卷帘展示和演示服务。
- 交付：冻结交付版本、校验文件与元数据、生成清单并保留可审计证据。

核心业务对象保持精简：

```text
存储源 -> 影像 -> 数据集 -> 服务 -> 交付版本
                    \-> 审计事件
```

一级导航继续保持：

- 数据
- 地图
- 服务

`存储源`、`待治理数据`和`交付版本`收进“数据”页面；元数据规则、分类和审计只向授权角色显示，不增加普通用户必须理解的一级入口。

## 2. 核心原则

### 2.1 外部数据默认引用

已有目录、NAS 和远程存储中的海量原始文件默认原位登记，不在接入时强制复制。需要稳定服务、处理或交付时再生成托管副本或派生资产。

### 2.2 JPG 优先、COG 延迟

入库成功只依赖产品识别、元数据、footprint 和可用的小型预览资产，不依赖 COG。

```text
缩略图     -> 列表和卡片
同名 JPG   -> 地图快速预览、透明度、卷帘、多时相
COG        -> 高清缩放、波段渲染、XYZ/OGC 服务和多景 Mosaic
```

COG 状态独立：

```text
none / queued / processing / ready / failed / stale
```

已经是 COG 的源文件直接复用；相同源文件的 COG 按内容指纹复用；COG 失败不影响影像检索和 JPG 预览。

### 2.3 未识别数据不能丢失

扫描发现但无法组成产品组、缺少主数据、未匹配解析模板或元数据不完整的文件，必须进入“待治理”队列，而不是被忽略或直接判定整个扫描失败。

### 2.4 交付必须可复现

数据篮继续作为临时选择工具。正式项目交付必须生成不可变交付版本，冻结影像、资产、元数据、服务引用、文件大小和 SHA-256。

## 3. 当前基线

现有 v7 已具备：

- ZIP、7Z、文件夹和 URL 接入。
- AIRSAT 文件名、XML、日志和栅格元数据解析。
- scene_key 去重、footprint、JPG/缩略图预览。
- DuckDB 检索、列表/卡片、一张图和空间绘制。
- 静态/动态数据集、入库自动刷新。
- 单景和多景 TiTiler 服务、XYZ、TileJSON、轻量 OGC API Tiles。
- STAC API、访问令牌、签名 Range 资产访问。
- 数据篮、Manifest/STAC/ZIP 全资产交付。
- 单景裁剪、波段选择和表达式处理。

v8 在此基础上补充五个领域：存储、元数据治理、分类与行政区、可视化、审计与正式交付。

## 4. 存储管理

### 4.1 支持范围

接入方式分为：

- `referenced`：原位引用，不复制原始文件。
- `managed`：复制到平台托管存储。
- `derived`：平台生成的 JPG、缩略图、COG、处理结果和导出包。

存储端点：

- P0：服务器本地目录、NAS/SMB UNC 路径。
- P1：S3/MinIO、SFTP。
- P2：只读 FTP/FTPS；普通 FTP 明确显示非加密风险。

### 4.2 最小模型

```text
StorageEndpoint
StorageCredential
StorageObject
StorageScanJob
```

`ImageryAsset` 增加 `storage_object` 和 `access_mode`，兼容现有 `path`，逐步把文件访问迁移到统一 `StorageBackend`。

### 4.3 扫描规则

- 根目录只能由管理员登记，客户端不能任意提交服务器绝对路径。
- 本地/NAS 对象键使用相对路径；S3 使用 bucket、prefix 和 key。
- 全量扫描、增量扫描、对账扫描和健康检查分开记录。
- 首次发现使用路径、大小、修改时间或 ETag 快速判断；交付或冲突时再计算 SHA-256。
- 一次缺失只标记 `first_missing`，连续完整扫描确认后才标记 `confirmed_missing`。
- 外部文件缺失不删除影像记录；已有派生预览仍可用于目录浏览。
- 扫描保存游标和检查点，支持暂停、重试和断点继续。

### 4.4 小资产托管

即使主数据采用引用模式，也建议把以下小资产复制到平台管理目录：

- preview JPG
- thumbnail JPG
- XML/JSON 元数据
- 解析运行摘要

这样 NAS 或远程端点临时离线时，目录、检索和快速预览仍然可用。

## 5. 元数据治理

### 5.1 目标

把当前代码内固定 AIRSAT 解析器升级为：

```text
内置解析插件 + 版本化 Schema + 声明式解析模板 + 质量检查 + 人工覆盖
```

### 5.2 模型

```text
MetadataSchema
MetadataSchemaField
MetadataParserTemplate
MetadataParserTemplateVersion
MetadataParserRun
MetadataOverride
MetadataQualityIssue
```

现有平台、卫星、传感器、时间、分辨率、极化、geometry 等固定字段继续作为高频检索投影。扩展字段保存到版本化 JSON，确认高频后再提升为专用列。

### 5.3 规则能力

允许：

- 文件名正则命名组。
- 受限 XML 节点路径。
- 受限 JSON 路径。
- GeoTIFF/JP2 只读元数据。
- 常量和枚举映射。
- trim、大小写、数字/时间转换、单位转换、coalesce、数组去重、四角生成 geometry。

禁止：

- 任意 Python、JavaScript、SQL 或模板表达式。
- 网络访问、环境变量读取和产品组外路径访问。
- 未受限 XPath、灾难性正则和无限输入。

### 5.4 版本与人工值

- 已发布模板版本不可原地修改。
- 每个字段保留原始值、标准值、来源文件、选择器、模板版本和转换信息。
- 重解析先生成 diff，不静默覆盖人工确认值。
- 人工锁定值优先，冲突进入 `needs_review`。
- AIRSAT 当前解析逻辑作为 `legacy adapter`，新引擎未匹配时继续回退，确保现有数据不回归。

## 6. 分类、行政区与高级检索

### 6.1 概念分离

- 项目：研发、售前或交付的业务关联。
- 分类：管理员维护的稳定树，如数据类型、业务领域、产品形态。
- 标签：用户快速标记，如待核查、重点、可交付。
- 行政区：系统参考数据，不允许普通用户随意修改。

卫星、传感器、极化等已经属于结构化元数据，不重复建设为人工分类。

### 6.2 行政区数据

数据源：`D:\行政区划天地图`

已核验：

| 文件 | 总要素 | 有效面要素 | 坐标系 |
|---|---:|---:|---|
| 中国_省.geojson | 42 | 34 | EPSG:4490 |
| 中国_市.geojson | 388 | 375 | EPSG:4490 |
| 中国_县.geojson | 2898 | 2891 | EPSG:4490 |

无 `gb` 编码且名称为“境界线”的 MultiLineString 不作为行政区导入。有效 `gb` 使用 `156` 加六位行政区代码，父级优先按编码推导，异常数据再按空间包含关系处理。

模型：

```text
AdministrativeUnit
ImageryAdministrativeUnit
Classification
Tag
ImageryClassification
ImageryTag
```

导入时统一记录源 CRS 和版本，对 Web 输出使用 EPSG:4326；预计算 bbox、中心点、简化 geometry 和父级。

### 6.3 影像行政区归属

影像入库或 footprint 变更后异步计算：

- `intersects`
- `center_inside`
- `coverage_ratio`
- `primary` 行政区

查询优先使用预计算关联，避免每次请求遍历全部县级几何。

### 6.4 检索补充

- 省、市、县级联。
- 分类、标签、项目。
- 存储来源和源文件状态。
- 元数据质量状态和待治理状态。
- 入库时间与拍摄时间段相交。
- 是否有 JPG、COG、在线服务和交付版本。
- 保存查询重新应用、复制和转动态数据集。
- 上传 GeoJSON 范围；SHP ZIP 延后。

地图与目录继续共享同一套筛选参数。

## 7. JPG 优先可视化

### 7.1 浏览模式

- 点击 footprint 后加载同名 JPG。
- 透明度使用 Ant Design Slider。
- 最多维护 4 景临时图层，支持显隐、顺序和单景切换。
- 小型预览不触发 COG 生成。

### 7.2 卷帘模式

- 仅支持两景。
- 使用成熟 Leaflet side-by-side 组件。
- 两景必须有预览并存在空间重叠。
- JPG 卷帘标记为“快速预览”；旋转影像按 bbox 铺设可能存在近似误差。

### 7.3 多时相

- 最多 4 景，按拍摄时间排序。
- 同一地图视口切换或叠加。
- 显示时间、卫星、分辨率和质量状态。
- 支持保存为数据集或视图预设。

### 7.4 波段组合

波段组合不能从 JPG 获得。采用两级策略：

1. 从原始栅格按降采样读取指定波段，生成最大约 2048 像素的缓存 PNG/JPG，用于快速组合预览。
2. 需要连续缩放、精确定位或服务访问时，后台异步生成或复用 COG。

首期支持 RGB 波段选择、单波段灰度、受限表达式、rescale、Gamma 和 NoData。SAR 极化语义必须来自元数据，不能把 HH/HV 直接当作普通 RGB。

## 8. 审计治理

### 8.1 审计事件

```text
AuditEvent
- actor
- actor_role_snapshot
- action
- target_type / target_id
- project_id
- source: web/api/worker/scheduler/admin/system
- result / reason
- request_id / correlation_id
- before_digest / after_digest
- redacted_metadata
- occurred_at
```

事件只追加，不提供普通修改和删除 API。敏感凭据、Authorization Header、文件内容和完整私密路径不得进入审计详情。

### 8.2 必须审计

- 登录、Token 创建与撤销、权限拒绝。
- 存储端点创建、测试、扫描、对象缺失和恢复。
- 导入、重复跳过、解析、重解析和人工元数据确认。
- 分类、标签、归档和恢复。
- 主数据下载、导出、在线处理。
- 数据集成员和顺序变化。
- 服务创建、发布、更新、下线和失败。
- 交付版本创建、校验、冻结、导出和确认。

不逐条写入每个瓦片请求；瓦片和高频 STAC 调用按时间窗聚合请求数、状态码、字节数和延迟。

## 9. 正式交付版本

现有数据篮和 ExportJob 保留，用于临时下载。正式交付增加：

```text
DeliveryProject
DeliverySnapshot
DeliverySnapshotItem
DeliveryArtifact
DeliveryValidationRun
DeliveryAcceptance
DeliveryIssue
```

流程：

```text
选择影像/数据集
-> 自动检查
-> 生成候选清单
-> 冻结 v1
-> 生成 Manifest/STAC/ZIP/校验报告
-> 交付
-> 确认或退回
-> 问题处理
-> 验收
```

正式交付默认 strict 模式：主数据、checksum、CRS、footprint、必填元数据或服务探测任一失败均不能冻结。内部临时共享可使用 partial 模式并明确列出缺失项。

## 10. 角色

继续使用 Django User、Group 和 Permission，提供角色模板，不建设复杂 ABAC：

- 平台管理员
- 数据管理员
- 研发人员
- 售前人员
- 交付负责人
- 普通查看者

默认仍允许登录用户查看未归档影像。存储凭据、元数据模板发布、人工值确认、交付冻结和完整审计需要专门权限。

## 11. 规模与架构

首期继续 SQLite + DuckDB，但增加以下约束：

- 端点扫描串行或按端点限并发，批量写入。
- 地图单次最多 200 景。
- 数据集和 Mosaic 首期最多 200 景。
- 卷帘 2 景，多时相 4 景。
- 行政区关联在入库时预计算。
- 审计事件按月归档，高频调用使用聚合表。
- 大文件 SHA-256 延迟到入库冲突、托管或交付阶段。

出现持续写锁、空间查询 p95 超过目标或扫描任务需要并行扩展时，再迁移 PostgreSQL/PostGIS 和 Redis/Celery。迁移是规模触发条件，不作为 v8 前置依赖。

## 12. 实施顺序

### Phase A：基础模型与审计骨架

- StorageEndpoint、StorageObject、StorageScanJob。
- Metadata Schema、模板版本、运行和质量问题。
- AdministrativeUnit、Classification、Tag。
- AuditEvent。
- 兼容迁移和现有 AIRSAT 回归测试。

### Phase B：本地/NAS 汇聚与治理

- 本地目录和 NAS 登记、测试、全量/增量扫描。
- referenced/managed 模式。
- 未识别文件进入待治理队列。
- 小资产托管、来源状态和缺失恢复。
- 元数据模板试跑、发布和批量重解析。

### Phase C：检索与 JPG 可视化

- 导入省、市、县行政区。
- 分类、标签和行政区高级检索。
- 保存查询重新应用。
- JPG 透明度、最多 4 景多时相和 2 景卷帘。
- 快速波段组合缓存预览。

### Phase D：S3/SFTP 与正式交付

- S3/MinIO、SFTP 存储后端。
- 引用资产按需托管和 COG 缓存。
- DeliveryProject 和不可变 DeliverySnapshot。
- 校验、冻结、交付报告、问题与确认。

### Phase E：运行治理

- 服务访问聚合。
- 数据质量、存储健康和审计报表。
- 备份恢复、配置导出和客户环境部署检查。
- 根据实测规模决定 PostgreSQL/PostGIS 和任务队列迁移。

## 13. 验收主线

1. 管理员登记本地/NAS目录后，无需浏览器上传即可扫描出产品组。
2. 外部主数据不复制也能进入目录；JPG、缩略图和元数据可托管后快速预览。
3. 新增一种不同 XML/JSON 格式的产品可通过配置模板解析，无需修改 Python。
4. 未识别产品可被检索、查看原因、绑定模板并重新解析。
5. `D:\行政区划天地图` 可导入，影像自动关联省市县并参与目录和地图检索。
6. 分类、标签、来源、质量、行政区、时间和影像属性可以组合查询。
7. 两景 JPG 卷帘、最多四景多时相和透明度在桌面/移动端可用，且不会触发 COG。
8. 波段组合可先生成轻量缓存预览；高清模式才异步准备 COG。
9. 导入、治理、下载、处理、发布和交付均有可查询审计事件。
10. 正式交付版本冻结后，后续源文件或元数据变化不会改变历史 Manifest 和 checksum。

## 14. 明确不做

- 通用个人网盘和桌面双向同步客户端。
- 矢量、结构化、三维和流式数据平台。
- WMS/WFS/WMTS 全协议平台。
- 遥感算法市场、AI 模型训练和任意代码运行。
- 商业订单、充值、计费和 CRM。
- 每个瓦片请求写一条数据库审计事件。
- 入库时强制把所有原始影像转换为 COG。
