from app.core.errors import InvalidCredentialsError
from app.core.security import create_access_token, verify_password
from app.repositories.users import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def authenticate(self, username: str, password: str) -> TokenResponse:
        user = self.repository.get_by_username(username)
        if user is None or not verify_password(password, user["password_hash"]):
            raise InvalidCredentialsError()

        token = create_access_token(user["user_id"], user["org_id"], user["role"])
        return TokenResponse(access_token=token)
