
import hashlib
import hmac
import secrets
from datetime import datetime

from database import execute, query


def hash_password(password):
    salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        260000
    ).hex()

    return f"{salt}${password_hash}"


def verify_password(password, stored_hash):
    try:
        salt, expected_hash = stored_hash.split("$", 1)

        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            260000
        ).hex()

        return hmac.compare_digest(actual_hash, expected_hash)

    except (ValueError, AttributeError):
        return False


def signup(business_name, full_name, username, password, currency="PKR"):
    business_name = business_name.strip()
    full_name = full_name.strip()
    username = username.strip().lower()

    if not business_name or not full_name or not username:
        raise ValueError("All required fields must be completed.")

    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters.")

    if query(
        "SELECT id FROM users WHERE username = :username",
        {"username": username}
    ):
        raise ValueError("This username is already registered.")

    now = datetime.now().isoformat()

    business_id = execute(
        """
        INSERT INTO businesses
        (name, owner, currency, created_at)
        VALUES (:name, :owner, :currency, :created_at)
        """,
        {
            "name": business_name,
            "owner": full_name,
            "currency": currency,
            "created_at": now
        }
    )

    execute(
        """
        INSERT INTO users
        (business_id, username, password_hash, full_name,
         role, active, created_at)
        VALUES (:business_id, :username, :password_hash,
                :full_name, 'owner', 1, :created_at)
        """,
        {
            "business_id": business_id,
            "username": username,
            "password_hash": hash_password(password),
            "full_name": full_name,
            "created_at": now
        }
    )

    return business_id


def login(username, password):
    username = username.strip().lower()

    users = query(
        """
        SELECT id, business_id, username, password_hash,
               full_name, role, active
        FROM users
        WHERE username = :username
        """,
        {"username": username}
    )

    if not users:
        return None

    user = users[0]

    if not user["active"]:
        return None

    if not verify_password(password, user["password_hash"]):
        return None

    user.pop("password_hash", None)
    return user