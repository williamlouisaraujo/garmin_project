import plotly.express as px


def weekly_distance_chart(df):
    if df.empty:
        return None
    return px.bar(df, x="week", y="distance_km", title="Distance hebdomadaire")