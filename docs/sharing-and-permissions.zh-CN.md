# 共享与权限

OpenColab 实现了基于来源的所有权和共享模型。每个来源（文件、分组或笔记）都有一个所有者，并可以选择性地与其他用户共享。

## 核心概念

### 所有权

每个来源都有一个 `owner_id`，用于追踪其创建者。所有权决定了谁可以共享、重命名或删除该来源。当用户上传文件、创建分组或保存笔记时，即成为该来源的所有者。

### 共享

每个来源最多只能有**一条共享记录**（`SourceShare`）。共享通过两个维度进行配置：

- **范围（Scope）** — 谁可以看到该来源：
  - `all` — 系统中所有用户均可见
  - `project` — 仅特定项目的成员可见
- **权限（Permission）** — 非所有者可执行的操作：
  - `read` — 仅查看
  - `readwrite` — 可修改（例如，在分组中添加/移除成员，编辑笔记）

### 显示名称

用户可通过 `PATCH /api/v1/auth/me` 设置 `display_name`。该名称显示在 UI 顶部、共享元数据（`shared_by_name`）以及来源响应中的 `owner_name` 字段。未设置时回退为 `username`。

## 各来源类型的行为

### 文件

| 操作 | 规则 |
|---|---|
| 默认可见性 | 私有（仅所有者可见） |
| 共享 | 所有者可共享；权限始终强制为 `read` |
| 取消共享 | **不允许** — 文件一旦共享即无法取消共享 |
| 删除（未共享） | 实际删除 — 移除来源及向量数据 |
| 删除（已共享） | **软删除** — 仅对执行删除的用户隐藏；其他用户仍可看到 |
| 重命名 | 仅所有者可操作 |

### 分组

| 操作 | 规则 |
|---|---|
| 默认可见性 | 私有（仅所有者可见） |
| 共享 | 所有者可以 `read` 或 `readwrite` 权限共享 |
| 取消共享 | 允许 — 其他用户将失去对该分组的访问权限（但自动共享的子文件仍保持共享） |
| 删除 | 仅所有者可操作 — 实际删除 |
| 重命名 | 仅所有者可操作 |
| 添加/移除成员 | 所有者，或任何拥有 `readwrite` 权限的用户 |

**分组共享时的自动共享：** 当分组被共享时，所有子文件（递归）将自动以相同范围共享。由于文件无法取消共享，此操作不可逆。API 提供 `share-preview` 端点，用于提示用户将有多少文件被自动共享。

**新成员的继承：** 当文件被添加到已共享的分组时，该文件将自动继承分组的共享设置。

### 笔记

| 操作 | 规则 |
|---|---|
| 默认可见性 | 私有（仅会话所有者可见） |
| 共享 | 会话所有者可以 `read` 或 `readwrite` 权限共享 |
| 取消共享 | 允许 |
| 删除 | 仅会话所有者可操作 |
| 编辑 | 会话所有者，或任何拥有 `readwrite` 权限的用户 |

## 数据模型

### `SourceShare` 表

每个已共享来源对应一行（`source_id` 唯一约束）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `source_id` | FK `sources.id` | 被共享的来源（CASCADE 删除） |
| `shared_by` | FK `users.id` | 共享操作的执行者（用户删除时 SET NULL） |
| `scope` | String | `"all"` 或 `"project"` |
| `project_id` | FK `projects.id` | scope 为 `"project"` 时必填（CASCADE 删除） |
| `permission` | String | `"read"` 或 `"readwrite"` |
| `shared_at` | DateTime | 初次共享的时间戳 |

### `HiddenSource` 表

追踪用户对已共享文件的软删除（`user_id` + `source_id` 唯一约束）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `user_id` | FK `users.id` | 执行隐藏操作的用户（CASCADE 删除） |
| `source_id` | FK `sources.id` | 被隐藏的来源（CASCADE 删除） |

### 来源模型新增字段

- `owner_id`（FK `users.id`，SET NULL）— 可为空，用于处理历史数据和已删除用户
- `owner` 关联 — 可预加载用于显示
- `share` 关联 — 与 `SourceShare` 一对一关联

## API 端点

### 共享操作

| 方法 | 端点 | 说明 |
|---|---|---|
| `GET` | `/api/v1/sources/{id}/share` | 获取来源的共享信息 |
| `POST` | `/api/v1/sources/{id}/share` | 共享来源 |
| `PATCH` | `/api/v1/sources/{id}/share` | 更新共享范围或权限 |
| `DELETE` | `/api/v1/sources/{id}/share` | 取消共享（文件返回 400） |
| `GET` | `/api/v1/sources/{id}/share-preview` | 预览分组的自动共享文件数量 |

