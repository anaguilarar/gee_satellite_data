from scripts import gee_functions
import plotly.graph_objects as go
from scripts import gee_functions
from scripts import gis_functions
import folium
import ee

def plot_vi_time_series(gee_satellite_class, vi_name):

    ndvi_data = gee_functions.get_band_timeseries_summary(gee_satellite_class, vi_name)

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

def plot_multiple_eeimage(imagestoplot, visparameters=None, geometry=None, images_labes = None,zoom=9.5):
    ##
    ## get the map center coordinates from the geometry
    centergeometry = gis_functions.geometry_center(geometry)
    Map = folium.Map(location=[centergeometry[1],
                               centergeometry[0]], zoom_start=zoom)
    for i in range(len(imagestoplot)):
        if visparameters is not None:
            if images_labes is not None:
                Map.addLayer(ee.Image(imagestoplot[i]), visparameters[i], images_labes[i])
            else:
                Map.addLayer(ee.Image(imagestoplot[i]), visparameters[i], 'gee_image_'+str(i+1))
        else:
            if images_labes is not None:
                Map.addLayer(ee.Image(imagestoplot[i]), {}, images_labes[i])
            else:
                Map.addLayer(ee.Image(imagestoplot[i]), {}, 'gee_image_' + str(i + 1))

    ## add geometry
    if geometry is not None:
        eegeom = gis_functions.polygon_fromgeometry(geometry)
        eegeom = gee_functions.geometry_as_ee(eegeom)
        Map.addLayer(ee.Image().paint(eegeom, 1, 3), {}, 'region of interest:')

    Map.setControlVisibility(layerControl=True, fullscreenControl=True, latLngPopup=True)
    return (Map)