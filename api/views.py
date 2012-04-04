from django.core.files.base import ContentFile

from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseServerError

from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django_reputation.models import Reputation, UserReputationAction

from treemap.models import Plot, Species, TreePhoto
from api.models import APIKey, APILog
from django.contrib.gis.geos import Point

from profiles.models import UserProfile

from api.auth import login_required, create_401unauthorized

from functools import wraps

from omgeo import Geocoder
from omgeo.places import PlaceQuery

import json
import struct
import ctypes
import math

import simplejson 

class HttpBadRequestException(Exception):
    pass

class InvalidAPIKeyException(Exception):
    pass

def route(**kwargs):
    @csrf_exempt
    def routed(request):
        method = request.method
        req_method = kwargs[method]
        return req_method(request)
    return routed

def validate_and_log_api_req(request):
    # Prefer "apikey" in REQUEST, but take either that or the
    # header value
    key = request.META.get("HTTP_X_API_KEY", None)
    key = request.REQUEST.get("apikey", key)

    if key is None:
        raise InvalidAPIKeyException("key not found as 'apikey' param or 'X-API-Key' header")

    apikeys = APIKey.objects.filter(key=key)

    if len(apikeys) > 0:
        apikey = apikeys[0]
    else:
        raise InvalidAPIKeyException("key not found")

    if not apikey.enabled:
        raise InvalidAPIKeyException("key is not enabled")

    # Log the request
    reqstr = ",".join(["%s=%s" % (k,request.REQUEST[k]) for k in request.REQUEST])
    APILog(url=request.get_full_path(),
           remoteip=request.META["REMOTE_ADDR"],
           requestvars=reqstr,
           method=request.method,
           apikey=apikey).save()

    return apikey
    

def api_call_raw(content_type="image/jpeg"):
    """ Wrap an API call that writes raw binary data """
    def decorate(req_function):
        @wraps(req_function)
        def newreq(request, *args, **kwargs):
            try:
                validate_and_log_api_req(request)
                outp = req_function(request, *args, **kwargs)
                response = HttpResponse(outp)
                response['Content-length'] = str(len(response.content))
                response['Content-Type'] = content_type
            except HttpBadRequestException, bad_request:
                response = HttpResponseBadRequest(bad_request.message)
            
            return response
        return newreq
    return decorate
      
def api_call(content_type="application/json"):
    """ Wrap an API call that returns an object that
        is convertable from json
    """
    def decorate(req_function):
        @wraps(req_function)
        @csrf_exempt
        def newreq(request, *args, **kwargs):
            try:
                validate_and_log_api_req(request)
                outp = req_function(request, *args, **kwargs)
                if issubclass(outp.__class__, HttpResponse):
                    response = outp
                else:
                    response = HttpResponse()
                    response.write('%s' % simplejson.dumps(outp))
                    response['Content-length'] = str(len(response.content))
                    response['Content-Type'] = content_type

            except HttpBadRequestException, bad_request:
                response = HttpResponseBadRequest(bad_request.message)

            return response
            
        return newreq
    return decorate

@require_http_methods(["GET"])
@api_call()
@login_required
def verify_auth(request):
    user_dict = user_to_dict(request.user)
    user_dict["status"] = "success"
    return user_dict

@require_http_methods(["POST"])
@api_call()
def register(request):
    data = json.loads(request.raw_post_data)

    user = User(username=data["username"],
                first_name=data["firstname"],
                last_name=data["lastname"],
                email=data["email"])

    user.set_password(data["password"])
    user.save()

    profile = UserProfile(user=user,zip_code=data["zipcode"],active=True)
    profile.save()

    return { "status": "success", "id": user.pk }

@require_http_methods(["POST"])
@api_call()
@login_required
def add_profile_photo(request, user_id, title):
    uploaded_image = ContentFile(request.raw_post_data)
    uploaded_image.name = "%s.png" % title

    profile = UserProfile.objects.get(user__id=user_id)
    profile.photo.save("%s.png" % title, uploaded_image)

    profile.save()

    return { "status": "succes" }

