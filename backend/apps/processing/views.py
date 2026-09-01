from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.audit_log.services import record_request_event

from .exceptions import ProcessingError
from .models import ProcessingJob
from .serializers import ProcessingJobSerializer, ProcessingJobWriteSerializer
from .services import remove_job_outputs, retry_job, validated_download_path


def _visible_jobs(user):
    queryset = ProcessingJob.objects.select_related("imagery", "created_by")
    if user.is_staff or user.is_superuser:
        return queryset
    return queryset.filter(created_by=user)


def _get_job(user, job_id):
    return get_object_or_404(_visible_jobs(user), pk=job_id)


class ProcessingJobListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        jobs = _visible_jobs(request.user)
        serializer = ProcessingJobSerializer(
            jobs,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = ProcessingJobWriteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        job = serializer.save(created_by=request.user)
        record_request_event(request, action="processing.created", object_type="processing_job", object_id=job.id, payload={"imagery_id": job.imagery_id, "output_format": job.output_format})
        return Response(
            ProcessingJobSerializer(job, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProcessingJobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job = _get_job(request.user, job_id)
        return Response(
            ProcessingJobSerializer(job, context={"request": request}).data
        )

    def patch(self, request, job_id):
        job = _get_job(request.user, job_id)
        if job.status != ProcessingJob.STATUS_PENDING:
            return Response(
                {"detail": "仅等待中的任务可以修改"},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = ProcessingJobWriteSerializer(
            job,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        return Response(
            ProcessingJobSerializer(job, context={"request": request}).data
        )

    def delete(self, request, job_id):
        job = _get_job(request.user, job_id)
        if job.status == ProcessingJob.STATUS_RUNNING:
            return Response(
                {"detail": "正在运行的任务不能删除"},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            remove_job_outputs(job)
        except ProcessingError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        job.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProcessingJobRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        job = _get_job(request.user, job_id)
        try:
            job = retry_job(job)
        except ProcessingError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        record_request_event(request, action="processing.retried", object_type="processing_job", object_id=job.id)
        return Response(
            ProcessingJobSerializer(job, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )


class ProcessingJobDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job = _get_job(request.user, job_id)
        if job.status != ProcessingJob.STATUS_SUCCEEDED:
            return Response(
                {"detail": "处理结果尚未生成"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            path = validated_download_path(job)
        except ProcessingError:
            return Response(
                {"detail": "处理结果不存在或路径无效"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename=path.name,
            content_type=job.output_media_type or "application/octet-stream",
        )
