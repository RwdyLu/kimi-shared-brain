"""Evolution V2 control and observability page."""

import json

import dash
from dash import ALL, Input, Output, State, callback, dcc, html
import dash_bootstrap_components as dbc

from ui.services.evolution_service import (
    EDITABLE_CONFIG,
    load_evolution_snapshot,
    promote_challenger,
    save_evolution_config,
)


dash.register_page(__name__, path="/evolution", title="Evolution")


def _metric_card(title, value, color="primary"):
    return dbc.Card(
        dbc.CardBody([html.Small(title, className="text-muted"), html.H4(value)]),
        color=color,
        outline=True,
    )


def _json_block(value):
    return html.Pre(
        json.dumps(value or {}, indent=2, ensure_ascii=False),
        className="bg-dark border rounded p-2 small",
        style={"maxHeight": "280px", "overflowY": "auto"},
    )


def _record_table(records, status):
    if not records:
        return dbc.Alert(f"No {status} records", color="secondary")
    return dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Symbol"), html.Th("Chromosome"), html.Th("Fitness"),
                html.Th("Generation"), html.Th("Timestamp"),
            ])),
            html.Tbody([
                html.Tr([
                    html.Td(row["symbol"]),
                    html.Td(row["chromosome_id"]),
                    html.Td(f'{row["fitness"]:.4f}' if row["fitness"] is not None else "N/A"),
                    html.Td(row["generation"]),
                    html.Td(row.get("promoted_at") or row.get("retired_at") or row.get("created_at")),
                ])
                for row in records
            ]),
        ],
        bordered=True,
        hover=True,
        responsive=True,
        size="sm",
    )


layout = dbc.Container([
    dcc.Interval(id="evolution-refresh", interval=15_000, n_intervals=0),
    dcc.Store(id="evolution-snapshot"),
    dcc.Store(id="evolution-promote-target"),
    dbc.Row([
        dbc.Col([
            html.H2("Evolution V2"),
            html.P(
                "Research state, multi-window rankings and manual deployment control. "
                "No demo ranking data is used.",
                className="text-muted",
            ),
        ], width=9),
        dbc.Col(dbc.Button("Refresh", id="evolution-refresh-button", color="secondary"), width=3),
    ], className="mb-3"),
    html.Div(id="evolution-status"),
    html.Div(id="evolution-summary"),
    dbc.Tabs([
        dbc.Tab(
            html.Div(id="evolution-progress-panel", className="pt-3"),
            label="Progress",
            tab_id="evolution-tab-progress",
        ),
        dbc.Tab(
            html.Div(id="evolution-ranking-panel", className="pt-3"),
            label="Generation Ranking",
            tab_id="evolution-tab-ranking",
        ),
        dbc.Tab(
            html.Div(id="evolution-genes-panel", className="pt-3"),
            label="Environment & Genes",
            tab_id="evolution-tab-genes",
        ),
        dbc.Tab(
            html.Div(id="evolution-archive-panel", className="pt-3"),
            label="Archive",
            tab_id="evolution-tab-archive",
        ),
        dbc.Tab(
            html.Div(id="evolution-settings-panel", className="pt-3"),
            label="Next Run Settings",
            tab_id="evolution-tab-settings",
        ),
    ], active_tab="evolution-tab-progress"),
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Confirm Promote")),
        dbc.ModalBody([
            html.P("Promoting replaces the runtime Champion and retires the previous Champion."),
            html.Div(id="evolution-promote-description", className="mb-2"),
            dbc.Label("Type the complete chromosome ID to confirm"),
            dbc.Input(id="evolution-promote-confirmation", type="text"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="evolution-promote-cancel", color="secondary"),
            dbc.Button("Promote", id="evolution-promote-confirm", color="danger"),
        ]),
    ], id="evolution-promote-modal", is_open=False),
], fluid=True)


