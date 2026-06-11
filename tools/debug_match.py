import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.nlp import extract_skills_from_text
from app.services.matcher import match_resume_to_job

cv_text = '''Programming Languages: Python, JavaScript (ES6+), SQL
Frontend Development: React.js, HTML5, CSS3, Responsive Design, Component Architecture
Backend Development: Node.js, Express.js, REST API Design, JWT Authentication, Bcrypt
Database Technologies: MongoDB, Mongoose ODM, MySQL
AI / Machine Learning: Machine Learning, Deep Learning, CNNs, TensorFlow, YOLOv8, Scikit-learn
Computer Vision & OCR: OpenCV, EasyOCR, Image Processing, Real-Time Object Detection
Data Science: Data Analysis, Feature Engineering, Model Evaluation, Data Preprocessing
Tools & Platforms: Git, GitHub, Jupyter Notebook, VS Code, FastAPI'''

skills_list = [
    'Python', 'JavaScript', 'React.js', 'HTML5', 'CSS3', 'Responsive Design', 'Component Architecture',
    'Node.js', 'Express.js', 'REST API Design', 'JWT Authentication', 'Bcrypt',
    'MongoDB', 'Mongoose ODM', 'MySQL', 'Machine Learning', 'Deep Learning', 'CNNs', 'TensorFlow',
    'YOLO', 'Scikit-learn', 'OpenCV', 'EasyOCR', 'Image Processing', 'Real-Time Object Detection',
    'Data Analysis', 'Feature Engineering', 'Model Evaluation', 'Data Preprocessing', 'Git', 'GitHub', 'Jupyter Notebook', 'VS Code', 'FastAPI'
]
required_skills = [
    'Python', 'Machine Learning', 'Deep Learning', 'TensorFlow', 'OpenCV', 'YOLO', 'OCR', 'Computer Vision',
    'Data Science', 'Scikit-learn', 'Git', 'GitHub', 'FastAPI', 'MongoDB', 'React.js'
]

extracted = extract_skills_from_text(cv_text, skills_list)
print('EXTRACTED:', extracted)

result = asyncio.get_event_loop().run_until_complete(
    match_resume_to_job(cv_text, 'AI Engineer', required_skills, extracted)
)
print('RESULT:', result)
