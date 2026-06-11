import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_helper = Database()

async def connect_to_mongo():
    logger.info(f"Connecting to MongoDB at {settings.MONGODB_URL}...")
    try:
        db_helper.client = AsyncIOMotorClient(settings.MONGODB_URL)
        db_helper.db = db_helper.client[settings.DATABASE_NAME]
        # Ping the database to verify the connection
        await db_helper.client.admin.command('ping')
        logger.info(f"Successfully connected to MongoDB database: {settings.DATABASE_NAME}")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise e

async def close_mongo_connection():
    if db_helper.client:
        logger.info("Closing MongoDB connection...")
        db_helper.client.close()
        logger.info("MongoDB connection closed.")

def get_database():
    """
    Dependency or helper to access the MongoDB database instance.
    """
    return db_helper.db
