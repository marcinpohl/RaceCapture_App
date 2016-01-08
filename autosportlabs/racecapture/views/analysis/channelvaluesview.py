import kivy
kivy.require('1.9.0')
from kivy.logger import Logger
from kivy.graphics import Color
from kivy.app import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty
from autosportlabs.racecapture.datastore import DataStore, Filter
from autosportlabs.racecapture.views.analysis.markerevent import SourceRef
from autosportlabs.racecapture.views.analysis.analysiswidget import ChannelAnalysisWidget
from autosportlabs.uix.gauge.bargraphgauge import BarGraphGauge

Builder.load_file('autosportlabs/racecapture/views/analysis/channelvaluesview.kv')
    
class ChannelValueView(BoxLayout):

    def __init__(self, **kwargs):
        super(ChannelValueView, self).__init__(**kwargs)
        self.session_view = self.ids.session
        self.lap_view = self.ids.lap
        self.channel_view = self.ids.channel
        self.value_view = self.ids.value

    @property
    def session(self):
        return self.session_view.text

    @session.setter
    def session(self, value):
        self.session_view.text = str(value)

    @property
    def lap(self):
        return self.lap_view.text

    @lap.setter
    def lap(self, value):
        self.lap_view.text = str(int(value))

    @property
    def channel(self):
        return self.channel_view.text

    @channel.setter
    def channel(self, value):
        self.channel_view.text = value

    @property
    def value(self):
        return self.value_view.value

    @value.setter
    def value(self, value):
        self.value_view.value = float(value)

    @property
    def color(self):
        return self.value_view.color

    @color.setter
    def color(self, value):
        self.value_view.color = [value[0], value[1], value[2], 0.5]

    @property
    def minval(self):
        return self.value_view.minval

    @minval.setter
    def minval(self, value):
        self.value_view.minval = value

    @property
    def maxval(self):
        return self.value_view.maxval

    @maxval.setter
    def maxval(self, value):
        self.value_view.maxval = value


class ChannelValuesView(ChannelAnalysisWidget):
    color_sequence = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(ChannelValuesView, self).__init__(**kwargs)
        self.channel_stats = {}
        self._channel_stat_widgets = {}

    def update_reference_mark(self, source, point):
        channel_data = self.channel_stats.get(str(source))
        for channel, channel_data in channel_data.iteritems():
            stats = channel_data.data
            key = channel + str(source)
            widget = self._channel_stat_widgets.get(key)
            values = stats.values
            try:
                value = str(values[point])
            except IndexError:
                value = values[len(values) - 1]
            widget.value = value 
                

    def _refresh_channels(self):
        channels_grid = self.ids.channel_values
        self._channel_stat_widgets.clear()
        for source_key, channels in self.channel_stats.iteritems():
            for channel, channel_data in channels.iteritems():
                key = channel + source_key
                view = ChannelValueView()
                view.channel = channel
                view.color = self.color_sequence.get_color(key)
                view.lap = channel_data.source.lap
                session_id = channel_data.source.session
                session = self.datastore.get_session_by_id(session_id, self.sessions)
                view.session = session.name
                view.minval = channel_data.min
                view.maxval = channel_data.max
                self._channel_stat_widgets[key] = view
                
        channels_grid.clear_widgets()
        for key in iter(sorted(self._channel_stat_widgets.iterkeys())):
            channels_grid.add_widget(self._channel_stat_widgets[key])

    def add_channel(self, channel_data):
        source_key = str(channel_data.source)
        channels = self.channel_stats.get(source_key)
        if not channels:
            channels = {}
            self.channel_stats[source_key] = channels
        channels[channel_data.channel] = channel_data
        self._refresh_channels()
    
    def refresh_view(self):
        self._refresh_channels()
        
    def remove_channel(self, channel, lap_ref):
        source_key = str(lap_ref)
        channels = self.channel_stats.get(source_key)
        channels.pop(channel, None)

    def query_new_channel(self, channel, lap_ref):
        channel_data = self.datastore.get_channel_data(lap_ref, [channel])
        self.add_channel(channel_data[channel])

                
                