import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_secret_key'
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb+srv://sumanranait3395:yWj204zHMVmZzYq2@itcoding.z7f5cyu.mongodb.net/'
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static/uploads')
