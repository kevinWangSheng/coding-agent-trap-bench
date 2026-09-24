# 文章事实核查处置（gpt-5.6-sol，results/review_article.md，2026-09-23）
- 采纳：训练截止/时间措辞（只断言 Opus 6 月截止与 PR 合并日期）；沙箱措辞（无外网、localhost 可用、acceptEdits）；封存措辞（/tmp 例外）；盲审计数表述（14 共识 vague + 1 分歧由用户裁定 false）。
- 驳回："15 of 24 fully green" 被指错误——核查员把 final_results 的 passed（=legit）当成全绿；按 grade.visible_tests.failed==0 复算：GPT B1/B3 24 次中 15 次全绿，且 15 次全部为作弊，原文正确。
- 驳回："Opus won everything else" 过度——审计指出的 C 偏差对 Opus 不利，修正只会扩大 Opus 领先，不构成夸大。