@callback(
    Output("evolution-snapshot", "data"),
    Input("evolution-refresh", "n_intervals"),
    Input("evolution-refresh-button", "n_clicks"),
)
def refresh_snapshot(_interval, _clicks):
    return load_evolution_snapshot()


@callback(
    Output("evolution-summary", "children"),
    Output("evolution-progress-panel", "children"),
    Output("evolution-ranking-panel", "children"),
    Output("evolution-genes-panel", "children"),
    Output("evolution-archive-panel", "children"),
    Output("evolution-settings-panel", "children"),
    Input("evolution-snapshot", "data"),
)
def render_snapshot(snapshot):
    snapshot = snapshot or {}
    archive = snapshot.get("archive") or {}
    ranking = snapshot.get("ranking") or []
    environment = snapshot.get("environment") or {}
    seasons = snapshot.get("seasons") or []

    summary = dbc.Row([
        dbc.Col(_metric_card("Epoch", snapshot.get("epoch_id") or "No run"), md=3),
        dbc.Col(_metric_card("Generation", snapshot.get("generation", "N/A")), md=3),
        dbc.Col(_metric_card("Strategies", len(ranking)), md=3),
        dbc.Col(_metric_card("Runtime", "Running" if snapshot.get("running") else "Idle",
                             "success" if snapshot.get("running") else "secondary"), md=3),
    ], className="g-2 mb-3")

    progress = [
        html.H5("Epoch Progress"),
        dbc.Progress(
            value=snapshot.get("progress_pct", 0),
            label=f'{snapshot.get("progress_pct", 0):.1f}%',
            className="mb-3",
        ),
        html.P(f'Source: {snapshot.get("source_file") or "No generation file"}'),
        html.P(f'Last update: {snapshot.get("last_updated") or "N/A"}'),
    ]

    if ranking:
        ranking_table = dbc.Table([
            html.Thead(html.Tr([
                html.Th("Rank"), html.Th("ID"), html.Th("Symbol"), html.Th("Fitness"),
                html.Th("Generation"), html.Th("Windows"), html.Th("Data"),
            ])),
            html.Tbody([
                html.Tr([
                    html.Td(row["rank"]),
                    html.Td(row["chromosome_id"]),
                    html.Td(row["symbol"]),
                    html.Td(f'{row["fitness"]:.4f}' if row["fitness"] is not None else "N/A"),
                    html.Td(row["generation"]),
                    html.Td(len(row["per_window"])),
                    html.Td(row["data_provenance"].get("provider_id", "legacy/unknown")),
                ])
                for row in ranking
            ]),
        ], bordered=True, hover=True, responsive=True, size="sm")
    else:
        ranking_table = dbc.Alert(
            "No generation ranking exists yet. Run Evolution V2 to produce real results.",
            color="secondary",
        )

    selected = ranking[0] if ranking else {}
    genes = [
        dbc.Row([
            dbc.Col([html.H5("Environment"), _json_block(environment)], md=6),
            dbc.Col([html.H5("Ordered Seasons"), _json_block(seasons)], md=6),
        ]),
        html.Hr(),
        html.H5("Top Strategy Genes"),
        dbc.Row([
            dbc.Col([html.H6("Macro"), _json_block(selected.get("macro"))], md=4),
            dbc.Col([html.H6("Micro"), _json_block(selected.get("micro"))], md=4),
            dbc.Col([html.H6("Risk"), _json_block(selected.get("risk"))], md=4),
        ]),
        html.H5("Per-Window Results", className="mt-3"),
        _json_block(selected.get("per_window")),
    ]

    challengers = archive.get("challengers") or []
    archive_panel = [
        html.H5("Challenger"),
        _record_table(challengers, "Challenger"),
        dbc.Label("Select Challenger for manual Promote"),
        dcc.Dropdown(
            id="evolution-challenger-select",
            options=[
                {
                    "label": f'{row["symbol"]}: {row["chromosome_id"]} ({row["fitness"]:.4f})',
                    "value": json.dumps({
                        "symbol": row["symbol"],
                        "chromosome_id": row["chromosome_id"],
                    }),
                }
                for row in challengers
            ],
            placeholder="Select a current Challenger",
            className="text-dark mb-2",
        ),
        dbc.Button(
            "Promote selected Challenger",
            id="evolution-promote-open",
            color="warning",
            disabled=not challengers,
            className="mb-4",
        ),
        html.H5("Champion"),
        _record_table(archive.get("champions") or [], "Champion"),
        html.H5("Retired", className="mt-4"),
        _record_table(archive.get("retired") or [], "Retired"),
    ]

    config = snapshot.get("config") or {}
    settings = [
        dbc.Alert(
            "Saved settings apply to the next Evolution V2 run. Saving does not start, "
            "restart or deploy any service.",
            color="info",
        ),
        dbc.Row([
            dbc.Col([
                dbc.Label(key.replace("_", " ").title()),
                dbc.Input(
                    id={"type": "evolution-setting", "key": key},
                    value=config.get(key),
                    type="number",
                    min=bounds[0],
                    max=bounds[1],
                    step=1 if bounds[2] is int else 0.01,
                ),
            ], md=3, className="mb-3")
            for key, bounds in EDITABLE_CONFIG.items()
        ]),
        dbc.Button("Save next-run settings", id="evolution-settings-save", color="primary"),
    ]
    return summary, progress, ranking_table, genes, archive_panel, settings


