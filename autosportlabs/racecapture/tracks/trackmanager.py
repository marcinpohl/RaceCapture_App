import json
import time
import copy
import errno
import string
import logging
from threading import Thread, Lock
from urlparse import urljoin, urlparse
import urllib2
import os
import traceback
from autosportlabs.racecapture.geo.geopoint import GeoPoint, Region
from kivy.logger import Logger
from utils import time_to_epoch

class TrackMap:

    def __init__(self, **kwargs):
        self.map_points = []
        self.sector_points = []
        self.name = ''
        self.created = None
        self.updated = None
        self.length = 0
        self.track_id = None
        self.start_finish_point = None
        self.finish_point = None
        self.country_code = None
        self.configuration = None

    @property
    def centerpoint(self):
        if len(self.map_points) > 0:
            return self.map_points[0]
        return None

    @property
    def short_id(self):
        short_id = 0
        if self.created is not None:
            try:
                short_id = time_to_epoch(self.created)
            except:
                pass
        return short_id

    def from_dict(self, track_dict):

        self.start_finish_point = GeoPoint.fromPointJson(track_dict.get('start_finish'))
        self.finish_point = GeoPoint.fromPointJson(track_dict.get('finish'))
        self.country_code = track_dict.get('country_code', self.country_code)
        self.created = track_dict.get('created', self.created)
        self.updated = track_dict.get('updated', self.updated)
        self.name = track_dict.get('name', self.name)
        self.configuration = track_dict.get('configuration', self.configuration)
        self.length = track_dict.get('length', self.length)
        self.track_id = track_dict.get('id')

        map_points_array = track_dict.get('track_map_array')

        if map_points_array:
            for point in map_points_array:
                self.map_points.append(GeoPoint.fromPoint(point[0], point[1]))

        sector_array = track_dict.get('sector_points')

        if sector_array:
            for point in sector_array:
                self.sector_points.append(GeoPoint.fromPoint(point[0], point[1]))

        if not self.short_id > 0:
            raise Warning("Could not parse trackMap: short_id is invalid")
    
    def to_dict(self):
        track_dict = {'sector_points': [], 'track_map_array': []}

        if self.start_finish_point:
            track_dict['start_finish'] = self.start_finish_point.toJson()

        if self.finish_point:
            track_dict['finish'] = self.finish_point.toJson()

        track_dict['country_code'] = self.country_code
        track_dict['created'] = self.created
        track_dict['updated'] = self.updated
        track_dict['name'] = self.name
        track_dict['configuration'] = self.configuration
        track_dict['length'] = self.length
        track_dict['id'] = self.track_id

        for point in self.map_points:
            track_dict['track_map_array'].append([point.latitude, point.longitude])

        for point in self.sector_points:
            track_dict['sector_points'].append([point.latitude, point.longitude])

        return track_dict

