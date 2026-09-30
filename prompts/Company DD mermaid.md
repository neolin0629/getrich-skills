flowchart TD

%% =========================
%% 0. DEFINE OBJECTIVE
%% =========================
A["明确研究目标
• 投资问题 / Research Question
• 投资时间框架
• 核心假设
• 待验证关键变量
• 信息需求清单"]

A --> B["信息收集 / Material Gathering"]

B --> B1["Primary Sources
• 公司公告 / 财报 / 招股书
• 交易所文件
• 年报 / 中报
• IR / 路演材料
• FDA / NMPA / 政策文件
• 行业协会
• 官方 Index Methodology
• 学术论文"]

B --> B2["Secondary Sources
• 券商研报
• 行业研究
• 数据库
• 新闻
• 专家访谈
• 第三方研究"]

B --> B3["Channel Check
• 客户
• 供应商
• 经销商
• 竞争对手
• 专家
• 实地调研"]

RP["研究原则
• 多来源 Cross-check
• 优先追溯原始 Material
• 区分 Fact / Management View / Sell-side View
• 异常数据必须深挖
• 关键经营信息尽量渠道验证
• 不单纯依赖 AI / 二手报告
• 长期行业覆盖形成 Research Edge"]

B1 --> C
B2 --> C
B3 --> C
RP -.贯穿全流程.-> C

%% =========================
%% STEP 1 INDUSTRY
%% =========================
C["Step 1：行业研究"]

C --> C1["市场空间
• 市场规模
• TAM / SAM / SOM
• 历史增长率
• 未来增长率
• 渗透率"]

C --> C2["行业周期
• 库存周期
• 产能周期
• CAPEX 周期
• 价格周期
• 当前周期位置"]

C --> C3["行业趋势
• 技术趋势
• 产品替代
• 商业模式变化
• 人口 / 消费趋势"]

C --> C4["政策监管
• 政策
• 监管
• 补贴
• 关税
• 牌照
• FDA / NMPA 等"]

%% =========================
%% STEP 2 VALUE CHAIN
%% =========================
C --> D["Step 2：产业链研究"]

D --> D1["上游
• 原材料
• 核心供应商
• 供应集中度
• 成本变化"]

D --> D2["中游
• 制造 / 平台 / 服务
• 产能
• 利用率
• 技术壁垒"]

D --> D3["下游
• 客户
• 渠道
• 终端需求
• 客户集中度"]

D --> D4["利润分配与议价权
• 谁赚最多利润
• 谁承担最多风险
• 谁拥有议价权
• 利润池如何变化"]

%% =========================
%% STEP 3 COMPETITION
%% =========================
D --> E["Step 3：竞争格局"]

E --> E1["Peer Universe
• 直接竞争者
• 间接竞争者
• 替代产品
• 海外竞争者
• Benchmark Peer"]

E --> E2["业务相似度
• 产品
• 客户
• 地区
• 商业模式
• 产业链位置"]

E --> E3["市场份额
• 当前 Share
• 3–5 年趋势
• Gain Share
• Lose Share"]

E --> E4["增长趋势比较
• Revenue Growth
• 3Y / 5Y CAGR
• Organic Growth
• Volume
• ASP"]

E --> E5["盈利趋势比较
• Gross Margin
• EBITDA Margin
• FCF Margin
• ROIC"]

E --> E6["竞争优势比较
• 成本
• 技术
• 产品
• 品牌
• 渠道
• 规模
• 牌照
• Switching Cost"]

E --> E7["竞争策略变化
• 定价
• 扩产
• R&D
• 新产品
• M&A
• 海外扩张"]

E --> E8["Competitive Change
• 谁在扩产
• 谁在降价
• 谁拿新客户
• 谁推出新技术
• 优势增强 / 削弱"]

%% =========================
%% STEP 4 COMPANY
%% =========================
E --> F["Step 4：公司基本面"]

F --> F1["公司基本情况
• 成立时间
• 主营业务
• 产品 / 服务
• 收入来源
• 地区结构"]

F --> F2["行业定位
• 所处赛道
• 产业链位置
• 行业发展阶段
• 公司市场地位
• 市占率"]

F --> F3["业务阶段 / Business Stage
• 导入期
• 成长期
• 成熟期
• 平台期
• 衰退期
• 新业务 vs 老业务阶段"]

F --> F4["商业模式
• 如何赚钱
• 收费模式
• Revenue Driver
• Volume × Price
• 客户数 × ARPU
• 产能 × 利用率 × ASP"]

F --> F5["客户与产品
• 客户类型
• Top 1 / Top 5
• 客户集中度
• 留存 / 流失
• 核心产品
• 新产品 Pipeline"]

F --> F6["上下游关系
• 供应商
• 原材料
• 渠道
• 客户
• 公司议价能力"]

F --> F7["竞争壁垒 / Moat
• 成本壁垒
• 技术壁垒
• 品牌壁垒
• 渠道壁垒
• 规模壁垒
• 牌照壁垒
• 数据 / Network Effect
• Switching Cost"]

F --> F8["劣势 / Weakness
• 技术短板
• 产品短板
• 成本劣势
• 客户集中
• 地区集中
• 品牌弱
• 规模不足
• 管理短板"]

F --> F9["增长来源
• 行业增长
• Gain Share
• Volume
• Price
• 新产品
• 新客户
• 新地区
• M&A"]

F --> F10["Corporate Development
• BD
• Licensing
• Milestone Payment
• Partnership
• Joint Venture
• 潜在 M&A
• 被收购可能性"]

%% =========================
%% STEP 4B SHAREHOLDER / INVESTOR
%% =========================
F --> S["Step 4B：股东、投资者与资本结构分析"]

S --> S1["股权结构 / Ownership
• 创始人持股
• 管理层持股
• 控股股东
• 实际控制人
• Free Float
• 集中度"]

S --> S2["股东类型
• Founder
• Family Office
• PE / VC
• Sovereign Fund
• Long-only Fund
• Hedge Fund
• 国资
• Corporate Investor"]

S --> S3["主要机构股东
• Top 10 Shareholders
• 持仓比例
• 新增 / 减持
• 持仓周期
• 是否长期持有"]

S --> S4["融资历史
• Seed / VC / PE
• Pre-IPO
• IPO
• Follow-on
• Placement
• Rights Issue
• CB / 可转债"]

S --> S5["融资价格与估值
• 每轮融资价格
• Post-money Valuation
• IPO Price
• 当前价格
• 老股东成本
• 潜在浮盈 / 浮亏"]

S --> S6["战略投资者
• 谁投资
• 投资金额
• 投资价格
• 战略目的
• 业务合作
• 渠道 / 技术 / 客户资源
• 是否真正产生协同"]

S --> S7["基石投资者 / Cornerstone Investors
• 投资者名单
• 认购金额
• 占 IPO 比例
• 配售价
• Lock-up Period
• 投资者背景
• 战略相关性
• 是否为财务投资者"]

S --> S8["基石质量判断
• 是否知名机构
• 是否产业资本
• 是否与公司存在业务关系
• 是否重复参与类似 IPO
• 是否可能只是稳定发行
• 是否具有价格发现意义"]

S --> S9["Anchor / Pre-IPO Investors
• Pre-IPO 投资时间
• Entry Price
• Discount to IPO
• 特殊权利
• 回购条款
• 对赌条款
• 优先清算权"]

S --> S10["老股东行为
• IPO 是否售旧股
• Secondary Sale
• 大股东是否套现
• 上市后持续减持
• Lock-up 到期
• 股东质押
• 股份转让"]

S --> S11["股东变化趋势
• 机构持仓增加 / 减少
• Founder Ownership 变化
• Insider Buying
• Insider Selling
• Activist Investor
• Ownership Concentration"]

S --> S12["投资者结构
• Long-only vs Hedge Fund
• Domestic vs Overseas
• Retail vs Institutional
• Passive vs Active
• Concentrated vs Diversified"]

S --> S13["投资者预期分析
• 当前股东为什么持有
• 市场关注哪些 KPI
• 市场主要 Thesis
• Consensus Positioning
• Crowded Trade 风险"]

S --> S14["资本市场行为
• Buyback
• Dividend
• Placement
• Share Issuance
• ESOP
• Stock Options
• 股权稀释"]

S --> S15["Ownership Red Flags
• 控股股东频繁减持
• 高比例质押
• 关联方持股复杂
• Nominee Shareholder
• 多层 Offshore Structure
• 频繁融资
• 大比例稀释
• Pre-IPO 投资者短期退出"]

%% =========================
%% STEP 5 FINANCIAL DD
%% =========================
S --> G["Step 5：财务尽调"]

G --> G0["财务尽调原则
• 必须做历史对比
• 必须做 Peer 对比
• 必须做结构对比
• 必须识别异常项"]

G --> G1["收入分析
• Revenue
• Organic Growth
• Volume
• ASP
• 产品 / 地区 / 客户结构"]

G --> G2["盈利能力
• Gross Margin
• EBITDA Margin
• EBIT Margin
• Net Margin"]

G --> G3["现金流
• OCF
• FCF
• EBITDA → OCF
• NI → OCF"]

G --> G4["营运资金
• AR
• AP
• Inventory
• DSO
• DPO
• CCC"]

G --> G5["CAPEX & Balance Sheet
• Maintenance CAPEX
• Growth CAPEX
• CAPEX / Revenue
• Cash
• Debt
• Liquidity
• Leverage"]

G --> G6["资本回报
• ROE
• ROA
• ROIC
• ROIC vs WACC"]

G --> G7["历史对比
• YoY
• QoQ
• 3Y CAGR
• 5Y Trend
• 周期不同阶段表现"]

G --> G8["Peer 对比
• Revenue Growth
• Margin
• ROIC
• DSO
• Inventory Days
• CAPEX
• FCF"]

G --> G9["结构对比
• 产品 Mix
• 地区 Mix
• 客户 Mix
• 新旧业务
• 高毛利 vs 低毛利"]

G --> G10["Red Flags
• Revenue ↑ / AR ↑↑
• DSO 持续上升
• Inventory > Revenue Growth
• Margin 异常
• NI 长期 > OCF
• CAPEX 激增
• 短债增加
• 激进资本化
• 一次性收益
• 关联交易"]

G10 --> G11{"是否存在异常？"}

G11 -- Yes --> VERIFY["进一步验证
• 查原始财报
• 查 Notes
• 对比历史
• 对比 Peer
• 查客户 / 供应商
• 渠道验证
• 管理层解释"]

VERIFY --> G
G11 -- No --> MG

%% =========================
%% MANAGEMENT & GOVERNANCE
%% =========================
G --> MG["Step 5B：管理层与治理"]

MG --> MG1["管理层背景
• Founder
• CEO / CFO
• 核心团队
• 行业经验"]

MG --> MG2["执行力
• Guidance vs Actual
• 战略兑现
• CAPEX 落地
• 新业务推进"]

MG --> MG3["激励机制
• Management Ownership
• Options
• KPI
• Bonus"]

MG --> MG4["资本配置
• CAPEX
• M&A
• Buyback
• Dividend
• Debt Repayment"]

MG --> MG5["治理风险
• Related Party
• 资金占用
• 股权稀释
• Insider Selling
• 审计问题"]

%% =========================
%% STEP 6 VALUATION
%% =========================
MG --> H["Step 6：估值"]

H --> H1["Relative Valuation
• PE
• PS
• EV / EBITDA
• EV / Sales
• P/B
• FCF Yield"]

H --> H2["Comparable Companies
• Peer Multiple
• Growth
• Margin
• ROIC
• Premium / Discount"]

H --> H3["Historical Valuation
• 3Y
• 5Y
• 10Y
• 当前历史位置"]

H --> H4["DCF
• Revenue
• Margin
• FCF
• WACC
• Terminal Growth"]

H --> H5["Implied Expectations
• 隐含 Revenue Growth
• 隐含 Margin
• 隐含 Market Share
• 市场 Price-in 什么"]

H --> H6["Investor Cost Comparison
• IPO Price
• Cornerstone Cost
• Pre-IPO Cost
• Current Price
• Major Shareholder Cost"]

%% =========================
%% STEP 7 CATALYST
%% =========================
H --> I["Step 7：Catalyst"]

I --> I1["公司 Catalyst
• 新产品
• 新客户
• 新产能
• 提价
• BD / Licensing
• M&A"]

I --> I2["行业 Catalyst
• 行业周期
• 供需改善
• 原材料下降
• 竞争对手退出"]

I --> I3["政策 / 技术 Catalyst
• 政策
• 临床数据
• FDA / NMPA
• 技术突破"]

I --> I4["资本市场 Catalyst
• IPO
• Spin-off
• Buyback
• Dividend
• Index Inclusion"]

I --> I5["Ownership Catalyst
• 基石解禁
• Pre-IPO 解禁
• 大股东增持 / 减持
• Strategic Investor 入股
• Activist Entry"]

%% =========================
%% STEP 8 RISK
%% =========================
I --> J["Step 8：Risk"]

J --> J1["行业风险
• 周期
• 需求下降
• 产能过剩"]

J --> J2["竞争风险
• Price War
• Lose Share
• 新进入者"]

J --> J3["技术风险
• 技术替代
• 产品失败
• 临床失败"]

J --> J4["经营风险
• 客户集中
• 原材料
• 供应链
• 执行风险"]

J --> J5["财务风险
• Debt
• Liquidity
• Cash Burn
• Accounting"]

J --> J6["政策风险"]

J --> J7["估值风险"]

J --> J8["股东与资本市场风险
• 大股东减持
• 基石解禁
• Pre-IPO 解禁
• 股权稀释
• Placement
• 股东质押
• 控制权变化"]

%% =========================
%% INVESTMENT THESIS
%% =========================
J --> K["形成 Investment Thesis"]

K --> K1["Industry
• 为什么现在看这个行业？"]

K --> K2["Company
• 为什么是这家公司？
• 当前处于什么业务阶段？"]

K --> K3["Moat vs Weakness
• 壁垒是否成立？
• 劣势是否可改善？"]

K --> K4["Competitive Position
• 为什么不是 Peer？
• 优势增强还是削弱？"]

K --> K5["Ownership
• 谁拥有公司？
• 谁在买？
• 谁在卖？
• 资本是否真正支持长期价值？"]

K --> K6["Growth
• 增长来自哪里？"]

K --> K7["Earnings
• Consensus 哪些假设可能错？"]

K --> K8["Valuation
• 市场当前 Price-in 什么？"]

K --> K9["Variant View
• 市场相信什么？
• 我们与市场分歧是什么？"]

K --> K10["Catalyst
• 什么推动 Re-rating？"]

K --> K11["Kill Thesis
• 什么情况证明我们错了？"]

%% =========================
%% FINAL OUTPUT
%% =========================
K --> L["最终投资结论"]

L --> L1["核心 Thesis"]

L --> L2["3–5 个关键理由"]

L --> L3["估值区间"]

L --> L4["Catalyst Timeline"]

L --> L5["主要风险"]

L --> L6["Ownership View
• 股东质量
• 基石质量
• 解禁压力
• Insider 行为
• 稀释风险"]

L --> L7["KPI Monitoring
• Revenue / Volume / ASP
• Market Share
• Margin
• DSO / Inventory
• CAPEX / FCF
• Peer Pricing
• Peer CAPEX
• Institutional Ownership
• Insider Transactions"]

L7 --> M["持续跟踪更新"]

M --> C

%% =========================
%% AI RESEARCH LOOP
%% =========================
AI["AI 在研究中的作用
• 快速整理资料
• 总结公告
• 比较多份资料
• 发现潜在线索"]

AI --> AI1["AI → 找线索 → 找原始 Material → Cross-check → 独立判断"]

AI1 -.辅助研究.-> C

AIR["AI 风险
• Hallucination
• 同源错误
• 二手资料错误
• 缺少行业上下文
• 无法判断管理层可信度"]

AIR -.风险控制.-> AI1