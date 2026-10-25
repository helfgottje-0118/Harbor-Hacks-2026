from backend.app.database import Base, engine, init_db

if __name__ == "__main__":
    Base.metadata.drop_all(bind=engine)
    init_db()
    print("HARBOR demo database reset")
