import pymysql
import time
import random
import threading
from contextlib import contextmanager

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3307,
    "user": "root",
    "password": "root",
    "database": "test",
    "autocommit": False,
    "charset": "utf8mb4"
}

def create_database():
    print("Проверка базы данных...")
    config_without_db = DB_CONFIG.copy()
    config_without_db.pop("database")
    config_without_db["autocommit"] = True

    try:
        conn = pymysql.connect(**config_without_db)
        with conn.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS test")
            print("База данных 'test' создана или уже существует")
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка при создании БД: {e}")
        print("Проверьте, что контейнер запущен на порту 3307")
        return False

@contextmanager
def get_connection():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

def measure_time(func):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        return result, time.perf_counter() - start
    return wrapper

def task1_storage_speed():
    print("Задание 1: Сравнение Storage Engines")
    print("="*50)

    with get_connection() as conn:
        with conn.cursor() as cur:
            for engine in ["InnoDB", "Aria", "MyISAM"]:
                table = f"test_{engine.lower()}"
                cur.execute(f"DROP TABLE IF EXISTS {table}")
                cur.execute(
                    f"CREATE TABLE {table} ("
                    f" id INT AUTO_INCREMENT PRIMARY KEY,"
                    f" val INT, txt VARCHAR(100)"
                    f") ENGINE={engine}"
                )
            conn.commit()
            print("Таблицы созданы")

            results = {}
            for engine in ["InnoDB", "Aria", "MyISAM"]:
                table = f"test_{engine.lower()}"
                times = []
                print(f"Тестирование {engine}...")

                for attempt in range(3):
                    cur.execute(f"TRUNCATE TABLE {table}")
                    conn.commit()

                    start = time.perf_counter()
                    for i in range(0, 50000, 1000):
                        data = [(j, f"row_{j}") for j in range(i, i + 1000)]
                        cur.executemany(
                            f"INSERT INTO {table} (val, txt) VALUES (%s, %s)",
                            data
                        )
                    conn.commit()
                    elapsed = time.perf_counter() - start
                    times.append(elapsed)
                    print(f"  Попытка {attempt + 1}: {elapsed:.3f} с")
                results[engine] = times
                print()

            print("Результаты:")
            print(f"{'Engine':<10} {'Try1':<9} {'Try2':<9} {'Try3':<9} {'Avg':<9}")
            print('-' * 48)
            for engine, times in results.items():
                avg = sum(times) / 3
                t1, t2, t3 = times
                print(f"{engine:<10} {t1:<9.3f} {t2:<9.3f} {t3:<9.3f} {avg:<9.3f}")

    print("Задание 1 выполнено")

def task2_crash_test():
    print("Задание 2: Поведение при сбое")
    print("="*50)

    with get_connection() as conn:
        with conn.cursor() as cur:
            for engine in ["InnoDB", "Aria", "MyISAM"]:
                table = f"crash_{engine.lower()}"
                cur.execute(f"DROP TABLE IF EXISTS {table}")
                cur.execute(
                    f"CREATE TABLE {table} ("
                    f" id INT PRIMARY KEY, data VARCHAR(100)"
                    f") ENGINE={engine}"
                )
            conn.commit()
            print("Таблицы созданы")

            print("Вставка 10 000 записей в каждую таблицу (без COMMIT)...")
            for engine in ["InnoDB", "Aria", "MyISAM"]:
                table = f"crash_{engine.lower()}"
                for start_id in range(0, 10000, 1000):
                    batch = [(i, f"data_{i}") for i in range(start_id, start_id + 1000)]
                    cur.executemany(
                        f"INSERT INTO {table} (id, data) VALUES (%s, %s)",
                        batch
                    )
                print(f"  Вставлено 10000 записей в {table}")

            print("\nВнимание! Сейчас нужно перезапустить контейнер.")
            print("Откройте новое окно PowerShell и выполните:")
            print("docker restart mariadb-lab")
            input("Нажмите Enter после перезапуска контейнера...")

    print("Ожидаем 10 секунд после перезапуска...")
    time.sleep(10)

    print("Проверка данных после сбоя:")
    with get_connection() as conn2:
        with conn2.cursor() as cur2:
            for engine in ["InnoDB", "Aria", "MyISAM"]:
                table = f"crash_{engine.lower()}"
                try:
                    cur2.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur2.fetchone()[0]
                    print(f"{table}: {count} записей")
                except Exception as e:
                    print(f"{table}: Ошибка - {e}")

    print("Задание 2 выполнено")

def task3_isolation_levels():
    print("Задание 3: Уровни изоляции транзакций")
    print("="*50)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS isolation_test")
            cur.execute(
                "CREATE TABLE isolation_test ("
                " id INT PRIMARY KEY, val INT"
                ") ENGINE=InnoDB"
            )
            cur.executemany(
                "INSERT INTO isolation_test VALUES (%s, %s)",
                [(1, 10), (2, 20)]
            )
            conn.commit()
    print("Таблица создана, начальные данные: (1,10), (2,20)")

    print("\nТест 1: READ COMMITTED")
    print("-"*30)

    def session1_rc():
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()
        try:
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cur.execute("START TRANSACTION")

            cur.execute("SELECT * FROM isolation_test")
            print(f"[RC] До вставки: {cur.fetchall()}")

            input("[RC] Нажмите Enter, когда сессия 2 выполнит вставку...")

            cur.execute("SELECT * FROM isolation_test")
            print(f"[RC] После вставки: {cur.fetchall()}")

            conn.commit()
        finally:
            conn.close()

    def session2_insert():
        time.sleep(1)
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO isolation_test VALUES (3, 30)")
            conn.commit()
            print("[RC] Сессия 2: строка (3, 30) вставлена и закоммичена")
        finally:
            conn.close()

    t1 = threading.Thread(target=session1_rc)
    t2 = threading.Thread(target=session2_insert)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE isolation_test")
            cur.executemany(
                "INSERT INTO isolation_test VALUES (%s, %s)",
                [(1, 10), (2, 20)]
            )
            conn.commit()

    print("\nТест 2: REPEATABLE READ")
    print("-"*30)

    def session1_rr():
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()
        try:
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute("START TRANSACTION")

            cur.execute("SELECT * FROM isolation_test")
            print(f"[RR] До вставки: {cur.fetchall()}")

            input("[RR] Нажмите Enter, когда сессия 2 выполнит вставку...")

            cur.execute("SELECT * FROM isolation_test")
            print(f"[RR] После вставки: {cur.fetchall()}")

            conn.commit()
        finally:
            conn.close()

    t1 = threading.Thread(target=session1_rr)
    t2 = threading.Thread(target=session2_insert)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    print("Задание 3 выполнено")

WORDS = [
    "apple", "banana", "orange", "grape", "cherry", "mango",
    "peach", "plum", "strawberry", "blueberry", "raspberry",
    "blackberry", "watermelon", "melon", "pear", "kiwi",
    "pineapple", "lemon", "lime", "coconut"
]

def generate_text(idx):
    selected = random.sample(WORDS, 12)
    if idx % 10 == 0:
        selected.append("apple")
    random.shuffle(selected)
    return " ".join(selected)

def task4_fulltext_speed():
    print("Задание 4: Полнотекстовый поиск")
    print("="*50)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS articles")
            cur.execute(
                "CREATE TABLE articles ("
                " id INT AUTO_INCREMENT PRIMARY KEY,"
                " title VARCHAR(200), body TEXT"
                ") ENGINE=InnoDB"
            )
            conn.commit()
            print("Таблица создана")

            print("Вставка 100 000 записей...")
            for start in range(0, 100000, 1000):
                batch = [
                    (f"title_{i}", generate_text(i))
                    for i in range(start, start + 1000)
                ]
                cur.executemany(
                    "INSERT INTO articles (title, body) VALUES (%s, %s)",
                    batch
                )
                if start % 10000 == 0:
                    print(f"  Вставлено {start + 1000} записей")
            conn.commit()
            print("Вставка завершена")

            print("\nЗамер A: LIKE '%apple%'")
            t0 = time.perf_counter()
            cur.execute("SELECT COUNT(*) FROM articles WHERE body LIKE '%apple%'")
            count_like = cur.fetchone()[0]
            time_like = time.perf_counter() - t0
            print(f"  Время: {time_like:.4f} с")
            print(f"  Найдено: {count_like} записей")

            print("\nСоздание FULLTEXT-индекса...")
            cur.execute("ALTER TABLE articles ADD FULLTEXT INDEX ft_idx (body)")
            conn.commit()
            print("Индекс создан")

            print("\nЗамер B: MATCH(body) AGAINST('apple')")
            t0 = time.perf_counter()
            cur.execute(
                "SELECT COUNT(*) FROM articles "
                "WHERE MATCH(body) AGAINST('apple')"
            )
            count_ft = cur.fetchone()[0]
            time_ft = time.perf_counter() - t0
            print(f"  Время: {time_ft:.4f} с")
            print(f"  Найдено: {count_ft} записей")

            print("\nEXPLAIN LIKE:")
            cur.execute(
                "EXPLAIN SELECT COUNT(*) FROM articles "
                "WHERE body LIKE '%apple%'"
            )
            for row in cur.fetchall():
                print(f"  {row}")

            print("\nEXPLAIN MATCH:")
            cur.execute(
                "EXPLAIN SELECT COUNT(*) FROM articles "
                "WHERE MATCH(body) AGAINST('apple')"
            )
            for row in cur.fetchall():
                print(f"  {row}")

    print("Задание 4 выполнено")

def task5_ranking():
    print("Задание 5: Ранжирование результатов")
    print("="*50)

    with get_connection() as conn:
        with conn.cursor() as cur:
            print("\nNatural Language Mode ('apple orange')")
            print("-"*40)

            cur.execute("""
                SELECT id, title,
                       MATCH(body) AGAINST('apple orange') AS relevance
                FROM articles
                WHERE MATCH(body) AGAINST('apple orange')
                ORDER BY relevance DESC
                LIMIT 10
            """)

            print(f"{'ID':<6} {'Title':<25} {'Relevance':<15}")
            print("-"*50)
            for row in cur.fetchall():
                print(f"{row[0]:<6} {row[1][:25]:<25} {row[2]:<15.4f}")

            print("\nBoolean Mode ('+apple -banana')")
            print("-"*40)

            cur.execute("""
                SELECT id, title,
                       MATCH(body) AGAINST('+apple -banana' IN BOOLEAN MODE) AS relevance
                FROM articles
                WHERE MATCH(body) AGAINST('+apple -banana' IN BOOLEAN MODE)
                ORDER BY relevance DESC
                LIMIT 10
            """)

            print(f"{'ID':<6} {'Title':<25} {'Relevance':<15}")
            print("-"*50)
            for row in cur.fetchall():
                print(f"{row[0]:<6} {row[1][:25]:<25} {row[2]:<15.4f}")

    print("Задание 5 выполнено")

WORDS2 = [
    "database", "sql", "index", "query", "transaction",
    "lock", "deadlock", "isolation", "commit", "rollback",
    "backup", "recovery", "replication", "cluster"
]

def generate_text2(i):
    return " ".join(random.sample(WORDS2, 10)) + f" {i}"

def task6_insert_overhead():
    print("Задание 6: Влияние FULLTEXT на скорость вставки")
    print("="*50)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS articles_no_ft")
            cur.execute("""
                CREATE TABLE articles_no_ft (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    body TEXT
                ) ENGINE=InnoDB
            """)

            cur.execute("DROP TABLE IF EXISTS articles_ft")
            cur.execute("""
                CREATE TABLE articles_ft (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    body TEXT,
                    FULLTEXT INDEX ft_idx (body)
                ) ENGINE=InnoDB
            """)
            conn.commit()
            print("Таблицы созданы")

            print("Генерация 20 000 записей...")
            data = [(generate_text2(i),) for i in range(20000)]
            print("Данные сгенерированы")

            print("\nВставка 20 000 записей без индекса...")
            t0 = time.perf_counter()
            for s in range(0, 20000, 1000):
                cur.executemany(
                    "INSERT INTO articles_no_ft (body) VALUES (%s)",
                    data[s:s+1000]
                )
                conn.commit()
            time_no = time.perf_counter() - t0
            print(f"Время без индекса: {time_no:.3f} с")

            print("\nВставка 20 000 записей с FULLTEXT-индексом...")
            t0 = time.perf_counter()
            for s in range(0, 20000, 1000):
                cur.executemany(
                    "INSERT INTO articles_ft (body) VALUES (%s)",
                    data[s:s+1000]
                )
                conn.commit()
            time_ft = time.perf_counter() - t0
            print(f"Время с индексом: {time_ft:.3f} с")

            overhead = (time_ft - time_no) / time_no * 100

            print("\nРезультаты:")
            print(f"Без индекса:     {time_no:.3f} с")
            print(f"C FULLTEXT:      {time_ft:.3f} с")
            print(f"Накладные расходы: +{overhead:.1f}%")

    print("Задание 6 выполнено")

if __name__ == "__main__":
    if not create_database():
        print("Не удалось подключиться к БД. Проверьте контейнер.")
        exit(1)

    task1_storage_speed()