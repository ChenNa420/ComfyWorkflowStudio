# Phase 1D Acceptance

Phase 1D 的目标不是“代码存在”，而是让一条真实 MiniMax H3 首帧转视频任务从 ComfyWorkflowStudio 成功进入本地 ComfyUI、完成生成并自动进入作品库。

## 当前实现

- 原始 Workflow 只读保存。
- 每次任务创建 Runtime Prompt Clone。
- UI Workflow 可根据 ComfyUI `/object_info` 转换为 API Prompt。
- Manifest 输入/参数映射注入 Runtime Prompt。
- 本地首帧自动上传到 ComfyUI。
- 动态时长按 Workflow `durationState` 或默认 `24fps + 4 frames padding` 计算。
- MiniMax 风格基准：5s=124、7s=172、7.5s=184、8s=196 frames。
- 动态时长会同步到 Runtime Prompt 中的 `duration/seconds` 与 `length/frames/frame_count/total_frames/...` 字段。
- `/prompt` 提交后使用 `/history` 确认结果。
- 输出文件自动回收到 `storage/outputs/<task-id>/` 并写入 `outputs` 表。
- `UNKNOWN` 不自动重试；转换不确定时进入 `NEEDS_REVIEW`。
- 工作流适配页已接真实 Manifest PUT API。

## Windows 本地代码验收

```powershell
cd D:\ComfyWorkflowStudio
git checkout feat/phase1b-1d
git pull

python -m unittest discover -s tests -v
npm run build
```

必须全部通过后再进行真实生成。

## Dry Run

确认 API、ComfyUI、工作流库、Manifest 与依赖：

```powershell
python scripts\phase1d_smoke.py --workflow minimax
```

如果工作流未导入，请先在 Web 的“导入工作流”页面从本地工作流包中导入对应 MiniMax H3 首帧转视频 JSON，并在“工作流适配”页确认首帧、Prompt、Duration 等语义。

## 真实生成

准备一张首帧图片后：

```powershell
python scripts\phase1d_smoke.py `
  --workflow minimax `
  --first-frame "D:\path\first-frame.png" `
  --duration 8 `
  --fps 24 `
  --run
```

成功标准：

1. API `/api/health` 为 `ok`。
2. ComfyUI 为 `connected`。
3. Workflow compatibility 为 `READY`。
4. 任务依次进入 `WAITING/PREPARING/SUBMITTING/RUNNING/SUCCEEDED`。
5. Task Events 中出现 `DURATION_APPLIED`。
6. 8 秒任务按 MiniMax H3 24fps + 4 padding 应显示 196 frames。
7. `/history` 返回成功。
8. 至少回收一个视频 Output。
9. Web 作品库可以看到生成结果。
10. 原始 Workflow JSON 未发生修改。

## 失败策略

- `FAILED`：提交前已确认失败，可人工修复后再次创建任务。
- `NEEDS_REVIEW`：UI → API 映射存在不确定项，不自动提交。
- `UNKNOWN`：任务可能已到达 ComfyUI，绝不自动再次提交，避免重复生成。

Phase 1D 只有在本地真实视频生成满足以上标准后才标记为 PASS。
