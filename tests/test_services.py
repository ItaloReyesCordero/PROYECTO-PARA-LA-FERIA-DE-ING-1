from __future__ import annotations

import pytest

from desglosa.ir import Import, Project, SourceFile
from desglosa.services import SERVICES, detect_services, service_of, services_by_file


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("redis", "redis"),
        ("redis.asyncio", "redis"),
        ("ioredis", "redis"),
        ("Illuminate\\Support\\Facades\\Redis", "redis"),
        ("StackExchange.Redis", "redis"),
        ("PDO", "sql"),
        ("java.sql.Connection", "sql"),
        ("com.mysql.cj.jdbc.Driver", "mysql"),
        ("psycopg2.extras", "postgres"),
        ("github.com/lib/pq", "postgres"),
        ("System.Data.SQLite", "sqlite"),  # antes que el genérico System.Data
        ("System.Data.SqlClient", "sql"),
        ("<sqlite3.h>", "sqlite"),
        ("mongoose", "mongodb"),
        ("smtplib", "correo"),
        ("nodemailer", "correo"),
        ("requests", "http"),
        ("axios", "http"),
        ("GuzzleHttp\\Client", "http"),
        ("net/http", "http"),
        ("pika", "colas"),
        ("boto3", "nube"),
        ("@aws-sdk/client-s3", "nube"),
        ("Aws\\S3\\S3Client", "nube"),
        ("stripe", "pagos"),
        ("serial", "serie"),
        ("<termios.h>", "serie"),
    ],
)
def test_known_imports(module, expected):
    assert service_of(module) == expected


@pytest.mark.parametrize(
    "module",
    ["fs", "os", "<stdio.h>", "java.util.List", "System.IO", "requestsx", "redisearch_local",
     "./db.js", "../redis", "awsome", "", "factura"],
)
def test_unrelated_imports(module):
    assert service_of(module) is None


def _project(files, imports):
    return Project(
        root_name="p",
        files=tuple(SourceFile(f, "python", "0", 1, True, 0, None) for f in files),
        symbols=(),
        imports=tuple(Import(f, m, None, line) for f, m, line in imports),
        calls=(),
        flows=(),
        tables=(),
        fks=(),
        table_access=(),
        warnings=(),
    )


def test_local_modules_are_not_services():
    # Un serial.py propio no es el puerto serie; un paquete redis/ propio no es Redis.
    p = _project(
        ["app/serial.py", "redis/client.py", "main.py"],
        [("main.py", "serial", 1), ("main.py", "redis.client", 2), ("main.py", "smtplib", 3)],
    )
    assert [u.service for u in detect_services(p)] == ["correo"]


def test_java_com_folder_does_not_hide_libraries():
    p = _project(
        ["src/main/java/com/acme/App.java", "src/main/java/com/acme/Repo.java"],
        [
            ("src/main/java/com/acme/App.java", "com.acme.Repo", 1),
            ("src/main/java/com/acme/Repo.java", "com.mysql.cj.jdbc.Driver", 2),
        ],
    )
    uses = detect_services(p)
    assert [(u.service, u.module) for u in uses] == [("mysql", "com.mysql.cj.jdbc.Driver")]
    assert services_by_file(uses) == {
        "src/main/java/com/acme/Repo.java": {"mysql": ["com.mysql.cj.jdbc.Driver"]}
    }


def test_service_table_is_well_formed():
    keys = [s.key for s in SERVICES]
    assert len(keys) == len(set(keys))
    for s in SERVICES:
        assert s.group in ("bd", "externo")
        assert all(p == p.lower() and p.strip() == p for p in s.patterns)
