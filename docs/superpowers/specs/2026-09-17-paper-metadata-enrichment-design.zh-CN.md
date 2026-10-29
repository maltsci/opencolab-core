# 论文元数据增强设计

生成日期：2026-09-17

分支：`public-one`

状态：APPROVED
采用方案：本地标识符提取 + 权威数据库精确查询 + 人工覆盖保护 + 完整离线降级

## 1. 背景与问题

OpenColab 当前在上传文件时使用原始文件名创建 `ResearchAsset.title`，资源库、课程资料选择器、知识问答来源等页面随后都展示这个标题。PDF 解析阶段虽然会尝试从正文第一行提取标题，但结果只保存在 `SourceExtraction.structured_json` 中，没有回写资源标题。

这会产生三个问题：

1. 文件名常包含下载前缀、序号、下划线或无意义缩写，用户无法快速识别论文。
2. 当前“第一行即标题”的规则容易把页眉、版权声明或期刊名称当成论文标题。
3. 系统没有 DOI、PMID、PMCID、arXiv ID 等规范标识符，无法引用权威数据库中的作者、期刊和发表时间等元数据。

本设计把该能力定义为“论文元数据增强”。PDF 入库和正文处理仍然是主流程，在线元数据查询是可关闭、可失败、可重试的异步增强流程。

## 2. 目标

### 2.1 产品目标

- PDF 处理完成后，资源列表优先展示论文标题，而不是原始文件名。
- 保存原始文件名，并在资源详情中明确展示，保证文件可追溯。
- 从本地 PDF 元数据和首页内容中提取 DOI、PMID、PMCID、arXiv ID。
- 仅使用精确标识符查询权威数据库，获取规范论文元数据。
- 当结果唯一且达到自动采用条件时更新资源标题；存在冲突时交给用户确认。
- 人工确认或编辑后的标题不得被后续自动任务覆盖。
- 在线查询关闭、网络不可用或供应方失败时，上传、解析、检索和问答仍然正常工作。

### 2.2 非目标

本版本不包含：

- 把 PDF 或全文发送给 Crossref、NCBI、PMC、arXiv 或其他外部服务。
- 使用论文标题、作者或摘要进行外部模糊搜索。
- 使用 LLM 判断论文身份或选择规范书目记录。
- 自动合并具有相同 DOI、但文件内容不同的资源。
- 建立独立的 `Publication` 实体或完整文献管理系统。
- 自动下载论文正文、补充材料或引用文献。
- 将在线数据库返回的摘要全文写入资源目录。

## 3. 术语与范围

- **原始文件名**：用户上传时的 `Source.name`，始终保留，不随标题变化。
- **本地标题候选**：从 PDF 内嵌元数据或解析文本中获得、尚未经过权威数据库验证的标题。
- **规范标题**：由精确标识符查询得到并通过自动采用规则或人工确认的标题。
- **人工锁定**：用户编辑或确认标题后，禁止后台任务自动覆盖。
- **arXiv ID**：本设计将需求中的 “Archive ID” 解释为 arXiv 标识符，例如 `2401.12345`。如果需求方指其他档案数据库，需要另行定义供应方和标识符格式。

v1 只处理 `application/pdf` 或文件扩展名为 `.pdf` 的上传资源。

## 4. 已有能力与复用点

### 4.1 上传与资源实体

`materialize_source_asset()` 已负责把 `Source` 转为 `ResearchAsset`，目前同时把 `source.name` 写入：

- `ResearchAsset.title`
- `ResearchAsset.catalog_metadata_json["title"]`

该过程继续保留。上传成功后，用户可以立即看到文件名，不等待 PDF 解析或外部网络。

### 4.2 本地解析与提取

`process_source()` 已按“解析 → 分块 → 向量化 → 提取”处理文件，并通过 `SourceExtraction` 保存结构化结果。元数据增强在提取成功后进入独立状态，不改变 `Source.processing_state=ready` 的时机。

### 4.3 资源展示

