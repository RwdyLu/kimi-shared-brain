import dash
from dash import dcc, html

# Register redirect page for plural form of strategy URLs
# 為策略 URL 的複數形式註冊重定向頁面
dash.register_page(__name__, path_template="/strategies/<strategy_name>", title="Strategy Detail")

def layout(strategy_name=None):
    """Redirect /strategies/<name> → /strategy/<name>"""
    if strategy_name:
        return dcc.Location(href=f"/strategy/{strategy_name}", id="redirect")
    return html.Div("Invalid strategy name / 無效的策略名稱")
