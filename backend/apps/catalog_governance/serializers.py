from rest_framework import serializers

from .models import (
    AdministrativeUnit,
    Classification,
    DatasetClassification,
    DatasetTag,
    ImageryAdministrativeUnit,
    ImageryClassification,
    ImageryTag,
    Tag,
)


class AdministrativeUnitSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = AdministrativeUnit
        fields = ["id", "level", "code", "name", "parent_id", "geometry", "bbox", "source_version", "source_file", "is_valid"]
        read_only_fields = fields


class AdministrativeTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = AdministrativeUnit
        fields = ["id", "level", "code", "name", "bbox", "source_version", "children"]

    def get_children(self, obj):
        return AdministrativeTreeSerializer(obj.children.filter(is_valid=True), many=True, context=self.context).data


class ClassificationSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(read_only=True, allow_null=True)
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = Classification
        fields = ["id", "name", "code", "description", "parent_id", "enabled", "sort_order", "children_count", "created_by", "created_at", "updated_at"]
        read_only_fields = ["id", "parent_id", "children_count", "created_by", "created_at", "updated_at"]

    def get_children_count(self, obj):
        return obj.children.count()


class ClassificationWriteSerializer(serializers.ModelSerializer):
    parent_id = serializers.PrimaryKeyRelatedField(source="parent", queryset=Classification.objects.all(), required=False, allow_null=True, default=None)

    class Meta:
        model = Classification
        fields = ["name", "code", "description", "parent_id", "enabled", "sort_order"]

    def validate(self, attrs):
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if self.instance and parent:
            ancestor = parent
            while ancestor is not None:
                if ancestor.pk == self.instance.pk:
                    raise serializers.ValidationError("分类父级不能是自身或下级节点")
                ancestor = ancestor.parent
        if not attrs.get("name", getattr(self.instance, "name", "")).strip():
            raise serializers.ValidationError({"name": "分类名称不能为空"})
        return attrs


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "color", "description", "enabled", "created_by", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("标签名称不能为空")
        return value


class ImageryAdministrativeUnitSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="administrative_unit.name", read_only=True)
    code = serializers.CharField(source="administrative_unit.code", read_only=True)
    level = serializers.CharField(source="administrative_unit.level", read_only=True)

    class Meta:
        model = ImageryAdministrativeUnit
        fields = ["administrative_unit", "name", "code", "level", "relation", "coverage_ratio", "primary"]


class ImageryClassificationSerializer(serializers.ModelSerializer):
    classification_name = serializers.CharField(source="classification.name", read_only=True)

    class Meta:
        model = ImageryClassification
        fields = ["classification", "classification_name", "source", "confidence", "created_by", "created_at"]


class ImageryTagSerializer(serializers.ModelSerializer):
    tag_name = serializers.CharField(source="tag.name", read_only=True)

    class Meta:
        model = ImageryTag
        fields = ["tag", "tag_name", "created_by", "created_at"]


class AssociationWriteSerializer(serializers.Serializer):
    object_type = serializers.ChoiceField(choices=["imagery", "dataset"])
    object_ids = serializers.ListField(child=serializers.CharField(), allow_empty=False, max_length=200)
    classification_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=200)
    tag_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=200)
    replace = serializers.BooleanField(required=False, default=False)


class ImageryIdsQuerySerializer(serializers.Serializer):
    administrative_unit_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list)
    classification_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list)
    tag_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list)
    include_archived = serializers.BooleanField(required=False, default=False)
