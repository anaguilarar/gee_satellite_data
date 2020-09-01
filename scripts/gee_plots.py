from scripts import gee_functions
import plotly.graph_objects as go


def plot_vi_time_series(gee_satellite_class, vi_name):
    ee_point = gee_functions.coords_togeepoint(gee_satellite_class._querypoint, 100)

    meanDictionary = gee_satellite_class.image_collection.map(lambda img:
                                       gee_functions.reduce_tosingle_columns(img.select([vi_name]),
                                                                             ee_point)).flatten()

    ndvi_data = gee_functions.fromeedict_totimeseriesfeatures(meanDictionary.getInfo(), 'mean')
    ndvi_data.columns = ['date', vi_name]

    fig = go.Figure(data=go.Scatter(x=ndvi_data.date, y=ndvi_data[vi_name]))

    fig.update_layout(
        xaxis=dict(
            linecolor='rgb(204, 204, 204)',
            linewidth=2,
            ticks='outside',
            tickfont=dict(
                family='Arial',
                size=12,
                color='rgb(82, 82, 82)',
            ),
        ),
        yaxis=dict(
            linecolor='rgb(204, 204, 204)',
            linewidth=2,
            ticks='outside',
            tickfont=dict(
                family='Arial',
                size=12,
                color='rgb(82, 82, 82)',
            ),
        ),
        autosize=True,
        margin=dict(
            autoexpand=False,
            l=100,
            r=20,
            t=110,
        ),
        showlegend=True,
        plot_bgcolor='white'
    )

    fig.update_layout(
        title="Vegetation Index time series",
        xaxis_title="Date",
        yaxis_title=vi_name.upper(),

        font=dict(
            family='Arial',
            size=18,
            color='rgb(10, 10, 10)',
        )
    )

    fig.show()
