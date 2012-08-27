import os


GEOSERVER_URL = ''
GEOSERVER_GEO_LAYER = ''
GEOSERVER_GEO_STYLE = ''
TILECACHE_URL = 'sdtrees.beardedmaps.com/tilecache/tilecache.py/'
TILECACHE_LAYER = 'trees'
SITE_ROOT = ''
STATIC_URL = '/static/'
SITE = 'Cleveland'


SITE_LOCATION = 'Cleveland'
PENDING_ON = False
REGION_NAME = 'Cleveland'
#local_settings
GOOGLE_API_KEY = 'abcdf'

COMPLETE_ARRAY = ['species','condition','sidewalk_damage','powerline_conflict_potential','dbh','plot_width','plot_length','plot_type']
MAP_CLICK_RADIUS = .0015 # in decimal degrees


LOGIN_REDIRECT_URL = '/'        

# must end with trees/ because of odd tilecache deployment issue
# will be populated with layer name /trees/{layername} dynamically
# in javascript depending on the google base layer being used
TC_URL = 'http://tilecache.urbanforestmap.org/tiles/1.0.0/oakland/'

STATIC_DATA = os.path.join(os.path.dirname(__file__), 'static/')

ADMINS = (
    ('Admin1', 'jeff@websubstrate.com'),
)

ROOT_URL = 'http://ec2-50-112-45-243.us-west-2.compute.amazonaws.com'

TILED_SEARCH_RESPONSE = False

# separate instance of tilecache for dynamic selection tiles
CACHE_SEARCH_TILES = True
CACHE_SEARCH_METHOD = 'disk' #'disk'
#CACHE_SEARCH_DISK_PATH = os.path.join(os.path.dirname(__file__), 'local_tiles/')
CACHE_SEARCH_DISK_PATH =  '/tmp/local_tiles/'
MAPNIK_STYLESHEET = os.path.join(os.path.dirname(__file__), 'mapserver/stylesheet.xml')

# sorl thumbnail settings
THUMBNAIL_DEBUG = False
THUMBNAIL_SUBDIR = '_thumbs'
#THUMBNAIL_EXTENSION = 'png'
#THUMBNAIL_QUALITY = 95 # if not using png

MANAGERS = ADMINS

# django-registration
REGISTRATION_OPEN = True # defaults to True
ACCOUNT_ACTIVATION_DAYS = 5

DEFAULT_FROM_EMAIL= 'contact@urbanforestmap.org'
EMAIL_MANAGERS = False

EMAIL_USE_TLS = True
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_HOST_USER = 'treemap@umbrellaconsulting.com'
EMAIL_HOST_PASSWORD = 'treemap05'
EMAIL_PORT = 587

#http://sftrees.securemaps.com/ticket/236
CONTACT_EMAILS = ['joshlivni@gmail.com']#,'admins@urbanforestmap.org']

CACHE_BACKEND = 'file:///tmp/oakland_cache'

DATABASES = {
    'default': {
        'NAME': 'opentree',
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'USER': 'postgres',
        'HOST': '',
        'PASSWORD': 'p0$7$qlg1$',
        'PORT': '5432',
    }
}

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'America/New_York'

SITE_ID = 1

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = os.path.join(os.path.dirname(__file__), 'media/')

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
# Examples: "http://media.lawrence.com", "http://example.com/media/"
MEDIA_URL = ''

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/admin_media/'
ADMIN_MEDIA_ROOT = os.path.join(os.path.dirname(__file__), 'admin_media/')

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'insecurxe'

TEMPLATE_DIRS = (
    os.path.join(os.path.dirname(__file__), 'templates/Cleveland'),
    os.path.join(os.path.dirname(__file__), 'templates'),
)

ADD_FORM_TARGETS = [
    ('addsame', 'Add another tree using the same details'),
    ('add', 'Add another tree with new details'),
    ('edit','Continue editing this tree'),
    ('view', 'I\'m finished'),
]
ADD_FORM_TARGETS_DEFAULT = 'view'