资源库、课程、项目资源和知识问答引用均读取 `ResearchAsset.title`。规范标题写回后，这些入口会自动获得一致结果。`catalog_metadata_json["title"]` 必须在同一事务内同步，避免目录搜索与详情展示出现两个标题。

### 4.4 PDF 能力

项目已经依赖 PyMuPDF，并已经具备 PPS、marker 和本地基础解析回退。因此本地元数据读取无需引入新的 PDF 依赖。

## 5. 用户体验

### 5.1 上传后的状态变化

1. 上传完成：资源立即展示原始文件名，并显示“等待解析”。
2. PDF 可检索：现有处理状态变为“处理完成”，正文预览和问答可用。
3. 元数据增强：资源标题旁显示独立状态，如“识别论文信息中”。
4. 唯一可信结果：列表标题自动更新为论文标题，并显示“已通过 Crossref/NCBI/arXiv 验证”。
5. 存在冲突：保留当前标题，显示“论文信息待确认”。
6. 离线或查询失败：保留本地标题候选或文件名，显示“未联网校验”，不显示资源处理失败。

资源的正文处理状态与元数据增强状态必须分开。用户不应因为 Crossref 超时而继续看到“等待处理”。

### 5.2 资源列表

列表的主要标题使用 `ResearchAsset.title`。标题下方或悬浮信息展示：

- 原始文件名，仅在其与当前标题不同时显示。
- DOI、PMID 或 arXiv ID 中已确认的标识符。
- 元数据状态：已验证、待确认、本地提取、未联网校验或查询失败。

列表搜索应同时匹配：

- 当前标题
- 原始文件名
- DOI
- PMID
- PMCID
- arXiv ID

### 5.3 资源详情

详情增加“论文信息”区域，展示：

- 标题
- 作者
- 期刊或会议
- 发表日期
- DOI
- PMID
- PMCID
- arXiv ID
- 元数据来源和最后校验时间
- 原始文件名

有管理权限的用户可以：

- 编辑标题并锁定。
- 从候选记录中选择一个结果。
- 取消人工锁定并重新运行识别。
- 在失败或离线后手动重试。

无管理权限的用户只能查看已经确认、允许在目录中展示的元数据，不能看到内部错误详情或未确认候选。

### 5.4 冲突确认

以下情况必须进入人工确认，不自动改名：

- 提取到多个无法归并到同一论文的标识符。
- DOI 与 PMID 查询结果的规范标题明显不一致。
- 标识符来自低可信文本区域，例如正文或参考文献。
- 权威标题与本地标题候选相似度不足。
- 已存在人工锁定标题。
- 外部记录缺少标题或返回结构不完整。

确认界面同时展示当前标题、本地候选、权威候选、来源数据库和标识符，不展示未经清洗的供应方原始响应。

## 6. 标题优先级和覆盖规则

标题来源优先级如下：

1. 人工编辑或人工确认并锁定的标题
2. 通过精确标识符校验、满足自动采用条件的规范标题
3. 高可信 PDF 内嵌标题
4. 高可信本地版面标题候选
5. 原始文件名

更新规则：

- `title_locked=true` 时，任何后台任务都不得修改 `ResearchAsset.title`。
- 规范标题写回时，必须在同一数据库事务中更新 `ResearchAsset.title` 和 `catalog_metadata_json["title"]`。
- 更新标题不得修改 `Source.name`、文件路径、内容哈希或资源修订的原始显示名。
- 重新解析同一资源时，可以刷新候选和规范元数据，但不能解除人工锁定。
- 用户选择“重新采用自动标题”时，系统先解除锁定，再重新执行匹配；该动作需要管理资源权限。

## 7. 标识符提取

### 7.1 候选来源

候选按可信度从高到低排序：

1. PDF XMP 或 DocumentInfo 中明确的 DOI、标题。
2. 首页顶部标题区中的显式 `doi:`、`PMID:`、`PMCID:`、`arXiv:` 字段。
3. 前两页中带字段标签或规范 URL 的标识符。
4. 其他正文区域中的标识符，只能作为待确认候选。