@require_http_methods(["GET"])
@api_call()
@login_required
def recent_edits(request, user_id):
    if (int(user_id) != request.user.pk):
        return create_401unauthorized()

    result_offset = int(request.REQUEST.get("offset",0))
    num_results = min(int(request.REQUEST.get("length",15)),15)

    acts = UserReputationAction.objects.filter(user=request.user).order_by('-date_created')[result_offset:(result_offset+num_results)]

    acts = [dict([("id",a.pk),("name",a.action.name),("created",str(a.date_created)),("value",a.value)]) for a in acts]

    return acts

    

@require_http_methods(["PUT"])
@api_call()
@login_required
def update_password(request, user_id):
    data = json.loads(request.raw_post_data)

    pw = data["password"]

    user = User.objects.get(pk=user_id)

    user.set_password(pw)
    user.save()

    return { "status": "success" }

@require_http_methods(["GET"])
@api_call_raw("otm/trees")
def get_trees_in_tile(request):
    """ API Request

    Get pixel coordinates for trees in a 256x256 tile

    Verb: GET
    Params:
       bbox - xmin,ymin,xmax,ymax projected into web mercator

    Output:
       Raw Binary format as follows:

       0xA3A5EA         - 3 byte magic number
       0x00             - 1 byte pad
       Number of points - 4 byte uint
       Section Header   - 4 bytes
       Point pair - 2 bytes
       Point pair
       ...
       Point pair
       Section Header
       ...

       Section Header:
       Position  Field          Value  Type
       Byte N    Style Type     0-255  Enum
       Byte N+1  Number of pts         Unsigned Short
       Byte N+3  -----          0      Padding

       Point Pair:
       Position Field     Type
       Byte N   X offset  Byte (Unsigned)
       Byte N+1 Y offset  Byte (Unsigned)

    """
    
    # This method should execute as fast as possible to avoid the django/ORM overhead we are going
    # to execute raw SQL queries
    from django.db import connection, transaction

    cursor = connection.cursor()

    # Construct the bbox
    bbox = request.GET['bbox']
    (xmin,ymin,xmax,ymax) = map(float,bbox.split(","))
    bboxFilterStr = "ST_GeomFromText('POLYGON(({xmin} {ymin},{xmin} {ymax},{xmax} {ymax},{xmax} {ymin},{xmin} {ymin}))', 4326)"
    bboxFilter = bboxFilterStr.format(xmin=xmin,ymin=ymin,xmax=xmax,ymax=ymax)

    (xminM,yminM) = latlng2webm(xmin,ymin) 
    (xmaxM,ymaxM) = latlng2webm(xmax,ymax)
    pixelsPerMeterX = 255.0/(xmaxM - xminM)
    pixelsPerMeterY = 255.0/(ymaxM - yminM)

    # Use postgis to do the SRS math, save ourselves some time
    selectx = "ROUND((ST_X(t.geometry) - {xoffset})*{xfactor}) as x".format(xoffset=xminM,xfactor=pixelsPerMeterX)
    selecty = "ROUND((ST_Y(t.geometry) - {yoffset})*{yfactor}) as y".format(yoffset=yminM,yfactor=pixelsPerMeterY)
    query = "SELECT {xfield}, {yfield}".format(xfield=selectx,yfield=selecty)

    where = "where ST_Contains({bfilter},geometry)".format(bfilter=bboxFilter)
    subselect = "select ST_Transform(geometry, 900913) as geometry from treemap_plot {where}".format(where=where)
    fromq = "FROM ({subselect}) as t".format(subselect=subselect)

    order = "order by x,y"

    selectQuery = "{0} {1} {2}".format(query, fromq, order)

    cursor.execute(selectQuery)
    transaction.commit_unless_managed()

    # We have the sorted list, now we want to remove duplicates
    results = []
    rows = cursor.fetchall()
    n = len(rows)

    if n > 0:
        last = rows[0]
        lasti = i = 1
        while i < n:
            if rows[i] != last:
                rows[lasti] = last = rows[i]
                lasti += 1
            i += 1

        rows = rows[:lasti]

    # After removing duplicates, we can have at most 1 tree per square
    # (since we are using integer values that fall on pixels)
    assert len(rows) <= 65536 # 256*256

    # right now we only show "type 1" trees so the header is
    # 1 | n trees | 0 | size
    sizeoffileheader = 4+4
    sizeofheader = 1+2+1
    sizeofrecord = 2
    buffersize = sizeoffileheader + sizeofheader + sizeofrecord*len(rows)

    buf = ctypes.create_string_buffer(buffersize)
    bufoffset = 0

    # File Header: magic (3), pad(1), length (4)
    # Little endian, no align
    struct.pack_into("<II", buf, bufoffset, 0xA3A5EA00, len(rows))
    bufoffset += 8 #sizeoffileheader

    # Section header: type (1), num(4)
    # Little endian, no align
    # Default to type 1
    struct.pack_into("<BHx", buf, bufoffset, 1, len(rows))
    bufoffset += 4 #sizeofheader

    # Write pairs: x(1), y(1)
    # Litle endian, no align
    for (x,y) in rows:
        struct.pack_into("<BB", buf, bufoffset, x, y)
        bufoffset += 2 #sizeofrecord

    return buf.raw

