"""Shared baseline/RSI execution guidance, versioned independently from model HTTP."""
STRONG_REACT_GUIDANCE = (
    '优先复用已有工具观察；只有现有结果缺少必要字段时才调用详情工具。'
    '调用前检查相同工具与参数是否已成功执行，避免重复读取。'
    '彼此独立的工具读取尽量在同一次响应中批量发出；有数据依赖时等待上游返回。'
    '需要按业务键逐组汇总、比较或筛选时，优先调用确定性聚合或显式关联工具并使用其返回值；跨多表按同一键求和、派生总额、阈值或比例条件时，优先使用 workspace_reconcile_keyed_sums；比例条件必须用显式 rightTerms（别名和权重）表达，例如 left >= 0.2×right 用 leftAlias=left、rightTerms=[{alias:right,multiplier:0.2}]、operator=gte、threshold=0，禁止用分开的聚合结果自行心算或重提未改变的结论。'
    'workspace_aggregate_rows 的 count 只统计行数，不能带 groupBy；统计不同渠道、产品等分组数量时必须调用 group_count，并从返回的 counts 确定数量。'
    '统计文本或说明字段的非空记录时，使用 workspace_aggregate_rows 的 nonempty_count；字符串空白不计入。'
    '需要按当前表的稳定排序分为前后两期时，使用 workspace_ordered_partition；prior 固定为前 floor(n/2) 行，current 为其余行，不能手工分段或猜测奇数行归属。'
    'workspace_reconcile_keyed_sums 的 comparisons 会返回 matchingTotals；需要汇总满足比较条件的金额时必须直接使用它，不得从 perKey 或行记录手工相加。'
    '公开交付口径如提供 referenceTime，所有“相对参考时刻”的日期判断必须以该时间为准，不得改用宿主机当前日期或资料中的任意一条日期。'
    '当运行时明确告知公开交付范围已被当前观察完整覆盖时，报告 evidenceIds 会从这些观察确定性写入；不得为抄写证据引用重复读取资料。'
    '分页读取先从 page=1 开始；若返回 mayHaveMore=true，保持相同 pageSize 并顺序读取下一页。'
    '发布前逐项核对任务要求的指标、筛选 ID 和证据，不能用简报文字代替结构化字段。'
)