参考文献区域中的 DOI 不参与自动采用。若无法可靠识别参考文献边界，则第三页以后的 DOI 默认视为低可信候选。

### 7.2 规范化

- DOI：移除 `doi:`、`https://doi.org/` 前缀，去除尾部标点，按大小写不敏感方式比较，存储规范小写值。
- PMID：只接受显式 `PMID` 标签后的数字。
- PMCID：规范为大写 `PMC` 加数字。
- arXiv ID：支持新旧格式，移除 `arXiv:` 和 URL 前缀；版本号如 `v2` 单独保存，基础 ID 用于查询。

所有正则表达式必须设置长度上限。任何提取结果在发起网络请求前必须再次经过严格格式校验。

### 7.3 本地标题候选

本地标题识别顺序为：

1. 合法且非占位值的 PDF 内嵌标题。
2. PPS 或 marker 输出中的首个一级标题。
3. 首页版面中满足标题特征的连续文本块。
4. 当前第一行启发式，仅作为低可信回退。

应排除常见无效值：原始文件名、`untitled`、扫描设备名称、期刊页眉、版权声明、DOI 字符串和过长文本。

## 8. 权威数据库查询

### 8.1 供应方

| 标识符 | 首选供应方 | 用途 |
| --- | --- | --- |
| DOI | Crossref REST API | 获取出版物标题、作者、期刊、发表日期和 DOI |
| PMID | NCBI E-utilities | 获取 PubMed 规范记录 |
| PMCID | PMC ID Converter | 转换 PMID、PMCID、DOI，再从对应供应方获取规范记录 |
| arXiv ID | arXiv API `id_list` | 获取预印本标题、作者、分类和版本日期 |

官方接口参考：

- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Crossref access and authentication](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
- [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [NCBI usage guidelines](https://www.ncbi.nlm.nih.gov/books/NBK25497/)
- [PMC ID Converter](https://pmc.ncbi.nlm.nih.gov/tools/id-converter-api/)
- [arXiv API user manual](https://info.arxiv.org/help/api/user-manual.html)
- [arXiv API terms of use](https://info.arxiv.org/help/api/tou.html)

### 8.2 查询约束

- 只允许固定的官方 HTTPS 主机，不能由用户提交任意查询 URL，防止 SSRF。
- 请求只包含规范化后的公开标识符、服务标识和管理员配置的联系邮箱。
- HTTP 客户端禁用环境代理继承，除非未来显式设计受控代理配置。
- 每个供应方单独设置并发限制、超时、重试和退避策略，遵守其公开使用政策。
- 成功结果缓存 30 天；未找到缓存 24 小时；临时失败不写长期缓存。
- 同一规范标识符的并发查询必须合并，避免重复请求。
- 响应体设置大小上限，仅解析需要的字段。
- 不记录完整外部响应和完整标识符到普通应用日志；日志使用供应方、结果状态和标识符哈希。

### 8.3 供应方适配器

定义统一内部接口：

```python
class BibliographicProvider(Protocol):
    async def lookup(self, identifier: NormalizedIdentifier) -> ProviderRecord | None:
        ...
```

`ProviderRecord` 只包含白名单字段：

- `provider`
- `identifier_type`
- `identifier`
- `title`
- `authors`
- `container_title`
- `published_date`
- `doi`
- `pmid`
- `pmcid`
- `arxiv_id`
- `record_url`
- `retrieved_at`

供应方特有原始 JSON、XML 或 Atom 内容不进入公开目录。

## 9. 记录归并与自动采用

### 9.1 归并规则

- DOI 相同的 Crossref 和 PubMed 记录归并为同一候选。
- PMC ID Converter 只提供标识符映射，不单独成为标题来源。
- 同时存在 DOI 和 arXiv ID 时，保留二者；若 DOI 对应正式发表版本，则 DOI 记录作为规范书目信息，arXiv 记录作为预印本标识。
- 多个供应方返回的作者、期刊或日期可以互补，但标题冲突必须进入人工确认。

### 9.2 自动采用条件

必须同时满足：

1. 资源标题未人工锁定。
2. 只有一个归并后的论文候选，或多个标识符明确归并到同一 DOI。
3. 标识符来自 PDF 内嵌元数据或首页/前两页的高可信区域。
4. 供应方返回的标识符与请求标识符完全一致。
5. 供应方标题通过基本有效性检查。
6. 本地标题候选存在时，其规范化文本与供应方标题达到确定性相似度门槛；不使用 LLM。

如果缺少本地标题候选，只有来自 PDF 内嵌元数据的标识符可以自动采用，其余进入人工确认。

产品验收阶段应使用真实 PDF 校准相似度门槛。门槛以“零错误自动改名”为优先目标，宁可降低自动覆盖率。

### 9.3 规范字段选择

- 有 DOI 的正式出版物：Crossref 提供规范标题和出版信息，PubMed 补充 PMID、PMCID。
- 无 DOI 但有 PMID：PubMed 提供规范标题和出版信息。
- 只有 arXiv ID：arXiv 提供规范标题和预印本信息。
- 供应方字段缺失时不使用空值覆盖已有确认字段。

## 10. 数据模型

### 10.1 `research_assets`

增加：

- `title_source: String(32)`，默认 `filename`，可取 `filename`、`local_pdf`、`crossref`、`pubmed`、`arxiv`、`manual`。
- `title_locked: Boolean`，默认 `false`。

原始文件名继续来自 `Source.name`，不在 `ResearchAsset` 重复存储。

### 10.2 `source_extractions`

增加：

- `metadata_status: String(32)`，带索引。
- `metadata_attempts: Integer`。
- `metadata_next_attempt_at: DateTime | null`，带索引。
- `metadata_checked_at: DateTime | null`。
- `metadata_error: String(1000) | null`。

状态值：

- `not_applicable`
- `pending`
- `resolving`
- `resolved`
- `needs_review`
- `no_identifier`
- `offline`
- `failed`

`structured_json` 升级为新 schema version，并增加：

```json
{
  "title": "Local title candidate",
  "bibliographic": {
    "local_title_candidate": {
      "value": "Local title candidate",
      "source": "pdf_xmp",
      "confidence": "high"
    },
    "identifier_candidates": [],
    "provider_candidates": [],
    "resolution": {
      "status": "needs_review",
      "reason_codes": []
    }
  }
}
```

候选中保存来源页码、区域和置信等级，不保存整页原文。

### 10.3 `catalog_metadata_json`

已采用的公开书目信息写入：

```json
{
  "title": "Canonical paper title",
  "bibliographic": {
    "authors": [],
    "container_title": "Journal name",
    "published_date": "2026-01-15",
    "doi": "10.xxxx/example",
    "pmid": "12345678",
    "pmcid": "PMC1234567",
    "arxiv_id": "2401.12345",
    "source": "crossref",
    "record_url": "https://doi.org/10.xxxx/example",
    "retrieved_at": "2026-09-17T00:00:00Z",
    "verification_status": "verified"
  }
}
```

公开目录只读取已采用的白名单字段。未确认候选继续留在受权限保护的 `SourceExtraction` 中。

### 10.4 查询缓存

新增 `bibliographic_metadata_cache`：

- `provider`
- `identifier_type`
- `normalized_identifier`
- `record_json`
- `result_status`
- `fetched_at`
- `expires_at`

`provider + identifier_type + normalized_identifier` 设置唯一约束。缓存不与具体用户或项目绑定，因为只保存公开书目记录，不保存用户上传内容。

## 11. 后台处理流程

```text
上传文件
  → 创建 Source 与 ResearchAsset，标题为文件名
  → PDF 解析、分块、向量化
  → Source.processing_state = ready
  → 本地提取标题与标识符
  → SourceExtraction.metadata_status = pending/offline/no_identifier
  → 元数据任务独立领取
  → 精确查询缓存或官方数据库
  → 归并、校验、判定
      ├─ 自动采用 → 更新 ResearchAsset 标题与目录元数据
      ├─ 存在冲突 → needs_review
      └─ 临时失败 → 退避重试，最终 failed
```

元数据任务使用数据库状态领取，并沿用 `SELECT ... FOR UPDATE SKIP LOCKED` 模式，保证多个 worker 不会重复处理同一条记录。

处理约束：

- 文档解析完成后先提交正文处理结果，再创建或更新元数据任务。
- 在线请求不得占用 PDF 解析状态，也不得回滚已经完成的向量化结果。
- 临时网络失败最多自动尝试 3 次，使用指数退避。
- 明确的 404 或无记录结果直接进入 `needs_review` 或 `no_identifier`，不重复请求。
- worker 重启后可以从数据库状态继续，不能依赖内存任务。

## 12. API 设计

### 12.1 列表和详情响应

`ResearchAssetResponse` 与目录列表响应增加：

- `original_filename`
- `title_source`
- `title_locked`
- `metadata_status`
- `bibliographic_summary`

列表只返回用于展示和搜索的摘要字段，不返回全部候选记录。

### 12.2 元数据详情

`GET /api/v1/research-assets/{asset_id}/bibliographic-metadata`

返回：

- 当前已采用元数据
- 本地标题和标识符候选
- 权威数据库候选
- 状态、失败原因码和最后校验时间
- 当前用户可执行的操作

未确认候选只对能够管理该资源的用户返回。

### 12.3 人工更新

`PATCH /api/v1/research-assets/{asset_id}/bibliographic-metadata`

支持：

- 人工修改标题并锁定。
- 选择一个候选记录并锁定。
- 补充或修正公开标识符。

所有写入必须验证资源管理权限，并在同一事务中同步标题和目录元数据。

### 12.4 重试

`POST /api/v1/research-assets/{asset_id}/bibliographic-metadata/retry`

只允许资源管理者调用。接口只把任务重置为 `pending`，不在请求线程中调用外部数据库。

### 12.5 解除锁定

`POST /api/v1/research-assets/{asset_id}/bibliographic-metadata/unlock`

解除后保留当前标题，直到新的结果满足自动采用条件或用户再次确认，避免按钮操作导致标题立即跳回文件名。

## 13. 配置

新增运行时配置：

- `bibliographic_lookup_enabled`，默认 `false`。
- `bibliographic_auto_apply_enabled`，默认 `false`；关闭时只生成候选，不自动修改标题。
- `bibliographic_lookup_contact_email`，启用在线查询时必填。

对应环境变量：

- `OPENCOLAB_BIBLIOGRAPHIC_LOOKUP_ENABLED`
- `OPENCOLAB_BIBLIOGRAPHIC_AUTO_APPLY_ENABLED`
- `OPENCOLAB_BIBLIOGRAPHIC_LOOKUP_CONTACT_EMAIL`

管理员系统设置页增加“在线论文元数据”区域，明确说明：

- 启用后，系统会把 DOI、PMID、PMCID 或 arXiv ID 发送给对应官方数据库。
- 不会发送 PDF、正文、标题或作者候选。
- 完全离线部署应保持关闭。

官方供应方 URL 固定在代码中，v1 不允许管理员填写任意服务 URL。

## 14. 隐私与安全

- 原始 PDF 和正文不进入元数据供应方请求。
- 标识符属于公开书目信息，但查询会让供应方知道部署方对该标识符发起过请求，因此必须由管理员显式开启。
- 供应方响应经过 Pydantic 白名单模型校验，未知字段丢弃。
- 外部 URL 不接受用户输入，重定向后仍需验证目标主机。
- 请求超时、响应大小、XML 实体解析和重定向次数必须有限制。
- `record_url` 只接受已知供应方域名或规范 `https://doi.org/` URL。
- 普通日志不记录原始 PDF 路径、完整响应或完整标识符。
- 权限裁剪发生在 API 返回候选之前；用户不能通过元数据接口推断无权访问资源的内容。

## 15. 错误处理与降级

| 场景 | 行为 |
| --- | --- |
| 在线查询关闭 | 保留本地候选或文件名，状态为 `offline` |
| 没有标识符 | 保留本地候选或文件名，状态为 `no_identifier` |
| 供应方超时或 5xx | 后台重试，不影响资源可用性 |
| 供应方限流 | 尊重 `Retry-After`，进入退避队列 |
| 标识符无记录 | 保留候选，允许人工补充或重试 |
| 多个候选冲突 | 不自动改名，状态为 `needs_review` |
| 用户已锁定标题 | 刷新元数据但不修改标题 |
| 响应格式变化 | 适配器失败并记录原因码，不写入部分解析结果 |
| 资源被删除或归档 | 终止待处理任务，不发起外部请求 |

## 16. 可观测性

增加聚合指标，不记录论文内容：

- 本地提取到标识符的 PDF 数量和比例。
- 各供应方成功、未找到、限流、超时、失败次数。
- 自动采用、人工确认、无标识符、离线降级数量。
- 元数据任务排队时间和处理时间。
- 被人工纠正的自动标题数量。

发布阻断指标：测试期间出现任何错误自动改名，必须先调整自动采用规则或关闭自动采用。

## 17. 测试策略

### 17.1 单元测试

- DOI、PMID、PMCID、arXiv ID 的正常、换行、尾部标点和恶意超长输入。
- 参考文献 DOI 不进入高可信候选。
- PDF 内嵌标题的占位值过滤。
- 标题规范化和确定性相似度计算。
- 多供应方记录归并和冲突判定。
- 人工锁定阻止后台覆盖。
- `ResearchAsset.title` 与 `catalog_metadata_json["title"]` 原子同步。
- 供应方响应白名单校验、重定向主机校验和响应大小限制。

### 17.2 适配器测试

使用 HTTP mock，不依赖真实互联网：

- Crossref 成功、404、429、5xx、超时和畸形 JSON。
- NCBI 成功、无记录、限流和畸形 XML/JSON。
- PMC 标识符转换成功和部分映射。
- arXiv 精确 ID 成功、空结果和 Atom 解析失败。
- 缓存命中、过期、并发合并和失败不污染缓存。

### 17.3 集成测试

- 上传 PDF 后先变为可检索，再独立完成元数据增强。
- worker 重启后可以继续待处理任务。
- 在线查询关闭时不产生任何外部请求。
- 无管理权限用户看不到候选或错误详情。
- 手动重试只排队，不阻塞 API。
- 删除资源后不再执行待处理任务。

### 17.4 前端测试

- 标题更新后列表、详情、课程和项目资料显示一致。
- 原始文件名只在与标题不同时显示。
- `pending`、`resolved`、`needs_review`、`offline`、`failed` 状态文案正确。
- 用户确认候选、编辑标题、解除锁定和重试的交互。
- 长标题、无作者、多作者、移动端布局和中英文切换。

### 17.5 真实 PDF 验收集

准备 30–50 篇实验室真实 PDF，覆盖：

- 出版社原版 PDF。
- PubMed/PMC 论文。
- arXiv 预印本。
- 同时包含 arXiv ID 和 DOI 的论文。
- 扫描版和图片型 PDF。
- 标识符只出现在首页、正文或参考文献的不同情况。
- 没有标识符的旧论文或内部材料。
- 标题包含公式、希腊字母、上下标和中英文混排的论文。

验收以精确率优先：任何自动采用的标题都必须对应当前 PDF；无法确定时允许保持文件名或进入人工确认。

## 18. 发布与回退

### 18.1 发布顺序

1. 上线数据库迁移、状态字段和本地候选提取，在线查询保持关闭。
2. 在测试环境启用在线查询，运行真实 PDF 验收集。
3. 验证外部请求审计、缓存、限流和离线降级。
4. 向少量测试人员开放候选确认和人工编辑。
5. 只有在自动改名没有错误后，才在目标环境启用自动采用。

### 18.2 回退

- 管理员关闭 `bibliographic_lookup_enabled` 即可立即停止新的外部查询。
- 关闭后保留已确认元数据和标题，不批量恢复文件名。
- 若自动采用规则存在问题，可单独关闭自动采用，继续收集候选供人工确认。
- 数据库迁移的新增字段和缓存表不影响旧读取路径。

## 19. 分阶段实施计划

### 阶段 1：本地提取与数据基础

主要改动：

- `backend/app/services/extraction_service.py`
- 新增书目标识符和标题候选解析服务
- `backend/app/models/research_asset.py`
- `backend/app/models/trace.py`
- 新增 Alembic migration
- `backend/app/schemas/research_asset.py`
- `.env.template`
- 对应后端测试

交付：

- 本地提取 DOI、PMID、PMCID、arXiv ID。
- 独立元数据状态。
- 标题来源和人工锁定字段。
- 不发起外部请求。

退出标准：本地测试集不会把参考文献 DOI 判定为可自动采用的主标识符。

### 阶段 2：权威数据库适配器与后台任务

主要改动：

- 新增 `bibliographic_metadata_service.py`
- 新增供应方适配器目录
- 新增查询缓存模型和迁移
- `backend/app/worker/main.py`
- `backend/app/services/runtime_config.py`
- `backend/app/core/config.py`
- 适配器、缓存、重试和安全测试

交付：

- Crossref、NCBI、PMC、arXiv 精确查询。
- 缓存、限流、超时、重试和离线开关。
- 记录归并与自动采用判定。

退出标准：关闭配置时零外部请求；供应方故障不影响 PDF 进入 `ready`。

### 阶段 3：API 与前端确认体验

主要改动：

- `backend/app/api/research_assets.py`
- `frontend/src/pages/Library.tsx`
- `frontend/src/components/library/AssetDetailDrawer.tsx`
- 新增论文信息与候选确认组件
- `frontend/src/pages/admin/Settings.tsx`
- `frontend/src/locales/en-US.json`
- `frontend/src/locales/zh-CN.json`
- API 权限测试和前端测试

交付：

- 原始文件名、规范标题、标识符和来源展示。
- 候选确认、人工编辑、锁定、解除锁定和重试。
- 管理员在线查询配置。

退出标准：用户能理解当前标题来自哪里；人工标题在重新解析和重试后保持不变。

### 阶段 4：真实数据验收与渐进发布

交付：

- 30–50 篇真实 PDF 验收报告。
- 自动采用精确率、人工确认率和无标识符比例。
- 供应方失败与离线演练。
- 对既有单个资源提供“重新识别”入口。

退出标准：自动改名错误数为 0；所有失败场景不阻断资源读取、检索和问答。

## 20. 成功标准

- 上传资源最终可以展示论文标题，同时保留并可查看原始文件名。
- DOI、PMID、PMCID、arXiv ID 的提取与展示有明确来源。
- 在线查询只发送精确标识符，不发送 PDF、正文、标题候选或作者候选。
- 外部供应方不可用时，资源仍能按当前 PDF 处理流程进入可用状态。
- 人工编辑或确认后的标题不会被后台任务覆盖。
- 所有自动采用标题在真实 PDF 验收集中均对应当前文档。
- 中英文界面均无硬编码用户可见文本。

## 21. 待确认事项

1. 需求中的 “Archive ID” 是否明确指 arXiv ID。本设计按 arXiv ID 实施。
2. 第一阶段是否需要对既有全部 PDF 批量回填。建议 v1 只处理新上传文件，并提供单资源重新识别；批量回填在真实数据验收后再开放。
3. 自动采用是否在生产环境默认开启。建议在线查询和自动采用均由管理员分别开启，测试环境验证通过后再开启自动采用。

## 22. 设计决策摘要

- 采用异步元数据增强，不延长 PDF 可阅读和可检索的等待时间。
- 只允许精确标识符查询，不做外部模糊搜索。
- 原始文件名与论文标题是两个不同字段，不互相覆盖。
- 人工操作优先，后台任务不能覆盖人工锁定标题。
- 权威数据库结果也不是无条件可信；冲突或来源位置不可靠时必须人工确认。
- v1 复用 `ResearchAsset` 和 `SourceExtraction`，不引入独立论文实体。
- 对外网络默认关闭，完全离线是正式支持路径，而不是异常路径。