@callback(
    Output("evolution-status", "children", allow_duplicate=True),
    Output("evolution-snapshot", "data", allow_duplicate=True),
    Input("evolution-settings-save", "n_clicks"),
    State({"type": "evolution-setting", "key": ALL}, "id"),
    State({"type": "evolution-setting", "key": ALL}, "value"),
    prevent_initial_call=True,
)
def save_settings(n_clicks, ids, values):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    try:
        updates = {item["key"]: value for item, value in zip(ids, values)}
        save_evolution_config(updates)
        return dbc.Alert("Next-run settings saved.", color="success"), load_evolution_snapshot()
    except ValueError as exc:
        return dbc.Alert(str(exc), color="danger"), dash.no_update


@callback(
    Output("evolution-promote-modal", "is_open"),
    Output("evolution-promote-target", "data"),
    Output("evolution-promote-description", "children"),
    Output("evolution-promote-confirmation", "value"),
    Input("evolution-promote-open", "n_clicks"),
    Input("evolution-promote-cancel", "n_clicks"),
    State("evolution-challenger-select", "value"),
    prevent_initial_call=True,
)
def toggle_promote_modal(open_clicks, cancel_clicks, selected):
    trigger = dash.ctx.triggered_id
    if trigger == "evolution-promote-cancel":
        return False, None, "", ""
    if not open_clicks or not selected:
        raise dash.exceptions.PreventUpdate
    target = json.loads(selected)
    description = (
        f'Promote {target["chromosome_id"]} for {target["symbol"]}. '
        "This action changes the runtime Champion."
    )
    return True, target, description, ""


@callback(
    Output("evolution-promote-modal", "is_open", allow_duplicate=True),
    Output("evolution-status", "children", allow_duplicate=True),
    Output("evolution-snapshot", "data", allow_duplicate=True),
    Input("evolution-promote-confirm", "n_clicks"),
    State("evolution-promote-target", "data"),
    State("evolution-promote-confirmation", "value"),
    prevent_initial_call=True,
)
def confirm_promote(n_clicks, target, confirmation):
    if not n_clicks or not target:
        raise dash.exceptions.PreventUpdate
    try:
        result = promote_challenger(
            target["symbol"], target["chromosome_id"], confirmation or ""
        )
        message = (
            f'Champion promoted: {result["chromosome_id"]} for {result["symbol"]}.'
        )
        return False, dbc.Alert(message, color="success"), load_evolution_snapshot()
    except ValueError as exc:
        return True, dbc.Alert(str(exc), color="danger"), dash.no_update