class TrackManager:
    RCP_VENUE_URL = 'https://race-capture.com/api/v1/venues'
    READ_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self, **kwargs):
        self.on_progress = lambda self, value: value
        self.tracks_user_dir = '.'
        self.track_user_subdir = '/venues'
        self.set_tracks_user_dir(kwargs.get('user_dir', self.tracks_user_dir) + self.track_user_subdir)
        self.update_lock = Lock()
        self.regions = []
        self.tracks = {}
        self.track_ids_in_region = []
        self.base_dir = kwargs.get('base_dir')
        
    def set_tracks_user_dir(self, path):
        try:
            os.makedirs(path)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
        self.tracks_user_dir = path
        
    def init(self, progress_cb, success_cb, fail_cb):
        self.load_regions()
        self.load_tracks(progress_cb, success_cb, fail_cb)
        
    def load_regions(self):
        del(self.regions[:])
        try:
            regions_json = json.load(open(os.path.join(self.base_dir, 'resource', 'settings', 'geo_regions.json')))
            regions_node = regions_json.get('regions')
            if regions_node:
                for region_node in regions_node:
                    region = Region()
                    region.fromJson(region_node)
                    self.regions.append(region)
        except Exception as detail:
            Logger.warning('TrackManager: Error loading regions data ' + traceback.format_exc())

    @property
    def track_ids(self):
        return self.tracks.keys()
    
    def get_track_ids_in_region(self):
        return self.track_ids_in_region
        
    def find_track_by_short_id(self, id):
        for track in self.tracks.itervalues():
            if id == track.short_id:
                return track
        return None
        
    def find_nearby_track(self, point, searchRadius):
        for track_id in self.tracks.keys():
            track = self.tracks[track_id]
            track_center = track.centerpoint
            if track_center and track_center.withinCircle(point, searchRadius):
                return track
        return None
        
    def filter_tracks_by_name(self, name, track_ids=None):
        if track_ids is None:
            track_ids = self.tracks.keys()
        filtered_track_ids = []

        for track_id in track_ids:
            track_name = self.tracks[track_id].name
            if string.lower(name.strip()) in string.lower(track_name.strip()):
                filtered_track_ids.append(track_id)

        return filtered_track_ids
                
    def filter_tracks_by_region(self, region_name):
        track_ids_in_region = self.track_ids_in_region
        del track_ids_in_region[:]
        
        if region_name is None:
            track_ids_in_region.extend(self.track_ids)
        else:
            for region in self.regions:
                if region.name == region_name:
                    if len(region.points) > 0:
                        for track_id in self.track_ids:
                            track = self.tracks[track_id]
                            if region.withinRegion(track.centerpoint):
                                track_ids_in_region.append(track_id)
                    else:
                        track_ids_in_region.extend(self.track_ids)
                    break
        return track_ids_in_region

    def get_track_by_id(self, track_id):
        return self.tracks.get(track_id)
    
    def load_json(self, uri):
        retries = 0
        while retries < self.READ_RETRIES:
            try:
                opener = urllib2.build_opener()
                opener.addheaders = [('Accept', 'application/json')]
                response = opener.open(uri).read()
                j = json.loads(response)
                return j
            except Exception as detail:
                Logger.warning('TrackManager: Failed to read: from {} : {}'.format(uri, traceback.format_exc()))
                if retries < self.READ_RETRIES:
                    Logger.warning('TrackManager: retrying in ' + str(self.RETRY_DELAY) + ' seconds...')
                    retries += 1
                    time.sleep(self.RETRY_DELAY)
        raise Exception('Error reading json doc from: ' + uri)

    def download_all_tracks(self):
        tracks = {}
        venues = self.fetch_venue_list(True)

        for venue in venues:
                track = TrackMap()
                track.from_dict(venue)
                tracks[track.track_id] = track

        return tracks

    def fetch_venue_list(self, full_response=False):
        total_venues = None
        next_uri = self.RCP_VENUE_URL + "?start=0&per_page=100"

        if full_response:
            next_uri += '&expand=1'

        venues_list = []

        while next_uri:
            response = self.load_json(next_uri)
            try:
                if total_venues is None:
                    total_venues = int(response.get('total', None))
                    if total_venues is None:
                        raise MissingKeyException('Venue list JSON: could not get total venue count')

                venues = response.get('venues', None)

                if venues is None:
                    raise MissingKeyException('Venue list JSON: could not get venue list')

                venues_list += venues
                next_uri = response.get('nextURI')

            except MissingKeyException as detail:
                Logger.error('TrackManager: Malformed venue JSON from url ' + nextUri + '; json =  ' + str(response) +
                             ' ' + str(detail))
                
        Logger.info('TrackManager: fetched list of ' + str(len(venues_list)) + ' tracks')

        if not total_venues == len(venues_list):
            Logger.warning('TrackManager: track list count does not reflect downloaded track list size ' + str(total_venues) + '/' + str(len(venues_list)))

        return venues_list

    def download_track(self, track_id):
        track_url = self.RCP_VENUE_URL + '/' + track_id
        response = self.load_json(track_url)
        track_map = TrackMap()
        try:
            track_json = response.get('venue')
            track_map.from_dict(track_json)
            return copy.deepcopy(track_map)
        except Warning:
            return None
        
    def save_track(self, track):
        path = self.tracks_user_dir + '/' + track.track_id + '.json'
        track_json_string = json.dumps(track.to_dict(), sort_keys=True, indent=2, separators=(',', ': '))
        with open(path, 'w') as text_file:
            text_file.write(track_json_string)
    
    def load_current_tracks_worker(self, success_cb, fail_cb, progress_cb=None):
        try:
            self.update_lock.acquire()
            self.load_tracks(progress_cb)
            success_cb()
        except Exception as detail:
            logging.exception('')
            fail_cb(detail)
        finally:
            self.update_lock.release()
        
    def load_tracks(self, progress_cb=None, success_cb=None, fail_cb=None):
        if success_cb and fail_cb:
            t = Thread(target=self.load_current_tracks_worker, args=(success_cb, fail_cb, progress_cb))
            t.daemon = True
            t.start()
        else:
            track_file_names = os.listdir(self.tracks_user_dir)
            self.tracks.clear()
            track_count = len(track_file_names)
            count = 0

            for trackPath in track_file_names:
                try:
                    json_data = open(self.tracks_user_dir + '/' + trackPath)
                    track_dict = json.load(json_data)

                    if track_dict is not None:
                        track = TrackMap()
                        track.from_dict(track_dict)

                        self.tracks[track.track_id] = track
                        count += 1
                        if progress_cb:
                            progress_cb(count, track_count, track.name)
                except Exception as detail:
                    Logger.warning('TrackManager: failed to read track file ' + trackPath + ';\n' + str(detail))

            del self.track_ids_in_region[:]
            self.track_ids_in_region.extend(self.track_ids)
                        
    def update_all_tracks_worker(self, success_cb, fail_cb, progress_cb=None):
        try:
            self.update_lock.acquire()
            self.refresh(progress_cb)
            success_cb()
        except Exception as detail:
            logging.exception('')
            fail_cb(detail)
        finally:
            self.update_lock.release()
            
    def refresh(self, progress_cb=None, success_cb=None, fail_cb=None):
        if success_cb and fail_cb:
            t = Thread(target=self.update_all_tracks_worker, args=(success_cb, fail_cb, progress_cb))
            t.daemon = True
            t.start()
        else:
            if len(self.tracks) == 0:
                Logger.info("TrackManager: No tracks found locally, fetching all tracks")
                track_list = self.download_all_tracks()
                count = 0
                total = len(track_list)

                for track_id, track in track_list.iteritems():
                    count += 1
                    if progress_cb:
                        progress_cb(count, total, track.name)
                    self.save_track(track)
                    self.tracks[track_id] = track
            else:
                Logger.info("TrackManager: refreshing tracks")
                venues = self.fetch_venue_list()

                track_count = len(venues)
                count = 0

                for venue in venues:
                    update = False
                    count += 1
                    venue_id = venue.get('id')

                    if self.tracks.get(venue_id) is None:
                        Logger.info('TrackManager: new track detected ' + venue.name)
                        update = True
                    elif not self.tracks[venue_id].updated == venue['updated']:
                        Logger.info('TrackManager: existing map changed ' + venue_id)
                        update = True

                    if update:
                        updated_track = self.download_track(venue_id)
                        if updated_track is not None:
                            self.save_track(updated_track, venue_id)
                            self.tracks[venue_id] = updated_track
                            if progress_cb:
                                progress_cb(count, track_count, updated_track.name)
                    else:
                        progress_cb(count, track_count)

class MissingKeyException(Exception):
    pass
