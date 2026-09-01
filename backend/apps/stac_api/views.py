from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.imagery.models import ImageryRecord
from apps.imagery.stac import STAC_COLLECTION
from apps.access_control.authentication import BearerTokenAuthentication, has_scope

from .services import collection, item_for_record, next_search_link, search_records


class BaseView(APIView):
    authentication_classes = [SessionAuthentication, BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if isinstance(request.successful_authenticator, BearerTokenAuthentication) and not has_scope(request.auth, "catalog/read"):
            raise PermissionDenied("Missing catalog/read scope")


class RootView(BaseView):
    def get(self, request):
        base = request.build_absolute_uri("/api/stac/")
        return Response({"stac_version": "1.0.0", "id": "airmap-catalog", "title": "Airmap STAC", "description": "Airmap 影像 STAC API", "conformsTo": ["https://api.stacspec.org/v1.0.0/core", "https://api.stacspec.org/v1.0.0/ogcapi-features-1/1.0.0"], "links": [{"rel": "self", "href": base}, {"rel": "data", "href": base + "collections"}, {"rel": "search", "href": base + "search", "method": "GET"}, {"rel": "search", "href": base + "search", "method": "POST"}]})


class CollectionView(BaseView):
    def get(self, request):
        if request.path.rstrip("/").endswith(STAC_COLLECTION):
            return Response(collection(request))
        href = request.build_absolute_uri(f"/api/stac/collections/{STAC_COLLECTION}")
        return Response({"stac_version": "1.0.0", "collections": [dict(collection(request), links=[{"rel": "self", "href": href}])], "links": [{"rel": "self", "href": request.build_absolute_uri()}]})


class ItemView(BaseView):
    def get(self, request, item_id):
        record = ImageryRecord.objects.filter(is_archived=False).prefetch_related("assets", "project_tags").filter(stac_id=item_id).first()
        if record is None:
            record = ImageryRecord.objects.filter(is_archived=False).prefetch_related("assets", "project_tags").filter(scene_key=item_id).first()
        if record is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(item_for_record(request, record))


class SearchView(BaseView):
    def _search(self, request, payload):
        params = dict(request.query_params)
        params = {key: (value[-1] if isinstance(value, list) else value) for key, value in params.items()}
        params.update({key: value for key, value in payload.items() if value is not None})
        if "query" in params and isinstance(params["query"], str):
            import json
            try:
                params["query"] = json.loads(params["query"])
            except ValueError:
                return Response({"detail": "query must be valid JSON."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            records, limit, offset = search_records(request, params)
        except (TypeError, ValueError, OverflowError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        matched = len(records)
        features = [item_for_record(request, record) for record in records[offset:offset + limit]]
        links = [{"rel": "self", "href": request.build_absolute_uri()}]
        if offset + len(features) < matched:
            links.append({"rel": "next", "href": next_search_link(request, params, offset + limit), "method": "GET"})
        return Response({"type": "FeatureCollection", "stac_version": "1.0.0", "features": features, "numberMatched": matched, "numberReturned": len(features), "context": {"matched": matched, "returned": len(features), "limit": limit, "offset": offset}, "links": links})

    def get(self, request):
        return self._search(request, {})

    def post(self, request):
        if not isinstance(request.data, dict):
            return Response({"detail": "Request body must be an object."}, status=status.HTTP_400_BAD_REQUEST)
        return self._search(request, request.data)


class CollectionItemsView(SearchView):
    """STAC collection item listing with the same filters as /search."""
