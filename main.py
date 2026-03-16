import os
import flet as ft
import akshare as ak
import pandas as pd
import threading
import traceback
import requests

# ==========================================
# 终极网络屏蔽模块 (Monkey Patch)
# ==========================================
_original_session_request = requests.Session.request

def _patched_request(self, method, url, **kwargs):
    mode = os.environ.get("APP_NET_MODE", "direct")
    if mode == "direct":
        kwargs["proxies"] = {"http": None, "https": None}
    elif mode == "custom":
        proxy_url = os.environ.get("APP_CUSTOM_PROXY", "")
        kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
    return _original_session_request(self, method, url, **kwargs)

requests.Session.request = _patched_request

def apply_network_settings(mode, proxy_url=""):
    os.environ["APP_NET_MODE"] = mode
    os.environ["APP_CUSTOM_PROXY"] = proxy_url

# ==========================================
# 核心数据与分析模块
# ==========================================
def fetch_and_analyze(stock_code):
    try:
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", adjust="qfq")
        if df.empty:
            return None, "未找到该股票数据，请检查代码是否正确（如：600519）。"
        
        df = df.tail(60).copy()
        df['MA20'] = df['收盘'].rolling(window=20).mean()
        df['Vol_MA5'] = df['成交量'].rolling(window=5).mean()
        
        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        
        analysis_result = {
            "name": f"{stock_code}",
            "trend": {},
            "sentiment": {},
            "money": {}
        }
        
        # --- 判断1：大方向 ---
        if today['收盘'] >= today['MA20']:
            analysis_result['trend'] = {"status": "顺风期 🟢", "desc": "当前价格在月均线之上，大趋势向上，处于健康状态。", "color": ft.Colors.GREEN_400}
        else:
            analysis_result['trend'] = {"status": "逆风期 🔴", "desc": "当前价格跌破月均线，趋势向下，大家都在亏钱，切勿盲目抄底。", "color": ft.Colors.RED_400}
            
        # --- 判断2：情绪面 ---
        past_5_days_close = df.iloc[-6]['收盘']
        return_5d = (today['收盘'] - past_5_days_close) / past_5_days_close * 100
        if return_5d > 15:
            analysis_result['sentiment'] = {"status": "极度危险 🔴", "desc": f"近5日已暴涨 {return_5d:.2f}%，情绪极度亢奋，极容易成为接盘侠！", "color": ft.Colors.RED_400}
        elif return_5d < -15:
            analysis_result['sentiment'] = {"status": "跌无可跌 🟢", "desc": f"近5日暴跌 {return_5d:.2f}%，短期风险释放，可能有反弹机会。", "color": ft.Colors.GREEN_400}
        else:
            analysis_result['sentiment'] = {"status": "情绪平稳 ⚪", "desc": "近期涨跌幅正常，没有极端的过热或过冷现象。", "color": ft.Colors.BLUE_200}
            
        # --- 判断3：资金面 ---
        vol_ratio = today['成交量'] / today['Vol_MA5']
        if today['收盘'] > yesterday['收盘'] and vol_ratio > 1.5:
            analysis_result['money'] = {"status": "主力抢筹 🟢", "desc": "放量上涨！成交量是平时的1.5倍以上，有大资金真金白银在买入。", "color": ft.Colors.GREEN_400}
        elif today['收盘'] < yesterday['收盘'] and vol_ratio > 1.5:
            analysis_result['money'] = {"status": "恐慌出逃 🔴", "desc": "放量大跌！伴随巨量抛单，主力大概率在疯狂出货，赶紧躲开！", "color": ft.Colors.RED_400}
        elif today['收盘'] > yesterday['收盘'] and vol_ratio < 0.8:
            analysis_result['money'] = {"status": "诱多警告 🔴", "desc": "无量上涨！价格虽然涨了，但买盘资金很少，典型的虚张声势，容易掉下来。", "color": ft.Colors.ORANGE_400}
        else:
            analysis_result['money'] = {"status": "资金平稳 ⚪", "desc": "今日量价表现正常，没有明显的大资金异动。", "color": ft.Colors.BLUE_200}

        return df, analysis_result
    
    except Exception as e:
        err_str = str(e)
        if "Connection" in err_str or "RemoteDisconnected" in err_str or "Timeout" in err_str:
            human_err = "🔴 网络连接被拒绝！(东方财富服务器封锁了海外IP)\n请检查代理设置或切换至全局模式。"
            return None, human_err
        return None, f"获取数据失败，错误信息: {err_str}"