def latlng2webm(lat,lng):
    num = lat * 0.017453292519943295
    x = 6378137.0 * num
    a = lng * 0.017453292519943295

    y = 3189068.5*math.log((1.0 + math.sin(a))/(1.0 - math.sin(a)))

    return (x,y)

@require_http_methods(["POST"])
@api_call()
def reset_password(request):
    resetform = PasswordResetForm({ "email" : request.REQUEST["email"]})

    if (resetform.is_valid()):
        opts = {
            'use_https': request.is_secure(),
            'token_generator': default_token_generator,
            'from_email': None,
            'email_template_name': 'reset_email_password.html',
            'request': request,
            }

        resetform.save(**opts)
        return { "status": "success" }
    else:
        raise HttpBadRequestException()

@require_http_methods(["GET"])
@api_call()
def version(request):
    """ API Request
    
    Get version information for OTM and the API. Generally, the API is unstable for
    any API version < 1 and minor changes (i.e. 1.4,1.5,1.6) represent no break in
    existing functionality

    Verb: GET
    Params: None
    Output:
      { 
        otm_version, string -> Open Tree Map Version (i.e. 1.0.2)
        api_version, string -> API version (i.e. 1.6) 
      }

    """
    return { "otm_version": settings.OTM_VERSION,
             "api_version": settings.API_VERSION }

@require_http_methods(["GET"])
@api_call_raw("image/jpeg")
def get_tree_image(request, plot_id, photo_id):
    """ API Request

    Verb: GET
    Params:
       
    Output:
      image/jpeg raw data
    """
    treephoto = TreePhoto.objects.get(pk=photo_id)

    if treephoto.tree.plot.pk == int(plot_id):
        return open(treephoto.photo.path, 'rb').read()
    else:
        raise HttpBadRequestException('invalid url (missing objects)')

@require_http_methods(["GET"])
@api_call()
def get_plot_list(request):
    """ API Request

    Get a list of all plots in the database. This is meant to be a lightweight
    listing service. To get more details about a plot use the ^plot/{id}$ service
    
    Verb: GET
    Params: 
      offset, integer, default = 0  -> offset to start results from
      size, integer, default = 100 -> Maximum 10000, number of results to get

    Output:
      [{
          width, integer, opt -> Width of tree bed
          length, integer, opt -> Length of bed
          type, string, opt -> Plot type
          geometry, Point -> Lat/lng pt
          readonly, boolean -> True if this is a readonly tree
          tree, {
             id, integer -> tree id
             species, integer, opt -> Species id
             dbh, real, opt -> Diameter of the tree
          }             
       }]

      """
    start = int(request.REQUEST.get("offset","0"))
    size = min(int(request.REQUEST.get("size", "100")), 10000)
    end = size + start

    plots = Plot.objects.filter(present=True)[start:end]

    return plots_to_list_of_dict(plots)

