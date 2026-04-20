import redis
from rq import Worker, Queue, Connection
from config import settings

# 队列列表
listen = ['default', 'high', 'low']

# 建立 Redis 连接
conn = redis.from_url(settings.redis_url)

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        print("Starting RQ Worker...")
        worker.work()