# ==========================================
# 原生 UI 手搓 K线图
# ==========================================
def create_pure_flet_chart(df):
    max_price = df['最高'].max()
    min_price = df['最低'].min()
    price_range = max_price - min_price if max_price != min_price else 1
    max_vol = df['成交量'].max()
    
    chart_height = 200 
    vol_height = 60    
    
    day_columns = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        open_p = row['开盘']
        close_p = row['收盘']
        high_p = row['最高']
        low_p = row['最低']
        vol = row['成交量']
        date_str = str(row['日期'])[:10]
        
        is_red = close_p >= open_p
        color = ft.Colors.RED_400 if is_red else ft.Colors.GREEN_400
        
        top_y = chart_height - ((max(open_p, close_p) - min_price) / price_range * chart_height)
        bottom_y = chart_height - ((min(open_p, close_p) - min_price) / price_range * chart_height)
        high_y = chart_height - ((high_p - min_price) / price_range * chart_height)
        low_y = chart_height - ((low_p - min_price) / price_range * chart_height)
        
        body_height = max(bottom_y - top_y, 2)
        tooltip_text = f"{date_str}\n高: {high_p:.2f}  开: {open_p:.2f}\n低: {low_p:.2f}  收: {close_p:.2f}\n量: {vol}"
        
        shadow = ft.Container(width=2, height=max(low_y - high_y, 1), bgcolor=color, top=high_y, left=3)
        body = ft.Container(width=8, height=body_height, bgcolor=color, top=top_y, left=0)
        
        k_line = ft.Stack([shadow, body], width=8, height=chart_height)
        k_line_container = ft.Container(content=k_line, tooltip=tooltip_text)
        
        v_h = (vol / max_vol) * vol_height if max_vol > 0 else 0
        vol_bar = ft.Container(width=8, height=max(v_h, 2), bgcolor=color, tooltip=f"成交量: {vol}")
        
        day_col = ft.Column([
            k_line_container,
            ft.Container(height=5),
            vol_bar
        ], spacing=0, alignment=ft.MainAxisAlignment.END)
        
        day_columns.append(day_col)

    chart_row = ft.Row(day_columns, spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
    
    return ft.Column([
        ft.Text(f"纯UI渲染蜡烛图 | 近60日最高价: {max_price:.2f} | 最低价: {min_price:.2f}", color=ft.Colors.GREY_500, size=12),
        ft.Container(content=chart_row, padding=10, bgcolor=ft.Colors.SURFACE_VARIANT, border_radius=8)
    ])


# ==========================================
# 全新多页面 UI 架构
# ==========================================
def main(page: ft.Page):
    page.title = "自研极客股票分析器"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0  # 移除全局内边距，让视图自己控制
    page.theme = ft.Theme(font_family="Roboto")
    
    # 状态管理
    app_state = {
        "stocks_list": ["000001", "600519"], # 默认演示用的代码
        "stocks_data": {} # 存储每个代码的数据 { "600519": {"status": "loaded", "df": df, "result": result} }
    }

    # ================= UI 组件 =================
    # 1. 顶部网络配置栏 (持久存在内存中，保持状态)
    net_mode = ft.Dropdown(
        width=130, height=40, text_size=12,
        options=[
            ft.dropdown.Option("direct", "直连(屏蔽)"),
            ft.dropdown.Option("system", "系统代理"),
            ft.dropdown.Option("custom", "自定义"),
        ],
        value="direct", border_color=ft.Colors.GREY_700, content_padding=5
    )
    proxy_input = ft.TextField(
        hint_text="http://127.0.0.1:7890", height=40, text_size=12,
        width=160, value="http://127.0.0.1:7890", visible=False, content_padding=10
    )
    def on_net_mode_change(e):
        proxy_input.visible = (net_mode.value == "custom")
        page.update()
    net_mode.on_change = on_net_mode_change

    def toggle_theme(e):
        page.theme_mode = ft.ThemeMode.LIGHT if page.theme_mode == ft.ThemeMode.DARK else ft.ThemeMode.DARK
        page.update()

    theme_icon = ft.IconButton(icon=ft.Icons.DARK_MODE, on_click=toggle_theme)

    # 2. 底部添加股票栏
    stock_input = ft.TextField(
        hint_text="输入6位代码", expand=True, border_color=ft.Colors.CYAN_700,
        text_style=ft.TextStyle(font_family="monospace"), height=50, content_padding=10
    )

    # 3. 主网格视图 (对照需求图中间的 2x3 布局)
    grid = ft.GridView(
        expand=True,
        runs_count=2, # 双列布局
        max_extent=220, # 最小宽度限制
        child_aspect_ratio=1.1, # 卡片宽高比
        spacing=10,
        run_spacing=10,
        padding=15
    )

    def show_toast(message):
        page.overlay.append(ft.SnackBar(ft.Text(message), open=True))
        page.update()

    # 删除股票
    def remove_stock(code):
        if code in app_state["stocks_list"]:
            app_state["stocks_list"].remove(code)
        if code in app_state["stocks_data"]:
            del app_state["stocks_data"][code]
        update_grid()

    # 刷新并生成网格内容
    def update_grid():
        grid.controls.clear()
        for code in app_state["stocks_list"]:
            data_info = app_state["stocks_data"].get(code, {"status": "init"})
            
            if data_info["status"] in ["init", "loading"]:
                # 加载中卡片
                card = ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text(code, weight="bold", size=18),
                            ft.ProgressRing(width=30, height=30)
                        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=20
                    ), elevation=2
                )
            elif data_info["status"] == "error":
                # 错误卡片
                card = ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Row([ft.Text(code, weight="bold"), ft.IconButton(ft.Icons.CLOSE, icon_size=16, on_click=lambda e, c=code: remove_stock(c))], alignment="spaceBetween"),
                            ft.Text(data_info["msg"], color="red", size=12, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS)
                        ]), padding=10
                    ), elevation=2
                )
            else:
                # 成功加载摘要卡片 (对应图片中的方块)
                res = data_info["result"]
                df = data_info["df"]
                latest_price = df.iloc[-1]['收盘']
                prev_price = df.iloc[-2]['收盘']
                change_pct = (latest_price - prev_price) / prev_price * 100
                color = ft.Colors.RED_400 if change_pct >= 0 else ft.Colors.GREEN_400
                sign = "+" if change_pct >= 0 else ""

                card = ft.Card(
                    content=ft.Container(
                        on_click=lambda e, c=code: page.go(f"/detail/{c}"), # 点击进入详情页
                        padding=15,
                        ink=True, # 点击波纹效果
                        content=ft.Column([
                            ft.Row([
                                ft.Text(res['name'], weight="bold", size=18),
                                ft.IconButton(ft.Icons.CLOSE, icon_size=14, padding=0, width=24, height=24, on_click=lambda e, c=code: remove_stock(c))
                            ], alignment="spaceBetween"),
                            ft.Text(f"¥{latest_price:.2f}", size=26, color=color, weight="bold"),
                            ft.Text(f"{sign}{change_pct:.2f}%", size=14, color=color),
                            ft.Divider(height=10),
                            ft.Text(f"{res['trend']['status']}", size=12, color=res['trend']['color']),
                            ft.Text(f"{res['money']['status']}", size=12, color=res['money']['color']),
                        ], spacing=3)
                    ), elevation=3
                )
            grid.controls.append(card)
        page.update()

    # 异步拉取数据任务
    def fetch_stock_task(code):
        apply_network_settings(net_mode.value, proxy_input.value.strip())
        df, result = fetch_and_analyze(code)
        if df is None:
            app_state["stocks_data"][code] = {"status": "error", "msg": result}
        else:
            app_state["stocks_data"][code] = {"status": "loaded", "df": df, "result": result}
        update_grid()

    # 添加股票按钮事件
    def on_add_click(e):
        code = stock_input.value.strip()
        if len(code) != 6 or not code.isdigit():
            show_toast("请输入6位纯数字股票代码！")
            return
        if code not in app_state["stocks_list"]:
            app_state["stocks_list"].append(code)
        
        app_state["stocks_data"][code] = {"status": "loading"}
        stock_input.value = ""
        update_grid()
        threading.Thread(target=fetch_stock_task, args=(code,), daemon=True).start()

    add_btn = ft.ElevatedButton("追踪", icon=ft.Icons.ADD, height=50, on_click=on_add_click, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE))

    # 初始化启动时加载默认数据
    for default_code in app_state["stocks_list"]:
        app_state["stocks_data"][default_code] = {"status": "loading"}
        threading.Thread(target=fetch_stock_task, args=(default_code,), daemon=True).start()


    # ================= 路由管理器 =================
    def route_change(route):
        page.views.clear()

        # --- 主界面视图 (Home) ---
        page.views.append(
            ft.View(
                "/",
                [
                    # 顶栏结构
                    ft.Container(
                        padding=ft.padding.only(left=15, right=15, top=10, bottom=5),
                        content=ft.Column([
                            ft.Row([ft.Text("极客股票终端", size=20, weight="bold"), theme_icon], alignment="spaceBetween"),
                            ft.Row([ft.Text("网络层: ", size=12, color=ft.Colors.GREY_500), net_mode, proxy_input])
                        ])
                    ),
                    ft.Divider(height=1),
                    # 主网格区域
                    grid,
                    # 底栏输入区
                    ft.Container(
                        padding=15,
                        bgcolor=ft.Colors.SURFACE_VARIANT,
                        content=ft.Row([stock_input, add_btn])
                    )
                ],
                padding=0,
                spacing=0
            )
        )

        # --- 详情界面视图 (Detail) ---
        if page.route.startswith("/detail/"):
            code = page.route.split("/")[-1]
            data_info = app_state["stocks_data"].get(code)
            
            detail_content = []
            if data_info and data_info["status"] == "loaded":
                res = data_info["result"]
                df = data_info["df"]
                
                # 放入 K 线图
                detail_content.append(create_pure_flet_chart(df))
                
                # 放入分析报告
                for key in ['trend', 'sentiment', 'money']:
                    data = res[key]
                    title = "大方向 (趋势)" if key == 'trend' else ("情绪面 (短期风险)" if key == 'sentiment' else "资金面 (主力动向)")
                    card = ft.Card(
                        content=ft.Container(
                            padding=15,
                            content=ft.Column([
                                ft.Text(title, size=14, color=ft.Colors.GREY_500),
                                ft.Text(data['status'], size=18, weight="bold", color=data['color']),
                                ft.Text(data['desc'], size=15)
                            ])
                        ), color=ft.Colors.SURFACE_VARIANT, elevation=2
                    )
                    detail_content.append(card)
            
            page.views.append(
                ft.View(
                    f"/detail/{code}",
                    [
                        ft.AppBar(title=ft.Text(f"深度分析: {code}"), bgcolor=ft.Colors.SURFACE_VARIANT),
                        ft.Container(
                            padding=15,
                            content=ft.Column(detail_content, spacing=15, scroll=ft.ScrollMode.AUTO)
                        )
                    ],
                    scroll=ft.ScrollMode.AUTO
                )
            )
        page.update()

    def view_pop(view):
        page.views.pop()
        top_view = page.views[-1]
        page.go(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    page.go(page.route)

if __name__ == "__main__":
    ft.app(target=main)
