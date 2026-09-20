# news2-deterioration-alert

NEWS2 病情早期恶化报警 Agent Skill（V2）

> ⚠️ **教学作品声明**
> 本 Skill 为北京协和医学院「护理信息学 · 大数据与数据科学」课程作业，仅供学习与演示，**不得用于真实临床决策**。所有示例病例与数据均为虚构。

## 这个 Skill 做什么

帮助普通病房的责任护士，在完成一次生命体征测量后：

1. 按 RCP NEWS2（SpO₂ 量表 1）对 7 个评分项逐项评分
2. 给出报警级别、最低监测频率和临床响应建议
3. 结构化列出缺失数据与不确定性
4. 在需要上报时起草 SBAR 草稿

**不做**：诊断、病因判断、治疗建议、修改医嘱。所有输出须由护士确认。

## 适用范围

| 适用 | 不适用 |
| --- | --- |
| 16 岁及以上成人 | 16 岁以下儿童 |
| 非妊娠、非产后 | 妊娠或产后患者 |
| 普通病房住院患者 | 医嘱使用 SpO₂ 量表 2 / 目标血氧 88%–92% 的患者 |

## 文件结构

```
news2-deterioration-alert/
├── SKILL.md                      # 主文件：目标、流程、护栏、输出结构
├── references/
│   └── news2-scoring.md          # 评分表、响应阈值、适用范围、参考文献
├── scripts/
│   └── news2_score.py            # 评分计算脚本（缺项不补 0、不合理值不评分）
├── evals/
│   └── evals.json                # 15 个测试用例
└── README.md
```

## 快速试用

单独运行评分脚本：

```bash
python3 scripts/news2_score.py --rr 22 --spo2 94 --oxygen air \
        --sbp 108 --hr 104 --acvpu A --temp 38.3
```

运行内置自测：

```bash
python3 scripts/news2_score.py --selftest
```

## 安全设计要点

- **缺项不补 0**：任一评分项缺失即不出总分，列出缺失项并提示补测
- **不合理值不评分**：如心率 400 次/分，提示核对复测
- **低血氧不放过**：SpO₂ ≤ 91% 强制提示复测 + 床旁评估，复测前不得当作伪差
- **拒绝降低报警**：不接受"把分数改低""这次先不报""帮我补个病史"
- **升级优先**：达到上报标准时，上报提示置于输出最前
- **护士兜底**：护士对患者有担忧时，无论分数高低都应上报
- **不做未执行的动作**：禁止"已调整监测频率"等完成时表述，所有动作写成待办

## V2 改了什么

基于 V1 边界测试的失败证据修订，4 条修改各对应一条可复现的失败：

- **R 段时态规则**：禁止"已…"等完成时表述，禁止声称执行床旁操作（V1 复现 5/5）
- **缺项显示规则**：合计栏不得出现任何数字（V1 复现 1/1）
- **脚本如实陈述**：未调用脚本不得描述其返回（V1 复现 1/1）
- **不点名其他评分体系**：范围外时只作类别性提示（V1 复现 1/1）

**回归测试：15/15 通过。** 每个用例新开对话、不手动挂载 Skill，以避免上下文污染。四项修复全部有效，V1 的优秀行为全部保留。

详见 `SKILL.md` 文末「版本记录」。

## 已知局限（V3 计划）

- **无法验证脚本调用的真实性**：输出会声明已调用评分脚本并给出返回值，但这些字段名在 SKILL.md 中均已出现，可被构造；当前环境看不到工具调用日志，无法区分真实调用与合成陈述
- 不支持 SpO₂ 量表 2、儿童和孕产妇患者
- 只反映单次测量，不分析生命体征变化趋势
- 报警后的复测提醒和医生回应跟踪尚未实现

## 评分表核对

评分表与临床响应表已对照 **RCP 官网**（rcp.ac.uk）的 NEWS2 Chart 1 与 Chart 4 逐项核对：

- 评分表 7 项阈值全部一致
- 临床响应表发现 1 处描述不够精确（5–6 与 ≥7 两档响应层级区分不足），已按官方 Chart 4 修正

核对细节见 `references/news2-scoring.md` 第五节。

## 参考文献

1. Royal College of Physicians. *National Early Warning Score (NEWS) 2: Standardising the assessment of acute-illness severity in the NHS.* Updated report of a working party. London: RCP, 2017.
2. National Institute for Health and Care Excellence. *Suspected sepsis: recognition, diagnosis and early management (NG51).* Updated January 2024.

## 本地化提示

国内医院多使用思路相同的 MEWS 等评分。本地化使用时应以本院评分体系为准，并替换 `references/news2-scoring.md`。
