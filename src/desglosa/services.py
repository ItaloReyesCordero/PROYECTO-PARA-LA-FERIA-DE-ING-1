"""Servicios externos detectados por los imports (Bloque 3, mapa de arquitectura).

Sin IA y sin adivinar: un archivo "usa Redis" solo si importa una librería conocida de
Redis. La tabla es de datos, como `langs/builtins.py`; agregar una librería es agregar
una línea.

Un import coincide con un patrón si es igual o empieza con el patrón seguido de un
separador (`.`, `/`, `\\`, `::` o `:`). Se compara en minúsculas y sin `<>` ni comillas.
Los imports que apuntan a un archivo o carpeta del propio proyecto no cuentan (un
`serial.py` propio no es el puerto serie).
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass

from desglosa.ir import Project


@dataclass(frozen=True)
class Service:
    key: str
    name: str
    group: str  # "bd" (base de datos) | "externo"
    patterns: tuple[str, ...]


SERVICES: tuple[Service, ...] = (
    Service("mysql", "MySQL", "bd", (
        "pymysql", "mysqldb", "mysql.connector", "aiomysql", "mysql", "mysql2", "com.mysql",
        "github.com/go-sql-driver/mysql", "mysql.data", "mysqlconnector",
    )),
    Service("postgres", "PostgreSQL", "bd", (
        "psycopg2", "psycopg", "asyncpg", "pg", "pg-promise", "postgres", "org.postgresql",
        "github.com/lib/pq", "github.com/jackc/pgx", "npgsql",
    )),
    Service("sqlite", "SQLite", "bd", (
        "sqlite3", "better-sqlite3", "microsoft.data.sqlite", "system.data.sqlite",
        "github.com/mattn/go-sqlite3", "rusqlite", "sqlite3.h",
    )),
    Service("mongodb", "MongoDB", "bd", (
        "pymongo", "motor", "mongoose", "mongodb", "com.mongodb",
        "org.springframework.data.mongodb", "mongodb.driver", "go.mongodb.org/mongo-driver",
        "mongoid",
    )),
    Service("redis", "Redis", "bd", (
        "redis", "aioredis", "ioredis", "predis", "illuminate\\support\\facades\\redis",
        "redis.clients.jedis", "org.springframework.data.redis", "io.lettuce",
        "stackexchange.redis", "github.com/go-redis/redis", "github.com/redis/go-redis",
        "github.com/gomodule/redigo",
    )),
    Service("sql", "Base de datos SQL", "bd", (
        "pdo", "illuminate\\database", "illuminate\\support\\facades\\db", "doctrine\\dbal",
        "doctrine\\orm", "sqlalchemy", "django.db", "peewee", "sequelize", "typeorm",
        "@prisma/client", "knex", "drizzle-orm", "javax.persistence", "jakarta.persistence",
        "org.hibernate", "java.sql", "javax.sql", "org.springframework.jdbc",
        "org.springframework.data.jpa", "microsoft.entityframeworkcore",
        "system.data.sqlclient", "microsoft.data.sqlclient", "system.data", "gorm.io/gorm",
        "database/sql", "github.com/jmoiron/sqlx", "diesel", "sqlx", "active_record",
        "activerecord", "sequel", "org.jetbrains.exposed", "androidx.room", "coredata", "grdb",
    )),
    Service("correo", "Correo (email)", "externo", (
        "smtplib", "email.mime", "email.message", "flask_mail", "django.core.mail",
        "nodemailer", "@sendgrid/mail", "phpmailer\\phpmailer",
        "illuminate\\support\\facades\\mail", "illuminate\\mail", "symfony\\component\\mailer",
        "javax.mail", "jakarta.mail",
        "org.springframework.mail", "system.net.mail", "mailkit", "net/smtp", "action_mailer",
        "lettre",
    )),
    Service("http", "HTTP / APIs web", "externo", (
        "requests", "httpx", "aiohttp", "urllib.request", "urllib3", "http.client", "axios",
        "node-fetch", "got", "superagent", "guzzlehttp", "illuminate\\support\\facades\\http",
        "symfony\\component\\httpclient", "java.net.http", "okhttp3", "org.apache.http",
        "org.springframework.web.client", "org.springframework.web.reactive.function.client",
        "retrofit2", "system.net.http", "restsharp", "net/http", "reqwest", "hyper",
        "alamofire", "faraday", "httparty", "io.ktor.client", "curl/curl.h",
    )),
    Service("colas", "Colas de mensajes", "externo", (
        "pika", "kafka", "confluent_kafka", "kafkajs", "amqplib", "celery", "bull", "bullmq",
        "kombu", "rq", "org.apache.kafka", "com.rabbitmq", "org.springframework.amqp",
        "org.springframework.kafka", "rabbitmq.client", "confluent.kafka",
        "github.com/segmentio/kafka-go", "github.com/streadway/amqp",
        "github.com/rabbitmq/amqp091-go", "illuminate\\support\\facades\\queue", "phpamqplib",
    )),
    Service("nube", "Nube (AWS, Google, Azure)", "externo", (
        "boto3", "botocore", "aws-sdk", "@aws-sdk", "google.cloud", "@google-cloud",
        "firebase_admin", "firebase-admin", "firebase", "azure", "@azure", "com.amazonaws",
        "software.amazon.awssdk", "com.google.cloud", "com.google.firebase", "amazon",
        "github.com/aws/aws-sdk-go", "github.com/aws/aws-sdk-go-v2", "cloud.google.com/go", "aws",
    )),
    Service("pagos", "Pagos", "externo", (
        "stripe", "paypalrestsdk", "paypal", "mercadopago", "culqi", "braintree", "com.stripe",
        "github.com/stripe/stripe-go",
    )),
    Service("serie", "Puerto serie", "externo", (
        "serial", "serialport", "@serialport", "system.io.ports", "com.fazecast.jserialcomm",
        "jssc", "gnu.io", "termios.h", "github.com/tarm/serial", "go.bug.st/serial",
    )),
)

BY_KEY = {s.key: s for s in SERVICES}
_SEP = re.compile(r"[./\\:]")


@dataclass(frozen=True)
class ServiceUse:
    service: str  # clave de SERVICES
    file: str
    module: str  # el import tal como está en el código
    line: int


def _normalize(module: str) -> str:
    return module.strip().strip("<>\"'`").strip().lower()


def _matches(module: str, pattern: str) -> bool:
    if module == pattern:
        return True
    if not module.startswith(pattern):
        return False
    rest = module[len(pattern):]
    return bool(_SEP.match(rest))


def _local_paths(project: Project) -> set[str]:
    """Terminaciones de las rutas de carpetas y archivos (sin extensión) del proyecto.

    `src/main/java/com/acme/App.java` aporta `app`, `acme/app`, `com/acme/app`… y sus
    carpetas `acme`, `com/acme`, `java/com/acme`…, todo en minúsculas.
    """
    out: set[str] = set()
    for f in project.files:
        parts = f.path.lower().split("/")
        parts[-1] = posixpath.splitext(parts[-1])[0]
        for end in range(1, len(parts) + 1):
            for start in range(end):
                out.add("/".join(parts[start:end]))
    return out


def _is_local(module: str, local: set[str]) -> bool:
    """¿El import apunta a algo del proyecto? Se prueban sus prefijos de al menos dos
    partes (uno si solo tiene una): así `com.mysql…` no se confunde con la carpeta `com/`
    de un proyecto Java, pero `App\\Models\\Factura` sí es local."""
    parts = [p for p in _SEP.split(module) if p]
    if not parts:
        return False
    shortest = min(2, len(parts))
    return any("/".join(parts[:k]) in local for k in range(len(parts), shortest - 1, -1))


def service_of(module: str, local: set[str] = frozenset()) -> str | None:
    """Clave del servicio que importa `module`, o None. El primero de SERVICES gana."""
    norm = _normalize(module)
    if not norm or norm.startswith("."):  # import relativo: es del proyecto
        return None
    if _is_local(norm, local):
        return None
    for svc in SERVICES:
        for pattern in svc.patterns:
            if _matches(norm, pattern):
                return svc.key
    return None


def detect_services(project: Project) -> list[ServiceUse]:
    """Cada import que corresponde a un servicio conocido, ordenado por archivo y línea."""
    local = _local_paths(project)
    out = []
    for imp in project.imports:
        key = service_of(imp.module_text, local)
        if key is not None:
            out.append(ServiceUse(key, imp.file, imp.module_text, imp.line))
    return sorted(out, key=lambda u: (u.file, u.line, u.service, u.module))


def services_by_file(uses: list[ServiceUse]) -> dict[str, dict[str, list[str]]]:
    """Archivo → servicio → imports que lo delatan (sin repetir)."""
    out: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for u in uses:
        mods = out[u.file][u.service]
        if u.module not in mods:
            mods.append(u.module)
    return {f: dict(sorted(s.items())) for f, s in sorted(out.items())}
