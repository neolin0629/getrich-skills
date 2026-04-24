<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>周复盘报告 | {{WEEK_DATE}}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0f0f1a;
            color: #c0c0d0;
            font-family: 'Microsoft YaHei', 'Segoe UI', -apple-system, sans-serif;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        
        /* 标题区 */
        .header {
            text-align: center;
            padding: 30px 20px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px;
            margin-bottom: 30px;
            border: 1px solid #333355;
        }
        .header h1 {
            font-size: 28px;
            color: #fff;
            margin-bottom: 10px;
        }
        .header .subtitle {
            color: #888899;
            font-size: 14px;
        }
        .header .period {
            display: inline-block;
            background: #e74c3c;
            color: white;
            padding: 5px 20px;
            border-radius: 20px;
            font-size: 14px;
            margin-top: 15px;
        }

        /* 卡片 */
        .card {
            background: #1a1a2e;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            border: 1px solid #333355;
        }
        .card-title {
            color: #f1c40f;
            font-size: 16px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #333355;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .card-title .icon {
            font-size: 20px;
        }

        /* 涨跌颜色 */
        .up { color: #e74c3c; }
        .down { color: #27ae60; }
        .neutral { color: #f1c40f; }

        /* 表格 */
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #333355;
        }
        th {
            color: #888899;
            font-weight: 500;
            font-size: 13px;
        }
        td {
            color: #d0d0e0;
            font-size: 14px;
        }
        tr:hover td {
            background: #252540;
        }

        /* 图表区 */
        .chart-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin-top: 15px;
        }
        .chart-item {
            background: #252540;
            border-radius: 8px;
            padding: 15px;
        }
        .chart-item img {
            width: 100%;
            border-radius: 5px;
        }
        .chart-item .title {
            color: #c0c0d0;
            font-size: 13px;
            text-align: center;
            margin-top: 10px;
        }

        /* 流动性信号灯 */
        .signal-lights {
            display: flex;
            justify-content: space-around;
            margin: 20px 0;
        }
        .signal-item {
            text-align: center;
        }
        .signal-light {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            margin: 0 auto 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }
        .signal-green { background: #27ae60; }
        .signal-yellow { background: #f1c40f; }
        .signal-red { background: #e74c3c; }
        .signal-label {
            color: #888899;
            font-size: 12px;
        }

        /* 结论区 */
        .conclusion {
            background: #252540;
            border-radius: 8px;
            padding: 20px;
            margin-top: 15px;
        }
        .conclusion-item {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
        }
        .conclusion-item:last-child { margin-bottom: 0; }
        .conclusion-bullet {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-top: 8px;
            flex-shrink: 0;
        }
        .conclusion-text {
            color: #d0d0e0;
            font-size: 14px;
        }

        /* 底部 */
        .footer {
            text-align: center;
            padding: 30px;
            color: #666677;
            font-size: 12px;
        }

        /* 全宽图表 */
        .chart-full { grid-column: 1 / -1; }
        
        /* 涨跌箭头 */
        .arrow-up::before { content: '▲ '; }
        .arrow-down::before { content: '▼ '; }
    </style>
</head>
<body>
    <div class="container">
        <!-- 标题区 -->
        <div class="header">
            <h1>📊 A股·期权·全球市场·流动性 周复盘</h1>
            <div class="subtitle">MillerQuant 量化分析系统</div>
            <div class="period">{{WEEK_DATE}}（{{WEEK_PERIOD}}）</div>
        </div>

        <!-- 一、本周市场快照 -->
        <div class="card">
            <div class="card-title"><span class="icon">📈</span> 一、本周市场快照</div>
            
            <!-- A股指数 -->
            <h3 style="color:#fff;margin:15px 0 10px;">A股指数</h3>
            <table>
                <thead>
                    <tr>
                        <th>指数</th>
                        <th>周一开盘</th>
                        <th>周五收盘</th>
                        <th>涨跌幅</th>
                        <th>趋势</th>
                    </tr>
                </thead>
                <tbody>
                    {{A_INDEX_TABLE}}
                </tbody>
            </table>

            <!-- 全球市场 -->
            <h3 style="color:#fff;margin:25px 0 10px;">全球市场</h3>
            <table>
                <thead>
                    <tr>
                        <th>市场</th>
                        <th>周一</th>
                        <th>周五</th>
                        <th>涨跌幅</th>
                        <th>趋势</th>
                    </tr>
                </thead>
                <tbody>
                    {{GLOBAL_TABLE}}
                </tbody>
            </table>

            <!-- 商品期货 -->
            <h3 style="color:#fff;margin:25px 0 10px;">商品期货</h3>
            <table>
                <thead>
                    <tr>
                        <th>品种</th>
                        <th>周一</th>
                        <th>周五</th>
                        <th>涨跌幅</th>
                        <th>趋势</th>
                    </tr>
                </thead>
                <tbody>
                    {{COMMODITY_TABLE}}
                </tbody>
            </table>

            <!-- 涨跌停统计 -->
            <div style="margin-top:25px;display:flex;gap:30px;">
                <div style="background:#252540;padding:15px 25px;border-radius:8px;">
                    <div style="color:#888899;font-size:12px;">涨停家数</div>
                    <div style="color:#e74c3c;font-size:24px;font-weight:bold;">{{ZT_COUNT}}</div>
                </div>
                <div style="background:#252540;padding:15px 25px;border-radius:8px;">
                    <div style="color:#888899;font-size:12px;">跌停家数</div>
                    <div style="color:#27ae60;font-size:24px;font-weight:bold;">{{DT_COUNT}}</div>
                </div>
                <div style="background:#252540;padding:15px 25px;border-radius:8px;">
                    <div style="color:#888899;font-size:12px;">VIX</div>
                    <div style="color:#f1c40f;font-size:24px;font-weight:bold;">{{VIX}}</div>
                </div>
            </div>
        </div>

        <!-- 二、期权市场分析 -->
        <div class="card">
            <div class="card-title"><span class="icon">📉</span> 二、期权市场分析</div>
            
            <table>
                <thead>
                    <tr>
                        <th>品种</th>
                        <th>当前IV</th>
                        <th>历史分位数</th>
                        <th>IV水位</th>
                    </tr>
                </thead>
                <tbody>
                    {{OPTIONS_TABLE}}
                </tbody>
            </table>

            <div class="conclusion">
                <h4 style="color:#f1c40f;margin-bottom:10px;">📋 期权策略建议</h4>
                <div class="conclusion-item">
                    <div class="conclusion-bullet" style="background:#3498db;"></div>
                    <div class="conclusion-text">
                        <strong>50ETF期权：</strong>{{OPTIONS_50}}
                    </div>
                </div>
                <div class="conclusion-item">
                    <div class="conclusion-bullet" style="background:#e74c3c;"></div>
                    <div class="conclusion-text">
                        <strong>300ETF期权：</strong>{{OPTIONS_300}}
                    </div>
                </div>
            </div>
        </div>

        <!-- 三、流动性监测 -->
        <div class="card">
            <div class="card-title"><span class="icon">💧</span> 三、流动性监测</div>
            
            <!-- 信号灯 -->
            <div class="signal-lights">
                <div class="signal-item">
                    <div class="signal-light signal-{{SIGNAL_T1}}">●</div>
                    <div class="signal-label">Tier1 全球</div>
                    <div style="color:#888;font-size:11px;">{{SIGNAL_T1_DESC}}</div>
                </div>
                <div class="signal-item">
                    <div class="signal-light signal-{{SIGNAL_T2}}">●</div>
                    <div class="signal-label">Tier2 宏观</div>
                    <div style="color:#888;font-size:11px;">{{SIGNAL_T2_DESC}}</div>
                </div>
                <div class="signal-item">
                    <div class="signal-light signal-{{SIGNAL_T3}}">●</div>
                    <div class="signal-label">Tier3 微观</div>
                    <div style="color:#888;font-size:11px;">{{SIGNAL_T3_DESC}}</div>
                </div>
                <div class="signal-item">
                    <div class="signal-light signal-{{SIGNAL_TOTAL}}">●</div>
                    <div class="signal-label">综合</div>
                    <div style="color:#888;font-size:11px;">{{SIGNAL_TOTAL_DESC}}</div>
                </div>
            </div>

            <!-- 流动性图表 -->
            <h3 style="color:#fff;margin:20px 0 15px;">流动性趋势图（1年期）</h3>
            <div class="chart-grid">
                <div class="chart-item">
                    <img src="L-chart1_cb_assets.png" alt="央行资产">
                    <div class="title">央行资产负债表</div>
                </div>
                <div class="chart-item">
                    <img src="L-chart2_dr007_spread.png" alt="DR007">
                    <div class="title">DR007 vs 逆回购利率</div>
                </div>
                <div class="chart-item">
                    <img src="L-chart4_volume_margin.png" alt="融资余额">
                    <div class="title">融资余额趋势</div>
                </div>
                <div class="chart-item">
                    <img src="L-chart5_csi_m2.png" alt="M2社融">
                    <div class="title">M2同比 vs 社融增量</div>
                </div>
                <div class="chart-item">
                    <img src="L-chart6_dxy_vix.png" alt="美元利率">
                    <div class="title">EFFR vs SOFR</div>
                </div>
                <div class="chart-item">
                    <img src="L-chart7_shibor_spread.png" alt="Shibor">
                    <div class="title">Shibor利率走势</div>
                </div>
                <div class="chart-item">
                    <img src="L-chart8_heatmap.png" alt="信号灯">
                    <div class="title">流动性信号灯热力图</div>
                </div>
                <div class="chart-item chart-full">
                    <img src="L-chart9_pbc_repo.png" alt="逆回购投放" style="width:49%;display:inline-block;">
                    <img src="L-chart9_pbc_repo_bot.png" alt="逆回购存量" style="width:49%;display:inline-block;">
                    <div class="title">央行买断式逆回购：月度投放量（左）+ 存量余额（右）</div>
                </div>
            </div>

            <div class="conclusion">
                <h4 style="color:#f1c40f;margin-bottom:10px;">📋 流动性核心结论</h4>
                <div class="conclusion-item">
                    <div class="conclusion-bullet" style="background:#27ae60;"></div>
                    <div class="conclusion-text"><strong>全球：</strong>{{LIQ_GLOBAL}}</div>
                </div>
                <div class="conclusion-item">
                    <div class="conclusion-bullet" style="background:#3498db;"></div>
                    <div class="conclusion-text"><strong>宏观：</strong>{{LIQ_MACRO}}</div>
                </div>
                <div class="conclusion-item">
                    <div class="conclusion-bullet" style="background:#9b59b6;"></div>
                    <div class="conclusion-text"><strong>微观：</strong>{{LIQ_MICRO}}</div>
                </div>
            </div>
        </div>

        <!-- 四、下周展望 -->
        <div class="card">
            <div class="card-title"><span class="icon">🔮</span> 四、下周展望</div>
            <div class="conclusion">
                <div class="conclusion-item">
                    <div class="conclusion-bullet" style="background:#f1c40f;"></div>
                    <div class="conclusion-text">{{OUTLOOK_1}}</div>
                </div>
                <div class="conclusion-item">
                    <div class="conclusion-bullet" style="background:#f1c40f;"></div>
                    <div class="conclusion-text">{{OUTLOOK_2}}</div>
                </div>
                <div class="conclusion-item">
                    <div class="conclusion-bullet" style="background:#f1c40f;"></div>
                    <div class="conclusion-text">{{OUTLOOK_3}}</div>
                </div>
            </div>
        </div>

        <!-- 底部 -->
        <div class="footer">
            <p>报告生成时间：{{GENERATE_TIME}}</p>
            <p>数据来源：AkShare + yfinance + FRED API</p>
            <p>MillerQuant 量化分析系统 | 周复盘 v6.0</p>
        </div>
    </div>
</body>
</html>
