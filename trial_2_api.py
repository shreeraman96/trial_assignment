#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import requests
from datetime import datetime
import json

from bokeh.models import GeoJSONDataSource,LinearColorMapper,NumeralTickFormatter
from bokeh.models import HoverTool,Select,ColorBar
from bokeh.palettes import brewer
from bokeh.io.doc import curdoc
from bokeh.layouts import widgetbox, row, column
from bokeh.plotting import figure


# In[2]:


tz_lookup = pd.read_csv('tz_lookup.csv')
tz_lookup = tz_lookup[tz_lookup['Borough'] == 'Manhattan']
tz_man = tz_lookup.LocationID.to_list()
tz_pu = tz_man[:1]


# In[3]:


template_str = "https://data.cityofnewyork.us/resource/2upf-qytp.json?$query=SELECT tpep_pickup_datetime as pu_time,tpep_dropoff_datetime as do_time, pulocationid as OTAZ,dolocationid as DTAZ, fare_amount as taxi_costs WHERE pulocationid in({}) AND dolocationid in ({}) limit 50000"
url = template_str.format(','.join(map(str,tz_pu)),','.join(map(str,tz_man)))


# In[4]:


print(url)


# In[5]:


resp = requests.get(url).json()


# In[6]:


taxi_info_2019 = pd.DataFrame(resp)
taxi_info_2019.head()


# In[7]:


def calc_taxi_time(row):
    interval = datetime.strptime(row['do_time'], "%Y-%m-%dT%H:%M:%S.000") - datetime.strptime(row['pu_time'], "%Y-%m-%dT%H:%M:%S.000")
    return int(interval.total_seconds())


# In[8]:


taxi_info_2019['taxi_costs'] = taxi_info_2019.apply(lambda row: float(row['taxi_costs']),axis=1)
taxi_info_2019['taxi_time_sec'] = taxi_info_2019.apply(lambda row: calc_taxi_time(row),axis=1)
taxi_info_2019.head()


# In[9]:


agg_trips = taxi_info_2019.groupby(["OTAZ","DTAZ"]).agg({"taxi_costs":'mean',"taxi_time_sec":'mean'}).reset_index(level='DTAZ')
agg_trips.head()


# In[10]:


tz_info = {}
for row in agg_trips.iterrows():
    otz = row[0]
    row = row[1]
    dest_info = tz_info.get(otz,{})
    dest_info[row['DTAZ']] = [row['taxi_costs'],row['taxi_time_sec']]
    tz_info[otz] = dest_info


# In[11]:


def calc_uncertainity(row,cost=True):
    if cost:
        return row['taxi_costs'] - tz_info[row['OTAZ']][row['DTAZ']][0]
    else:
        return row['taxi_time_sec'] - tz_info[row['OTAZ']][row['DTAZ']][1]


# In[12]:


taxi_info_2019['cost_uncertainity'] = taxi_info_2019.apply(lambda row: calc_uncertainity(row,True),axis=1)
taxi_info_2019['time_uncertainity'] = taxi_info_2019.apply(lambda row: calc_uncertainity(row,False),axis=1)
agg_trips = taxi_info_2019.groupby(["OTAZ","DTAZ"]).agg({"taxi_costs":'mean',"taxi_time_sec":'mean','cost_uncertainity':'mean','time_uncertainity':'mean'}).reset_index()
agg_trips.head()


# In[13]:


taz = gpd.read_file('taxi_zones.shp')
taz = taz[taz['LocationID'].isin(tz_man)]


# In[14]:


zone_shp = {}
for row in taz.iterrows():
    row = row[1]
    zone_shp[row['LocationID']] = row['geometry'] 


# In[15]:


agg_trips['geometry'] = agg_trips.apply(lambda row: zone_shp[int(row['DTAZ'])],axis =1 )
agg_trips['OTAZ'] = agg_trips.apply(lambda row: int(row['OTAZ']),axis = 1 )
agg_trips['DTAZ'] = agg_trips.apply(lambda row: int(row['DTAZ']),axis = 1 )
agg_trips.head()


# In[16]:


agg_geoDf = gpd.GeoDataFrame(agg_trips)
agg_geoDf.set_geometry('geometry',inplace=True)
#agg_geoDf.crs = {'init': 'epsg:4326'}
agg_geoDf.head()


# In[17]:


def geoJsonDataSource(df,tz):
    df = df[df['OTAZ'] == tz]
    geoJson = json.loads(df.to_json())
    return json.dumps(geoJson)


# In[18]:


attr_map = {
    'cost': [0.0,100.0,'0.0','Avg cost and Uncertainity to each destination from {}'],
    'time': [0.0,1000.0,'0.0','Avg taxi time and Uncertainity in Seconds to each destination from {}']
}


# In[19]:


def make_plot(field_name,tz,geosource,attr_map):
    attributes = attr_map[field_name]
    
    min_range = attributes[0]
    max_range = attributes[1]
    field_format = attributes[2]
    
    palette = brewer['Blues'][8]
    palette = palette[::-1]
    
    color_mapper = LinearColorMapper(palette = palette,low = min_range, high = max_range)
    
    format_tick = NumeralTickFormatter(format = field_format)
    color_bar = ColorBar(color_mapper = color_mapper,label_standoff = 18,formatter=format_tick,
                        border_line_color = None,location = (0,0))
    
    title = attributes[3].format(tz)
    
    plot = figure(title = title,
                 plot_height = 650,
                 plot_width = 850,
                 toolbar_location = None)
    plot.xgrid.grid_line_color = None
    plot.ygrid.grid_line_color = None
    plot.axis.visible = False
    color_fill = 'taxi_costs' if field_name == 'cost' else 'time_uncertainity'
    plot.patches('xs','ys',
                source = geosource,
                fill_color = {'field': color_fill,'transform':color_mapper},
                line_color = 'black',
                line_width = 0.25,
                fill_alpha = 1)
    plot.add_layout(color_bar,'right')
    
    hover = HoverTool(tooltips = [
    ('Dest Taxi Zone','@DTAZ'),
    ('Avg Taxi Cost','@taxi_costs'),
    ('Avg Time (secs)','@taxi_time_sec'),
    ('cost uncertainity','@cost_uncertainity'),
    ('time uncertainity','@time_uncertainity')
    ])
    plot.add_tools(hover)
    return plot
    


# In[20]:

print("debug - started plotting")

geosource = GeoJSONDataSource(geojson=geoJsonDataSource(agg_geoDf,tz_pu[0]))

palette = brewer['Blues'][8]
palette = palette[::-1]

hover = HoverTool(tooltips = [
    ('Dest Taxi Zone','@DTAZ'),
    ('Avg Taxi Cost','@taxi_costs'),
    ('Avg Time (secs)','@taxi_time_sec'),
    ('cost uncertainity','@cost_uncertainity'),
    ('time uncertainity','@time_uncertainity')
])

try:
    plot = make_plot('cost',str(tz_pu[0]),geosource,attr_map)
except:
    print("exception in plot")

select_tz = Select(title = 'Select Taxi Zone: ', value = '4',options=list(map(str,tz_pu)))

select_asp = Select(title = 'Select Measure',value = 'cost',options = ['cost','time'])

layout = column(plot,widgetbox(select_tz),widgetbox(select_asp))
curdoc().add_root(layout)

print("plot complete")

# In[21]:


#agg_trips


# In[ ]:




