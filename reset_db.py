from app import db, create_tables, app

with app.app_context():
    db.drop_all()   # Drops all existing tables
    db.create_all() # Creates tables using the updated models
    create_tables() # Adds default admin user
    print("Database reset successfully!")