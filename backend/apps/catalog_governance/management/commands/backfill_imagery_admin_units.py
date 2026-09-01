from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog_governance.models import AdministrativeUnit, ImageryAdministrativeUnit
from apps.catalog_governance.services import geometry_bbox, geometry_center, point_in_geometry


def _bbox_intersects(left, right):
    return left[0] <= right[2] and left[2] >= right[0] and left[1] <= right[3] and left[3] >= right[1]


def _overlap_ratio(left, right):
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    area = max(0.0, (left[2] - left[0]) * (left[3] - left[1]))
    return round(min(1.0, (width * height) / area), 6) if area else 0.0


class Command(BaseCommand):
    help = "根据影像 footprint 回填省、市、县行政区关联"

    def add_arguments(self, parser):
        parser.add_argument("--source-version", default="")
        parser.add_argument("--imagery-id", action="append", default=[])
        parser.add_argument("--keep-existing", action="store_true")
        parser.add_argument("--include-archived", action="store_true")

    def handle(self, *args, **options):
        from apps.imagery.models import ImageryRecord

        units = AdministrativeUnit.objects.filter(is_valid=True)
        if options["source_version"]:
            units = units.filter(source_version=options["source_version"])
        images = ImageryRecord.objects.all()
        if not options["include_archived"]:
            images = images.filter(is_archived=False)
        if options["imagery_id"]:
            images = images.filter(pk__in=options["imagery_id"])
        created = 0
        processed = 0
        with transaction.atomic():
            for imagery in images.iterator():
                if not imagery.geometry:
                    continue
                try:
                    image_bbox = imagery.bbox or geometry_bbox(imagery.geometry)
                    center = geometry_center(imagery.geometry)
                except (TypeError, ValueError, KeyError):
                    continue
                if not options["keep_existing"]:
                    ImageryAdministrativeUnit.objects.filter(imagery=imagery).delete()
                candidates = []
                for unit in units:
                    if not _bbox_intersects(image_bbox, unit.bbox):
                        continue
                    center_inside = point_in_geometry(center, unit.geometry)
                    candidates.append((unit, center_inside, _overlap_ratio(image_bbox, unit.bbox)))
                candidates.sort(key=lambda item: (not item[1], {"county": 0, "city": 1, "province": 2}.get(item[0].level, 9), -item[2]))
                primary_id = candidates[0][0].pk if candidates else None
                for unit, center_inside, coverage in candidates:
                    _, was_created = ImageryAdministrativeUnit.objects.update_or_create(
                        imagery=imagery, administrative_unit=unit,
                        defaults={
                            "relation": ImageryAdministrativeUnit.RELATION_CENTER_INSIDE if center_inside else ImageryAdministrativeUnit.RELATION_INTERSECTS,
                            "coverage_ratio": coverage,
                            "primary": unit.pk == primary_id,
                        },
                    )
                    created += int(was_created)
                processed += 1
        self.stdout.write(self.style.SUCCESS(f"已处理 {processed} 景影像，新增 {created} 条行政区关联"))
