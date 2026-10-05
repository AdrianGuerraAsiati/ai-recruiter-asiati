"""AWS Rekognition adapter for Talent ID biometrics."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from botocore.exceptions import ClientError

from app.config import get_aws_region
from app.infrastructure.bedrock.session import get_cached_session


class FaceNotDetectedError(ValueError):
    pass


class FaceAssociationError(ValueError):
    pass


@dataclass(frozen=True)
class EnrollmentResult:
    provider_user_id: str
    face_ids: tuple[str, ...]


@dataclass(frozen=True)
class RecognitionMatch:
    provider_user_id: str
    similarity: float


class RekognitionBiometricProvider:
    provider_name = "aws_rekognition"

    def __init__(
        self,
        *,
        client: Any,
        collection_id: str,
        association_threshold: float,
    ) -> None:
        self._client = client
        self._collection_id = collection_id
        self._association_threshold = association_threshold

    def enroll(
        self,
        *,
        provider_user_id: str,
        image_bytes: bytes,
    ) -> EnrollmentResult:
        self._ensure_user(provider_user_id)

        indexed = self._client.index_faces(
            CollectionId=self._collection_id,
            Image={"Bytes": image_bytes},
            MaxFaces=1,
            QualityFilter="AUTO",
            DetectionAttributes=[],
        )
        face_ids = tuple(
            record["Face"]["FaceId"]
            for record in indexed.get("FaceRecords", [])
            if record.get("Face", {}).get("FaceId")
        )
        if not face_ids:
            raise FaceNotDetectedError("No se detectó un rostro utilizable.")

        association = self._client.associate_faces(
            CollectionId=self._collection_id,
            UserId=provider_user_id,
            FaceIds=list(face_ids),
            UserMatchThreshold=self._association_threshold,
            ClientRequestToken=uuid4().hex,
        )
        associated = tuple(
            face["FaceId"]
            for face in association.get("AssociatedFaces", [])
            if face.get("FaceId")
        )
        if len(associated) != len(face_ids):
            if self._faces_belong_to_user(
                provider_user_id=provider_user_id,
                face_ids=face_ids,
            ):
                associated = face_ids
            else:
                self._client.delete_faces(
                    CollectionId=self._collection_id,
                    FaceIds=list(face_ids),
                )
                raise FaceAssociationError(
                    "El rostro no pudo asociarse al empleado."
                )

        return EnrollmentResult(
            provider_user_id=provider_user_id,
            face_ids=associated,
        )

    def recognize(
        self,
        *,
        image_bytes: bytes,
        threshold: float,
    ) -> RecognitionMatch | None:
        response = self._client.search_users_by_image(
            CollectionId=self._collection_id,
            Image={"Bytes": image_bytes},
            UserMatchThreshold=threshold,
            MaxUsers=1,
            QualityFilter="AUTO",
        )
        matches = response.get("UserMatches", [])
        if not matches:
            return None

        best = matches[0]
        provider_user_id = best.get("User", {}).get("UserId")
        similarity = best.get("Similarity")
        if provider_user_id is None or similarity is None:
            return None

        return RecognitionMatch(
            provider_user_id=str(provider_user_id),
            similarity=float(similarity),
        )

    def _ensure_user(self, provider_user_id: str) -> None:
        try:
            self._client.create_user(
                CollectionId=self._collection_id,
                UserId=provider_user_id,
                ClientRequestToken=uuid4().hex,
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "ConflictException":
                return
            if code == "InvalidParameterException" and self._user_exists(provider_user_id):
                return
            raise

    def _faces_belong_to_user(
        self,
        *,
        provider_user_id: str,
        face_ids: tuple[str, ...],
    ) -> bool:
        expected = set(face_ids)
        matched = set()
        next_token = None

        while True:
            params = {
                "CollectionId": self._collection_id,
                "MaxResults": 100,
            }
            if next_token:
                params["NextToken"] = next_token

            response = self._client.list_faces(**params)
            for face in response.get("Faces", []):
                face_id = str(face.get("FaceId") or "")
                if face_id in expected and str(face.get("UserId") or "") == provider_user_id:
                    matched.add(face_id)

            if matched == expected:
                return True

            next_token = response.get("NextToken")
            if not next_token:
                return False

    def _user_exists(self, provider_user_id: str) -> bool:
        next_token = None
        while True:
            params = {
                "CollectionId": self._collection_id,
                "MaxResults": 100,
            }
            if next_token:
                params["NextToken"] = next_token

            response = self._client.list_users(**params)
            if any(
                str(user.get("UserId") or "") == provider_user_id
                for user in response.get("Users", [])
            ):
                return True

            next_token = response.get("NextToken")
            if not next_token:
                return False


def get_rekognition_client():
    """Use the same Roles Anywhere/default AWS session as the recruiter."""
    return get_cached_session().client(
        "rekognition",
        region_name=get_aws_region(),
    )
