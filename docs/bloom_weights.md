# Bloom 分类学权重文档化（P20-7）

## 概述

本文件记录 ChallengeDaily 中使用的 Bloom's Taxonomy（布卢姆分类学）权重分配，
包括每个层级的定义、权重值、数据来源和计算公式。

## Bloom 六层级权重

| 层级 | 英文 | 权重 | 说明 |
|------|------|------|------|
| 记忆 | Remember | 0.10 | 识别、回忆事实和基本概念 |
| 理解 | Understand | 0.15 | 解释、归纳、推断 |
| 应用 | Apply | 0.20 | 在新情境中使用信息 |
| 分析 | Analyze | 0.20 | 分解、比较、组织 |
| 评价 | Evaluate | 0.20 | 批判性判断、论证 |
| 创造 | Create | 0.15 | 生成、规划、产出 |

**权重总和 = 1.00**

## 权重依据

权重参考 Bloom revised taxonomy (Anderson & Krathwohl, 2001) 的认知复杂度层级，
并结合工作日报场景做了调整：

- **应用/分析/评价** 权重较高（各 0.20），因为日报的核心价值在于反映
  用户"做了什么"（应用）、"如何做"（分析）和"为什么这样做"（评价）
- **记忆** 权重最低（0.10），因为机械记忆类活动在知识工作中占比低
- **创造** 权重 0.15，体现创新产出但避免过度强调

## 计算公式

```
bloom_score = Σ(activity_duration_min × bloom_weight[activity_bloom_level]) / total_duration_min
```

## 活动到 Bloom 层级的映射规则

| 活动分类 | Bloom 层级 | 理由 |
|----------|-----------|------|
| 开发（编码） | Apply | 应用知识解决具体问题 |
| 学习/阅读 | Understand | 理解新概念 |
| 会议 | Analyze | 交流中分析不同观点 |
| 文档写作 | Create | 产出新内容 |
| 设计 | Create | 产出设计方案 |
| 测试 | Evaluate | 验证、判断质量 |
| 沟通 | Understand | 理解他人意图 |
| 休息 | — | 不计入 Bloom 评分 |
| 娱乐 | — | 不计入 Bloom 评分 |
| 社交 | Remember | 基本社交互动 |

## 引用来源

1. Anderson, L. W., & Krathwohl, D. R. (2001). *A Taxonomy for Learning, Teaching, and Assessing: A Revision of Bloom's Taxonomy of Educational Objectives*. Longman.
2. Bloom, B. S. (1956). *Taxonomy of Educational Objectives, Handbook I: The Cognitive Domain*. David McKay Co Inc.

## 变更日志

- 2026-07-16: 初始文档化（P20-7）
