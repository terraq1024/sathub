"""Small OGC API Tiles facade for published imagery services.

The service remains the source of truth for availability and access policy. This
module only exposes standard discovery metadata and translates OGC tile row/col
coordinates to the existing XYZ proxy.
"""

from urllib.error import HTTPError
from urllib.request import urlopen

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ImageryService
from .services import service_zoom_range, titiler_tile_url


def _online_service(service_key):
    return ImageryService.objects.filter(
        service_key=service_key,
        status__in=[ImageryService.STATUS_ONLINE, ImageryService.STATUS_DEGRADED],
    ).first()


def _authorize(request, service):
    if service.visibility != ImageryService.VISIBILITY_PUBLIC and not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
    return None


def _base_url(request, service_key):
    return request.build_absolute_uri(f"/api/services/{service_key}/ogcapi").rstrip("/")


def _service_or_error(service_key):
    service = _online_service(service_key)
    if service is None:
        return None, Response({"detail": "Service is not online."}, status=status.HTTP_404_NOT_FOUND)
    return service, None


class OGCServiceLandingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, service_key):
        service, error = _service_or_error(service_key)
        if error:
            return error
        if (error := _authorize(request, service)):
            return error
        base = _base_url(request, service_key)
        return Response({
            "title": service.name,
            "description": "OGC API Tiles access to a published imagery service.",
            "links": [
                {"rel": "self", "href": base, "type": "application/json"},
                {"rel": "tilesets", "href": f"{base}/tiles", "type": "application/json"},
                {"rel": "tilejson", "href": request.build_absolute_uri(f"/api/services/{service_key}/tilejson"), "type": "application/json"},
            ],
        })


class OGCTilesetsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, service_key):
        service, error = _service_or_error(service_key)
        if error:
            return error
        if (error := _authorize(request, service)):
            return error
        base = _base_url(request, service_key)
        return Response({
            "tilesets": [{
                "title": service.name,
                "dataType": "map",
                "crs": "http://www.opengis.net/def/crs/EPSG/0/3857",
                "tileMatrixSetURI": "http://www.opengis.net/def/tilematrixset/OGC/1.0/WebMercatorQuad",
                "links": [
                    {"rel": "self", "href": f"{base}/tiles/WebMercatorQuad", "type": "application/json"},
                    {"rel": "tile", "href": f"{base}/tiles/WebMercatorQuad/{{tileMatrix}}/{{tileRow}}/{{tileCol}}", "type": "image/png", "templated": True},
                ],
            }],
            "links": [{"rel": "self", "href": f"{base}/tiles", "type": "application/json"}],
        })


class OGCTilesetMetadataView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, service_key, tile_matrix_set):
        service, error = _service_or_error(service_key)
        if error:
            return error
        if (error := _authorize(request, service)):
            return error
        if tile_matrix_set != "WebMercatorQuad":
            return Response({"detail": "Only WebMercatorQuad is supported."}, status=status.HTTP_404_NOT_FOUND)
        minzoom, maxzoom = service_zoom_range(service)
        base = _base_url(request, service_key)
        return Response({
            "title": service.name,
            "dataType": "map",
            "crs": "http://www.opengis.net/def/crs/EPSG/0/3857",
            "tileMatrixSet": "WebMercatorQuad",
            "tileMatrixSetURI": "http://www.opengis.net/def/tilematrixset/OGC/1.0/WebMercatorQuad",
            "minTileMatrix": str(minzoom),
            "maxTileMatrix": str(maxzoom),
            "bounds": _bounds(service),
            "links": [
                {"rel": "self", "href": f"{base}/tiles/WebMercatorQuad", "type": "application/json"},
                {"rel": "tile", "href": f"{base}/tiles/WebMercatorQuad/{{tileMatrix}}/{{tileRow}}/{{tileCol}}", "type": "image/png", "templated": True},
            ],
        })


class OGCTileView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, service_key, tile_matrix_set, tile_matrix, tile_row, tile_col):
        service, error = _service_or_error(service_key)
        if error:
            return error
        if (error := _authorize(request, service)):
            return error
        if tile_matrix_set != "WebMercatorQuad":
            return Response({"detail": "Only WebMercatorQuad is supported."}, status=status.HTTP_404_NOT_FOUND)
        try:
            with urlopen(titiler_tile_url(service, tile_matrix, tile_col, tile_row), timeout=30) as upstream:
                response = HttpResponse(upstream.read(), content_type=upstream.headers.get_content_type(), status=upstream.status)
                response["Cache-Control"] = "public, max-age=300" if service.visibility == ImageryService.VISIBILITY_PUBLIC else "private, max-age=60"
                return response
        except HTTPError as exc:
            if exc.code == 404:
                return HttpResponse(status=204)
            return Response({"detail": f"TiTiler returned HTTP {exc.code}."}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            return Response({"detail": f"TiTiler request failed: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)


def _bounds(service):
    bboxes = [
        asset.imagery.bbox for asset in service.service_assets.all()
        if asset.imagery.bbox and len(asset.imagery.bbox) == 4
    ]
    if not bboxes and service.source_dataset_id:
        bboxes = [
            member.imagery.bbox for member in service.source_dataset.members.all()
            if member.enabled and member.imagery.bbox and len(member.imagery.bbox) == 4
        ]
    if not bboxes:
        return [-180, -85, 180, 85]
    return [min(b[0] for b in bboxes), min(b[1] for b in bboxes), max(b[2] for b in bboxes), max(b[3] for b in bboxes)]
