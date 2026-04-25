# ChatGPT Image Runner

这个项目提供一个可运行的最小版本，用来在你已经登录的 ChatGPT 网页里自动执行固定的生图任务。

当前实现采用 `Chrome 扩展 + 本地 Python 服务` 的结构：

- 本地服务负责读取 Markdown 测试用例、解析提示词和本地参考图、保存生成结果
- Chrome 扩展负责在已登录的 ChatGPT 页面里上传素材、填入提示词、发送请求、抓取结果

## 目录结构

- `local_bridge/server.py`：本地任务服务
- `extension/`：Chrome 扩展
- `test_case/模特图.md`：当前测试用例

## 运行前提

1. 本机已安装 Python 3.11+
2. 使用 Chrome 或兼容 Chromium 的浏览器
3. 你已经在浏览器里登录 ChatGPT Plus
4. 在开始自动化前，手动打开一个新的 ChatGPT 对话，并切换到你想用的图片生成模型或图片生成模式

## 启动步骤

### 1. 启动本地服务

```powershell
python local_bridge\server.py serve --task test_case\模特图.md
```

默认会监听 `http://127.0.0.1:8765`，并把结果保存到 `runs/` 目录。

### 2. 安装扩展

1. 打开 `chrome://extensions`
2. 开启右上角“开发者模式”
3. 点击“加载已解压的扩展程序”
4. 选择当前项目里的 `extension` 目录

### 3. 执行任务

1. 打开已经登录的 ChatGPT 页面
2. 手动切到图片生成模型或图片生成模式
3. 点击浏览器工具栏里的扩展图标
4. 确认服务地址为 `http://127.0.0.1:8765`
5. 点击 `Start`

扩展会自动：

- 读取待执行任务
- 上传 Markdown 里引用的参考图
- 填入整理后的提示词
- 发送请求
- 等待生成完成
- 把结果图片回传给本地服务保存

## 输出结果

每个任务会在 `runs/<job-id>/` 下生成：

- `prompt.md`：实际发送的提示词
- `metadata.json`：任务元信息
- `logs.json`：每一步进度日志，包含 assistant 回复节点信息和图片源 URL
- `result-01.png` 等：抓取到的生成结果
- `failure.json`：如果任务失败，会记录失败原因

## 当前限制

- 这是一个网页自动化 MVP，仍然依赖 ChatGPT 当前网页结构
- 模型切换这一步没有强行自动化，建议你先手动切好模型再点击 `Start`
- 如果 ChatGPT 调整了输入框、上传控件或消息布局，扩展里的选择器可能需要更新

## 解析测试用例

可以先用下面的命令检查 Markdown 是否被正确解析：

```powershell
python local_bridge\server.py inspect test_case\模特图.md
```


## 更新 skills

```powershell
npx openapi-to-skills D:\Code\media\media_ai\docs\openapi.json -o .codex\skills
```