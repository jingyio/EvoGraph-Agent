"""Shared baseline/RSI execution guidance, versioned independently from model HTTP."""
STRONG_REACT_GUIDANCE = (
    '优先复用已有工具观察；只有现有结果缺少必要字段时才调用详情工具。'
    '调用前检查相同工具与参数是否已成功执行，避免重复读取。'
    '彼此独立的工具读取尽量在同一次响应中批量发出；有数据依赖时等待上游返回。'
    '发布前逐项核对任务要求的指标、筛选 ID 和证据，不能用简报文字代替结构化字段。'
)
