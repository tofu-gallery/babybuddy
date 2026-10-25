# -*- coding: utf-8 -*-
# Tofu (2026-10-25): this file is Tofu's addition; it is not part of upstream Baby Buddy.
import io
import os
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from core import models


def uploads(allowed):
    return override_settings(
        BABY_BUDDY={**settings.BABY_BUDDY, "ALLOW_UPLOADS": allowed}
    )


def image_upload(name="photo.png"):
    file = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(file, format="PNG")
    return SimpleUploadedFile(name, file.getvalue(), content_type="image/png")


class UploadsTestCaseBase(APITestCase):
    fixtures = ["tests.json"]

    def setUp(self):
        self.client.login(username="admin", password="admin")
        media_root = tempfile.TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        self.media_root = media_root.name
        media = override_settings(MEDIA_ROOT=self.media_root)
        media.enable()
        self.addCleanup(media.disable)

    def files_written(self):
        return [name for _, _, names in os.walk(self.media_root) for name in names]


class APIUploadsTestCase(UploadsTestCaseBase):
    """
    While uploads are off, the API keeps no picture of a child and no image of
    a note (api.serializers.UploadFieldsSerializer); while they are on, it
    keeps both, as upstream's API does.
    """

    def post_child(self):
        return self.client.post(
            reverse("api:child-list"),
            {
                "first_name": "Photo",
                "last_name": "Child",
                "birth_date": "2017-11-12",
                "picture": image_upload(),
            },
            format="multipart",
        )

    def post_note(self):
        return self.client.post(
            reverse("api:note-list"),
            {"child": 1, "note": "A note with an image.", "image": image_upload()},
            format="multipart",
        )

    @uploads(False)
    def test_child_picture_not_kept_without_uploads(self):
        response = self.post_child()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["picture"])
        self.assertFalse(models.Child.objects.get(pk=response.data["id"]).picture)
        self.assertEqual(self.files_written(), [])

    @uploads(False)
    def test_child_picture_not_changed_without_uploads(self):
        response = self.client.patch(
            reverse("api:child-detail", args=["fake-child"]),
            {"picture": image_upload()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["picture"])
        self.assertFalse(models.Child.objects.get(slug="fake-child").picture)
        self.assertEqual(self.files_written(), [])

    @uploads(False)
    def test_note_image_not_kept_without_uploads(self):
        response = self.post_note()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["image"])
        self.assertFalse(models.Note.objects.get(pk=response.data["id"]).image)
        self.assertEqual(self.files_written(), [])

    @uploads(False)
    def test_options_show_read_only_without_uploads(self):
        for endpoint, field_name in (
            (reverse("api:child-list"), "picture"),
            (reverse("api:note-list"), "image"),
        ):
            response = self.client.options(endpoint)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            field = response.data["actions"]["POST"][field_name]
            self.assertTrue(field["read_only"])

    @uploads(True)
    def test_child_picture_kept_with_uploads(self):
        response = self.post_child()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        picture = models.Child.objects.get(pk=response.data["id"]).picture
        self.assertTrue(picture.name.startswith("child/picture/"))
        self.assertEqual(len(self.files_written()), 1)

    @uploads(True)
    def test_note_image_kept_with_uploads(self):
        response = self.post_note()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        image = models.Note.objects.get(pk=response.data["id"]).image
        self.assertTrue(image.name.startswith("notes/images/"))
        self.assertEqual(len(self.files_written()), 1)


class AdminUploadsTestCase(UploadsTestCaseBase):
    """
    While uploads are off, the admin's note form has no image field
    (core.admin.NoteAdmin), as its child form has no picture field.
    """

    def post_note(self):
        return self.client.post(
            reverse("admin:core_note_add"),
            {
                "child": 1,
                "note": "An admin note with an image.",
                "time_0": "2026-10-25",
                "time_1": "08:30:00",
                "image": image_upload(),
                "_save": "Save",
            },
        )

    @uploads(False)
    def test_note_form_has_no_image_without_uploads(self):
        response = self.client.get(reverse("admin:core_note_add"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("image", response.context["adminform"].form.fields)

    @uploads(False)
    def test_note_image_not_kept_without_uploads(self):
        response = self.post_note()
        self.assertRedirects(response, reverse("admin:core_note_changelist"))
        note = models.Note.objects.get(note="An admin note with an image.")
        self.assertFalse(note.image)
        self.assertEqual(self.files_written(), [])

    @uploads(True)
    def test_note_image_kept_with_uploads(self):
        response = self.post_note()
        self.assertRedirects(response, reverse("admin:core_note_changelist"))
        note = models.Note.objects.get(note="An admin note with an image.")
        self.assertTrue(note.image.name.startswith("notes/images/"))
        self.assertEqual(len(self.files_written()), 1)