@require_http_methods(["GET"])
@api_call()
def plots_closest_to_point(request, lat=None, lon=None):
    point = Point(float(lon), float(lat), srid=4326)

    distance_string = request.GET.get('distance', settings.MAP_CLICK_RADIUS)
    try:
        distance = float(distance_string)
    except ValueError:
        raise HttpBadRequestException('The distance parameter must be a number')

    max_plots_string = request.GET.get('max_plots', '1')
    try:
        max_plots = int(max_plots_string)
    except ValueError:
        raise HttpBadRequestException('The max_plots parameter must be a number between 1 and 500')

    if max_plots > 500 or max_plots < 1:
        raise HttpBadRequestException('The max_plots parameter must be a number between 1 and 500')

    species = request.GET.get('species', None)

    plots, extent = Plot.locate.with_geometry(point, distance, max_plots, species)

    return plots_to_list_of_dict(plots)

def plots_to_list_of_dict(plots):
    return [plot_to_dict(plot) for plot in plots]

def plot_to_dict(plot):
    current_tree = plot.current_tree()
    if current_tree:
        tree_dict = { "id" : current_tree.pk }

        if current_tree.species:
            tree_dict["species"] = current_tree.species.pk
            tree_dict["species_name"] = current_tree.species.common_name
            tree_dict["sci_name"] = current_tree.get_scientific_name()

        if current_tree.dbh:
            tree_dict["dbh"] = current_tree.dbh

        if current_tree.height:
            tree_dict["height"] = current_tree.height

        if current_tree.canopy_height:
            tree_dict["canopy_height"] = current_tree.canopy_height

        images = current_tree.treephoto_set.all()

        if len(images) > 0:
            tree_dict["images"] = [{ "id": image.pk, "title": image.title } for image in images]
    else:
        tree_dict = None

    return {
        "id": plot.pk,
        "width": plot.width,
        "length": plot.length,
        "type": plot.type,
        "readonly": plot.readonly,
        "tree": tree_dict,
        "address": plot.geocoded_address,
        "geometry": {
            "srid": plot.geometry.srid,
            "lat": plot.geometry.y,
            "lng": plot.geometry.x
        }
    }

def user_to_dict(user):
    return {
        "id": user.pk,
        "firstname": user.first_name,
        "lastname": user.last_name,
        "email": user.email,
        "zipcode": UserProfile.objects.get(user__pk=user.pk).zip_code,
        "reputation": Reputation.objects.reputation_for_user(user).reputation
        }



@require_http_methods(["GET"])
@api_call()
def geocode_address(request, address):
    if address is None or len(address) == 0:
        raise HttpBadRequestException("No address specfified")

    query = PlaceQuery(address)
    if 'OMGEO_GEOCODER_SOURCES' in dir(settings) and settings.OMGEO_GEOCODER_SOURCES is not None:
        geocoder = Geocoder(settings.OMGEO_GEOCODER_SOURCES)
    else:
        geocoder = Geocoder()

    results = geocoder.geocode(query)
    if results != False:
        response = []
        for result in results:
            response.append({
                 "match_addr": result.match_addr,
                 "x": result.x,
                 "y": result.y,
                 "score": result.score,
                 "locator": result.locator,
                 "geoservice": result.geoservice,
                 "wkid": result.wkid,
            })
        return response
    else:
        # This is not a very helpful error message, but omgeo as of v1.2 does not
        # report failure details.
        return {"error": "The geocoder failed to generate a list of results."}