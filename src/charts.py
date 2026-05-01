from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

_LAYOUT = dict(
    margin=dict(l=0, r=0, t=40, b=0),
    showlegend=False,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(size=12),
)


def weekly_distance_chart(weekly: pd.DataFrame) -> go.Figure | None:
    if weekly.empty:
        return None
    fig = px.bar(
        weekly,
        x="week_label",
        y="distance_km",
        title="Distance par semaine (km)",
        labels={"week_label": "", "distance_km": "km"},
        color_discrete_sequence=["#00A7E1"],
        text="distance_km",
    )
    fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    fig.update_layout(**_LAYOUT)
    return fig


def weekly_elevation_chart(weekly: pd.DataFrame) -> go.Figure | None:
    if weekly.empty:
        return None
    fig = px.bar(
        weekly,
        x="week_label",
        y="elevation_m",
        title="Dénivelé par semaine (m D+)",
        labels={"week_label": "", "elevation_m": "m"},
        color_discrete_sequence=["#FF6B35"],
        text="elevation_m",
    )
    fig.update_traces(texttemplate="%{text}m", textposition="outside")
    fig.update_layout(**_LAYOUT)
    return fig


def weekly_count_chart(weekly: pd.DataFrame) -> go.Figure | None:
    if weekly.empty:
        return None
    fig = px.bar(
        weekly,
        x="week_label",
        y="count",
        title="Sorties par semaine",
        labels={"week_label": "", "count": "sorties"},
        color_discrete_sequence=["#4CAF50"],
        text="count",
    )
    fig.update_traces(texttemplate="%{text}", textposition="outside")
    fig.update_layout(**_LAYOUT)
    return fig
