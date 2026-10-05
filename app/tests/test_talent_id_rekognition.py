"""AWS Rekognition adapter coverage for Talent ID."""

from botocore.exceptions import ClientError

from app.infrastructure.talent_id_rekognition import (
    FaceAssociationError,
    FaceNotDetectedError,
    RekognitionBiometricProvider,
)


class FakeRekognitionClient:
    def __init__(self):
        self.created = []
        self.deleted = []
        self.search_response = {"UserMatches": []}
        self.index_response = {
            "FaceRecords": [{"Face": {"FaceId": "face-1"}}],
        }
        self.associate_response = {
            "AssociatedFaces": [{"FaceId": "face-1"}],
        }
        self.conflict_on_create = False
        self.invalid_parameter_on_create = False
        self.users = []
        self.faces = []

    def create_user(self, **kwargs):
        self.created.append(kwargs)
        if self.conflict_on_create:
            raise ClientError(
                {"Error": {"Code": "ConflictException", "Message": "exists"}},
                "CreateUser",
            )
        if self.invalid_parameter_on_create:
            raise ClientError(
                {
                    "Error": {
                        "Code": "InvalidParameterException",
                        "Message": "Request has invalid parameters",
                    }
                },
                "CreateUser",
            )
        return {}

    def list_users(self, **kwargs):
        return {"Users": list(self.users)}

    def list_faces(self, **kwargs):
        return {"Faces": list(self.faces)}

    def index_faces(self, **kwargs):
        return self.index_response

    def associate_faces(self, **kwargs):
        return self.associate_response

    def delete_faces(self, **kwargs):
        self.deleted.append(kwargs)
        return {}

    def search_users_by_image(self, **kwargs):
        return self.search_response


def _provider(client):
    return RekognitionBiometricProvider(
        client=client,
        collection_id="talent-intelligence-employees",
        association_threshold=90.0,
    )


def test_enroll_creates_user_indexes_and_associates_face():
    client = FakeRekognitionClient()

    result = _provider(client).enroll(
        provider_user_id="employee-1",
        image_bytes=b"jpeg",
    )

    assert result.provider_user_id == "employee-1"
    assert result.face_ids == ("face-1",)
    assert client.created[0]["UserId"] == "employee-1"


def test_enroll_accepts_existing_rekognition_user():
    client = FakeRekognitionClient()
    client.conflict_on_create = True

    result = _provider(client).enroll(
        provider_user_id="employee-1",
        image_bytes=b"jpeg",
    )

    assert result.face_ids == ("face-1",)




def test_enroll_accepts_existing_user_when_rekognition_returns_invalid_parameter():
    client = FakeRekognitionClient()
    client.invalid_parameter_on_create = True
    client.users = [{"UserId": "employee-1", "UserStatus": "ACTIVE"}]

    result = _provider(client).enroll(
        provider_user_id="employee-1",
        image_bytes=b"jpeg",
    )

    assert result.face_ids == ("face-1",)


def test_enroll_does_not_hide_invalid_parameter_for_unknown_user():
    client = FakeRekognitionClient()
    client.invalid_parameter_on_create = True
    client.users = []

    try:
        _provider(client).enroll(
            provider_user_id="employee-1",
            image_bytes=b"jpeg",
        )
    except ClientError as exc:
        assert exc.response["Error"]["Code"] == "InvalidParameterException"
    else:
        raise AssertionError("ClientError was not raised")


def test_enroll_rejects_image_without_usable_face():
    client = FakeRekognitionClient()
    client.index_response = {"FaceRecords": []}

    try:
        _provider(client).enroll(
            provider_user_id="employee-1",
            image_bytes=b"jpeg",
        )
    except FaceNotDetectedError:
        pass
    else:
        raise AssertionError("FaceNotDetectedError was not raised")


def test_enroll_accepts_face_that_rekognition_reports_as_already_associated():
    client = FakeRekognitionClient()
    client.associate_response = {
        "AssociatedFaces": [],
        "UnsuccessfulFaceAssociations": [],
        "UserStatus": "ACTIVE",
    }
    client.faces = [
        {
            "FaceId": "face-1",
            "UserId": "employee-1",
        }
    ]

    result = _provider(client).enroll(
        provider_user_id="employee-1",
        image_bytes=b"jpeg",
    )

    assert result.face_ids == ("face-1",)
    assert client.deleted == []


def test_enroll_cleans_indexed_face_when_association_fails():
    client = FakeRekognitionClient()
    client.associate_response = {"AssociatedFaces": []}

    try:
        _provider(client).enroll(
            provider_user_id="employee-1",
            image_bytes=b"jpeg",
        )
    except FaceAssociationError:
        pass
    else:
        raise AssertionError("FaceAssociationError was not raised")

    assert client.deleted[0]["FaceIds"] == ["face-1"]


def test_recognition_returns_best_user_match():
    client = FakeRekognitionClient()
    client.search_response = {
        "UserMatches": [
            {
                "User": {"UserId": "employee-1"},
                "Similarity": 99.6,
            }
        ]
    }

    match = _provider(client).recognize(
        image_bytes=b"jpeg",
        threshold=98.0,
    )

    assert match is not None
    assert match.provider_user_id == "employee-1"
    assert match.similarity == 99.6
