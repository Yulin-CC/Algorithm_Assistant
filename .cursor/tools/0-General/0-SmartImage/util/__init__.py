# 1 理解图像：import describe → describe_file / describe_files
# 2 误检定档：import label_grade → run_dataset（框和掩膜都判 fit|adjust|wrong，不改写标注）
# 3 漏检定位：import label_miss → run_miss。变化检测 run_miss_change（--masks），提示词须先向用户确认
# 4 补标：import opt_fill → run_fill（默认 GroundingPI 定位，再 Triton SAM 修边。SAM3 是定位的另一选择）。变化检测 pair 记录只允许 --locate off --refine sam
# 5 调整：import opt_adjust → run_adjust（定档 adjust 的框中心当报点，再走补标链。不改原标注）。变化检测 run_adjust_change（--masks）由 Qwen 重新报点再交 Triton SAM
# 6 结果分析：import analysis → analyze（误检、不贴合、已有漏检；不再问模型）
# 叠图：import overlay。只画框和掩膜，不调用模型。
# 变化检测：import label_grade → run_change（--masks）。两期整图在 overlay.save_change_overview。
# 中间文件：检测定档 draft/overlay/。变化检测：repro/<版本>/{crop/analysis_crop,crop/vismask_crop,analysis}；漏检补标调整在 repro/<版本>/draft/{miss,fill,adjust}。
