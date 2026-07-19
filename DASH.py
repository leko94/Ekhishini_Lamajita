from __future__ import annotations

import hmac
import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html, no_update
from flask import Response, jsonify, request
from plotly.subplots import make_subplots

from data_service import EXCEL_FILE, SHEET_NAME, load_dashboard_payload

REFRESH_SECONDS = max(int(os.getenv("REFRESH_SECONDS", "60")), 15)
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "").strip()
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "").strip()

GREEN = "#155B3B"
LIGHT_GREEN = "#EAF5EF"
GOLD = "#E5A823"
NAVY = "#12263A"
MUTED = "#64748B"
BORDER = "#DDE5EA"
RED = "#B42318"

app = Dash(
    __name__,
    title="Ekhishini Lamajita",
    update_title="Refreshing data…",
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server


@server.route("/health")
def health() -> Response:
    return jsonify({"status": "ok", "service": "ekhishini-lamajita"})


@server.before_request
def optional_basic_auth() -> Response | None:
    """Enable browser basic authentication when both credentials are configured."""
    if not DASHBOARD_USERNAME or not DASHBOARD_PASSWORD or request.path == "/health":
        return None
    auth = request.authorization
    valid = bool(
        auth
        and hmac.compare_digest(auth.username or "", DASHBOARD_USERNAME)
        and hmac.compare_digest(auth.password or "", DASHBOARD_PASSWORD)
    )
    if valid:
        return None
    return Response(
        "Authentication required.",
        401,
        {"WWW-Authenticate": 'Basic realm="Ekhishini Lamajita"'},
    )


def money(value: float) -> str:
    return f"R {value:,.2f}"


def empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        showarrow=False,
        font={"size": 15, "color": MUTED},
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
    )
    figure.update_layout(
        template="plotly_white",
        height=360,
        margin={"l": 20, "r": 20, "t": 50, "b": 30},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


def status_component(payload: dict) -> html.Div:
    meta = payload.get("meta", {})
    if not payload.get("ok"):
        return html.Div(
            [
                html.Span("Data error", className="status-dot status-error"),
                html.Span(meta.get("error", "Unknown data error"), className="status-detail"),
            ],
            className="status-block",
        )

    loaded_at = meta.get("loaded_at", "")
    try:
        display_time = datetime.fromisoformat(loaded_at).strftime("%d %b %Y, %H:%M:%S")
    except ValueError:
        display_time = loaded_at

    children = [
        html.Span("Live", className="status-dot status-live"),
        html.Span(f"Updated {display_time}", className="status-detail"),
        html.Span(meta.get("source", ""), className="status-source"),
    ]
    if meta.get("warning"):
        children.append(html.Span(meta["warning"], className="status-warning"))
    return html.Div(children, className="status-block")


def member_options(payload: dict) -> list[dict[str, str]]:
    if not payload.get("ok"):
        return [{"label": "All members", "value": "ALL"}]
    df = pd.DataFrame(payload.get("records", []))
    if df.empty:
        return [{"label": "All members", "value": "ALL"}]
    names = sorted(df.loc[df["Type"].eq("Member"), "Name"].dropna().astype(str).unique())
    return [{"label": "All members", "value": "ALL"}] + [
        {"label": name, "value": name} for name in names
    ]


def trend_figure(df: pd.DataFrame, months: list[str], selected_member: str) -> go.Figure:
    if selected_member != "ALL":
        selected = df[df["Name"].eq(selected_member)]
        if selected.empty:
            return empty_figure("The selected member is not available.")
        monthly = selected[months].sum(axis=0)
        title = f"Monthly activity — {selected_member}"
        bar_name = "Monthly amount"
    else:
        monthly = df[months].sum(axis=0)
        title = "Monthly fund movement and cumulative value"
        bar_name = "Monthly net movement"

    cumulative = monthly.cumsum()
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=months,
            y=monthly.values,
            name=bar_name,
            marker_color=[GREEN if value >= 0 else RED for value in monthly.values],
            hovertemplate="%{x}<br>Monthly: R %{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=months,
            y=cumulative.values,
            mode="lines+markers",
            name="Cumulative",
            line={"color": GOLD, "width": 3},
            marker={"size": 7},
            hovertemplate="%{x}<br>Cumulative: R %{y:,.2f}<extra></extra>",
        ),
        secondary_y=True,
    )
    figure.update_layout(
        template="plotly_white",
        title={"text": title, "x": 0.02, "xanchor": "left"},
        height=390,
        margin={"l": 55, "r": 55, "t": 65, "b": 55},
        legend={"orientation": "h", "y": 1.12, "x": 1, "xanchor": "right"},
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    figure.update_yaxes(title_text="Monthly amount (R)", tickprefix="R ", secondary_y=False)
    figure.update_yaxes(title_text="Cumulative (R)", tickprefix="R ", secondary_y=True)
    figure.update_xaxes(tickangle=-25)
    return figure


def member_totals_figure(df: pd.DataFrame) -> go.Figure:
    members = df[df["Type"].eq("Member")].sort_values("Total", ascending=True)
    if members.empty:
        return empty_figure("No member contribution rows were found.")
    figure = go.Figure(
        go.Bar(
            x=members["Total"],
            y=members["Name"],
            orientation="h",
            marker={"color": GREEN},
            text=[money(value) for value in members["Total"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>Total: R %{x:,.2f}<extra></extra>",
        )
    )
    figure.update_layout(
        template="plotly_white",
        title={"text": "Member contribution totals", "x": 0.02, "xanchor": "left"},
        height=max(390, 60 + len(members) * 38),
        margin={"l": 130, "r": 90, "t": 65, "b": 45},
        xaxis={"title": "Total (R)", "tickprefix": "R ", "rangemode": "tozero"},
        yaxis={"title": ""},
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return figure


def heatmap_figure(df: pd.DataFrame, months: list[str]) -> go.Figure:
    members = df[df["Type"].eq("Member")]
    if members.empty:
        return empty_figure("No monthly member data are available.")
    z = members[months].to_numpy(dtype=float)
    figure = go.Figure(
        go.Heatmap(
            z=z,
            x=months,
            y=members["Name"],
            colorscale="RdYlGn",
            zmid=0,
            colorbar={"title": "R"},
            hovertemplate="%{y}<br>%{x}: R %{z:,.2f}<extra></extra>",
        )
    )
    figure.update_layout(
        template="plotly_white",
        title={"text": "Monthly contribution heatmap", "x": 0.02, "xanchor": "left"},
        height=max(390, 80 + len(members) * 42),
        margin={"l": 130, "r": 35, "t": 65, "b": 60},
        xaxis={"tickangle": -25},
        yaxis={"title": ""},
        paper_bgcolor="white",
    )
    return figure


def insight_text(df: pd.DataFrame, months: list[str]) -> str:
    members = df[df["Type"].eq("Member")]
    if members.empty:
        return "No member records are available for the summary."
    monthly_member_totals = members[months].sum(axis=0)
    strongest_month = str(monthly_member_totals.idxmax())
    strongest_value = float(monthly_member_totals.max())
    negative_months = monthly_member_totals[monthly_member_totals < 0]
    negative_note = (
        f" Net outflows occurred in {', '.join(negative_months.index.tolist())}."
        if not negative_months.empty
        else " No month has a negative overall member movement."
    )
    return (
        f"The strongest member-contribution month is {strongest_month} at "
        f"{money(strongest_value)}.{negative_note}"
    )


initial_payload = load_dashboard_payload()

app.layout = html.Div(
    className="page-shell",
    children=[
        dcc.Store(id="data-store", data=initial_payload),
        dcc.Interval(
            id="refresh-interval",
            interval=REFRESH_SECONDS * 1000,
            n_intervals=0,
        ),
        dcc.Download(id="download-data"),
        html.Header(
            className="topbar",
            children=[
                html.Div(
                    className="brand",
                    children=[
                        html.Img(src=app.get_asset_url("logoekhishishini.jpeg"), className="brand-image"),
                        html.Div(
                            [
                                html.H1("Ekhishini Lamajita"),
                                html.P("Stokvel contributions, income and monthly fund movement"),
                            ]
                        ),
                    ],
                ),
                html.Div(id="data-status", children=status_component(initial_payload)),
            ],
        ),
        html.Main(
            className="dashboard-container",
            children=[
                html.Section(
                    className="control-panel card",
                    children=[
                        html.Div(
                            className="control-group",
                            children=[
                                html.Label("Dashboard view", htmlFor="member-filter"),
                                dcc.Dropdown(
                                    id="member-filter",
                                    options=member_options(initial_payload),
                                    value="ALL",
                                    clearable=False,
                                    searchable=True,
                                ),
                            ],
                        ),
                        html.Div(
                            className="button-row",
                            children=[
                                html.Button("Refresh now", id="refresh-button", n_clicks=0, className="primary-button"),
                                html.Button("Download CSV", id="download-button", n_clicks=0, className="secondary-button"),
                            ],
                        ),
                        html.Div(
                            className="source-note",
                            children=f"Sheet: {SHEET_NAME} • Fallback file: {EXCEL_FILE} • Auto-refresh: {REFRESH_SECONDS} seconds",
                        ),
                    ],
                ),
                html.Section(
                    className="kpi-grid",
                    children=[
                        html.Div([html.P("Current fund value"), html.H2(id="fund-value")], className="kpi-card kpi-primary"),
                        html.Div([html.P("Member contributions"), html.H2(id="member-value")], className="kpi-card"),
                        html.Div([html.P("Profit / other income"), html.H2(id="income-value")], className="kpi-card"),
                        html.Div([html.P("Active members"), html.H2(id="member-count")], className="kpi-card"),
                        html.Div([html.P("Top contributor"), html.H2(id="top-member")], className="kpi-card"),
                    ],
                ),
                html.Section(
                    className="insight-card",
                    children=[html.Span("Data insight"), html.P(id="insight-text")],
                ),
                html.Section(
                    className="chart-grid chart-grid-main",
                    children=[
                        html.Div(dcc.Graph(id="trend-chart", config={"displaylogo": False}), className="card chart-card chart-wide"),
                        html.Div(dcc.Graph(id="member-chart", config={"displaylogo": False}), className="card chart-card"),
                    ],
                ),
                html.Section(
                    className="card chart-card",
                    children=[dcc.Graph(id="heatmap-chart", config={"displaylogo": False})],
                ),
                html.Section(
                    className="card table-card",
                    children=[
                        html.Div(
                            className="section-heading",
                            children=[
                                html.Div([html.H3("Detailed contribution register"), html.P("Values are recalculated from the monthly columns.")]),
                            ],
                        ),
                        dash_table.DataTable(
                            id="contribution-table",
                            page_size=12,
                            sort_action="native",
                            filter_action="native",
                            fixed_rows={"headers": True},
                            style_table={"overflowX": "auto", "maxHeight": "620px", "overflowY": "auto"},
                            style_header={
                                "backgroundColor": GREEN,
                                "color": "white",
                                "fontWeight": "700",
                                "border": "none",
                                "padding": "12px",
                            },
                            style_cell={
                                "fontFamily": "Inter, Arial, sans-serif",
                                "fontSize": "13px",
                                "padding": "10px",
                                "border": f"1px solid {BORDER}",
                                "minWidth": "105px",
                                "width": "120px",
                                "maxWidth": "170px",
                                "textAlign": "right",
                            },
                            style_cell_conditional=[
                                {"if": {"column_id": "Name"}, "textAlign": "left", "minWidth": "180px", "width": "210px"},
                                {"if": {"column_id": "Type"}, "textAlign": "center", "width": "90px", "minWidth": "80px"},
                            ],
                            style_data_conditional=[
                                {"if": {"filter_query": "{Type} = 'Income'"}, "backgroundColor": LIGHT_GREEN, "fontWeight": "700"},
                                {"if": {"filter_query": "{Total} < 0", "column_id": "Total"}, "color": RED, "fontWeight": "700"},
                            ],
                        ),
                    ],
                ),
                html.Footer(
                    [
                        html.Span("Ekhishini Lamajita"),
                        html.Span("Data refreshes from the connected GitHub Excel file."),
                    ]
                ),
            ],
        ),
    ],
)


@app.callback(
    Output("data-store", "data"),
    Output("data-status", "children"),
    Output("member-filter", "options"),
    Input("refresh-interval", "n_intervals"),
    Input("refresh-button", "n_clicks"),
)
def refresh_data(_interval_count: int, _button_clicks: int):
    payload = load_dashboard_payload()
    return payload, status_component(payload), member_options(payload)


@app.callback(
    Output("fund-value", "children"),
    Output("member-value", "children"),
    Output("income-value", "children"),
    Output("member-count", "children"),
    Output("top-member", "children"),
    Output("insight-text", "children"),
    Output("trend-chart", "figure"),
    Output("member-chart", "figure"),
    Output("heatmap-chart", "figure"),
    Output("contribution-table", "columns"),
    Output("contribution-table", "data"),
    Input("data-store", "data"),
    Input("member-filter", "value"),
)
def render_dashboard(payload: dict, selected_member: str):
    if not payload or not payload.get("ok"):
        message = payload.get("meta", {}).get("error", "The dashboard data could not be loaded.") if payload else "No data payload was received."
        empty = empty_figure(message)
        return (
            "Unavailable",
            "Unavailable",
            "Unavailable",
            "0",
            "Unavailable",
            message,
            empty,
            empty,
            empty,
            [],
            [],
        )

    df = pd.DataFrame(payload.get("records", []))
    months = payload.get("months", [])
    if df.empty or not months:
        empty = empty_figure("No usable rows were found in the spreadsheet.")
        return ("R 0.00", "R 0.00", "R 0.00", "0", "—", "No usable rows were found.", empty, empty, empty, [], [])

    for column in [*months, "Total"]:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    member_df = df[df["Type"].eq("Member")]
    income_df = df[df["Type"].eq("Income")]
    member_total = float(member_df["Total"].sum())
    income_total = float(income_df["Total"].sum())
    fund_total = float(df["Total"].sum())

    if member_df.empty:
        top_label = "—"
    else:
        top_row = member_df.loc[member_df["Total"].idxmax()]
        top_label = f"{top_row['Name']} · {money(float(top_row['Total']))}"

    table_df = df.copy()
    if selected_member and selected_member != "ALL":
        table_df = df[df["Name"].eq(selected_member)]

    columns = [
        {"name": "Member / income", "id": "Name", "type": "text"},
        {"name": "Type", "id": "Type", "type": "text"},
        *[{"name": month, "id": month, "type": "numeric", "format": {"specifier": ",.2f", "prefix": "R "}} for month in months],
        {"name": "Total", "id": "Total", "type": "numeric", "format": {"specifier": ",.2f", "prefix": "R "}},
    ]

    return (
        money(fund_total),
        money(member_total),
        money(income_total),
        f"{len(member_df):,}",
        top_label,
        insight_text(df, months),
        trend_figure(df, months, selected_member or "ALL"),
        member_totals_figure(df),
        heatmap_figure(df, months),
        columns,
        table_df.to_dict("records"),
    )


@app.callback(
    Output("download-data", "data"),
    Input("download-button", "n_clicks"),
    State("data-store", "data"),
    prevent_initial_call=True,
)
def download_csv(n_clicks: int, payload: dict):
    if not n_clicks or not payload or not payload.get("ok"):
        return no_update
    df = pd.DataFrame(payload.get("records", []))
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return dcc.send_data_frame(df.to_csv, f"ekhishini_dashboard_{stamp}.csv", index=False)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8050"))
    app.run_server(host="0.0.0.0", port=port, debug=os.getenv("DASH_DEBUG", "false").lower() == "true")
