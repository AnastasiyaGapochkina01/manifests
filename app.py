from flask import Flask, request, Response
from prometheus_client import generate_latest, Counter, Histogram, REGISTRY
import psycopg2
import time
import os

app = Flask(__name__)

app.config['PG_HOST'] = os.getenv('PG_HOST', 'localhost')
app.config['PG_PORT'] = os.getenv('PG_PORT', '5432')
app.config['PG_DATABASE'] = os.getenv('PG_DATABASE', 'postgres')
app.config['PG_USER'] = os.getenv('PG_USER', 'postgres')
app.config['PG_PASSWORD'] = os.getenv('PG_PASSWORD', 'postgres')

REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP Requests',
    ['method', 'endpoint', 'status_code']
)

ERROR_COUNT = Counter(
    'http_errors_total',
    'Total HTTP Errors',
    ['method', 'endpoint', 'status_code']
)

RESPONSE_TIME = Histogram(
    'http_response_time_seconds',
    'HTTP Response Time',
    ['method', 'endpoint']
)

def get_db_connection():
    """Создает подключение к PostgreSQL."""
    return psycopg2.connect(
        host=app.config['PG_HOST'],
        port=app.config['PG_PORT'],
        dbname=app.config['PG_DATABASE'],
        user=app.config['PG_USER'],
        password=app.config['PG_PASSWORD']
    )

def init_db():
    """Создает таблицу logs, если она не существует."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            endpoint VARCHAR(255),
            method VARCHAR(10),
            status_code INTEGER,
            response_time FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

@app.before_request
def start_timer():
    """Старт отсчета времени выполнения запроса."""
    request.start_time = time.time()

@app.after_request
def log_request(response):
    """Логирует данные запроса в PostgreSQL и обновляет метрики."""
    resp_time = time.time() - request.start_time

    endpoint = request.path
    method = request.method
    status_code = response.status_code

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO logs (endpoint, method, status_code, response_time)
            VALUES (%s, %s, %s, %s)
        ''', (endpoint, method, status_code, resp_time))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        app.logger.error(f"Ошибка записи в базу данных: {e}")

    REQUEST_COUNT.labels(method, endpoint, status_code).inc()
    if status_code >= 400:
        ERROR_COUNT.labels(method, endpoint, status_code).inc()
    RESPONSE_TIME.labels(method, endpoint).observe(resp_time)

    return response

@app.route('/generate-load')
def generate_load():
    """
    Генерирует CPU-нагрузку для тестирования метрик.
    Параметры:
        ?n=10000 - количество итераций (по умолчанию 1000000)
    """
    iterations = int(request.args.get('n', 1000000))

    # CPU-intensive calculation
    result = 0
    for i in range(iterations):
        result += i * i
        result -= i * 0.5
        result = abs(result)

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT pg_sleep(0.1)')  # Имитация долгого SQL-запроса
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        app.logger.error(f"Database error: {e}")
        return "Error", 500

    return f"Load generated with {iterations} iterations", 200

@app.route('/metrics')
def metrics():
    """Эндпоинт для сбора метрик Prometheus."""
    return Response(generate_latest(REGISTRY), mimetype='text/plain')

@app.route('/')
def index():
    """Тестовый эндпоинт."""
    return 'Main Page'

@app.route('/error')
def trigger_error():
    """Эндпоинт для генерации ошибки."""
    return 'Server Error', 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)