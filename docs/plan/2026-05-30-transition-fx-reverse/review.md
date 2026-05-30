# Review: 短视频「转场/特效」反解 (`fx_`)

**Sessions**: 41529b37-8723-4107-8555-72ce2a0a7c9a
**Outcome**: shipped — 实验目标达成（X0→X3 全过），方向证成；管线未并入 main、未进生产编排（本就是 POC 范围）。

> 本文件只谈 **agent 的协作过程**，不谈技术结论。技术结论在 `spec.md §9–§12`。

## What went well (fortify)

- **De-risk-first 真的省了返工。** X0 一支 throwaway 探针（没写一行管线代码前）同时炸出两个会贯穿全程的坑：端点是 Anthropic SSE 而非 OpenAI `choices[]`、`agent-vision` 后端路由不固定。这两个若拖到 X2 才发现，VLM 客户端要重写。值得继续：**最大未知先用一次性脚本证伪/证实，再动地基。**
- **对自己的乐观判断做了二次证伪。** X1 我一度声称 temp=0 已可复现（n=2 偶然一致），X2 完整重跑后发现标签仍漂，**主动改口并记入 spec §11**，没让乐观结论留在文档里骗下一个人。后续 X3 又用 k=3 实证落定。这是文档「不撒谎」原则起作用的一次。
- **不信 VLM 标签、亲自核帧。** car @101 的 push/slide 靠逐帧 contact sheet 看出来是硬切误报，不是看 confidence 高就采信。验收主线（定位）和软指标（type）分开统计，避免用一个软标签的命中率冒充整体准确率。
- **spec 里程碑块的写法可复用：** verdict + 量化表 + 设计决策 + 诚实局限 四段固定，跨 BGM/Font/fx 一致，恢复成本低。

## Friction & fixes

- **Recon 误判端点协议**（先入为主说成 OpenAI `choices[]`）— 根因：凭印象没探测 — 下次：对任何外部 API，**先发一个真实请求看返回结构**再设计客户端，别从「它应该长这样」开工。
- **轻信「agent-vision 会路由到 doubao-seed-2.0-pro」**，X0 整段假设了固定后端，实际落到 kimi-k2.6 / doubao-seed-2.0-code — 根因：把用户口述的路由当事实 — 下次：凡「可复现实验」，**每次调用都记真实 `model`**，并优先锁定确定性后端（直连 Ark），不依赖网关别名。
- **真实素材专属 bug 拖到 X3 才暴露**（full-range YUV 抽帧失败、末帧越界）— 根因：开发样本 Lotus 是 limited-range 16:9 广告，与抖音竖屏 full-range 特征不同，bug 被样本掩盖 — 下次：de-risk 样本尽量贴近生产特征，或**明确预期：用替身素材跑通的管线，到真实素材必然还有一批尾部 bug**，把这批 bug 预算进 eval 阶段。
- **`EnterWorktree` 被拦**（"already isolated working copy"）→ 改用 `git switch -c` 直接建分支 — 结果：plan 落在主 checkout 的分支上而非独立 worktree。功能上无碍（分支即 plan 身份），但与 dev-plan「一 plan 一 worktree」的默认假设有偏差，恢复时要知道是在主 checkout 上切分支。
- **外部 Ark 调用偶发分类器瞬时拒绝**（探针跑了 3 次才过）— 根因：外部 API 调用被安全分类器误伤 — 处理：重试即可（瞬时）；管线侧已对单窗 VLM 调用包 try/except，单窗失败不毁整批。

## Corrections for the user

- 「走 `agent-vision` 会路由到 doubao-seed-2.0-pro」这句不准——它是负载均衡别名。**做可复现实验时，请直接给确定性端点**（本例的直连 Ark `/api/coding` + `doubao-seed-2.0-pro`），能省掉 X1 摸后端那段弯路。
- 真实抖音素材在 X0 之后才给——这是「先用 Lotus 跑通机制」的刻意决定，合理；代价是真实素材专属 bug 必然推迟到 X3。若想更早暴露，可在 X1 就丢一条真实竖屏片做 detect-only（不烧 VLM，便宜）。

## Knowledge to promote

- ✅ **已在本次收尾写入 `CLAUDE.md`**：fx_ 作为第 4 条管线登记；settled-decisions 增加「fx = VLM 描述非检索 / 定位确定但 type 需 k=3 投票 / 后端锁 Ark doubao-seed-2.0-pro、拒用 agent-vision / 召回盲点」；run-commands 与 `VOLC_ARK_API_KEY` 凭据位置。
- 留给未来（超出本 plan，spec §12 已记）：k-投票收进 `fx_extract`；收紧运动类 prompt；结构化输出做 ARC 的 RL 微调语料（用户最终目标）。