### 共享请求体

```json
{
  "scope": "all",
  "project_id": null,
  "permission": "read"
}
```

- `scope` — `"all"` 或 `"project"`
- `project_id` — scope 为 `"project"` 时必填
- `permission` — `"read"` 或 `"readwrite"`（文件忽略此字段，始终为 `"read"`）

### 共享响应（POST）

```json
{
  "shared": true,
  "auto_shared_files": 3,
  "scope": "all",
  "permission": "read"
}
```

### 用户资料

| 方法 | 端点 | 说明 |
|---|---|---|
| `PATCH` | `/api/v1/auth/me` | 更新显示名称 |

```json
{ "display_name": "Alice" }
```

### 扩展的来源响应

`GET /api/v1/sources` 和 `GET /api/v1/sources/{id}` 现在包含：

```json
{
  "id": "...",
  "type": "file",
  "name": "paper.pdf",
  "owner_id": "user-uuid",
  "owner_name": "Alice",
  "is_shared": true,
  "can_edit": false,
  "share": {
    "shared_by": "user-uuid",
    "shared_by_name": "Alice",
    "scope": "all",
    "project_id": null,
    "permission": "read",
    "shared_at": "2025-01-01T00:00:00Z"
  }
}
```

- `owner_name` — 来源所有者的显示名称（或用户名）
- `is_shared` — 是否存在共享记录
- `can_edit` — 当前用户是否为所有者或拥有 `readwrite` 权限
- `share` — 未共享时为 null

## 可见性规则

`GET /api/v1/sources` 返回以下内容的并集：

1. 用户**拥有**（通过工作区链接）且**未隐藏**的来源
2. 范围为 `"all"` 且**未被当前用户隐藏**的共享来源
3. 范围为 `"project"` 且用户为**该项目成员**且**未隐藏**的共享来源

管理员用户遵循相同的可见性规则（无特殊权限绕过）。

## 边界情况

| 场景 | 行为 |
|---|---|
| 所有者隐藏已共享文件 | 仅对该用户隐藏；其他用户仍可看到 |
| 分组取消共享 | 分组对非所有者消失；自动共享的子文件仍保持共享状态 |
| 项目删除（含项目范围共享） | FK CASCADE 删除 `SourceShare` 行；相关来源恢复为私有 |
| 用户账号删除 | `owner_id` 设为 NULL；`shared_by` 设为 NULL；已共享来源仍可访问 |
| 两用户上传相同文件（content_hash 去重） | 来源保留原始所有者；第二个用户仅获得工作区链接 |
| readwrite 用户将文件添加至已共享分组 | 文件归添加用户所有，并自动以分组范围共享 |
| 共享范围变更 | `PATCH /api/v1/sources/{id}/share` 就地更新范围/权限 |

## 前端

### 共享对话框

来源页面的共享对话框（`ShareDialog`）提供：

- 范围选择器 — 单选组："所有用户" / "项目成员"
- 项目下拉框 — 范围为"project"时显示
- 权限选择器 — 单选："只读" / "读写"（适用于分组和笔记）
- 文件不可逆警告："文件一旦共享，将无法取消共享"
- 分组自动共享警告："此操作还将共享该分组中的 N 个文件"
- 已共享项目：显示当前设置，并提供取消共享按钮（仅限分组/笔记）

### 视觉标识

- 已共享来源在名称旁显示共享图标
- 其他用户拥有的来源在名称后显示所有者名称
- 悬停共享图标时显示"由 {name} 共享"的提示

### UI 中的权限控制

- 仅所有者可看到"共享"和"重命名"操作
- `readwrite` 用户可添加/移除分组成员
- `read` 用户仅有查看权限
- 已共享文件的删除操作文案变更为"从我的视图中隐藏"

### 国际化（i18n）

所有共享相关字符串均使用 `share.*` 命名空间下的 i18n 键，支持 `en-US` 和 `zh-CN` 翻译。

## 数据库迁移

迁移 `d5a3f1e7b9c2_add_sharing_and_ownership`：

- 在 `users` 表中添加 `display_name` 字段
- 在 `sources` 表中添加 `owner_id` 字段（含外键和索引）
- 创建 `source_shares` 表
- 创建 `hidden_sources` 表
- 从现有 `workspace_sources` 链接回填 `owner_id`
